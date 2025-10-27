# app/catalog.py
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

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


@dataclass
class SchemaHint:
    snippet: str
    tables: List[str]
    intents: List[str] = field(default_factory=list)
    disambiguation_datasets: List[str] = field(default_factory=list)

    @property
    def primary_intent(self) -> Optional[str]:
        return self.intents[0] if self.intents else None


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

BASE_SYNONYMS: Dict[str, List[str]] = {
    # Leadership / Roles
    "managing director": ["title", "role_rank", "titlemaster", "consultantroster"],
    "managing directors": ["title", "role_rank", "titlemaster", "consultantroster"],
    "mds": ["title", "role_rank", "titlemaster", "consultantroster"],

    # Contacts / Clients
    "contact": ["contact", "email", "clientcontact", "clientlist"],
    "contacts": ["contact", "email", "clientcontact", "clientlist"],
    "client": ["clientlist", "client", "client_firm_name"],

    # Consultants / ICs
    "consultant": ["consultantroster", "name", "title_id", "phone_number"],
    "ic": ["icroster", "consultantic"],

    # Engagements / Projects
    "engagement": ["clientengagement", "projectteam", "projectreviewform"],

    # Capabilities
    "skill": ["capability", "capabilities", "resourcecapability", "firmcapabilities"],
    "skills": ["capability", "capabilities", "resourcecapability", "firmcapabilities"],
    "capability": ["firmcapabilities", "resourcecapability"],
    "capabilities": ["firmcapabilities", "resourcecapability"],

    # Tools (mapped via ToolCapability -> FirmTool -> FirmCapabilities)
    "powerbi": ["tool", "firmtool", "toolcapability"],
    "power bi": ["tool", "firmtool", "toolcapability"],
    "excel": ["tool", "firmtool", "toolcapability"],
    "powerpoint": ["tool", "firmtool", "toolcapability"],
    "disco": ["tool", "firmtool", "toolcapability"],
}

ALIAS_HINTS: Dict[str, List[str]] = {
    "clients": ["clientlist", "clientcontact", "client_firm_name", "client", "clientengagement"],
    "titles": ["titlemaster", "consultantroster", "role_rank", "title"],
    "tools": ["firmtool", "toolcapability", "resourcecapability", "tool_name", "capability"],
    "capabilities": ["firmcapabilities", "resourcecapability", "capability_name", "capability"],
}


def _merge_synonyms(
    base: Dict[str, List[str]],
    aliases: Optional[Dict[str, Dict[str, List[str]]]] = None,
    extra: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, List[str]]:
    synonyms = {k: list(v) for k, v in base.items()}

    if aliases:
        for category, mapping in aliases.items():
            hints = ALIAS_HINTS.get(category, [])
            for canonical, alias_list in mapping.items():
                terms = hints + [
                    canonical,
                    canonical.replace(" ", ""),
                    canonical.replace(" ", "_"),
                ]
                synonyms.setdefault(canonical.lower(), [])
                synonyms[canonical.lower()].extend(terms)
                for alias in alias_list:
                    normalized = alias.lower()
                    synonyms.setdefault(normalized, [])
                    synonyms[normalized].extend(terms)

    if extra:
        for key, values in extra.items():
            synonyms.setdefault(key.lower(), [])
            synonyms[key.lower()].extend([v.lower() for v in values])

    return {k.lower(): sorted(set(vv)) for k, vv in synonyms.items()}


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9_]+", text.lower())


def _normalize(term: str) -> str:
    return term.replace("_", " ").strip().lower()


def _match_allowed_values(column: str, allowed: Dict[str, List[str]]) -> Optional[List[str]]:
    if not allowed:
        return None

    normalized_map = {_normalize(key): values for key, values in allowed.items()}
    column_key = _normalize(column)

    candidates = {
        column_key,
        _normalize(f"{column}s"),
        _normalize(f"{column}es"),
        _normalize(f"{column[:-1]}ies") if column.endswith("y") else "",
    }

    for cand in candidates:
        if cand and cand in normalized_map:
            return normalized_map[cand]
    return None


