from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from cyberslm.knowledge.store import KnowledgeStore

EXPLICIT_REFERENCE = re.compile(
    r"\b(?:CWE-\d+|CAPEC-\d+|T\d{4}(?:\.\d{3})?|ATT&CK|CWE|CAPEC|OWASP)\b",
    re.IGNORECASE,
)
IDENTIFIER = re.compile(r"\b(?:CWE-\d+|CAPEC-\d+|T\d{4}(?:\.\d{3})?)\b", re.IGNORECASE)
ATTACK_SUBTECHNIQUE = re.compile(r"^(T\d{4})\.\d{3}$", re.IGNORECASE)
RAG_POLICIES = frozenset({"auto", "on", "off"})
GENERIC_TITLE_TOKENS = frozenset(
    {
        "cheat",
        "sheet",
        "security",
        "prevention",
        "request",
        "server",
        "side",
        "cwe",
        "capec",
        "attack",
        "improper",
    }
)

EVIDENCE_GAP_SIGNAL = re.compile(
    r"\b(?:no|without|missing|lacks?|not provided|not shown)\b[^.]{0,240}"
    r"\b(?:evidence|telemetry|logs?|requests?|responses?|versions?|reproduction|hosts?|"
    r"users?|timestamps?|destinations?|volumes?|detection logic|configurations?)\b",
    re.IGNORECASE,
)
VALIDATION_SIGNAL = re.compile(
    r"\b(?:verify|verification|validate|validation|test|testing|reproduce|proof of concept|poc)\b",
    re.IGNORECASE,
)
NON_MUTATING_VALIDATION_SIGNAL = re.compile(
    r"\b(?:without|do not|don't|must not|avoid)\b[^.]{0,100}"
    r"\b(?:dumping|extracting|changing (?:data|state|configuration)|modifying|"
    r"accessing|deleting|writing|delays?)\b",
    re.IGNORECASE,
)

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
    "owasp": re.compile(
        r"\b(?:authentication|login endpoint|account (?:enumeration|exists)|enumeration risk|"
        r"authorization|access control|"
        r"business logic|workflow|replay|cross-site request forgery|csrf|"
        r"cross-site scripting|xss|cryptograph\w*|encryption keys?|ciphertext|"
        r"deserializ\w*|stack traces?|error handling|file[- ]uploads?|image uploads?|"
        r"account[- ]recovery|"
        r"forgot password|password reset|reset tokens?|security headers?|http headers?|"
        r"mime sniffing|clickjacking|injection|interpreters?|query syntax|input validation|"
        r"syntactic|semantic validation|allowlist|"
        r"json web token|jwt|security logging|password storage|password hash\w*|"
        r"argon2|memory-hard|rest api|content types?|rate limiting|secrets? management|"
        r"rotation|revocation|server-side request forgery|ssrf|session cookies?|"
        r"session fixation|(?:transport layer security|tls) (?:server|configuration|protocol|"
        r"version|cipher)|external entit\w*|xxe|"
        r"xml pars\w*|shell command|sql text|database quer\w*|user-supplied urls?|"
        r"outbound network)\b",
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
    additional_source_keys: tuple[str, ...] = (),
) -> RetrievalDecision:
    """Decide whether a chat turn should consult the local knowledge index."""
    normalized_policy = policy.strip().casefold()
    if normalized_policy not in RAG_POLICIES:
        raise ValueError("Knowledge policy must be one of: auto, on, off")

    unknown_sources = set(additional_source_keys) - SOURCE_SIGNALS.keys()
    if unknown_sources:
        rendered = ", ".join(sorted(unknown_sources))
        raise ValueError(f"Unknown additional knowledge source(s): {rendered}")
    source_keys = tuple(
        dict.fromkeys((*MODE_SOURCES.get(mode, MODE_SOURCES["general"]), *additional_source_keys))
    )
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
        if re.search(r"\bCWE\b", prompt, re.IGNORECASE):
            referenced_sources.add("cwe")
        if re.search(r"\bCAPEC\b", prompt, re.IGNORECASE):
            referenced_sources.add("capec")
        if re.search(r"\bOWASP\b", prompt, re.IGNORECASE):
            referenced_sources.add("owasp")
        selectable_sources = tuple(
            dict.fromkeys((*MODE_SOURCES["general"], *additional_source_keys))
        )
        selected_sources = tuple(
            source for source in selectable_sources if source in referenced_sources
        )
        if selected_sources:
            return RetrievalDecision(
                normalized_policy,
                True,
                "explicit_reference",
                selected_sources,
            )

    # Retrieved examples can tempt a small model to fill stated evidence gaps. Bounded
    # validation requests also benefit more from the safety contract than extra attack examples.
    # Exact IDs or explicit ATT&CK/CWE/CAPEC requests above still override these abstentions.
    if EVIDENCE_GAP_SIGNAL.search(prompt):
        return RetrievalDecision(normalized_policy, False, "insufficient_evidence", source_keys)
    if VALIDATION_SIGNAL.search(prompt) and NON_MUTATING_VALIDATION_SIGNAL.search(prompt):
        return RetrievalDecision(normalized_policy, False, "operational_validation", source_keys)

    matched_sources = tuple(
        source for source in source_keys if SOURCE_SIGNALS[source].search(prompt)
    )
    if matched_sources:
        return RetrievalDecision(normalized_policy, True, "source_relevant", matched_sources)
    return RetrievalDecision(normalized_policy, False, "not_source_relevant", source_keys)


