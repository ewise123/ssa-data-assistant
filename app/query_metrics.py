import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, List, Optional, TypedDict


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "query_metrics.db"

INITIAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS query_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    dataset TEXT,
    status TEXT NOT NULL,
    row_count INTEGER,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_query_log_question ON query_log (question);
CREATE INDEX IF NOT EXISTS idx_query_log_status ON query_log (status);
"""


class TopQueryRow(TypedDict):
    question: str
    count: int
    last_asked: str


def _ensure_database() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(INITIAL_SCHEMA)


@contextmanager
def _conn() -> Generator[sqlite3.Connection, None, None]:
    _ensure_database()
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        yield conn
    finally:
        conn.close()


def record_query(
    question: str,
    dataset: Optional[str],
    status: str,
    row_count: Optional[int] = None,
    error_message: Optional[str] = None,
) -> None:
    """
    Persist a query event for analytics. `status` should be one of:
    - "ok": results returned successfully
    - "empty": executed but no rows returned
    - "error": execution or generation error
    """
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO query_log (question, dataset, status, row_count, error_message)
            VALUES (?, ?, ?, ?, ?)
            """,
            (question, dataset, status, row_count, error_message),
        )
        conn.commit()


def fetch_top_queries(limit: int = 10) -> List[TopQueryRow]:
    """
    Return the most frequently asked questions ordered by frequency then recency.
    """
    with _conn() as conn:
        cur = conn.execute(
            """
            SELECT
                question,
                COUNT(*) AS count,
                MAX(created_at) AS last_asked
            FROM query_log
            GROUP BY question
            ORDER BY count DESC, last_asked DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()
        return [
            TopQueryRow(
                question=row["question"],
                count=row["count"],
                last_asked=row["last_asked"],
            )
            for row in rows
        ]

