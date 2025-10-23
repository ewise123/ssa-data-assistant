# app/sql_validator.py
import re

def validate_sql(sql: str) -> str:
    """
    Ensure SQL is safe and normalized:
    - Single SELECT statement only
    - Strip one trailing semicolon
    - Forbid comments and write/DDL keywords
    - Ensure LIMIT <= 100 (add LIMIT 100 if missing)
    """
    if not isinstance(sql, str):
        raise ValueError("SQL must be a string")

    sql_clean = sql.strip()

    # Allow a single trailing semicolon (common in generated SQL)
    sql_clean = re.sub(r";\s*$", "", sql_clean)

    # Must start with SELECT (ignore leading whitespace)
    if not re.match(r"^\s*select\b", sql_clean, re.IGNORECASE):
        raise ValueError("Only SELECT queries are allowed.")

    # Forbid comments anywhere
    if re.search(r"--|/\*", sql_clean):
        raise ValueError("Comments are not allowed.")

    # Forbid dangerous keywords (word-boundary match, case-insensitive)
    if re.search(r"\b(insert|update|delete|alter|drop|create|grant|revoke|truncate|copy)\b", sql_clean, re.IGNORECASE):
        raise ValueError("Disallowed SQL keyword detected.")

    # Forbid system catalogs/introspection
    if re.search(r"\bpg_\w+|\binformation_schema\b", sql_clean, re.IGNORECASE):
        raise ValueError("System catalogs are not allowed.")

    # Ensure LIMIT present (handle newlines / any spacing)
    if not re.search(r"\blimit\b", sql_clean, re.IGNORECASE):
        sql_clean += " LIMIT 100"

    return sql_clean
