# SSA Data Assistant v2 - Implementation Plan

> Synthesized from 5 parallel research tracks (April 2026). This plan transforms the current single-shot NL-to-SQL pipeline into a modern, agentic system with RAG, semantic schema linking, and continuous learning.

---

## Executive Summary

The current system suffers from three root problems:
1. **Schema linking is keyword-only** -- the #1 accuracy bottleneck across all research
2. **Few-shot examples are static** -- 8 hardcoded examples can't cover the diversity of real questions
3. **No learning loop** -- problem queries are logged but never used to improve the system

The research converges on a clear upgrade path: **embed the schema, retrieve relevant examples dynamically, decompose the pipeline into explicit steps, and build a feedback loop that compounds accuracy over time.**

Expected accuracy improvement: from an estimated 50-65% to 80-90% on domain queries.

---

## Architecture: Current vs. Target

### Current Pipeline
```
Question → keyword_score_tables() → single_LLM_call(static_few_shot) → regex_validate() → execute() → [single_retry]
```

### Target Pipeline
```
Question
    │
    ▼
[1] Embed question (text-embedding-3-small)
    │
    ├──→ [2a] Schema RAG: retrieve top-5 tables/columns via vector similarity
    │         (hybrid: embeddings + existing keyword/synonym scoring)
    │
    ├──→ [2b] Golden Query RAG: retrieve top-3 similar verified (question, SQL) pairs
    │
    ├──→ [2c] Documentation RAG: retrieve top-3 relevant business rules/join hints
    │
    ▼
[3] Query Classification: simple | complex | nested
    │
    ▼
[4] Query Planning (complex/nested only):
    LLM outputs structured plan: {tables, joins, filters, aggregations}
    Validate plan against catalog before generating SQL
    │
    ▼
[5] SQL Generation:
    - Simple: single candidate, temperature=0
    - Complex: 2-3 candidates, select best via execution + LLM review
    │
    ▼
[6] Validation (layered):
    - pglast: PostgreSQL syntax check
    - sqlglot qualify(): column/table existence against catalog
    - AST pattern detection: cartesian products, missing WHERE, SELECT *
    - Existing keyword blocklist: INSERT/UPDATE/DELETE/DROP
    - LIMIT 100 enforcement
    │
    ▼
[7] EXPLAIN pre-check:
    - Run EXPLAIN (FORMAT JSON), reject if estimated cost > threshold
    │
    ▼
[8] Execute → classify result:
    │
    ├─ Success → candidate for golden query library
    ├─ Error → classify error type → targeted repair prompt (max 2 retries)
    └─ Empty → relax filters or re-run schema linking with broader context
    │
    ▼
[9] Log full trace (Langfuse) + record to query_metrics
```

---

## Phased Implementation

### Phase 1: Foundation -- Schema Descriptions + Embeddings + Validation
**Goal:** Replace the two biggest bottlenecks (keyword schema linking, regex validation)
**Impact:** Estimated +15-25% accuracy improvement
**New dependencies:** `sqlglot`, `pglast`, `chromadb`

#### 1.1 Auto-Generate Schema Descriptions (M-Schema)
**File:** new `app/schema_enrichment.py`

Write a one-time script that:
1. Introspects `Project_Master_Database` via the existing `catalog.py` machinery
2. For each table: queries `pg_stats` for most_common_vals, null_fraction, n_distinct
3. Sends each table's DDL + stats to GPT-5.4 with prompt: "Describe this table and each column in plain English for a business user"
4. Outputs `app/config/schema_descriptions.yaml`:
   ```yaml
   tables:
     ClientEngagement:
       description: "Tracks consultant assignments to client projects..."
       columns:
         EngagementID:
           type: INT
           description: "Unique identifier for each engagement"
           sample_values: [1001, 1002, 1003]
         BillRate:
           type: DECIMAL
           description: "Hourly billing rate in USD"
           sample_values: [75.00, 150.00, 250.00]
           semantic_type: currency
           preferred_filter: "= or BETWEEN"
   ```
