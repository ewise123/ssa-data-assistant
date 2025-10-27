# app/ai_sql.py
import os
from typing import Any, Dict, List, Optional, Tuple, Union

from openai import OpenAI
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from .catalog import Catalog, SchemaHint, suggest_schema_snippet
from .schema_hints import SCHEMA_HINTS, SCHEMA_NAME  # reuse constant for schema name

# === SYSTEM PROMPT ===
_SYSTEM = """You are a careful data assistant for PostgreSQL.
Your job is to write one safe, read-only SQL query.

Rules:
- Output ONE SQL statement starting with SELECT (no CTE unless needed).
- Never write INSERT, UPDATE, DELETE, ALTER, CREATE, DROP, GRANT, REVOKE, TRUNCATE, or COPY.
- Use ONLY tables and columns listed in the provided schema hint. Do NOT invent table or column names.
- ALWAYS schema-qualify and double-quote identifiers: e.g. "Project_Master_Database"."ClientList".
- Use JOINs only across relationships implied by matching *_id columns or those shown in the hint.
- Prefer simple WHERE filters and ILIKE for text search.
- ALWAYS include LIMIT 100 unless the user asked for a smaller limit.
- PostgreSQL dialect. Return ONLY the SQL (no commentary)."""

# === FEW-SHOT EXAMPLES ===
_FEWSHOTS = [
    # --- Clients & Contacts ---
    {
        "user": "List client firm names and industries.",
        "assistant": f'SELECT client_firm_name, industry FROM "{SCHEMA_NAME}"."ClientList" LIMIT 100'
    },
    {
        "user": "Show contact_name and email for each client firm.",
        "assistant": f'''SELECT cl.client_firm_name, cc.contact_name, cc.email
FROM "{SCHEMA_NAME}"."ClientList" cl
JOIN "{SCHEMA_NAME}"."ClientContact" cc
  ON cc.client_id = cl.client_id
LIMIT 100'''
    },

    # --- Consultants: Managing Directors ---
    {
        "user": "List managing directors with phone numbers.",
        "assistant": f'''SELECT cr.name, tm.title, cr.phone_number
FROM "{SCHEMA_NAME}"."ConsultantRoster" cr
LEFT JOIN "{SCHEMA_NAME}"."TitleMaster" tm
  ON tm.title_id = cr.title_id
WHERE tm.title ILIKE '%Managing Director%' OR cr.role_rank ILIKE '%MD%'
LIMIT 100'''
    },

    # --- Tools ---
    {
        "user": "Show resources who use the tool Power BI.",
        "assistant": f'''SELECT r.name AS resource_name, r.role_rank, ft.tool_name
FROM "{SCHEMA_NAME}"."FirmTool" ft
JOIN "{SCHEMA_NAME}"."ToolCapability" tc   ON tc.tool_id = ft.tool_id
JOIN "{SCHEMA_NAME}"."FirmCapabilities" fc ON fc.capability_id = tc.capability_id
JOIN "{SCHEMA_NAME}"."ResourceCapability" rc ON rc.capability_id = fc.capability_id
JOIN "{SCHEMA_NAME}"."ConsolidatedResourceRoster" r ON r.resource_id = rc.resource_id
WHERE ft.tool_name ILIKE '%power%bi%'
LIMIT 100'''
    },

    # --- Capabilities ---
    {
        "user": "List resources with the capability Control Tower.",
        "assistant": f'''SELECT r.name AS resource_name, r.role_rank, fc.capability_name
FROM "{SCHEMA_NAME}"."ResourceCapability" rc
JOIN "{SCHEMA_NAME}"."ConsolidatedResourceRoster" r ON r.resource_id = rc.resource_id
JOIN "{SCHEMA_NAME}"."FirmCapabilities" fc ON fc.capability_id = rc.capability_id
WHERE fc.capability_name ILIKE '%control tower%'
LIMIT 100'''
    },

    # --- Engagements ---
    {
        "user": "Show project_name, status, and client_firm_name.",
        "assistant": f'''SELECT ce.project_name, ce.status, cl.client_firm_name
FROM "{SCHEMA_NAME}"."ClientEngagement" ce
JOIN "{SCHEMA_NAME}"."ClientList" cl
  ON cl.client_id = ce.client_id
LIMIT 100'''
    },

    # --- Training ---
    {
        "user": "List course_name and link_to_course.",
        "assistant": f'SELECT course_name, link_to_course FROM "{SCHEMA_NAME}"."TrainingLearning" LIMIT 100'
    },
    {
        "user": "Show courses and their capabilities.",
        "assistant": f'''SELECT tl.course_name, fc.capability_name
FROM "{SCHEMA_NAME}"."CourseCapability" cc
JOIN "{SCHEMA_NAME}"."TrainingLearning" tl ON tl.course_id = cc.course_id
JOIN "{SCHEMA_NAME}"."FirmCapabilities" fc ON fc.capability_id = cc.capability_id
LIMIT 100'''
    },
]


def _ensure_hint(
    question: str,
    dataset: Optional[str],
    catalog: Optional[Catalog],
    config: Optional[Dict[str, Any]],
    disambiguation: Optional[Dict[str, Any]],
    hint: Optional[SchemaHint],
) -> Tuple[Optional[SchemaHint], Optional[str]]:
    if hint is None and catalog:
        hint = suggest_schema_snippet(
            question,
            catalog,
            config=config,
            disambiguation_rules=disambiguation,
        )

    snippet = hint.snippet if hint else None
    if snippet is None and dataset:
        fallback = SCHEMA_HINTS.get(dataset.lower())
        snippet = fallback.strip() if fallback else None
    return hint, snippet


