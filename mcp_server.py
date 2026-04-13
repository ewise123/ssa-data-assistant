"""
MCP Server for SSA Data Assistant.

Exposes the SSA database schema, golden queries, and read-only query
execution as MCP tools — letting Claude generate SQL natively. Zero
OpenAI dependency; uses ChromaDB's built-in local embeddings
(all-MiniLM-L6-v2 via onnxruntime) for vector search.

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
            "PG_SEARCH_PATH": "Project_Master_Database"
          }
        }
      }
    }
"""
from __future__ import annotations

import hashlib
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
os.chdir(ROOT)  # app modules use relative paths (app/config/, data/, etc.)
load_dotenv(ROOT / ".env")

import chromadb
import yaml

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
from app.schema_enrichment import load_schema_descriptions
from app.sql_validator import SQLValidationError, build_sqlglot_schema, validate_sql

from mcp.server.fastmcp import FastMCP


# ---------------------------------------------------------------------------
# Logging (stderr only — stdout is the MCP protocol channel)
# ---------------------------------------------------------------------------

def _log(msg: str) -> None:
    print(msg, file=sys.stderr)


def _stable_id(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Local-embedding retrieval (ChromaDB default: all-MiniLM-L6-v2)
# Separate data dir from the FastAPI app's OpenAI-indexed collections.
# ---------------------------------------------------------------------------

_MCP_DATA_DIR = ROOT / "data" / "chromadb_mcp"


def _get_chroma() -> chromadb.ClientAPI:
    _MCP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(_MCP_DATA_DIR))


_CHROMA = _get_chroma()


def _index_schema(descriptions: dict[str, Any]) -> chromadb.Collection:
    """Index table/column descriptions using local embeddings."""
    col = _CHROMA.get_or_create_collection("schema", metadata={"hnsw:space": "cosine"})
    if col.count() > 0:
        return col

    schema_name = descriptions.get("schema", "")
    tables = descriptions.get("tables", {})
    documents, metadatas, ids = [], [], []

    for table_name, tdata in tables.items():
        table_desc = tdata.get("description", "")
        col_names = list(tdata.get("columns", {}).keys())
        rels = tdata.get("relationships", [])

        text = f"Table: {table_name}. {table_desc} Columns: {', '.join(col_names)}."
        if rels:
            text += f" Relationships: {'; '.join(rels)}."
        documents.append(text)
        metadatas.append({"type": "table", "table": table_name})
        ids.append(_stable_id(f"table:{schema_name}.{table_name}"))

        for cname, cinfo in tdata.get("columns", {}).items():
            cdesc = cinfo.get("description", "")
            ctype = cinfo.get("type", "")
            samples = cinfo.get("sample_values", [])
            text = f"Column: {table_name}.{cname} ({ctype}). {cdesc}"
            if samples:
                text += f" Example values: {', '.join(str(v) for v in samples[:5])}."
            documents.append(text)
            metadatas.append({"type": "column", "table": table_name, "column": cname})
            ids.append(_stable_id(f"col:{schema_name}.{table_name}.{cname}"))

    if documents:
        col.upsert(ids=ids, documents=documents, metadatas=metadatas)
    return col


def _index_golden_queries(verified: list[dict[str, Any]]) -> chromadb.Collection:
    """Index verified golden queries using local embeddings."""
    col = _CHROMA.get_or_create_collection("golden_queries", metadata={"hnsw:space": "cosine"})
    if col.count() > 0:
        return col

    documents, metadatas, ids = [], [], []
    seen_ids: set[str] = set()
    for vq in verified:
        q = vq.get("question", "")
        sql = vq.get("generated_sql", "")
        if not q or not sql:
            continue
        doc_id = _stable_id(f"golden:{q}")
        if doc_id in seen_ids:
            continue
        seen_ids.add(doc_id)
        documents.append(q)
        metadatas.append({"sql": sql})
        ids.append(doc_id)

    if documents:
        col.upsert(ids=ids, documents=documents, metadatas=metadatas)
    return col


