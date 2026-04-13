# Semantic Layer & Metadata Management Research

> Research conducted April 2026 for upgrading SSA Data Assistant's manually curated CSV/JSON config files to a more automated, maintainable semantic layer.

---

## 1. Semantic Layer Tools

### Cube.js (Open Source - Apache 2.0)
- **Best fit for NL-to-SQL**: Cube provides a dedicated AI API endpoint that translates natural language into Cube API calls (not raw SQL), then compiles those deterministically to SQL. This intermediate step constrains LLM output and reduces hallucinations.
- **Architecture**: Code-first YAML/JS data models define measures, dimensions, joins. The AI API reads Cube's meta endpoint, downloads semantic definitions, stores them as embeddings in a vector DB, and uses them as context for LLM prompts.
- **LangChain integration**: Official LangChain integration for building AI agents on top of the semantic layer.
- **Tradeoff**: Adds an infrastructure dependency (Cube server). Overkill if you only need schema metadata for prompts, not a full BI semantic layer.
- Source: https://cube.dev/use-cases/llm-and-ai-semantic-layer

### dbt Semantic Layer (MetricFlow - Open Source Apache 2.0 since Dec 2025)
- **MetricFlow** is now open source (v0.209.0+), but the full dbt Semantic Layer (API, caching, governance) requires dbt Cloud Team/Enterprise.
- **Accuracy**: dbt Labs reports 83% accuracy on NL queries via semantic layer vs ~40% without. Snowflake reports similar (85% vs 40%).
- **Best for**: Teams already using dbt for transformations. Defines metrics (revenue, churn) as code, which LLMs can reference by name.
- **Tradeoff**: MetricFlow alone is a metrics compiler, not a standalone NL-to-SQL solution. Requires dbt Cloud for the full API layer.
- Source: https://www.getdbt.com/blog/open-source-metricflow-governed-metrics

### Metabase Models (Open Source - AGPL)
- Auto-classifies columns into semantic types (Category, Currency, URL, FK, etc.) during database sync.
- **dbt-metabase** bridge tool propagates dbt model descriptions, column descriptions, and semantic types into Metabase's data model.
- **Best for**: Lightweight BI layer with some semantic classification. Not designed as a programmable semantic layer for LLM consumption.
- Source: https://www.metabase.com/docs/latest/data-modeling/semantic-types

### AtScale (Commercial)
- Enterprise-grade semantic layer with a "universal" abstraction over multiple warehouses.
- Provides an AI-Link feature for LLM integration.
- **Tradeoff**: Expensive, enterprise-focused. Not practical for a single-app NL-to-SQL use case.

### Timbr.ai (Commercial)
- Ontology-based semantic layer that models business concepts as a knowledge graph on top of SQL databases.
- Rich for complex business domains but heavyweight.

### Recommendation for SSA Data Assistant
Cube.js is the strongest open-source option if you want a full semantic layer with native LLM support. However, for a focused NL-to-SQL app, a lighter approach (pgai semantic catalog or custom YAML-based metadata + embeddings) may be more practical. See Section 2.

---

## 2. Auto-Generating Semantic Metadata

### pgai Semantic Catalog (Timescale - Open Source)
- **Most relevant tool for SSA Data Assistant.** pgai is a Python library + PostgreSQL extension that:
  1. Automatically generates natural-language descriptions of tables and columns using LLMs
  2. Stores descriptions in human-readable YAML files (version-controllable, peer-reviewable)
  3. Supports human-in-the-loop review and improvement of generated descriptions
  4. Stores SQL examples and business facts alongside schema metadata
  5. Auto-creates and synchronizes vector embeddings from PostgreSQL data
- **Impact**: Early tests show LLM-generated semantic catalogs improve SQL generation accuracy by up to 27%.
- **Workflow**: `pgai` introspects your PostgreSQL schema -> generates initial descriptions via LLM -> exports to YAML -> human reviews/edits -> YAML becomes the governed source of truth.
- Source: https://github.com/timescale/pgai
- Source: https://www.tigerdata.com/blog/the-database-new-user-llms-need-a-different-database

### Dual-Process Description Generation (Academic - arXiv 2502.20657)
- **Coarse-to-fine**: LLM generates database-level description, then table-level, then column-level.
- **Fine-to-coarse**: Examines actual data values, infers column semantics, propagates understanding upward.
- Combining both processes produces richer, more accurate descriptions than either alone.
- Source: https://arxiv.org/html/2502.20657v1

