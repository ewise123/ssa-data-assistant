"""
RAG module: embedding-based retrieval for schema linking, golden queries,
and documentation. Uses ChromaDB for vector storage and OpenAI embeddings.

Collections:
  - schema:          table/column descriptions for schema linking
  - golden_queries:  verified (question, SQL) pairs for few-shot retrieval
  - documentation:   business rules, join hints, disambiguation rules
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import chromadb
import openai
import yaml

_DATA_DIR = Path("data/chromadb")
_SCHEMA_DESCRIPTIONS_PATH = Path("app/config/schema_descriptions.yaml")
_EMBEDDING_MODEL = "text-embedding-3-small"

# Batch size for OpenAI embedding API calls
_EMBED_BATCH_SIZE = 64


# ------------------------------------------------------------------
# Embedding helper
# ------------------------------------------------------------------

def _get_openai_client() -> openai.OpenAI:
    return openai.OpenAI()


def embed_texts(texts: list[str], model: str = _EMBEDDING_MODEL) -> list[list[float]]:
    """Embed a list of texts using OpenAI's embedding API."""
    if not texts:
        return []
    client = _get_openai_client()
    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), _EMBED_BATCH_SIZE):
        batch = texts[i : i + _EMBED_BATCH_SIZE]
        response = client.embeddings.create(model=model, input=batch)
        all_embeddings.extend([item.embedding for item in response.data])
    return all_embeddings


def embed_text(text: str, model: str = _EMBEDDING_MODEL) -> list[float]:
    """Embed a single text string."""
    return embed_texts([text], model=model)[0]


# ------------------------------------------------------------------
# ChromaDB client
# ------------------------------------------------------------------

def _get_chroma_client() -> chromadb.ClientAPI:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(_DATA_DIR))


