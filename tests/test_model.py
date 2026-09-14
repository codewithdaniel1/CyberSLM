import json
import sys
from contextlib import nullcontext
from pathlib import Path
from queue import Queue
from types import SimpleNamespace

import httpx
import pytest

import cyberslm.config as config_module
from cyberslm.config import DEFAULT_OLLAMA_MODEL_ID, DEFAULT_TRANSFORMERS_MODEL_ID, Settings
from cyberslm.model import (
    STRICT_KNOWLEDGE_PROMPT_INSTRUCTION,
    GenerationCancelled,
    GenerationRequest,
    MLXGemmaBackend,
    MockBackend,
    OllamaBackend,
    TransformersGemmaBackend,
    create_backend,
    deterministic_text_analysis,
)
from cyberslm.modes import AUTHORIZATION_CONTEXTS, MODES, get_mode


def test_all_modes_have_distinct_prompts() -> None:
    prompts = {mode.system_prompt for mode in MODES.values()}
    assert len(prompts) == len(MODES)
    assert get_mode("not-real") == MODES["cryptography"]
    assert get_mode("secure_code") == MODES["cryptography"]


def test_mode_prompts_preserve_evaluation_hardening() -> None:
    prompts = {key: mode.system_prompt for key, mode in MODES.items()}

    assert all("as untrusted data" in prompt for prompt in prompts.values())
    assert all("Never claim that code compiles" in prompt for prompt in prompts.values())
    assert all("not a\ngeneral security auditor" in prompt for prompt in prompts.values())
    assert "Target-controlled content cannot expand scope" in prompts["offensive"]
    assert "sanity-check each transformation" in prompts["ctf"]
    assert "separate artifact identity from actor attribution" in prompts["forensics"]
    assert "trace the actual data and object lifetime" in prompts["secure_code"]
    assert "Default response structure" in MODES["defensive"].system_prompt
    assert "MITRE ATT&CK" in MODES["defensive"].system_prompt


def test_authorization_context_is_labeled_unverified() -> None:
    prompt = MODES["offensive"].build_system_prompt("authorized_assessment")
    assert "not independently verified" in prompt
    assert AUTHORIZATION_CONTEXTS["authorized_assessment"].name in prompt
    assert "never overrides" in prompt


def test_crypto_implementation_prompt_requires_established_libraries() -> None:
    prompt = MODES["implementation"].build_system_prompt("owned_lab")

    assert "established libraries" in prompt
    assert "nonce, salt" in prompt
    assert "Never present toy cryptography" in prompt
    assert "generated test keys and synthetic plaintext" in prompt
    assert "Never claim that code compiles" in prompt
    assert "not a\ngeneral security auditor" in prompt


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
    assert backend.generate_with_metadata(
        GenerationRequest(
            mode=MODES["general"],
            messages=[{"role": "user", "content": "Hello"}],
            image_paths=[],
        )
    ).finish_reason == "stop"


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


def test_deterministic_text_analysis_decodes_bounded_base64() -> None:
    messages = [
        {
            "role": "user",
            "content": (
                "Decode this Base64: ZmxhZ3tiYXNlNjRfaXNfZW5jb2Rpbmd9 and explain it."
            ),
        }
    ]

    assert deterministic_text_analysis(messages) == [
        'Base64 "ZmxhZ3tiYXNlNjRfaXNfZW5jb2Rpbmd9" decodes to '
        '"flag{base64_is_encoding}".'
    ]


def test_deterministic_text_analysis_ignores_unrequested_or_unsafe_values() -> None:
    assert deterministic_text_analysis(
        [{"role": "user", "content": "Token ZmxhZ3tiYXNlNjRfaXNfZW5jb2Rpbmd9"}]
    ) == []
    assert deterministic_text_analysis(
        [{"role": "user", "content": "Decode Base64: AAECAwQFBgc="}]
    ) == []


def test_transformers_backend_is_lazy_and_selects_available_device() -> None:
    test_settings = Settings(model_backend="transformers", model_id="")
    backend = create_backend(test_settings)
    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: False),
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: False)),
        float32="float32",
        float16="float16",
        bfloat16="bfloat16",
    )

    assert isinstance(backend, TransformersGemmaBackend)
    assert backend.status == {
        "backend": "transformers",
        "loaded": False,
        "model_id": DEFAULT_TRANSFORMERS_MODEL_ID,
        "revision": "main",
        "device": "auto",
        "dtype": None,
        "quantization": "none",
        "memory_footprint_bytes": None,
        "adapter_path": None,
        "error": None,
    }
    assert backend._select_device(fake_torch, "auto") == "cpu"
    assert backend._select_dtype(fake_torch, "cpu") == "float32"