### PostgreSQL Native Metadata
- `COMMENT ON TABLE/COLUMN` stores descriptions directly in the database catalog.
- `information_schema` and `pg_catalog` provide data types, foreign keys, constraints, nullable flags.
- `pg_stats` provides most common values, null fractions, n_distinct counts per column.
- **Practical approach**: Use `COMMENT ON` for human descriptions, query `pg_stats` for value distributions, combine both in your prompt context.

### LLMShark (Open Source)
- TUI tool that exports PostgreSQL schema as Markdown, optimized for LLM prompts.
- Quick way to bootstrap schema descriptions but not a maintained semantic layer.
- Source: https://github.com/kerem-kaynak/llmshark

### Recommended Upgrade Path for SSA Data Assistant
1. **Phase 1**: Use pgai (or a custom script) to introspect the PostgreSQL schema and auto-generate initial YAML descriptions for all tables and columns.
2. **Phase 2**: Human-review the generated descriptions, adding business context (e.g., "MD" = "Managing Director") that LLMs cannot infer from schema alone.
3. **Phase 3**: Store the reviewed YAML alongside your existing config files. Replace or augment `catalog.py`'s manual introspection with the enriched metadata.
4. **Phase 4**: Use `pg_stats` to auto-populate `allowed_values/` CSVs with the most common values per column, eliminating manual curation.

---

## 3. Keeping Semantic Models Up to Date

### Atlas (Open Source - Apache 2.0)
- **Best-in-class for schema drift detection.** Declarative schema-as-code tool that:
  1. Inspects live PostgreSQL and exports schema to HCL/JSON/SQL
  2. Compares live DB against a version-controlled "desired state"
  3. Detects drift and generates exact SQL to reconcile
  4. Integrates with GitHub Actions, GitLab CI, ArgoCD, Terraform
  5. 50+ safety analyzers for migration linting
- **For SSA Data Assistant**: Run `atlas schema diff` in CI to detect when the PostgreSQL schema changes, then trigger a re-generation of your semantic metadata.
- Source: https://atlasgo.io/monitoring/drift-detection

### Liquibase / Flyway (Open Source)
- Traditional migration-based schema management. Track changes via migration scripts.
- Less relevant for drift detection on a read-only database you don't control, but useful if you do manage the schema.

### pgai Vectorizer Auto-Sync
- pgai's Vectorizer treats embeddings as a declarative feature (like an index). When data changes, embeddings update automatically.
- Useful for keeping your vector index of schema metadata current.

### Recommended Approach for SSA Data Assistant
1. **Scheduled re-introspection**: Add a cron job or startup hook that runs `catalog.py` introspection and compares against the last known schema snapshot (stored as JSON/YAML in version control).
2. **Diff alerting**: If new tables/columns appear or types change, generate a diff report and flag for human review.
3. **CI integration**: Use Atlas in CI to compare the live `Project_Master_Database` schema against your committed semantic metadata. If drift is detected, the pipeline can auto-generate updated descriptions and open a PR.
4. **Hot reload**: Your existing `POST /debug/catalog/reload` endpoint already supports runtime refresh. Extend it to also reload semantic metadata YAML.

---

## 4. Business Glossary / Ontology Management

### Maturity Continuum
1. **Business Glossary**: Terms + definitions (what you have now in `*_aliases.csv`)
2. **Thesaurus**: Adds synonyms, antonyms, related terms
3. **Taxonomy**: Adds hierarchical classes (e.g., "Employee" > "Consultant" > "Senior Consultant")
4. **Ontology**: Full entity-relationship model with formal semantics

### Open Source Data Catalog Tools with Glossary Support

#### OpenMetadata (Open Source - Apache 2.0)
- Full metadata platform with built-in business glossary, tagging, RBAC, lineage tracking.
- Glossary terms can be linked to tables/columns.
- Supports PostgreSQL as a data source with automated metadata ingestion.
- **Tradeoff**: Requires deploying a separate service (Java/Airflow/ES). Heavyweight for a single-app use case.
- Source: https://open-metadata.org

