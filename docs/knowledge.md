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
| Reviewed training corpus | `data/training/` | No | Explicitly assembled optional LoRA input |
| Candidate adapters | `data/adapters/` | No | Local experimental weights and metadata |

There is currently **no shipped fine-tuning corpus or adapter**. The training workflow requires a
separately reviewed manifest and corpus; private data, raw RAG documents, and evaluation answers
are never silently converted into training data.

## Synchronize knowledge

```bash
uv run cyberslm-knowledge sync
```

This downloads and indexes the pinned sources:

- MITRE Enterprise ATT&CK 19.1
- Common Weakness Enumeration 4.20
- Common Attack Pattern Enumeration and Classification 3.9

The normal command intentionally excludes sources that have not passed their admission
benchmark. The first opt-in pilot is a reviewed 24-document subset of the OWASP Cheat Sheet
Series. Developers can evaluate it without changing the default retrieval source set:

```bash
uv run cyberslm-knowledge sync --source owasp
uv run cyberslm-knowledge verify --source owasp
```

Its repository commit, archive hash, document allowlist, parser, and attribution notice are
committed. Normal `sync`, `verify`, and evaluation routing continue to use only ATT&CK, CWE, and
CAPEC until the pilot is admitted.

Inspect the local store:

```bash
uv run cyberslm-knowledge status
uv run cyberslm-knowledge embed
uv run cyberslm-knowledge verify
uv run cyberslm-knowledge search "failed SSH logins brute force" --mode defensive
uv run cyberslm-knowledge search "CWE-89 SQL injection" --mode secure_code --json
```

The CLI reports source and embedding progress and preserves the existing index if a download or
validation fails. Evaluations still work when the index is absent and can run with RAG disabled.
Set `CYBERSLM_RAG_ENABLED=false` to disable retrieval without deleting the local index.

## Retrieval behavior

Retrieval is non-agentic and read-only. Before searching, each message applies one of three
policies:

- **Auto** (recommended) searches for exact ATT&CK/CWE/CAPEC IDs and when deterministic,
  mode-aware signals indicate that the local sources are relevant.
- **On** always attempts a search, which is useful when the automatic gate misses a query.
- **Off** skips local retrieval for that message.

The evaluation runner accepts these policies and records its decision and reason. When a search
proceeds:

1. Source documents are deterministically split into overlapping passages.
2. The latest question is searched with SQLite FTS5 and a local BGE embedding.
3. Lexical and semantic rankings are combined with reciprocal-rank fusion.
4. Up to the configured number of matching ATT&CK/CWE/CAPEC documents are selected.
5. Reference text is inserted into the model prompt as untrusted factual material.
6. CyberSLM is asked to cite relevant references as `[1]`, `[2]`, and so on.
7. The backend appends the exact consulted titles and URLs to the response deterministically.

Network access is used only when the user explicitly runs knowledge synchronization or initially
downloads the configured embedding model.

The first `sync` also downloads the configured FastEmbed ONNX model and builds local vectors.
Normal retrieval uses local-only model loading and falls back to FTS5 if the embedding cache is
unavailable.

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

The additional-source discovery review is complete. See
[`knowledge-source-evaluation.md`](knowledge-source-evaluation.md) for the eight-source decision
matrix, the three approved pilots, deferred integrations, and the admission benchmark required
before any new source joins the default index.
