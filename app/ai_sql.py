# app/ai_sql.py
import os
from enum import Enum
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
- PostgreSQL dialect. Return ONLY the SQL (no commentary).

Important query patterns:
- When the user asks "who knows" or "connected to" or "resources for contacts", ALWAYS SELECT columns from BOTH sides of the relationship (e.g., both the contact name AND the resource name).
- When the user asks for "everything about X" or "all info about X", SELECT all columns from the main table, not just the ID and name.
- When listing resources/people with optional attributes (tools, capabilities), prefer LEFT JOIN so resources without that attribute still appear.
- Use SELECT DISTINCT when JOINing through mapping tables that could produce duplicate rows.
- Title matching: "Director" means EXACTLY the title 'Director' (use ILIKE '%Director%' AND NOT ILIKE '%Managing Director%' if needed to exclude MDs). "Managing Director" is a separate, specific title. Do not confuse the two.
- For date filters: use date columns with BETWEEN or >= / < operators, e.g., start_date >= '2024-01-01' AND start_date < '2025-01-01'. Always include related context columns (project name, client, dates) not just IDs."""

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

    # --- Director vs Managing Director ---
    {
        "user": "Show me Directors and their email addresses.",
        "assistant": f'''SELECT cr.name, tm.title, cr.email
FROM "{SCHEMA_NAME}"."ConsultantRoster" cr
JOIN "{SCHEMA_NAME}"."TitleMaster" tm ON tm.title_id = cr.title_id
WHERE tm.title ILIKE '%Director%' AND tm.title NOT ILIKE '%Managing Director%'
LIMIT 100'''
    },

    # --- Everything about a client ---
    {
        "user": "Show me everything about AIG.",
        "assistant": f'''SELECT *
FROM "{SCHEMA_NAME}"."ClientList"
WHERE client_firm_name ILIKE '%AIG%'
LIMIT 100'''
    },

    # --- Projects with dates ---
    {
        "user": "What projects started in 2024?",
        "assistant": f'''SELECT ce.project_name, cl.client_firm_name, ce.start_date, ce.status
FROM "{SCHEMA_NAME}"."ClientEngagement" ce
JOIN "{SCHEMA_NAME}"."ClientList" cl ON cl.client_id = ce.client_id
WHERE ce.start_date >= '2024-01-01' AND ce.start_date < '2025-01-01'
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
    golden_examples: Optional[List[Dict[str, str]]] = None,
    doc_context: Optional[List[str]] = None,
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
                schema = config.get("join_map", {}).get("schema", "Project_Master_Database")
                intent_lines = [
                    f"IMPORTANT — This question matches the '{path.get('intent')}' pattern.",
                    f"Description: {path.get('description', '').strip()}",
                    f"You MUST use ALL of these tables: {', '.join(path.get('tables', []))}",
                ]
                joins = path.get("joins") or []
                if joins:
                    intent_lines.append("You MUST include these exact JOINs:")
                    for pair in joins:
                        src, tgt = pair
                        src_table, src_col = src.split(".")
                        tgt_table, tgt_col = tgt.split(".")
                        intent_lines.append(
                            f'  JOIN "{schema}"."{tgt_table}" ON "{schema}"."{src_table}".{src_col} = "{schema}"."{tgt_table}".{tgt_col}'
                        )
                filters = path.get("canonical_filters") or []
                if filters:
                    intent_lines.append("Apply these filters:")
                    for flt in filters:
                        intent_lines.append(
                            f"  {flt.get('table')}.{flt.get('column')} {flt.get('preferred_filter')} {flt.get('pattern')}"
                        )
                defaults = path.get("result_defaults") or []
                if defaults:
                    intent_lines.append(f"SELECT these columns: {', '.join(defaults)}")
                messages.append(
                    ChatCompletionSystemMessageParam(
                        role="system",
                        content="\n".join(intent_lines)
                    )
                )
                break

    if doc_context:
        doc_text = "\n".join(f"- {chunk}" for chunk in doc_context)
        messages.append(
            ChatCompletionSystemMessageParam(
                role="system",
                content=f"Relevant business rules and documentation:\n{doc_text}"
            )
        )

    if repair_context:
        messages.append(
            ChatCompletionSystemMessageParam(
                role="system",
                content=repair_context.strip()
            )
        )

    # Dynamic golden examples take priority; fall back to static few-shots
    if golden_examples:
        for ex in golden_examples:
            messages.append(ChatCompletionUserMessageParam(role="user", content=ex["user"]))
            messages.append(ChatCompletionAssistantMessageParam(role="assistant", content=ex["assistant"]))
        # Include a few static examples for coverage if golden set is small
        if len(golden_examples) < 3:
            for ex in _FEWSHOTS[:3]:
                messages.append(ChatCompletionUserMessageParam(role="user", content=ex["user"]))
                messages.append(ChatCompletionAssistantMessageParam(role="assistant", content=ex["assistant"]))
    else:
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
    golden_examples: Optional[List[Dict[str, str]]] = None,
    doc_context: Optional[List[str]] = None,
) -> Tuple[str, Optional[SchemaHint]]:
    """
    Generate SQL for the user's natural-language question.
    Returns the SQL and the schema hint used (for downstream repair logic).
    """
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    messages, hint = _build_messages(
        question,
        dataset,
        catalog,
        config,
        disambiguation,
        schema_hint,
        golden_examples=golden_examples,
        doc_context=doc_context,
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


class SQLErrorType(Enum):
    SYNTAX_ERROR = "syntax"
    UNKNOWN_COLUMN = "unknown_column"
    UNKNOWN_TABLE = "unknown_table"
    EXECUTION_ERROR = "execution"
    EMPTY_RESULT = "empty"
    TIMEOUT = "timeout"
    PERMISSION_DENIED = "permission"
    GENERIC = "generic"


def classify_error(reason: str, previous_sql: str = "") -> SQLErrorType:
    """Classify an error string into an actionable error type."""
    r = reason.lower()
    if "column" in r and ("not exist" in r or "does not exist" in r or "unknown" in r):
        return SQLErrorType.UNKNOWN_COLUMN
    if "relation" in r and ("not exist" in r or "does not exist" in r):
        return SQLErrorType.UNKNOWN_TABLE
    if "syntax" in r or "parse" in r:
        return SQLErrorType.SYNTAX_ERROR
    if "timeout" in r or "cancel" in r or "statement_timeout" in r:
        return SQLErrorType.TIMEOUT
    if "permission" in r or "denied" in r:
        return SQLErrorType.PERMISSION_DENIED
    if "no rows" in r or "empty" in r:
        return SQLErrorType.EMPTY_RESULT
    return SQLErrorType.EXECUTION_ERROR


_ERROR_REPAIR_PROMPTS: Dict[SQLErrorType, str] = {
    SQLErrorType.UNKNOWN_COLUMN: (
        "The query failed because a column does not exist.\n"
        "Error: {reason}\n"
        "Previous SQL:\n{previous_sql}\n\n"
        "Fix: Check the schema hint above for the correct column names. "
        "Column names are case-sensitive when double-quoted. "
        "Write ONE corrected SELECT using only columns from the schema hint."
    ),
    SQLErrorType.UNKNOWN_TABLE: (
        "The query failed because a table does not exist.\n"
        "Error: {reason}\n"
        "Previous SQL:\n{previous_sql}\n\n"
        "Fix: Check the schema hint above for correct table names. "
        "Always use schema-qualified names: \"Project_Master_Database\".\"TableName\". "
        "Write ONE corrected SELECT."
    ),
    SQLErrorType.SYNTAX_ERROR: (
        "The query has a SQL syntax error.\n"
        "Error: {reason}\n"
        "Previous SQL:\n{previous_sql}\n\n"
        "Fix: Correct the syntax. Use PostgreSQL dialect. "
        "Write ONE corrected SELECT."
    ),
    SQLErrorType.TIMEOUT: (
        "The query timed out (exceeded 10 seconds).\n"
        "Previous SQL:\n{previous_sql}\n\n"
        "Fix: Simplify the query. Reduce the number of JOINs, "
        "add more specific WHERE conditions, or remove subqueries. "
        "Write ONE simpler SELECT that answers the same question."
    ),
    SQLErrorType.EMPTY_RESULT: (
        "The query executed successfully but returned zero rows.\n"
        "Previous SQL:\n{previous_sql}\n\n"
        "Fix: The filter conditions are probably too restrictive or use wrong values. "
        "Check the sample values in the schema hint. Try using ILIKE with wildcards "
        "instead of exact matches. Broaden the WHERE conditions. "
        "Write ONE corrected SELECT that is more likely to match data."
    ),
    SQLErrorType.EXECUTION_ERROR: (
        "The query failed during execution.\n"
        "Error: {reason}\n"
        "Previous SQL:\n{previous_sql}\n\n"
        "Fix: Read the error message carefully. Use only tables and columns "
        "from the schema hint. Write ONE corrected SELECT."
    ),
    SQLErrorType.PERMISSION_DENIED: (
        "The query was denied due to permissions.\n"
        "Error: {reason}\n"
        "Previous SQL:\n{previous_sql}\n\n"
        "Fix: Use only SELECT on user tables. Do not access system catalogs. "
        "Write ONE corrected SELECT."
    ),
    SQLErrorType.GENERIC: (
        "The previous SQL did not produce useful results.\n"
        "Error: {reason}\n"
        "Previous SQL:\n{previous_sql}\n\n"
        "Write ONE corrected SELECT using only the schema hint above."
    ),
}


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
    Ask the model to repair an unsatisfactory SQL query using classified error feedback.
    Returns the repaired SQL (or empty string) and the schema hint used.
    """
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    error_type = classify_error(reason, previous_sql)
    template = _ERROR_REPAIR_PROMPTS.get(error_type, _ERROR_REPAIR_PROMPTS[SQLErrorType.GENERIC])
    repair_context = template.format(reason=reason, previous_sql=previous_sql)

    print(f"[repair] Error classified as {error_type.value}: {reason[:100]}")

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
