# Research: SQL Validation, Evaluation, and Observability for NL-to-SQL Systems

> Research conducted April 2026 for upgrading the SSA Data Assistant from regex-based SQL validation to production-grade validation, evaluation, and observability.

---

## 1. AST-Based SQL Validation

### Tool Comparison

| Tool | Approach | PostgreSQL Support | Dependencies | Best For |
|------|----------|-------------------|--------------|----------|
| **sqlglot** | Pure Python parser/transpiler | Good (dialect flag) | Zero deps | Schema validation, column resolution, type inference, transpilation |
| **pglast** | Wraps PostgreSQL's actual C parser (libpg_query) | Perfect (uses PG internals) | C extension (libpg_query) | Exact PG syntax validation, fingerprinting, normalization |
| **sqlparse** | Tokenizer (not a true parser) | Minimal | Zero deps | Formatting, splitting statements; **not suitable for validation** |

### Recommendation: sqlglot for validation, pglast as a complement

**sqlglot** is the clear winner for schema-aware validation because of its optimizer pipeline. **pglast** is valuable as a complement for exact PostgreSQL syntax checking and query fingerprinting (deduplication). **sqlparse** should be avoided for validation -- it is a tokenizer, not a parser.

### sqlglot: Schema-Aware Column/Table Validation

sqlglot's `qualify()` function rewrites SQL ASTs to have fully qualified table and column references, and **raises `OptimizeError` when columns or tables don't exist in the schema**.

```python
import sqlglot
from sqlglot.optimizer.qualify import qualify

# Define your schema catalog (mirrors your DB introspection)
schema = {
    "Project_Master_Database": {
        "ClientEngagement": {
            "ClientEngagementID": "INT",
            "ClientName": "VARCHAR",
            "ProjectName": "VARCHAR",
            "StartDate": "DATE",
            "EndDate": "DATE",
        },
        "Timesheet": {
            "TimesheetID": "INT",
            "ClientEngagementID": "INT",
            "EmployeeName": "VARCHAR",
            "Hours": "DECIMAL",
        }
    }
}

# Parse and validate -- raises OptimizeError if columns don't exist
sql = 'SELECT ClientName, FakeColumn FROM "ClientEngagement"'
try:
    expression = sqlglot.parse_one(sql, dialect="postgres")
    qualified = qualify(expression, schema=schema, dialect="postgres",
                       validate_qualify_columns=True)
    safe_sql = qualified.sql(dialect="postgres")
except sqlglot.errors.OptimizeError as e:
    print(f"Validation error: {e}")
    # "Column 'FakeColumn' could not be resolved"
```

**Key parameters for `qualify()`:**
- `schema` -- nested dict: `{catalog: {db: {table: {col: type}}}}` or `MappingSchema` instance
- `validate_qualify_columns=True` -- raises error on unknown columns (default: True)
- `dialect="postgres"` -- PostgreSQL-specific parsing
- `db` / `catalog` -- default database/catalog names for unqualified references

### sqlglot: Type Inference for Semantic Checks

The `annotate_types` optimizer rule propagates type information through the AST:

```python
from sqlglot.optimizer import optimize
from sqlglot.optimizer.annotate_types import annotate_types

expression = sqlglot.parse_one("SELECT Hours + ClientName FROM Timesheet", dialect="postgres")
annotated = annotate_types(expression, schema=schema, dialect="postgres")
# Can now inspect .type on each expression node
# Detect: adding DECIMAL + VARCHAR is a type mismatch
```

**Limitation:** Type inference adds overhead and doesn't cover all edge cases. For production use, combine AST-based type checking with execution-time error handling.

### sqlglot: Detecting Problematic Patterns

Walk the AST to detect dangerous patterns:

