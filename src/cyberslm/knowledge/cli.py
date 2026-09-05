from __future__ import annotations

import argparse
import hashlib
import hmac
import json
from collections.abc import Sequence

from cyberslm.config import settings
from cyberslm.knowledge.embeddings import LocalEmbedder, rebuild_embeddings
from cyberslm.knowledge.ingest import sync_source
from cyberslm.knowledge.retrieve import retrieve
from cyberslm.knowledge.sources import ALL_SOURCES, SOURCES
from cyberslm.knowledge.store import KnowledgeStore
from cyberslm.modes import MODES


def embedding_progress(completed: int, total: int) -> None:
    print(f"Embedded {completed}/{total} pending passages...", flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage CyberSLM's local knowledge store")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync = subparsers.add_parser("sync", help="Download and index authoritative sources")
    sync.add_argument("--source", action="append", choices=tuple(ALL_SOURCES), dest="sources")
    sync.add_argument(
        "--no-embeddings", action="store_true", help="Skip rebuilding semantic embeddings"
    )

    subparsers.add_parser("status", help="Show indexed source versions and document counts")
    verify = subparsers.add_parser("verify", help="Verify local sources and index metadata")
    verify.add_argument(
        "--source", action="append", choices=tuple(ALL_SOURCES), dest="sources"
    )
    subparsers.add_parser("embed", help="Build local semantic embeddings for indexed passages")

    search = subparsers.add_parser("search", help="Search the local knowledge index")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=4)
    search.add_argument("--mode", choices=tuple(MODES), default="general")
    search.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings.ensure_directories()
    store = KnowledgeStore(settings.knowledge_database_path)

    if args.command == "sync":
        selected = args.sources or list(SOURCES)
        source_dir = settings.knowledge_dir / "sources"
        for key in selected:
            source = ALL_SOURCES[key]
            print(f"Syncing {source.name} {source.version}...", flush=True)
            count = sync_source(store, source, source_dir)
            print(f"Indexed {count} documents from {source.name}.")
        if not args.no_embeddings:
            embedder = LocalEmbedder(
                settings.rag_embedding_model,
                settings.embedding_cache_dir,
                allow_download=True,
            )
            print(f"Building semantic embeddings with {embedder.model_name}...", flush=True)
            embedded = rebuild_embeddings(store, embedder, progress=embedding_progress)
            print(f"Embedded {embedded} new passages.")
        return 0

    if args.command == "status":
        status = store.status()
        print(f"Knowledge database: {status['path']}")
        print(f"Documents: {status['document_count']}")
        print(f"Passages: {status['chunk_count']}")
        for source in status["sources"]:
            expected = ALL_SOURCES.get(source["source_key"])
            verified = bool(
                expected
                and source["version"] == expected.version
                and hmac.compare_digest(source["sha256"], expected.sha256)
                and source["document_count"] == expected.document_count
            )
            print(
                f"- {source['name']} {source['version']}: "
                f"{source['document_count']} documents "
                f"({'verified' if verified else 'unverified'}, synced {source['synced_at']})"
            )
        for embedding in status["embedding_models"]:
            print(f"- Embeddings {embedding['model']}: {embedding['count']} passages")
        return 0

    if args.command == "verify":
        status = store.status()
        indexed = {source["source_key"]: source for source in status["sources"]}
        source_dir = settings.knowledge_dir / "sources"
        valid = True
        selected = args.sources or list(SOURCES)
        for key in selected:
            expected = ALL_SOURCES[key]
            raw_path = source_dir / expected.filename
            record = indexed.get(key)
            raw_digest = ""
            if raw_path.is_file():
                digest = hashlib.sha256()
                with raw_path.open("rb") as source_file:
                    for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
                        digest.update(chunk)
                raw_digest = digest.hexdigest()
            checks = {
                "source file": raw_path.is_file()
                and hmac.compare_digest(raw_digest, expected.sha256),
                "index metadata": bool(
                    record
                    and record["version"] == expected.version
                    and hmac.compare_digest(record["sha256"], expected.sha256)
                    and record["document_count"] == expected.document_count
                ),
            }
            source_valid = all(checks.values())
            valid = valid and source_valid
            details = ", ".join(
                f"{name}={'ok' if passed else 'failed'}" for name, passed in checks.items()
            )
            label = "OK" if source_valid else "FAIL"
            print(f"{label} {expected.name} {expected.version}: {details}")
        chunks_valid = status["chunk_count"] >= status["document_count"] > 0
        valid = valid and chunks_valid
        print(
            f"{'OK' if chunks_valid else 'FAIL'} passage index: "
            f"{status['chunk_count']} passages for {status['document_count']} documents"
        )
        if settings.rag_semantic_enabled:
            embedding_counts = {
                item["model"]: item["count"] for item in status["embedding_models"]
            }
            embedded = embedding_counts.get(settings.rag_embedding_model, 0)
            embeddings_valid = embedded == status["chunk_count"]
            valid = valid and embeddings_valid
            print(
                f"{'OK' if embeddings_valid else 'FAIL'} semantic index: "
                f"{embedded}/{status['chunk_count']} passages with "
                f"{settings.rag_embedding_model}"
            )
        return 0 if valid else 1

    if args.command == "embed":
        embedder = LocalEmbedder(
            settings.rag_embedding_model,
            settings.embedding_cache_dir,
            allow_download=True,
        )
        print(f"Building semantic embeddings with {embedder.model_name}...", flush=True)
        embedded = rebuild_embeddings(store, embedder, progress=embedding_progress)
        print(f"Embedded {embedded} new passages.")
        return 0

    embedder = (
        LocalEmbedder(settings.rag_embedding_model, settings.embedding_cache_dir)
        if settings.rag_semantic_enabled
        else None
    )
    results = retrieve(
        store,
        args.query,
        args.mode,
        limit=args.limit,
        max_chars=settings.rag_max_chars,
        embedder=embedder,
    )
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for result in results:
            print(f"{result['title']}\n{result['url']}\n{result['content'][:500]}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
