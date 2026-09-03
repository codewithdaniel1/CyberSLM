from __future__ import annotations

import re

from cyberslm.knowledge.store import KnowledgeStore

EXPLICIT_REFERENCE = re.compile(r"\b(?:CWE-\d+|T\d{4}(?:\.\d{3})?|ATT&CK)\b", re.IGNORECASE)
IDENTIFIER = re.compile(r"\b(?:CWE-\d+|T\d{4}(?:\.\d{3})?)\b", re.IGNORECASE)


def expanded_query(prompt: str) -> str:
    lowered = prompt.casefold()
    additions: list[str] = []
    rules = (
        (("failed login", "password guess", "brute force", "ssh login"), "T1110 brute force"),
        (("cursor.execute", " select ", "sql query"), "CWE-89 SQL injection"),
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
    return store.search(
        query,
        limit=limit,
        max_chars=max_chars,
        source_keys=source_keys,
    )