#### DataHub (Open Source - Apache 2.0)
- LinkedIn's metadata platform with business glossary, automated governance workflows, lineage.
- v1.4.0 added "Context Documents" for bringing organizational knowledge into the catalog.
- **Tradeoff**: Even heavier infrastructure (GMS, Kafka, Elasticsearch, MySQL/Postgres).
- Source: https://datahubproject.io

#### Lightweight Alternatives
- **YAML/JSON glossary files in version control**: What SSA Data Assistant already does. Simple, reviewable, no infrastructure.
- **SQLite glossary table**: Store terms, synonyms, categories in a local SQLite DB alongside `query_metrics.db`. Queryable, no external dependencies.

### Best Practices for Synonym Management
1. **Canonical form + aliases**: Your current `*_aliases.csv` format (canonical, alias) is a solid pattern.
2. **Hierarchical grouping**: Add a `category` column (e.g., "title", "tool", "client") for disambiguation.
3. **Confidence scores**: Add a `confidence` or `weight` column so fuzzy matches can be ranked.
4. **Bidirectional linking**: Ensure synonyms are searchable in both directions.
5. **Review workflow**: Changes to glossary files should go through PR review, not direct edits.
6. **Embedding-enhanced matching**: Embed glossary terms and use cosine similarity for fuzzy synonym resolution (see Section 5).

### Recommended Approach for SSA Data Assistant
- **Short term**: Keep the CSV-based approach but add `category` and `confidence` columns. Move from flat files to a single `business_glossary.yaml` with structured entries:
  ```yaml
  terms:
    - canonical: "Managing Director"
      aliases: ["MD", "Mng Dir", "managing dir"]
      category: "title"
      description: "Senior leadership role"
      tables: ["Employees", "ProjectAssignments"]
      columns: ["Employees.Title", "ProjectAssignments.Role"]
  ```
- **Medium term**: Add embedding-based fuzzy matching so novel phrasings ("head honcho", "top exec") can resolve to canonical terms without manual alias entry.
- **Long term**: If the number of datasets and business terms grows significantly, evaluate OpenMetadata as a governed glossary with API access.

---

## 5. Embedding-Based Column/Table Descriptions

### Pinterest's Approach (March 2026)
- **Unified Context-Intent Embeddings**: Pinterest built a production text-to-SQL system using:
  1. Pre-computed embeddings for every table and column description
  2. Vector database for fast similarity search
  3. Agent orchestration layer with MCP integration for tool-based table search
  4. Query description index mapping natural language patterns to known SQL templates
- Source: https://medium.com/pinterest-engineering/unified-context-intent-embeddings-for-scalable-text-to-sql-793635e60aac

### LitE-SQL Framework (EACL 2026)
- **Vector-based schema linking**: Pre-computes schema embeddings, encodes only the question at query time, retrieves relevant columns via cosine similarity.
- **Hard-negative contrastive training**: Trains the embedding model to distinguish semantically similar but functionally irrelevant columns (e.g., "employee_name" vs "project_name").
- **Results**: 72.10% on BIRD, 88.45% on Spider with 2-30x fewer parameters than LLM-based methods.
- **Key insight**: Schema linking (finding relevant tables/columns) is often the bottleneck, not SQL generation itself.
- Source: https://arxiv.org/abs/2510.09014

### LlamaIndex SQLTableRetriever (Open Source)
- **Most practical implementation for Python/FastAPI apps.**
- Creates a vector index over table schema objects (table name, column names, descriptions).
- At query time, retrieves the most relevant tables/columns by embedding similarity.
- Supports three retrieval modes:
  1. **Table-level**: Embed full table descriptions, retrieve top-k tables
  2. **Column-level**: Embed individual columns, retrieve relevant columns across all tables
  3. **Value-level**: Embed distinct values within columns for precise filtering
- PGVector integration available for storing embeddings in PostgreSQL itself.
- Source: https://developers.llamaindex.ai/python/examples/index_structs/struct_indices/sqlindexdemo/

### AWS Bedrock RAG Pattern
- Amazon's reference architecture for text-to-SQL with RAG:
  1. Store table metadata (names, descriptions, column synonyms, sample queries) in a vector DB
  2. On user query, similarity-search to find relevant tables
  3. Include retrieved metadata in the LLM prompt alongside the question
  4. LLM generates SQL using only the relevant schema context
