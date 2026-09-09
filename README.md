# CyberSLM-AppSec

CyberSLM-AppSec is a format-neutral project for building compact application-security language
models. Its primary capability is reviewing source code, explaining supported vulnerability
mechanisms and impact, proposing minimal secure fixes, and describing safe verification steps.
Exact framework identifiers such as CWE numbers are optional: the model should include one only
when it is confident or when a trusted retrieved source confirms it.

The naming convention includes the base family and size:

```text
gemma3-4b-cyberslm-appsec
qwen3-4b-cyberslm-appsec
llama3.2-3b-cyberslm-appsec
```

CyberSLM-AppSec is not tied to Ollama. A local standard Safetensors/PEFT checkpoint is the canonical
training artifact; Unsloth and MLX are training paths, while Transformers, MLX, Ollama, and
GGUF-compatible applications are inference or distribution targets. Publishing to the Hugging
Face Hub is deferred.

## Artifact flow

```text
Reviewed chat dataset
        │
        ├── Unsloth training ──┐
        └── MLX training ──────┤
                              ▼
                   local PEFT Safetensors
                              │
                 ┌────────────┴────────────┐
                 ▼                         ▼
        merged Safetensors          quantized GGUF
                 │                         │
          Transformers          Ollama / llama.cpp / UIs

ATT&CK + CWE + CAPEC ── optional external RAG context ──► any runtime
```

RAG is deliberately separate from model weights. Rapidly changing facts remain searchable and
replaceable instead of being baked into a checkpoint.

## Current status

- Reviewed-corpus validation with license, privacy, reviewer, and SHA-256 gates
- Framework-neutral chat JSONL export for Hugging Face datasets and Unsloth
- A guarded Unsloth continued-pretraining command with corpus integrity checks and run metadata
- Existing Apple Silicon MLX LoRA experiment path
- Hugging Face Transformers inference, including local PEFT adapter loading
- Ollama text/image inference and evaluation
- Reproducible quality, safety, false-refusal, retrieval, citation, and human-review tooling
- Local hybrid RAG over pinned MITRE ATT&CK, CWE, and CAPEC releases
- A checked-in Ollama definition for the `gemma3-4b-cyberslm-appsec:dev` development baseline

The tracked Streamlit UI, FastAPI chat server, conversation database, backup utility, and launchers
were removed after v0.5. Historical release notes remain available, but current development is
model-only.

The next milestone is the first reproducible Unsloth run producing a standard PEFT adapter and
merged Hugging Face checkpoint. The Ollama `:dev` model is an untouched baseline, not a fine-tune.

## Setup