```python
import sqlglot.expressions as exp

def detect_cartesian_joins(sql: str) -> list[str]:
    """Detect CROSS JOINs and implicit cartesian products."""
    warnings = []
    tree = sqlglot.parse_one(sql, dialect="postgres")
    
    # Detect explicit CROSS JOINs
    for join in tree.find_all(exp.Join):
        if isinstance(join, exp.Cross):
            warnings.append("Explicit CROSS JOIN detected")
    
    # Detect multiple FROM tables without JOIN conditions
    from_clause = tree.find(exp.From)
    if from_clause:
        tables = list(tree.find_all(exp.Table))
        joins = list(tree.find_all(exp.Join))
        if len(tables) > 1 and len(joins) == 0:
            warnings.append("Multiple tables in FROM without JOIN -- possible cartesian product")
    
    return warnings

def detect_select_star(sql: str) -> bool:
    """Detect SELECT * which may expose too many columns."""
    tree = sqlglot.parse_one(sql, dialect="postgres")
    return any(isinstance(s, exp.Star) for s in tree.find_all(exp.Star))
```

### pglast: Exact PostgreSQL Syntax Validation + Fingerprinting

```python
import pglast

# Validate syntax using PostgreSQL's actual parser
try:
    tree = pglast.parse_sql("SELECT * FROM users WHERE id = $1")
    # If it parses, it's valid PostgreSQL syntax
except pglast.parser.ParseError as e:
    print(f"Invalid PostgreSQL syntax: {e}")

# Fingerprint queries for deduplication/analytics
fp1 = pglast.fingerprint("SELECT * FROM users WHERE id = 1")
fp2 = pglast.fingerprint("SELECT * FROM users WHERE id = 2")
assert fp1 == fp2  # Same fingerprint -- same query pattern

# Pretty-print / normalize
from pglast import prettify
normalized = prettify("select a,b from   t where x=1")
# Returns clean, normalized SQL
```

### Integration Pattern for SSA Data Assistant

Replace the current regex-based `validate_sql()` with a layered approach:

```
Layer 1: pglast.parse_sql()       -- reject syntactically invalid PostgreSQL
Layer 2: sqlglot qualify()         -- reject unknown tables/columns against CATALOG
Layer 3: sqlglot AST walk          -- reject CROSS JOINs, SELECT *, missing WHERE on large tables
Layer 4: Existing keyword blocklist -- keep INSERT/UPDATE/DELETE/DROP blocking
Layer 5: LIMIT enforcement         -- keep existing LIMIT 100 injection
```

---

## 2. Query Plan Analysis with EXPLAIN

### The Approach

Run `EXPLAIN (FORMAT JSON)` on generated SQL *before* executing it. Parse the plan to detect problems.

```python
import json
from typing import Any

async def analyze_query_plan(conn, sql: str) -> dict[str, Any]:
    """Run EXPLAIN on SQL and return analysis."""
    # EXPLAIN doesn't execute the query -- safe for validation
    plan_rows = await conn.execute(f"EXPLAIN (FORMAT JSON) {sql}")
    plan = json.loads(plan_rows[0][0])
    
    analysis = {
        "estimated_rows": 0,
        "has_seq_scan_large_table": False,
        "has_cartesian_product": False,
        "estimated_cost": 0,
        "warnings": [],
    }
    
    def walk_plan(node):
        node_type = node.get("Node Type", "")
        rows = node.get("Plan Rows", 0)
        
        # Detect full table scans on large tables
        if node_type == "Seq Scan" and rows > 10000:
            analysis["has_seq_scan_large_table"] = True
            analysis["warnings"].append(
                f"Sequential scan on {node.get('Relation Name')} "
                f"(~{rows} rows) -- may be slow"
            )
        
        # Detect nested loops with high row counts (cartesian products)
        if node_type == "Nested Loop" and rows > 100000:
            analysis["has_cartesian_product"] = True
            analysis["warnings"].append(
                f"Nested Loop producing ~{rows} rows -- possible cartesian product"
            )
        
        # Track total estimated cost
        analysis["estimated_cost"] = max(
            analysis["estimated_cost"],
            node.get("Total Cost", 0)
        )
        analysis["estimated_rows"] = max(
            analysis["estimated_rows"], rows
        )
        
        # Recurse into child plans
        for child in node.get("Plans", []):
            walk_plan(child)
    
    walk_plan(plan[0]["Plan"])
    return analysis
```

