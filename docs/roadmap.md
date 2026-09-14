# CyberSLM-Crypto roadmap

Status: 2026-09-14

CyberSLM-Crypto is a portable applied-cryptography model project that complements CyberWorkbench.
The previous application-security direction is historical and will not be used as a training or
promotion baseline for this model.

## Current milestone: first cryptography candidate

1. **Lock the specialty.**
   - [x] Set the model behavior and Ollama development prompt to applied cryptography only.
   - [x] Exclude audit, SOC, offensive, forensics, and non-cryptography CTF work from the scope.
   - [x] Establish `gemma3-4b-cyberslm-crypto` as the first naming target.
2. **Build trustworthy crypto data.**
   - [ ] Approve a small, versioned set of source documents and terms for training use.
   - [ ] Add a provenance-preserving crypto corpus exporter; never reuse the CWE/CAPEC corpus.
   - [ ] Write and human-review crypto instruction examples for implementation and protocol use.
   - [x] Generate deterministic original crypto-CTF draft examples across the starter taxonomy.
   - [ ] Human-review and promote original crypto CTF challenge/solution pairs; never scrape
     unlicensed writeups.
   - [ ] Build a held-out crypto evaluation suite before tuning.
3. **Train and validate.**
   - [x] Maintain a guarded, reproducible Unsloth runner that records exact corpus and environment
     metadata.
   - [ ] Run a five-step smoke train on a reviewed crypto corpus using NVIDIA/Colab.
   - [ ] Train one controlled Gemma 3 4B candidate.
   - [ ] Validate the adapter, metadata, tokenizer, and merged Safetensors with SHA-256 manifests.
   - [ ] Compare candidate and untouched base using human-reviewed crypto evaluations.
4. **Derive portable releases.**
   - [ ] Convert an accepted merged checkpoint to GGUF and validate it in Ollama.
   - [ ] Create `gemma3-4b-cyberslm-crypto:0.1` from that accepted GGUF.
   - [ ] Package adapter, merged Safetensors, GGUF, hashes, and reconstruction instructions in a
     GitHub Release.
5. **Offer optional standards RAG.**
   - [ ] Package only reviewed, hash-pinned crypto standards material as a companion bundle.
   - [ ] Ensure the model remains useful with RAG disabled.

## Deferred

- General cybersecurity auditing and existing AppSec evaluation/RAG expansion
- A custom chat UI, conversation storage, hosted inference, agents, or MCP
- Multiple base-model families before the first Gemma 3 crypto candidate is validated
- Hugging Face Hub publication until the artifact and licensing gate passes