Install [`uv`](https://docs.astral.sh/uv/), then:

```bash
./setup.sh
```

Windows PowerShell:

```powershell
./setup.ps1
```

The core installation contains data, RAG, and evaluation tooling. Install only the runtime needed
for a task:

```bash
uv sync --extra transformers --extra dev  # Hugging Face / PEFT
uv sync --extra mlx --extra train --extra dev  # Apple MLX training
```

Unsloth training should use its current official NVIDIA environment or Colab GPU; CyberSLM's
runner validates the reviewed input files before it imports Unsloth. This avoids forcing CUDA-only
packages into every local installation.

## Training data

CyberSLM never turns RAG documents, evaluation answers, conversations, or private uploads into
training examples automatically. Stable CWE/CAPEC documents may be exported only through the
explicit, provenance-preserving continued-pretraining command documented below. Prepare a reviewed
instruction corpus using
[`training/manifest.example.json`](training/manifest.example.json), then run:

```bash
uv run cyberslm-train inspect --dataset data/training/corpus.jsonl
uv run cyberslm-train validate \
  --dataset data/training/corpus.jsonl \
  --manifest data/training/manifest.json
uv run cyberslm-train export \
  --dataset data/training/corpus.jsonl \
  --manifest data/training/manifest.json \
  --output data/training/huggingface
```

The export contains `train.jsonl`, `validation.jsonl`, and `dataset-info.json`. Each example uses a
standard `messages` array suitable for `datasets.load_dataset("json", ...)`, Transformers/TRL, or
manual Unsloth training.

The existing MLX experiment remains available:

```bash
uv run cyberslm-train run \
  --dataset data/training/corpus.jsonl \
  --manifest data/training/manifest.json \
  --output data/adapters/mlx-candidate \
  --confirm-reviewed
```

Export the verified local AppSec raw-text corpus for a manual Unsloth continued-pretraining run:

```bash
uv run cyberslm-train export-pretraining \
  --output data/training/appsec-pretraining-v1 \
  --source cwe --source capec \
  --confirm-training-use
```

This uses existing local snapshots and does not download sources. See
[training/README.md](training/README.md) for the provenance and hash contract.

Validate the exported corpus locally without downloading or loading a model:

```bash
uv run cyberslm-unsloth \
  --base-revision <UNSLOTH_MODEL_COMMIT_SHA> \
  --confirm-reviewed \
  --validate-only
```

On an NVIDIA/Colab environment with Unsloth installed, remove `--validate-only` to train the PEFT
adapter and merged Safetensors checkpoint. The runner writes `cyberslm-training.json` with the
exact base revision, corpus manifest hash, hyperparameters, metrics, and package versions. It does
not upload anything.

Follow [the Colab GPU runbook](docs/unsloth-colab.md) for the five-step smoke train and first full
candidate run. The smoke output and full candidate use separate directories to avoid accidentally
promoting a partial training run.

See [training/README.md](training/README.md) for the artifact contract and promotion gates.

## Safetensors and PEFT

The target local canonical adapter contains at least:

```text
adapter_config.json
adapter_model.safetensors
tokenizer and chat-template files
cyberslm-training.json
```

Set the exact base and adapter when evaluating locally:

```dotenv
CYBERSLM_MODEL_BACKEND=transformers
CYBERSLM_MODEL_ID=google/gemma-3-4b-it
CYBERSLM_ADAPTER_PATH=data/adapters/gemma3-4b-cyberslm-appsec
```

```bash
uv run cyberslm-eval run --backend transformers --rag-policy off --temperature 0
```

Hub publishing is not part of the current milestone. The adapter and merged model remain local,
with hashes and metadata sufficient to reproduce and audit them.

## Distribution goal

The first public CyberSLM-AppSec release will use this GitHub repository as its source of truth.
Git tracks the training/evaluation code, release metadata, notices, and SHA-256 manifests. A
versioned GitHub Release will carry the generated PEFT adapter, sharded merged Safetensors,
quantized GGUF package, and exact reconstruction instructions. Model binaries remain ignored in
normal repository history so cloning the source does not download many gigabytes unexpectedly.

The release must support two independent paths:

- Unsloth/Transformers users download the adapter or merged Safetensors checkpoint.
- Ollama users download and reconstruct the GGUF, then create the named model with the included
  Modelfile.

GitHub release assets must each remain below 2 GiB, so larger checkpoints and GGUF packages will
be split deterministically and verified after reconstruction.

## Ollama and GGUF

Build the untouched development baseline:

```bash
ollama pull gemma3:4b
ollama create gemma3-4b-cyberslm-appsec:dev -f ollama/Modelfile.gemma3-4b
ollama run gemma3-4b-cyberslm-appsec:dev
```

Evaluate it through the same harness:

```bash
uv run cyberslm-eval run \
  --backend ollama \
  --model gemma3-4b-cyberslm-appsec:dev \
  --dataset evals/datasets/smoke.jsonl \
  --rag-policy off \
  --temperature 0
```

See [docs/ollama.md](docs/ollama.md). A released Ollama model will be derived from the accepted
merged checkpoint rather than trained as an Ollama-only artifact.

## RAG knowledge

`ollama run gemma3-4b-cyberslm-appsec:<version>` alone does **not** perform RAG. Ollama loads the model;
a retrieval client must search the knowledge index and add relevant passages to each prompt.
CyberSLM will ship its RAG material as a separate, hashed companion bundle that can be connected
to the Ollama model without changing its weights.

```bash
uv run cyberslm-knowledge sync
uv run cyberslm-knowledge verify
uv run cyberslm-knowledge search "CWE-89 SQL injection" --mode secure_code --json
```

Generated downloads, indexes, embeddings, corpora, adapters, and evaluation reports stay outside
Git. Their definitions, hashes, manifests, and evaluators are committed so they can be rebuilt.
See [docs/knowledge.md](docs/knowledge.md).

## Evaluation

```bash
uv run cyberslm-eval validate
uv run cyberslm-eval run --backend ollama --model gemma3-4b-cyberslm-appsec:dev --rag-policy off
uv run cyberslm-eval run --backend ollama --model gemma3-4b-cyberslm-appsec:dev --rag-policy auto
uv run cyberslm-eval compare BASELINE.json CANDIDATE.json
```

No adapter is promoted merely because training loss improved. It must beat the untouched base on
held-out answer quality without weakening safety, appropriate refusal, source attribution, or RAG
behavior.

AppSec candidates are also compared with Foundation-Sec-8B-Instruct. The preliminary three-way
baseline and the rule for switching training bases are recorded in
[docs/appsec-model-comparison.md](docs/appsec-model-comparison.md).

## Repository layout

```text
src/cyberslm/training/    corpus gates and training commands
src/cyberslm/evaluation/  model and RAG evaluation harness
src/cyberslm/knowledge/   pinned-source ingestion and retrieval
src/cyberslm/model.py     Transformers, MLX, Ollama, and mock evaluation runtimes
training/                 manifests and engine guidance
ollama/                   derived Ollama model definitions
evals/                    committed datasets; local results are ignored
data/                     ignored local knowledge and training artifacts
```

See the [project roadmap](docs/roadmap.md). The former application remains recoverable from the
[`v0.5.0a1` release](https://github.com/codewithdaniel1/CyberSLM/releases/tag/v0.5.0a1).

## License and safety

Repository code is licensed under [Apache-2.0](LICENSE). Base models, training datasets, and RAG
sources retain their own terms. Publishing a checkpoint requires a separate license review.

CyberSLM is an analyst aid. Verify generated guidance and code before use, and restrict offensive
work to systems you own or are explicitly authorized to test.
