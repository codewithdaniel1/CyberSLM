from __future__ import annotations

import json
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from cyberslm.knowledge.ingest import parse_attack, parse_cwe, verify_payload
from cyberslm.knowledge.retrieve import expanded_query, retrieve
from cyberslm.knowledge.sources import KnowledgeSource
from cyberslm.knowledge.store import KnowledgeStore


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
        [document("cwe:CWE-89", "CWE-89 SQL Injection", "Parameterized SQL queries")],
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
    defensive_results = retrieve(store, "Investigate failed SSH logins", "defensive")
    assert [item["external_id"] for item in defensive_results] == ["T1110"]


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
