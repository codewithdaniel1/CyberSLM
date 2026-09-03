from __future__ import annotations

import json
import re
import sqlite3
import threading
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
                """
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
                f"""SELECT d.*, bm25(knowledge_fts, 8.0, 1.0) AS rank
                    FROM knowledge_fts
                    JOIN knowledge_documents d ON d.id = knowledge_fts.document_id
                    WHERE knowledge_fts MATCH ?{source_filter}
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
        )[:limit]
        results = []
        remaining = max_chars
        for row in rows:
            item = dict(row)
            if remaining is not None:
                if remaining <= 0:
                    break
                item["content"] = item["content"][:remaining]
                remaining -= len(item["content"])
            item["metadata"] = json.loads(item["metadata"])
            item["relevance"] = round(-float(item.pop("rank")), 4)
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
            results.append(item)
        return results

    def status(self) -> dict[str, Any]:
        with self._connect() as connection:
            document_count = connection.execute(
                "SELECT COUNT(*) FROM knowledge_documents"
            ).fetchone()[0]
            sources = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM knowledge_sources ORDER BY source_key"
                ).fetchall()
            ]
        return {
            "ready": document_count > 0,
            "document_count": document_count,
            "sources": sources,
            "path": str(self.path),
        }
