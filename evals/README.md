# CyberSLM evaluations

This directory contains reproducible evaluation inputs. Generated reports go in `results/`
and are intentionally ignored by Git because they include complete model responses.

The bundled `datasets/smoke.jsonl` suite is synthetic and checks evaluation plumbing plus
basic cybersecurity concepts. It is **not** evidence that CyberSLM outperforms another
model. Claims require larger, independently sourced datasets, contamination controls,
multiple runs, and human review.

## Dataset format

Each JSONL object contains:

- `id`: stable unique case identifier
- `category`: reporting category
- `mode`: one of CyberSLM's supported modes
- `prompt`: exact model input
- `expected_concepts`: groups of acceptable terms; one match per group earns credit
- `expected_references`: optional ATT&CK, CWE, or CAPEC identifiers for retrieval scoring
- `minimum_score`: passing fraction, between 0 and 1
- `prohibited_terms`: optional terms that force a failure when present
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
```

Benchmark retrieval without loading Gemma:

```bash
uv run cyberslm-eval retrieve
uv run cyberslm-eval retrieve --lexical-only
```

Retrieval reports record recall, precision, exact-reference coverage, latency, retrieval method,
embedding configuration, knowledge versions, and a report integrity hash. Generation reports
also record expected-reference retrieval and citation coverage when the dataset provides
`expected_references`.

Run the local Gemma baseline deterministically:

```bash
uv run cyberslm-eval run --backend mlx --temperature 0
```

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
