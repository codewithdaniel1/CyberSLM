from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from cyberslm.config import settings
from cyberslm.knowledge.ingest import sync_source
from cyberslm.knowledge.retrieve import retrieve
from cyberslm.knowledge.sources import SOURCES
from cyberslm.knowledge.store import KnowledgeStore
from cyberslm.modes import MODES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage CyberSLM's local knowledge store")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sync = subparsers.add_parser("sync", help="Download and index authoritative sources")
    sync.add_argument("--source", action="append", choices=tuple(SOURCES), dest="sources")

    subparsers.add_parser("status", help="Show indexed source versions and document counts")

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
            source = SOURCES[key]
            print(f"Syncing {source.name} {source.version}...", flush=True)
            count = sync_source(store, source, source_dir)
            print(f"Indexed {count} documents from {source.name}.")
        return 0

    if args.command == "status":
        status = store.status()
        print(f"Knowledge database: {status['path']}")
        print(f"Documents: {status['document_count']}")
        for source in status["sources"]:
            print(
                f"- {source['name']} {source['version']}: "
                f"{source['document_count']} documents (synced {source['synced_at']})"
            )
        return 0

    results = retrieve(
        store,
        args.query,
        args.mode,
        limit=args.limit,
        max_chars=settings.rag_max_chars,
    )
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for result in results:
            print(f"{result['title']}\n{result['url']}\n{result['content'][:500]}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
