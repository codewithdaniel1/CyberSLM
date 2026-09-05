from __future__ import annotations

import json
import os
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from cyberslm.knowledge.chunking import chunk_text
from cyberslm.knowledge.embeddings import DEFAULT_EMBEDDING_MODEL
from cyberslm.knowledge.ingest import parse_attack, parse_capec, parse_cwe, verify_payload
from cyberslm.knowledge.retrieve import decide_retrieval, expanded_query, retrieve
from cyberslm.knowledge.sources import KnowledgeSource
from cyberslm.knowledge.store import KnowledgeStore


class FakeEmbedder:
    model_name = "test-embedding"

    def embed_query(self, query: str) -> list[float]:
        del query
        return [0.0, 1.0]


def test_embedding_runtime_disables_telemetry() -> None:
    assert DEFAULT_EMBEDDING_MODEL
    assert os.environ["ORT_DISABLE_TELEMETRY"] == "1"


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

    assert decide_retrieval("Explain T1110", "general", "off").reason == "disabled_for_message"
    assert decide_retrieval("Hello", "general", "on").reason == "forced_for_message"
    assert not decide_retrieval("Explain T1110", "general", enabled=False).should_retrieve
    with pytest.raises(ValueError, match="auto, on, off"):
        decide_retrieval("Hello", "general", "sometimes")


def test_exact_identifier_lookup_ignores_mode_source_routing(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "knowledge.db")
    replace(
        store,
        "attack",
        [document("attack:T1110", "T1110 Brute Force", "Failed password guessing")],
    )

    results = retrieve(store, "Explain T1110", "secure_code", source_keys=("cwe",))
    assert results[0]["external_id"] == "T1110"


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