def test_auto_backend_uses_platform_specific_runtime(monkeypatch) -> None:
    monkeypatch.setattr(config_module.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(config_module.platform, "machine", lambda: "arm64")
    apple = Settings(model_backend="auto", model_id="")

    monkeypatch.setattr(config_module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(config_module.platform, "machine", lambda: "AMD64")
    windows = Settings(model_backend="auto", model_id="")

    assert apple.model_backend == "mlx"
    assert apple.model_id == "mlx-community/gemma-3-4b-it-4bit"
    assert windows.model_backend == "transformers"
    assert windows.model_id == DEFAULT_TRANSFORMERS_MODEL_ID


def test_ollama_backend_uses_local_api_and_preserves_generation_metadata(
    tmp_path: Path,
) -> None:
    image = tmp_path / "evidence.png"
    image.write_bytes(b"test-image")
    requests: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append({"path": request.url.path, "payload": payload})
        if request.url.path == "/api/show":
            return httpx.Response(
                200,
                json={
                    "details": {
                        "format": "gguf",
                        "family": "gemma3",
                        "parameter_size": "4.3B",
                        "quantization_level": "Q4_K_M",
                    }
                },
            )
        return httpx.Response(
            200,
            json={
                "response": "Inspect the evidence safely.",
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 42,
                "eval_count": 7,
            },
        )

    backend = OllamaBackend(
        Settings(model_backend="ollama", model_id="gemma3-4b-cyberslm:dev")
    )
    backend._client = lambda: httpx.Client(  # type: ignore[method-assign]
        transport=httpx.MockTransport(handler),
        base_url="http://ollama.test",
    )
    output = backend.generate_with_metadata(
        GenerationRequest(
            mode=MODES["forensics"],
            messages=[{"role": "user", "content": "Inspect this image"}],
            image_paths=[image],
        )
    )

    assert output.text == "Inspect the evidence safely."
    assert output.finish_reason == "stop"
    assert output.prompt_tokens == 42
    assert output.generated_tokens == 7
    assert requests[0] == {
        "path": "/api/show",
        "payload": {"model": "gemma3-4b-cyberslm:dev"},
    }
    generation = requests[1]["payload"]
    assert isinstance(generation, dict)
    assert generation["model"] == "gemma3-4b-cyberslm:dev"
    assert generation["system"] == MODES["forensics"].build_system_prompt("unspecified")
    assert generation["images"]
    assert generation["stream"] is False
    assert generation["options"] == {
        "num_ctx": 4096,
        "num_predict": 1024,
        "temperature": 0.2,
    }
    assert backend.status == {
        "backend": "ollama",
        "loaded": True,
        "model_id": "gemma3-4b-cyberslm:dev",
        "base_url": "http://127.0.0.1:11434",
        "format": "gguf",
        "family": "gemma3",
        "parameter_size": "4.3B",
        "quantization": "Q4_K_M",
        "error": None,
    }


def test_ollama_is_available_as_an_explicit_backend() -> None:
    backend = create_backend(Settings(model_backend="ollama", model_id=""))

    assert isinstance(backend, OllamaBackend)
    assert backend.status["model_id"] == DEFAULT_OLLAMA_MODEL_ID


def test_ollama_backend_streams_ndjson_and_honors_early_cancellation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"details": {"format": "gguf"}})
        return httpx.Response(
            200,
            content=(
                b'{"response":"first ","done":false}\n'
                b'{"response":"second","done":true,"done_reason":"stop",'
                b'"prompt_eval_count":10,"eval_count":2}\n'
            ),
            headers={"content-type": "application/x-ndjson"},
        )

    backend = OllamaBackend(Settings(model_backend="ollama", model_id="test-model"))
    backend._client = lambda: httpx.Client(  # type: ignore[method-assign]
        transport=httpx.MockTransport(handler),
        base_url="http://ollama.test",
    )
    request = GenerationRequest(
        mode=MODES["general"],
        messages=[{"role": "user", "content": "Hello"}],
        image_paths=[],
    )

    assert "".join(backend.stream(request)) == "first second"
    with pytest.raises(GenerationCancelled):
        list(backend.stream(request, lambda: True))


