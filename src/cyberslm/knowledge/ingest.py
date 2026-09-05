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
MAX_OWASP_DOCUMENT_BYTES = 256 * 1024
MAX_OWASP_TOTAL_BYTES = 2 * 1024 * 1024
OWASP_CHEAT_SHEET_FILES = (
    "Authentication_Cheat_Sheet.md",
    "Authorization_Cheat_Sheet.md",
    "Business_Logic_Security_Cheat_Sheet.md",
    "Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.md",
    "Cross_Site_Scripting_Prevention_Cheat_Sheet.md",
    "Cryptographic_Storage_Cheat_Sheet.md",
    "Deserialization_Cheat_Sheet.md",
    "Error_Handling_Cheat_Sheet.md",
    "File_Upload_Cheat_Sheet.md",
    "Forgot_Password_Cheat_Sheet.md",
    "HTTP_Headers_Cheat_Sheet.md",
    "Injection_Prevention_Cheat_Sheet.md",
    "Input_Validation_Cheat_Sheet.md",
    "JSON_Web_Token_Cheat_Sheet.md",
    "Logging_Cheat_Sheet.md",
    "OS_Command_Injection_Defense_Cheat_Sheet.md",
    "Password_Storage_Cheat_Sheet.md",
    "REST_Security_Cheat_Sheet.md",
    "SQL_Injection_Prevention_Cheat_Sheet.md",
    "Secrets_Management_Cheat_Sheet.md",
    "Server_Side_Request_Forgery_Prevention_Cheat_Sheet.md",
    "Session_Management_Cheat_Sheet.md",
    "Transport_Layer_Security_Cheat_Sheet.md",
    "XML_External_Entity_Prevention_Cheat_Sheet.md",
)


def clean_text(value: str) -> str:
    value = html.unescape(value)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def clean_markdown(value: str) -> str:
    """Normalize trusted Markdown into readable, deterministic retrieval text."""
    value = re.sub(r"<!--.*?-->", "", value, flags=re.DOTALL)
    value = re.sub(r"!\[([^]]*)]\([^)]*\)", r"\1", value)
    value = re.sub(r"\[([^]]+)]\([^)]*\)", r"\1", value)
    value = re.sub(r"^\[[^]]+]:\s+\S+.*$", "", value, flags=re.MULTILINE)
    lines: list[str] = []
    for raw_line in value.splitlines():
        line = raw_line.strip()
        if line.startswith("```") or line.startswith("~~~"):
            continue
        line = re.sub(r"^#{1,6}\s+", "", line)
        line = re.sub(r"^>\s?", "", line)
        line = re.sub(r"[*_~`]", "", line)
        line = clean_text(line)
        if line:
            lines.append(line)
        elif lines and lines[-1] != "":
            lines.append("")
    return "\n".join(lines).strip()


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
            "GET", source.url, headers={"User-Agent": "CyberSLM/0.4 knowledge-sync"}
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


def parse_capec(payload: bytes) -> Iterable[dict[str, Any]]:
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        xml_names = [name for name in archive.namelist() if name.lower().endswith(".xml")]
        if len(xml_names) != 1:
            raise RuntimeError("Expected one XML document in the CAPEC archive")
        root = ElementTree.fromstring(archive.read(xml_names[0]))

    namespace_match = re.match(r"\{(.+)}", root.tag)
    namespace = {"capec": namespace_match.group(1)} if namespace_match else {}
    prefix = "capec:" if namespace else ""
    for pattern in root.findall(f".//{prefix}Attack_Pattern", namespace):
        identifier = pattern.get("ID")
        name = pattern.get("Name")
        status = pattern.get("Status", "")
        if not identifier or not name or status.lower() == "deprecated":
            continue
        description = element_text(pattern.find(f"{prefix}Description", namespace))
        execution = element_text(pattern.find(f"{prefix}Execution_Flow", namespace))
        prerequisites = element_text(pattern.find(f"{prefix}Prerequisites", namespace))
        mitigations = element_text(pattern.find(f"{prefix}Mitigations", namespace))
        weaknesses = [
            f"CWE-{item.get('CWE_ID')}"
            for item in pattern.findall(f".//{prefix}Related_Weakness", namespace)
            if item.get("CWE_ID")
        ]
        external_id = f"CAPEC-{identifier}"
        content = "\n".join(
            part
            for part in (
                f"CAPEC ID: {external_id}",
                f"Attack pattern: {name}",
                f"Description: {description}",
                f"Prerequisites: {prerequisites}" if prerequisites else "",
                f"Execution flow: {execution}" if execution else "",
                f"Mitigations: {mitigations}" if mitigations else "",
                f"Related weaknesses: {', '.join(weaknesses)}" if weaknesses else "",
            )
            if part
        )
        yield {
            "id": f"capec:{external_id}",
            "external_id": external_id,
            "title": f"{external_id} — {name}",
            "url": f"https://capec.mitre.org/data/definitions/{identifier}.html",
            "content": content,
            "metadata": {
                "abstraction": pattern.get("Abstraction"),
                "status": status,
                "related_weaknesses": weaknesses,
            },
        }


def parse_owasp(
    payload: bytes,
    filenames: tuple[str, ...] = OWASP_CHEAT_SHEET_FILES,
) -> Iterable[dict[str, Any]]:
    """Parse the reviewed OWASP pilot allowlist from a pinned repository archive."""
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        members: dict[str, zipfile.ZipInfo] = {}
        for info in archive.infolist():
            matching = [
                filename
                for filename in filenames
                if info.filename.endswith(f"/cheatsheets/{filename}")
            ]
            if not matching:
                continue
            filename = matching[0]
            if filename in members:
                raise RuntimeError(f"Duplicate OWASP cheat sheet in archive: {filename}")
            if info.file_size > MAX_OWASP_DOCUMENT_BYTES:
                raise RuntimeError(f"OWASP cheat sheet exceeds size limit: {filename}")
            members[filename] = info

        missing = sorted(set(filenames) - set(members))
        if missing:
            raise RuntimeError(f"Missing reviewed OWASP cheat sheets: {', '.join(missing)}")
        if sum(info.file_size for info in members.values()) > MAX_OWASP_TOTAL_BYTES:
            raise RuntimeError("Reviewed OWASP cheat sheets exceed the total size limit")

        for filename in filenames:
            raw_markdown = archive.read(members[filename]).decode("utf-8-sig")
            heading = re.search(r"^#\s+(.+?)\s*$", raw_markdown, re.MULTILINE)
            if not heading:
                raise RuntimeError(f"OWASP cheat sheet has no title heading: {filename}")
            title = clean_text(heading.group(1))
            content = clean_markdown(raw_markdown)
            if not content:
                raise RuntimeError(f"OWASP cheat sheet has no usable content: {filename}")
            slug = filename.removesuffix(".md")
            external_id = f"OWASP-CS-{slug.replace('_', '-').upper()}"
            yield {
                "id": f"owasp:{slug}",
                "external_id": external_id,
                "title": title,
                "url": f"https://cheatsheetseries.owasp.org/cheatsheets/{slug}.html",
                "content": f"OWASP Cheat Sheet: {title}\n\n{content}",
                "metadata": {
                    "file": f"cheatsheets/{filename}",
                    "license": "CC-BY-SA-4.0",
                    "selection": "reviewed-secure-development-pilot",
                },
            }


PARSERS = {
    "attack": parse_attack,
    "cwe": parse_cwe,
    "capec": parse_capec,
    "owasp": parse_owasp,
}


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
