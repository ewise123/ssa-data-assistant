# app/sql_validator.py
import re

def validate_sql(sql: str) -> str:
    """
    Ensures SQL is safe:
    - Must start with SELECT
    - No semicolons, DDL/DML, comments, or pg_* introspection
    - Auto-add LIMIT 100 if none present
    """
    sql_clean = sql.strip()

    # ✅ Correct: IGNORECASE flag + word boundary \b
    if not re.match(r"^\s*select\b", sql_clean, re.IGNORECASE):
        raise ValueError("Only SELECT queries are allowed.")

    banned = [
        ";", "--", "/*",  # multi-statement / comments
        "insert", "update", "delete", "alter", "drop", "create",
        "grant", "revoke", "truncate", "copy",
        "pg_", "information_schema"
    ]
    if any(b in sql_clean.lower() for b in banned):
        raise ValueError("Disallowed SQL keyword detected.")

    if " limit " not in sql_clean.lower():
        sql_clean += " LIMIT 100"
    return sql_clean