class QueryEmbedder(Protocol):
    model_name: str

    def embed_query(self, query: str) -> list[float]: ...


def _topic_tokens(value: str) -> set[str]:
    tokens: set[str] = set()
    for token in re.findall(r"[a-z0-9]+", value.casefold()):
        if token in GENERIC_TITLE_TOKENS or token.isdigit():
            continue
        if len(token) > 4 and token.endswith("ies"):
            token = f"{token[:-3]}y"
        elif len(token) > 4 and token.endswith("es"):
            token = token[:-2]
        elif len(token) > 3 and token.endswith("s"):
            token = token[:-1]
        tokens.add(token)
    return tokens


def _prefer_title_match(
    prompt: str,
    results: list[dict],
    preferred_source_keys: tuple[str, ...],
) -> list[dict]:
    """Promote one directly named pilot topic while preserving the remaining rank order."""
    if not preferred_source_keys or len(results) < 2:
        return results
    prompt_tokens = _topic_tokens(prompt)
    preferred = set(preferred_source_keys)
    candidates: list[tuple[int, int]] = []
    for index, item in enumerate(results):
        if item["source_key"] not in preferred:
            continue
        title_tokens = _topic_tokens(item["title"])
        overlap = prompt_tokens & title_tokens
        if overlap:
            candidates.append((len(overlap), -index))
    if not candidates:
        return results
    best_index = -max(candidates)[1]
    if best_index == 0:
        return results
    return [results[best_index], *results[:best_index], *results[best_index + 1 :]]


def expanded_query(prompt: str) -> str:
    lowered = prompt.casefold()
    additions: list[str] = []
    rules = (
        (("failed login", "password guess", "brute force", "ssh login"), "T1110 brute force"),
        (("sql injection", "cursor.execute", " select ", "sql query"), "CWE-89 SQL injection"),
        (("shell command", "operating system command", "command injection"), "CWE-78"),
        (("path traversal", "dot-dot path", "outside its intended directory"), "CWE-22"),
        (("use-after-free", "use after free"), "CWE-416 use after free"),
        (
            (
                "ssrf",
                "server-side request forgery",
                "server fetches",
                "url fetcher",
                "fetches user-supplied url",
            ),
            "CWE-918 server-side request forgery",
        ),
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
    preferred_source_keys: tuple[str, ...] = (),
) -> list[dict]:
    selected_source_keys = source_keys or {
        "secure_code": ("cwe",),
        "defensive": ("attack",),
        "forensics": ("attack",),
    }.get(mode)
    query = expanded_query(prompt)
    # Only identifiers supplied by the user should bypass ranking. Identifiers added by query
    # expansion are ranking hints; treating them as exact requests starves complementary sources.
    exact_ids = IDENTIFIER.findall(prompt)
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
        embedded_models = {item["model"]: item["count"] for item in status["embedding_models"]}
        if embedded_models.get(embedder.model_name, 0) == status["chunk_count"]:
            try:
                query_vector = embedder.embed_query(query)
            except (RuntimeError, ValueError, OSError):
                query_vector = None
    candidate_limit = max(limit, 4) if preferred_source_keys else limit
    results = store.hybrid_search(
        query,
        query_vector,
        embedder.model_name if embedder else "",
        limit=candidate_limit,
        max_chars=None,
        source_keys=selected_source_keys,
    )
    results = _prefer_title_match(prompt, results, preferred_source_keys)
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