def suggest_schema_snippet(
    question: str,
    catalog: Catalog,
    config: Optional[Dict[str, Any]] = None,
    extra_synonyms: Optional[Dict[str, List[str]]] = None,
    disambiguation_rules: Optional[Dict[str, Any]] = None,
) -> SchemaHint:
    q = question.lower()
    synonyms = _merge_synonyms(
        BASE_SYNONYMS,
        aliases=config.get("aliases") if config else None,
        extra=extra_synonyms,
    )

    scores: Dict[str, float] = {table_name: 0.0 for table_name in catalog.tables.keys()}

    words = set(_tokenize(q))
    hint_terms = set(words)
    for key, syns in synonyms.items():
        if key in q:
            hint_terms.update(syns)

    for table_name, table in catalog.tables.items():
        lower_name = table_name.lower()
        for term in hint_terms:
            if term and term in lower_name:
                scores[table_name] += 4
        for column in table.columns:
            lower_column = column.name.lower()
            for term in hint_terms:
                if term and term in lower_column:
                    scores[table_name] += 2

    matched_intents: List[Tuple[str, float]] = []
    join_map = (config or {}).get("join_map", {}) or {}
    for path in join_map.get("paths", []):
        intent = path.get("intent") or ""
        tables = path.get("tables", [])
        description = path.get("description", "")
        keywords = set(_tokenize(intent)) | set(_tokenize(description))
        for join_cols in path.get("joins", []):
            for join_col in join_cols:
                keywords.update(_tokenize(join_col))
        matched = len(keywords & hint_terms)
        if matched == 0 and intent and intent in q:
            matched = 1
        if matched:
            matched_intents.append((intent, float(matched)))
            for table_name in tables:
                if table_name in scores:
                    scores[table_name] += 6 * matched

    matched_datasets: List[str] = []
    rules_source = disambiguation_rules or (config or {}).get("disambiguation")
    for rule in (rules_source or {}).get("rules", []):
        terms = rule.get("if_contains", [])
        if any(term.lower() in q for term in terms):
            dataset = rule.get("dataset")
            if dataset:
                matched_datasets.append(dataset)
            for table_name in rule.get("prefer_tables", []):
                if table_name in scores:
                    scores[table_name] += 8

    ranked_tables = [name for name, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)]
    top = [name for name in ranked_tables if scores[name] > 0][:5]
    if not top:
        top = ranked_tables[:5]

    semantics = (config or {}).get("semantics", {})
    allowed_values = (config or {}).get("allowed", {})

    lines: List[str] = ['Tables (schema-qualified):']
    table_matched_columns: Dict[str, List[str]] = {}
    for table_name in top:
        table = catalog.tables[table_name]
        matched_cols = [
            column.name for column in table.columns if any(term in column.name.lower() for term in hint_terms)
        ]
        if not matched_cols:
            matched_cols = [column.name for column in table.columns[:6]]
        table_matched_columns[table_name] = matched_cols
        cols_str = ", ".join(matched_cols)
        lines.append(f'  - "{catalog.schema}"."{table.name}"({cols_str})')

    rel_lines: List[str] = []
    for fk in catalog.fks:
        if fk.src_table in top and fk.tgt_table in top:
            rel_lines.append(
                f'  - "{catalog.schema}"."{fk.src_table}".{fk.src_column} -> '
                f'"{catalog.schema}"."{fk.tgt_table}".{fk.tgt_column}'
            )
    if rel_lines:
        lines.append("Relationships:")
        lines.extend(sorted(rel_lines, key=str.lower))

    semantic_lines: List[str] = []
    allowed_lines: List[str] = []
    for table_name in top:
        table_semantics = semantics.get(table_name, {})
        for column in table_matched_columns.get(table_name, []):
            meta = table_semantics.get(column)
            if meta:
                descriptor = meta.get("semantic_type") or "text"
                preferred = meta.get("preferred_filter")
                note_bits = [descriptor]
                if preferred:
                    note_bits.append(f"filter: {preferred}")
                if meta.get("notes"):
                    note_bits.append(meta["notes"])
                semantic_lines.append(
                    f'  - "{table_name}".{column}: {", ".join(note_bits)}'
                )

            allowed = _match_allowed_values(column, allowed_values)
            if allowed:
                preview = ", ".join(allowed[:5])
                if len(allowed) > 5:
                    preview += ", …"
                allowed_lines.append(f'  - {column}: {{{preview}}}')

    if semantic_lines:
        lines.append("Semantic hints:")
        lines.extend(semantic_lines)
    if allowed_lines:
        lines.append("Allowed values (samples):")
        lines.extend(allowed_lines)

    if matched_intents:
        intent_descriptions = [intent for intent, _ in sorted(matched_intents, key=lambda x: x[1], reverse=True)]
        lines.append(f'Intent hints: {", ".join(intent_descriptions[:3])}')

    if matched_datasets:
        lines.append(f"Disambiguation datasets: {', '.join(dict.fromkeys(matched_datasets))}")

    lines.append('Note: Use double quotes and schema-qualified names exactly as listed above.')

    snippet = "\n".join(lines)

    if top:
        primary_intent = matched_intents[0][0] if matched_intents else None
        dataset_hint = matched_datasets[0] if matched_datasets else "n/a"
        print(
            f"[router] tables={top} "
            f"{'intent='+primary_intent if primary_intent else 'intent=n/a'} "
            f"dataset_hint={dataset_hint}"
        )

    return SchemaHint(
        snippet=snippet,
        tables=top,
        intents=[intent for intent, _ in sorted(matched_intents, key=lambda x: x[1], reverse=True)],
        disambiguation_datasets=list(dict.fromkeys(matched_datasets)),
    )