5. Auto-populates `allowed_values/` from `pg_stats.most_common_vals` (replaces manual CSV curation)
6. Human reviews and enriches descriptions (adds business context LLM can't infer)

**Merge existing config:** Fold `column_semantics.csv` data into the YAML as `semantic_type` and `preferred_filter` fields.

#### 1.2 Embedding-Based Schema Linking
**File:** new `app/rag.py`

```
Components:
  - ChromaDB persistent store at ./data/chromadb/
  - Three collections: "schema", "golden_queries", "documentation"
  - Embedding model: text-embedding-3-small (already using OpenAI)
```

Build a `SchemaRetriever` class that:
1. At startup: embeds all table/column descriptions from `schema_descriptions.yaml` into the `schema` collection
2. At query time: embeds the user question, retrieves top-5 tables + top-10 columns by cosine similarity
3. **Hybrid scoring:** combine vector similarity score with existing keyword/synonym score from `catalog.py`
   - `final_score = 0.6 * vector_score + 0.4 * keyword_score`
   - This preserves the value of manually curated synonyms while adding semantic understanding
4. Validates retrieved tables have connecting foreign key paths (reject structurally disconnected tables)

**Modify:** `suggest_schema_snippet()` in `catalog.py` to call `SchemaRetriever` and merge scores.

#### 1.3 AST-Based SQL Validation
**File:** rewrite `app/sql_validator.py`

Replace regex-based validation with a layered approach:

```
Layer 1: pglast.parse_sql(sql)
  → Reject syntactically invalid PostgreSQL
  → Fingerprint for analytics deduplication

Layer 2: sqlglot.qualify(expression, schema=CATALOG_SCHEMA, dialect="postgres")
  → Reject unknown tables/columns
  → Fully qualify all references

Layer 3: AST pattern detection
  → Reject CROSS JOINs
  → Warn on SELECT * (rewrite to explicit columns if possible)
  → Warn on multiple FROM tables without JOIN conditions
  → Warn on missing WHERE on tables with >10K rows

Layer 4: Existing keyword blocklist (keep as safety net)
  → INSERT, UPDATE, DELETE, ALTER, DROP, CREATE, GRANT, REVOKE, TRUNCATE, COPY

Layer 5: LIMIT enforcement (keep existing logic)
```

Build the `CATALOG_SCHEMA` dict from the existing `Catalog` dataclass at startup.

#### 1.4 Model Upgrade
**File:** modify `app/ai_sql.py`

- Change default model from `gpt-4o-mini` to `gpt-4.1-mini` (or `gpt-5.4` with `reasoning: {effort: "none"}` for drop-in replacement)
- Add `reasoning.effort` parameter support for complex queries (set to "medium" for queries classified as complex)
- Keep model configurable via environment variable

---

### Phase 2: RAG -- Golden Queries + Dynamic Few-Shot + Documentation
**Goal:** Replace static few-shot examples with dynamic retrieval
**Impact:** Estimated +4-12% additional accuracy improvement
**Depends on:** Phase 1 (ChromaDB infrastructure)

#### 2.1 Golden Query Library
**File:** extend `app/rag.py`, extend `app/query_metrics.py`

1. Add `verified` boolean column to `query_metrics` SQLite schema
2. Create admin endpoint `POST /admin/verify-query` to mark queries as correct/incorrect
3. When a query is marked verified:
   - Embed the (question, SQL) pair
   - Store in the `golden_queries` ChromaDB collection with metadata: `{question, sql, tables_used, verified_by, verified_at}`
4. **Bootstrap:** Mine existing `query_metrics.db` for successful queries (status=ok, rows > 0). Have a domain expert verify 30-50 covering common patterns.
5. Target: 20-30 verified examples per major table/query pattern

#### 2.2 Dynamic Few-Shot Retrieval
**File:** modify `app/ai_sql.py`

Replace the static `_FEWSHOTS` list with dynamic retrieval:
1. At query time: embed the user question, retrieve top-3 similar golden queries
2. If golden query hit: include as few-shot examples (highest priority)
3. If no golden query match (similarity < threshold): fall back to static examples for that query category
4. Include retrieved examples in prompt after schema context, before user question

**Selection strategy:** Use DAIL-SQL's combined approach:
- Score by question similarity (cosine distance)
- Bonus for SQL structural similarity (same tables/join patterns)

#### 2.3 Documentation RAG
**File:** extend `app/rag.py`

Convert existing config files into embeddable chunks and index in the `documentation` collection:

| Source | Chunk Strategy |
|--------|---------------|
| `join_map.json` | One chunk per intent: "To find resources by tool, join FirmTool → ResourceTool → ConsolidatedResourceRoster on tool_id" |
| `disambiguation.json` | One chunk per rule: "When asking about ICs (individual contributors), use ConsultantRoster and ICRoster tables" |
| `column_semantics.csv` | One chunk per column: "ClientEngagement.BillRate is a currency field, filter with = or BETWEEN" |
| `*_aliases.csv` | One chunk per canonical term with all aliases |
| Business rules (new) | One chunk per rule: "Active consultant = Status is 'Active' AND EndDate IS NULL" |

Retrieve top-3 relevant documentation chunks at query time, include in prompt.

#### 2.4 Enriched Prompt Format (M-Schema)
**File:** modify `app/ai_sql.py`

Restructure the prompt to include richer context:

```
SYSTEM: You are a PostgreSQL SQL expert...

SCHEMA (retrieved by relevance):
Table: "Project_Master_Database"."ClientEngagement"
  Description: Tracks consultant assignments to client projects
  Columns:
    - EngagementID (INT, PK): Unique engagement identifier
    - ClientName (VARCHAR): Client firm name. Values: "Acme Corp", "Widget Inc", ...
    - BillRate (DECIMAL): Hourly rate in USD. Range: 75-250
    - Status (VARCHAR): Engagement status. Values: "Active", "Completed", "On Hold"
  Relationships:
    → ConsultantRoster.ConsultantID via ClientEngagement.ConsultantID

JOIN PATHS (from documentation RAG):
  For resource-by-tool queries: FirmTool.tool_id → ResourceTool.tool_id → ...

EXAMPLES (from golden query RAG):
  Q: How many active consultants do we have?
  SQL: SELECT COUNT(*) FROM "Project_Master_Database"."ConsultantRoster" WHERE "Status" = 'Active'

QUESTION: {user_question}
```

---

### Phase 3: Agentic Pipeline -- Decomposition + Classification + Multi-Candidate
**Goal:** Handle complex queries that single-shot generation fails on
**Impact:** Estimated +5-10% additional accuracy improvement on complex queries
**Depends on:** Phase 2

#### 3.1 Query Classification
**File:** new `app/query_classifier.py`

Add a lightweight classification step before SQL generation:

```python
class QueryComplexity(Enum):
    SIMPLE = "simple"      # Single table, basic filter/aggregation
    MODERATE = "moderate"   # 2-3 table joins, standard patterns
    COMPLEX = "complex"     # Multi-join, subqueries, nested aggregations
```

Classification approach (choose one):
- **Option A (cheap):** Rule-based on schema linking results -- if >3 tables matched or question contains aggregation + comparison keywords → complex
- **Option B (accurate):** Quick LLM call with question + matched tables → classify

Route to different generation strategies:
- Simple: single candidate, temperature=0, no planning step
- Moderate: single candidate with planning step
- Complex: 2-3 candidates + planning step + selection

#### 3.2 Query Planning Step
**File:** modify `app/ai_sql.py`

For moderate/complex queries, add a structured planning step before SQL generation:

```json
{
  "tables_needed": ["ClientEngagement", "ConsultantRoster"],
  "join_path": "ClientEngagement.ConsultantID = ConsultantRoster.ConsultantID",
  "filters": [{"column": "Status", "operator": "=", "value": "Active"}],
  "aggregations": [{"function": "COUNT", "column": "*"}],
  "ordering": null,
  "limit": 100
}
```

Validate the plan against the catalog:
- Do all tables exist?
- Do join columns exist and have matching types?
- Do filter columns exist?
- Is the join path connected?

If plan validation fails, re-run planning with error feedback before attempting SQL generation.

#### 3.3 Multi-Candidate Generation + Selection
**File:** modify `app/ai_sql.py`

For complex queries:
1. Generate 3 SQL candidates with temperature=0.3 (diverse but not random)
2. Validate all candidates through the Phase 1 validation pipeline
3. Execute valid candidates
4. Selection logic:
   - If only one succeeds → use it
   - If multiple succeed → prefer the one with fewer joins (simpler is usually more correct)
   - If multiple succeed with same structure → use the one whose EXPLAIN cost is lowest
   - If none succeed → proceed to error-classified repair

#### 3.4 Error Classification + Targeted Repair
**File:** modify `app/ai_sql.py`

Replace generic `propose_sql_repair()` with error-classified correction:

```python
class SQLErrorType(Enum):
    SYNTAX_ERROR = "syntax"           # pglast parse failure
    UNKNOWN_COLUMN = "unknown_column" # sqlglot qualify failure
    UNKNOWN_TABLE = "unknown_table"   # sqlglot qualify failure
    EXECUTION_ERROR = "execution"     # DB runtime error
    EMPTY_RESULT = "empty"            # Query returned 0 rows
    TIMEOUT = "timeout"               # Exceeded 10s limit
    CARTESIAN = "cartesian"           # EXPLAIN detected cartesian product
```

Each error type gets a specialized repair prompt:
- `UNKNOWN_COLUMN` → "Column X doesn't exist. Available columns in table Y: [list]. Did you mean Z?"
- `EMPTY_RESULT` → "Query returned no rows. Filter was: X. Sample values for that column: [values]. Try relaxing the filter or using ILIKE."
- `TIMEOUT` → "Query timed out. Simplify joins or add more specific WHERE conditions."

Max 2 repair attempts (diminishing returns beyond that).

---

### Phase 4: Observability + Feedback Loop
**Goal:** Measure accuracy, collect feedback, enable continuous improvement
**Impact:** Enables compound accuracy gains over time
**Depends on:** Phases 1-2 (can start partially in parallel)

#### 4.1 Langfuse Integration
**File:** modify `app/main.py`, `app/ai_sql.py`

1. `pip install langfuse`
2. Swap `import openai` → `from langfuse.openai import openai` (drop-in replacement)
3. Add `@observe()` decorators to pipeline functions:
   - `suggest_schema_snippet()` → traces schema routing
   - `propose_sql()` → traces SQL generation
   - `validate_sql()` → traces validation
   - `run_select()` → traces execution
4. Configure dashboards:
   - Token usage + cost per day
   - P50/P95 latency breakdown by pipeline stage
   - Error rate by category
   - Repair rate trend
   - Empty result rate trend

#### 4.2 User Feedback UI
**File:** modify `app/static/index.html`, add `POST /feedback` endpoint

Add to the results display:
- Thumbs up / thumbs down buttons
- "Edit SQL" button for power users (opens a modal with the generated SQL, user can correct and re-execute)
- Store feedback in `query_metrics.db`:
  ```sql
  ALTER TABLE query_log ADD COLUMN feedback TEXT;        -- 'positive', 'negative', NULL
  ALTER TABLE query_log ADD COLUMN corrected_sql TEXT;   -- user-corrected SQL, if any
  ALTER TABLE query_log ADD COLUMN feedback_at TEXT;      -- ISO timestamp
  ```

#### 4.3 Feedback → Golden Query Pipeline

When a user gives thumbs up:
- Auto-flag as candidate for golden query library
- Admin reviews periodically via `/admin/problem-queries` dashboard (extend with verification workflow)

When a user provides a SQL correction:
- Store as a high-priority golden query (expert-corrected examples yield up to 14.9% accuracy improvement)
- Embed and add to ChromaDB immediately

When a user gives thumbs down:
- Flag for review
- Log which schema was routed, which examples were retrieved (helps diagnose whether the issue is schema linking, few-shot selection, or generation)

#### 4.4 Evaluation Test Suite
**File:** new `tests/sql_accuracy/`

Build a regression test suite:
1. Curate 100+ (question, expected_SQL, expected_tables) test cases from golden queries
2. Nightly CI job runs all test cases against the pipeline
3. Measures: execution accuracy, empty result rate, schema routing accuracy, repair rate
4. Alerts on regression (accuracy drops >3% from baseline)

#### 4.5 LLM-as-Judge (Sampling)
**File:** new `app/sql_judge.py`

For quality monitoring (not on every request):
1. On 10% of queries + all empty/error queries: run back-translation validation
2. LLM translates SQL back to natural language → compare with original question → score 1-5
3. Log scores to Langfuse for trend analysis
4. Alert if average score drops below threshold

---

### Phase 5: Advanced (Future)
**Lower priority, higher effort. Pursue based on Phase 1-4 results.**

#### 5.1 EXPLAIN Pre-Validation
Run `EXPLAIN (FORMAT JSON)` before execution. Reject if estimated cost > 10,000 or estimated rows > 100,000. Adds 1-50ms latency but catches catastrophic queries.

#### 5.2 Structured Business Glossary
Migrate `*_aliases.csv` to a single `business_glossary.yaml` with categories, descriptions, confidence scores, and table/column links. Add embedding-based fuzzy synonym resolution for novel phrasings.

#### 5.3 Schema Drift Detection
Add Atlas or a custom diff script to CI that compares live PostgreSQL schema against committed `schema_descriptions.yaml`. When drift detected: auto-generate updated descriptions, open a PR for review.

#### 5.4 Self-Hosting Option
Evaluate Snowflake Arctic-Text2SQL-R1-7B as an alternative to OpenAI for SQL generation. 68.9% on BIRD with 95x fewer parameters than GPT-4o. Would eliminate API dependency and reduce per-query cost to near zero. Requires GPU infrastructure.

#### 5.5 Natural Language Feedback
FISQL-inspired: user says "also show end dates" → system modifies SQL based on feedback. Corrects 2x more errors than simple retry. Requires conversational state management.

---

## Dependency Graph

```
Phase 1.1 (Schema Descriptions)
    │
    ├──→ Phase 1.2 (Embedding Schema Linking) ──→ Phase 2.3 (Doc RAG)
    │                                              Phase 2.4 (M-Schema Prompt)
    │
    └──→ Phase 1.3 (AST Validation) ──→ Phase 3.3 (Multi-Candidate)

Phase 1.4 (Model Upgrade) ── independent, can do anytime ──

Phase 1.2 ──→ Phase 2.1 (Golden Query Library)
           ──→ Phase 2.2 (Dynamic Few-Shot)

Phase 2.* ──→ Phase 3.1 (Query Classification)
           ──→ Phase 3.2 (Query Planning)
           ──→ Phase 3.4 (Error Classification)

Phase 1.* ──→ Phase 4.1 (Langfuse) ── can start after Phase 1
Phase 2.1 ──→ Phase 4.2 (Feedback UI)
           ──→ Phase 4.3 (Feedback Pipeline)
           ──→ Phase 4.4 (Eval Test Suite)
```

---

## New Dependencies

| Package | Version | Purpose | Size |
|---------|---------|---------|------|
| `chromadb` | >=0.5 | Vector store for RAG (file-based, zero infrastructure) | ~50MB |
| `sqlglot` | >=25.0 | SQL parsing, schema validation, type inference | ~5MB |
| `pglast` | >=7.0 | PostgreSQL syntax validation, fingerprinting | ~2MB (C extension) |
| `langfuse` | >=2.0 | LLM observability, tracing, feedback | ~10MB |

Total: 4 new packages. No new infrastructure (ChromaDB is file-based in `./data/chromadb/`).

---

## What NOT To Do

Based on research, these are explicitly rejected approaches:

| Approach | Why Not |
|----------|---------|
| Adopt Vanna.ai | Repository archived March 2026. No future updates. |
| Add LangChain as dependency | Massive dependency weight. Agent approach unreliable in production. Cherry-pick ideas instead. |
| Replace existing SQL validator | Our safety layer is more rigorous than any OSS tool provides. Augment, don't replace. |
| Replace keyword routing entirely | Hybrid (vector + keyword) outperforms pure vector. Keep synonyms/aliases as a boost signal. |
| Switch to DataHerald | Requires MongoDB + Docker. Development slowing. |
| Self-host 70B model | Unless query volume justifies GPU cost. Start with API-based models. |
| Add a full semantic layer (Cube.js) | Overkill for a single-app use case. Our YAML-based approach is the right weight. |

---

## Success Metrics

| Metric | Current (Estimated) | Phase 1 Target | Phase 2 Target | Phase 3+ Target |
|--------|-------------------|----------------|----------------|-----------------|
| Execution accuracy | ~60% | ~75% | ~83% | ~88% |
| Valid SQL rate | ~85% | ~95% | ~96% | ~97% |
| Empty result rate | ~25% | ~15% | ~10% | ~7% |
| Repair rate | ~30% | ~20% | ~12% | ~8% |
| Avg latency (P95) | ~3s | ~4s | ~4.5s | ~5s |
| Cost per query | ~$0.002 | ~$0.004 | ~$0.008 | ~$0.02 (complex) |

Note: Latency and cost increase slightly as the pipeline adds steps, but accuracy gains far outweigh this. Complex queries cost more but should be a small fraction of total volume.

---

## Research Reports

Detailed findings backing this plan are in:
- `docs/nl2sql-research-2025-2026.md` -- Agentic architectures, schema linking, self-correction, benchmarks
- `docs/semantic-layer-research.md` -- Semantic tools, metadata generation, drift detection
- `docs/RAG_FOR_NL2SQL_RESEARCH.md` -- Few-shot retrieval, golden queries, documentation RAG
- `docs/research-sql-validation-observability.md` -- AST validation, EXPLAIN, LLM-as-judge, Langfuse
- `docs/nl-to-sql-tools-research.md` -- Vanna, DataHerald, LangChain, LlamaIndex, SQLCoder evaluation