def _build_messages(
    question: str,
    dataset: Optional[str],
    catalog: Optional[Catalog],
    config: Optional[Dict[str, Any]],
    disambiguation: Optional[Dict[str, Any]],
    schema_hint: Optional[SchemaHint],
    repair_context: Optional[str] = None,
) -> Tuple[
    List[Union[
        ChatCompletionSystemMessageParam,
        ChatCompletionUserMessageParam,
        ChatCompletionAssistantMessageParam
    ]],
    Optional[SchemaHint],
]:
    hint, snippet = _ensure_hint(question, dataset, catalog, config, disambiguation, schema_hint)

    messages: List[
        Union[
            ChatCompletionSystemMessageParam,
            ChatCompletionUserMessageParam,
            ChatCompletionAssistantMessageParam
        ]
    ] = [
        ChatCompletionSystemMessageParam(role="system", content=_SYSTEM)
    ]

    if snippet:
        messages.append(
            ChatCompletionSystemMessageParam(
                role="system",
                content=f"Schema hint (real database structure):\n{snippet}"
            )
        )

    if hint and hint.disambiguation_datasets:
        dataset_note = ", ".join(hint.disambiguation_datasets)
        messages.append(
            ChatCompletionSystemMessageParam(
                role="system",
                content=f"Disambiguation: prioritize datasets {dataset_note}."
            )
        )

    if hint and hint.primary_intent and config:
        join_map = (config.get("join_map", {}) or {}).get("paths", [])
        for path in join_map:
            if path.get("intent") == hint.primary_intent:
                intent_lines = [
                    f"Intent: {path.get('intent')}",
                    f"Description: {path.get('description', '').strip()}",
                    f"Tables: {', '.join(path.get('tables', []))}",
                ]
                joins = path.get("joins") or []
                if joins:
                    join_str = "; ".join(" = ".join(pair) for pair in joins)
                    intent_lines.append(f"Joins: {join_str}")
                filters = path.get("canonical_filters") or []
                if filters:
                    filter_str = "; ".join(
                        f"{flt.get('table')}.{flt.get('column')} {flt.get('preferred_filter')} {flt.get('pattern')}"
                        for flt in filters
                    )
                    intent_lines.append(f"Canonical filters: {filter_str}")
                defaults = path.get("result_defaults") or []
                if defaults:
                    intent_lines.append(f"Default columns: {', '.join(defaults)}")
                messages.append(
                    ChatCompletionSystemMessageParam(
                        role="system",
                        content="\n".join(intent_lines)
                    )
                )
                break

    if repair_context:
        messages.append(
            ChatCompletionSystemMessageParam(
                role="system",
                content=repair_context.strip()
            )
        )

    for ex in _FEWSHOTS:
        messages.append(ChatCompletionUserMessageParam(role="user", content=ex["user"]))
        messages.append(ChatCompletionAssistantMessageParam(role="assistant", content=ex["assistant"]))

    messages.append(ChatCompletionUserMessageParam(role="user", content=question))
    return messages, hint


def propose_sql(
    question: str,
    dataset: Optional[str] = None,
    catalog: Optional[Catalog] = None,
    config: Optional[Dict[str, Any]] = None,
    schema_hint: Optional[SchemaHint] = None,
    disambiguation: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Optional[SchemaHint]]:
    """
    Generate SQL for the user's natural-language question.
    Returns the SQL and the schema hint used (for downstream repair logic).
    """
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    messages, hint = _build_messages(
        question,
        dataset,
        catalog,
        config,
        disambiguation,
        schema_hint,
    )

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0
        )
    except Exception as exc:
        raise RuntimeError(f"OpenAI API error: {exc}") from exc

    content = resp.choices[0].message.content if resp.choices else ""
    sql = content.strip() if content else ""
    return sql, hint


def propose_sql_repair(
    question: str,
    previous_sql: str,
    reason: str,
    dataset: Optional[str],
    catalog: Optional[Catalog],
    config: Optional[Dict[str, Any]],
    schema_hint: Optional[SchemaHint],
    disambiguation: Optional[Dict[str, Any]],
) -> Tuple[str, Optional[SchemaHint]]:
    """
    Ask the model to repair an unsatisfactory SQL query using DB feedback and schema metadata.
    Returns the repaired SQL (or empty string) and the schema hint used.
    """
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    repair_context = (
        "The previous SQL did not produce useful results. Read the details below and write ONE corrected SELECT.\n"
        f"Original SQL:\n{previous_sql}\n\n"
        f"Issue: {reason}\n"
        "Requirements:\n"
        "- Use ONLY tables/columns from the schema hint.\n"
        "- Keep schema-qualified identifiers with double quotes.\n"
        "- Prefer joins and filters suggested by the intent guidance.\n"
        "- Include LIMIT 100 unless a smaller limit is explicitly required.\n"
        "Return ONLY the SQL."
    )

    messages, hint = _build_messages(
        question,
        dataset,
        catalog,
        config,
        disambiguation,
        schema_hint,
        repair_context=repair_context,
    )

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0
        )
    except Exception as exc:
        raise RuntimeError(f"OpenAI API error: {exc}") from exc

    content = resp.choices[0].message.content if resp.choices else ""
    sql = content.strip() if content else ""
    return sql, hint
