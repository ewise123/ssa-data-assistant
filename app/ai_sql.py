# app/ai_sql.py
import os
from typing import Optional
from openai import OpenAI
from openai.types.chat import ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam, ChatCompletionAssistantMessageParam
from .schema_hints import SCHEMA_HINTS

_SYSTEM = """You are a careful data assistant. Produce a single, safe, READ-ONLY SQL query.
Rules:
- Output ONE statement that starts with SELECT.
- Never write INSERT/UPDATE/DELETE/ALTER/DDL.
- Use only tables/columns mentioned in the schema hint.
- Prefer exact joins shown in the hint.
- Always include LIMIT 100 unless the user explicitly asks for a smaller limit.
- Postgres dialect.
Return ONLY the SQL (no explanation).
"""

# Few-shot examples (adjust to your schema later)
_FEWSHOTS = [
    {
        "user": "List client names and industries.",
        "assistant": "SELECT name, industry FROM clients LIMIT 100"
    },
    {
        "user": "Show contact names and emails for each client.",
        "assistant": """SELECT c.name AS client_name, cc.full_name, cc.email
FROM clients c
JOIN client_contacts cc ON cc.client_id = c.client_id
LIMIT 100"""
    },
]
def _build_messages(question: str, dataset: Optional[str]) -> list[ChatCompletionSystemMessageParam | ChatCompletionUserMessageParam | ChatCompletionAssistantMessageParam]:
    hint = SCHEMA_HINTS.get((dataset or "").lower(), "")
    messages: list[ChatCompletionSystemMessageParam | ChatCompletionUserMessageParam | ChatCompletionAssistantMessageParam] = [
        ChatCompletionSystemMessageParam(role="system", content=_SYSTEM)
    ]
    if hint:
        messages.append(ChatCompletionSystemMessageParam(role="system", content=f"Schema hint:\n{hint.strip()}"))
    for ex in _FEWSHOTS:
        messages.append(ChatCompletionUserMessageParam(role="user", content=ex["user"]))
        messages.append(ChatCompletionAssistantMessageParam(role="assistant", content=ex["assistant"]))
    messages.append(ChatCompletionUserMessageParam(role="user", content=question))
    return messages

def propose_sql(question: str, dataset: Optional[str]) -> str:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    messages = _build_messages(question, dataset)
    # Simple chat completion that returns plain SQL text
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0
    )
    content = resp.choices[0].message.content
    sql = content.strip() if content is not None else ""
    return sql
