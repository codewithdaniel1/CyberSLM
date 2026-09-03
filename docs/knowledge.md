# CyberSLM data and knowledge

CyberSLM keeps different kinds of data separate because they have different trust,
privacy, licensing, and reproducibility requirements.

| Data | Location | Committed to Git? | Purpose |
| --- | --- | --- | --- |
| Gemma model weights | `~/.cache/huggingface/hub/` | No | Base language and vision model |
| ATT&CK/CWE/CAPEC downloads | `data/knowledge/sources/` | No | Rebuildable authoritative snapshots |
| Searchable knowledge index | `data/knowledge/knowledge.db` | No | Local SQLite FTS5 retrieval for RAG |
| Embedding model cache | `data/knowledge/models/` | No | Local BGE ONNX model used for semantic search |
| Cyber mode prompts | `src/cyberslm/modes.py` | Yes | Task behavior and response structures |
| Evaluation datasets | `evals/datasets/` | Yes | Reproducible measurement, never training |
| Evaluation reports | `evals/results/` | No | Local model outputs and scores |
| Conversations | `data/cyberslm.db` | No | Private chat history, never training by default |
| Uploaded screenshots | `data/uploads/` | No | Private conversation attachments |
| Reviewed training corpus | `data/training/` | No | Explicitly assembled optional LoRA input |
| Candidate adapters | `data/adapters/` | No | Local experimental weights and metadata |
| Private backup archives | `backups/` | No | Integrity-checked DB, index, and upload snapshots |

There is currently **no shipped fine-tuning corpus or adapter**. CyberSLM 0.5 is specialized
through cyber prompts and retrieval, not modified weights by default. Its optional adapter
workflow requires a separately reviewed manifest and corpus; private chat history, uploaded
evidence, and evaluation answers are never silently converted into training data.

## Synchronize knowledge

```bash
uv run cyberslm-knowledge sync
```

This downloads and indexes the pinned sources:

- MITRE Enterprise ATT&CK 19.1
- Common Weakness Enumeration 4.20
- Common Attack Pattern Enumeration and Classification 3.9

Inspect the local store:

```bash
uv run cyberslm-knowledge status
uv run cyberslm-knowledge embed
uv run cyberslm-knowledge verify
uv run cyberslm-knowledge search "failed SSH logins brute force" --mode defensive
uv run cyberslm-knowledge search "CWE-89 SQL injection" --mode secure_code --json
```

The Streamlit sidebar exposes the same operation under **Knowledge and updates**. The API runs
one background sync at a time, reports source/embedding progress, and preserves the existing
index if a download or validation fails.

The app still works when the index is absent. The sidebar will say `RAG empty`, and model
answers will use only Gemma and the selected mode prompt. Set `CYBERSLM_RAG_ENABLED=false`
to disable retrieval without deleting the local index.

## Retrieval behavior

Retrieval is non-agentic and read-only:

1. Source documents are deterministically split into overlapping passages.
2. The latest question is searched with SQLite FTS5 and a local BGE embedding.
3. Lexical and semantic rankings are combined with reciprocal-rank fusion.
4. Up to the configured number of matching ATT&CK/CWE/CAPEC documents are selected.
5. Reference text is inserted into the model prompt as untrusted factual material.
6. CyberSLM is asked to cite relevant references as `[1]`, `[2]`, and so on.
7. The backend appends the exact consulted titles and URLs to the response deterministically.

No external request occurs during chat. Network access is used only when the user explicitly
runs the knowledge synchronization or embedding command.

The first `sync` also downloads the configured FastEmbed ONNX model and builds local vectors.
Normal API and UI requests use local-only model loading; they fall back to FTS5 if the model
cache is unavailable rather than downloading files during a chat.

Source versions, SHA-256 digests, and expected parsed-document counts are committed with the
source definitions. Synchronization verifies all three before replacing indexed documents.
Use `cyberslm-knowledge verify` to check both the downloaded files and index metadata against
that manifest. A mismatch exits unsuccessfully instead of silently accepting changed data.
Embedding commits are incremental: an interrupted build resumes with only missing passages.
Hybrid search activates only when the configured model covers the complete passage index;
otherwise CyberSLM continues with lexical retrieval.

## Source terms and attribution

ATT&CK and CWE permit research, development, and commercial use subject to their terms and
attribution requirements. Source versions, download URLs, observed SHA-256 digests,
synchronization times, document counts, and copyright notices are stored in the local database.

- [MITRE ATT&CK data license](https://github.com/mitre-attack/attack-stix-data/blob/master/LICENSE.txt)
- [CWE terms of use](https://cwe.mitre.org/about/termsofuse.html)
- [CAPEC terms of use](https://capec.mitre.org/about/termsofuse.html)

The imported information is provided by its publishers as-is. Retrieval does not guarantee
correct coverage, and model output must still be verified against the linked source.
