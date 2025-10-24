# app/db.py
import os
from contextlib import contextmanager
from typing import Any, Dict, List, Sequence, Tuple, cast

import psycopg
from psycopg import conninfo, sql
from psycopg.abc import Query
from psycopg.rows import dict_row

PG_SEARCH_PATH = os.getenv("PG_SEARCH_PATH", "Project_Master_Database")


@contextmanager
def get_conn():
    dsn = os.getenv("PG_DSN_READONLY")
    if not dsn:
        raise RuntimeError("PG_DSN_READONLY not set")

    with psycopg.connect(dsn) as conn:
        # Ensure the expected schema is used and keep queries snappy.
        search_path_items = [
            part.strip() for part in (PG_SEARCH_PATH or "").split(",") if part.strip()
        ] or ["public"]

        with conn.cursor() as cur:
            search_path_sql = sql.SQL(", ").join(
                sql.Identifier(item) for item in search_path_items
            )
            cur.execute(sql.SQL("SET search_path TO {}").format(search_path_sql))
            cur.execute("SET statement_timeout = '10s'")
            cur.execute("SET application_name = 'ssa-data-assistant'")

        yield conn


def run_select(
    sql_query: str,
    params: Sequence[Any] | None = None,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Execute a SELECT statement and return (columns, rows as dicts).
    """
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            query = cast(Query, sql_query)
            cur.execute(query, params)

            if cur.description is None:
                return [], []

            cols = [d.name for d in cur.description]
            rows: List[Dict[str, Any]] = cur.fetchall()
            return cols, rows


def describe_dsn() -> Dict[str, Any]:
    """
    Return a sanitized view of the configured DSN (without the password).
    Helpful for diagnostics and logging.
    """
    dsn = os.getenv("PG_DSN_READONLY")
    if not dsn:
        return {}

    try:
        parsed = conninfo.conninfo_to_dict(dsn)
    except Exception:
        # Fall back to minimal info if parsing fails.
        return {"raw": "unparsed"}

    parsed.pop("password", None)
    return parsed
