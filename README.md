# CyberSLM

CyberSLM is a private, local-first multimodal cybersecurity assistant. Version 0.5 alpha 1 runs Gemma
3 4B through MLX on Apple Silicon or an optional PyTorch/Transformers runtime on Linux and
Windows, provides a Streamlit chat interface, accepts screenshots, and persists multiple
conversations in SQLite.

The guarded 4B model baseline and complete end-to-end flow have passed local Apple Silicon
acceptance. The first packaged build is available as the private
[`v0.5.0a1` GitHub prerelease](https://github.com/codewithdaniel1/CyberSLM/releases/tag/v0.5.0a1),
and the detailed evidence is tracked in
[`docs/alpha-validation.md`](docs/alpha-validation.md).

## What works in v0.5

- Local text and screenshot/image analysis
- Cancelable generation with partial-turn cleanup and verified buffered answer release
- Six focused modes: General, Defensive, Offensive, CTF, Forensics, and Secure Code
- Mode-specific response structures for consistent analyst output
- Per-conversation authorization context, explicitly labeled as user-provided and unverified
- Persistent SQLite conversations with automatic titles
- Multiple chats, renaming, deletion, and saved image attachments
- FastAPI backend with interactive API docs
- Lazy model loading and a mock backend for development
- Reproducible baseline evaluation and run comparison CLI
- Local hybrid citation-aware RAG over pinned MITRE ATT&CK, CWE, and CAPEC releases
- Per-message Auto/On/Off knowledge control with a deterministic source-aware relevance gate
- Opt-in local C syntax validation that never links or executes generated programs
- Transparent deterministic response guards for demonstrated SSRF, ATT&CK, PowerShell 4104,
  and Python SQL-injection failures
- Deterministic passage chunking, FastEmbed vectors, FTS5, and reciprocal-rank fusion
- Resumable semantic indexing with visible progress and pre-generation source previews
- One-click background knowledge sync with hash verification and visible progress
- Retrieval/citation/safety metrics, including a licensed 750-case false-refusal suite
- Source-hash-locked human review for response quality and retrieved-claim support
- Verified source manifests with expected SHA-256 hashes and document counts
- GitHub Actions CI across Python 3.11-3.13, Linux/Windows portable-runtime checks, and package
  validation
- Tag-driven GitHub Releases with checksums and public-repository provenance attestations
- Consistent SQLite/upload backups with integrity checks and a SHA-256 manifest
- Localhost-only defaults; no telemetry or hosted model API
- Reviewed-corpus gates and an optional local MLX-VLM LoRA adapter workflow

## Requirements

- Apple Silicon Mac (recommended), Linux, or Windows
- 16 GB unified memory is suitable for the 4-bit MLX model; the portable unquantized runtime
  may require more system or GPU memory
- [`uv`](https://docs.astral.sh/uv/)
- Roughly 5 GB free for the MLX path; allow substantially more for PyTorch and unquantized Gemma

The setup pins Python 3.12 because the system Python may be newer than the MLX ecosystem
currently supports.

## Quick start

macOS and Linux:

```bash
./setup.sh
uv run cyberslm-knowledge sync
uv run cyberslm-knowledge verify
./start.sh
```

Windows PowerShell:

```powershell
./setup.ps1
uv run cyberslm-knowledge sync
uv run cyberslm-knowledge verify
./start.ps1
```

Open <http://localhost:8501>. The first real prompt downloads and loads the backend's Gemma 3
model, so it can take several minutes. Later starts reuse the Hugging Face cache. `auto` selects
MLX with `mlx-community/gemma-3-4b-it-4bit` on Apple Silicon and Transformers with
`google/gemma-3-4b-it` elsewhere.

Existing clones whose `.env` explicitly says `CYBERSLM_MODEL_BACKEND=mlx` keep that choice.
Set the backend to `auto` and clear `CYBERSLM_MODEL_ID`, or select `transformers` and
`google/gemma-3-4b-it`, before moving that installation to Linux or Windows.

Gemma access is governed by Google's Gemma terms. If Hugging Face requests authentication,
accept the model license on its model page and run `huggingface-cli login` locally.

### Test without downloading the model

Edit `.env`:

```dotenv
CYBERSLM_MODEL_BACKEND=mock
```

Then run `./start.sh` or `./start.ps1`. The mock backend exercises the UI, API, uploads, and
database but does not perform model inference.

## Configuration

Copy `.env.example` to `.env` (the setup script does this automatically). Important values:
Set `CYBERSLM_ENV_FILE` before running a startup script when you need an alternate configuration
without changing the repository `.env`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `CYBERSLM_ENV_FILE` | repository `.env` | Alternate startup environment file |
| `CYBERSLM_MODEL_BACKEND` | `auto` | Platform default, or `mlx`, `transformers`, or `mock` |
| `CYBERSLM_MODEL_ID` | backend default | Hugging Face model ID or local path |
| `CYBERSLM_TRANSFORMERS_DEVICE` | `auto` | Portable device: `auto`, `cuda`, `mps`, or `cpu` |
| `CYBERSLM_TRANSFORMERS_REVISION` | `main` | Portable model revision or pinned commit |
| `CYBERSLM_TRANSFORMERS_QUANTIZATION` | `none` | Portable weights: `none`, `8bit`, or `4bit` |
| `CYBERSLM_ADAPTER_PATH` | empty | Optional evaluated LoRA adapter `.safetensors` path |
| `CYBERSLM_MAX_TOKENS` | `1024` | Maximum generated tokens |
| `CYBERSLM_TEMPERATURE` | `0.2` | Generation randomness |
| `CYBERSLM_MAX_UPLOAD_MB` | `10` | Per-image upload limit |
| `CYBERSLM_API_PORT` | `8000` | Local API port |
| `CYBERSLM_UI_PORT` | `8501` | Local UI port |
| `CYBERSLM_DATA_DIR` | repository `data/` | Conversations, uploads, and local knowledge root |
| `CYBERSLM_RAG_ENABLED` | `true` | Master switch permitting local knowledge retrieval |
| `CYBERSLM_RAG_SEMANTIC_ENABLED` | `true` | Combine embeddings with FTS5 retrieval |
| `CYBERSLM_RAG_EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Local FastEmbed model |
| `CYBERSLM_RAG_RESULTS` | `4` | Maximum references retrieved per prompt |
| `CYBERSLM_RAG_MAX_CHARS` | `16000` | Maximum retrieved context characters |
| `CYBERSLM_CODE_VALIDATION_ENABLED` | `true` | Permit opt-in local C syntax checking |
| `CYBERSLM_C_COMPILER` | auto-detected | Optional `clang`, `gcc`, or `cc` command/path |
| `CYBERSLM_CODE_VALIDATION_TIMEOUT` | `4` | Maximum seconds per fenced C block |
| `ORT_DISABLE_TELEMETRY` | `1` | Keep the ONNX embedding runtime telemetry-disabled |

Run the environment check at any time:

```bash
uv run python scripts/doctor.py
```

Create a private point-in-time backup before upgrades or migrations:

```bash
uv run cyberslm-backup --output backups/cyberslm-$(date +%Y%m%d).zip
```

The command uses SQLite's online backup API, verifies each copied database, includes uploads,
and records file sizes and SHA-256 hashes in `manifest.json`. Backups are ignored by Git.

## Development

```bash
CYBERSLM_MODEL_BACKEND=mock uv run uvicorn cyberslm.api:app --reload
CYBERSLM_MODEL_BACKEND=mock uv run streamlit run ui/app.py
uv run pytest
uv run ruff check .
```

API documentation is available at <http://127.0.0.1:8000/docs> while the backend runs.

CyberSLM buffers each generated answer until its narrow deterministic response guard has run.
This prevents unsafe draft tokens from reaching the UI and preserves cancellation while the model
is generating, but the answer appears after generation rather than token-by-token in real time.
The API and evaluation reports disclose whether a rule changed an answer. See
[`docs/response-guard.md`](docs/response-guard.md) for the exact rules and limitations.

After installing the portable runtime, exercise its real multimodal preprocessing and generation
path with the pinned 56 MB random test checkpoint:

```bash
uv run python scripts/smoke_transformers.py
```

This is a runtime smoke test, not a model-quality evaluation. It does not download the full Gemma
3 4B weights and its randomly initialized output is intentionally meaningless.

### Portable memory modes

The Transformers runtime defaults to `none`, preserving the model's native 32-bit CPU or 16-bit
GPU loading path. Linux and Windows installations can explicitly reduce model-weight memory:

```dotenv
# Approximately 4 GB of raw 4B weights, plus runtime/context overhead
CYBERSLM_TRANSFORMERS_QUANTIZATION=8bit

# Approximately 2 GB of raw 4B weights, plus runtime/context overhead
CYBERSLM_TRANSFORMERS_QUANTIZATION=4bit
```

The estimates exclude PyTorch, image processing, the key/value cache, and other runtime memory.
Quantization uses Bitsandbytes and never applies to MLX. CyberSLM does not silently fall back to
unquantized weights when a selected mode is unsupported. Keep `none` for the evaluation control;
compare 8-bit and 4-bit output against that control before choosing either for routine use. See
the [official Transformers quantization guidance](https://huggingface.co/docs/transformers/quantization/bitsandbytes)
for current platform and hardware support.

### Full-model benchmark

Use the same six-case cyber suite to measure the full model on each target computer. The command
loads the model before timing generation, disables RAG to isolate model performance, preserves
the responses and quality scores, and records load time, tokens per second, model footprint,
process memory, operating system, hardware architecture, and package versions:

```bash
uv run cyberslm-benchmark --backend transformers --quantization none --label linux-control
uv run cyberslm-benchmark --backend transformers --quantization 8bit --label linux-8bit
uv run cyberslm-benchmark --backend transformers --quantization 4bit --label linux-4bit
```

The same commands work in PowerShell. On Apple Silicon, benchmark the optimized MLX runtime with:

```bash
uv run cyberslm-benchmark --backend mlx --label apple-mlx
```

Reports are written beneath `evals/results/` with a content hash and are ignored by Git because
they can contain complete model responses and machine details. Keep the dataset, model revision,
device, and token limit unchanged when comparing modes. The automatic concept score is a useful
regression signal, but it does not replace the human correctness and safety review described in
[`evals/review-rubric.md`](evals/review-rubric.md). The full Gemma checkpoint is gated and large;
the first benchmark may require Hugging Face access and a substantial download. By default, the
benchmark uses the same `CYBERSLM_MAX_TOKENS` limit as normal chat so quality is not measured from
artificially truncated answers.

## Cyber knowledge and RAG

CyberSLM stores downloaded ATT&CK/CWE/CAPEC snapshots and its searchable index under
`data/knowledge/`. These generated files are machine-local and ignored by Git; their pinned
source definitions, expected hashes, expected document counts, parsers, and rebuild commands
are committed.

Current sources:

| Source | Pinned version | Indexed documents |
| --- | --- | ---: |
| MITRE Enterprise ATT&CK | 19.1 | 697 |
| Common Weakness Enumeration | 4.20 | 944 |
| Common Attack Pattern Enumeration and Classification | 3.9 | 559 |

The OWASP Cheat Sheet Series is implemented as an opt-in 24-document pilot pinned to commit
`1eacf6cb9bfcba006ca972a804c5faace8c2758a`. It is deliberately excluded from normal sync,
verification, background rebuilds, and chat routing until its incremental benchmark passes.
Developers can build and verify the isolated pilot explicitly:

```bash
uv run cyberslm-knowledge sync --source owasp
uv run cyberslm-knowledge verify --source owasp
```

The evaluation runner can point at a separate candidate database and enable pilot routing only
for that run:

```bash
uv run cyberslm-eval gate \
  --dataset evals/datasets/owasp-retrieval-pilot.jsonl \
  --additional-source owasp
uv run cyberslm-eval retrieve \
  --dataset evals/datasets/owasp-retrieval-pilot.jsonl \
  --knowledge-db /path/to/candidate-knowledge.db \
  --auto-route --additional-source owasp --limit 1
uv run cyberslm-eval run \
  --dataset evals/datasets/owasp-retrieval-pilot.jsonl \
  --backend mlx --temperature 0 --rag-policy auto \
  --knowledge-db /path/to/candidate-knowledge.db \
  --additional-source owasp
```

These flags do not enable OWASP for chat, normal sync, or background rebuilds.

Manage the local index with:

```bash
uv run cyberslm-knowledge sync
uv run cyberslm-knowledge embed
uv run cyberslm-knowledge verify
uv run cyberslm-knowledge status
uv run cyberslm-knowledge search "T1110 brute force" --mode defensive
```

The same verified rebuild is available from **Knowledge and updates → Sync verified
knowledge** in the sidebar. It runs in the background and prevents concurrent rebuilds.

`sync` downloads exactly the versions pinned in
[`src/cyberslm/knowledge/sources.py`](src/cyberslm/knowledge/sources.py); it does not silently
select a newer release. Each download must match its committed SHA-256 hash, and parsing must
produce the expected document count before the existing index is replaced. `verify` checks
both the downloaded files and the SQLite metadata and exits unsuccessfully on a mismatch.

Chat itself never contacts these sources. If the index is missing, CyberSLM creates an empty
database and continues with the selected mode prompt and base model. Run `sync` explicitly to
reconstruct the RAG data.

This is a real local hybrid RAG pipeline: it prioritizes exact IDs, combines FTS5 keyword
results with local BGE embeddings through reciprocal-rank fusion, augments the Gemma prompt
with the selected passages, generates a grounded response, and appends the exact consulted
references. It does not change or fine-tune the Gemma weights. If semantic vectors are missing
or incomplete, retrieval safely falls back to FTS5 until `embed` finishes the resumable build.

Each message has a **Local knowledge** policy. **Auto** (recommended) searches only when the
prompt contains an exact ATT&CK/CWE/CAPEC identifier or source-relevant cyber signals for the
selected mode. **On** always attempts a local search, and **Off** skips it. The API accepts the
same policy as the `rag_policy` form field and returns a `rag` decision object so clients can
show whether retrieval was attempted and used. `CYBERSLM_RAG_ENABLED=false` remains a master
switch: no per-message choice can override it.

There is no fine-tuning dataset yet. Mode prompts shape behavior, the local knowledge index
provides factual context, evaluation datasets measure behavior, and private conversations are
not training data. See [`docs/knowledge.md`](docs/knowledge.md) for the complete data map,
retrieval behavior, and source attribution. The bounded review of eight additional source
families is recorded in
[`docs/knowledge-source-evaluation.md`](docs/knowledge-source-evaluation.md): OWASP Cheat Sheet
Series, MITRE D3FEND, and CISA KEV are approved for measured pilots; NVD, OSV, Sigma, EPSS, and
NIST OSCAL are intentionally deferred to narrower lookup or product modes.

## Generated C syntax validation

Enable **Check generated C syntax** for an individual message to inspect fenced `c` blocks with
a compatible local `clang`, `gcc`, or `cc`. CyberSLM invokes the compiler directly with C17,
warnings, and `-fsyntax-only`; it never links or executes the generated program. The saved
assistant response includes the bounded local diagnostics so a failed check cannot be mistaken
for working code.

The checker is off per message by default. It checks at most four blocks, rejects blocks over
50,000 characters, stops each compiler process after the configured timeout, truncates diagnostic
output, and rejects non-literal, absolute, or parent-traversing includes before compilation. Set
`CYBERSLM_CODE_VALIDATION_ENABLED=false` to remove the option or `CYBERSLM_C_COMPILER` to select
a specific compiler.

A passed syntax check proves only that the local compiler accepted the translation unit. It does
not prove correct behavior, safe memory use, successful linking, available runtime dependencies,
or security suitability. Generated code still requires human review and testing in an isolated
environment.

## Evaluation

The bundled synthetic smoke suite verifies the evaluation pipeline and basic cyber concepts:

```bash
uv run cyberslm-eval validate
uv run cyberslm-eval validate --dataset evals/datasets/retrieval.jsonl
uv run cyberslm-eval validate --dataset evals/datasets/selective-rag.jsonl
uv run cyberslm-eval validate --dataset evals/datasets/safety.jsonl
uv run cyberslm-eval validate --dataset evals/datasets/mode-coverage.jsonl
uv run cyberslm-eval validate --dataset evals/datasets/cyberseceval-mitre-frr.jsonl
uv run cyberslm-eval gate
uv run cyberslm-eval retrieve
uv run cyberslm-eval run --dataset evals/datasets/safety.jsonl --backend mlx --temperature 0
uv run cyberslm-eval run --dataset evals/datasets/mode-coverage.jsonl \
  --backend mlx --temperature 0 --rag-policy auto
uv run cyberslm-eval run --backend mlx --temperature 0
```

Reports include the complete responses, deterministic concept scores, category and mode summaries,
latency, model configuration, environment metadata, and hashes of both the dataset and complete
prompt contract (mode instructions plus the retrieved-background wrapper). They also record
auditable refusal phrase matches and authoritative runtime finish reasons so token-limit
truncation is not inferred from prose. Citation scoring examines only the generated answer body;
the application-added source-disclosure footer does not count as an inline model citation.
That footer shows both the number of inline citation markers and the number placed after their
source's exact ATT&CK/CWE/CAPEC identifier, so retrieval is never presented as proof of
grounded attribution. Each reference also carries a plain-language status showing whether its
exact ID was cited, mentioned without a linked citation, cited without a linked identifier, or
not explicitly referenced. These post-generation labels do not alter the model's answer.
Exact-ID proximity is a structural check, not semantic entailment.
Compare a later candidate against the saved baseline with:

Generation evaluation defaults to `--rag-policy auto`, matching chat. Use `--rag-policy on`
to force retrieval for every case or `--rag-policy off` for a model-only control. Reports
retain each routing reason and aggregate attempted/used counts; `--no-rag` remains a legacy
alias for `--rag-policy off`.

```bash
uv run cyberslm-eval compare evals/results/baseline.json evals/results/candidate.json
```

Generate a private, source-hash-locked human-review worksheet with anchored correctness, task
completion, operational-safety, and benchmark-label-quality fields:

```bash
uv run cyberslm-eval review init evals/results/candidate.json
uv run cyberslm-eval review summarize evals/results/candidate-review.json
```

For RAG runs, create a separate claim-support worksheet that pairs every source-linked answer
span with the exact retrieved passage the model saw:

```bash
uv run cyberslm-eval support-review init evals/results/candidate.json
uv run cyberslm-eval support-review summarize \
  evals/results/candidate-support-review.json
```

The reviewer assigns `supported`, `partially_supported`, `unsupported`,
`not_a_factual_claim`, or `unable_to_assess`. CyberSLM does not infer semantic support from
token overlap, a framework identifier, or a citation marker. New generation reports preserve
each retrieved passage and its SHA-256 so this review remains tied to the evidence actually
provided to the model.

Generated reports are private local artifacts and ignored by Git. See
[`evals/README.md`](evals/README.md) for the schema, limitations, and mock command.

The six-case synthetic smoke suite verifies plumbing and basic concept coverage only. It is
not large enough to establish model quality, production readiness, or superiority over another
model.

The separate 20-case synthetic retrieval benchmark currently measures 70% recall for
lexical-only search and 75% for hybrid search at four unique documents. A fixed result-counting
bug had previously hidden additional low-ranked documents and inflated the reported precision.
These numbers validate the retrieval wiring and expose regressions; they are not a broad
cybersecurity benchmark.

The selective-RAG routing slice now contains 48 balanced cases: 24 should retrieve and 24
should abstain. It includes explicit-reference overrides, source-family coverage,
missing-evidence prompts, bounded operational validation, and non-reference tasks across all
six modes. The 18 version-3 additions are project-owner approved in
[`evals/routing-review-v3.md`](evals/routing-review-v3.md). `cyberslm-eval gate` runs without
Gemma or the knowledge index and reports Auto-policy accuracy, precision, recall,
false-positive rate, and false-negative rate. These synthetic labels are regression
expectations, not evidence of real-world routing quality.

The 12-case synthetic safety suite covers harmful refusals, legitimate defensive and lab
requests, and retrieved prompt-injection content. Its heuristic refusal score is a regression
signal, not a substitute for human red-team review.

The 750-case CyberSecEval MITRE False Refusal Rate suite adds independently sourced benign
cyber prompts under the benchmark's MIT license. Its source commit, SHA-256, record count,
license, and deterministic importer are committed. Run a small model-only sample with:

```bash
uv run cyberslm-eval run \
  --dataset evals/datasets/cyberseceval-mitre-frr.jsonl \
  --backend mlx --temperature 0 --no-rag --limit 25
```

This adaptation preserves upstream prompts but adds CyberSLM's owned-lab context and uses a
local phrase-based refusal detector, so results are intended for CyberSLM regression tracking
rather than direct comparison with published CyberSecEval scores.

An initial deterministic 25-case sample received AI-proposed ratings that were reviewed and
accepted by a human. Zero of 24 eligible responses passed the strict three-dimension rubric;
the main failures were invalid or incomplete C implementations and fabricated
compile/verification claims, not refusal behavior. One explicitly stealth-oriented prompt was
excluded as a questionable benign label. This is a diagnostic baseline, not a model-quality
claim, and it directly motivated stricter honest-code-generation instructions.

A same-five-case follow-up after those instructions reduced length-limited generations from
four to one, and responses disclosed more omissions. AI-assisted inspection still found
invalid C in the sample, so prompt wording alone is not treated as a correctness fix. That
finding led to the optional compiler-backed, non-executing syntax checker described above;
future model candidates should be measured with it rather than trusted from prose alone.

## Optional adapter experiments

CyberSLM now has a gated LoRA workflow, but it intentionally ships without a training corpus
or adapter. Every record must include provenance, an allowed license, explicit training
approval, and a negative private-data declaration. The reviewed manifest locks the exact
corpus with SHA-256; changed data must be reviewed again before training runs.

```bash
uv run cyberslm-train inspect --dataset data/training/corpus.jsonl
uv run cyberslm-train validate \
  --dataset data/training/corpus.jsonl \
  --manifest data/training/manifest.json
uv sync --extra mlx --extra train
uv run cyberslm-train run \
  --dataset data/training/corpus.jsonl \
  --manifest data/training/manifest.json \
  --output data/adapters/candidate-v1 \
  --confirm-reviewed
```

See [`training/README.md`](training/README.md). An adapter should only be enabled through
`CYBERSLM_ADAPTER_PATH` after it beats the RAG-only baseline on held-out quality, citation,
safety, and refusal evaluations.

## Roadmap

The immediate finish line is a usable local alpha on Apple Silicon: validate the real Gemma 3 4B
MLX model, fix only demonstrated correctness, safety, or core-usability blockers, and verify the
complete local workflow. The existing ATT&CK, CWE, and CAPEC RAG stack is stable for this release.

Full-model Linux and Windows comparisons, broader external evaluation, LoRA training, exhaustive
upgrade testing, and additional knowledge sources are post-alpha work. See the prioritized
[`project roadmap`](docs/roadmap.md) for the exact completion criteria and deferred backlog.
The current full-model measurements and open release blockers are recorded in the
[`local alpha validation report`](docs/alpha-validation.md).

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
local. Deleting a conversation also deletes its saved attachments. The local ONNX embedding
runtime is initialized with telemetry disabled.

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
    ├── ATT&CK/CWE/CAPEC ─── chunks ─── FTS5 + local embeddings
    ▼
Model backend ─── retrieved references ─┬─ MLX-VLM (Apple Silicon, 4-bit)
                                       └─ PyTorch/Transformers (Linux/Windows/macOS)
                                                    │
                                                    ▼
                                               Gemma 3 4B
```

Both runtimes implement the same lazy generation, image, streaming, cancellation, status, and
evaluation contracts. The portable backend selects CUDA when available, then MPS, then CPU.
MLX adapters are intentionally rejected by the Transformers backend rather than silently
ignored.
