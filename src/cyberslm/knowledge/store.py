from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
from array import array
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cyberslm.knowledge.chunking import CHUNKING_VERSION, chunk_text

STOP_WORDS = {
    "about",
    "after",
    "also",
    "and",
    "are",
    "can",
    "does",
    "for",
    "from",
    "have",
    "how",
    "into",
    "that",
    "the",
    "their",
    "then",
    "this",
    "using",
    "what",
    "when",
    "where",
    "which",
    "with",
    "would",
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class KnowledgeStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS knowledge_documents (
                    id TEXT PRIMARY KEY,
                    source_key TEXT NOT NULL,
                    source_version TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS knowledge_sources (
                    source_key TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    url TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    document_count INTEGER NOT NULL,
                    notice TEXT NOT NULL,
                    synced_at TEXT NOT NULL
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
                    document_id UNINDEXED,
                    title,
                    content,
                    tokenize='porter unicode61'
                );

                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    chunking_version INTEGER NOT NULL,
                    UNIQUE(document_id, position)
                );

                CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_document
                    ON knowledge_chunks(document_id);

                CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunk_fts USING fts5(
                    chunk_id UNINDEXED,
                    document_id UNINDEXED,
                    title,
                    content,
                    tokenize='porter unicode61'
                );

                CREATE TABLE IF NOT EXISTS knowledge_embeddings (
                    chunk_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    dimension INTEGER NOT NULL,
                    vector BLOB NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(chunk_id, model)
                );

                CREATE INDEX IF NOT EXISTS idx_knowledge_embeddings_model
                    ON knowledge_embeddings(model);
                """
            )
            chunk_count = connection.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()[0]
            document_count = connection.execute(
                "SELECT COUNT(*) FROM knowledge_documents"
            ).fetchone()[0]
            if document_count and not chunk_count:
                for document in connection.execute("SELECT * FROM knowledge_documents"):
                    self._insert_chunks(connection, dict(document))

    @staticmethod
    def _insert_chunks(connection: sqlite3.Connection, document: dict[str, Any]) -> None:
        for position, content in enumerate(chunk_text(document["content"])):
            chunk_id = f"{document['id']}#{position}"
            connection.execute(
                """INSERT INTO knowledge_chunks
                   (id, document_id, position, content, chunking_version)
                   VALUES (?, ?, ?, ?, ?)""",
                (chunk_id, document["id"], position, content, CHUNKING_VERSION),
            )
            connection.execute(
                """INSERT INTO knowledge_chunk_fts
                   (chunk_id, document_id, title, content) VALUES (?, ?, ?, ?)""",
                (chunk_id, document["id"], document["title"], content),
            )

    def replace_source(
        self,
        *,
        source_key: str,
        source_name: str,
        source_version: str,
        source_url: str,
        source_sha256: str,
        notice: str,
        documents: Iterable[dict[str, Any]],
    ) -> int:
        prepared = list(documents)
        timestamp = utc_now()
        with self._lock, self._connect() as connection:
            existing_ids = [
                row["id"]
                for row in connection.execute(
                    "SELECT id FROM knowledge_documents WHERE source_key = ?", (source_key,)
                ).fetchall()
            ]
            if existing_ids:
                placeholders = ",".join("?" for _ in existing_ids)
                chunk_ids = [
                    row["id"]
                    for row in connection.execute(
                        f"SELECT id FROM knowledge_chunks WHERE document_id IN ({placeholders})",
                        existing_ids,
                    ).fetchall()
                ]
                if chunk_ids:
                    chunk_placeholders = ",".join("?" for _ in chunk_ids)
                    connection.execute(
                        f"DELETE FROM knowledge_embeddings "
                        f"WHERE chunk_id IN ({chunk_placeholders})",
                        chunk_ids,
                    )
                    connection.execute(
                        f"DELETE FROM knowledge_chunk_fts "
                        f"WHERE chunk_id IN ({chunk_placeholders})",
                        chunk_ids,
                    )
                connection.execute(
                    f"DELETE FROM knowledge_chunks WHERE document_id IN ({placeholders})",
                    existing_ids,
                )
                connection.execute(
                    f"DELETE FROM knowledge_fts WHERE document_id IN ({placeholders})",
                    existing_ids,
                )
            connection.execute(
                "DELETE FROM knowledge_documents WHERE source_key = ?", (source_key,)
            )

            for document in prepared:
                connection.execute(
                    """INSERT INTO knowledge_documents
                       (id, source_key, source_version, external_id, title, url,
                        content, metadata, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        document["id"],
                        source_key,
                        source_version,
                        document["external_id"],
                        document["title"],
                        document["url"],
                        document["content"],
                        json.dumps(document.get("metadata", {}), sort_keys=True),
                        timestamp,
                    ),
                )
                connection.execute(
                    "INSERT INTO knowledge_fts (document_id, title, content) VALUES (?, ?, ?)",
                    (document["id"], document["title"], document["content"]),
                )
                stored_document = {
                    **document,
                    "source_key": source_key,
                    "source_version": source_version,
                }
                self._insert_chunks(connection, stored_document)

            connection.execute(
                """INSERT INTO knowledge_sources
                   (source_key, name, version, url, sha256, document_count, notice, synced_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source_key) DO UPDATE SET
                       name = excluded.name,
                       version = excluded.version,
                       url = excluded.url,
                       sha256 = excluded.sha256,
                       document_count = excluded.document_count,
                       notice = excluded.notice,
                       synced_at = excluded.synced_at""",
                (
                    source_key,
                    source_name,
                    source_version,
                    source_url,
                    source_sha256,
                    len(prepared),
                    notice,
                    timestamp,
                ),
            )
        return len(prepared)

    @staticmethod
    def _fts_query(query: str) -> str:
        raw_tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9_.:-]*", query)
        tokens: list[str] = []
        for token in raw_tokens:
            cleaned = token.strip(".:-").casefold()
            if len(cleaned) < 3 or cleaned in STOP_WORDS or cleaned in tokens:
                continue
            tokens.append(cleaned)
        return " OR ".join(f'"{token}"' for token in tokens[:24])

    def search(
        self,
        query: str,
        limit: int = 4,
        max_chars: int | None = None,
        source_keys: tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        fts_query = self._fts_query(query)
        if not fts_query or limit < 1:
            return []
        source_filter = ""
        parameters: list[Any] = [fts_query]
        if source_keys:
            placeholders = ",".join("?" for _ in source_keys)
            source_filter = f" AND d.source_key IN ({placeholders})"
            parameters.extend(source_keys)
        parameters.append(max(limit * 10, 40))
        with self._connect() as connection:
            rows = connection.execute(
                f"""SELECT d.*, c.id AS chunk_id, c.position,
                           c.content AS chunk_content,
                           bm25(knowledge_chunk_fts, 8.0, 1.0) AS rank
                    FROM knowledge_chunk_fts
                    JOIN knowledge_chunks c ON c.id = knowledge_chunk_fts.chunk_id
                    JOIN knowledge_documents d ON d.id = c.document_id
                    WHERE knowledge_chunk_fts MATCH ?{source_filter}
                    ORDER BY rank
                    LIMIT ?""",
                parameters,
            ).fetchall()
        exact_ids = {
            token.upper()
            for token in re.findall(r"(?:CWE-|T)\d{2,5}(?:\.\d{3})?", query, re.IGNORECASE)
        }
        rows = sorted(
            rows,
            key=lambda row: (
                row["external_id"].upper() not in exact_ids,
                float(row["rank"]),
            ),
        )
        results = []
        seen_documents: set[str] = set()
        remaining = max_chars
        for row in rows:
            if row["id"] in seen_documents:
                continue
            seen_documents.add(row["id"])
            item = dict(row)
            item["content"] = item.pop("chunk_content")
            if remaining is not None:
                if remaining <= 0:
                    break
                item["content"] = item["content"][:remaining]
                remaining -= len(item["content"])
            item["metadata"] = json.loads(item["metadata"])
            item["relevance"] = round(-float(item.pop("rank")), 4)
            item["retrieval_method"] = "lexical"
            results.append(item)
            if len(results) >= limit:
                break
        return results

    def list_chunks(
        self,
        *,
        source_keys: tuple[str, ...] | None = None,
        missing_embedding_model: str | None = None,
    ) -> list[dict[str, Any]]:
        joins = ""
        filters: list[str] = []
        parameters: list[Any] = []
        if source_keys:
            placeholders = ",".join("?" for _ in source_keys)
            filters.append(f"d.source_key IN ({placeholders})")
            parameters.extend(source_keys)
        if missing_embedding_model:
            joins = (
                " LEFT JOIN knowledge_embeddings e"
                " ON e.chunk_id = c.id AND e.model = ?"
            )
            parameters.insert(0, missing_embedding_model)
            filters.append("e.chunk_id IS NULL")
        where = f" WHERE {' AND '.join(filters)}" if filters else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""SELECT c.id AS chunk_id, c.document_id, c.position, c.content,
                           d.title, d.source_key
                    FROM knowledge_chunks c
                    JOIN knowledge_documents d ON d.id = c.document_id
                    {joins}{where}
                    ORDER BY c.id""",
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_embeddings(
        self,
        model: str,
        embeddings: Iterable[tuple[str, list[float]]],
    ) -> int:
        timestamp = utc_now()
        count = 0
        with self._lock, self._connect() as connection:
            for chunk_id, values in embeddings:
                vector = array("f", values)
                if not vector:
                    raise ValueError("Embedding vectors cannot be empty")
                connection.execute(
                    """INSERT INTO knowledge_embeddings
                       (chunk_id, model, dimension, vector, updated_at)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(chunk_id, model) DO UPDATE SET
                           dimension = excluded.dimension,
                           vector = excluded.vector,
                           updated_at = excluded.updated_at""",
                    (chunk_id, model, len(vector), vector.tobytes(), timestamp),
                )
                count += 1
        return count

    def semantic_search(
        self,
        query_vector: list[float],
        model: str,
        *,
        limit: int = 40,
        source_keys: tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        if not query_vector or limit < 1:
            return []
        source_filter = ""
        parameters: list[Any] = [model]
        if source_keys:
            placeholders = ",".join("?" for _ in source_keys)
            source_filter = f" AND d.source_key IN ({placeholders})"
            parameters.extend(source_keys)
        with self._connect() as connection:
            rows = connection.execute(
                f"""SELECT d.*, c.id AS chunk_id, c.position,
                           c.content AS chunk_content, e.dimension, e.vector
                    FROM knowledge_embeddings e
                    JOIN knowledge_chunks c ON c.id = e.chunk_id
                    JOIN knowledge_documents d ON d.id = c.document_id
                    WHERE e.model = ?{source_filter}""",
                parameters,
            ).fetchall()

        query_norm = math.sqrt(sum(value * value for value in query_vector)) or 1.0
        scored: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            vector = array("f")
            vector.frombytes(row["vector"])
            if len(vector) != len(query_vector) or len(vector) != row["dimension"]:
                continue
            vector_norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            similarity = sum(a * b for a, b in zip(query_vector, vector, strict=True)) / (
                query_norm * vector_norm
            )
            scored.append((similarity, row))
        scored.sort(key=lambda item: item[0], reverse=True)
        results = []
        seen_documents: set[str] = set()
        for similarity, row in scored:
            if row["id"] in seen_documents:
                continue
            seen_documents.add(row["id"])
            item = dict(row)
            item["content"] = item.pop("chunk_content")
            item.pop("vector")
            item.pop("dimension")
            item["metadata"] = json.loads(item["metadata"])
            item["relevance"] = round(similarity, 6)
            item["retrieval_method"] = "semantic"
            results.append(item)
            if len(results) >= limit:
                break
        return results

    def hybrid_search(
        self,
        query: str,
        query_vector: list[float] | None,
        model: str,
        *,
        limit: int = 4,
        max_chars: int | None = None,
        source_keys: tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        if query_vector is None:
            return self.search(query, limit, max_chars, source_keys)
        candidate_limit = max(limit * 10, 40)
        lexical = self.search(query, candidate_limit, None, source_keys)
        semantic = self.semantic_search(
            query_vector,
            model,
            limit=candidate_limit,
            source_keys=source_keys,
        )
        candidates: dict[str, dict[str, Any]] = {}
        scores: dict[str, float] = {}
        methods: dict[str, set[str]] = {}
        for weight, method, items in ((0.8, "lexical", lexical), (0.2, "semantic", semantic)):
            for rank, item in enumerate(items, start=1):
                document_id = item["id"]
                score = weight / (60 + rank)
                if score > scores.get(document_id, -1):
                    candidates[document_id] = item
                scores[document_id] = scores.get(document_id, 0.0) + score
                methods.setdefault(document_id, set()).add(method)
        fused = sorted(candidates, key=lambda item_id: scores[item_id], reverse=True)
        anchors = [items[0]["id"] for items in (lexical, semantic) if items]
        ranked = list(dict.fromkeys([*anchors, *fused]))[:limit]
        results = []
        remaining = max_chars
        for document_id in ranked:
            item = candidates[document_id].copy()
            if remaining is not None:
                if remaining <= 0:
                    break
                item["content"] = item["content"][:remaining]
                remaining -= len(item["content"])
            item["relevance"] = round(scores[document_id], 6)
            item["retrieval_method"] = "+".join(sorted(methods[document_id]))
            results.append(item)
        return results

    def get_by_external_ids(
        self,
        external_ids: Iterable[str],
        *,
        max_chars: int | None = None,
        source_keys: tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        requested = list(dict.fromkeys(identifier.upper() for identifier in external_ids))
        if not requested:
            return []
        placeholders = ",".join("?" for _ in requested)
        source_filter = ""
        parameters: list[Any] = requested.copy()
        if source_keys:
            source_placeholders = ",".join("?" for _ in source_keys)
            source_filter = f" AND source_key IN ({source_placeholders})"
            parameters.extend(source_keys)
        with self._connect() as connection:
            rows = connection.execute(
                f"""SELECT * FROM knowledge_documents
                    WHERE UPPER(external_id) IN ({placeholders}){source_filter}""",
                parameters,
            ).fetchall()

        by_id = {row["external_id"].upper(): row for row in rows}
        results = []
        remaining = max_chars
        for identifier in requested:
            row = by_id.get(identifier)
            if row is None:
                continue
            item = dict(row)
            if remaining is not None:
                if remaining <= 0:
                    break
                item["content"] = item["content"][:remaining]
                remaining -= len(item["content"])
            item["metadata"] = json.loads(item["metadata"])
            item["relevance"] = None
            item["retrieval_method"] = "exact"
            results.append(item)
        return results

    def status(self) -> dict[str, Any]:
        with self._connect() as connection:
            document_count = connection.execute(
                "SELECT COUNT(*) FROM knowledge_documents"
            ).fetchone()[0]
            chunk_count = connection.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()[0]
            embeddings = [
                dict(row)
                for row in connection.execute(
                    """SELECT model, COUNT(*) AS count
                       FROM knowledge_embeddings GROUP BY model ORDER BY model"""
                ).fetchall()
            ]
            sources = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM knowledge_sources ORDER BY source_key"
                ).fetchall()
            ]
        return {
            "ready": document_count > 0,
            "document_count": document_count,
            "chunk_count": chunk_count,
            "embedding_models": embeddings,
            "sources": sources,
            "path": str(self.path),
        }
