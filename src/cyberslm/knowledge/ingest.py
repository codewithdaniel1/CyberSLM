from __future__ import annotations

import hashlib
import hmac
import html
import json
import re
import zipfile
from collections.abc import Iterable
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import httpx

from cyberslm.knowledge.sources import KnowledgeSource
from cyberslm.knowledge.store import KnowledgeStore

MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024


def clean_text(value: str) -> str:
    value = html.unescape(value)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def verify_payload(source: KnowledgeSource, payload: bytes) -> str:
    digest = hashlib.sha256(payload).hexdigest()
    if not hmac.compare_digest(digest, source.sha256):
        raise RuntimeError(
            f"SHA-256 mismatch for {source.name} {source.version}: "
            f"expected {source.sha256}, received {digest}. The local index was not changed."
        )
    return digest


def download_source(source: KnowledgeSource, destination: Path) -> tuple[bytes, str]:
    with (
        httpx.Client(follow_redirects=True, timeout=120) as client,
        client.stream(
            "GET", source.url, headers={"User-Agent": "CyberSLM/0.3 knowledge-sync"}
        ) as response,
    ):
        response.raise_for_status()
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > MAX_DOWNLOAD_BYTES:
                raise RuntimeError(f"Source exceeds {MAX_DOWNLOAD_BYTES} bytes: {source.url}")
            chunks.append(chunk)
    payload = b"".join(chunks)
    digest = verify_payload(source, payload)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return payload, digest


def external_reference(value: dict[str, Any], source_name: str) -> dict[str, str] | None:
    return next(
        (
            reference
            for reference in value.get("external_references", [])
            if reference.get("source_name") == source_name and reference.get("external_id")
        ),
        None,
    )


def parse_attack(payload: bytes) -> Iterable[dict[str, Any]]:
    bundle = json.loads(payload)
    for value in bundle.get("objects", []):
        if value.get("type") != "attack-pattern":
            continue
        if value.get("revoked") or value.get("x_mitre_deprecated"):
            continue
        reference = external_reference(value, "mitre-attack")
        if not reference:
            continue
        external_id = reference["external_id"]
        name = value.get("name", external_id)
        tactics = [item.get("phase_name", "") for item in value.get("kill_chain_phases", [])]
        platforms = value.get("x_mitre_platforms", [])
        parts = [
            f"ATT&CK ID: {external_id}",
            f"Technique: {name}",
            f"Description: {clean_text(value.get('description', ''))}",
        ]
        if tactics:
            parts.append(f"Tactics: {', '.join(tactics)}")
        if platforms:
            parts.append(f"Platforms: {', '.join(platforms)}")
        yield {
            "id": f"attack:{external_id}",
            "external_id": external_id,
            "title": f"{external_id} — {name}",
            "url": reference.get("url", f"https://attack.mitre.org/techniques/{external_id}/"),
            "content": "\n".join(parts),
            "metadata": {"tactics": tactics, "platforms": platforms},
        }


def element_text(element: ElementTree.Element | None) -> str:
    if element is None:
        return ""
    return clean_text(" ".join(element.itertext()))


def parse_cwe(payload: bytes) -> Iterable[dict[str, Any]]:
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        xml_names = [name for name in archive.namelist() if name.lower().endswith(".xml")]
        if len(xml_names) != 1:
            raise RuntimeError("Expected one XML document in the CWE archive")
        root = ElementTree.fromstring(archive.read(xml_names[0]))

    namespace_match = re.match(r"\{(.+)}", root.tag)
    namespace = {"cwe": namespace_match.group(1)} if namespace_match else {}
    prefix = "cwe:" if namespace else ""
    for weakness in root.findall(f".//{prefix}Weakness", namespace):
        identifier = weakness.get("ID")
        name = weakness.get("Name")
        status = weakness.get("Status", "")
        if not identifier or not name or status.lower() == "deprecated":
            continue
        description = element_text(weakness.find(f"{prefix}Description", namespace))
        extended = element_text(weakness.find(f"{prefix}Extended_Description", namespace))
        consequences = element_text(weakness.find(f"{prefix}Common_Consequences", namespace))
        mitigations = element_text(weakness.find(f"{prefix}Potential_Mitigations", namespace))
        external_id = f"CWE-{identifier}"
        content = "\n".join(
            part
            for part in (
                f"CWE ID: {external_id}",
                f"Weakness: {name}",
                f"Description: {description}",
                f"Extended description: {extended}" if extended else "",
                f"Common consequences: {consequences}" if consequences else "",
                f"Potential mitigations: {mitigations}" if mitigations else "",
            )
            if part
        )
        yield {
            "id": f"cwe:{external_id}",
            "external_id": external_id,
            "title": f"{external_id} — {name}",
            "url": f"https://cwe.mitre.org/data/definitions/{identifier}.html",
            "content": content,
            "metadata": {"abstraction": weakness.get("Abstraction"), "status": status},
        }


PARSERS = {"attack": parse_attack, "cwe": parse_cwe}


def sync_source(store: KnowledgeStore, source: KnowledgeSource, source_dir: Path) -> int:
    destination = source_dir / source.filename
    payload, digest = download_source(source, destination)
    documents = list(PARSERS[source.key](payload))
    if len(documents) != source.document_count:
        raise RuntimeError(
            f"Document-count mismatch for {source.name} {source.version}: "
            f"expected {source.document_count}, parsed {len(documents)}. "
            "The local index was not changed."
        )
    return store.replace_source(
        source_key=source.key,
        source_name=source.name,
        source_version=source.version,
        source_url=source.url,
        source_sha256=digest,
        notice=source.notice,
        documents=documents,
    )
