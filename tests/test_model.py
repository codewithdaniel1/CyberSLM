from pathlib import Path

from cyberslm.model import GenerationRequest, MockBackend
from cyberslm.modes import MODES, get_mode


def test_all_modes_have_distinct_prompts() -> None:
    prompts = {mode.system_prompt for mode in MODES.values()}
    assert len(prompts) == len(MODES)
    assert get_mode("not-real") == MODES["general"]


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
