from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class KnowledgeSource:
    key: str
    name: str
    version: str
    url: str
    filename: str
    notice: str


SOURCES: dict[str, KnowledgeSource] = {
    "attack": KnowledgeSource(
        key="attack",
        name="MITRE Enterprise ATT&CK",
        version="19.1",
        url=(
            "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/"
            "master/enterprise-attack/enterprise-attack-19.1.json"
        ),
        filename="enterprise-attack-19.1.json",
        notice=(
            "© 2026 The MITRE Corporation. This work is reproduced and distributed "
            "with the permission of The MITRE Corporation."
        ),
    ),
    "cwe": KnowledgeSource(
        key="cwe",
        name="Common Weakness Enumeration",
        version="4.20",
        url="https://cwe.mitre.org/data/xml/cwec_v4.20.xml.zip",
        filename="cwec_v4.20.xml.zip",
        notice=(
            "© 2006-2026 The MITRE Corporation. CWE is reproduced and distributed "
            "under the CWE Terms of Use."
        ),
    ),
}
