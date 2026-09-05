from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from cyberslm.knowledge.store import KnowledgeStore

EXPLICIT_REFERENCE = re.compile(
    r"\b(?:CWE-\d+|CAPEC-\d+|T\d{4}(?:\.\d{3})?|ATT&CK|CAPEC)\b", re.IGNORECASE
)
IDENTIFIER = re.compile(
    r"\b(?:CWE-\d+|CAPEC-\d+|T\d{4}(?:\.\d{3})?)\b", re.IGNORECASE
)
ATTACK_SUBTECHNIQUE = re.compile(r"^(T\d{4})\.\d{3}$", re.IGNORECASE)
RAG_POLICIES = frozenset({"auto", "on", "off"})

MODE_SOURCES = {
    "general": ("attack", "cwe", "capec"),
    "secure_code": ("cwe",),
    "defensive": ("attack",),
    "forensics": ("attack",),
    "offensive": ("attack", "cwe", "capec"),
    "ctf": ("attack", "cwe", "capec"),
}

SOURCE_SIGNALS = {
    "attack": re.compile(
        r"\b(?:failed (?:ssh )?logins?|password (?:guessing|spraying)|brute force|"
        r"credential (?:access|dumping)|lateral movement|privilege escalation|persistence|"
        r"command and control|c2|exfiltrat\w*|phishing|ransomware|"
        r"malware[- ](?:analysis|behavior|execution|infection|activity|sample)|powershell|"
        r"process injection|scheduled task|event id \d+|threat hunt\w*|ioc|"
        r"indicator of compromise|incident response|security alert|detection engineering|"
        r"suspicious (?:login|sign-in|authentication|process|traffic)|unauthorized access|"
        r"account takeover|reverse shell|web shell|exploit(?:ation)?)\b",
        re.IGNORECASE,
    ),
    "cwe": re.compile(
        r"\b(?:sql injection|command injection|path traversal|cross-site scripting|xss|"
        r"cross-site request forgery|csrf|server-side request forgery|ssrf|buffer overflow|"
        r"use-after-free|deserializ\w*|input validation|memory safety|secure cod\w*|"
        r"code review|review (?:this )?(?:code|function)|software weakness|"
        r"security (?:bug|issue|flaw)|untrusted input|unsafe function)\b|"
        r"cursor\.execute|os\.system|subprocess|strcpy|memcpy|shell\s*=\s*true|\beval\s*\(",
        re.IGNORECASE,
    ),
    "capec": re.compile(
        r"\b(?:attack pattern|abuse case|social engineering|"
        r"reconnaissance|adversary behavior|(?:build|create|develop|construct)(?:ing|ed)?\s+"
        r"(?:an?\s+)?(?:authorized\s+)?threat model\w*)\b",
        re.IGNORECASE,
    ),
}


@dataclass(frozen=True, slots=True)
class RetrievalDecision:
    policy: str
    should_retrieve: bool
    reason: str
    source_keys: tuple[str, ...] = ()

    def metadata(self, document_count: int = 0) -> dict:
        return {
            "policy": self.policy,
            "attempted": self.should_retrieve,
            "used": document_count > 0,
            "reason": self.reason,
            "source_keys": list(self.source_keys),
            "document_count": document_count,
        }


def decide_retrieval(
    prompt: str,
    mode: str,
    policy: str = "auto",
    *,
    enabled: bool = True,
) -> RetrievalDecision:
    """Decide whether a chat turn should consult the local knowledge index."""
    normalized_policy = policy.strip().casefold()
    if normalized_policy not in RAG_POLICIES:
        raise ValueError("Knowledge policy must be one of: auto, on, off")

    source_keys = MODE_SOURCES.get(mode, MODE_SOURCES["general"])
    if not enabled:
        return RetrievalDecision(normalized_policy, False, "master_switch_off")
    if normalized_policy == "off":
        return RetrievalDecision(normalized_policy, False, "disabled_for_message")
    if normalized_policy == "on":
        return RetrievalDecision(normalized_policy, True, "forced_for_message", source_keys)
    if EXPLICIT_REFERENCE.search(prompt):
        referenced_sources = set()
        for identifier in IDENTIFIER.findall(prompt):
            normalized_identifier = identifier.upper()
            if normalized_identifier.startswith("T"):
                referenced_sources.add("attack")
            elif normalized_identifier.startswith("CWE-"):
                referenced_sources.add("cwe")
            elif normalized_identifier.startswith("CAPEC-"):
                referenced_sources.add("capec")
        if re.search(r"\bATT&CK\b", prompt, re.IGNORECASE):
            referenced_sources.add("attack")
        if re.search(r"\bCAPEC\b", prompt, re.IGNORECASE):
            referenced_sources.add("capec")
        selected_sources = tuple(
            source for source in MODE_SOURCES["general"] if source in referenced_sources
        )
        return RetrievalDecision(
            normalized_policy,
            True,
            "explicit_reference",
            selected_sources or source_keys,
        )

    matched_sources = tuple(
        source for source in source_keys if SOURCE_SIGNALS[source].search(prompt)
    )
    if matched_sources:
        return RetrievalDecision(normalized_policy, True, "source_relevant", matched_sources)
    return RetrievalDecision(normalized_policy, False, "not_source_relevant", source_keys)


class QueryEmbedder(Protocol):
    model_name: str

    def embed_query(self, query: str) -> list[float]: ...


def expanded_query(prompt: str) -> str:
    lowered = prompt.casefold()
    additions: list[str] = []
    rules = (
        (("failed login", "password guess", "brute force", "ssh login"), "T1110 brute force"),
        (("sql injection", "cursor.execute", " select ", "sql query"), "CWE-89 SQL injection"),
        (("shell command", "operating system command", "command injection"), "CWE-78"),
        (("path traversal", "dot-dot path", "outside its intended directory"), "CWE-22"),
        (("use-after-free", "use after free"), "CWE-416 use after free"),
        (("ssrf", "server-side request forgery"), "CWE-918 server-side request forgery"),
        (("cross-site scripting", "xss"), "CWE-79 cross-site scripting"),
        (("cross-site request forgery", "csrf"), "CWE-352 cross-site request forgery"),
        (("powershell", "event id 4104"), "T1059.001 PowerShell script block"),
        (("dns beacon", "dns query", "periodic dns"), "T1071.004 DNS"),
    )
    padded = f" {lowered} "
    for signals, expansion in rules:
        if any(signal in padded for signal in signals):
            additions.append(expansion)
    freed_buffer_write = re.search(
        r"\bfree\s*\(\s*(?P<pointer>[A-Za-z_]\w*)\s*\)\s*;.{0,200}"
        r"\b(?:memcpy|memmove|strcpy|strncpy)\s*\(\s*(?P=pointer)\b",
        prompt,
        re.IGNORECASE | re.DOTALL,
    )
    if freed_buffer_write and not any("CWE-416" in item for item in additions):
        additions.append("CWE-416 use after free")
    return " ".join([prompt, *additions])


def retrieve(
    store: KnowledgeStore,
    prompt: str,
    mode: str,
    *,
    limit: int = 4,
    max_chars: int = 16_000,
    embedder: QueryEmbedder | None = None,
    source_keys: tuple[str, ...] | None = None,
) -> list[dict]:
    selected_source_keys = source_keys or {
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
        source_keys=selected_source_keys,
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
