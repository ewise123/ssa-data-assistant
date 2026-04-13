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


class ProblemQueryRow(TypedDict):
    question: str
    status: str
    count: int
    last_asked: str
    last_error: Optional[str]


def _ensure_database() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(INITIAL_SCHEMA)
        conn.row_factory = sqlite3.Row
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(query_log)")}
        if "canonical_question" not in columns:
            conn.execute("ALTER TABLE query_log ADD COLUMN canonical_question TEXT")
        if "generated_sql" not in columns:
            conn.execute("ALTER TABLE query_log ADD COLUMN generated_sql TEXT")
        if "verified" not in columns:
            conn.execute("ALTER TABLE query_log ADD COLUMN verified INTEGER DEFAULT 0")
        if "feedback" not in columns:
            conn.execute("ALTER TABLE query_log ADD COLUMN feedback TEXT")
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
    normalized = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in question.lower())
    return " ".join(normalized.split())


def record_query(
    question: str,
    dataset: Optional[str],
    status: str,
    row_count: Optional[int] = None,
    error_message: Optional[str] = None,
    generated_sql: Optional[str] = None,
) -> int:
    """
    Persist a query event for analytics. `status` should be one of:
    - "ok": results returned successfully
    - "empty": executed but no rows returned
    - "error": execution or generation error

    Returns the row ID of the inserted record.
    """
    with _conn() as conn:
        canonical = _normalize_question(question)
        cur = conn.execute(
            """
            INSERT INTO query_log (question, canonical_question, dataset, status, row_count, error_message, generated_sql)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (question, canonical, dataset, status, row_count, error_message, generated_sql),
        )
        conn.commit()
        return cur.lastrowid or 0


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


def fetch_problem_queries(limit: int = 50) -> List[ProblemQueryRow]:
    with _conn() as conn:
        cur = conn.execute(
            """
            SELECT
                canonical_question AS canonical,
                MIN(question) AS question,
                status,
                COUNT(*) AS count,
                MAX(created_at) AS last_asked,
                MAX(
                    CASE
                        WHEN error_message IS NOT NULL AND TRIM(error_message) <> ''
                        THEN error_message
                        ELSE NULL
                    END
                ) AS last_error
            FROM query_log
            WHERE status IN ('empty', 'error')
            GROUP BY canonical_question, status
            ORDER BY count DESC, last_asked DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()
        return [
            ProblemQueryRow(
                question=row["question"],
                status=row["status"],
                count=row["count"],
                last_asked=row["last_asked"],
                last_error=row["last_error"],
            )
            for row in rows
        ]


class VerifiableQueryRow(TypedDict):
    id: int
    question: str
    generated_sql: Optional[str]
    status: str
    row_count: Optional[int]
    verified: int
    created_at: str


def fetch_verifiable_queries(limit: int = 50) -> List[VerifiableQueryRow]:
    """Return recent successful queries that have SQL stored, for admin verification."""
    with _conn() as conn:
        cur = conn.execute(
            """
            SELECT id, question, generated_sql, status, row_count, verified, created_at
            FROM query_log
            WHERE generated_sql IS NOT NULL AND generated_sql != ''
              AND status = 'ok'
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [
            VerifiableQueryRow(
                id=row["id"],
                question=row["question"],
                generated_sql=row["generated_sql"],
                status=row["status"],
                row_count=row["row_count"],
                verified=row["verified"],
                created_at=row["created_at"],
            )
            for row in cur.fetchall()
        ]


def verify_query(query_id: int, verified: bool = True) -> bool:
    """Mark a query as verified (golden) or unverified. Returns True if found."""
    with _conn() as conn:
        cur = conn.execute(
            "UPDATE query_log SET verified = ? WHERE id = ?",
            (1 if verified else 0, query_id),
        )
        conn.commit()
        return cur.rowcount > 0


def fetch_verified_queries() -> List[VerifiableQueryRow]:
    """Return all verified golden queries."""
    with _conn() as conn:
        cur = conn.execute(
            """
            SELECT id, question, generated_sql, status, row_count, verified, created_at
            FROM query_log
            WHERE verified = 1 AND generated_sql IS NOT NULL AND generated_sql != ''
            ORDER BY created_at DESC
            """,
        )
        return [
            VerifiableQueryRow(
                id=row["id"],
                question=row["question"],
                generated_sql=row["generated_sql"],
                status=row["status"],
                row_count=row["row_count"],
                verified=row["verified"],
                created_at=row["created_at"],
            )
            for row in cur.fetchall()
        ]
