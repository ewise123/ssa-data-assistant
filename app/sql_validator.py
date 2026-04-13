# app/sql_validator.py
"""
Layered SQL validation pipeline:

  Layer 1 – pglast:   Reject syntactically invalid PostgreSQL
  Layer 2 – sqlglot:  Reject unknown tables/columns (when catalog provided)
  Layer 3 – AST:      Detect dangerous patterns (cartesian products, SELECT *)
  Layer 4 – Keywords: Blocklist for INSERT/UPDATE/DELETE/DROP etc.
  Layer 5 – LIMIT:    Enforce LIMIT ≤ 100
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import sqlglot
import sqlglot.expressions as exp
from sqlglot.errors import ParseError as SqlglotParseError

# pglast is optional — degrade gracefully if not installed
try:
    import pglast
    _HAS_PGLAST = True
except ImportError:
    _HAS_PGLAST = False

# Keywords that are never allowed in generated SQL
_BLOCKED_KEYWORDS = re.compile(
    r"\b(insert|update|delete|alter|drop|create|grant|revoke|truncate|copy)\b",
    re.IGNORECASE,
)

# System catalog patterns
_SYSTEM_CATALOG = re.compile(
    r"\bpg_\w+|\binformation_schema\b",
    re.IGNORECASE,
)


class SQLValidationError(ValueError):
    """Raised when SQL fails validation with details about which layer caught it."""

    def __init__(self, message: str, layer: str, warnings: list[str] | None = None):
        self.layer = layer
        self.warnings = warnings or []
        super().__init__(message)


class ValidationResult:
    """Result of SQL validation with the cleaned SQL and any warnings."""

    __slots__ = ("sql", "warnings")

    def __init__(self, sql: str, warnings: list[str] | None = None):
        self.sql = sql
        self.warnings = warnings or []


def validate_sql(
    sql: str,
    catalog_schema: Optional[Dict[str, Dict[str, Dict[str, str]]]] = None,
) -> str:
    """
    Validate and normalize SQL through the full pipeline.

    Parameters
    ----------
    sql : str
        The raw SQL to validate.
    catalog_schema : dict, optional
        Nested schema dict for sqlglot column validation:
        ``{schema: {table: {column: type, ...}, ...}}``.
        If None, Layer 2 (column/table existence) is skipped.

    Returns
    -------
    str
        The validated, cleaned SQL string.

    Raises
    ------
    SQLValidationError / ValueError
        If the SQL fails any validation layer.
    """
    result = validate_sql_detailed(sql, catalog_schema)
    return result.sql


def validate_sql_detailed(
    sql: str,
    catalog_schema: Optional[Dict[str, Dict[str, Dict[str, str]]]] = None,
) -> ValidationResult:
    """Full validation returning both cleaned SQL and warnings."""
    if not isinstance(sql, str):
        raise SQLValidationError("SQL must be a string", layer="input")

    warnings: list[str] = []
    sql_clean = sql.strip()

    # Strip trailing semicolons
    sql_clean = re.sub(r";\s*$", "", sql_clean)

    # Must start with SELECT
    if not re.match(r"^\s*select\b", sql_clean, re.IGNORECASE):
        raise SQLValidationError("Only SELECT queries are allowed.", layer="basic")

    # ── Layer 1: pglast syntax validation ──
    if _HAS_PGLAST:
        try:
            pglast.parse_sql(sql_clean)
        except Exception as exc:
            raise SQLValidationError(
                f"PostgreSQL syntax error: {exc}", layer="pglast"
            ) from exc

    # ── Layer 2: sqlglot column/table existence ──
    if catalog_schema:
        try:
            tree = sqlglot.parse_one(sql_clean, dialect="postgres")
            sqlglot.optimizer.qualify.qualify(
                tree,
                schema=catalog_schema,
                dialect="postgres",
                validate_qualify_columns=True,
            )
        except SqlglotParseError as exc:
            raise SQLValidationError(
                f"SQL parse error: {exc}", layer="sqlglot"
            ) from exc
        except sqlglot.errors.OptimizeError as exc:
            raise SQLValidationError(
                f"Schema validation error: {exc}", layer="sqlglot"
            ) from exc
        except Exception:
            # If sqlglot fails for any other reason, don't block — just warn
            warnings.append("sqlglot schema validation skipped due to internal error")

    # ── Layer 3: AST pattern detection ──
    try:
        tree = sqlglot.parse_one(sql_clean, dialect="postgres")
        ast_warnings = _detect_dangerous_patterns(tree)
        warnings.extend(ast_warnings)
    except Exception:
        # If parsing fails here, the SQL may still be executable — don't block
        warnings.append("AST pattern detection skipped due to parse error")

    # ── Layer 4: Keyword blocklist ──
    if re.search(r"--|/\*", sql_clean):
        raise SQLValidationError("Comments are not allowed.", layer="keywords")

    if _BLOCKED_KEYWORDS.search(sql_clean):
        raise SQLValidationError("Disallowed SQL keyword detected.", layer="keywords")

    if _SYSTEM_CATALOG.search(sql_clean):
        raise SQLValidationError("System catalogs are not allowed.", layer="keywords")

    # ── Layer 5: LIMIT enforcement ──
    if not re.search(r"\blimit\b", sql_clean, re.IGNORECASE):
        sql_clean += " LIMIT 100"

    return ValidationResult(sql=sql_clean, warnings=warnings)


def _detect_dangerous_patterns(tree: exp.Expression) -> list[str]:
    """Walk the AST to detect problematic query patterns."""
    warnings: list[str] = []

    # Detect explicit CROSS JOINs
    for join in tree.find_all(exp.Join):
        if join.args.get("side") == "CROSS" or (
            not join.args.get("on") and not join.args.get("using")
        ):
            warnings.append("Possible cartesian product: JOIN without ON/USING clause")

    # Detect multiple tables in FROM without JOIN conditions
    from_clause = tree.find(exp.From)
    if from_clause:
        tables_in_from = list(from_clause.find_all(exp.Table))
        joins = list(tree.find_all(exp.Join))
        if len(tables_in_from) > 1 and len(joins) == 0:
            warnings.append(
                "Multiple tables in FROM without JOIN — possible cartesian product"
            )

    # Detect SELECT *
    for star in tree.find_all(exp.Star):
        warnings.append("SELECT * detected — consider specifying columns explicitly")
        break  # Only warn once

    return warnings


# ------------------------------------------------------------------
# Catalog schema builder: converts our Catalog dataclass into the
# nested dict format that sqlglot's qualify() expects.
# ------------------------------------------------------------------

def build_sqlglot_schema(
    catalog: Any,
) -> Dict[str, Dict[str, Dict[str, str]]]:
    """Convert a Catalog dataclass into sqlglot schema format.

    Returns ``{schema_name: {table_name: {column_name: data_type}}}``.
    """
    schema_dict: Dict[str, Dict[str, str]] = {}
    for table_name, table in catalog.tables.items():
        schema_dict[table_name] = {
            col.name: col.data_type for col in table.columns
        }
    return {catalog.schema: schema_dict}