def _index_documentation(config: dict[str, Any]) -> chromadb.Collection:
    """Index business rules / join hints from config using local embeddings."""
    col = _CHROMA.get_or_create_collection("documentation", metadata={"hnsw:space": "cosine"})
    if col.count() > 0:
        return col

    documents, metadatas, ids = [], [], []

    # Join map intents
    for path in config.get("join_map", {}).get("paths", []):
        intent = path.get("intent", "")
        desc = path.get("description", "")
        tables = path.get("tables", [])
        joins = path.get("joins", [])
        lines = [f"Query pattern: {intent}. {desc}"]
        lines.append(f"Tables: {', '.join(tables)}.")
        if joins:
            lines.append(f"Joins: {'; '.join(f'{j[0]} = {j[1]}' for j in joins)}.")
        text = " ".join(lines)
        documents.append(text)
        metadatas.append({"source": f"join_map:{intent}"})
        ids.append(_stable_id(f"doc:join:{intent}"))

    # Disambiguation rules
    for rule in config.get("disambiguation", {}).get("rules", []):
        keywords = rule.get("if_contains", [])
        dataset = rule.get("dataset", "")
        prefer = rule.get("prefer_tables", [])
        text = (
            f"When the question mentions {', '.join(repr(k) for k in keywords)}, "
            f"this is about {dataset}. Use tables: {', '.join(prefer)}."
        )
        documents.append(text)
        metadatas.append({"source": f"disambiguation:{dataset}"})
        ids.append(_stable_id(f"doc:disambig:{dataset}:{keywords[0] if keywords else ''}"))

    # Column semantics by table
    for table_name, columns in config.get("semantics", {}).items():
        parts = []
        for cname, meta in columns.items():
            p = [f"{table_name}.{cname}"]
            if meta.get("semantic_type"):
                p.append(f"type={meta['semantic_type']}")
            if meta.get("preferred_filter"):
                p.append(f"filter: {meta['preferred_filter']}")
            parts.append(", ".join(p))
        text = f"Column details for {table_name}: " + "; ".join(parts) + "."
        documents.append(text)
        metadatas.append({"source": f"semantics:{table_name}"})
        ids.append(_stable_id(f"doc:sem:{table_name}"))

    # Aliases
    for category, mapping in config.get("aliases", {}).items():
        strs = []
        for canonical, alias_list in list(mapping.items())[:20]:
            strs.append(f"{canonical} (a.k.a. {', '.join(alias_list)})")
        text = f"Aliases for {category}: {'; '.join(strs)}."
        documents.append(text)
        metadatas.append({"source": f"aliases:{category}"})
        ids.append(_stable_id(f"doc:alias:{category}"))

    if documents:
        col.upsert(ids=ids, documents=documents, metadatas=metadatas)
    return col


# ---------------------------------------------------------------------------
# Initialize everything
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

# 2. Config
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
    CONFIG = {"aliases": {}, "join_map": {"paths": []}, "semantics": {}, "allowed": {}, "disambiguation": {"rules": []}}

# 3. Schema descriptions
SCHEMA_DESCRIPTIONS = load_schema_descriptions()
if SCHEMA_DESCRIPTIONS:
    _log(f"[mcp] Schema descriptions: {len(SCHEMA_DESCRIPTIONS.get('tables', {}))} tables")

# 4. Local-embedding vector stores (ChromaDB default: all-MiniLM-L6-v2)
SCHEMA_COL: chromadb.Collection | None = None
GOLDEN_COL: chromadb.Collection | None = None
DOC_COL: chromadb.Collection | None = None

if SCHEMA_DESCRIPTIONS:
    try:
        SCHEMA_COL = _index_schema(SCHEMA_DESCRIPTIONS)
        _log(f"[mcp] Schema index: {SCHEMA_COL.count()} docs (local embeddings)")
    except Exception as exc:
        _log(f"[mcp] WARNING: Schema index failed: {exc}")

