# CyberSLM-AppSec Unsloth GPU run

This runbook performs the first continued-pretraining smoke test and full candidate run without
placing another model on the local Mac. Google Colab storage is temporary; download the completed
adapter and metadata before ending the session.

## Before opening Colab

1. Push the current CyberSLM source revision to GitHub.
2. Review the Gemma license and the CWE/CAPEC source terms referenced in the corpus manifest.
3. Select an NVIDIA GPU runtime in Colab. A T4 may be sufficient for the 4-bit LoRA smoke run;
   an L4 or larger GPU is preferable for the complete run.
4. Do not paste Hugging Face tokens into the notebook or repository. Use Colab Secrets if access
   to a gated model requires a token.

## 1. Install the runner

Run these commands in Colab:

```bash
!git clone https://github.com/codewithdaniel1/CyberSLM.git
%cd CyberSLM
!pip install -q unsloth
!pip install -q -e .
!nvidia-smi
```

The Unsloth installation command may change with CUDA and PyTorch releases. If its official Gemma
3 notebook specifies a different installation cell, use that cell and then rerun `pip install -e
.` for CyberSLM.

## 2. Rebuild the pinned corpus

The raw corpus is deliberately absent from Git history. Rebuild it from the source definitions
and pinned archive hashes:

```bash
!cyberslm-knowledge sync --source cwe --source capec --no-embeddings
!cyberslm-knowledge verify --source cwe --source capec
!cyberslm-train export-pretraining \
  --output data/training/appsec-pretraining-v1 \
  --source cwe --source capec \
  --confirm-training-use
```

The resulting manifest must report 1,503 records and match the expected source versions and
archive hashes. The training runner independently verifies every exported file.

## 3. Pin the base checkpoint

Capture the exact immutable revision returned at the time of the run:

```bash
!python -c "from huggingface_hub import model_info; print(model_info('unsloth/gemma-3-4b-it-unsloth-bnb-4bit').sha)"
```

Store the full commit SHA in the Colab environment. Do not use `main` as the revision:

```bash
%env CYBERSLM_BASE_REVISION=paste_full_commit_sha_here
```

## 4. Run the no-download preflight

```bash
!cyberslm-unsloth \
  --base-revision "$CYBERSLM_BASE_REVISION" \
  --confirm-reviewed \
  --validate-only
```

This should finish before any model is loaded.

## 5. Run a five-step smoke train

```bash
!cyberslm-unsloth \
  --base-revision "$CYBERSLM_BASE_REVISION" \
  --output data/adapters/gemma3-4b-cyberslm-appsec-smoke \
  --max-steps 5 \
  --confirm-reviewed \
  --skip-merge
```

The smoke run proves CUDA loading, tokenization, forward/backward training, validation, and PEFT
adapter saving. It is not a candidate model and must not be released.

## 6. Run the first full candidate

Use a new output directory so the smoke artifact cannot be mistaken for the candidate:

```bash
!cyberslm-unsloth \
  --base-revision "$CYBERSLM_BASE_REVISION" \
  --output data/adapters/gemma3-4b-cyberslm-appsec-cpt-v1 \
  --epochs 1 \
  --learning-rate 5e-5 \
  --confirm-reviewed
```

This creates the PEFT adapter, trainer checkpoints, merged 16-bit Safetensors, and
`cyberslm-training.json`. Training loss alone does not approve the candidate.

## 7. Preserve the artifacts

Download at minimum:

```text
data/adapters/gemma3-4b-cyberslm-appsec-cpt-v1/adapter/
data/adapters/gemma3-4b-cyberslm-appsec-cpt-v1/merged/
data/adapters/gemma3-4b-cyberslm-appsec-cpt-v1/cyberslm-training.json
```

The next local stage validates and hashes those files, reloads the adapter with plain
Transformers, evaluates it against untouched Gemma 3 and Foundation-Sec, and only then converts an
accepted candidate to GGUF for Ollama.

References:

- [Official Unsloth Gemma 3 guide](https://unsloth.ai/docs/models/gemma-3-how-to-run-and-fine-tune)
- [Official Unsloth continued-pretraining guide](https://unsloth.ai/docs/basics/continued-pretraining)
