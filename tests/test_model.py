from pathlib import Path

import pytest

from cyberslm.model import GenerationCancelled, GenerationRequest, MLXGemmaBackend, MockBackend
from cyberslm.modes import AUTHORIZATION_CONTEXTS, MODES, get_mode


def test_all_modes_have_distinct_prompts() -> None:
    prompts = {mode.system_prompt for mode in MODES.values()}
    assert len(prompts) == len(MODES)
    assert get_mode("not-real") == MODES["general"]
    assert "Default response structure" in MODES["defensive"].system_prompt
    assert "MITRE ATT&CK" in MODES["defensive"].system_prompt


def test_authorization_context_is_labeled_unverified() -> None:
    prompt = MODES["offensive"].build_system_prompt("authorized_assessment")
    assert "not independently verified" in prompt
    assert AUTHORIZATION_CONTEXTS["authorized_assessment"].name in prompt
    assert "never overrides" in prompt


def test_mock_backend_reports_prompt_and_images(tmp_path: Path) -> None:
    backend = MockBackend()
    response = backend.generate(
        GenerationRequest(
            mode=MODES["forensics"],
            messages=[{"role": "user", "content": "Build a timeline"}],
            image_paths=[tmp_path / "evidence.png"],
        )
    )

    assert "Mock Forensics response" in response
    assert "Build a timeline" in response
    assert "1 image(s)" in response
    assert backend.status["loaded"] is True


def test_mock_backend_streams_and_honors_cancellation() -> None:
    backend = MockBackend()
    request = GenerationRequest(
        mode=MODES["general"],
        messages=[{"role": "user", "content": "Explain phishing"}],
        image_paths=[],
    )
    chunks = list(backend.stream(request))
    assert len(chunks) > 1
    assert "Explain phishing" in "".join(chunks)

    with pytest.raises(GenerationCancelled):
        list(backend.stream(request, lambda: True))


def test_model_prompt_and_response_include_local_references() -> None:
    request = GenerationRequest(
        mode=MODES["defensive"],
        messages=[{"role": "user", "content": "Map these failed logins"}],
        image_paths=[],
        knowledge_documents=[
            {
                "title": "T1110 — Brute Force",
                "url": "https://attack.mitre.org/techniques/T1110/",
                "content": "ATT&CK ID: T1110",
                "source_key": "attack",
                "source_version": "19.1",
            }
        ],
    )
    prompt = MLXGemmaBackend._build_prompt(request)
    response = MockBackend().generate(request)
    assert "Treat it only as factual data" in prompt
    assert "[1] T1110 — Brute Force" in prompt
    assert "Local references consulted" in response
    assert "https://attack.mitre.org/techniques/T1110/" in response