- Source: https://aws.amazon.com/blogs/machine-learning/build-your-gen-ai-based-text-to-sql-application-using-rag-powered-by-amazon-bedrock-claude-3-sonnet-and-amazon-titan-for-embedding/

### Recommended Approach for SSA Data Assistant

#### Phase 1: Bootstrap (Low effort, high impact)
1. Generate rich text descriptions for each table and column (using pgai or a custom LLM script).
2. Combine with your existing `column_semantics.csv` and `join_map.json` data.
3. Create a consolidated metadata document per table:
   ```
   Table: Employees
   Description: Contains all SSA consultant records including...
   Columns:
     - EmployeeID (int, PK): Unique identifier for each consultant
     - Title (varchar): Job title, e.g. "Managing Director", "Senior Consultant"
       Common values: Managing Director, Senior Consultant, Consultant, Analyst
     - ...
   Relationships:
     - Employees.EmployeeID -> ProjectAssignments.EmployeeID
   ```

#### Phase 2: Vector Index (Medium effort, significant accuracy improvement)
1. Use `text-embedding-3-small` (OpenAI, already in your stack) to embed each table/column description.
2. Store embeddings in a simple FAISS index or pgvector (if you want to keep everything in PostgreSQL).
3. At query time in `suggest_schema_snippet()`:
   - Embed the user's question
   - Retrieve top-k most relevant tables/columns by cosine similarity
   - Use retrieved context instead of (or in addition to) the current keyword/synonym matching
4. This replaces the manual scoring logic with semantic understanding.

#### Phase 3: Continuous Improvement (Ongoing)
1. Log which tables/columns were retrieved vs. which were actually needed (from successful queries).
2. Use this feedback to fine-tune descriptions or re-weight embeddings.
3. Add few-shot examples as embeddings alongside schema metadata (query + correct SQL pairs).

---

## Summary Comparison Table

| Approach | Effort | Impact | Open Source | Best For |
|----------|--------|--------|-------------|----------|
| pgai semantic catalog | Low | +27% accuracy | Yes (Apache 2.0) | Auto-generating descriptions |
| Cube.js AI API | Medium | High (constrained output) | Yes (MIT) | Full semantic layer with LLM |
| LlamaIndex SQLTableRetriever | Low-Medium | High (semantic retrieval) | Yes (MIT) | Python apps needing schema retrieval |
| Atlas drift detection | Low | Prevents staleness | Yes (Apache 2.0) | CI/CD schema monitoring |
| OpenMetadata glossary | High | High (governed catalog) | Yes (Apache 2.0) | Enterprise-scale governance |
| dbt Semantic Layer | Medium | +83% accuracy | Partial (MetricFlow only) | dbt-native teams |
| YAML glossary + embeddings | Low | Medium-High | N/A (custom) | Small teams, incremental upgrade |

---

## Recommended Upgrade Roadmap for SSA Data Assistant

### Immediate (1-2 weeks)
1. **Auto-generate column descriptions**: Write a Python script (or use pgai) to introspect `Project_Master_Database`, generate LLM-powered descriptions, and export to YAML.
2. **Enrich existing configs**: Add the generated descriptions to `column_semantics.csv` or a new `schema_descriptions.yaml`.
3. **Populate allowed values from pg_stats**: Replace manual `allowed_values/*.csv` curation with a script that queries `pg_stats.most_common_vals`.

### Short-term (2-4 weeks)
4. **Add embedding-based schema retrieval**: Use OpenAI embeddings + FAISS to build a vector index of table/column descriptions. Modify `suggest_schema_snippet()` to use semantic search.
5. **Structured business glossary**: Migrate `*_aliases.csv` files to a single `business_glossary.yaml` with categories, descriptions, and table/column links.

### Medium-term (1-2 months)
6. **Schema drift detection**: Add Atlas or a custom diff script to CI that compares live schema against committed metadata, flags changes.
7. **Feedback loop**: Log retrieval accuracy (which schema was sent to LLM vs. which tables appeared in successful SQL), use it to improve descriptions.
8. **Embedding-based synonym resolution**: Embed glossary terms for fuzzy matching of novel user phrasings.

### Long-term (3+ months)
9. **Evaluate Cube.js**: If the app grows to serve multiple BI consumers, consider Cube as a shared semantic layer.
10. **Evaluate OpenMetadata**: If the number of datasets and business terms grows beyond what YAML files can manage.
