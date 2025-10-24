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
- Output ONE SQL statement starting with SELECT.
- Never write INSERT, UPDATE, DELETE, ALTER, CREATE, DROP, GRANT, REVOKE, or TRUNCATE.
- Use only tables and columns mentioned in the provided schema hint.
- Always schema-qualify and double-quote identifiers: e.g. "Project_Master_Database"."ClientList".
- Prefer the relationships given in the hint for JOINs.
- Always include LIMIT 100 unless the user explicitly asks for a smaller limit.
- PostgreSQL dialect. Return ONLY the SQL (no commentary or markdown).
"""

# === FEW-SHOT EXAMPLES ===
_FEWSHOTS: List[dict] = [
    # --- Clients dataset ---
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

    # --- Consultants dataset ---
    {
        "user": "Show consultant names, titles, and phone numbers.",
        "assistant": f'''SELECT cr.name, tm.title, cr.phone_number
FROM "{SCHEMA_NAME}"."ConsultantRoster" cr
LEFT JOIN "{SCHEMA_NAME}"."TitleMaster" tm
  ON tm.title_id = cr.title_id
LIMIT 100'''
    },
    {
        "user": "List IC names and emails.",
        "assistant": f'SELECT name, email FROM "{SCHEMA_NAME}"."ICRoster" LIMIT 100'
    },

    # --- Engagements dataset ---
    {
        "user": "Show project_name, status, and client_firm_name.",
        "assistant": f'''SELECT ce.project_name, ce.status, cl.client_firm_name
FROM "{SCHEMA_NAME}"."ClientEngagement" ce
JOIN "{SCHEMA_NAME}"."ClientList" cl
  ON cl.client_id = ce.client_id
LIMIT 100'''
    },
    {
        "user": "List project team members with their project_role for a sample of engagements.",
        "assistant": f'''SELECT ce.project_name, ptr.name AS resource_name, pt.project_role
FROM "{SCHEMA_NAME}"."ProjectTeam" pt
JOIN "{SCHEMA_NAME}"."ClientEngagement" ce ON ce.engagement_id = pt.engagement_id
JOIN "{SCHEMA_NAME}"."ConsolidatedResourceRoster" ptr ON ptr.resource_id = pt.resource_id
LIMIT 100'''
    },

    # --- Training dataset ---
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

