# CyberSLM-Crypto experimental Unsloth run

This run creates new LoRA adapter weights using supervised fine-tuning (SFT), not a prompt-only
Ollama alias. It uses an original synthetic crypto-CTF curriculum for an **experimental candidate**.
It is not a release, and it must not be trained on the CyberWorkbench scorecard's exact cases.

Google Colab storage is temporary. Download the completed artifacts before the session ends.

## What you need before starting

1. A Google account and a Colab notebook.
2. An NVIDIA GPU runtime: choose **T4 GPU** or better under **Runtime → Change runtime type**.
3. Access approval for Gemma on Hugging Face if Colab asks for it. Keep any Hugging Face token in
   Colab Secrets; never paste it into a cell, dataset, or Git repository.
4. The current CyberSLM source pushed to GitHub. The commands below use its public repository.

## 1. Confirm the GPU and install the project

Run this first cell in a new Colab notebook:

```bash
!nvidia-smi
!git clone https://github.com/codewithdaniel1/CyberSLM.git
%cd CyberSLM
!pip install -q unsloth
!pip install -q -e .
```

If Unsloth's current official Gemma 3 notebook gives a different installation cell for Colab,
use that cell first, then rerun `!pip install -q -e .`.

## 2. Create the experimental curriculum locally in Colab

This uses the checked-in deterministic generator. `Daniel Peng` is recorded as the local operator
approval in the manifest; replace it with your preferred name/handle if needed.

```bash
!cyberslm-train generate-crypto-ctf-drafts
!cyberslm-train promote-crypto-ctf-drafts \
  --reviewer "Daniel Peng" \
  --confirm-experimental-training
!cyberslm-train validate \
  --dataset data/training/crypto-ctf-sft-v0-experimental/corpus.jsonl \
  --manifest data/training/crypto-ctf-sft-v0-experimental/manifest.json
```

Promotion is intentionally explicit: it marks the manifest and every record as
`experimental-operator-approved`, not independently reviewed or release-ready.

## 3. Pin the exact base checkpoint

Run this cell and copy the full commit hash it prints. Do not replace it with `main`.

```python
from huggingface_hub import model_info

CYBERSLM_BASE_REVISION = model_info(
    "unsloth/gemma-3-4b-it-unsloth-bnb-4bit"
).sha
print(CYBERSLM_BASE_REVISION)
```

Then set it in a shell cell (replace the placeholder with the copied full hash):

```bash
%env CYBERSLM_BASE_REVISION=paste_the_full_commit_hash_here
```

## 4. Run the no-GPU preflight

This validates the corpus, manifest, provenance, review marker, and immutable base revision
without downloading the base model or importing Unsloth:

```bash
!cyberslm-unsloth-sft \
  --dataset data/training/crypto-ctf-sft-v0-experimental/corpus.jsonl \
  --manifest data/training/crypto-ctf-sft-v0-experimental/manifest.json \
  --base-revision "$CYBERSLM_BASE_REVISION" \
  --confirm-experimental-training \
  --validate-only
```

## 5. Run a five-step smoke training run

This proves model access, GPU use, the Gemma 3 chat template, response-only loss, validation,
and adapter saving. It is not a candidate to publish.

```bash
!cyberslm-unsloth-sft \
  --dataset data/training/crypto-ctf-sft-v0-experimental/corpus.jsonl \
  --manifest data/training/crypto-ctf-sft-v0-experimental/manifest.json \
  --base-revision "$CYBERSLM_BASE_REVISION" \
  --output data/adapters/gemma3-4b-cyberslm-crypto-ctf-smoke \
  --max-steps 5 \
  --confirm-experimental-training \
  --skip-merge
```

## 6. Run the first experimental candidate

Only after the smoke run completes, use a fresh output directory. One epoch is deliberately
conservative for this small starting curriculum.

```bash
!cyberslm-unsloth-sft \
  --dataset data/training/crypto-ctf-sft-v0-experimental/corpus.jsonl \
  --manifest data/training/crypto-ctf-sft-v0-experimental/manifest.json \
  --base-revision "$CYBERSLM_BASE_REVISION" \
  --output data/adapters/gemma3-4b-cyberslm-crypto-ctf-sft-v0 \
  --epochs 1 \
  --learning-rate 2e-5 \
  --confirm-experimental-training
```

The output contains:

```text
data/adapters/gemma3-4b-cyberslm-crypto-ctf-sft-v0/
├── adapter/                  Portable PEFT Safetensors adapter and tokenizer files
├── checkpoints/              Resumable trainer checkpoints
├── merged/                   Merged 16-bit Safetensors checkpoint
└── cyberslm-training.json    Exact base, corpus hash, settings, metrics, and environment
```

## 7. Download artifacts and return here

Download these folders/files from Colab:

```text
adapter/
merged/
cyberslm-training.json
```

Once you have them locally, tell me where you saved the downloaded output directory. I will verify
its metadata and hashes, compare it with the untouched Gemma base and Foundation-Sec on held-out
tests, and only then prepare a GGUF/Ollama import. `publish-local` refreshes the local Ollama
definition; it cannot turn an adapter into new Ollama weights until this conversion stage is done.

References:

- [Official Unsloth Gemma 3 guide](https://unsloth.ai/docs/models/gemma-3-how-to-run-and-fine-tune)
- [Unsloth chat templates](https://unsloth.ai/docs/basics/chat-templates)
