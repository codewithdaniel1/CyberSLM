from __future__ import annotations

import json
import os
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from cyberslm.knowledge.chunking import chunk_text
from cyberslm.knowledge.embeddings import DEFAULT_EMBEDDING_MODEL
from cyberslm.knowledge.ingest import (
    MAX_OWASP_DOCUMENT_BYTES,
    parse_attack,
    parse_capec,
    parse_cwe,
    parse_owasp,
    verify_payload,
)
from cyberslm.knowledge.retrieve import decide_retrieval, expanded_query, retrieve
from cyberslm.knowledge.sources import ALL_SOURCES, PILOT_SOURCES, SOURCES, KnowledgeSource
from cyberslm.knowledge.store import KnowledgeStore


class FakeEmbedder:
    model_name = "test-embedding"

    def embed_query(self, query: str) -> list[float]:
        del query
        return [0.0, 1.0]


def test_embedding_runtime_disables_telemetry() -> None:
    assert DEFAULT_EMBEDDING_MODEL
    assert os.environ["ORT_DISABLE_TELEMETRY"] == "1"


def test_owasp_source_is_available_only_as_a_pilot() -> None:
    assert "owasp" not in SOURCES
    assert ALL_SOURCES["owasp"] is PILOT_SOURCES["owasp"]
    assert PILOT_SOURCES["owasp"].document_count == 24


def document(identifier: str, title: str, content: str) -> dict:
    return {
        "id": identifier,
        "external_id": identifier.split(":", 1)[1],
        "title": title,
        "url": f"https://example.test/{identifier}",
        "content": content,
    }


def replace(store: KnowledgeStore, source: str, documents: list[dict]) -> None:
    store.replace_source(
        source_key=source,
        source_name=source.upper(),
        source_version="1",
        source_url="https://example.test/source",
        source_sha256="abc123",
        notice="Test data",
        documents=documents,
    )


