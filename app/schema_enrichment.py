"""
Schema enrichment: introspect the database, gather statistics,
generate LLM-powered descriptions, and output a structured YAML
catalog that downstream modules (RAG, prompt builder) can consume.

Usage as CLI:
    python -m app.schema_enrichment                  # generate descriptions via LLM
    python -m app.schema_enrichment --stats-only     # just dump stats, skip LLM
    python -m app.schema_enrichment --enrich-only    # only LLM-enrich existing YAML
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Bootstrap: load .env early so PG_DSN_READONLY / OPENAI_API_KEY are present.
# ---------------------------------------------------------------------------
from dotenv import load_dotenv

load_dotenv()

from app.catalog import Catalog, Column, Table, load_catalog
from app.config_loader import load_column_semantics
from app.db import run_select

_CONFIG_DIR = Path("app/config")
_OUTPUT_PATH = _CONFIG_DIR / "schema_descriptions.yaml"
_COLUMN_SEMANTICS_PATH = _CONFIG_DIR / "column_semantics.csv"
_ALLOWED_VALUES_DIR = _CONFIG_DIR / "allowed_values"

# How many sample values to fetch per column from pg_stats
_MAX_SAMPLE_VALUES = 8


# ------------------------------------------------------------------
# 1.  Gather column statistics from pg_stats
# ------------------------------------------------------------------

def _fetch_column_stats(schema: str, catalog: Catalog) -> dict[str, dict[str, dict[str, Any]]]:
    """Return {table: {column: {n_distinct, null_frac, most_common_vals}}}.

    Tries pg_stats first; falls back to direct DISTINCT queries if the
    read-only user lacks access to pg_stats.
    """
    result: dict[str, dict[str, dict[str, Any]]] = {}

    # --- Try pg_stats first ---
    stats_sql = """
    SELECT
        s.tablename  AS table_name,
        s.attname    AS column_name,
        s.n_distinct,
        s.null_frac,
        s.most_common_vals::text AS most_common_vals
    FROM pg_stats s
    WHERE s.schemaname = %s
    ORDER BY s.tablename, s.attname
    """
    _, rows = run_select(stats_sql, (schema,))

    if rows:
        for row in rows:
            table = row["table_name"]
            col = row["column_name"]
            mcv_raw = row.get("most_common_vals") or ""
            sample_values = _parse_pg_array(mcv_raw)[:_MAX_SAMPLE_VALUES]
            result.setdefault(table, {})[col] = {
                "n_distinct": row.get("n_distinct"),
                "null_frac": round(float(row.get("null_frac") or 0), 4),
                "sample_values": sample_values,
            }
        return result

    # --- Fallback: query distinct values directly for text/varchar columns ---
    print("  pg_stats not accessible; falling back to direct sample queries...")
    text_types = {"character varying", "text", "varchar", "char", "character"}
    for table_name, table in catalog.tables.items():
        for col in table.columns:
            if col.data_type.lower() not in text_types:
                continue
            try:
                sample_sql = (
                    f'SELECT DISTINCT "{col.name}" AS val '
                    f'FROM "{schema}"."{table_name}" '
                    f'WHERE "{col.name}" IS NOT NULL '
                    f"LIMIT {_MAX_SAMPLE_VALUES}"
                )
                _, sample_rows = run_select(sample_sql)
                vals = [str(r["val"]) for r in sample_rows if r.get("val")]
                if vals:
                    result.setdefault(table_name, {})[col.name] = {
                        "n_distinct": None,
                        "null_frac": 0,
                        "sample_values": vals,
                    }
            except Exception:
                # Skip columns we can't query (e.g., timeout on large tables)
                continue
    return result


def _parse_pg_array(text: str) -> list[str]:
    """Parse a PostgreSQL text-encoded array like {a,b,c} into a Python list."""
    if not text or not text.startswith("{"):
        return []
    inner = text.strip("{}")
    if not inner:
        return []
    values: list[str] = []
    in_quote = False
    current: list[str] = []
    for ch in inner:
        if ch == '"' and not in_quote:
            in_quote = True
        elif ch == '"' and in_quote:
            in_quote = False
        elif ch == "," and not in_quote:
            values.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        values.append("".join(current).strip())
    return values


# ------------------------------------------------------------------
# 2.  Merge introspected catalog + stats + existing semantics
# ------------------------------------------------------------------

def _build_raw_catalog(
    catalog: Catalog,
    stats: dict[str, dict[str, dict[str, Any]]],
    semantics: dict[str, dict[str, dict[str, str]]],
) -> dict[str, Any]:
    """Build a raw dict ready for YAML serialisation (no LLM descriptions yet)."""
    tables_out: dict[str, Any] = {}

    for table_name, table in sorted(catalog.tables.items()):
        table_stats = stats.get(table_name, {})
        table_sem = semantics.get(table_name, {})
        columns_out: dict[str, Any] = {}

        for col in table.columns:
            col_stats = table_stats.get(col.name, {})
            col_sem = table_sem.get(col.name, {})
            entry: dict[str, Any] = {"type": col.data_type}

            if col_sem.get("semantic_type"):
                entry["semantic_type"] = col_sem["semantic_type"]
            if col_sem.get("preferred_filter"):
                entry["preferred_filter"] = col_sem["preferred_filter"]
            if col_sem.get("notes"):
                entry["notes"] = col_sem["notes"]

            sample = col_stats.get("sample_values", [])
            if sample:
                entry["sample_values"] = sample

            null_frac = col_stats.get("null_frac", 0)
            if null_frac and null_frac > 0.01:
                entry["null_fraction"] = null_frac

            n_distinct = col_stats.get("n_distinct")
            if n_distinct is not None:
                entry["n_distinct"] = (
                    int(n_distinct) if float(n_distinct) > 0 else float(n_distinct)
                )

            columns_out[col.name] = entry

        # Foreign keys where this table is the source
        relationships = []
        for fk in catalog.fks:
            if fk.src_table == table_name:
                relationships.append(
                    f"{fk.src_column} -> {fk.tgt_table}.{fk.tgt_column}"
                )
            elif fk.tgt_table == table_name:
                relationships.append(
                    f"{fk.tgt_column} <- {fk.src_table}.{fk.src_column}"
                )

        tables_out[table_name] = {
            "columns": columns_out,
            **({"relationships": sorted(relationships)} if relationships else {}),
        }

    return {
        "schema": catalog.schema,
        "generated_by": "app.schema_enrichment",
        "tables": tables_out,
    }


# ------------------------------------------------------------------
# 3.  LLM-powered description generation
# ------------------------------------------------------------------

def _generate_descriptions(
    raw_catalog: dict[str, Any],
    model: str = "gpt-4.1-mini",
) -> dict[str, Any]:
    """Call OpenAI to generate plain-English descriptions for every table and column."""
    import openai

    client = openai.OpenAI()
    enriched = dict(raw_catalog)
    tables = dict(enriched["tables"])

    for table_name, table_data in tables.items():
        ddl_lines = [f'Table: "{raw_catalog["schema"]}"."{table_name}"']
        ddl_lines.append("Columns:")
        for col_name, col_info in table_data["columns"].items():
            parts = [f"  {col_name} ({col_info['type']})"]
            if col_info.get("sample_values"):
                preview = ", ".join(str(v) for v in col_info["sample_values"][:5])
                parts.append(f"    sample values: {preview}")
            if col_info.get("semantic_type"):
                parts.append(f"    semantic type: {col_info['semantic_type']}")
            ddl_lines.append("\n".join(parts))

        if table_data.get("relationships"):
            ddl_lines.append("Relationships:")
            for rel in table_data["relationships"]:
                ddl_lines.append(f"  {rel}")

        ddl_text = "\n".join(ddl_lines)

        prompt = (
            "You are a database documentation expert. Given the following table schema "
            "with column types, sample values, and relationships, write:\n"
            "1. A one-sentence description of the table's business purpose.\n"
            "2. A one-sentence description for each column explaining what it stores "
            "in business terms.\n\n"
            "Output valid JSON with this structure:\n"
            '{"table_description": "...", "columns": {"col_name": "description", ...}}\n\n'
            "Be concise. Use business language, not technical jargon.\n\n"
            f"{ddl_text}"
        )

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content or "{}"
        try:
            descriptions = json.loads(content)
        except json.JSONDecodeError:
            print(f"  [warn] Failed to parse LLM response for {table_name}, skipping")
            continue

        table_data["description"] = descriptions.get("table_description", "")
        col_descriptions = descriptions.get("columns", {})
        for col_name, col_info in table_data["columns"].items():
            if col_name in col_descriptions:
                col_info["description"] = col_descriptions[col_name]

        tables[table_name] = table_data
        print(f"  [enriched] {table_name} ({len(table_data['columns'])} columns)")

    enriched["tables"] = tables
    return enriched


# ------------------------------------------------------------------
# 4.  Write allowed_values from pg_stats
# ------------------------------------------------------------------

def _write_allowed_values(
    stats: dict[str, dict[str, dict[str, Any]]],
    catalog: Catalog,
    output_dir: Path,
) -> int:
    """Write allowed_values CSVs for categorical columns with low cardinality."""
    output_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for table_name, table in catalog.tables.items():
        table_stats = stats.get(table_name, {})
        for col in table.columns:
            col_stats = table_stats.get(col.name, {})
            n_distinct = col_stats.get("n_distinct")
            sample_vals = col_stats.get("sample_values", [])

            # Only write for low-cardinality columns (<=50 distinct values)
            if n_distinct is None or not (0 < float(n_distinct) <= 50):
                continue
            if not sample_vals:
                continue

            filename = f"{col.name.lower()}.csv"
            filepath = output_dir / filename
            # Don't overwrite manually curated files
            if filepath.exists():
                continue

            filepath.write_text(
                "\n".join(sample_vals) + "\n", encoding="utf-8"
            )
            count += 1
            print(f"  [allowed_values] wrote {filename} ({len(sample_vals)} values)")
    return count


# ------------------------------------------------------------------
# 5.  YAML output
# ------------------------------------------------------------------

def _write_yaml(data: dict[str, Any], path: Path) -> None:
    """Write enriched catalog to YAML."""
    path.parent.mkdir(parents=True, exist_ok=True)

    class _Dumper(yaml.SafeDumper):
        pass

    # Represent lists inline when they're short
    def _represent_list(dumper: yaml.SafeDumper, data: list) -> Any:
        if all(isinstance(v, (str, int, float)) for v in data) and len(data) <= 10:
            return dumper.represent_sequence(
                "tag:yaml.org,2002:seq", data, flow_style=True
            )
        return dumper.represent_sequence("tag:yaml.org,2002:seq", data)

    _Dumper.add_representer(list, _represent_list)

    with path.open("w", encoding="utf-8") as fh:
        yaml.dump(data, fh, Dumper=_Dumper, default_flow_style=False, sort_keys=False, allow_unicode=True, width=120)

    print(f"\n  Wrote {path} ({path.stat().st_size:,} bytes)")


# ------------------------------------------------------------------
# 6.  Load existing YAML (for incremental enrichment)
# ------------------------------------------------------------------

def load_schema_descriptions(path: Path = _OUTPUT_PATH) -> dict[str, Any] | None:
    """Load previously generated schema descriptions, if they exist."""
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ------------------------------------------------------------------
# Main entry point
# ------------------------------------------------------------------

def run(
    *,
    stats_only: bool = False,
    enrich_only: bool = False,
    model: str = "gpt-4.1-mini",
) -> dict[str, Any]:
    schema = os.getenv("PG_SEARCH_PATH", "Project_Master_Database")

    if enrich_only:
        existing = load_schema_descriptions()
        if not existing:
            print("No existing schema_descriptions.yaml found. Run without --enrich-only first.")
            sys.exit(1)
        print(f"Enriching existing catalog with LLM descriptions (model={model})...")
        enriched = _generate_descriptions(existing, model=model)
        _write_yaml(enriched, _OUTPUT_PATH)
        return enriched

    print(f"Loading catalog for schema '{schema}'...")
    catalog = load_catalog(schema)
    print(f"  Found {len(catalog.tables)} tables, {len(catalog.fks)} foreign keys")

    print("Fetching column statistics from pg_stats...")
    stats = _fetch_column_stats(schema, catalog)
    stats_count = sum(len(cols) for cols in stats.values())
    print(f"  Got stats for {stats_count} columns across {len(stats)} tables")

    print("Loading existing column semantics...")
    semantics = load_column_semantics(_COLUMN_SEMANTICS_PATH)
    sem_count = sum(len(cols) for cols in semantics.values())
    print(f"  Loaded semantics for {sem_count} columns")

    print("Building raw catalog...")
    raw = _build_raw_catalog(catalog, stats, semantics)

    print("Writing auto-discovered allowed values...")
    av_count = _write_allowed_values(stats, catalog, _ALLOWED_VALUES_DIR)
    print(f"  Wrote {av_count} new allowed_values files")

    if stats_only:
        _write_yaml(raw, _OUTPUT_PATH)
        return raw

    print(f"Generating LLM descriptions (model={model})...")
    enriched = _generate_descriptions(raw, model=model)
    _write_yaml(enriched, _OUTPUT_PATH)
    return enriched


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate enriched schema descriptions for the SSA Data Assistant"
    )
    parser.add_argument(
        "--stats-only",
        action="store_true",
        help="Dump schema + stats without calling the LLM",
    )
    parser.add_argument(
        "--enrich-only",
        action="store_true",
        help="Only add LLM descriptions to an existing YAML file",
    )
    parser.add_argument(
        "--model",
        default="gpt-4.1-mini",
        help="OpenAI model for description generation (default: gpt-4.1-mini)",
    )
    args = parser.parse_args()
    run(stats_only=args.stats_only, enrich_only=args.enrich_only, model=args.model)


if __name__ == "__main__":
    main()