try:
    verified = fetch_verified_queries()
    if verified:
        GOLDEN_COL = _index_golden_queries(verified)
        _log(f"[mcp] Golden queries: {GOLDEN_COL.count()} examples (local embeddings)")
except Exception as exc:
    _log(f"[mcp] WARNING: Golden query index failed: {exc}")

try:
    DOC_COL = _index_documentation(CONFIG)
    _log(f"[mcp] Documentation: {DOC_COL.count()} chunks (local embeddings)")
except Exception as exc:
    _log(f"[mcp] WARNING: Documentation index failed: {exc}")

_log("[mcp] Ready — fully local, no external API dependencies")


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
# JSON serialization
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

    # Vector scores from local-embedding retriever
    vector_scores: dict[str, float] | None = None
    if SCHEMA_COL is not None:
        try:
            results = SCHEMA_COL.query(
                query_texts=[question],
                where={"type": "table"},
                n_results=min(5, SCHEMA_COL.count()),
                include=["metadatas", "distances"],
            )
            if results and results["metadatas"]:
                vector_scores = {}
                for meta, dist in zip(results["metadatas"][0], results["distances"][0]):
                    vector_scores[meta["table"]] = 1.0 - dist  # cosine distance → similarity
        except Exception as exc:
            _log(f"[mcp] Schema vector search error: {exc}")

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

    # Append relevant documentation chunks
    if DOC_COL is not None:
        try:
            docs = DOC_COL.query(
                query_texts=[question],
                n_results=min(3, DOC_COL.count()),
                include=["documents", "distances"],
            )
            if docs and docs["documents"] and docs["documents"][0]:
                parts.append("\nRelevant business rules / documentation:")
                for doc_text, dist in zip(docs["documents"][0], docs["distances"][0]):
                    if (1.0 - dist) > 0.2:  # only include if reasonably relevant
                        parts.append(f"  - {doc_text}")
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
    if GOLDEN_COL is None or GOLDEN_COL.count() == 0:
        return "No golden queries available."

    k = min(max(k, 1), 5)

    try:
        results = GOLDEN_COL.query(
            query_texts=[question],
            n_results=min(k, GOLDEN_COL.count()),
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:
        return f"ERROR retrieving golden queries: {exc}"

    if not results or not results["documents"] or not results["documents"][0]:
        return "No similar golden queries found."

    lines = []
    count = 0
    for doc, meta, dist in zip(
        results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        similarity = 1.0 - dist
        if similarity < 0.3:
            continue
        count += 1
        lines.append(f"Example {count} (similarity: {similarity:.2f}):")
        lines.append(f"  Q: {doc}")
        lines.append(f"  SQL: {meta.get('sql', '')}")
        lines.append("")

    if not lines:
        return "No similar golden queries found (similarity below threshold)."

    return f"Found {count} similar verified queries:\n\n" + "\n".join(lines)


@mcp.tool()
def execute_query(sql: str) -> str:
    """Validate and execute a read-only SQL SELECT query against PostgreSQL.

    Runs the SQL through a 5-layer validation pipeline (syntax, schema,
    dangerous patterns, keyword blocklist, LIMIT) before executing.

    Args:
        sql: A SELECT query to validate and execute.
    """
    try:
        validated_sql = validate_sql(sql, catalog_schema=SQLGLOT_SCHEMA)
    except (SQLValidationError, ValueError) as exc:
        layer = getattr(exc, "layer", "unknown")
        return f"VALIDATION ERROR (layer: {layer}): {exc}"

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

    result = {"row_count": len(rows), "columns": columns, "rows": rows}
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
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    if args.transport == "streamable-http":
        mcp.run(transport="streamable-http", port=args.port)
    else:
        mcp.run(transport="stdio")