def test_store_search_and_source_replacement(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db")
    replace(
        store,
        "attack",
        [
            document("attack:T1110", "T1110 — Brute Force", "Password guessing activity"),
            document("attack:T1059", "T1059 — Command Interpreter", "Shell execution"),
        ],
    )

    result = store.search("failed password guessing T1110", limit=1)
    assert result[0]["external_id"] == "T1110"
    assert store.status()["document_count"] == 2

    replace(
        store,
        "attack",
        [document("attack:T1059", "T1059 — Command Interpreter", "Shell execution")],
    )
    assert store.search("T1110 password guessing") == []
    assert store.status()["document_count"] == 1


def test_search_respects_character_budget(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db")
    replace(store, "cwe", [document("cwe:CWE-89", "CWE-89 SQL Injection", "injection " * 20)])
    result = store.search("SQL injection", max_chars=25)
    assert len(result[0]["content"]) == 25


def test_search_limit_counts_unique_documents_not_matching_chunks(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db")
    replace(
        store,
        "test",
        [
            document("test:ONE", "Repeated guidance", "security guidance. " * 300),
            document("test:TWO", "Second guidance", "security guidance for validation"),
        ],
    )

    results = store.search("security guidance", limit=2)

    assert {item["external_id"] for item in results} == {"ONE", "TWO"}


def test_mode_aware_retrieval_and_query_expansion(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db")
    replace(
        store,
        "cwe",
        [
            document("cwe:CWE-89", "CWE-89 SQL Injection", "Parameterized SQL queries"),
            document("cwe:CWE-416", "CWE-416 Use After Free", "Freed memory is reused"),
        ],
    )
    replace(
        store,
        "attack",
        [document("attack:T1110", "T1110 Brute Force", "Failed password guessing")],
    )

    code_results = retrieve(
        store,
        'Review cursor.execute(f"SELECT * FROM users WHERE name={name}")',
        "secure_code",
    )
    assert code_results[0]["external_id"] == "CWE-89"
    assert len(code_results) == 1
    assert all(item["source_key"] == "cwe" for item in code_results)
    assert retrieve(store, "Decode this Base64 string", "ctf") == []
    assert "T1110" in expanded_query("Investigate failed SSH logins")
    assert "T1071.004" in expanded_query("Investigate a periodic DNS query")
    assert "CWE-89" in expanded_query("Verify suspected SQL injection")
    assert "CWE-416" in expanded_query("Review this use-after-free")
    assert "CWE-416" in expanded_query(
        'char *p = malloc(16); free(p); strcpy(p, "ok");'
    )
    assert "CWE-918" in expanded_query("A server fetches user-supplied URLs")
    assert retrieve(store, "Review this use-after-free", "secure_code")[0][
        "external_id"
    ] == "CWE-416"
    defensive_results = retrieve(store, "Investigate failed SSH logins", "defensive")
    assert [item["external_id"] for item in defensive_results] == ["T1110"]


def test_selective_retrieval_policy() -> None:
    ordinary = decide_retrieval("Thanks, that makes sense.", "general")
    assert not ordinary.should_retrieve
    assert ordinary.reason == "not_source_relevant"

    defensive = decide_retrieval("Triage these failed SSH logins", "defensive")
    assert defensive.should_retrieve
    assert defensive.reason == "source_relevant"
    assert defensive.source_keys == ("attack",)

    code = decide_retrieval("Review this SQL injection bug", "secure_code")
    assert code.should_retrieve
    assert code.source_keys == ("cwe",)

    exact = decide_retrieval("Explain T1110", "ctf")
    assert exact.should_retrieve
    assert exact.reason == "explicit_reference"
    assert exact.source_keys == ("attack",)

    assert not decide_retrieval(
        "The threat model was not provided, so compare these authentication systems.",
        "general",
    ).should_retrieve
    assert decide_retrieval(
        "Build an authorized threat model for this service.",
        "offensive",
    ).source_keys == ("capec",)
    assert not decide_retrieval(
        "The file is mystery.bin; identify its exact vulnerability without the file.",
        "ctf",
    ).should_retrieve
    assert not decide_retrieval(
        "Does a hash from a public malware report prove attribution?",
        "forensics",
    ).should_retrieve
    assert decide_retrieval(
        "Plan safe malware sample analysis.",
        "forensics",
    ).source_keys == ("attack",)

    evidence_gap = decide_retrieval(
        "Possible data exfiltration, but there is no host, user, timestamp, or telemetry.",
        "defensive",
    )
    assert not evidence_gap.should_retrieve
    assert evidence_gap.reason == "insufficient_evidence"

    path_validation = decide_retrieval(
        "Describe a non-destructive way to verify suspected path traversal.",
        "offensive",
    )
    assert path_validation.should_retrieve
    assert path_validation.reason == "source_relevant"

    bounded_validation = decide_retrieval(
        "Verify SQL injection without dumping records or changing data.",
        "offensive",
    )
    assert not bounded_validation.should_retrieve
    assert bounded_validation.reason == "operational_validation"

    explicit_validation = decide_retrieval(
        "Using CWE-22, describe a non-destructive path-traversal validation.",
        "offensive",
    )
    assert explicit_validation.should_retrieve
    assert explicit_validation.reason == "explicit_reference"

    explicit_cwe_family = decide_retrieval(
        "Use CWE as a reference for this conservative validation.",
        "offensive",
    )
    assert explicit_cwe_family.source_keys == ("cwe",)

    assert decide_retrieval("Explain T1110", "general", "off").reason == "disabled_for_message"
    assert decide_retrieval("Hello", "general", "on").reason == "forced_for_message"
    assert not decide_retrieval("Explain T1110", "general", enabled=False).should_retrieve
    with pytest.raises(ValueError, match="auto, on, off"):
        decide_retrieval("Hello", "general", "sometimes")


def test_pilot_sources_are_opt_in_for_retrieval_policy() -> None:
    prompt = "How should an API validate a JWT issuer and audience?"

    production = decide_retrieval(prompt, "general")
    pilot = decide_retrieval(prompt, "general", additional_source_keys=("owasp",))
    explicit_pilot = decide_retrieval(
        "Use the OWASP guidance for password storage.",
        "general",
        additional_source_keys=("owasp",),
    )

    assert not production.should_retrieve
    assert "owasp" not in production.source_keys
    assert pilot.should_retrieve
    assert pilot.reason == "source_relevant"
    assert pilot.source_keys == ("owasp",)
    assert explicit_pilot.reason == "explicit_reference"
    assert explicit_pilot.source_keys == ("owasp",)

    with pytest.raises(ValueError, match="Unknown additional knowledge source"):
        decide_retrieval(prompt, "general", additional_source_keys=("unknown",))


def test_exact_identifier_lookup_ignores_mode_source_routing(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db")
    replace(
        store,
        "attack",
        [document("attack:T1110", "T1110 Brute Force", "Failed password guessing")],
    )

    results = retrieve(store, "Explain T1110", "secure_code", source_keys=("cwe",))
    assert results[0]["external_id"] == "T1110"


def test_query_expansion_does_not_short_circuit_complementary_sources(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db")
    replace(
        store,
        "cwe",
        [document("cwe:CWE-79", "CWE-79 XSS", "Cross-site scripting weakness")],
    )
    replace(
        store,
        "owasp",
        [
            document(
                "owasp:Cross_Site_Scripting_Prevention_Cheat_Sheet",
                "Cross Site Scripting Prevention Cheat Sheet",
                "Context-sensitive output encoding prevents cross-site scripting in HTML",
            )
        ],
    )

    results = retrieve(
        store,
        "How should we prevent cross-site scripting with contextual output encoding?",
        "general",
        limit=4,
    )

    assert {item["source_key"] for item in results} == {"cwe", "owasp"}


def test_preferred_pilot_source_promotes_direct_title_match() -> None:
    class FixedRankStore:
        def hybrid_search(self, *args, **kwargs) -> list[dict]:
            del args, kwargs
            return [
                {
                    **document(
                        "owasp:BUSINESS",
                        "Business Logic Security Cheat Sheet",
                        "Authorization checks for workflows and entry points",
                    ),
                    "source_key": "owasp",
                },
                {
                    **document(
                        "owasp:AUTHORIZATION",
                        "Authorization Cheat Sheet",
                        "Authorization must be enforced for each request",
                    ),
                    "source_key": "owasp",
                },
            ]

    store = FixedRankStore()
    prompt = "How should authorization be enforced on every API request?"

    baseline = retrieve(store, prompt, "general", limit=2, source_keys=("owasp",))
    preferred = retrieve(
        store,
        prompt,
        "general",
        limit=2,
        source_keys=("owasp",),
        preferred_source_keys=("owasp",),
    )

    assert baseline[0]["external_id"] == "BUSINESS"
    assert preferred[0]["external_id"] == "AUTHORIZATION"


def test_parse_attack_techniques() -> None:
    payload = {
        "objects": [
            {
                "type": "attack-pattern",
                "name": "Brute Force",
                "description": "Adversaries may use brute force techniques.",
                "x_mitre_platforms": ["Linux"],
                "kill_chain_phases": [{"phase_name": "credential-access"}],
                "external_references": [
                    {
                        "source_name": "mitre-attack",
                        "external_id": "T1110",
                        "url": "https://attack.mitre.org/techniques/T1110/",
                    }
                ],
            }
        ]
    }
    parsed = list(parse_attack(json.dumps(payload).encode()))
    assert parsed[0]["external_id"] == "T1110"
    assert "credential-access" in parsed[0]["content"]


def test_parse_cwe_archive() -> None:
    xml = b"""<?xml version="1.0"?>
    <Weakness_Catalog xmlns="http://cwe.mitre.org/cwe-7">
      <Weaknesses>
        <Weakness ID="89" Name="SQL Injection" Abstraction="Base" Status="Stable">
          <Description>SQL commands built from externally-controlled input.</Description>
          <Potential_Mitigations>
            <Mitigation><Description>Use parameterized queries.</Description></Mitigation>
          </Potential_Mitigations>
        </Weakness>
      </Weaknesses>
    </Weakness_Catalog>"""
    archive_bytes = BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        archive.writestr("cwec.xml", xml)

    parsed = list(parse_cwe(archive_bytes.getvalue()))
    assert parsed[0]["external_id"] == "CWE-89"
    assert "parameterized queries" in parsed[0]["content"]


def test_source_payload_hash_must_match() -> None:
    source = KnowledgeSource(
        key="test",
        name="Test source",
        version="1",
        url="https://example.test/source",
        filename="source.json",
        sha256="2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
        document_count=1,
        notice="Test data",
    )
    assert verify_payload(source, b"hello") == source.sha256
    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        verify_payload(source, b"changed")


def test_parse_capec_archive() -> None:
    xml = b"""<?xml version="1.0"?>
    <Attack_Pattern_Catalog xmlns="http://capec.mitre.org/capec-3">
      <Attack_Patterns>
        <Attack_Pattern ID="66" Name="SQL Injection" Abstraction="Standard" Status="Stable">
          <Description>Manipulate an SQL query through untrusted input.</Description>
          <Mitigations><Mitigation>Use parameterized queries.</Mitigation></Mitigations>
          <Related_Weaknesses><Related_Weakness CWE_ID="89"/></Related_Weaknesses>
        </Attack_Pattern>
      </Attack_Patterns>
    </Attack_Pattern_Catalog>"""
    archive_bytes = BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        archive.writestr("capec.xml", xml)

    parsed = list(parse_capec(archive_bytes.getvalue()))
    assert parsed[0]["external_id"] == "CAPEC-66"
    assert parsed[0]["metadata"]["related_weaknesses"] == ["CWE-89"]


def test_parse_reviewed_owasp_cheat_sheets() -> None:
    filenames = ("Authentication_Cheat_Sheet.md", "Input_Validation_Cheat_Sheet.md")
    archive_bytes = BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        archive.writestr(
            "snapshot/cheatsheets/Authentication_Cheat_Sheet.md",
            "# Authentication Cheat Sheet\n\nUse generic error messages.\n",
        )
        archive.writestr(
            "snapshot/cheatsheets/Input_Validation_Cheat_Sheet.md",
            "# Input Validation Cheat Sheet\n\nUse an allowlist.\n",
        )

    parsed = list(parse_owasp(archive_bytes.getvalue(), filenames))

    assert [item["title"] for item in parsed] == [
        "Authentication Cheat Sheet",
        "Input Validation Cheat Sheet",
    ]
    assert parsed[0]["external_id"] == "OWASP-CS-AUTHENTICATION-CHEAT-SHEET"
    assert parsed[0]["metadata"]["license"] == "CC-BY-SA-4.0"
    assert parsed[1]["url"].endswith("/Input_Validation_Cheat_Sheet.html")


def test_parse_owasp_requires_every_reviewed_file() -> None:
    archive_bytes = BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        archive.writestr(
            "snapshot/cheatsheets/Authentication_Cheat_Sheet.md",
            "# Authentication Cheat Sheet\n",
        )
    with pytest.raises(RuntimeError, match="Missing reviewed OWASP cheat sheets"):
        list(
            parse_owasp(
                archive_bytes.getvalue(),
                ("Authentication_Cheat_Sheet.md", "Input_Validation_Cheat_Sheet.md"),
            )
        )


def test_parse_owasp_rejects_duplicate_and_oversized_members() -> None:
    filename = "Authentication_Cheat_Sheet.md"
    duplicate_archive = BytesIO()
    with zipfile.ZipFile(duplicate_archive, "w") as archive:
        archive.writestr(
            f"snapshot-a/cheatsheets/{filename}", "# Authentication Cheat Sheet\n"
        )
        archive.writestr(
            f"snapshot-b/cheatsheets/{filename}", "# Authentication Cheat Sheet\n"
        )
    with pytest.raises(RuntimeError, match="Duplicate OWASP cheat sheet"):
        list(parse_owasp(duplicate_archive.getvalue(), (filename,)))

    oversized_archive = BytesIO()
    with zipfile.ZipFile(oversized_archive, "w") as archive:
        archive.writestr(
            f"snapshot/cheatsheets/{filename}", b"x" * (MAX_OWASP_DOCUMENT_BYTES + 1)
        )
    with pytest.raises(RuntimeError, match="exceeds size limit"):
        list(parse_owasp(oversized_archive.getvalue(), (filename,)))

def test_chunking_is_bounded_and_overlapping() -> None:
    chunks = chunk_text("alpha " * 300, max_chars=240, overlap_chars=30)
    assert len(chunks) > 1
    assert all(len(chunk) <= 240 for chunk in chunks)
    assert chunks[0][-20:] in chunks[1]


def test_hybrid_retrieval_uses_semantic_vectors(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db")
    replace(
        store,
        "attack",
        [
            document("attack:T1110", "T1110 Brute Force", "Password guessing"),
            document("attack:T1566", "T1566 Phishing", "Malicious email delivery"),
        ],
    )
    chunks = store.list_chunks()
    vectors = {
        "attack:T1110": [1.0, 0.0],
        "attack:T1566": [0.0, 1.0],
    }
    store.upsert_embeddings(
        FakeEmbedder.model_name,
        ((chunk["chunk_id"], vectors[chunk["document_id"]]) for chunk in chunks),
    )

    results = retrieve(
        store,
        "deceptive message delivery",
        "defensive",
        limit=1,
        embedder=FakeEmbedder(),
    )
    assert results[0]["external_id"] == "T1566"
    assert "semantic" in results[0]["retrieval_method"]
