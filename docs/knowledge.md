# CyberSLM data and knowledge

CyberSLM keeps different kinds of data separate because they have different trust,
privacy, licensing, and reproducibility requirements.

| Data | Location | Committed to Git? | Purpose |
| --- | --- | --- | --- |
| Gemma model weights | `~/.cache/huggingface/hub/` | No | Base language and vision model |
| ATT&CK/CWE source downloads | `data/knowledge/sources/` | No | Rebuildable authoritative source snapshots |
| Searchable knowledge index | `data/knowledge/knowledge.db` | No | Local SQLite FTS5 retrieval for RAG |
| Cyber mode prompts | `src/cyberslm/modes.py` | Yes | Task behavior and response structures |
| Evaluation datasets | `evals/datasets/` | Yes | Reproducible measurement, never training |
| Evaluation reports | `evals/results/` | No | Local model outputs and scores |
| Conversations | `data/cyberslm.db` | No | Private chat history, never training by default |
| Uploaded screenshots | `data/uploads/` | No | Private conversation attachments |

There is currently **no fine-tuning corpus**. CyberSLM 0.3 is specialized through cyber
mode prompts and retrieval from authoritative local sources. Conversation history and
evaluation answers are never silently converted into training data.

## Synchronize knowledge

```bash
uv run cyberslm-knowledge sync
```

This downloads and indexes the pinned sources:

- MITRE Enterprise ATT&CK 19.1
- Common Weakness Enumeration 4.20

Inspect the local store:

```bash
uv run cyberslm-knowledge status
uv run cyberslm-knowledge search "failed SSH logins brute force" --mode defensive
uv run cyberslm-knowledge search "CWE-89 SQL injection" --mode secure_code --json
```

The app still works when the index is absent. The sidebar will say `RAG empty`, and model
answers will use only Gemma and the selected mode prompt. Set `CYBERSLM_RAG_ENABLED=false`
to disable retrieval without deleting the local index.

## Retrieval behavior

Retrieval is non-agentic and read-only:

1. The latest user question is converted into a local SQLite FTS5 query.
2. Up to the configured number of matching ATT&CK/CWE documents are selected.
3. Reference text is inserted into the model prompt as untrusted factual material.
4. CyberSLM is asked to cite relevant references as `[1]`, `[2]`, and so on.
5. The backend appends the exact consulted titles and URLs to the response deterministically.

No external request occurs during chat. Network access is used only when the user explicitly
runs the knowledge synchronization command.

## Source terms and attribution

ATT&CK and CWE permit research, development, and commercial use subject to their terms and
attribution requirements. Source versions, download URLs, SHA-256 digests, synchronization
times, document counts, and copyright notices are stored in the local database.

- [MITRE ATT&CK data license](https://github.com/mitre-attack/attack-stix-data/blob/master/LICENSE.txt)
- [CWE terms of use](https://cwe.mitre.org/about/termsofuse.html)

The imported information is provided by its publishers as-is. Retrieval does not guarantee
correct coverage, and model output must still be verified against the linked source.