### Practicality Assessment

| Aspect | Assessment |
|--------|------------|
| **Safety** | EXPLAIN does not execute the query -- safe for pre-validation |
| **Latency** | Adds ~1-5ms for simple queries, ~10-50ms for complex ones |
| **Accuracy** | Estimates depend on table statistics (`ANALYZE`); can be wrong for skewed data |
| **Cartesian detection** | Reliable -- nested loops with huge row estimates are a strong signal |
| **Full scan detection** | Reliable -- Seq Scan on large tables is clearly visible |
| **Impossible WHERE** | Partially detectable -- planner shows "rows=0" estimate |

### When to Use EXPLAIN Validation

- **Recommended:** Run EXPLAIN on every generated query before execution. The overhead is small (1-50ms) and it catches catastrophic queries (cartesian products, missing indexes on huge tables) that would otherwise timeout at 10 seconds.
- **Not recommended:** Using `EXPLAIN ANALYZE` (which actually runs the query) as a validation step -- defeats the purpose.
- **Threshold approach:** If estimated cost > 10000 or estimated rows > 100000, flag for review or reject.

### Detecting Impossible WHERE Clauses

```python
# If EXPLAIN returns Plan Rows = 0 for the top-level node,
# the planner believes the query will return nothing
if analysis["estimated_rows"] == 0:
    analysis["warnings"].append(
        "Query planner estimates 0 rows -- WHERE clause may be impossible"
    )
```

---

## 3. LLM-as-Judge for SQL Evaluation

### Approaches

#### 3a. Back-Translation (SQL2NL) Validation

The most promising approach: ask a second LLM to translate the generated SQL *back* to natural language, then compare with the original question.

```python
async def validate_sql_with_backtranslation(
    original_question: str,
    generated_sql: str,
    schema_context: str,
    client: openai.AsyncOpenAI,
) -> dict:
    """Use back-translation to check if SQL answers the question."""
    
    # Step 1: Ask LLM to describe what the SQL does
    backtranslation = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": (
                "You are a SQL analyst. Given a SQL query and database schema, "
                "describe in plain English what question this query answers. "
                "Be specific about filters, aggregations, and joins."
            )},
            {"role": "user", "content": f"Schema:\n{schema_context}\n\nSQL:\n{generated_sql}"}
        ],
        temperature=0,
    )
    sql_description = backtranslation.choices[0].message.content
    
    # Step 2: Ask LLM to judge if the descriptions match
    judgment = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": (
                "Compare the original user question with the SQL query description. "
                "Rate the match on a scale of 1-5:\n"
                "5 = Perfect match\n"
                "4 = Mostly correct, minor differences\n"
                "3 = Partially correct, missing some aspects\n"
                "2 = Significantly different\n"
                "1 = Completely wrong\n\n"
                "Respond with JSON: {\"score\": N, \"explanation\": \"...\"}"
            )},
            {"role": "user", "content": (
                f"Original question: {original_question}\n\n"
                f"SQL description: {sql_description}"
            )}
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    
    result = json.loads(judgment.choices[0].message.content)
    return {
        "score": result["score"],
        "explanation": result["explanation"],
        "sql_description": sql_description,
        "is_valid": result["score"] >= 4,
    }
```

#### 3b. Direct LLM Evaluation (Arize Pattern)

