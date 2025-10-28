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
        conn.row_factory = sqlite3.Row
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(query_log)")}
        if "canonical_question" not in columns:
            conn.execute("ALTER TABLE query_log ADD COLUMN canonical_question TEXT")
        pending = conn.execute(
            "SELECT id, question FROM query_log WHERE canonical_question IS NULL OR canonical_question = ''"
        ).fetchall()
        for row in pending:
            conn.execute(
                "UPDATE query_log SET canonical_question = ? WHERE id = ?",
                (_normalize_question(row["question"]), row["id"]),
            )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_query_log_canonical ON query_log (canonical_question)")
        conn.commit()


@contextmanager
def _conn() -> Generator[sqlite3.Connection, None, None]:
    _ensure_database()
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.row_factory = sqlite3.Row
        yield conn
    finally:
        conn.close()


def _normalize_question(question: str) -> str:
    return "".join(ch for ch in question.lower().strip() if ch.isalnum() or ch.isspace())


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
        canonical = _normalize_question(question)
        conn.execute(
            """
            INSERT INTO query_log (question, canonical_question, dataset, status, row_count, error_message)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (question, canonical, dataset, status, row_count, error_message),
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
                canonical_question AS canonical,
                MIN(question) AS question,
                COUNT(*) AS count,
                MAX(created_at) AS last_asked
            FROM query_log
            GROUP BY canonical_question
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
