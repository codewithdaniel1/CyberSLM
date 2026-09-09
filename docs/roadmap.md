# CyberSLM-AppSec roadmap

Status: 2026-09-09

CyberSLM-AppSec is now a format-neutral application-security model project. The v0.5
Streamlit/FastAPI application is historical; current work focuses on secure-code review,
vulnerability explanation, minimal remediation, safe verification, and portable model artifacts.

## Artifact contract

The canonical release input is a local standard Safetensors/PEFT checkpoint named from its exact
base family and size, initially `gemma3-4b-cyberslm-appsec`. Hugging Face Hub publication is
deferred.

1. A PEFT adapter is the small, inspectable training artifact.
2. A merged Safetensors checkpoint is derived for standard Transformers use.
3. GGUF quantizations are derived from that accepted checkpoint for Ollama and llama.cpp.
4. MLX artifacts may be derived for Apple Silicon.
5. RAG indexes remain external, replaceable knowledge packages.

Every derivative must record the base revision, dataset hash, chat template, training settings,
merge method, converter revision, and quantization.

## Current milestone: universal training foundation

1. **Remove the application layer.**
   - [x] Remove Streamlit, FastAPI, conversation storage, backup code, and launchers.
   - [x] Remove their runtime dependencies and app-only tests.
   - [x] Preserve ignored local user data rather than deleting it during source cleanup.
2. **Make reviewed data portable.**
   - [x] Retain the license, privacy, reviewer, and corpus-hash gate.
   - [x] Export `train.jsonl` and `validation.jsonl` with standard chat `messages` records.
   - [x] Emit dataset metadata that locks the source corpus hash and exact base model.
3. **Establish local Safetensors as the canonical model format.**
   - [x] Allow the Transformers evaluator to load standard local PEFT adapters.
   - [ ] Add artifact validation for PEFT configuration, tokenizer, chat template, and training
     metadata.
   - [ ] Add an explicit merge command that produces portable Safetensors without publishing.
   - [ ] Generate SHA-256 manifests for every adapter, merged-model, tokenizer, and metadata file.
4. **Add reproducible Unsloth training.**
   - [x] Export the verified CWE 4.20 and CAPEC 3.9 documents as deterministic raw-text
     train/validation JSONL with record provenance and SHA-256 manifests.
   - [x] Add a guarded Gemma 3 4B Unsloth runner with a hash-verified, no-download preflight.
   - [x] Document a separate five-step Colab smoke run before the full candidate run.
   - [ ] Run the exported corpus through that runner on NVIDIA/Colab.
   - [x] Make the runner capture exact package versions, base revision, corpus hash, metrics, and
     hyperparameters in `cyberslm-training.json`.
   - [ ] Produce the first PEFT adapter and merged 16-bit Hugging Face checkpoint on NVIDIA/Colab.
   - [ ] Re-import the adapter with plain Transformers and verify output parity.
   - [x] Add a held-out AppSec comparison suite and establish Gemma 3 4B and
     Foundation-Sec-8B-Instruct baselines.
   - [ ] Human-approve the AppSec comparison labels and blind-review all baseline responses.
   - [ ] If the corrected Gemma candidate cannot beat Foundation-Sec on the human-reviewed gate,
     validate Foundation-Sec Safetensors as the next Unsloth training base.
5. **Derive deployment formats.**
   - [ ] Export GGUF from the accepted merged checkpoint and validate its chat template.
   - [ ] Create `gemma3-4b-cyberslm-appsec:0.1` in Ollama from that GGUF.
   - [ ] Derive and validate MLX weights if the conversion preserves required capabilities.
   - [ ] Package the accepted PEFT adapter and sharded merged Safetensors for Unsloth and
     Transformers users.
   - [ ] Package the accepted GGUF plus Modelfile and reconstruction instructions for Ollama
     users.
   - [ ] Keep every GitHub Release asset below 2 GiB and generate SHA-256 hashes for both parts
     and reconstructed artifacts.
   - [ ] Publish a versioned GitHub Release only after license and evaluation approval.
6. **Package RAG as a companion artifact.**
   - [ ] Export normalized ATT&CK/CWE/CAPEC documents with source versions and SHA-256 manifests.
   - [ ] Document attaching that bundle to `gemma3-4b-cyberslm-appsec` in Open WebUI.
   - [ ] Keep the existing CyberSLM retriever available for reproducible evaluation and stricter
     citation controls.
   - [ ] Verify that running the model without the companion bundle remains a valid no-RAG mode.

Hugging Face Hub upload and hosted inference are explicitly deferred. GitHub Releases are the
initial public distribution channel once the local Safetensors-to-Ollama pipeline produces an
accepted CyberSLM-AppSec model.

## Evaluation gate

The untouched predecessor `gemma3-4b-cyberslm:dev` Ollama baseline completed the six-case suite at 1,024
tokens. No-RAG scored 5/6 automatic passes with no truncation; the remaining Base64 answer was a
wording false negative. Auto-RAG scored 4/6 and revealed an unsafe SSRF validation suggestion plus
weak citation attribution.

Before fine-tuning results can be promoted:

- resolve and rerun the Ollama Auto-RAG safety/citation regression;
- compare the same held-out prompts across Transformers/PEFT, Unsloth, merged Safetensors, and
  GGUF/Ollama;
- confirm that chat-template differences do not change behavior materially;
- retain human review for safety and factual correctness; and
- require the candidate to beat the untouched base without increasing unsafe compliance or false
  refusals.

## RAG scope

The pinned MITRE ATT&CK, CWE, and CAPEC pipeline remains the reference RAG implementation. Its
index is not included in model weights or uploaded with the model. Future work may expose
framework-neutral retrieval output or package normalized documents for standard RAG tools.

Additional knowledge-source experiments remain deferred until the first universal checkpoint is
validated.

## Deferred

- A custom chat UI, conversation database, or hosted application
- Automatic training on conversations, uploads, evaluation responses, or raw RAG documents
- Full training on the local 16 GB Mac when an NVIDIA/Colab run is more reproducible
- Multiple base-model families before the Gemma 3 pipeline works end to end
- Hugging Face Hub publishing or hosted inference
- Agent or MCP integration

Historical v0.5 application evidence remains in `docs/alpha-validation.md` and
`docs/releases/v0.5.0a1.md`.
