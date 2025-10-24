# app/catalog.py
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .db import run_select


@dataclass
class Column:
    name: str
    data_type: str


@dataclass
class Table:
    name: str
    columns: List[Column] = field(default_factory=list)


@dataclass
class ForeignKey:
    src_table: str
    src_column: str
    tgt_table: str
    tgt_column: str


@dataclass
class Catalog:
    schema: str
    tables: Dict[str, Table] = field(default_factory=dict)  # key = table name (quoted as created)
    fks: List[ForeignKey] = field(default_factory=list)


class CatalogLoadError(RuntimeError):
    """Raised when the catalog cannot be loaded from the database."""


def load_catalog(schema: str) -> Catalog:
    # 1) Tables & columns
    cols_sql = """
    SELECT table_name, column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = %s
    ORDER BY table_name, ordinal_position
    """

    # 2) Foreign keys
    fks_sql = """
    SELECT
      tc.table_name AS src_table,
      kcu.column_name AS src_column,
      ccu.table_name AS tgt_table,
      ccu.column_name AS tgt_column
    FROM information_schema.table_constraints AS tc
    JOIN information_schema.key_column_usage AS kcu
      ON tc.constraint_name = kcu.constraint_name
     AND tc.table_schema = kcu.table_schema
    JOIN information_schema.constraint_column_usage AS ccu
      ON ccu.constraint_name = tc.constraint_name
     AND ccu.table_schema = tc.table_schema
    WHERE tc.constraint_type = 'FOREIGN KEY'
      AND tc.table_schema = %s
    ORDER BY src_table, src_column
    """

    try:
        _, cols_rows = run_select(cols_sql, (schema,))
    except Exception as exc:
        raise CatalogLoadError(f"Could not fetch columns for schema '{schema}': {exc}") from exc

    try:
        _, fks_rows = run_select(fks_sql, (schema,))
    except Exception as exc:
        raise CatalogLoadError(f"Could not fetch foreign keys for schema '{schema}': {exc}") from exc

    cat = Catalog(schema=schema)
    for row in cols_rows:
        table = cat.tables.setdefault(row["table_name"], Table(name=row["table_name"]))
        table.columns.append(Column(name=row["column_name"], data_type=row["data_type"]))

    for row in fks_rows:
        cat.fks.append(
            ForeignKey(
                src_table=row["src_table"],
                src_column=row["src_column"],
                tgt_table=row["tgt_table"],
                tgt_column=row["tgt_column"],
            )
        )

    return cat


# --- Simple router: pick relevant tables/columns for a question ---

DEFAULT_SYNONYMS: Dict[str, List[str]] = {
    # business terms -> column/table hints (lowercase for matching)
    "managing director": ["title", "role_rank", "titlemaster", "consultantroster"],
    "managing directors": ["title", "role_rank", "titlemaster", "consultantroster"],
    "mds": ["title", "titlemaster", "consultantroster"],
    "powerbi": ["power", "bi", "capability", "capabilities", "firmcapabilities", "resourcecapability", "tool", "toolcapability", "firmtool"],
    "power bi": ["power", "bi", "capability", "capabilities", "firmcapabilities", "resourcecapability", "tool", "toolcapability", "firmtool"],
    "contact": ["contact", "email", "clientcontact", "clientlist"],
    "contacts": ["contact", "email", "clientcontact", "clientlist"],
    "client": ["clientlist", "client", "client_firm_name"],
    "consultant": ["consultantroster", "name", "title_id", "phone_number"],
    "ic": ["icroster", "consultantic"],
    "engagement": ["clientengagement", "projectteam", "projectreviewform"],
    "skill": ["capability", "capabilities", "resourcecapability", "firmcapabilities"],
    "skills": ["capability", "capabilities", "resourcecapability", "firmcapabilities"],
}


def suggest_schema_snippet(
    question: str,
    catalog: Catalog,
    extra_synonyms: Dict[str, List[str]] | None = None,
) -> str:
    q = question.lower()
    synonyms = dict(DEFAULT_SYNONYMS)
    if extra_synonyms:
        for key, values in extra_synonyms.items():
            synonyms[key.lower()] = [value.lower() for value in values]

    # Build a simple score per table: keyword hits in table/column names + synonyms
    scores: Dict[str, int] = {table_name: 0 for table_name in catalog.tables.keys()}

    # tokenize crude words
    words = set(re.findall(r"[a-z0-9_]+", q))
    hint_terms = set(words)
    for key, syns in synonyms.items():
        if key in q:
            hint_terms.update(syns)

    for table_name, table in catalog.tables.items():
        lower_name = table_name.lower()
        # table name match
        for term in hint_terms:
            if term in lower_name:
                scores[table_name] += 4
        # column name matches
        for column in table.columns:
            lower_column = column.name.lower()
            for term in hint_terms:
                if term in lower_column:
                    scores[table_name] += 2

    # Pick top 5 tables by score (non-zero), fallback to top by name if none scored
    top = [
        name for name, score in sorted(scores.items(), key=lambda item: item[1], reverse=True) if score > 0
    ][:5]
    if not top:
        top = list(sorted(catalog.tables.keys()))[:5]

    # Keep only columns that seem relevant (or first few cols if none match)
    lines: List[str] = ['Tables (schema-qualified):']
    for table_name in top:
        table = catalog.tables[table_name]
        matched_cols = [
            column.name for column in table.columns if any(term in column.name.lower() for term in hint_terms)
        ]
        if not matched_cols:
            matched_cols = [column.name for column in table.columns[:6]]
        cols_str = ", ".join(matched_cols)
        lines.append(f'  - "{catalog.schema}"."{table.name}"({cols_str})')

    # Add join hints from FKs among the chosen tables
    rel_lines: List[str] = []
    for fk in catalog.fks:
        if fk.src_table in top and fk.tgt_table in top:
            rel_lines.append(
                f'  - "{catalog.schema}"."{fk.src_table}".{fk.src_column} -> '
                f'"{catalog.schema}"."{fk.tgt_table}".{fk.tgt_column}'
            )
    if rel_lines:
        lines.append("Relationships:")
        lines.extend(rel_lines)

    # Small note to bias quoted usage
    lines.append('Note: Use double quotes and schema-qualified names exactly as listed above.')
    return "\n".join(lines)