From [Arize AI's research](https://arize.com/blog/text-to-sql-evaluating-sql-generation-with-llm-as-a-judge/):

- Use GPT-4 Turbo as judge with schema context in the prompt
- F1 scores of 0.70-0.76 for correctness detection
- **Including schema in the evaluation prompt significantly reduces false positives**
- Best as a sampling-based quality check, not on every request (cost)

#### 3c. SQLens Framework (Amazon Science, NeurIPS 2025)

[SQLens](https://arxiv.org/html/2506.04494v1) combines database signals + LLM signals:

1. Parse SQL into AST
2. Collect "error signals" from both the database (execution errors, empty results, constraint violations) and the LLM (logical inconsistencies)
3. Predict semantic correctness at the **clause level** (not just query level)
4. **25.78% improvement in F1** over best LLM self-evaluation methods

### Performance and Cost Tradeoffs

| Approach | Latency | Cost per Query | Accuracy | Best For |
|----------|---------|---------------|----------|----------|
| Back-translation | +1-2s (2 LLM calls) | ~$0.002-0.005 | Good (not quantified) | High-stakes queries |
| Direct LLM judge | +0.5-1s (1 LLM call) | ~$0.001-0.003 | F1: 0.70-0.76 | Sampling/offline eval |
| SQLens (combined) | +1-3s | Varies | F1: +25.78% over baseline | Production systems with correction loops |

### Practical Recommendation for SSA Data Assistant

- **Don't run LLM-as-judge on every request** -- too expensive and slow
- **Use it for:** (a) queries that return 0 rows, (b) queries flagged by AST validation, (c) random sampling for quality monitoring
- **Store judgments** in the existing SQLite analytics DB for trend analysis

---

## 4. Evaluation Frameworks and Metrics

### Key Metrics Beyond Execution Success

| Metric | What It Measures | How to Compute |
|--------|-----------------|----------------|
| **Execution Accuracy (EX)** | Does the query execute without errors? | `success_count / total_count` |
| **Result Accuracy** | Does the query return correct data? | Requires gold-standard answers or LLM-as-judge |
| **Semantic Correctness** | Does the SQL logically answer the question? | LLM-as-judge or human review |
| **Query Efficiency** | Is the query well-optimized? | EXPLAIN cost, actual execution time |
| **User Satisfaction** | Did the user find the result useful? | Thumbs up/down, session behavior |
| **Repair Rate** | How often does the first attempt fail? | `repair_count / total_count` |
| **Empty Result Rate** | How often are results empty? | `empty_count / total_count` |
| **Schema Routing Accuracy** | Did the router pick the right tables? | Compare routed tables vs. gold-standard |

### Production Accuracy Reality Check

- **Academic benchmarks (Spider 1.0):** LLMs achieve 85-88% execution accuracy
- **Clean enterprise data with semantic layer:** 86-95% accuracy achievable
- **Raw enterprise data without context:** Accuracy collapses to 10-20%
- **SSA Data Assistant (with schema routing + few-shot):** Likely 60-80% range; measuring this is the goal

### Evaluation Pipeline Architecture

```
                    +-----------------+
                    |  User Question  |
                    +--------+--------+
                             |
                    +--------v--------+
                    | NL-to-SQL System |
                    +--------+--------+
                             |
              +--------------+--------------+
              |              |              |
    +---------v----+ +------v------+ +-----v-------+
    | Execution    | | LLM Judge   | | User        |
    | Success/Fail | | (sampling)  | | Feedback    |
    +---------+----+ +------+------+ +-----+-------+
              |              |              |
              +--------------+--------------+
                             |
                    +--------v--------+
                    | Evaluation Store |
                    | (SQLite/Postgres)|
                    +--------+--------+
                             |
                    +--------v--------+
                    |  Dashboard &    |
                    |  Trend Analysis |
                    +-----------------+
```

### BenchPress: Domain-Specific Benchmarking (CIDR 2026)

[BenchPress](https://arxiv.org/abs/2510.13853) is a human-in-the-loop system for creating domain-specific text-to-SQL benchmarks:

- Domain experts annotate SQL queries with natural language descriptions
- Uses RAG + LLM to suggest annotations, humans verify
- Enables enterprise-specific evaluation rather than relying on generic benchmarks
- **Practical for SSA:** Build a test suite of 50-100 known questions + expected SQL, run nightly

### A/B Testing Approach

```
1. Deploy variant B (new validation) alongside variant A (current system)
2. Route 10% of traffic to variant B
3. Compare metrics: execution success rate, repair rate, user satisfaction
4. Use LLM-as-judge on disagreements (A succeeds but B fails, or vice versa)
5. Promote variant B when metrics are statistically significant
```

---

## 5. Feedback Loops

### Feedback Mechanisms (Ranked by Value)

| Mechanism | Implementation Effort | Signal Quality | Volume |
|-----------|----------------------|---------------|--------|
| **Thumbs up/down** | Low | Low (binary, no explanation) | High |
| **SQL correction by expert** | Medium | Very High | Low |
| **Natural language feedback** | Medium | High | Medium |
| **Result editing (select correct rows)** | High | High | Low |
| **Implicit signals (copy, re-ask, abandon)** | Medium | Medium | High |

### FISQL: Rich Interactive Feedback (EDBT 2025)

[FISQL](https://openproceedings.org/2025/conf/edbt/paper-300.pdf) enables natural language feedback on SQL results:
- User says "I also want to see the project end dates"
- System modifies the SQL based on feedback
- **Corrects ~2x more errors** than simple retry
- **15% accuracy improvement per feedback round**

### Feedback-to-Improvement Pipeline

```python
# 1. Capture feedback
@app.post("/feedback")
async def submit_feedback(request: FeedbackRequest):
    """Store user feedback on query results."""
    record_feedback(
        query_id=request.query_id,
        question=request.question,
        generated_sql=request.generated_sql,
        feedback_type=request.feedback_type,  # "thumbs_up", "thumbs_down", "correction"
        corrected_sql=request.corrected_sql,  # Optional: expert-corrected SQL
        comment=request.comment,              # Optional: natural language feedback
    )

# 2. Use corrections as few-shot examples
async def get_similar_corrections(question: str, top_k: int = 3) -> list:
    """Retrieve past corrections for similar questions."""
    # Vector similarity search against stored corrections
    # Returns (question, corrected_sql) pairs for few-shot prompting
    pass

# 3. Include in prompt construction
def build_prompt(question: str, schema: str) -> str:
    corrections = get_similar_corrections(question)
    few_shot_section = "\n".join(
        f"Q: {c.question}\nSQL: {c.corrected_sql}"
        for c in corrections
    )
    return f"""...
    Here are examples of corrected queries for similar questions:
    {few_shot_section}
    ...
    """
```

### Research Finding: Past Feedback Improves Accuracy

[ACM HILDA 2025 paper](https://dl.acm.org/doi/10.1145/3736733.3736739): Using past user feedback conversations improves translation accuracy by **up to 14.9%**.

### Recommended Implementation for SSA Data Assistant

**Phase 1 (Quick Win):**
- Add thumbs up/down buttons to the UI
- Log to existing SQLite `query_metrics.db`
- Track satisfaction rate on the admin dashboard

**Phase 2 (High Value):**
- Add "Edit SQL" button for power users
- Store corrected SQL as few-shot examples
- Auto-include relevant corrections in the OpenAI prompt

**Phase 3 (Advanced):**
- Natural language feedback ("also show end dates")
- Re-generation with feedback context
- Periodic fine-tuning review of accumulated corrections

---

## 6. Observability and Monitoring

### What to Log (Per Request)

```python
@dataclass
class QueryTrace:
    # Request metadata
    trace_id: str
    timestamp: datetime
    user_question: str
    
    # Schema routing
    routed_tables: list[str]
    routing_score: float
    routing_latency_ms: float
    
    # SQL generation
    generated_sql: str
    openai_model: str
    prompt_tokens: int
    completion_tokens: int
    generation_latency_ms: float
    
    # Validation
    validation_passed: bool
    validation_errors: list[str]
    explain_cost: float | None
    explain_warnings: list[str]
    
    # Execution
    execution_success: bool
    execution_error: str | None
    execution_latency_ms: float
    row_count: int
    
    # Repair (if triggered)
    repair_attempted: bool
    repair_success: bool
    repair_sql: str | None
    repair_tokens: int
    
    # User feedback (filled later)
    feedback_type: str | None  # thumbs_up, thumbs_down, correction
    feedback_timestamp: datetime | None
```

### Observability Platform: Langfuse (Recommended)

[Langfuse](https://langfuse.com/) is open-source (MIT), self-hostable, and purpose-built for LLM observability.

**Integration with existing OpenAI calls:**

```python
# Minimal change: swap the import
from langfuse.openai import openai  # Drop-in replacement
from langfuse.decorators import observe

@observe()
async def ask_pipeline(question: str) -> dict:
    """The /ask endpoint pipeline, now fully traced."""
    
    # All OpenAI calls are automatically traced with:
    # - Prompt/completion tokens
    # - Latency
    # - Cost (auto-calculated)
    # - Input/output content
    
    schema = suggest_schema_snippet(question)
    sql = await propose_sql(question, schema)
    # ... rest of pipeline
```

**Key Langfuse features for NL-to-SQL:**
- Automatic token + cost tracking per request
- Trace waterfall view (routing -> generation -> validation -> execution)
- User feedback collection API
- Evaluation datasets for regression testing
- Prompt versioning and A/B testing
- Dashboard with P50/P99 latency, error rates, cost breakdown

**Alternative: LangSmith** -- more polished but proprietary, no self-hosting without enterprise license. Both integrate with OpenAI Python SDK directly.

### Dashboard Metrics

Build these dashboards (Langfuse provides most out of the box):

**Operational Dashboard:**
- Request volume (per hour/day)
- P50/P95/P99 latency breakdown (routing, generation, execution)
- Error rate by type (validation, execution, timeout)
- Token usage and cost (daily/weekly trends)

**Quality Dashboard:**
- Execution success rate (should be >90%)
- Empty result rate (should be <15%)
- Repair rate (lower is better -- means first attempts succeed)
- User satisfaction rate (thumbs up / total feedback)
- Schema routing accuracy (via sampling)

**Degradation Detection:**
- Alert when execution success rate drops >5% below 7-day average
- Alert when average latency increases >50% above baseline
- Alert when token usage spikes (may indicate prompt injection or runaway repair loops)
- Alert when empty result rate exceeds threshold
- Weekly LLM-as-judge sampling to detect semantic accuracy drift

### Error Categorization Taxonomy

```python
class ErrorCategory(str, Enum):
    # Validation errors (caught before execution)
    SYNTAX_ERROR = "syntax_error"
    UNKNOWN_TABLE = "unknown_table"
    UNKNOWN_COLUMN = "unknown_column"
    UNSAFE_SQL = "unsafe_sql"
    TYPE_MISMATCH = "type_mismatch"
    
    # Execution errors (caught during execution)
    TIMEOUT = "timeout"
    PERMISSION_DENIED = "permission_denied"
    RUNTIME_ERROR = "runtime_error"
    
    # Result quality errors (caught after execution)
    EMPTY_RESULT = "empty_result"
    TOO_MANY_ROWS = "too_many_rows"
    LIKELY_CARTESIAN = "likely_cartesian"
    
    # Semantic errors (caught by LLM judge or user feedback)
    WRONG_TABLES = "wrong_tables"
    WRONG_FILTERS = "wrong_filters"
    WRONG_AGGREGATION = "wrong_aggregation"
    WRONG_JOINS = "wrong_joins"
    MISUNDERSTOOD_QUESTION = "misunderstood_question"
```

### Token Usage Tracking

```python
# Track per-request token usage in SQLite
CREATE TABLE IF NOT EXISTS token_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    total_tokens INTEGER NOT NULL,
    estimated_cost_usd REAL NOT NULL,
    stage TEXT NOT NULL  -- 'generation', 'repair', 'judge'
);

-- Daily cost report
SELECT 
    DATE(timestamp) as day,
    SUM(estimated_cost_usd) as total_cost,
    COUNT(*) as total_requests,
    AVG(total_tokens) as avg_tokens,
    SUM(CASE WHEN stage = 'repair' THEN 1 ELSE 0 END) as repair_calls
FROM token_usage
GROUP BY DATE(timestamp)
ORDER BY day DESC;
```

---

## Implementation Roadmap

### Phase 1: Foundation (1-2 weeks)

1. **Add sqlglot validation** -- replace regex with AST-based validation in `sql_validator.py`
   - Parse with `sqlglot.parse_one(sql, dialect="postgres")`
   - Qualify against `CATALOG` schema using `qualify()`
   - Keep existing keyword blocklist as a safety net
   - Add AST-based pattern detection (CROSS JOIN, missing WHERE)

2. **Add pglast syntax validation** -- first layer of defense
   - `pglast.parse_sql(sql)` catches syntax errors the LLM produces
   - `pglast.fingerprint()` for query deduplication in analytics

3. **Enhance logging** -- extend `query_metrics.db` schema
   - Add token usage, latency breakdown, error categorization
   - Add EXPLAIN cost estimates

### Phase 2: Observability (1-2 weeks)

4. **Integrate Langfuse** -- drop-in OpenAI SDK replacement
   - Swap `import openai` for `from langfuse.openai import openai`
   - Add `@observe()` decorators to pipeline functions
   - Configure dashboards for latency, cost, error rates

5. **Add EXPLAIN pre-validation** -- catch catastrophic queries
   - Run `EXPLAIN (FORMAT JSON)` before execution
   - Reject queries with estimated cost > threshold
   - Log EXPLAIN warnings to traces

### Phase 3: Feedback + Evaluation (2-3 weeks)

6. **Add user feedback UI** -- thumbs up/down in `index.html`
   - New `/feedback` POST endpoint
   - Store in `query_metrics.db`
   - Display on admin dashboard

7. **Build evaluation dataset** -- 50-100 known question/SQL pairs
   - Derived from production query logs + expert review
   - Nightly regression runs

8. **Add LLM-as-judge sampling** -- quality monitoring
   - Back-translation validation on 10% of queries
   - Alert on score degradation

### Phase 4: Continuous Improvement (Ongoing)

9. **Feedback-to-few-shot pipeline** -- use corrections in prompts
10. **A/B testing infrastructure** -- compare prompt/model variants
11. **Fine-tuned error detection** -- SQLens-inspired clause-level analysis

---

## Key Dependencies

| Package | Version | Purpose | Install |
|---------|---------|---------|---------|
| `sqlglot` | >=25.0 | SQL parsing, qualification, type annotation | `pip install sqlglot` |
| `pglast` | >=7.0 | PostgreSQL syntax validation, fingerprinting | `pip install pglast` |
| `langfuse` | >=2.0 | LLM observability, tracing, feedback | `pip install langfuse` |

All are well-maintained, actively developed, and production-ready.

---

## Sources

### AST-Based SQL Validation
- [sqlglot GitHub](https://github.com/tobymao/sqlglot) -- Python SQL Parser and Transpiler
- [sqlglot qualify API](https://sqlglot.com/sqlglot/optimizer/qualify.html) -- Schema-aware column qualification
- [sqlglot qualify_columns API](https://sqlglot.com/sqlglot/optimizer/qualify_columns.html) -- Column validation
- [sqlglot annotate_types API](https://sqlglot.com/sqlglot/optimizer/annotate_types.html) -- Type inference
- [pglast GitHub](https://github.com/lelit/pglast) -- PostgreSQL AST wrapper
- [pglast API docs](https://pglast.readthedocs.io/en/stable/api.html) -- v7 documentation
- [Table schema validation with SQL parsing](https://medium.com/happn-tech/table-schema-validation-against-sql-query-fun-with-sql-parsing-in-python-3e334c510529)

### Query Plan Analysis
- [PostgreSQL EXPLAIN documentation](https://www.postgresql.org/docs/current/using-explain.html)
- [Reading a Postgres EXPLAIN ANALYZE Query Plan](https://thoughtbot.com/blog/reading-an-explain-analyze-query-plan)

### LLM-as-Judge
- [Text To SQL: Evaluating SQL Generation with LLM as a Judge (Arize AI)](https://arize.com/blog/text-to-sql-evaluating-sql-generation-with-llm-as-a-judge/)
- [SQLens: Error Detection and Correction in Text-to-SQL (Amazon/NeurIPS 2025)](https://arxiv.org/html/2506.04494v1)
- [LLM-Based Equivalence Evaluation for Text-to-SQL](https://arxiv.org/pdf/2506.09359)
- [Confidence Scoring for LLM-Generated SQL (Amazon)](https://assets.amazon.science/03/bb/db4fedf948cebfd88475be8bb191/11-confidence-scoring-for-llm.pdf)
- [Evaluating NL2SQL via SQL2NL](https://aclanthology.org/2025.findings-emnlp.1031/)

### Evaluation Frameworks
- [BenchPress: Human-in-the-Loop Annotation for Text-to-SQL Benchmarks](https://arxiv.org/abs/2510.13853)
- [Redefining text-to-SQL metrics (Nature Scientific Reports)](https://www.nature.com/articles/s41598-025-04890-9)
- [Text-to-SQL Comparison of LLM Accuracy 2026](https://research.aimultiple.com/text-to-sql/)
- [NL2SQL System Design Guide 2025](https://medium.com/@adityamahakali/nl2sql-system-design-guide-2025-c517a00ae34d)

### Feedback Loops
- [FISQL: Rich Interactive Feedback for Text-to-SQL (EDBT 2025)](https://openproceedings.org/2025/conf/edbt/paper-300.pdf)
- [Utilizing Past User Feedback for More Accurate Text-to-SQL (ACM HILDA 2025)](https://dl.acm.org/doi/10.1145/3736733.3736739)
- [Beyond Text-to-SQL: Feedback Loops and Memory Layers (Wren AI)](https://medium.com/wrenai/beyond-text-to-sql-why-feedback-loops-and-memory-layers-are-the-future-of-genbi-28b06512a0a2)
- [GenEdit: Compounding Operators and Continuous Improvement](https://vldb.org/cidrdb/papers/2025/p28-maamari.pdf)
- [Google Cloud: Techniques for improving text-to-SQL](https://cloud.google.com/blog/products/databases/techniques-for-improving-text-to-sql)

### Observability
- [Langfuse: LLM Observability Overview](https://langfuse.com/docs/observability/overview)
- [Langfuse: Token and Cost Tracking](https://langfuse.com/docs/observability/features/token-and-cost-tracking)
- [Langfuse: Python Decorators Integration](https://langfuse.com/docs/sdk/python/decorators)
- [Langfuse: OpenAI Python Integration](https://langfuse.com/integrations/model-providers/openai-py)
- [Langfuse vs LangSmith Comparison](https://www.zenml.io/blog/langfuse-vs-langsmith)
- [Traceloop: Granular LLM Monitoring](https://www.traceloop.com/blog/granular-llm-monitoring-for-tracking-token-usage-and-latency-per-user-and-feature)

### NL2SQL Research
- [NL2SQL Handbook (HKUSTDial)](https://github.com/HKUSTDial/NL2SQL_Handbook)
- [SQL-of-Thought: Multi-agentic with Guided Error Correction](https://arxiv.org/html/2509.00581v2)
- [Boundary-Aware NL2SQL: Reliability through Hybrid Reward](https://arxiv.org/html/2601.10318)
- [Natural Language to SQL: The Complete 2026 Guide (BlazeSQL)](https://www.blazesql.com/blog/natural-language-to-sql)
