# CyberSLM-Crypto

CyberSLM-Crypto is a portable, applied-cryptography language-model project. It complements
[CyberWorkbench](https://github.com/codewithdaniel1) by owning a narrow specialty rather than
duplicating broad security work.

Its job is to help engineers reason about and correctly use established cryptography:

- authenticated encryption, hashes, MACs, signatures, KDFs, key agreement, and randomness;
- secure library/API use and interoperability;
- cryptographic protocol composition and misuse resistance;
- key generation, storage, rotation, backup, and retirement; and
- post-quantum standards and migration planning; and
- cryptography CTFs and educational challenges using supplied or synthetic data.

It is not a general vulnerability auditor, SOC analyst, penetration-testing assistant, forensics
tool, non-cryptography CTF solver, or generic secure-code reviewer. Those requests belong in
CyberWorkbench.

The first model will be named after its base model, for example:

```text
gemma3-4b-cyberslm-crypto
```

## Artifact flow

```text
Reviewed crypto corpus ──► Unsloth / MLX training ──► PEFT Safetensors adapter
                                                           │
                                      ┌────────────────────┴───────────────────┐
                                      ▼                                        ▼
                           merged Safetensors                         quantized GGUF
                                      │                                        │
                         Transformers / Unsloth                     Ollama / llama.cpp

Optional standards bundle ──► external RAG context ──► any runtime
```

Safetensors is the canonical training artifact. GGUF/Ollama and MLX are derived formats; CyberSLM
is not locked to any one runtime. Rapidly changing standards context remains an optional external
RAG bundle rather than being silently baked into weights.

## Current status

- Portable PEFT/Safetensors training and evaluation foundation
- Guarded Unsloth CUDA/Colab runner that records corpus hashes, base revision, packages, settings,
  and metrics
- A fresh crypto scope, model prompt, Ollama definition, and crypto evaluation plan
- No crypto candidate has been trained yet

The former AppSec corpus, CWE/CAPEC export path, AppSec evaluation, and historical evaluation
material are retained only as historical evidence. They must not be used to train or promote a
CyberSLM-Crypto candidate.

## Setup

Install [`uv`](https://docs.astral.sh/uv), then:

```bash
./setup.sh
```

Windows PowerShell:

```powershell
./setup.ps1
```

Install only the inference/training runtime needed for a task:

```bash
uv sync --extra transformers --extra dev  # Transformers / PEFT validation
uv sync --extra mlx --extra train --extra dev  # Apple MLX experiment
```

Use an NVIDIA CUDA machine or Colab for Unsloth. The first experimental crypto-CTF candidate uses
chat-style supervised fine-tuning and produces real LoRA adapter weights:

```bash
uv run cyberslm-unsloth-sft \
  --dataset data/training/crypto-ctf-sft-v0-experimental/corpus.jsonl \
  --manifest data/training/crypto-ctf-sft-v0-experimental/manifest.json \
  --base-revision <UNSLOTH_MODEL_COMMIT_SHA> \
  --confirm-experimental-training \
  --validate-only
```

Follow the complete [Unsloth Colab runbook](docs/unsloth-colab.md). The curriculum is clearly
marked experimental and is not a release corpus. Do not substitute the historical
`appsec-pretraining-v1` corpus or train on the held-out CyberWorkbench scorecard cases.

## Crypto corpus and evaluation

Before training, we will create a narrow, reviewed corpus from sources whose terms allow this use
and from human-reviewed instruction examples. The starting sources are NIST cryptographic
standards and key-management guidance; the exact document versions, terms, hashes, extraction
method, and reviewer approval will be committed in the corpus manifest.

The candidate must beat untouched Gemma 3 4B on the held-out crypto suite, with special attention
to correct primitive selection, nonce/salt/key separation, protocol reasoning, evidence restraint,
and avoiding invented cryptography. See [the specialization contract](docs/crypto-specialization.md)
and [roadmap](docs/roadmap.md).

## Ollama

The checked-in development definition creates the prompt-only baseline:

```bash
ollama pull gemma3:4b
ollama create gemma3-4b-cyberslm-crypto:dev -f ollama/Modelfile.gemma3-4b
ollama run gemma3-4b-cyberslm-crypto:dev
```

After a tracked Modelfile or accepted model-artifact update, republish the local alias with:

```bash
uv run cyberslm-ollama publish-local
```

An accepted release will be converted from the merged Safetensors candidate, not created as an
Ollama-only model. See [the Ollama guide](docs/ollama.md).

## License and safety

Repository code is licensed under [Apache-2.0](LICENSE). Base models and source documents retain
their own terms. A checkpoint is not published until source licensing, evaluation, and artifact
integrity checks pass. Verify cryptographic advice against the relevant standard and library
documentation before production use.
