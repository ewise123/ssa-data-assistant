# app/db.py
import os
from typing import Any, Dict, List, Tuple, cast
import psycopg
from psycopg.rows import dict_row
from psycopg.abc import Query
from contextlib import contextmanager

PG_DSN = os.getenv("PG_DSN_READONLY")
PG_SEARCH_PATH = os.getenv("PG_SEARCH_PATH", "public")  # set in .env: Project_Master_Database

@contextmanager
def get_conn():
    if not PG_DSN:
        raise RuntimeError("PG_DSN_READONLY not set")
    with psycopg.connect(PG_DSN) as conn:
        # ✅ ensure your schema is used by default & keep queries snappy
        with conn.cursor() as cur:
            cur.execute('SET search_path TO "{PG_SEARCH_PATH}"')
            cur.execute("SET statement_timeout = '10s'")
            cur.execute("SET application_name = 'ssa-data-assistant'")
        yield conn

def run_select(sql: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Execute a SELECT and return (columns, rows as dicts).
    """
    with get_conn() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            query = cast(Query, sql)
            cur.execute(query)
            if cur.description is None:
                return [], []
            cols = [d.name for d in cur.description]
            rows: List[Dict[str, Any]] = cur.fetchall()
            return cols, rows

