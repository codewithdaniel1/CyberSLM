# CyberSLM-Crypto training

CyberSLM uses standard local PEFT Safetensors as its canonical adapter format. Training engines
are replaceable: Unsloth is the primary NVIDIA/Colab path, while the existing MLX experiment
remains available for Apple Silicon. Accepted models can then be merged to standard Safetensors
and converted to GGUF for Ollama or llama.cpp. Hugging Face Hub publishing is deferred.

The project now specializes in applied cryptography. The former AppSec CWE/CAPEC export is
historical only and must not be used to train CyberSLM-Crypto.

## Reviewed-data gate

There is no shipped production corpus. Each JSONL record must contain:

- a unique `id`;
- a CyberSLM `mode`;
- `split` set to `train` or `validation`;
- `source` and `license` provenance;
- `approved_for_training: true`;
- `contains_private_data: false`; and
- a `messages` array ending with an assistant response.

The manifest records the reviewer, timestamp, allowed licenses, exact corpus SHA-256, base model,
dataset version, and minimum approved example count.

```bash
uv run cyberslm-train inspect --dataset data/training/corpus.jsonl
uv run cyberslm-train validate \
  --dataset data/training/corpus.jsonl \
  --manifest data/training/manifest.json
```

## Export for Hugging Face and Unsloth

```bash
uv run cyberslm-train export \
  --dataset data/training/corpus.jsonl \
  --manifest data/training/manifest.json \
  --output data/training/huggingface
```

This produces `train.jsonl`, `validation.jsonl`, and `dataset-info.json`. The JSONL files retain
standard chat `messages`, provenance, and review fields. Load them in a manual Unsloth notebook:

```python
from datasets import load_dataset

dataset = load_dataset(
    "json",
    data_files={
        "train": "train.jsonl",
        "validation": "validation.jsonl",
    },
)
```

## Historical AppSec continued-pretraining corpus

The following AppSec exporter is retained so historical results remain reproducible. It is not a
valid input for CyberSLM-Crypto and is separate from ordinary RAG use:

```bash
uv run cyberslm-knowledge verify
uv run cyberslm-train export-pretraining \
  --knowledge-db data/knowledge/knowledge.db \
  --output data/training/appsec-pretraining-v1 \
  --source cwe \
  --source capec \
  --confirm-training-use
```

The command refuses unpinned versions, archive-hash mismatches, incomplete document sets,
unsupported sources, and export without explicit confirmation. It writes deterministic
`train.jsonl` and `validation.jsonl` files with a `text` field plus record-level provenance. The
manifest records source versions, notices, terms links, counts, file sizes, and SHA-256 hashes.
Generated corpus files remain ignored; the exporter and source definitions are tracked so another
developer can reproduce them from the verified archives.

## Reproducible Unsloth run

Run this stage on an NVIDIA CUDA machine or a Colab GPU, not on the local Apple Silicon setup.
Install the repository and Unsloth using its current official Gemma 3 environment. Resolve the
immutable commit for the selected Unsloth mirror before training:

```bash
python -c "from huggingface_hub import model_info; print(model_info('unsloth/gemma-3-4b-it-unsloth-bnb-4bit').sha)"
```

First run the no-GPU preflight. It verifies the corpus sizes, record counts, and SHA-256 hashes
without importing Unsloth or downloading the base model:

```bash
uv run cyberslm-unsloth \
  --manifest data/training/crypto-pretraining-v1/pretraining-manifest.json \
  --base-revision <FULL_COMMIT_SHA> \
  --confirm-reviewed \
  --validate-only
```

Do not run the preflight or training command until a source-reviewed crypto corpus has been
created. Then remove `--validate-only` to run one conservative continued-pretraining epoch:

```bash
uv run cyberslm-unsloth \
  --manifest data/training/crypto-pretraining-v1/pretraining-manifest.json \
  --output data/adapters/gemma3-4b-cyberslm-crypto-cpt-v1 \
  --base-model unsloth/gemma-3-4b-it-unsloth-bnb-4bit \
  --base-revision <FULL_COMMIT_SHA> \
  --epochs 1 \
  --learning-rate 5e-5 \
  --confirm-reviewed
```

The command follows Unsloth's Gemma 3 `FastModel` plus TRL `SFTTrainer` raw-text path. It saves:

```text
data/adapters/gemma3-4b-cyberslm-crypto-cpt-v1/
├── adapter/                  PEFT adapter and tokenizer files
├── checkpoints/              resumable trainer checkpoints
├── merged/                   merged 16-bit Safetensors checkpoint
└── cyberslm-training.json    corpus hash, base revision, arguments, metrics, and versions
```

Use `--skip-merge` if the GPU machine lacks enough disk space; the accepted adapter can be merged
later. Do not change the base revision between training, merging, and evaluation. A completed run
is still only a candidate until it passes the held-out comparison gate.

For a safer first execution, follow the complete [Colab smoke-test runbook](../docs/unsloth-colab.md).
It uses `--max-steps 5` and a separate output directory before starting the full epoch.

The equivalent manual Unsloth save calls are:

```python
# Canonical small local PEFT adapter
model.save_pretrained("gemma3-4b-cyberslm-crypto-adapter")
tokenizer.save_pretrained("gemma3-4b-cyberslm-crypto-adapter")

# Portable merged checkpoint for standard Transformers and later conversion
model.save_pretrained_merged(
    "gemma3-4b-cyberslm-crypto-merged",
    tokenizer,
    save_method="merged_16bit",
)
```

Do not put access tokens in notebooks, manifests, datasets, or repository files. No model upload
is required for the current local workflow.

## Existing MLX experiment

```bash
uv sync --extra mlx --extra train
uv run cyberslm-train run \
  --dataset data/training/corpus.jsonl \
  --manifest data/training/manifest.json \
  --output data/adapters/mlx-candidate \
  --confirm-reviewed
```

MLX output is an engine-specific experimental artifact. It is not the universal release source
unless it is merged and converted into a checkpoint that passes the same cross-runtime tests.

## Promotion gate

An accepted training run must preserve:

- `adapter_config.json` and `adapter_model.safetensors`;
- tokenizer, processor, and chat-template files required by the exact base;
- `cyberslm-training.json` with base revision, dataset hash, engine/package versions, seed, and
  hyperparameters; and
- evaluation reports from the untouched base and candidate on identical held-out cases.

Training loss is not an acceptance metric by itself. The candidate must improve applied-crypto
guidance without weakening factual accuracy, safety, evidence restraint, or grounded RAG.

Primary references:

- [Unsloth Gemma 3 guide and notebooks](https://unsloth.ai/docs/models/gemma-3-how-to-run-and-fine-tune)
- [Unsloth continued-pretraining guide](https://unsloth.ai/docs/basics/continued-pretraining)
- [Hugging Face PEFT quick tour](https://huggingface.co/docs/peft/main/en/quicktour)
