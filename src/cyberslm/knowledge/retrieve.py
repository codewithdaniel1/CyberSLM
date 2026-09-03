from __future__ import annotations

import re
from typing import Protocol

from cyberslm.knowledge.store import KnowledgeStore

EXPLICIT_REFERENCE = re.compile(
    r"\b(?:CWE-\d+|CAPEC-\d+|T\d{4}(?:\.\d{3})?|ATT&CK|CAPEC)\b", re.IGNORECASE
)
IDENTIFIER = re.compile(
    r"\b(?:CWE-\d+|CAPEC-\d+|T\d{4}(?:\.\d{3})?)\b", re.IGNORECASE
)
ATTACK_SUBTECHNIQUE = re.compile(r"^(T\d{4})\.\d{3}$", re.IGNORECASE)


class QueryEmbedder(Protocol):
    model_name: str

    def embed_query(self, query: str) -> list[float]: ...


def expanded_query(prompt: str) -> str:
    lowered = prompt.casefold()
    additions: list[str] = []
    rules = (
        (("failed login", "password guess", "brute force", "ssh login"), "T1110 brute force"),
        (("cursor.execute", " select ", "sql query"), "CWE-89 SQL injection"),
        (("shell command", "operating system command", "command injection"), "CWE-78"),
        (("path traversal", "dot-dot path", "outside its intended directory"), "CWE-22"),
        (("ssrf", "server-side request forgery"), "CWE-918 server-side request forgery"),
        (("cross-site scripting", "xss"), "CWE-79 cross-site scripting"),
        (("cross-site request forgery", "csrf"), "CWE-352 cross-site request forgery"),
        (("powershell", "event id 4104"), "T1059.001 PowerShell script block"),
    )
    padded = f" {lowered} "
    for signals, expansion in rules:
        if any(signal in padded for signal in signals):
            additions.append(expansion)
    return " ".join([prompt, *additions])


def retrieve(
    store: KnowledgeStore,
    prompt: str,
    mode: str,
    *,
    limit: int = 4,
    max_chars: int = 16_000,
    embedder: QueryEmbedder | None = None,
) -> list[dict]:
    if mode == "ctf" and not EXPLICIT_REFERENCE.search(prompt):
        return []
    source_keys = {
        "secure_code": ("cwe",),
        "defensive": ("attack",),
        "forensics": ("attack",),
    }.get(mode)
    query = expanded_query(prompt)
    exact_ids = IDENTIFIER.findall(query)
    if exact_ids:
        exact_results = store.get_by_external_ids(
            exact_ids,
            max_chars=max_chars,
            source_keys=source_keys,
        )
        if exact_results:
            return exact_results[:limit]
    query_vector = None
    if embedder is not None:
        status = store.status()
        embedded_models = {
            item["model"]: item["count"] for item in status["embedding_models"]
        }
        if embedded_models.get(embedder.model_name, 0) == status["chunk_count"]:
            try:
                query_vector = embedder.embed_query(query)
            except (RuntimeError, ValueError, OSError):
                query_vector = None
    results = store.hybrid_search(
        query,
        query_vector,
        embedder.model_name if embedder else "",
        limit=limit,
        max_chars=None,
        source_keys=source_keys,
    )
    first_subtechnique = next(
        (
            ATTACK_SUBTECHNIQUE.match(item["external_id"])
            for item in results
            if ATTACK_SUBTECHNIQUE.match(item["external_id"])
        ),
        None,
    )
    if first_subtechnique:
        parent_id = first_subtechnique.group(1).upper()
        if all(item["external_id"].upper() != parent_id for item in results):
            parents = store.get_by_external_ids(
                [parent_id],
                source_keys=("attack",),
            )
            if parents:
                parents[0]["retrieval_method"] = "parent-promotion"
                results = [parents[0], *results]

    selected = []
    remaining = max_chars
    for item in results[:limit]:
        item = item.copy()
        if remaining is not None:
            if remaining <= 0:
                break
            item["content"] = item["content"][:remaining]
            remaining -= len(item["content"])
        selected.append(item)
    return selected
