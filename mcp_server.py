"""
MCP Server for SSA Data Assistant.

Exposes the SSA database schema, golden queries, and read-only query
execution as MCP tools — letting Claude generate SQL natively without
routing through OpenAI for SQL generation.

Usage (stdio, for Claude Desktop / Claude Code):
    python mcp_server.py

Usage (HTTP, for remote access):
    python mcp_server.py --transport streamable-http --port 8001

Claude Code config (~/.claude/settings.json):
    {
      "mcpServers": {
        "ssa-data-assistant": {
          "command": "python",
          "args": ["<path-to>/mcp_server.py"],
          "env": {
            "PG_DSN_READONLY": "...",
            "PG_SEARCH_PATH": "Project_Master_Database",
            "OPENAI_API_KEY": "..."
          }
        }
      }
    }

Note: OPENAI_API_KEY is used only for text-embedding-3-small (schema/query
retrieval), NOT for SQL generation. If omitted, the server falls back to
keyword-only schema routing with reduced accuracy.
"""
from __future__ import annotations

import io
import json
import os
import sys
from contextlib import redirect_stdout
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load .env before any app imports (they read env vars at import time)
ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

from app.catalog import (
    Catalog,
    CatalogLoadError,
    load_catalog,
    suggest_schema_snippet,
)
from app.config_loader import (
    load_aliases,
    load_allowed_values,
    load_column_semantics,
    load_disambiguation_rules,
    load_join_map,
)
from app.db import run_select
from app.query_metrics import fetch_verified_queries
from app.rag import (
    DocumentationStore,
    GoldenQueryStore,
    SchemaRetriever,
    index_config_as_documentation,
)
from app.schema_enrichment import load_schema_descriptions
from app.sql_validator import SQLValidationError, build_sqlglot_schema, validate_sql

from mcp.server.fastmcp import FastMCP


# ---------------------------------------------------------------------------
# Logging (stderr only — stdout is the MCP protocol channel)
# ---------------------------------------------------------------------------

def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------------------
# Initialize catalog, config, and RAG stores
# ---------------------------------------------------------------------------

SCHEMA = os.getenv("PG_SEARCH_PATH", "Project_Master_Database")
_log(f"[mcp] Initializing (schema={SCHEMA})")

# 1. Database catalog
try:
    CATALOG: Catalog | None = load_catalog(SCHEMA)
    SQLGLOT_SCHEMA = build_sqlglot_schema(CATALOG)
    _log(f"[mcp] Catalog: {len(CATALOG.tables)} tables, {len(CATALOG.fks)} FKs")
except (CatalogLoadError, Exception) as exc:
    _log(f"[mcp] WARNING: Catalog unavailable: {exc}")
    CATALOG = None
    SQLGLOT_SCHEMA = None

# 2. Config files (aliases, join map, semantics, allowed values, disambiguation)
try:
    CONFIG: dict[str, Any] = {
        "aliases": load_aliases(),
        "join_map": load_join_map(),
        "semantics": load_column_semantics(),
        "allowed": load_allowed_values(),
        "disambiguation": load_disambiguation_rules(),
    }
    _log("[mcp] Config loaded")
except Exception as exc:
    _log(f"[mcp] WARNING: Config load failed: {exc}")
    CONFIG = {
        "aliases": {},
        "join_map": {"paths": []},
        "semantics": {},
        "allowed": {},
        "disambiguation": {"rules": []},
    }

# 3. Schema descriptions (M-Schema YAML)
SCHEMA_DESCRIPTIONS = load_schema_descriptions()
if SCHEMA_DESCRIPTIONS:
    _log(f"[mcp] Schema descriptions: {len(SCHEMA_DESCRIPTIONS.get('tables', {}))} tables")

# 4. RAG: embedding-based schema retriever
try:
    SCHEMA_RETRIEVER: SchemaRetriever | None = SchemaRetriever()
    if SCHEMA_RETRIEVER.count == 0:
        desc_path = Path("app/config/schema_descriptions.yaml")
        if desc_path.exists():
            n = SCHEMA_RETRIEVER.index_from_yaml(desc_path)
            _log(f"[mcp] Indexed {n} schema docs into ChromaDB")
    else:
        _log(f"[mcp] Schema retriever: {SCHEMA_RETRIEVER.count} docs")
