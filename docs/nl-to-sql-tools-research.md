# NL-to-SQL Tools & Frameworks Research Report

**Date:** April 2026
**Purpose:** Evaluate open-source NL-to-SQL tools for potential adoption or idea incorporation into the SSA Data Assistant.

---

## Table of Contents

1. [Vanna.ai](#1-vannaai)
2. [DataHerald](#2-dataherald)
3. [Waii (waii.ai)](#3-waii-waiiai)
4. [LangChain SQL Agent](#4-langchain-sql-agent)
5. [LlamaIndex NL-to-SQL](#5-llamaindex-nl-to-sql)
6. [SQLCoder / Defog](#6-sqlcoder--defog)
7. [Other Notable Tools (2025-2026)](#7-other-notable-tools-2025-2026)
8. [Comparative Analysis](#8-comparative-analysis)
9. [Recommendations for SSA Data Assistant](#9-recommendations-for-ssa-data-assistant)

---

## 1. Vanna.ai

### Architecture Overview

Vanna is a Python RAG (Retrieval-Augmented Generation) framework for NL-to-SQL. Its core design follows a two-step pattern:

1. **Train** a RAG "model" on your data (DDL, documentation, sample SQL queries)
2. **Ask** questions in natural language, which retrieves the 10 most relevant training items and uses them in the LLM prompt to generate SQL

Vanna 2.0 (released late 2024) was a complete architectural rewrite introducing:
- **Agent-based API** replacing the legacy `VannaBase` class methods
- **User-aware architecture** where every component knows user identity
- **Lifecycle hooks, LLM middlewares, conversation storage, observability, context enrichers**
- **ToolRegistry** pattern for agent tool management

The base class hierarchy uses multiple inheritance: you create a custom class inheriting from both a vector store backend (e.g., `ChromaDB_VectorStore`) and an LLM backend (e.g., `OpenAI_Chat`).

### Key Features

- **Pluggable LLMs:** OpenAI, Anthropic, Google Gemini, Ollama (local), Mistral, and more
- **Pluggable vector stores:** ChromaDB, Qdrant, Pinecone, FAISS, Weaviate, Marqo, and others
- **Training methods:** DDL statements, documentation strings, SQL query examples, or auto-training from `information_schema`
- **Built-in FastAPI server** (`VannaFastAPIServer`) for deployment
- **Plotly chart generation** from query results
- **Streaming support** via SSE endpoints

### Accuracy/Quality

- Claims high accuracy through RAG approach (retrieves most relevant training data per question)
- No published benchmark numbers on BIRD or Spider
- Accuracy depends heavily on the quality and quantity of training data provided
- Works best when trained with representative SQL examples for the target schema

### FastAPI Integration

Vanna provides a built-in `VannaFastAPIServer` with endpoints for chat (POST `/api/vanna/v2/chat_sse`), health checks, and an optional web UI. However, there are significant reported issues:
- **Version confusion:** `pip install "vanna[anthropic,fastapi]"` installs v0.1.0 instead of v2.x
- **404 errors** on FastAPI endpoints in some installations
- **Module import failures** between v1 and v2

### License & Maintenance

- **License:** MIT
- **GitHub stars:** ~23.2k
- **CRITICAL: Repository was archived (read-only) on March 29, 2026.** No new issues, PRs, or code changes possible.
- Last active development was late 2025 / early 2026

### Notable Limitations

- **Archived repo** -- no future updates or bug fixes from the community
- **Training data dependency** -- requires significant upfront investment in training data
- **Version instability** -- v2.0 had rough edges with FastAPI server, import issues
- **No built-in SQL validation** -- relies on the LLM to generate safe SQL
- **No built-in security layer** -- no SELECT-only enforcement, no keyword blocklist

### Ideas to Incorporate

- **RAG for few-shot examples:** Retrieve the most relevant past queries as few-shot examples for the LLM prompt. Our system already does schema routing; adding vector-similarity retrieval of past successful queries would improve accuracy.
- **Training on DDL + documentation + SQL triples:** The three-source training approach (schema, docs, examples) is effective.
- **User-aware context enrichment:** Passing user identity/role into the prompt pipeline for permission-aware SQL generation.

---

## 2. DataHerald

### Architecture Overview

DataHerald is an enterprise NL-to-SQL engine with a modular, microservices architecture:

```
User Question
    |
    v
[LangChain Agent] -- chooses tools:
    |-- Schema Lookup
    |-- Few-Shot Retrieval (Vector Store)
    |-- Fine-tuned LLM (optional)
    |-- SQL Generator
    |-- Evaluator (scores SQL quality)
    |
    v
Generated SQL + Confidence Score
    |
    v
[Execution + Self-Correction Loop]
```

Key modules (all replaceable via base class extension):
- **SQL Generator** -- generates SQL from natural language
- **Vector Store** -- stores context data (sample SQL, schema info); defaults to MongoDB for application state
- **Evaluator** -- scores accuracy of generated SQL
- **DB Connector** -- supports Postgres, DuckDB, BigQuery, ClickHouse, Databricks, Snowflake, MySQL/MariaDB, MS SQL Server, Redshift, AWS Athena

### Key Features

- **Dual agent architecture:** RAG-only agent (few-shot prompting) and an advanced agent using a fine-tuned LLM-as-a-tool
- **Self-correction:** Evaluator module scores generated SQL; if below threshold, triggers regeneration
- **Verified queries:** Admin can verify correct SQL, which gets prioritized in future retrievals
- **Confidence scoring:** Each generated query gets an accuracy score
- **Admin console:** GUI for configuration, monitoring, and query verification
- **Fine-tuning pipeline:** Can fine-tune a custom model on your verified query pairs
- **Slackbot integration** for end-user access

### Accuracy/Quality

- No published benchmark numbers
- Accuracy improves over time through the verified query feedback loop
- The fine-tuned LLM-as-a-tool approach reportedly outperforms pure RAG on complex queries
- Self-correction loop catches many execution errors

### FastAPI Integration

DataHerald runs as a Docker-based microservice with its own REST API. Integration with an existing FastAPI app would require:
- Running DataHerald as a sidecar service
- Making HTTP calls from your FastAPI app to DataHerald's API
- Or extracting the engine module and embedding it directly (complex due to MongoDB dependency)

### License & Maintenance

- **License:** Apache 2.0
- **GitHub stars:** ~3.6k
- **Maintenance:** Development has slowed significantly in 2025-2026; last major contributions over a month old as of early 2026
- The company focuses more on their hosted/enterprise offering

### Notable Limitations

- **Heavy infrastructure:** Requires MongoDB, Docker, vector database -- complex deployment
- **Slowing development:** Open-source version appears deprioritized vs. commercial
- **MongoDB dependency** for application state is non-trivial
- **No standalone library** -- it's a full service, not a pip-installable library
- **Limited documentation** for advanced customization

### Ideas to Incorporate

- **Evaluator/confidence scoring:** Adding a post-generation SQL quality evaluator that scores queries before execution.
- **Verified query feedback loop:** Storing admin-verified correct query pairs and using them as prioritized few-shot examples.
- **Fine-tuning pipeline concept:** If query volume justifies it, fine-tuning a smaller model on our specific schema's verified queries.

---

## 3. Waii (waii.ai)

### Architecture Overview

Waii built a sophisticated NL-to-SQL engine centered on a **dynamic metadata knowledge graph**:

```
Natural Language Question
    |
    v
[Knowledge Graph] -- encodes tables, columns, metrics, relationships
    |
    v
[Dialect-Aware SQL Compiler]
    |
    v
[Query Optimizer]
    |
    v
Executable SQL (optimized for target DB dialect)
```

Key architectural components:
- **Metadata Knowledge Graph:** Maps the enterprise's entire data landscape -- tables, columns, metrics, and their semantic relationships
- **Unified Semantic Layer:** Business terms mapped to technical schema elements
- **Dialect-Aware SQL Compiler:** Generates correct SQL for each target database platform
- **Built-in Query Optimizer:** Ensures generated SQL performs well
- **Continuous learning** through document integration, external system integration, training examples, and user feedback

### Key Features

- **Broad database support:** Postgres, Trino, MySQL, Databricks, Snowflake, SQL Server, BigQuery, Athena, Presto, Redshift, Oracle, MongoDB, SQLite, OSQuery
- **Semantic layer integration:** DataHub, dbt, cube.dev, OpenMetadata.org
- **API-first design** with SDK available (JS SDK on GitHub)

### Accuracy/Quality

- No publicly available benchmark numbers
- Enterprise-grade accuracy claims based on the knowledge graph approach
- The semantic layer approach reportedly reduces ambiguity significantly

### FastAPI Integration

- **Not possible.** Waii was acquired by Salesforce (completed August 15, 2025) and is being integrated into Salesforce Data Cloud, Agentforce, and Tableau Next.
- The standalone API may be deprecated or folded into Salesforce products.
- Not open source; no self-hosted option available.

### License & Maintenance

- **Proprietary** -- never open-sourced
- **Acquired by Salesforce** in August 2025
- JS SDK exists on GitHub but the core engine is proprietary
- Future availability as a standalone product is uncertain

### Notable Limitations

- **Not available for adoption** -- proprietary, now owned by Salesforce
- **No open-source alternative** with the same knowledge graph approach
- **Vendor lock-in risk** if integrated as a service

### Ideas to Incorporate

- **Semantic layer / knowledge graph concept:** Building a richer metadata layer that maps business terms to schema elements. Our `column_semantics.csv` and `*_aliases.csv` files are a lightweight version of this -- could be expanded.
- **Dialect-aware SQL compilation:** If we ever support multiple database backends.
- **Continuous learning from user feedback:** Systematically incorporating corrections.

---

## 4. LangChain SQL Agent

### Architecture Overview

LangChain's SQL agent uses a ReAct (Reasoning + Acting) agent pattern:

```
User Question
    |
    v
[ReAct Agent] (powered by LLM)
    |-- Tool: sql_db_list_tables  -- lists available tables
    |-- Tool: sql_db_schema       -- gets CREATE TABLE for specific tables
    |-- Tool: sql_db_query         -- executes SQL and returns results
    |-- Tool: sql_db_query_checker -- LLM reviews SQL before execution
    |
    v
Agent reasons about which tools to use, iterates until answer found
```

Current recommended approach (2025+):
- Uses `create_react_agent` from `langgraph.prebuilt`
- Pulls system prompts from LangChain Hub (`hub.pull("langchain-ai/sql-agent-system-prompt")`)
- `SQLDatabaseToolkit` wraps a `SQLDatabase` object with the tool set
- Supports customizable prompts and tool configurations

### Key Features

- **Agentic approach:** The agent decides autonomously which tables to inspect, what SQL to write, and whether to retry
- **Schema discovery:** Agent uses `sql_db_list_tables` and `sql_db_schema` tools to explore the database dynamically
- **Error recovery:** If a query fails, the agent can see the error and rewrite the SQL
- **Query checking:** Optional `sql_db_query_checker` tool uses an LLM to review SQL before execution
- **LangGraph integration:** Modern implementations use LangGraph for more structured agent flows
- **Any LLM:** Works with OpenAI, Anthropic, Google, local models, etc.

### Accuracy/Quality

- **Significant accuracy concerns reported in production:**
  - Returns wrong numbers with confidence
  - Joins on wrong keys
  - Mixes up time zones
  - Uses stale or wrong tables
  - Works well on tutorial databases but struggles with custom/complex schemas
- No published benchmark numbers for the agent approach
- Accuracy depends heavily on the LLM used and prompt engineering

### FastAPI Integration

Straightforward -- LangChain is a Python library that can be called from any FastAPI endpoint:

```python
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langgraph.prebuilt import create_react_agent

db = SQLDatabase.from_uri(dsn)
toolkit = SQLDatabaseToolkit(db=db, llm=llm)
agent = create_react_agent(llm, toolkit.get_tools())
# Call agent from FastAPI endpoint
```

### License & Maintenance

- **License:** MIT
- **Very actively maintained** -- LangChain is one of the most active AI framework projects
- Large community, frequent releases
- SQL tools are in `langchain-community` package

### Notable Limitations

- **Accuracy on complex schemas:** The autonomous agent approach can go off the rails with large or complex schemas
- **Cost:** Multiple LLM calls per question (listing tables, getting schemas, writing SQL, checking SQL) -- 3-6x more expensive per query
- **Latency:** Multiple round-trips to the LLM add significant latency
- **Unpredictable behavior:** Agent may take unexpected paths, hard to debug
- **No built-in SQL safety validation** beyond what the LLM provides
- **Schema context window:** For large databases, the agent may not efficiently discover the right tables
- **Dependency weight:** LangChain brings in many transitive dependencies

### Ideas to Incorporate

- **Query checker tool concept:** Using an LLM to review generated SQL before execution (our system does static validation but not semantic checking).
- **Tool-use pattern:** The idea of giving the SQL generation LLM access to tools (list tables, get schema, check query) rather than providing everything upfront could improve handling of ambiguous questions.
- **LangGraph's structured agent flows:** More predictable than pure ReAct agents for production use.

---

## 5. LlamaIndex NL-to-SQL

### Architecture Overview

LlamaIndex provides multiple approaches at different complexity levels:

**Simple (NLSQLTableQueryEngine):**
```
User Question + Specified Tables
    |
    v
[LLM generates SQL using table schemas]
    |
    v
Execute SQL -> Synthesize natural language response
```

**Advanced (SQLTableRetrieverQueryEngine):**
```
User Question
    |
    v
[ObjectIndex over table schemas] -- retrieves relevant tables
    |
    v
[LLM generates SQL with retrieved table schemas]
    |
    v
Execute SQL -> Synthesize natural language response
```

**Workflow-based (Advanced Text-to-SQL Workflow):**
```
User Question
    |
    v
[Semantic Table Retrieval] -- finds relevant tables via embeddings
    |
    v
[Sample Row Retrieval] -- retrieves example rows for context
    |
    v
[SQL Generation with full context]
    |
    v
[Retry Policy on failure] -- configurable retry with backoff
    |
    v
Execute SQL -> Response synthesis
```

### Key Features

- **Table retrieval via embeddings:** `ObjectIndex` indexes table schemas, retrieves relevant ones based on semantic similarity to the question
- **Row-level retrieval:** Embeds individual rows and retrieves the most relevant ones as context for SQL generation
- **Column value retrieval:** Retrieves semantically similar column values to help with filtering
- **Workflow system:** Multi-step orchestration with built-in retry policies (exponential backoff, configurable max attempts)
- **Response synthesis:** Can generate natural language answers from SQL results, not just raw data
- **Any LLM supported** via LlamaIndex's LLM abstraction

### Accuracy/Quality

- No published benchmark numbers for the built-in engines
- The advanced workflow approach with table + row retrieval reportedly outperforms simple approaches significantly
- Quality depends on the retrieval quality and LLM used
- Row-level and column-value retrieval are unique and address a real accuracy gap

### FastAPI Integration

LlamaIndex is a Python library -- straightforward to embed in FastAPI:

```python
from llama_index.core import SQLDatabase
from llama_index.core.query_engine import NLSQLTableQueryEngine

sql_database = SQLDatabase(engine, include_tables=["table1", "table2"])
query_engine = NLSQLTableQueryEngine(sql_database=sql_database)
# Call from FastAPI endpoint
response = query_engine.query("What are the top projects?")
```

### License & Maintenance

- **License:** MIT
- **Actively maintained** -- LlamaIndex is a major AI framework
- Good documentation with detailed examples
- Active community and frequent releases

### Notable Limitations

- **No built-in SQL safety validation** -- no SELECT-only enforcement
- **SQLAlchemy dependency** -- requires SQLAlchemy ORM layer (our project uses raw psycopg)
- **Context window pressure:** For large schemas, even the retriever approach can struggle
- **Response synthesis overhead:** The default flow generates a natural language response, adding latency
- **Less control over SQL generation** compared to hand-crafted prompt engineering
- **No join path guidance** -- doesn't have a concept like our `join_map.json`

### Ideas to Incorporate

- **Semantic table retrieval via embeddings:** Instead of our keyword/synonym scoring in `suggest_schema_snippet()`, embedding table schemas and retrieving by similarity could improve recall for ambiguous questions.
- **Row-level context retrieval:** Embedding and retrieving sample rows as context for the LLM prompt -- especially useful for filter value matching.
- **Column value retrieval:** Using embeddings to find the right column values (similar to our `allowed_values/*.csv` but with semantic matching instead of exact/fuzzy matching).
- **Retry policies with backoff:** Our single retry in `propose_sql_repair()` could be enhanced with configurable retry policies.

---

## 6. SQLCoder / Defog

### Architecture Overview

SQLCoder is a family of specialized SQL-generation LLMs from Defog:

```
Database Schema (DDL) + Natural Language Question
    |
    v
[SQLCoder Model] -- fine-tuned specifically for SQL generation
    |
    v
SQL Query
```

Model family:
- **SQLCoder (15B)** -- fine-tuned StarCoder, first release
- **SQLCoder-2 (15B)** -- improved version
- **SQLCoder-34B-Alpha** -- larger model, better accuracy
- **SQLCoder-70B-Alpha** -- built on CodeLlama-70B, state-of-the-art among open models

### Key Features

- **Purpose-built for SQL:** Unlike general-purpose LLMs, these models are fine-tuned exclusively for text-to-SQL
- **Self-hostable:** Can run locally or on your own infrastructure
- **Schema-in-prompt:** Takes CREATE TABLE statements as input context
- **No external dependencies:** Just the model -- no vector database, no agent framework needed
- **Fine-tunable:** Can be further fine-tuned on your specific schema for maximum accuracy

### Accuracy/Quality

Published benchmarks (on Defog's sql-eval framework):

| Model | Accuracy |
|-------|----------|
| SQLCoder-70B | 93% (unseen schemas) |
| SQLCoder-70B (date queries) | 96% |
| SQLCoder-70B (ORDER BY) | 97.1% |
| SQLCoder-70B (ratio calcs) | 85.7% |
| GPT-4 | ~85-90% (on same eval) |
| GPT-3.5-turbo | ~70% (on same eval) |

**Important caveat:** These benchmarks are on Defog's own evaluation framework, not standard benchmarks like BIRD or Spider. Results may differ on other benchmarks.

Training data: 20,000+ carefully curated human-written SQL examples.

### FastAPI Integration

Can be integrated as a replacement for the OpenAI API call in your pipeline:

```python
# Option 1: Self-host with vLLM/TGI and call via API
# Option 2: Use Hugging Face transformers directly
from transformers import AutoModelForCausalLM, AutoTokenizer

model = AutoModelForCausalLM.from_pretrained("defog/sqlcoder-70b-alpha")
tokenizer = AutoTokenizer.from_pretrained("defog/sqlcoder-70b-alpha")
# Generate SQL from prompt
```

**However:** The 70B model requires significant GPU resources (multiple A100 GPUs). The 7B model is more practical for self-hosting.

### License & Maintenance

- **License:** Apache 2.0 (for SQLCoder-2), CC-BY-SA-4.0 (for 70B-alpha)
- **Available on Hugging Face** for download
- Defog also provides `sql-eval` framework (open source) for benchmarking
- Active development, though model releases are periodic rather than continuous

### Notable Limitations

- **Infrastructure requirements:** 70B model needs substantial GPU resources
- **No RAG built in:** Just a model -- doesn't include retrieval, schema routing, or context management
- **No error correction:** Single-shot generation; doesn't self-correct
- **Schema size limits:** Context window limits how much schema can be provided
- **Stale knowledge:** Fine-tuned on a fixed training set; doesn't learn from your data over time
- **Not a framework:** You still need to build the surrounding pipeline (schema selection, validation, execution, error handling)

### Ideas to Incorporate

- **Specialized SQL model as a component:** Could replace or supplement GPT-4o-mini for SQL generation specifically, potentially improving accuracy while reducing cost (if self-hosting is feasible).
- **Fine-tuning on our schema:** If we accumulate enough verified query pairs, fine-tuning a smaller model on our specific schema could outperform general-purpose models.
- **Defog's sql-eval framework:** Could adapt their evaluation methodology for testing our own system's accuracy.

---

## 7. Other Notable Tools (2025-2026)

### 7a. Snowflake Arctic-Text2SQL-R1

**What it is:** A family of reasoning-first models from Snowflake AI Research, using Group Relative Policy Optimization (GRPO) with execution-based reward signals.

**Key results:**
- Arctic-Text2SQL-R1-32B: **71.83% on BIRD** (state-of-the-art among all models, open and proprietary)
- Arctic-Text2SQL-R1-14B: **70.04% on BIRD**
- Arctic-Text2SQL-R1-7B: **68.9% on BIRD** (outperforms GPT-4o with 95x fewer parameters)

**License:** Open source on Hugging Face
**Why it matters:** Proves that small, specialized models can beat general-purpose giants. The 7B model is practical to self-host.

### 7b. Wren AI

**What it is:** Open-source text-to-SQL + text-to-chart GenBI agent with a built-in semantic layer.

**Architecture:**
- **Wren UI:** Web interface for questions and data modeling
- **Wren AI Service:** Python/FastAPI pipeline -- intent classification, vector retrieval (Qdrant), LLM prompting, SQL correction loops
- **Wren Engine:** Rust + Apache DataFusion semantic engine with MDL (Modeling Definition Language)

**Key features:**
- Semantic layer (MDL) encodes business definitions once, grounds all queries
- Supports 12+ databases and any LLM (OpenAI, Claude, Gemini, Ollama)
- RAG architecture using Qdrant for schema/context retrieval
- SQL correction loops for self-healing

**License:** AGPL-3.0
**GitHub stars:** ~6,000+
**Why it matters:** The closest architectural analog to what we could build -- a FastAPI-based system with a semantic layer, RAG retrieval, and correction loops. The MDL concept is particularly relevant.

### 7c. Contextual AI's BIRD-SQL Pipeline

**What it is:** Open-sourced pipeline that achieved #1 on BIRD benchmark (February 2025).

**Architecture:** Two-stage system:
1. **Candidate generation:** Generate multiple SQL candidates with diverse prompting
2. **Candidate selection:** Filter and rank candidates to select the best one

**License:** Open source on GitHub
**Why it matters:** The multi-candidate generation + selection approach is a proven accuracy booster that could be adapted into any system.

### 7d. Google NL2SQL Studio

**What it is:** Open-source toolkit from Google Cloud Platform for building NL2SQL pipelines.

**Key features:**
- Web UI for schema input, query testing, and result visualization
- Library integration framework to compare different NL2SQL approaches
- Built-in evaluation metrics and benchmarking tools
- RLHF capabilities for improving accuracy from human feedback
- Multi-turn chat support
- Lightweight local deployment option (nl2sql-lite)

**License:** Apache 2.0
**Why it matters:** The evaluation and benchmarking framework is valuable for systematically measuring accuracy improvements.

### 7e. DBHub (Bytebase)

**What it is:** Universal database MCP server that bridges AI assistants and databases.

**Key details:** Not directly NL-to-SQL but provides the database interface layer for AI tools like Claude, Cursor, and VS Code. 100K+ downloads by early 2026.

**License:** Open source (MIT)

### 7f. New Benchmarks

- **BIRD-Interact (June 2025):** Conversational and agentic evaluation modes
- **LiveSQLBench:** Contamination-free benchmark covering full SQL spectrum
- **BIRD-CRITIC (SWE-SQL):** Diagnostic benchmark for SQL debugging

---

## 8. Comparative Analysis

### Feature Matrix

| Feature | Vanna.ai | DataHerald | LangChain SQL | LlamaIndex | SQLCoder | Wren AI |
|---------|----------|------------|---------------|------------|----------|---------|
| **Architecture** | RAG + LLM | Agent + RAG + Fine-tune | ReAct Agent | Query Engine + Retriever | Specialized LLM | Semantic Layer + RAG |
| **License** | MIT | Apache 2.0 | MIT | MIT | Apache 2.0 / CC-BY-SA | AGPL-3.0 |
| **Active Development** | ARCHIVED | Slowing | Very Active | Very Active | Periodic | Active |
| **Self-hostable** | Yes | Yes (Docker) | Yes | Yes | Yes (GPU needed) | Yes (Docker) |
| **FastAPI Integration** | Built-in (buggy) | Sidecar service | Easy (library) | Easy (library) | Easy (model call) | Has own FastAPI |
| **SQL Safety** | None built-in | Basic | None built-in | None built-in | None | Unknown |
| **Schema Routing** | Via RAG retrieval | Via vector search | Agent discovers | Via ObjectIndex | Manual | Via semantic layer |
| **Error Recovery** | Manual retry | Self-correction loop | Agent retries | Retry policies | None | Correction loops |
| **Learning from Feedback** | Train new examples | Verified queries | None built-in | None built-in | Fine-tune | User feedback |
| **Infrastructure Needs** | Low (pip install) | High (Docker+Mongo) | Low (pip install) | Low (pip install) | High (GPU) | Medium (Docker) |

### Accuracy Expectations (Rough Ranking)

1. **SQLCoder-70B / Arctic-Text2SQL-R1** -- highest raw SQL generation accuracy on benchmarks
2. **Wren AI / DataHerald** -- good accuracy through semantic layer / feedback loops
3. **Vanna.ai** -- good with sufficient training data
4. **LlamaIndex** -- depends heavily on retrieval quality
5. **LangChain SQL Agent** -- most variable; can be excellent or terrible depending on schema complexity

### Cost/Complexity Tradeoff

| Tool | Setup Effort | Per-Query Cost | Maintenance Burden |
|------|-------------|---------------|-------------------|
| Vanna.ai | Medium (training needed) | Low (1 LLM call) | LOW (archived, frozen) |
| DataHerald | High (Docker, Mongo) | Medium (agent calls) | Medium |
| LangChain SQL | Low (pip install) | HIGH (3-6 LLM calls) | Low |
| LlamaIndex | Low-Medium | Low-Medium | Low |
| SQLCoder | High (GPU infra) | Very Low (self-hosted) | Medium |
| Wren AI | Medium (Docker) | Medium | Medium |

---

## 9. Recommendations for SSA Data Assistant

### What to Adopt Wholesale

**Nothing.** None of these tools should replace the current system wholesale because:
- Our system already handles the specific SSA schema well with custom routing, join maps, and aliases
- Most tools would require significant rearchitecting and add infrastructure complexity
- Our SQL validation layer (`sql_validator.py`) is more rigorous than any of these tools provide
- The tools that are architecturally closest (Vanna, DataHerald) have maintenance/stability concerns

### Ideas to Incorporate (Priority Order)

#### High Priority -- Low Effort

1. **Vector-similarity retrieval of past successful queries (from Vanna, DataHerald)**
   - Store verified question/SQL pairs in a lightweight vector store (ChromaDB is pip-installable)
   - At query time, retrieve the 3-5 most similar past queries as few-shot examples
   - This is the single highest-ROI improvement across all the tools studied
   - Implementation: Add a `query_embeddings` table to SQLite or use ChromaDB alongside existing infrastructure

2. **Multi-candidate SQL generation + selection (from Contextual AI)**
   - Generate 2-3 SQL candidates with temperature > 0
   - Use a lightweight evaluator (LLM or rule-based) to pick the best one
   - Catches many single-shot generation errors
   - Implementation: Modify `propose_sql()` to generate multiple candidates, add selection logic

3. **LLM-based query review before execution (from LangChain)**
   - After generating SQL, use a quick LLM call to review it against the schema
   - "Does this SQL correctly answer the question given these tables?"
   - Implementation: Add a `review_sql()` step between `propose_sql()` and `validate_sql()`

#### Medium Priority -- Medium Effort

4. **Semantic table/column retrieval via embeddings (from LlamaIndex)**
   - Embed table and column descriptions, retrieve by similarity to question
   - Would improve `suggest_schema_snippet()` for ambiguous questions
   - Implementation: Embed our schema hints and column semantics, use for retrieval alongside current keyword scoring

5. **Confidence scoring (from DataHerald)**
   - Assign a confidence score to each generated query
   - Surface to the UI ("High confidence" vs "I'm not sure about this query")
   - Route low-confidence queries for human review
   - Implementation: Add confidence estimation based on schema match quality + LLM self-assessment

6. **Verified query feedback loop (from DataHerald, Vanna)**
   - Allow admins to mark queries as "correct" or "incorrect" via the admin dashboard
   - Store verified pairs and use them as prioritized few-shot examples
   - Implementation: Extend `query_metrics.py` with a verification status field

#### Lower Priority -- Higher Effort

7. **Semantic layer / MDL concept (from Wren AI, Waii)**
   - Formalize our existing config files (aliases, column semantics, join map) into a proper semantic modeling layer
   - Define business terms, calculated metrics, and relationships in a structured format
   - This is what our system is evolving toward but could be more formalized

8. **Specialized SQL model evaluation (from SQLCoder, Arctic-Text2SQL)**
   - If we find GPT-4o-mini accuracy insufficient, evaluate Snowflake's Arctic-Text2SQL-R1-7B as a replacement
   - The 7B model is practical to self-host and outperforms GPT-4o on SQL benchmarks
   - Would eliminate OpenAI API dependency and reduce per-query cost to near zero

9. **Systematic accuracy evaluation (from Google NL2SQL Studio, Defog sql-eval)**
   - Build a test suite of question/expected-SQL pairs for our specific schema
   - Run automated accuracy evaluations when changing prompts or models
   - Implementation: Create a `tests/sql_accuracy/` directory with test cases

### What NOT to Do

- **Don't add LangChain as a dependency** -- it brings massive dependency weight and the agent approach is unreliable for production. Cherry-pick the ideas instead.
- **Don't switch to DataHerald** -- it requires MongoDB and Docker, adds infrastructure complexity, and development is slowing.
- **Don't adopt Vanna.ai** -- the repository is archived with no future development.
- **Don't self-host a 70B model** unless query volume justifies the GPU cost.
- **Don't remove our SQL validator** -- none of these tools have equivalent safety guardrails.

---

## Sources

### Vanna.ai
- [Vanna GitHub Repository](https://github.com/vanna-ai/vanna)
- [Vanna FastAPI Docs](https://vanna.ai/docs/placeholder/deployment/fastapi)
- [Vanna PyPI](https://pypi.org/project/vanna/)
- [Text-to-SQL with Vanna AI (Medium)](https://medium.com/mitb-for-all/text-to-sql-just-got-easier-meet-vanna-ai-your-rag-powered-sql-sidekick-e781c3ffb2c5)

### DataHerald
- [DataHerald GitHub Repository](https://github.com/Dataherald/dataherald)
- [DataHerald on LangChain Blog](https://blog.langchain.com/dataherald/)
- [DataHerald Context Improvement (Medium)](https://medium.com/dataherald/improving-accuracy-of-nl-to-sql-enterprise-use-cases-through-context-fb237b2cfd8e)

### Waii
- [Waii Official Site](https://www.waii.ai/)
- [Waii Overview Docs](https://doc.waii.ai/deployment/docs/waii-overview)
- [Salesforce Acquires Waii](https://www.salesforce.com/news/stories/salesforce-signs-definitive-agreement-to-acquire-waii/)
- [Salesforce Completes Waii Acquisition](https://www.hpcwire.com/bigdatawire/this-just-in/salesforce-completes-acquisition-of-waii-to-advance-natural-language-to-sql-in-data-cloud/)

### LangChain SQL Agent
- [LangChain SQL Agent Docs](https://docs.langchain.com/oss/python/langchain/sql-agent)
- [SQLDatabaseToolkit API Reference](https://python.langchain.com/api_reference/community/agent_toolkits/langchain_community.agent_toolkits.sql.toolkit.SQLDatabaseToolkit.html)
- [Stop LLM SQL Mistakes (Medium)](https://medium.com/@Quaxel/stop-llm-sql-mistakes-5-langchain-tool-policies-fb27be5df383)
- [LangChain SQL Agent Tutorial 2025](https://gist.github.com/shibyan-ai-engineer/e1228f29492811894d93030930b692cd)

### LlamaIndex
- [LlamaIndex Text-to-SQL Guide](https://developers.llamaindex.ai/python/examples/index_structs/struct_indices/sqlindexdemo/)
- [LlamaIndex Advanced Text-to-SQL Workflows](https://developers.llamaindex.ai/python/examples/workflow/advanced_text_to_sql/)
- [NLSQLTableQueryEngine API Reference](https://developers.llamaindex.ai/python/framework-api-reference/query_engine/NL_SQL_table/)

### SQLCoder / Defog
- [Open-sourcing SQLCoder (Defog Blog)](https://defog.ai/blog/open-sourcing-sqlcoder)
- [SQLCoder-70B Blog Post](https://defog.ai/blog/open-sourcing-sqlcoder-70b)
- [SQLCoder GitHub](https://github.com/defog-ai/sqlcoder)
- [SQLCoder-70B on Hugging Face](https://huggingface.co/defog/sqlcoder-70b-alpha)
- [Defog sql-eval Framework](https://github.com/defog-ai/sql-eval)

### Snowflake Arctic-Text2SQL
- [Arctic-Text2SQL-R1 Blog](https://www.snowflake.com/en/engineering-blog/arctic-text2sql-r1-sql-generation-benchmark/)
- [Arctic-Text2SQL-R1-7B on Hugging Face](https://huggingface.co/Snowflake/Arctic-Text2SQL-R1-7B)
- [Arctic-Text2SQL Paper (arXiv)](https://arxiv.org/abs/2505.20315)

### Wren AI
- [Wren AI GitHub](https://github.com/Canner/WrenAI)
- [Wren AI Official Site](https://www.getwren.ai/oss)
- [Wren AI vs. Vanna Comparison](https://www.getwren.ai/post/wren-ai-vs-vanna-the-enterprise-guide-to-choosing-a-text-to-sql-solution)

### Contextual AI
- [Open-Sourcing Best Local Text-to-SQL](https://contextual.ai/blog/open-sourcing-the-best-local-text-to-sql-system)
- [BIRD-SQL GitHub](https://github.com/ContextualAI/bird-sql)

### Google NL2SQL Studio
- [NL2SQL Studio GitHub](https://github.com/GoogleCloudPlatform/nl2sql-studio)
- [NL2SQL Studio Docs](https://googlecloudplatform.github.io/nl2sql-studio/)

### General / Benchmarks
- [Top 5 Text-to-SQL Tools 2026 (Bytebase)](https://www.bytebase.com/blog/top-text-to-sql-query-tools/)
- [NL-to-SQL Guide 2026 (BlazeSQL)](https://www.blazesql.com/blog/natural-language-to-sql)
- [NL-to-SQL Making Databases Accessible (Groundy)](https://groundy.com/articles/natural-language-sql-ai-finally-making-databases/)
- [NL2SQL System Design Guide 2025](https://medium.com/@adityamahakali/nl2sql-system-design-guide-2025-c517a00ae34d)
- [RAG for NL2SQL Enterprise Accuracy](https://autonmis.com/learning/rag-for-nl2sql)
- [BIRD Benchmark](https://bird-bench.github.io/)
- [LiveSQLBench](https://livesqlbench.ai/)
