# RAG for NL-to-SQL: Research Report

> Research conducted April 2026. Findings for upgrading SSA Data Assistant (FastAPI + OpenAI + PostgreSQL).

---

## Table of Contents

1. [Few-Shot Example Retrieval](#1-few-shot-example-retrieval)
2. [Query History as Training Data](#2-query-history-as-training-data)
3. [Documentation RAG](#3-documentation-rag)
4. [Schema RAG](#4-schema-rag)
5. [Tools and Frameworks](#5-tools-and-frameworks)
6. [Evaluation and Benchmarks](#6-evaluation-and-benchmarks)
7. [Recommended Architecture for SSA Data Assistant](#7-recommended-architecture-for-ssa-data-assistant)
8. [Implementation Roadmap](#8-implementation-roadmap)

---

## 1. Few-Shot Example Retrieval

### The Problem

Static few-shot examples in prompts are a blunt instrument. They consume tokens regardless of relevance and cannot adapt to the enormous variety of questions a production system receives. Modern NL-to-SQL systems dynamically select the most relevant examples at query time using embedding similarity.

### How It Works

1. **Offline**: Collect (question, SQL) pairs. Embed each question using an embedding model. Store embeddings in a vector database.
2. **Online**: When a new question arrives, embed it, retrieve the top-k most similar stored questions by cosine similarity, and inject their (question, SQL) pairs into the LLM prompt.

### Selection Strategies

| Strategy | Description | Used By |
|----------|-------------|---------|
| **Question Similarity** | Embed NL questions, retrieve by cosine similarity | Most systems, Vanna.ai |
| **Masked Question Similarity** | Replace domain-specific entities with generic tokens before embedding, reducing domain bias | DAIL-SQL, OpenSearch-SQL |
| **Question + SQL Skeleton Similarity** | Score candidates on both NL similarity and SQL structural similarity | DAIL-SQL (86.6% on Spider) |
| **Question Classification** | Route to category-specific example pools based on intent/query type | DIN-SQL, multi-agent pipelines |

### Optimal Number of Examples

- **3-5 examples** is the most common sweet spot in production systems. DAIL-SQL and OpenSearch-SQL use 5-shot settings during LLM inference.
- Vanna.ai retrieves **10 pieces of training data** by default (configurable via `n_results_sql`, `n_results_ddl`, `n_results_documentation`).
- Microsoft's NL-to-SQL architecture recommends **50-100 stored examples**, retrieving the **top 5** by cosine similarity at runtime.
- More examples improve coverage but increase token cost and latency. Beyond 5-7 examples, diminishing returns are common.

### Embedding Models for Example Retrieval

| Model | Dimensions | Notes |
|-------|-----------|-------|
| `text-embedding-3-small` (OpenAI) | 1536 | Current recommended default, good cost/quality balance |
| `text-embedding-3-large` (OpenAI) | 3072 | Higher quality, higher cost |
| `text-embedding-ada-002` (OpenAI) | 1536 | Legacy but widely used in existing implementations |
| `all-MiniLM-L6-v2` (Sentence Transformers) | 384 | Free, local, fast; good for prototyping or cost-sensitive deployments |

### Key Insight

Dynamic few-shot retrieval consistently improves accuracy by **4-12%** over static examples across benchmarks. The combination of question similarity with SQL skeleton similarity (DAIL-SQL approach) achieves the best results but is more complex to implement.

---

## 2. Query History as Training Data

### The "Golden Query" Pattern

The most impactful RAG strategy for production NL-to-SQL is building a library of verified (question, SQL, result) tuples from actual usage, then retrieving similar past queries to guide future generation.

### Architecture

```
User asks question
        |
        v
Embed question --> Vector search against golden query store
        |
        v
Retrieve top-k similar golden (question, SQL) pairs
        |
        v
Include as few-shot examples in LLM prompt
        |
        v
Generate SQL --> Execute --> Return results
        |
        v
[Optional] Admin verifies SQL --> Add to golden store
```

### Building the Golden Query Library

**Phase 1: Bootstrap from existing data**
- Mine the SSA Data Assistant's existing `query_metrics.db` SQLite database for successful queries (status != error, rows > 0).
- Extract (question, generated_sql) pairs from historical logs.
- Have a domain expert verify the SQL correctness.

**Phase 2: Continuous learning loop**
- When a generated query executes successfully and returns meaningful results, flag it as a candidate.
- Provide an admin UI (or extend the existing `/admin/problem-queries` dashboard) for data admins to mark queries as "verified" or "rejected."
- Verified queries are embedded and added to the vector store.
- DataHerald's experience shows that as more golden records are added, accuracy improves measurably.

**Phase 3: Feedback signals**
- Track which queries users re-ask (indicating dissatisfaction with prior results).
- Track which queries return 0 rows or trigger the repair loop.
- Use negative signals to identify gaps in the golden library.

### How Many Golden Queries Are Needed?

- DataHerald recommends **20-30 verified examples per table** for meaningful improvement.
- Fine-tuning (a separate strategy) requires at minimum **10 golden SQL queries**, but **200+** for robust results.
- For RAG-based few-shot retrieval, even **50-100 total golden queries** covering the main query patterns provides significant accuracy gains.

### Relevance to SSA Data Assistant

The app already has `query_metrics.py` logging to SQLite with question text, generated SQL, row counts, and error status. This is the raw material for a golden query library. The upgrade path is:

1. Add a `verified` boolean column to `query_metrics`.
2. Embed verified queries using OpenAI embeddings.
3. Store embeddings (ChromaDB file or pgvector in a separate schema).
4. Retrieve top-3 similar golden queries during `propose_sql()`.

---

## 3. Documentation RAG

### What Gets Indexed

For NL-to-SQL systems, "documentation" includes:

| Content Type | Example | Chunking Strategy |
|-------------|---------|-------------------|
| **Business glossary** | "Active consultant = status is 'Active' AND end_date IS NULL" | One chunk per term/definition pair |
| **Business rules** | "Revenue is calculated as hours * bill_rate, excluding internal projects" | One chunk per rule |
| **Column descriptions** | "ClientEngagement.BillRate = hourly rate charged to client in USD" | One chunk per column or per table |
| **Domain knowledge** | "SSA tracks consultants across multiple engagements simultaneously" | Paragraph-level chunks |
| **Query patterns** | "Questions about utilization require joining Timesheet and Engagement tables" | One chunk per pattern |
| **Data quality notes** | "Some legacy records have NULL in Department before 2020 migration" | One chunk per note |

### Chunking Strategy for Database Documentation

Unlike document RAG where you chunk long texts, database documentation is naturally structured:

- **Per-entity chunks**: One chunk per table description, one per column description, one per business rule.
- **Semantic grouping**: Group related columns and their descriptions together (e.g., all date columns in a table).
- **Metadata tagging**: Tag each chunk with table name, column name, and content type for filtered retrieval.

### How Vanna.ai Handles Documentation

Vanna stores documentation as a separate collection in the vector store alongside DDL and SQL examples. When a question arrives, it retrieves relevant documentation chunks independently and includes them in the prompt. The `vn.add_documentation()` method accepts free-text strings describing business terminology, relationships, or rules.

### Relevance to SSA Data Assistant

The app already has structured documentation:
- `column_semantics.csv` -- semantic type and preferred filter per column
- `*_aliases.csv` -- synonym mappings
- `disambiguation.json` -- routing rules
- `join_map.json` -- intent-based join paths

These could be embedded as documentation chunks in a vector store, replacing or augmenting the current keyword-based `suggest_schema_snippet()` approach with semantic retrieval.

---

## 4. Schema RAG

### The Problem with Full Schema in Prompt

Sending the entire database schema in every prompt wastes tokens and confuses the LLM with irrelevant tables/columns. The SSA Data Assistant currently uses `suggest_schema_snippet()` with keyword matching, synonym lookups, and disambiguation rules. Schema RAG replaces or augments this with vector similarity search.

### What Gets Embedded

| Schema Element | Embedding Text Format | Example |
|---------------|----------------------|---------|
| **Table** | Table name + description + purpose | "ClientEngagement: Tracks consultant assignments to client projects with dates, rates, and status" |
| **Column** | Table.Column + type + description + sample values | "ClientEngagement.BillRate (decimal): Hourly billing rate in USD. Typical values: 75.00-250.00" |
| **Relationship** | FK description + join semantics | "ClientEngagement.ConsultantID references Consultant.ID: links an engagement to the assigned consultant" |
| **Composite** | Table summary with all columns listed | Full DDL statement or structured description of table |

### Schema Summarization (Key Technique)

Raw DDL embeds poorly because column names are often cryptic. A critical preprocessing step is **LLM-generated schema summaries**:

1. Feed each table's DDL to an LLM with the prompt: "Describe this table's purpose and what each column means in plain English."
2. Embed the generated summary instead of (or alongside) the raw DDL.
3. This dramatically improves retrieval accuracy because user questions are in natural language, and summaries bridge the vocabulary gap.

### Hybrid Retrieval (Best Practice)

The Semantic-RAG approach combines:
- **Dense vector retrieval**: Cosine similarity between question embedding and schema embeddings
- **Symbolic/keyword lookup**: Exact match on table names, column names, known synonyms
- **Metadata filtering**: Filter by schema area, data domain, or table type before vector search

This hybrid approach outperforms pure vector or pure keyword approaches because:
- Vector search catches semantic matches ("who are our people" -> Consultant table)
- Keyword search catches exact matches ("ClientEngagement" mentioned directly)
- Metadata filtering reduces the search space efficiently

### Relevance to SSA Data Assistant

The current `catalog.py` introspects the database and builds a `Catalog` of `Table` and `Column` dataclasses. These could be:
1. Serialized to descriptive text strings
2. Optionally summarized by an LLM
3. Embedded and stored in a vector store
4. Retrieved by similarity at query time instead of (or alongside) the current scoring in `suggest_schema_snippet()`

---

## 5. Tools and Frameworks

### Comparison Matrix

| Tool | Architecture | RAG Approach | Vector Stores | LLM Support | License | Best For |
|------|-------------|-------------|---------------|-------------|---------|----------|
| **Vanna.ai** | Python library, modular base classes | Stores DDL + docs + question-SQL pairs; retrieves top-10 at query time | ChromaDB, Qdrant, Pinecone, pgvector, Marqo, custom | OpenAI, Anthropic, Ollama, Mistral, any OpenAI-compatible | MIT | Drop-in RAG for existing apps |
| **Wren AI** | Full-stack (Next.js + FastAPI + Rust engine) | Semantic layer (MDL) + Qdrant vector retrieval + SQL correction loops | Qdrant | OpenAI, Claude, Gemini, Ollama | AGPL-3.0 | Full GenBI platform replacement |
| **DataHerald** | API service + LangChain agents | Golden SQL retrieval + schema linking + 7 agent tools | Built-in vector DB | OpenAI (GPT-4) | Apache 2.0 | Enterprise API with admin workflow |
| **LlamaIndex** | Python framework | NLSQLTableQueryEngine + SQLAutoVectorQueryEngine; hybrid SQL + vector | Any (FAISS, Chroma, Qdrant, pgvector) | Any | MIT | Flexible, composable pipelines |
| **LangChain** | Python framework | create_sql_agent with custom retriever tools for few-shot examples | Any (FAISS, Chroma, Qdrant, pgvector) | Any | MIT | Agent-based SQL with tool use |
| **SQLCoder (Defog)** | Fine-tuned LLM (7B-70B) | Schema context in prompt (not vector RAG) | N/A (model-based) | Self-hosted (Llama-based) | Apache 2.0 | Low-latency, self-hosted |
| **BlazeSQL** | Commercial SaaS | Proprietary RAG pipeline | Proprietary | Proprietary | Commercial | Turnkey solution |

### Detailed Analysis of Top Candidates

#### Vanna.ai -- Best Fit for SSA Data Assistant

**Why**: Vanna is a Python library (not a full platform) that can be integrated into an existing FastAPI app. Its modular architecture uses multiple inheritance:

```python
from vanna.openai import OpenAI_Chat
from vanna.chromadb import ChromaDB_VectorStore

class MyVanna(ChromaDB_VectorStore, OpenAI_Chat):
    def __init__(self, config=None):
        ChromaDB_VectorStore.__init__(self, config=config)
        OpenAI_Chat.__init__(self, config=config)

vn = MyVanna(config={
    'api_key': OPENAI_API_KEY,
    'model': 'gpt-4o-mini',
    'path': './data/vanna_chromadb',  # persistent storage
    'n_results_sql': 5,
    'n_results_ddl': 3,
    'n_results_documentation': 3,
})
```

**Training**:
```python
# Add DDL
vn.train(ddl="""
    CREATE TABLE "Project_Master_Database"."ClientEngagement" (
        "EngagementID" INT PRIMARY KEY,
        "ConsultantName" VARCHAR(200),
        "BillRate" DECIMAL(10,2),
        ...
    )
""")

# Add documentation
vn.train(documentation="Active consultants have Status = 'Active' and no EndDate.")

# Add golden query
vn.train(
    question="How many active consultants do we have?",
    sql='SELECT COUNT(*) FROM "Project_Master_Database"."Consultant" WHERE "Status" = \'Active\''
)
```

**Query-time retrieval**: `vn.generate_sql("What is our average bill rate?")` internally retrieves the top-k most relevant DDL, documentation, and SQL examples, assembles them into a prompt, and calls the LLM.

**Integration path**: You can use Vanna's retrieval logic without its execution layer. Call `vn.get_similar_question_sql()`, `vn.get_related_ddl()`, and `vn.get_related_documentation()` to get context, then feed it into your existing `propose_sql()` prompt.

#### Wren AI -- Full Platform Alternative

Wren AI is more opinionated: it provides a complete stack (UI, API, semantic engine, vector store). Its key innovation is the **Modeling Definition Language (MDL)** semantic layer that encodes business definitions, metric calculations, and relationships in a structured format. The LLM generates SQL grounded in MDL semantics rather than raw schema.

**Architecture**: Next.js UI -> Apollo GraphQL -> Python/FastAPI AI Service (RAG + LLM) -> Rust/DataFusion Engine -> Database.

**Tradeoff**: More powerful semantics, but requires adopting the full Wren stack rather than integrating into an existing app. AGPL-3.0 license has copyleft implications.

#### DataHerald -- Enterprise Golden Query Management

DataHerald's key contribution is the **verified golden SQL workflow**:
1. System generates SQL for a question
2. Admin verifies/edits the SQL through a UI
3. Verified pair is stored in vector DB as a "golden record"
4. Future similar questions retrieve golden records as few-shot context
5. Their agent uses **7 tools** including schema linking, SQL execution, and few-shot retrieval

**Architecture**: Two agents -- a RAG-only agent (simpler, few-shot based) and an advanced agent (fine-tuned LLM as a tool). The RAG agent outperforms LangChain's default SQL Agent by 12-250% in their benchmarks.

#### LangChain SQL Agent

LangChain's `create_sql_agent` provides an agent-based approach where the LLM can use tools (query database schema, execute SQL, retrieve examples). For RAG integration:

```python
# Custom retriever tool for few-shot examples
from langchain.tools import Tool
from langchain_community.vectorstores import Chroma

vectorstore = Chroma(persist_directory="./golden_queries")
retriever = vectorstore.as_retriever(search_kwargs={"k": 5})

retriever_tool = Tool(
    name="sql_examples",
    description="Retrieves similar SQL query examples",
    func=retriever.get_relevant_documents
)

agent = create_sql_agent(
    llm=llm,
    db=db,
    extra_tools=[retriever_tool],
    agent_type="openai-tools",
)
```

**Tradeoff**: Maximum flexibility but requires more assembly. Agent-based approach can be slower (multiple LLM calls) but handles complex queries better.

---

## 6. Evaluation and Benchmarks

### Standard Benchmarks

| Benchmark | Size | Focus | Key Metric |
|-----------|------|-------|------------|
| **Spider** | 10,181 questions, 200 DBs | Cross-database generalization, query complexity | Execution Accuracy (EX) |
| **BIRD** | 12,751 questions, 95 DBs (33.4 GB) | Real-world scale, database content/values, efficiency | Execution Accuracy (EX) |
| **Spider 2.0** | Extended | Enterprise workflows, multi-step tasks | Task completion |

### RAG vs. Non-RAG Performance

| Approach | Spider EX | BIRD EX | Notes |
|----------|-----------|---------|-------|
| GPT-4o (zero-shot, full schema) | ~78% | ~55% | Baseline without RAG |
| GPT-4o + static few-shot | ~82% | ~59% | Fixed examples |
| GPT-4o + RAG few-shot retrieval | ~84-86% | ~62-65% | Dynamic example selection |
| DAIL-SQL (GPT-4 + RAG + skeleton) | 86.6% | -- | Best few-shot method |
| DIN-SQL (GPT-4 + chain-of-thought) | 82.8% | -- | Decomposition approach |
| Fine-tuned SQLCoder-70B | ~85% | ~60% | No RAG needed, model-based |
| RAG + embedding fine-tuning | +12% over baseline | +5.79% | Prompt tuning with RAG |
| TailorSQL (workload-tailored) | 2x improvement | -- | Specializes to query patterns |

### Real-World vs. Academic Gap

**Critical finding**: LLMs achieve 85%+ on clean academic benchmarks but **10-20% in real enterprise environments** (per Autonmis research). The gap comes from:
- Ambiguous column names and business terminology
- Complex joins across many tables
- Data quality issues (NULLs, inconsistent formats)
- Domain-specific conventions not in schema

RAG narrows this gap significantly by providing domain context, but does not eliminate it.

### Metrics That Matter for Production

| Metric | What It Measures | Target |
|--------|-----------------|--------|
| **Execution Accuracy** | Does the generated SQL return correct results? | >80% for common queries |
| **Valid SQL Rate** | Does the SQL parse and execute without errors? | >95% |
| **Latency (P95)** | End-to-end response time | <5 seconds |
| **Repair Rate** | How often the retry/repair loop is needed | <15% |
| **Zero-Result Rate** | Queries returning empty results | <10% |
| **Token Cost per Query** | LLM API cost | <$0.05 for simple queries |
| **Golden Query Hit Rate** | How often a similar golden query exists | Track and grow over time |

---

## 7. Recommended Architecture for SSA Data Assistant

### Current Architecture (Baseline)

```
Question --> suggest_schema_snippet() [keyword/synonym matching]
         --> propose_sql() [static system prompt + schema hint + few-shot]
         --> validate_sql() --> run_select()
         --> [on failure] propose_sql_repair()
```

### Proposed RAG-Enhanced Architecture

```
Question
    |
    v
[1] Embed question (OpenAI text-embedding-3-small)
    |
    +---> [2a] Schema RAG: retrieve top-5 relevant table/column descriptions
    |         from vector store (replacing/augmenting suggest_schema_snippet)
    |
    +---> [2b] Example RAG: retrieve top-3 similar golden (question, SQL) pairs
    |         from vector store
    |
    +---> [2c] Documentation RAG: retrieve top-3 relevant business rules/docs
    |         from vector store
    |
    v
[3] Assemble prompt:
    - System instructions (existing)
    - Retrieved schema context (from 2a)
    - Retrieved documentation context (from 2c)
    - Retrieved few-shot examples (from 2b)
    - User question
    |
    v
[4] propose_sql() --> validate_sql() --> run_select()
    |
    v
[5] On success: candidate for golden query library
    On failure: propose_sql_repair() with same RAG context
    |
    v
[6] record_query() + record RAG retrieval metadata for analytics
```

### Technology Choices

| Component | Recommendation | Rationale |
|-----------|---------------|-----------|
| **Vector Store** | **ChromaDB** (file-based) | Zero infrastructure, persistent to `./data/`, Python-native, MIT licensed. Upgrade to pgvector later if needed. |
| **Embedding Model** | **text-embedding-3-small** (OpenAI) | Already using OpenAI; 1536-dim; good quality/cost ratio; ~$0.00002 per 1K tokens |
| **Integration Approach** | **Vanna.ai as library** OR **custom RAG module** | Vanna provides the retrieval logic out of the box. Alternatively, build a thin custom module using `chromadb` + `openai` directly for more control. |
| **Golden Query Storage** | **ChromaDB collection** + **SQLite extension** | Extend existing `query_metrics.db` with verified flag; embed verified queries into ChromaDB |
| **Schema Embedding** | **LLM-summarized descriptions** | Generate plain-English table/column descriptions from DDL, embed those |

### Custom Module vs. Vanna.ai

**Option A: Vanna.ai as library**
- Pros: Battle-tested retrieval, multiple vector store backends, active community, handles prompt assembly
- Cons: Another dependency, less control over prompt format, may conflict with existing prompt engineering
- Effort: ~2-3 days to integrate

**Option B: Custom RAG module**
- Pros: Full control, minimal dependencies (just `chromadb` + `openai`), fits existing architecture perfectly
- Cons: More code to write and maintain
- Effort: ~4-5 days to build

**Recommendation**: Start with Option B (custom module) because the SSA Data Assistant already has sophisticated prompt engineering in `ai_sql.py` and schema routing in `catalog.py`. A custom module preserves this investment while adding RAG retrieval as an enhancement layer. If the app were starting from scratch, Vanna would be the faster path.

---

## 8. Implementation Roadmap

### Phase 1: Golden Query Library (Highest Impact, Lowest Risk)

**Duration**: 1-2 weeks

1. Add `verified` boolean and `embedding` blob columns to `query_metrics` SQLite schema.
2. Install `chromadb` and create a persistent collection at `./data/rag_store/`.
3. Build `app/rag.py` module with:
   - `embed_text(text: str) -> list[float]` using OpenAI embeddings
   - `add_golden_query(question: str, sql: str)` -- embed and store
   - `get_similar_queries(question: str, k: int = 3) -> list[tuple[str, str]]` -- retrieve
4. Create admin endpoint `POST /admin/verify-query` to mark queries as golden.
5. Modify `propose_sql()` in `ai_sql.py` to call `get_similar_queries()` and include results as few-shot examples.
6. Seed with 30-50 manually verified queries covering common patterns.

### Phase 2: Documentation RAG

**Duration**: 1 week

1. Convert existing config files to embeddable text chunks:
   - `column_semantics.csv` -> one chunk per row: "TableName.ColumnName: semantic_type, preferred_filter"
   - `join_map.json` -> one chunk per intent: "For [intent], join [tables] on [conditions]"
   - Business rules from `disambiguation.json` -> one chunk per rule
2. Embed and store in a `documentation` collection in ChromaDB.
3. Add `get_relevant_documentation(question: str, k: int = 3)` to `app/rag.py`.
4. Include retrieved documentation in the prompt.

### Phase 3: Schema RAG

**Duration**: 1-2 weeks

1. Generate LLM summaries for each table in the catalog (one-time batch job).
2. Embed table summaries and column descriptions.
3. Store in a `schema` collection in ChromaDB.
4. Replace or augment `suggest_schema_snippet()` with vector-based schema retrieval.
5. Maintain the existing synonym matching as a fallback/boost signal (hybrid approach).

### Phase 4: Evaluation and Tuning

**Duration**: Ongoing

1. Build a test suite of 100+ (question, expected_SQL) pairs from golden queries.
2. Measure execution accuracy before and after each RAG phase.
3. Tune retrieval parameters: k values, similarity thresholds, prompt ordering.
4. Monitor token costs and latency impact.
5. A/B test RAG-enhanced vs. current pipeline on live traffic.

---

## Key Takeaways

1. **Few-shot example retrieval via embeddings is the single highest-impact upgrade.** Dynamic selection of 3-5 relevant examples improves accuracy by 4-12% over static examples.

2. **Golden query libraries compound over time.** Start logging verified queries now. Even 50 golden queries significantly improve generation quality.

3. **ChromaDB is the right vector store for this app.** Zero infrastructure overhead, file-based persistence in the existing `data/` directory, and easy to upgrade to pgvector later.

4. **Schema summarization is critical.** Embedding raw DDL performs poorly. LLM-generated plain-English descriptions of tables and columns dramatically improve schema retrieval.

5. **Hybrid retrieval (vector + keyword) beats pure vector.** Keep the existing synonym matching and disambiguation logic as a complement to vector search, not a replacement.

6. **The academic-to-production gap is real.** Expect 85%+ accuracy on benchmarks but plan for 60-70% initially on real enterprise queries. RAG narrows this gap but domain-specific tuning is essential.

7. **Build incrementally.** Phase 1 (golden queries) delivers the most value with the least risk. Each subsequent phase adds value on top.

---

## Sources

### Few-Shot Example Retrieval
- [Natural Language to SQL Architecture (Microsoft)](https://techcommunity.microsoft.com/blog/azurearchitectureblog/nl-to-sql-architecture-alternatives/4136387)
- [Exploring RAG-based Approaches for Text-to-SQL (Nilenso)](https://blog.nilenso.com/blog/2025/05/15/exploring-rag-based-approach-for-text-to-sql/)
- [DAIL-SQL: Few-shot NL2SQL on GPT-4 (GitHub)](https://github.com/BeachWang/DAIL-SQL)
- [OpenSearch-SQL: Dynamic Few-shot and Consistency Alignment](https://arxiv.org/html/2502.14913v1)

### Query History and Golden Queries
- [Golden Dataset Curation for Text2SQL (Medium)](https://medium.com/towards-generative-ai/golden-dataset-curation-for-text2sql-138f2e77847e)
- [Getting Started with DataHerald NL-to-SQL API (Medium)](https://medium.com/dataherald/fine-tune-and-deploy-your-own-gpt-4-nl-to-sql-llm-b31f3796d623)
- [DataHerald Golden SQLs Documentation](https://dataherald.readthedocs.io/en/latest/api.golden_sql.html)

### Schema RAG
- [Semantic-RAG for Text-to-SQL (Medium)](https://medium.com/@lbirjega/semantic-rag-for-text-to-sql-ed57fcdb0a45)
- [Schema Retrieval with Embeddings and Vector Stores (MDPI)](https://www.mdpi.com/2076-3417/16/2/586)
- [AWS Text-to-SQL with RAG (Amazon Bedrock)](https://aws.amazon.com/blogs/machine-learning/build-your-gen-ai-based-text-to-sql-application-using-rag-powered-by-amazon-bedrock-claude-3-sonnet-and-amazon-titan-for-embedding/)

### Tools and Frameworks
- [Vanna.ai GitHub Repository](https://github.com/vanna-ai/vanna)
- [Vanna.ai DeepWiki Architecture](https://deepwiki.com/vanna-ai/vanna)
- [Wren AI GitHub Repository](https://github.com/Canner/WrenAI)
- [DataHerald GitHub Repository](https://github.com/Dataherald/dataherald)
- [LlamaIndex Text-to-SQL Guide](https://www.llamaindex.ai/blog/combining-text-to-sql-with-semantic-search-for-retrieval-augmented-generation-c60af30ec3b)
- [LangChain SQL Agent with Domain Knowledge](https://blog.langchain.com/incorporating-domain-specific-knowledge-in-sql-llm-solutions/)
- [SQLCoder by Defog (GitHub)](https://github.com/defog-ai/sqlcoder)

### Evaluation
- [Text-to-SQL Benchmarks and State-of-the-Art (DataHerald)](https://medium.com/dataherald/text-to-sql-benchmarks-and-the-current-state-of-the-art-63dd3b3943fe)
- [RAG for NL2SQL: Beyond Basics for Enterprise Accuracy (Autonmis)](https://autonmis.com/learning/rag-for-nl2sql)
- [Prompt Tuning for NL-to-SQL with Embedding Fine-Tuning and RAG](https://arxiv.org/html/2511.08245v1)
- [NL2SQL System Design Guide 2025 (Medium)](https://medium.com/@adityamahakali/nl2sql-system-design-guide-2025-c517a00ae34d)

### Vector Store Comparison
- [Vector Database Comparison 2026 (4xxi)](https://4xxi.com/articles/vector-database-comparison/)
- [pgvector vs ChromaDB (Elest.io)](https://blog.elest.io/pgvector-vs-chromadb-when-to-extend-postgresql-and-when-to-go-dedicated/)
- [Best Vector Databases in 2025 (Firecrawl)](https://www.firecrawl.dev/blog/best-vector-databases)

### FastAPI + RAG Integration
- [Building Production-Ready RAG in FastAPI (DEV Community)](https://dev.to/hamluk/building-production-ready-rag-in-fastapi-with-vector-databases-39gf)
- [FastAPI-Powered RAG Backend with pgvector (Medium)](https://medium.com/@fredyriveraacevedo13/building-a-fastapi-powered-rag-backend-with-postgresql-pgvector-c239f032508a)
- [RAG System with Async FastAPI, Qdrant, and LangChain](https://blog.futuresmart.ai/rag-system-with-async-fastapi-qdrant-langchain-and-openai)