except Exception as exc:
    _log(f"[mcp] WARNING: Schema retriever unavailable: {exc}")
    SCHEMA_RETRIEVER = None

# 5. RAG: golden query store (verified question→SQL pairs)
try:
    GOLDEN_STORE: GoldenQueryStore | None = GoldenQueryStore()
    verified = fetch_verified_queries()
    for vq in verified:
        if vq.get("generated_sql"):
            GOLDEN_STORE.add(vq["question"], vq["generated_sql"])
    _log(f"[mcp] Golden queries: {GOLDEN_STORE.count} examples")
except Exception as exc:
    _log(f"[mcp] WARNING: Golden query store unavailable: {exc}")
    GOLDEN_STORE = None

# 6. RAG: documentation store (business rules, join hints)
try:
    DOC_STORE: DocumentationStore | None = DocumentationStore()
    if DOC_STORE.count == 0:
        n = index_config_as_documentation(DOC_STORE, CONFIG)
        _log(f"[mcp] Indexed {n} documentation chunks")
    else:
        _log(f"[mcp] Documentation store: {DOC_STORE.count} chunks")
except Exception as exc:
    _log(f"[mcp] WARNING: Documentation store unavailable: {exc}")
    DOC_STORE = None

_log("[mcp] Ready")


# ---------------------------------------------------------------------------
# MCP server definition
# ---------------------------------------------------------------------------

_INSTRUCTIONS = """\
You are an expert SQL assistant for SSA Consultants' Project_Master_Database \
(PostgreSQL). Users ask natural language questions about consultants, clients, \
engagements, tools, capabilities, and organizational data.

## Workflow
1. Call `get_schema` with the user's question to discover relevant tables, \
columns, relationships, and sample values
2. Call `get_golden_examples` to find similar verified queries as reference
3. Write a SELECT query based on the schema context and examples
4. Call `execute_query` to validate and run the SQL
5. Present results clearly, answering the user's original question

## SQL Rules
- Schema-qualify all table names: "Project_Master_Database"."TableName"
- Double-quote all identifiers (tables and columns use MixedCase)
- Use ILIKE for case-insensitive text matching
- Always include LIMIT (max 100)
- Only SELECT queries are allowed
- Prefer explicit JOINs over subqueries
- Use explicit column names, not SELECT *

## Error Recovery
If execute_query returns an error, read the details, adjust the SQL, and retry.
If 0 rows returned, check filter values against sample values from get_schema \
and try ILIKE or relaxed filters.
"""

mcp = FastMCP("SSA Data Assistant", instructions=_INSTRUCTIONS)


# ---------------------------------------------------------------------------
# JSON serialization (handles Decimal, date, bytes from PostgreSQL)
# ---------------------------------------------------------------------------

