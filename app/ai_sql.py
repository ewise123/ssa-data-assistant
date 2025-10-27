# app/ai_sql.py
import os
from typing import Optional, List, Union
from openai import OpenAI
from openai.types.chat import ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam, ChatCompletionAssistantMessageParam

# Local imports
from .catalog import Catalog, suggest_schema_snippet
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

    # --- Tools (FirmTool → ToolCapability → FirmCapabilities → ResourceCapability → Resources) ---
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

    # --- Capabilities (ResourceCapability → Resources) ---
    {
        "user": "List resources with the capability Control Tower.",
        "assistant": f'''SELECT r.name AS resource_name, r.role_rank, fc.capability_name
FROM "{SCHEMA_NAME}"."ResourceCapability" rc
JOIN "{SCHEMA_NAME}"."ConsolidatedResourceRoster" r ON r.resource_id = rc.resource_id
JOIN "{SCHEMA_NAME}"."FirmCapabilities" fc ON fc.capability_id = rc.capability_id
WHERE fc.capability_name ILIKE '%control tower%'
LIMIT 100'''
    },

    # --- Engagements: simple join to client ---
    {
        "user": "Show project_name, status, and client_firm_name.",
        "assistant": f'''SELECT ce.project_name, ce.status, cl.client_firm_name
FROM "{SCHEMA_NAME}"."ClientEngagement" ce
JOIN "{SCHEMA_NAME}"."ClientList" cl
  ON cl.client_id = ce.client_id
LIMIT 100'''
    },

    # --- Training: courses with tools/capabilities ---
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

# === MESSAGE BUILDER (with dynamic catalog awareness) ===
def _build_messages(
    question: str,
    dataset: Optional[str],
    catalog: Optional[Catalog]
) -> List[
    Union[
        ChatCompletionSystemMessageParam,
        ChatCompletionUserMessageParam,
        ChatCompletionAssistantMessageParam
    ]
]:
    """
    Build the full chat history sent to the OpenAI API:
    - system rules
    - dynamic schema hint (from catalog)
    - few-shot examples
    - user question
    """
    messages: List[
        Union[
            ChatCompletionSystemMessageParam,
            ChatCompletionUserMessageParam,
            ChatCompletionAssistantMessageParam
        ]
    ] = [
        ChatCompletionSystemMessageParam(role="system", content=_SYSTEM)
    ]

    # Add dynamic schema hint (auto-detected tables & joins)
    if catalog:
        snippet = suggest_schema_snippet(question, catalog)
        messages.append(
            ChatCompletionSystemMessageParam(
                role="system",
                content=f"Schema hint (real database structure):\n{snippet}"
            )
        )
    else:
        # fallback to static hints by dataset
        hint = SCHEMA_HINTS.get((dataset or "").lower(), "")
        if hint:
            messages.append(
                ChatCompletionSystemMessageParam(
                    role="system",
                    content=f"Schema hint:\n{hint.strip()}"
                )
            )

    # few-shot examples
    for ex in _FEWSHOTS:
        messages.append(ChatCompletionUserMessageParam(role="user", content=ex["user"]))
        messages.append(ChatCompletionAssistantMessageParam(role="assistant", content=ex["assistant"]))

    # user question
    messages.append(ChatCompletionUserMessageParam(role="user", content=question))
    return messages

# === MAIN FUNCTION ===
def propose_sql(
    question: str,
    dataset: Optional[str] = None,
    catalog: Optional[Catalog] = None
) -> str:
    """
    Generate SQL for the user's natural-language question.
    Uses the OpenAI API, with dynamic schema hints from the catalog.
    """
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    messages = _build_messages(question, dataset, catalog)

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0
        )
        content = resp.choices[0].message.content
        sql = content.strip() if content else ""
        return sql
    except Exception as e:
        raise RuntimeError(f"OpenAI API error: {e}")

# app/ai_sql.py (add near bottom)
def propose_sql_repair(
    question: str,
    previous_sql: str,
    db_error: str,
    dataset: Optional[str],
    catalog: Optional[Catalog]
) -> str:
    """
    Ask the model to repair a failing SQL query using the DB error + catalog snippet.
    Returns a fresh SQL string.
    """
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # Build a fresh message stack with the same rules & dynamic schema hint
    messages = _build_messages(question, dataset, catalog)

    # Add a targeted repair instruction (keeps it concise and focused)
    repair_note = (
        "The previous SQL failed. Read the error and produce ONE corrected SELECT:\n"
        f"Previous SQL:\n{previous_sql}\n\n"
        f"Database error:\n{db_error}\n\n"
        "Constraints:\n"
        "- Use ONLY tables/columns in the schema hint above.\n"
        "- Use schema-qualified, double-quoted identifiers.\n"
        "- Include LIMIT 100.\n"
        "Return ONLY the SQL."
    )
    messages.append(ChatCompletionUserMessageParam(role="user", content=repair_note))

    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0
    )
    content = resp.choices[0].message.content
    return content.strip() if content else ""