def _stable_id(text: str) -> str:
    """Generate a deterministic ID from text content."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ------------------------------------------------------------------
# Schema collection: index table/column descriptions for retrieval
# ------------------------------------------------------------------

class SchemaRetriever:
    """Embeds and retrieves schema elements (tables, columns) by semantic similarity."""

    COLLECTION_NAME = "schema"

    def __init__(self) -> None:
        self._client = _get_chroma_client()
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    @property
    def count(self) -> int:
        return self._collection.count()

    def index_from_yaml(self, path: Path = _SCHEMA_DESCRIPTIONS_PATH) -> int:
        """Load schema_descriptions.yaml and index all tables and columns.

        Returns the number of documents indexed.
        """
        if not path.exists():
            raise FileNotFoundError(
                f"Schema descriptions not found at {path}. "
                "Run 'python -m app.schema_enrichment' first."
            )

        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        schema_name = data.get("schema", "")
        tables = data.get("tables", {})

        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []
        ids: list[str] = []

        for table_name, table_data in tables.items():
            # Table-level document
            table_desc = table_data.get("description", "")
            col_names = list(table_data.get("columns", {}).keys())
            relationships = table_data.get("relationships", [])

            table_text = (
                f"Table: {table_name}. "
                f"{table_desc} "
                f"Columns: {', '.join(col_names)}."
            )
            if relationships:
                table_text += f" Relationships: {'; '.join(relationships)}."

            documents.append(table_text)
            metadatas.append({
                "type": "table",
                "table": table_name,
                "schema": schema_name,
            })
            ids.append(_stable_id(f"table:{schema_name}.{table_name}"))

            # Column-level documents
            for col_name, col_info in table_data.get("columns", {}).items():
                col_desc = col_info.get("description", "")
                col_type = col_info.get("type", "")
                semantic_type = col_info.get("semantic_type", "")
                sample_vals = col_info.get("sample_values", [])

                col_text = (
                    f"Column: {table_name}.{col_name} ({col_type}). "
                    f"{col_desc}"
                )
                if semantic_type:
                    col_text += f" Semantic type: {semantic_type}."
                if sample_vals:
                    preview = ", ".join(str(v) for v in sample_vals[:5])
                    col_text += f" Example values: {preview}."

                documents.append(col_text)
                metadatas.append({
                    "type": "column",
                    "table": table_name,
                    "column": col_name,
                    "schema": schema_name,
                })
                ids.append(_stable_id(f"column:{schema_name}.{table_name}.{col_name}"))

        if not documents:
            return 0

        # Embed all at once and upsert
        embeddings = embed_texts(documents)
        self._collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings,
        )
        return len(documents)

    def retrieve_tables(
        self,
        question: str,
        n_tables: int = 5,
        n_columns: int = 10,
    ) -> SchemaRetrievalResult:
        """Retrieve the most relevant tables and columns for a question.

        Returns a SchemaRetrievalResult with scored tables and columns.
        """
        q_embedding = embed_text(question)

        # Retrieve table-level matches
        table_results = self._collection.query(
            query_embeddings=[q_embedding],
            where={"type": "table"},
            n_results=min(n_tables, self._collection.count()),
            include=["metadatas", "distances", "documents"],
        )

        # Retrieve column-level matches
        column_results = self._collection.query(
            query_embeddings=[q_embedding],
            where={"type": "column"},
            n_results=min(n_columns, self._collection.count()),
            include=["metadatas", "distances", "documents"],
        )

        tables: list[ScoredTable] = []
        if table_results and table_results["metadatas"]:
            for meta, dist in zip(
                table_results["metadatas"][0],
                table_results["distances"][0],
            ):
                # ChromaDB cosine distance = 1 - similarity
                similarity = 1.0 - dist
                tables.append(ScoredTable(
                    name=meta["table"],
                    vector_score=similarity,
                ))

        columns: list[ScoredColumn] = []
        if column_results and column_results["metadatas"]:
            for meta, dist in zip(
                column_results["metadatas"][0],
                column_results["distances"][0],
            ):
                similarity = 1.0 - dist
                columns.append(ScoredColumn(
                    table=meta["table"],
                    column=meta["column"],
                    vector_score=similarity,
                ))

        return SchemaRetrievalResult(tables=tables, columns=columns)


# ------------------------------------------------------------------
# Result types
# ------------------------------------------------------------------

class ScoredTable:
    __slots__ = ("name", "vector_score", "keyword_score", "final_score")

    def __init__(
        self,
        name: str,
        vector_score: float = 0.0,
        keyword_score: float = 0.0,
    ) -> None:
        self.name = name
        self.vector_score = vector_score
        self.keyword_score = keyword_score
        self.final_score = 0.0

    def compute_final_score(
        self,
        vector_weight: float = 0.6,
        keyword_weight: float = 0.4,
    ) -> float:
        self.final_score = (
            vector_weight * self.vector_score
            + keyword_weight * self.keyword_score
        )
        return self.final_score


class ScoredColumn:
    __slots__ = ("table", "column", "vector_score")

    def __init__(self, table: str, column: str, vector_score: float = 0.0) -> None:
        self.table = table
        self.column = column
        self.vector_score = vector_score


class SchemaRetrievalResult:
    __slots__ = ("tables", "columns")

    def __init__(
        self,
        tables: list[ScoredTable] | None = None,
        columns: list[ScoredColumn] | None = None,
    ) -> None:
        self.tables = tables or []
        self.columns = columns or []

    def table_names(self) -> list[str]:
        return [t.name for t in self.tables]

    def columns_for_table(self, table_name: str) -> list[str]:
        return [c.column for c in self.columns if c.table == table_name]


# ------------------------------------------------------------------
# Golden query collection: verified (question, SQL) pairs
# ------------------------------------------------------------------

class GoldenQueryStore:
    """Stores and retrieves verified (question, SQL) pairs for few-shot examples."""

    COLLECTION_NAME = "golden_queries"

    def __init__(self) -> None:
        self._client = _get_chroma_client()
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    @property
    def count(self) -> int:
        return self._collection.count()

    def add(self, question: str, sql: str, tables_used: list[str] | None = None) -> str:
        """Add a verified query pair. Returns the document ID."""
        doc_id = _stable_id(f"golden:{question}")
        embedding = embed_text(question)
        metadata: dict[str, Any] = {
            "sql": sql,
        }
        if tables_used:
            metadata["tables_used"] = ",".join(tables_used)

        self._collection.upsert(
            ids=[doc_id],
            documents=[question],
            metadatas=[metadata],
            embeddings=[embedding],
        )
        return doc_id

    def retrieve(
        self,
        question: str,
        k: int = 3,
        min_similarity: float = 0.3,
    ) -> list[GoldenQuery]:
        """Retrieve the k most similar golden queries."""
        if self._collection.count() == 0:
            return []

        q_embedding = embed_text(question)
        results = self._collection.query(
            query_embeddings=[q_embedding],
            n_results=min(k, self._collection.count()),
            include=["metadatas", "distances", "documents"],
        )

        queries: list[GoldenQuery] = []
        if results and results["metadatas"]:
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                similarity = 1.0 - dist
                if similarity < min_similarity:
                    continue
                queries.append(GoldenQuery(
                    question=doc,
                    sql=meta.get("sql", ""),
                    similarity=similarity,
                ))
        return queries


class GoldenQuery:
    __slots__ = ("question", "sql", "similarity")

    def __init__(self, question: str, sql: str, similarity: float) -> None:
        self.question = question
        self.sql = sql
        self.similarity = similarity


# ------------------------------------------------------------------
# Documentation collection: business rules, join hints, etc.
# ------------------------------------------------------------------

class DocumentationStore:
    """Stores and retrieves business documentation chunks."""

    COLLECTION_NAME = "documentation"

    def __init__(self) -> None:
        self._client = _get_chroma_client()
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    @property
    def count(self) -> int:
        return self._collection.count()

    def add(self, text: str, source: str, doc_type: str = "rule") -> str:
        """Add a documentation chunk."""
        doc_id = _stable_id(f"doc:{source}:{text[:80]}")
        embedding = embed_text(text)
        self._collection.upsert(
            ids=[doc_id],
            documents=[text],
            metadatas=[{"source": source, "type": doc_type}],
            embeddings=[embedding],
        )
        return doc_id

    def retrieve(self, question: str, k: int = 3) -> list[DocChunk]:
        """Retrieve the k most relevant documentation chunks."""
        if self._collection.count() == 0:
            return []

        q_embedding = embed_text(question)
        results = self._collection.query(
            query_embeddings=[q_embedding],
            n_results=min(k, self._collection.count()),
            include=["metadatas", "distances", "documents"],
        )

        chunks: list[DocChunk] = []
        if results and results["metadatas"]:
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                chunks.append(DocChunk(
                    text=doc,
                    source=meta.get("source", ""),
                    similarity=1.0 - dist,
                ))
        return chunks


class DocChunk:
    __slots__ = ("text", "source", "similarity")

    def __init__(self, text: str, source: str, similarity: float) -> None:
        self.text = text
        self.source = source
        self.similarity = similarity


# ------------------------------------------------------------------
# Hybrid scoring: merge vector scores with keyword scores
# ------------------------------------------------------------------

def merge_scores(
    vector_tables: list[ScoredTable],
    keyword_scores: dict[str, float],
    vector_weight: float = 0.6,
    keyword_weight: float = 0.4,
    top_k: int = 5,
) -> list[ScoredTable]:
    """Merge vector similarity scores with keyword-based scores.

    Normalizes both score sets to [0, 1] before combining.
    Returns the top-k tables sorted by final score.
    """
    # Normalize keyword scores to [0, 1]
    max_keyword = max(keyword_scores.values()) if keyword_scores else 1.0
    if max_keyword == 0:
        max_keyword = 1.0

    # Build a combined table list
    all_tables: dict[str, ScoredTable] = {}

    for st in vector_tables:
        all_tables[st.name] = ScoredTable(
            name=st.name,
            vector_score=st.vector_score,
            keyword_score=keyword_scores.get(st.name, 0.0) / max_keyword,
        )

    # Add tables that only appear in keyword scores
    for table_name, score in keyword_scores.items():
        if table_name not in all_tables:
            all_tables[table_name] = ScoredTable(
                name=table_name,
                vector_score=0.0,
                keyword_score=score / max_keyword,
            )

    # Compute final scores
    for st in all_tables.values():
        st.compute_final_score(vector_weight, keyword_weight)

    ranked = sorted(all_tables.values(), key=lambda t: t.final_score, reverse=True)
    return ranked[:top_k]


# ------------------------------------------------------------------
# Index config files into the documentation collection
# ------------------------------------------------------------------

def index_config_as_documentation(
    doc_store: DocumentationStore,
    config: dict[str, Any],
) -> int:
    """Convert config files (join_map, disambiguation, semantics, aliases)
    into embeddable text chunks and index them into the documentation store.

    Returns the number of chunks indexed.
    """
    chunks: list[tuple[str, str, str]] = []  # (text, source, doc_type)

    # --- Join map: one chunk per intent path ---
    join_map = config.get("join_map", {})
    for path in join_map.get("paths", []):
        intent = path.get("intent", "")
        desc = path.get("description", "")
        tables = path.get("tables", [])
        joins = path.get("joins", [])
        defaults = path.get("result_defaults", [])
        filters = path.get("canonical_filters", [])

        lines = [f"Query pattern: {intent}. {desc}"]
        lines.append(f"Tables involved: {', '.join(tables)}.")
        if joins:
            join_strs = []
            for pair in joins:
                join_strs.append(f"{pair[0]} = {pair[1]}")
            lines.append(f"Join path: {'; '.join(join_strs)}.")
        if filters:
            filter_strs = []
            for f in filters:
                filter_strs.append(
                    f"{f.get('table')}.{f.get('column')} using {f.get('preferred_filter')} with pattern {f.get('pattern')}"
                )
            lines.append(f"Filters: {'; '.join(filter_strs)}.")
        if defaults:
            lines.append(f"Recommended SELECT columns: {', '.join(defaults)}.")

        chunks.append((" ".join(lines), f"join_map:{intent}", "join_path"))

    # --- Disambiguation rules: one chunk per rule ---
    disambig = config.get("disambiguation", {})
    for rule in disambig.get("rules", []):
        keywords = rule.get("if_contains", [])
        dataset = rule.get("dataset", "")
        prefer = rule.get("prefer_tables", [])
        text = (
            f"When the question mentions {', '.join(repr(k) for k in keywords)}, "
            f"this is about the {dataset} domain. "
            f"Use these tables: {', '.join(prefer)}."
        )
        chunks.append((text, f"disambiguation:{dataset}:{keywords[0] if keywords else ''}", "rule"))

    # --- Column semantics: group by table for denser chunks ---
    semantics = config.get("semantics", {})
    for table_name, columns in semantics.items():
        col_descriptions = []
        for col_name, meta in columns.items():
            parts = [f"{table_name}.{col_name}"]
            if meta.get("semantic_type"):
                parts.append(f"type={meta['semantic_type']}")
            if meta.get("preferred_filter"):
                parts.append(f"filter with {meta['preferred_filter']}")
            if meta.get("notes"):
                parts.append(meta["notes"])
            col_descriptions.append(", ".join(parts))
        text = f"Column details for {table_name}: " + "; ".join(col_descriptions) + "."
        chunks.append((text, f"semantics:{table_name}", "column_info"))

    # --- Aliases: one chunk per category ---
    aliases = config.get("aliases", {})
    for category, mapping in aliases.items():
        alias_strs = []
        for canonical, alias_list in list(mapping.items())[:20]:  # cap to avoid huge chunks
            alias_strs.append(f"{canonical} (also known as: {', '.join(alias_list)})")
        text = f"Aliases for {category}: {'; '.join(alias_strs)}."
        chunks.append((text, f"aliases:{category}", "alias"))

    if not chunks:
        return 0

    for text, source, doc_type in chunks:
        doc_store.add(text, source=source, doc_type=doc_type)

    return len(chunks)