def _json_default(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return obj.hex()
    return str(obj)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_schema(question: str) -> str:
    """Retrieve relevant database schema for a natural language question.

    Uses hybrid vector + keyword search to find the most relevant tables,
    columns, relationships, sample values, and business rules. Call this
    first before writing SQL.

    Args:
        question: The natural language question about the database.
    """
    if CATALOG is None:
        return "ERROR: Database catalog not loaded. Check server logs."

    # Vector similarity scores from embedding retriever
    vector_scores: dict[str, float] | None = None
    if SCHEMA_RETRIEVER is not None:
        try:
            retrieval = SCHEMA_RETRIEVER.retrieve_tables(question)
            vector_scores = {t.name: t.vector_score for t in retrieval.tables}
        except Exception as exc:
            _log(f"[mcp] Schema retriever error (falling back to keywords): {exc}")

    # Hybrid schema routing (redirect stdout — it prints router debug info)
    with redirect_stdout(io.StringIO()):
        hint = suggest_schema_snippet(
            question=question,
            catalog=CATALOG,
            config=CONFIG,
            vector_scores=vector_scores,
            schema_descriptions=SCHEMA_DESCRIPTIONS,
        )

    parts = [hint.snippet]

    # Append relevant documentation (business rules, join hints)
    if DOC_STORE is not None:
        try:
            docs = DOC_STORE.retrieve(question, k=3)
            if docs:
                parts.append("\nRelevant business rules / documentation:")
                for doc in docs:
                    parts.append(f"  - {doc.text}")
        except Exception as exc:
            _log(f"[mcp] Doc retrieval error: {exc}")

    return "\n".join(parts)


@mcp.tool()
def get_golden_examples(question: str, k: int = 3) -> str:
    """Retrieve similar verified (question, SQL) pairs from the golden query library.

    These are human-verified correct queries — use them as reference patterns
    when writing SQL for similar questions.

    Args:
        question: The natural language question to match against.
        k: Number of examples to return (1-5, default 3).
    """
    if GOLDEN_STORE is None or GOLDEN_STORE.count == 0:
        return "No golden queries available."

    k = min(max(k, 1), 5)

    try:
        examples = GOLDEN_STORE.retrieve(question, k=k)
    except Exception as exc:
        return f"ERROR retrieving golden queries: {exc}"

    if not examples:
        return "No similar golden queries found (similarity below threshold)."

    lines = [f"Found {len(examples)} similar verified queries:\n"]
    for i, ex in enumerate(examples, 1):
        lines.append(f"Example {i} (similarity: {ex.similarity:.2f}):")
        lines.append(f"  Q: {ex.question}")
        lines.append(f"  SQL: {ex.sql}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def execute_query(sql: str) -> str:
    """Validate and execute a read-only SQL SELECT query against PostgreSQL.

    Runs the SQL through a 5-layer validation pipeline (syntax, schema,
    dangerous patterns, keyword blocklist, LIMIT) before executing.

    Args:
        sql: A SELECT query to validate and execute.
    """
    # Validate through the full pipeline
    try:
        validated_sql = validate_sql(sql, catalog_schema=SQLGLOT_SCHEMA)
    except (SQLValidationError, ValueError) as exc:
        layer = getattr(exc, "layer", "unknown")
        return f"VALIDATION ERROR (layer: {layer}): {exc}"

    # Execute against PostgreSQL
    try:
        columns, rows = run_select(validated_sql)
    except Exception as exc:
        return f"EXECUTION ERROR: {exc}\n\nSQL was:\n{validated_sql}"

    if not rows:
        return (
            f"Query returned 0 rows.\n"
            f"SQL: {validated_sql}\n\n"
            f"Try: check filter values against get_schema sample values, "
            f"use ILIKE for text matching, or relax filters."
        )

    result = {
        "row_count": len(rows),
        "columns": columns,
        "rows": rows,
    }
    return json.dumps(result, default=_json_default, indent=2)


@mcp.tool()
def list_tables() -> str:
    """List all tables in the database with descriptions and column counts.

    Call this for a high-level overview before using get_schema for details.
    """
    if CATALOG is None:
        return "ERROR: Database catalog not loaded. Check server logs."

    desc_tables = (SCHEMA_DESCRIPTIONS or {}).get("tables", {})
    lines = [f'Database: "{SCHEMA}" — {len(CATALOG.tables)} tables\n']

    for table_name in sorted(CATALOG.tables.keys()):
        table = CATALOG.tables[table_name]
        desc = desc_tables.get(table_name, {}).get("description", "")
        col_count = len(table.columns)
        line = f'  "{SCHEMA}"."{table_name}" ({col_count} columns)'
        if desc:
            line += f"\n    {desc}"
        lines.append(line)

    total_cols = sum(len(t.columns) for t in CATALOG.tables.values())
    lines.append(f"\nTotal: {len(CATALOG.tables)} tables, {total_cols} columns, {len(CATALOG.fks)} foreign keys")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SSA Data Assistant MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
    )
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    if args.transport == "streamable-http":
        mcp.run(transport="streamable-http", port=args.port)
    else:
        mcp.run(transport="stdio")
