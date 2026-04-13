# NL2SQL / Text-to-SQL State of the Art: 2025-2026 Research Report

> Compiled April 2026 for planning a major upgrade to the SSA Data Assistant NL2SQL pipeline.

---

## Table of Contents

1. [Agentic / Multi-Step Approaches](#1-agentic--multi-step-approaches)
2. [Schema Linking Best Practices](#2-schema-linking-best-practices)
3. [Self-Correction and Iterative Refinement](#3-self-correction-and-iterative-refinement)
4. [Prompt Engineering for SQL Generation](#4-prompt-engineering-for-sql-generation)
5. [Benchmarks and Accuracy](#5-benchmarks-and-accuracy)
6. [Production Frameworks and Tools](#6-production-frameworks-and-tools)
7. [Recommendations for SSA Data Assistant](#7-recommendations-for-ssa-data-assistant)

---

## 1. Agentic / Multi-Step Approaches

Modern NL2SQL systems have converged on a **multi-agent pipeline** architecture where specialized agents handle distinct sub-tasks. The key insight driving all these systems is: **decompose the NL-to-SQL problem into smaller, well-defined steps instead of asking an LLM to do everything at once.**

### 1.1 SQL-of-Thought (NeurIPS DL4C 2025)

**Architecture:** Five specialized agents in sequence:

1. **Schema Linking Agent** - Extracts relevant tables and columns needed for the question
2. **Subproblem Decomposition Agent** - Breaks the query into clause-level subproblems (WHERE, GROUP BY, JOIN, DISTINCT, ORDER BY, HAVING, EXCEPT, LIMIT, UNION), each expressed as a key-value pair in structured JSON
3. **Query Plan Agent** - Generates a step-by-step execution plan mapping user intent to schema and subproblems; serves as an intermediate reasoning step to organize schema elements, logical conditions, and aggregations
4. **SQL Generation Agent** - Consumes the natural language question + query plan to generate executable SQL
5. **Error Correction Agent** - Classifies errors into a concise taxonomy (missing joins, agg-no-groupby, having-vs-where, etc.) rather than blind regeneration

**Key insight:** Separating planning from generation reduces hallucination and enforces logical structure. The error taxonomy means corrections are targeted, not random retries.

**Results:** State-of-the-art on Spider and its variants.

- Source: [SQL-of-Thought (arxiv.org)](https://arxiv.org/html/2509.00581v2)

### 1.2 MAC-SQL (COLING 2025)

**Architecture:** Three collaborating agents:

1. **Selector** - Prunes the database schema by selecting relevant tables and columns, reducing irrelevant information and input length
2. **Decomposer** - The core agent that systematically decomposes complex questions into progressively refined sub-questions using chain-of-thought reasoning; generates SQL starting from the simplest sub-problem
3. **Refiner** - Executes generated SQL externally, gets execution feedback, and refines erroneous queries

**Key insight:** The Selector agent is critical for large databases. The progressive decomposition means complex nested queries are built incrementally from simpler parts.

- Source: [MAC-SQL (arxiv.org)](https://arxiv.org/abs/2312.11242)
- Code: [github.com/wbbeyourself/MAC-SQL](https://github.com/wbbeyourself/MAC-SQL)

### 1.3 CHESS: Contextual Harnessing for Efficient SQL Synthesis (ICML 2025)

**Architecture:** Four specialized agents:

1. **Information Retriever (IR)** - Extracts relevant data and context from the database
2. **Schema Selector (SS)** - Prunes large schemas (tested on 4000+ column databases with 2% accuracy gain and 5x token reduction)
3. **Candidate Generator (CG)** - Generates high-quality SQL candidates and refines iteratively
4. **Unit Tester (UT)** - Validates queries through LLM-based natural language unit tests (not just execution checks)

**Results:** 71.10% on BIRD test set (within 2% of leading proprietary methods) while requiring ~83% fewer LLM calls. 61.5% on BIRD dev with open-source models.

**Key insight:** The LLM-based unit testing approach is novel -- it generates natural language test cases for the query and validates them, catching semantic errors that execution alone would miss.

- Source: [CHESS (arxiv.org)](https://arxiv.org/abs/2405.16755)

### 1.4 CHASE-SQL (ICLR 2025, Google Cloud / Stanford)

**Architecture:** Multi-path generation + preference-optimized selection:

1. **Divide-and-Conquer Path** - Breaks down complex queries into sub-queries
2. **Chain-of-Thought Path** - Reasoning based on query execution plans (how a DB engine would process it)
3. **Instance-Aware Few-Shot Path** - Generates tailored few-shot examples per query instance
4. **Selection Agent** - A fine-tuned binary selection LLM that ranks candidates via pairwise comparison

**Results:** 73.0% on BIRD test (SOTA at submission), 87.6% on Spider test.

**Key insight:** Generating diverse candidates through multiple reasoning paths and then selecting the best one via a trained ranker. This is an inference-time scaling approach.

- Source: [CHASE-SQL (arxiv.org)](https://arxiv.org/abs/2410.01943)

### 1.5 DIN-SQL (NeurIPS 2024)

**Architecture:** Four decomposed modules (all implemented via prompting):

1. **Schema Linking Module** - Prompt-based identification of relevant database elements
2. **Query Classification** - Classifies each query as: easy, non-nested complex, or nested complex
3. **SQL Generation** - Tailored generation strategy based on classification
4. **Self-Correction** - Post-generation validation and repair

**Results:** Improved Spider SOTA from 79.9% to 85.3%. Greatest improvements on "extra hard" and "hard" difficulty categories. Consistently improves few-shot performance by ~10%.

**Key insight:** Simply breaking the problem into the right level of granularity is enough -- all modules are implemented via prompting, no fine-tuning needed. The query classification step allows routing to different generation strategies.

- Source: [DIN-SQL (arxiv.org)](https://arxiv.org/abs/2304.11015)

### 1.6 Alpha-SQL (ICML 2025, HKUST)

**Architecture:** Uses Monte Carlo Tree Search (MCTS) for SQL construction:

- **LLM-as-Action-Model** dynamically generates SQL construction actions during MCTS
- **Self-supervised reward function** evaluates candidate SQL quality
- Iteratively infers SQL construction actions based on partial reasoning states

**Results:** 69.7% on BIRD dev using a 32B open-source LLM without fine-tuning (outperforms GPT-4o-based zero-shot by 2.5%).

**Key insight:** Tree search over SQL construction actions provides systematic exploration of the solution space, avoiding the "one-shot generation" problem.

- Source: [Alpha-SQL (arxiv.org)](https://arxiv.org/abs/2502.17248)
- Code: [github.com/HKUSTDial/Alpha-SQL](https://github.com/HKUSTDial/Alpha-SQL)

### 1.7 ReFoRCE (Spider 2.0 Leaderboard Leader, 2025)

**Architecture:** Three-mechanism agent:

1. **Self-Refinement** - Iteratively corrects syntax and semantic errors across SQL dialects
2. **Consensus Enforcement** - Majority-vote across multiple candidates to select high-confidence answers
3. **Column Exploration** - Iterative column exploration guided by execution feedback for deferred cases

**Results:** 35.83 on Spider 2.0-Snow, 36.56 on Spider 2.0-Lite (top of Spider 2.0 leaderboard).

- Source: [ReFoRCE (arxiv.org)](https://arxiv.org/abs/2502.00675)

### 1.8 Feather-SQL (IJCNLP 2025)

**Architecture:** A "1+1 Model Collaboration" paradigm:

- **General-purpose chat model** handles reasoning-intensive auxiliary tasks (schema linking, candidate selection)
- **Fine-tuned SQL specialist** focuses on query generation
- Six core modules: schema pruning, schema linking, multi-path generation, multi-candidate generation, correction, and selection

**Key insight:** Pairing a reasoning model with a SQL specialist is more cost-effective than using a frontier model for everything. Relevant for production systems wanting to minimize API costs.

**Results:** ~10% boost on BIRD for models without fine-tuning; SLM accuracy ceiling raised to 54.76%.

- Source: [Feather-SQL (arxiv.org)](https://arxiv.org/abs/2503.17811)

### Summary: Common Agent Architecture Pattern

Nearly all modern systems follow this general flow:

```
Question → Schema Linking → Query Planning/Decomposition → SQL Generation → Validation → [Self-Correction Loop] → Final SQL
```

The key differentiators are:
- **Number of candidate paths** (single vs. multi-path generation)
- **Selection mechanism** (voting, pairwise ranking, execution-based filtering)
- **Error correction approach** (taxonomy-guided vs. blind retry vs. execution feedback)
- **Schema linking method** (embedding-based vs. LLM-based vs. hybrid)

---

## 2. Schema Linking Best Practices

Schema linking -- deciding which tables and columns are relevant to a natural language question -- is consistently identified as the **single most impactful step** in the NL2SQL pipeline. Getting this wrong cascades errors through all downstream steps.

### 2.1 Approaches by Category

#### Embedding-Based Retrieval (Practical, Production-Ready)

**LitE-SQL (EACL 2026):**
- Pre-computes dense embeddings for each column from its schema metadata (table name, column name, data type, sample values)
- Stores embeddings in a vector database (e.g., FAISS, ChromaDB)
- At query time, embeds the user question and retrieves top-K similar columns via cosine similarity
- **Key innovation:** Hard-negative filtered supervised contrastive loss (HN-SupCon) to distinguish semantically similar but functionally irrelevant columns (e.g., "employee_name" vs "manager_name" when only one is needed)
- Source: [LitE-SQL (arxiv.org)](https://arxiv.org/abs/2510.09014)

**RESQL (ReAct Schema Linking, 2025):**
- Merges the ReAct paradigm (reasoning + acting) with schema linking
- LLMs alternate between reasoning about what schema elements are needed and acting (querying a tool to verify column existence, check sample values, etc.)
- Uses cosine similarity on embeddings for initial candidate retrieval
- Source: [RESQL](https://johal.in/resql-react-schema-linking-sql-generation-2025/)

**Production tip:** Caching embeddings in Redis can cut latency by 50%. For large schemas (10K+ elements), use hierarchical linking: table-level retrieval first, then column-level within matched tables.

#### Graph-Based Approaches

**SGU-SQL:**
- Represents user queries and database schemas as unified structured graphs
- Decomposes complicated linked structures with syntax trees
- Uses graph structure to guide LLMs step by step
- Captures foreign key relationships and table connectivity explicitly

**Pathfinding Graph Schema Linking (2025):**
- Uses graph pathfinding algorithms to traverse schema relationships
- Ensures all predicted tables have connecting foreign key paths
- Catches cases where LLMs select semantically relevant but structurally disconnected tables
- Source: [Pathfinding Graph Schema Linking (arxiv.org)](https://arxiv.org/pdf/2505.18363)

#### LLM-Based Approaches

**IBM Research (EDBT 2026):**
- In-depth analysis of LLM-based schema linking
- Explores question decomposition as a pre-processing step for better linking
- Finds that LLMs are good at understanding semantic relationships but often disregard the relational model
- **Foreign Key Path refinement** is critical: all predicted tables must have a connecting path of foreign keys
- Source: [IBM Schema Linking Analysis (openproceedings.org)](https://openproceedings.org/2026/conf/edbt/paper-24.pdf)

**LinkAlign (EMNLP 2025):**
- Scalable schema linking for real-world large-scale multi-database systems
- Multi-round retrieval and similarity scoring
- Designed for production environments with many databases
- Source: [LinkAlign (arxiv.org)](https://arxiv.org/abs/2503.18596)

#### Hybrid Approaches (Recommended)

**CHESS's Schema Selector:**
- Combines LLM-based reasoning with structured pruning
- Tested on industrial databases with 4000+ columns
- 2% accuracy gain + 5x token reduction

**Solid-SQL (COLING 2025):**
- Enhanced schema-linking based in-context learning
- Combines multiple linking signals (lexical match, embedding similarity, LLM reasoning)
- Source: [Solid-SQL (aclanthology.org)](https://aclanthology.org/2025.coling-main.654.pdf)

### 2.2 State-of-the-Art Best Practices

1. **Multi-signal fusion:** Combine lexical matching (exact/fuzzy string match), embedding similarity, and LLM-based semantic reasoning
2. **Hierarchical pruning:** Table-level first, then column-level (reduces token cost dramatically)
3. **Foreign key path validation:** After selecting tables, verify they can be joined via foreign key paths
4. **Hard-negative training:** If using embeddings, train with hard negatives (similar but irrelevant columns)
5. **Value-aware linking:** Include sample values in embeddings/prompts so the LLM can match "California" to a state column
6. **Iterative refinement:** If initial SQL fails, re-run schema linking with the error context

---

## 3. Self-Correction and Iterative Refinement

Self-correction is where the biggest practical gains are. Modern systems go far beyond simple "retry on error."

### 3.1 Error Detection Approaches

#### SQLens (NeurIPS 2025, Amazon)

The most comprehensive error detection/correction framework:

- **Clause-level error detection** (not binary correct/incorrect)
- Integrates signals from both the database (execution results, schema constraints) and the LLM
- **Error taxonomy** includes: question ambiguity, data ambiguity, missing joins, wrong aggregations, incorrect filters, etc.
- Produces interpretable, clause-level error signals that guide targeted correction
- **Results:** Outperforms best LLM self-evaluation by 25.78% F1 for error detection; improves execution accuracy by up to 20%

- Source: [SQLens (arxiv.org)](https://arxiv.org/abs/2506.04494)

#### SQL-of-Thought Error Taxonomy

Classifies errors into actionable categories:
- Missing joins
- agg-no-groupby (aggregation without GROUP BY)
- having-vs-where confusion
- Wrong column references
- Incorrect subquery structure

**Key insight:** Named error categories allow targeted fix strategies instead of generic "please fix this SQL" prompts.

### 3.2 Correction Strategies

#### Execution-Feedback Loop (Most Practical)

Used by MAC-SQL, ReFoRCE, LitE-SQL, and others:

```
Generate SQL → Execute → Check Result
  ├─ Syntax error → Feed error message back to LLM for repair
  ├─ Empty result → Relax filters or check schema linking
  ├─ Unexpected result shape → Verify GROUP BY, aggregations
  └─ Success → Return result
```

**LitE-SQL's execution-guided self-correction:**
- Fine-tuned in two stages: supervised fine-tuning, then execution-guided reinforcement learning
- Enables self-correction without multi-candidate sampling (single-pass correction)

**ExCoT-DPO (2025):**
- Uses on-policy iterative Direct Preference Optimization
- Model generates candidate CoTs and SQL, executes them, uses results as preference signal
- Repeated rounds of self-generated reasoning + execution verification

#### Multi-Candidate + Selection (Higher Accuracy, Higher Cost)

Used by CHASE-SQL, Contextual AI, ReFoRCE:

```
Generate N candidates (diverse paths) → Execute all → Filter valid ones → Rank/vote → Select best
```

- CHASE-SQL: 3 diverse reasoning paths + fine-tuned pairwise ranker
- Contextual AI: Generates diverse candidates, filters by execution, then ranks
- ReFoRCE: Majority-vote consensus across candidates

#### Reflective Reasoning (2026)

- Uses interpreter-based checks AND LLM-based semantic evaluation
- Performs selective reflective updates to only the affected components
- Does not regenerate the entire query -- patches specific clauses
- Source: [Reflective Reasoning for SQL (arxiv.org)](https://www.arxiv.org/pdf/2601.06678)

#### RoboPhD: Self-Improving (2025-2026)

- Every generated SQL undergoes agentic answer evaluation
- Model reviews its own query execution results in context of the original question
- Responds with acceptance or an improved SQL query
- Source: [RoboPhD (arxiv.org)](https://www.arxiv.org/pdf/2601.01126)

### 3.3 Practical Self-Correction Pipeline

Based on the research, the optimal production correction pipeline is:

1. **Syntax check** - Parse SQL before execution (catches 10-15% of errors for free)
2. **Execute and classify** - Run query, classify result: error / empty / suspicious / good
3. **Error-specific repair prompt** - Feed classified error + original question + schema back to LLM
4. **Semantic validation** - For non-empty results, optionally verify the result makes sense given the question
5. **Max 2-3 retries** - Diminishing returns beyond 2-3 correction rounds

---

## 4. Prompt Engineering for SQL Generation

### 4.1 Schema Representation in Prompts

#### DDL Format (Basic)
```sql
CREATE TABLE employees (
  id INTEGER PRIMARY KEY,
  name VARCHAR(100),
  department_id INTEGER REFERENCES departments(id)
);
```
- Pros: Familiar to LLMs, includes constraints and types
- Cons: Verbose, doesn't convey semantics

#### M-Schema Format (Enhanced, Recommended)
Uses SQLAlchemy-style reflection to provide:
- Table and column names with data types
- Foreign key relationships explicitly listed
- Representative sample values for each column
- Natural language descriptions of columns

**Research finding:** M-Schema with sample values consistently outperforms bare DDL across all benchmarks. The sample values are critical for the LLM to understand what data actually looks like.

#### Enriched DDL (Practical Middle Ground)
Augment DDL with:
- Column descriptions as comments
- Business rules as comments
- Sample values as comments
- Foreign key annotations

### 4.2 Few-Shot Example Selection

#### DAIL-SQL (VLDB 2024, 86.6% on Spider)

Systematic study of prompt engineering for NL2SQL:

- **Question representations tested:** 5 different formats; Code Representation Prompt and OpenAI Demonstration Prompt are best
- **Example selection:** Must consider BOTH question similarity AND query similarity (not just one)
- **DAIL Organization:** Exclude the full database schema from examples; present only question-query pairs to reduce token cost
- **Results:** 86.6% on Spider test with GPT-4, using only ~1600 tokens per question
- **Self-consistency voting** (generating multiple answers and picking the majority) provides additional 0.4% boost

- Source: [DAIL-SQL (github.com)](https://github.com/BeachWang/DAIL-SQL)

### 4.3 Chain-of-Thought Strategies

#### Query Execution Plan CoT (ICLR 2025)

The reasoning process mirrors database engine execution steps:
1. Identify and locate relevant tables for the question
2. Perform operations (counting, filtering, matching between tables)
3. Select appropriate columns to return

This approach grounds the reasoning in how SQL actually executes, reducing hallucination.

#### Divide-and-Prompt

Divides the text-to-SQL task into subtasks, approaches each through CoT:
- **QDecomp** - Breaks complex user questions into sub-questions
- **QPL** - Query Plan Language as intermediate representation
- **DARA** - Iteratively refines intent understanding

#### Subproblem Decomposition (SQL-of-Thought)

Decomposes into SQL clause-level subproblems:
```json
{
  "WHERE": "filter employees by department = 'Engineering'",
  "GROUP BY": "group by project name",
  "HAVING": "only groups with count > 5",
  "ORDER BY": "sort by count descending",
  "LIMIT": "top 10"
}
```

### 4.4 Prompt Context Best Practices

Based on all research reviewed:

1. **Include schema with sample values** - M-Schema or enriched DDL with 3-5 sample values per column
2. **Include relevant few-shot examples** - Selected by both question AND SQL similarity; 3-5 examples optimal
3. **Include business context/hints** - Column descriptions, domain-specific terminology mappings
4. **Use structured output** - Ask for JSON with reasoning steps before SQL
5. **Specify SQL dialect explicitly** - PostgreSQL syntax rules, quoting conventions, etc.
6. **Include negative instructions** - "Do NOT use subqueries when JOINs suffice", "Always use double quotes for identifiers"
7. **Provide join paths** - Explicitly list how tables connect via foreign keys
8. **Limit schema to relevant subset** - After schema linking, only include matched tables/columns in prompt

### 4.5 Prompt Template Structure (Recommended)

```
SYSTEM: You are a PostgreSQL SQL expert. Generate read-only SELECT queries.
Rules: [safety rules, dialect rules, quoting rules]

SCHEMA:
[Filtered schema with descriptions and sample values]

JOIN PATHS:
[Relevant foreign key paths between included tables]

EXAMPLES:
[3-5 similar question-SQL pairs]

REASONING INSTRUCTIONS:
1. Identify which tables and columns are needed
2. Determine the join path between tables
3. Identify filters, aggregations, and ordering
4. Write the SQL query

USER: [Natural language question]
```

---

## 5. Benchmarks and Accuracy

### 5.1 Spider 1.0 (Classic Benchmark)

| Method | Execution Accuracy | Year | Notes |
|--------|-------------------|------|-------|
| DAIL-SQL (GPT-4) | 86.6% | 2024 | Few-shot prompting, self-consistency |
| CHASE-SQL | 87.6% | 2025 | Multi-path + preference-optimized selection |
| DIN-SQL | 85.3% | 2024 | Decomposed in-context learning |
| Human Performance | ~93% | - | Estimated upper bound |

### 5.2 BIRD Benchmark (More Realistic, Messy Data)

| Method | Execution Accuracy | Year | Notes |
|--------|-------------------|------|-------|
| Google Cloud (Gemini) | 76.13% | 2025 | Single trained model track |
| CHASE-SQL | 73.0% | 2025 | Multi-path reasoning |
| CHESS | 71.10% | 2025 | Multi-agent, 83% fewer LLM calls |
| Arctic-Text2SQL-R1-32B | 71.83% | 2025 | Snowflake, open-source model |
| Alpha-SQL (32B, zero-shot) | 69.7% | 2025 | MCTS-based, no fine-tuning |
| Human Performance | ~92.96% | - | Expert-level upper bound |

### 5.3 Spider 2.0 (Enterprise-Scale, Very Hard)

| Method | Execution Accuracy | Notes |
|--------|-------------------|-------|
| ReFoRCE | 35.83% (Snow) / 36.56% (Lite) | Top of leaderboard |
| o1-preview | 17.1% | |
| GPT-4o | 10.1% | |

Spider 2.0 uses real enterprise databases with 3000+ columns, multiple SQL dialects (BigQuery, Snowflake), and complex transformation workflows. Even the best systems solve only ~36% of tasks.

### 5.4 Key Takeaways

- **Spider 1.0 is largely saturated** at ~87-88% (human is ~93%)
- **BIRD is the current standard** for realistic evaluation (~71-76% for top systems, human ~93%)
- **Spider 2.0 represents real enterprise difficulty** (~36% for the best, GPT-4o only 10%)
- **Production accuracy estimates:** 70-85% with frontier LLMs out of the box; 86-95% with proper semantic layer and business context; 50-70% on messy enterprise databases with zero context
- **Benchmark reliability concern:** A 2026 study found annotation errors in benchmarks cause relative performance changes of -3% to 31% and rank shifts of up to 3 positions

---

## 6. Production Frameworks and Tools

### 6.1 Vanna 2.0 (Open Source, Python, Production-Ready)

- **Architecture:** RAG-based framework (train on your DDL, SQL examples, and docs; then ask questions)
- **Key features in 2.0:** Agent-based architecture, user-aware components with identity flows, enterprise security (row-level security, audit logging), lifecycle hooks, LLM middlewares, conversation storage, observability/tracing
- **Deployment options:** Jupyter, Streamlit, Flask, Slack, custom API
- **Training data:** DDL statements, example SQL queries, business documentation
- **Vector stores:** Supports ChromaDB, Pinecone, Qdrant, Milvus, and others
- GitHub: [github.com/vanna-ai/vanna](https://github.com/vanna-ai/vanna) (12K+ stars)

### 6.2 Contextual AI's Bird-SQL (Open Source, Local)

- **Architecture:** 2-stage: diverse candidate generation + filtering/ranking
- **Key insight:** Inference-time scaling through parallel candidate generation enables local models to compete with API models
- **Held #1 on BIRD** in February 2025 with fully local models
- GitHub: [github.com/ContextualAI/bird-sql](https://github.com/ContextualAI/bird-sql)

### 6.3 Arctic-Text2SQL-R1 (Snowflake, Open Source)

- **32B parameter model** achieving 71.83% on BIRD (SOTA for open-source single model)
- **14B variant** at 70.04% (top under 30B parameters)
- Specifically trained for SQL generation with reinforcement learning
- Source: [Snowflake Blog](https://www.snowflake.com/en/engineering-blog/arctic-text2sql-r1-sql-generation-benchmark/)

### 6.4 DBHub (Open Source, Multi-DB)

- 100K+ downloads, 2K+ GitHub stars
- Supports PostgreSQL, MySQL, MariaDB, SQL Server, SQLite
- Custom tools defined in configuration files
- Built-in web interface for executing queries
- Security-first: read-only mode and safety controls

### 6.5 Cost and Latency Considerations (2025)

- Multi-agent pipelines with frontier models: **5-15 seconds per query, $0.05-0.30 per complex query**
- Single-pass with smaller models: **1-3 seconds, $0.001-0.01 per query**
- Hybrid approach (small model + frontier model for hard queries): best cost/accuracy tradeoff

---

## 7. Recommendations for SSA Data Assistant

Based on this research, here are prioritized recommendations for upgrading the SSA Data Assistant's NL2SQL pipeline, ordered by impact and implementation effort.

### High Impact, Moderate Effort

#### 7.1 Implement Multi-Step Pipeline (Inspired by DIN-SQL / SQL-of-Thought)

Replace the current single-shot `propose_sql()` with a multi-step pipeline:

```
Question → Schema Linking → Query Classification → Query Planning → SQL Generation → Validation → [Correction Loop]
```

**Why:** DIN-SQL showed that simply decomposing the problem into steps improves accuracy by ~10% with zero fine-tuning. The SSA Data Assistant already has rudimentary schema routing (`suggest_schema_snippet`); this would formalize and enhance it.

**Steps:**
1. Add a dedicated schema linking step using the existing catalog + embedding similarity
2. Add query classification (simple vs. complex vs. nested) to route to different generation strategies
3. Add a structured planning step that outputs the required tables, joins, filters, and aggregations as JSON before SQL generation
4. Keep the existing `propose_sql_repair()` but enhance it with error classification

#### 7.2 Enhance Schema Linking with Embeddings

The current `suggest_schema_snippet()` uses synonym matching and keyword scoring. Upgrade to:

1. **Pre-compute embeddings** for every column (table_name + column_name + data_type + sample_values)
2. **Store in a vector index** (ChromaDB or FAISS -- lightweight, no extra infrastructure)
3. **At query time:** Embed the question, retrieve top-K columns, then validate foreign key paths between matched tables
4. **Combine with existing synonym/alias matching** for a hybrid approach

**Why:** LitE-SQL showed that embedding-based schema linking with hard-negative training is the current SOTA. Even without fine-tuning embeddings, off-the-shelf embeddings + the existing synonym matching would significantly improve schema selection.

#### 7.3 Enrich Prompts with M-Schema Format

Replace bare table/column names in prompts with enriched schema that includes:
- Column descriptions (from `column_semantics.csv`)
- Sample values (query a few from the database or maintain a cache)
- Foreign key relationships explicitly listed
- Business context from disambiguation rules

**Why:** Every study shows that richer schema context in the prompt improves accuracy. The SSA app already has `column_semantics.csv` and `join_map.json` -- these just need to be integrated into the prompt format.

#### 7.4 Implement Error Taxonomy for Self-Correction

Replace the current generic `propose_sql_repair()` with error-classified correction:

1. **Parse the error message** to classify: syntax error, missing column, ambiguous column, permission denied, timeout, empty result, etc.
2. **Use error-specific repair prompts:** "The query returned empty results. The filter used was X. Here are sample values for that column: [values]. Please adjust the filter." vs. generic "fix this SQL"
3. **Limit to 2 retries** (diminishing returns beyond that)

**Why:** SQLens showed 25.78% improvement in F1 for error detection with taxonomy-based classification. SQL-of-Thought's error taxonomy enables targeted fixes.

### Medium Impact, Lower Effort

#### 7.5 Add Few-Shot Example Selection

Maintain a library of (question, SQL) pairs from past successful queries (already logged in `query_metrics.db`). At query time:
- Embed the incoming question
- Retrieve 3-5 most similar past questions with their SQL
- Include in the prompt

**Why:** DAIL-SQL showed this alone achieves 86.6% on Spider. The SSA app already logs queries -- mine the successful ones.

#### 7.6 Add Query Planning Step

Before SQL generation, have the LLM output a structured plan:
```json
{
  "tables_needed": ["ClientEngagement", "ProjectTeam"],
  "join_path": "ClientEngagement.EngagementID = ProjectTeam.EngagementID",
  "filters": [{"column": "Client", "operator": "=", "value": "Acme Corp"}],
  "aggregations": [{"function": "COUNT", "column": "TeamMemberID"}],
  "ordering": null,
  "limit": 100
}
```

Then validate this plan against the catalog before generating SQL. This catches errors before they become SQL syntax issues.

#### 7.7 Multi-Candidate Generation (For Complex Queries)

For queries classified as "complex," generate 3 candidates with different reasoning approaches (temperature variation), execute all, and pick the one that returns valid results. Use majority voting if multiple succeed.

**Why:** CHASE-SQL and Contextual AI showed this provides 2-5% accuracy gains. Only apply to complex queries to manage cost.

### Longer-Term / Advanced

#### 7.8 Consider Vanna 2.0 or Build Custom RAG Layer

Evaluate whether adopting Vanna 2.0's RAG architecture (train on DDL + example queries + docs) could replace the current prompt construction. This would provide:
- Automatic retrieval of relevant schema and examples
- Built-in conversation context
- Enterprise features (audit, rate limiting)

#### 7.9 Fine-Tune a Small Model for Schema Linking

If API costs become a concern, fine-tune a small local model (e.g., based on Feather-SQL's approach) specifically for schema linking, and use the frontier model only for SQL generation.

#### 7.10 Implement Semantic Validation

After query execution, optionally have the LLM review the results in context of the original question (RoboPhD approach) to catch cases where the SQL runs successfully but returns wrong data.

---

## Sources

### Agentic Architectures
- [SQL-of-Thought: Multi-agentic Text-to-SQL with Guided Error Correction](https://arxiv.org/html/2509.00581v2)
- [MAC-SQL: A Multi-Agent Collaborative Framework for Text-to-SQL](https://arxiv.org/abs/2312.11242)
- [CHESS: Contextual Harnessing for Efficient SQL Synthesis](https://arxiv.org/abs/2405.16755)
- [CHASE-SQL: Multi-Path Reasoning and Preference Optimized Candidate Selection](https://arxiv.org/abs/2410.01943)
- [DIN-SQL: Decomposed In-Context Learning of Text-to-SQL](https://arxiv.org/abs/2304.11015)
- [Alpha-SQL: Zero-Shot Text-to-SQL using MCTS](https://arxiv.org/abs/2502.17248)
- [ReFoRCE: Self-Refinement, Consensus, Column Exploration](https://arxiv.org/abs/2502.00675)
- [Feather-SQL: Lightweight NL2SQL with Dual-Model Collaboration](https://arxiv.org/abs/2503.17811)
- [An Agentic System for Schema Aware NL2SQL Generation](https://arxiv.org/abs/2603.18018)

### Schema Linking
- [LitE-SQL: Vector-based Schema Linking and Execution-Guided Self-Correction](https://arxiv.org/abs/2510.09014)
- [LinkAlign: Scalable Schema Linking for Real-World Large-Scale Multi-Database](https://arxiv.org/abs/2503.18596)
- [In-depth Analysis of LLM-based Schema Linking (IBM, EDBT 2026)](https://openproceedings.org/2026/conf/edbt/paper-24.pdf)
- [Efficient Schema Linking with Pathfinding Graph](https://arxiv.org/pdf/2505.18363)
- [Solid-SQL: Enhanced Schema-linking based In-context Learning](https://aclanthology.org/2025.coling-main.654.pdf)
- [RESQL: ReAct Schema Linking](https://johal.in/resql-react-schema-linking-sql-generation-2025/)

### Self-Correction
- [SQLens: End-to-End Error Detection and Correction (NeurIPS 2025)](https://arxiv.org/abs/2506.04494)
- [RoboPhD: Self-Improving Text-to-SQL](https://www.arxiv.org/pdf/2601.01126)
- [Reflective Reasoning for SQL Generation](https://www.arxiv.org/pdf/2601.06678)
- [ExCoT-DPO: Execution-Based Verification](https://aclanthology.org/2025.findings-acl.982.pdf)
- [EMLC: Multi-Level Correction Framework](https://www.sciencedirect.com/science/article/abs/pii/S0306457325005011)

### Prompt Engineering
- [DAIL-SQL: Benchmark Evaluation of Prompt Engineering](https://github.com/BeachWang/DAIL-SQL)
- [Chain-of-Thought Prompting for Text-to-SQL](https://arxiv.org/abs/2304.11556)
- [Knowledge Distillation with Structured CoT](https://arxiv.org/pdf/2512.17053)
- [Enterprise NL2SQL Generation on AWS](https://aws.amazon.com/blogs/machine-learning/enterprise-grade-natural-language-to-sql-generation-using-llms-balancing-accuracy-latency-and-scale/)

### Benchmarks
- [Spider 2.0](https://spider2-sql.github.io/)
- [BIRD Benchmark](https://bird-bench.github.io/)
- [BIRD-CRITIC](https://bird-critic.github.io/)
- [Text2SQL Leaderboard (OpenLM)](https://openlm.ai/text2sql-leaderboard/)
- [Text-to-SQL Benchmarks are Broken (CIDR 2026)](https://vldb.org/cidrdb/papers/2026/p5-jin.pdf)

### Production Tools
- [Vanna AI (GitHub)](https://github.com/vanna-ai/vanna)
- [Contextual AI Bird-SQL (GitHub)](https://github.com/ContextualAI/bird-sql)
- [Arctic-Text2SQL-R1 (Snowflake)](https://www.snowflake.com/en/engineering-blog/arctic-text2sql-r1-sql-generation-benchmark/)
- [Awesome LLM-based Text2SQL (Survey + Resources)](https://github.com/DEEP-PolyU/Awesome-LLM-based-Text2SQL)

### Surveys
- [Natural Language to SQL: State of the Art and Open Problems (VLDB 2025)](https://www.vldb.org/pvldb/vol18/p5466-luo.pdf)
- [A Survey on Employing LLMs for Text-to-SQL (ACM Computing Surveys)](https://dl.acm.org/doi/10.1145/3737873)
- [Next-Generation Database Interfaces (TKDE 2025)](https://github.com/DEEP-PolyU/Awesome-LLM-based-Text2SQL)