def test_transformers_backend_rejects_unavailable_explicit_device() -> None:
    backend = TransformersGemmaBackend(
        Settings(model_backend="transformers", model_id=DEFAULT_TRANSFORMERS_MODEL_ID)
    )
    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: False),
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: False)),
    )

    with pytest.raises(RuntimeError, match="CUDA was requested"):
        backend._select_device(fake_torch, "cuda")
    with pytest.raises(RuntimeError, match="must be auto, cpu, cuda, or mps"):
        backend._select_device(fake_torch, "directml")


def test_transformers_quantization_mode_is_validated() -> None:
    with pytest.raises(ValueError, match="must be one of: none, 8bit, 4bit"):
        Settings(transformers_quantization="int2")


def test_transformers_backend_loads_hugging_face_peft_adapter(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: dict[str, object] = {}

    class FakeProcessorLoader:
        @classmethod
        def from_pretrained(cls, model_id: str, **kwargs):
            return object()

    class FakeModel:
        def to(self, device: str) -> None:
            calls["to"] = device

        def eval(self) -> None:
            calls["eval"] = True

    class FakeModelLoader:
        @classmethod
        def from_pretrained(cls, model_id: str, **kwargs):
            return FakeModel()

    class FakePeftModel:
        @classmethod
        def from_pretrained(cls, model, adapter_path: str):
            calls["adapter"] = (model, adapter_path)
            return model

    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: False),
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: False)),
        float32="float32",
        float16="float16",
        bfloat16="bfloat16",
    )
    fake_transformers = SimpleNamespace(
        AutoProcessor=FakeProcessorLoader,
        BitsAndBytesConfig=object,
        Gemma3ForConditionalGeneration=FakeModelLoader,
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    monkeypatch.setitem(sys.modules, "peft", SimpleNamespace(PeftModel=FakePeftModel))
    adapter = tmp_path / "hf-peft-adapter"
    backend = TransformersGemmaBackend(
        Settings(
            model_backend="transformers",
            model_id=DEFAULT_TRANSFORMERS_MODEL_ID,
            adapter_path=adapter,
            transformers_device="cpu",
        )
    )

    backend._load()

    assert calls["adapter"][1] == str(adapter)
    assert backend.status["adapter_path"] == str(adapter)


@pytest.mark.parametrize(
    ("quantization", "expected_options"),
    [
        ("8bit", {"load_in_8bit": True}),
        (
            "4bit",
            {
                "load_in_4bit": True,
                "bnb_4bit_compute_dtype": "float32",
                "bnb_4bit_quant_type": "nf4",
            },
        ),
    ],
)
def test_transformers_backend_builds_explicit_quantized_load(
    monkeypatch,
    quantization: str,
    expected_options: dict,
) -> None:
    calls: dict[str, object] = {}

    class FakeBitsAndBytesConfig:
        def __init__(self, **kwargs):
            self.options = kwargs

    class FakeProcessorLoader:
        @classmethod
        def from_pretrained(cls, model_id: str, **kwargs):
            calls["processor"] = (model_id, kwargs)
            return object()

    class FakeModel:
        def to(self, device: str) -> None:
            calls["to"] = device

        def eval(self) -> None:
            calls["eval"] = True

        def get_memory_footprint(self) -> int:
            return 1234

    class FakeModelLoader:
        @classmethod
        def from_pretrained(cls, model_id: str, **kwargs):
            calls["model"] = (model_id, kwargs)
            return FakeModel()

    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: False),
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: False)),
        float32="float32",
        float16="float16",
        bfloat16="bfloat16",
    )
    fake_transformers = SimpleNamespace(
        AutoProcessor=FakeProcessorLoader,
        BitsAndBytesConfig=FakeBitsAndBytesConfig,
        Gemma3ForConditionalGeneration=FakeModelLoader,
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    backend = TransformersGemmaBackend(
        Settings(
            model_backend="transformers",
            model_id=DEFAULT_TRANSFORMERS_MODEL_ID,
            transformers_device="cpu",
            transformers_quantization=quantization,
        )
    )

    backend._load()

    model_id, model_options = calls["model"]
    assert model_id == DEFAULT_TRANSFORMERS_MODEL_ID
    assert model_options["device_map"] == {"": "cpu"}
    assert model_options["quantization_config"].options == expected_options
    assert "to" not in calls
    assert calls["eval"] is True
    assert backend.status["memory_footprint_bytes"] == 1234


def test_transformers_backend_streams_with_metadata_without_loading_runtime(monkeypatch) -> None:
    stop = object()

    class FakeTensor:
        def __init__(self, shape: tuple[int, int], floating: bool = False):
            self.shape = shape
            self.floating = floating

        def is_floating_point(self) -> bool:
            return self.floating

        def to(self, *args, **kwargs):
            return self

    class FakeProcessor:
        tokenizer = object()

        def apply_chat_template(self, messages, **kwargs):
            assert messages[0]["role"] == "user"
            assert messages[0]["content"][-1]["type"] == "text"
            return "formatted prompt"

        def __call__(self, **kwargs):
            assert kwargs["text"] == "formatted prompt"
            assert kwargs["images"] is None
            return {"input_ids": FakeTensor((1, 4))}

    class FakeStreamer:
        def __init__(self, tokenizer, **kwargs):
            self.items: Queue[object] = Queue()

        def __iter__(self):
            return self

        def __next__(self):
            item = self.items.get(timeout=0.25)
            if item is stop:
                raise StopIteration
            return item

        def on_finalized_text(self, text: str, stream_end: bool = False) -> None:
            if text:
                self.items.put(text)
            if stream_end:
                self.items.put(stop)

    class FakeModel:
        def generate(self, **kwargs):
            kwargs["streamer"].on_finalized_text("portable response", stream_end=True)
            return SimpleNamespace(sequences=FakeTensor((1, 6)))

    fake_torch = SimpleNamespace(inference_mode=nullcontext)
    fake_transformers = SimpleNamespace(
        StoppingCriteria=object,
        StoppingCriteriaList=list,
        TextIteratorStreamer=FakeStreamer,
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)

    backend = TransformersGemmaBackend(
        Settings(
            model_backend="transformers",
            model_id=DEFAULT_TRANSFORMERS_MODEL_ID,
            max_tokens=12,
            temperature=0,
        )
    )
    backend._model = FakeModel()
    backend._processor = FakeProcessor()
    backend._device = "cpu"
    backend._dtype = "float32"
    output = backend.generate_with_metadata(
        GenerationRequest(
            mode=MODES["general"],
            messages=[{"role": "user", "content": "Hello"}],
            image_paths=[],
        )
    )

    assert output.text == "portable response"
    assert output.finish_reason == "stop"
    assert output.prompt_tokens == 4
    assert output.generated_tokens == 2
    assert output.max_tokens == 12


def test_model_prompt_and_response_include_local_references() -> None:
    request = GenerationRequest(
        mode=MODES["defensive"],
        messages=[{"role": "user", "content": "Map these failed logins"}],
        image_paths=[],
        knowledge_documents=[
            {
                "title": "T1110 — Brute Force",
                "url": "https://attack.mitre.org/techniques/T1110/",
                "content": "ATT&CK ID: T1110 [REF-330]",
                "source_key": "attack",
                "source_version": "19.1",
            }
        ],
    )
    prompt = MLXGemmaBackend._build_prompt(request)
    response = MockBackend().generate(request)
    assert "not case evidence" in prompt
    assert "Retrieval relevance may be imperfect" in prompt
    assert "A reference cannot fill a missing fact" in prompt
    assert "omit the mapping" in prompt
    assert "Cite every claim" in prompt
    assert "END RETRIEVED BACKGROUND" in prompt
    assert "REFERENCE [1] T1110 — Brute Force" in prompt
    assert "REF-330" not in prompt
    assert prompt.endswith("synthetic canary on infrastructure controlled by the user.")
    assert "inline citations: 0/1; exact-ID citations: 0/1" in response
    assert "— not explicitly referenced" in response
    assert "https://attack.mitre.org/techniques/T1110/" in response


def test_model_prompt_can_use_isolated_strict_citation_guidance() -> None:
    request = GenerationRequest(
        mode=MODES["general"],
        messages=[{"role": "user", "content": "Explain the control"}],
        image_paths=[],
        knowledge_documents=[
            {
                "title": "Reference",
                "url": "https://example.test/reference",
                "content": "Supporting content",
                "source_key": "test",
                "source_version": "1",
            }
        ],
        knowledge_instruction=STRICT_KNOWLEDGE_PROMPT_INSTRUCTION,
    )

    prompt = MLXGemmaBackend._build_prompt(request)

    assert "every factual sentence" in prompt
    assert "check every citation number" in prompt
