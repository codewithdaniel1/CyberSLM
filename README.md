# CyberSLM

CyberSLM is a private, local-first multimodal cybersecurity assistant built for Apple
Silicon. Version 0.3 runs a 4-bit Gemma 3 4B model through MLX, provides a Streamlit chat
interface, accepts screenshots, and persists multiple conversations in SQLite.

## What works in v0.3

- Local text and screenshot/image analysis
- Six focused modes: General, Defensive, Offensive, CTF, Forensics, and Secure Code
- Mode-specific response structures for consistent analyst output
- Per-conversation authorization context, explicitly labeled as user-provided and unverified
- Persistent SQLite conversations with automatic titles
- Multiple chats, renaming, deletion, and saved image attachments
- FastAPI backend with interactive API docs
- Lazy model loading and a mock backend for development
- Reproducible baseline evaluation and run comparison CLI
- Local citation-aware RAG over pinned MITRE ATT&CK and CWE releases
- Localhost-only defaults; no telemetry or hosted model API

## Requirements

- Apple Silicon Mac (M1 or newer); 16 GB unified memory is suitable for the default model
- macOS
- [`uv`](https://docs.astral.sh/uv/)
- Roughly 5 GB of free disk space for the environment and model cache

The setup pins Python 3.12 because the system Python may be newer than the MLX ecosystem
currently supports.

## Quick start

```bash
./setup.sh
uv run cyberslm-knowledge sync
./start.sh
```

Open <http://localhost:8501>. The first real prompt downloads and loads
`mlx-community/gemma-3-4b-it-4bit`, so it can take several minutes. Later starts reuse the
Hugging Face cache.

Gemma access is governed by Google's Gemma terms. If Hugging Face requests authentication,
accept the model license on its model page and run `huggingface-cli login` locally.

### Test without downloading the model

Edit `.env`:

```dotenv
CYBERSLM_MODEL_BACKEND=mock
```

Then run `./start.sh`. The mock backend exercises the UI, API, uploads, and database but
does not perform model inference.

## Configuration

Copy `.env.example` to `.env` (the setup script does this automatically). Important values:

| Variable | Default | Purpose |
| --- | --- | --- |
| `CYBERSLM_MODEL_BACKEND` | `mlx` | `mlx` for Gemma or `mock` for testing |
| `CYBERSLM_MODEL_ID` | `mlx-community/gemma-3-4b-it-4bit` | Hugging Face model ID or local path |
| `CYBERSLM_MAX_TOKENS` | `768` | Maximum generated tokens |
| `CYBERSLM_TEMPERATURE` | `0.2` | Generation randomness |
| `CYBERSLM_MAX_UPLOAD_MB` | `10` | Per-image upload limit |
| `CYBERSLM_API_PORT` | `8000` | Local API port |
| `CYBERSLM_UI_PORT` | `8501` | Local UI port |
| `CYBERSLM_RAG_ENABLED` | `true` | Enable local knowledge retrieval |
| `CYBERSLM_RAG_RESULTS` | `4` | Maximum references retrieved per prompt |
| `CYBERSLM_RAG_MAX_CHARS` | `16000` | Maximum retrieved context characters |

Run the environment check at any time:

```bash
uv run python scripts/doctor.py
```

## Development

```bash
CYBERSLM_MODEL_BACKEND=mock uv run uvicorn cyberslm.api:app --reload
CYBERSLM_MODEL_BACKEND=mock uv run streamlit run ui/app.py
uv run pytest
uv run ruff check .
```

API documentation is available at <http://127.0.0.1:8000/docs> while the backend runs.

## Cyber knowledge and RAG

CyberSLM stores downloaded ATT&CK/CWE snapshots and its searchable FTS5 index under
`data/knowledge/`. They are machine-local, ignored by Git, and reproducible with:

```bash
uv run cyberslm-knowledge sync
uv run cyberslm-knowledge verify
uv run cyberslm-knowledge status
uv run cyberslm-knowledge search "T1110 brute force" --mode defensive
```

There is no fine-tuning dataset yet. Mode prompts shape behavior, the local knowledge index
provides factual context, evaluation datasets measure behavior, and private conversations are
not training data. See [`docs/knowledge.md`](docs/knowledge.md) for the complete data map,
retrieval behavior, and source attribution.

## Evaluation

The bundled synthetic smoke suite verifies the evaluation pipeline and basic cyber concepts:

```bash
uv run cyberslm-eval validate
uv run cyberslm-eval run --backend mlx --temperature 0
```

Reports include the complete responses, deterministic concept scores, category summaries,
latency, model configuration, environment metadata, and hashes of both the dataset and mode
prompts. Compare a later candidate against the saved baseline with:

```bash
uv run cyberslm-eval compare evals/results/baseline.json evals/results/candidate.json
```

Generated reports are private local artifacts and ignored by Git. See
[`evals/README.md`](evals/README.md) for the schema, limitations, and mock command.

## Authorization context

Each conversation can be labeled as not specified, an owned system/local lab, CTF/training,
an authorized assessment, or defensive operations. CyberSLM includes that selection in the
model prompt and stores it in SQLite with the conversation.

This field records context; it does not verify authorization and never overrides the base
safety boundaries. Existing databases are migrated automatically and existing conversations
default to `Not specified`.

## Data and privacy

Conversations are stored at `data/cyberslm.db`; uploads are stored in `data/uploads/`.
Both are ignored by Git. The default services bind only to `127.0.0.1`, and inference is
local. Deleting a conversation also deletes its saved attachments.

CyberSLM is an analyst aid, not an authority. Verify findings before acting, retain original
evidence, and use offensive functionality only on systems you own or are authorized to test.

## Architecture

```text
Browser :8501
    │
    ▼
Streamlit UI ──── screenshots
    │
    ▼
FastAPI :8000 ─── SQLite conversations
    │
    ├── Local ATT&CK/CWE retrieval ─── SQLite FTS5
    ▼
Model backend ─── retrieved citations ─── MLX-VLM ─── Gemma 3 4B (4-bit)
```

The model backend is intentionally isolated so later milestones can add streaming, RAG,
fine-tuned adapters, and additional local runtimes without changing persistence, evaluation,
or UI contracts.
