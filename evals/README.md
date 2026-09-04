# CyberSLM evaluations

This directory contains reproducible evaluation inputs. Generated reports go in `results/`
and are intentionally ignored by Git because they include complete model responses.

The bundled `datasets/smoke.jsonl` suite is synthetic and checks evaluation plumbing plus
basic cybersecurity concepts. `datasets/cyberseceval-mitre-frr.jsonl` adds a larger external
false-refusal suite. Neither is evidence that CyberSLM outperforms another model. Claims
require broader independently sourced datasets, contamination controls, multiple runs, and
human review.

## External source

The 750-case `cyberseceval-mitre-frr.jsonl` dataset is deterministically derived from Meta's
[PurpleLlama CyberSecEval MITRE False Refusal Rate data](https://github.com/meta-llama/PurpleLlama/blob/4be64c3a24442b51c76175e6ec67722cc3f5fe38/CybersecurityBenchmarks/datasets/mitre_frr/mitre_frr.json):

| Field | Pinned value |
| --- | --- |
| Upstream commit | `4be64c3a24442b51c76175e6ec67722cc3f5fe38` |
| Upstream SHA-256 | `7a9b400bdf5ddbb36d5e7c3e8f6b5adb5d13125b8d03be66fd252a0f20b79d15` |
| Records | 750 benign prompts |
| License | [MIT](https://github.com/meta-llama/PurpleLlama/blob/4be64c3a24442b51c76175e6ec67722cc3f5fe38/CybersecurityBenchmarks/LICENSE); copied to `evals/licenses/PurpleLlama-CybersecurityBenchmarks-MIT.txt` |

The importer preserves each prompt and its upstream metadata, adds CyberSLM's `owned_lab`
authorization context, assigns Secure Code mode, and scores only whether the model refuses a
benign prompt. It does not invent reference answers or correctness labels. Because CyberSLM
uses its own simple phrase-based refusal detector and additional system prompt, its
false-refusal rate is useful for local regression testing but is not directly comparable to
scores published with the upstream CyberSecEval runner.

Refusal matches are retained per case for auditability. The detector normalizes Markdown and
looks for explicit first-person refusal language within the opening 800 characters, avoiding
late caveats after a substantive answer; it remains a deterministic heuristic, not a semantic
judge. Generation reports also preserve the runtime's finish reason, prompt and generated
token counts, configured token ceiling, and aggregate length-limited rate.

The generated dataset is committed so CI never depends on network access. Reconstruct it from
the pinned source and verify it against the schema with:

```bash
uv run cyberslm-eval sync --source purplellama-mitre-frr
uv run cyberslm-eval validate --dataset evals/datasets/cyberseceval-mitre-frr.jsonl
```

Sync fails if the download hash, record count, or benign labels differ from the committed
source manifest in `src/cyberslm/evaluation/sources.py`.

## Dataset format

Each JSONL object contains:

- `id`: stable unique case identifier
- `category`: reporting category
- `mode`: one of CyberSLM's supported modes
- `prompt`: exact model input
- `expected_concepts`: groups of acceptable terms; may be empty for behavior-only cases
- `expected_references`: optional ATT&CK, CWE, or CAPEC identifiers for retrieval scoring
- `minimum_score`: passing fraction, between 0 and 1
- `prohibited_terms`: optional terms that force a failure when present
- `expected_behavior`: optional `refuse_harmful` or `answer_safely` safety expectation
- `images`: optional paths relative to the dataset file
- `authorization_context`: optional user-provided environment context; defaults to `unspecified`
- `metadata`: optional provenance or notes

Expected concepts are transparent, deterministic plumbing checks. They do not measure
factuality, reasoning quality, calibration, or whether advice is operationally safe.

Each report records the dataset and CyberSLM mode-prompt hashes so comparisons reveal when
either evaluation inputs or system instructions changed.

## Commands

Validate the dataset:

```bash
uv run cyberslm-eval validate
uv run cyberslm-eval validate --dataset evals/datasets/retrieval.jsonl
uv run cyberslm-eval validate --dataset evals/datasets/safety.jsonl
uv run cyberslm-eval validate --dataset evals/datasets/cyberseceval-mitre-frr.jsonl
```

Benchmark retrieval without loading Gemma:

```bash
uv run cyberslm-eval retrieve
uv run cyberslm-eval retrieve --lexical-only
```

Retrieval reports record recall, precision, exact-reference coverage, latency, retrieval method,
embedding configuration, knowledge versions, and a report integrity hash. Generation reports
also record expected-reference retrieval, citation coverage, and heuristic refusal behavior
when the dataset supplies those expectations. Human review should back the safety heuristic
before it is used for a release decision.

Run the local Gemma baseline deterministically:

```bash
uv run cyberslm-eval run --backend mlx --temperature 0
```

Start with a small deterministic external sample before running all 750 cases:

```bash
uv run cyberslm-eval run \
  --dataset evals/datasets/cyberseceval-mitre-frr.jsonl \
  --backend mlx --temperature 0 --no-rag --limit 25
```

Remove `--limit 25` for the full suite. Reports include `false_refusals`,
`false_refusal_rate`, finish reasons, and length-limited generation rates.

When the local knowledge index is populated, evaluations include RAG by default and record
the source versions and hashes in the report. Use `--no-rag` for a model-only control run.

Exercise the harness without loading a model:

```bash
uv run cyberslm-eval run --backend mock --output evals/results/mock.json
```

Compare two runs:

```bash
uv run cyberslm-eval compare evals/results/baseline.json evals/results/candidate.json
```
