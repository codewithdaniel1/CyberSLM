# CyberSLM evaluations

This directory contains reproducible evaluation inputs. Generated reports go in `results/`
and are intentionally ignored by Git because they include complete model responses.

The bundled `datasets/smoke.jsonl` suite is synthetic and checks evaluation plumbing plus
basic cybersecurity concepts. `datasets/cyberseceval-mitre-frr.jsonl` adds a larger external
false-refusal suite. `datasets/selective-rag.jsonl` contains balanced synthetic labels for the
Auto RAG gate. `datasets/mode-coverage.jsonl` is a balanced 24-case AI-authored draft spanning
all six modes and four quality dimensions. None is evidence that CyberSLM outperforms another model. Claims
require broader independently sourced datasets, contamination controls, multiple runs, and
human review.

## Balanced mode-coverage draft

`mode-coverage.jsonl` contains one case for every mode/dimension pairing: six modes crossed
with correctness, groundedness, prompt-injection resistance, and safety-boundary behavior.
Generation reports summarize results by both category and mode so a strong aggregate cannot
hide a weak specialist mode.

The project owner reviewed and approved the initial 24 cases on 2026-09-04, so each is marked
`human-approved`. Any new or materially edited case must use `pending-human-review` until a
human checks its prompt, authorization context, expected concepts, prohibited terms, expected
behavior, passing threshold, and safety. AI-authored labels alone are not independent review.

The first deterministic Gemma model-only run used temperature 0, a 1,024-token ceiling, and
no RAG. Deterministic scoring passed 16/24 cases (66.7%), safety behavior passed 24/24 with no
false refusals, and one response hit the token limit. Some prompt-injection cases safely quoted
their planted marker and therefore failed the intentionally strict prohibited-term check, so
these keyword scores must be read alongside qualitative review.

The project owner accepted the initial AI-assisted qualitative review, which passes 7/24 under
the strict rule that every dimension must score at least 3/4. Its means are 2.04 correctness,
2.71 task completion, and 3.04 operational safety.

A first prompt-hardening candidate targets fabricated observations, guessed mappings, embedded
instructions, scope changes, and destructive validation. Its deterministic keyword pass rate
is 15/24 (62.5%), down one case, while truncations improve from one to zero and safety behavior
remains 24/24. The project owner accepted its AI-assisted qualitative review: strict passes
improve from 7/24 to 9/24 and mean correctness rises from 2.04 to 2.17, while mean operational
safety falls from 3.04 to 2.96.

The matched Auto-RAG run searches 5/24 cases and uses references in all five. The four cases
with expected references achieve 100% recall and precision, safety behavior remains 24/24,
and deterministic scoring improves to 16/24 (66.7%). The project owner accepted its
AI-assisted qualitative review at 8/24, one below the model-only control, because the model
sometimes treats relevant background material as incident-specific evidence.

That run's apparent 100% citation coverage was a measurement defect: the scorer counted the
numbered source-disclosure footer that CyberSLM appends after generation. Citation scoring now
examines only the answer body. A stricter grounded-background candidate retained 100% retrieval
recall and precision and 24/24 safety behavior, but scored 15/24 deterministically and produced
no valid inline citations across the five RAG cases. Its prompt reduced one real-secret path
probe to a synthetic canary, but Gemma still over-applied ATT&CK background and suggested
destructive SQL examples. Treat this as a diagnosed model/context-use limitation, not a RAG
quality win. The project owner approved its AI-assisted qualitative review at 8/24, with means
of 2.17 correctness, 2.50 task completion, and 2.92 operational safety.

A selective-abstention candidate keeps RAG for DNS, path traversal, and use-after-free, but
skips it for an alert with explicitly missing telemetry and SQL validation that forbids data
access or mutation. Explicit ATT&CK, CWE, CAPEC, and exact-ID requests still override
abstention. The matched run restores 16/24 deterministic passes, scores all five labeled
routing decisions and all three expected reference sets correctly, preserves 24/24 safety
behavior, and has no length-limited responses. The AI-assisted qualitative draft improves to
10/24, with means of 2.29 correctness, 2.58 task completion, and 3.04 operational safety. The
project owner approved both the five generation-routing labels and the qualitative review.
Genuine inline citation coverage remains 0/3.

Two focused prompt-only citation experiments reached 2/3 and 1/3 coverage, respectively, but
misplaced one citation and degraded technical answer quality. Neither prompt was adopted.
Instead, the application footer now reports the inline-citation count and the stricter exact-ID
citation count. The latter requires a source number after that source's exact ATT&CK/CWE/CAPEC
identifier on the same line. The focused verifier run correctly reports 0/3 exact-ID
attributions for the adopted prompt. Each retrieved source is also labeled as exact-ID cited,
exact-ID mentioned without a linked citation, citation present without a linked identifier, or
not explicitly referenced. These labels are deterministic post-generation assistance: they do
not edit the answer, do not count as model-authored citations, and do not establish that a
surrounding claim is entailed by the source.

Generation reports now retain the exact retrieved passage and its SHA-256. The separate
claim-support workflow extracts answer spans containing a retrieved source's identifier or
citation number and pairs each span with that passage for human review. Extraction is
deterministic, but support verdicts are not: a reviewer must choose supported, partially
supported, unsupported, not a factual claim, or unable to assess. References with no linked
answer span remain visible as attribution gaps rather than being silently excluded.

The first six-case claim-support run preserved three exact retrieved passages and extracted two
source-linked mapping spans. The project owner approved the AI-assisted review: both spans are
only partially supported because the passages define the ATT&CK/CWE taxonomy but do not, by
themselves, establish the case-specific mapping. The CWE-22 passage had no linked answer span.
The strict fully-supported rate is therefore 0/2; this tiny diagnostic sample is not a general
groundedness score. It does not justify automatic citation repair.

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
- `expected_retrieval`: optional boolean label for whether Auto should query local knowledge
- `minimum_score`: passing fraction, between 0 and 1
- `prohibited_terms`: optional terms that force a failure when present
- `expected_behavior`: optional `refuse_harmful` or `answer_safely` safety expectation
- `images`: optional paths relative to the dataset file
- `authorization_context`: optional user-provided environment context; defaults to `unspecified`
- `metadata`: optional provenance or notes

Expected concepts are transparent, deterministic plumbing checks. They do not measure
factuality, reasoning quality, calibration, or whether advice is operationally safe.

Each report records the dataset hash and a hash of CyberSLM's complete prompt contract,
including mode instructions and the retrieved-background wrapper. The contract version and
knowledge-instruction hash are also stored explicitly so comparisons reveal incompatible
prompt conditions.

## Commands

Validate the dataset:

```bash
uv run cyberslm-eval validate
uv run cyberslm-eval validate --dataset evals/datasets/retrieval.jsonl
uv run cyberslm-eval validate --dataset evals/datasets/selective-rag.jsonl
uv run cyberslm-eval validate --dataset evals/datasets/safety.jsonl
uv run cyberslm-eval validate --dataset evals/datasets/mode-coverage.jsonl
uv run cyberslm-eval validate --dataset evals/datasets/cyberseceval-mitre-frr.jsonl
```

Benchmark retrieval without loading Gemma:

```bash
uv run cyberslm-eval gate
uv run cyberslm-eval retrieve
uv run cyberslm-eval retrieve --lexical-only
```

The gate benchmark also runs without a knowledge index. It measures the deterministic Auto
decision against 24 should-retrieve and 24 should-skip labels, reporting the confusion matrix,
accuracy, precision, recall, and false-positive/false-negative rates. The 18 version-3
additions contribute three prompts per mode and are project-owner approved in
[`routing-review-v3.md`](routing-review-v3.md). These synthetic cases are regression coverage;
they are not a real-world routing-quality claim.

Retrieval reports record recall, precision, exact-reference coverage, latency, retrieval method,
embedding configuration, knowledge versions, and a report integrity hash. Generation reports
also record expected-reference retrieval, inline answer-body citation coverage, per-reference
attribution status, exact-ID attribution coverage, unmapped citations, and heuristic refusal
behavior when the dataset supplies those expectations. The automatically appended
source-disclosure footer is excluded from citation and attribution coverage. Saved knowledge
records retain their external IDs, exact retrieved passages, and passage hashes so attribution
and claim-support results remain auditable. Human review should back the structural and safety
heuristics before either is used for a release decision.

Generation cases may additionally provide `expected_retrieval`. Auto-policy reports score the
routing decision separately from retrieved-reference accuracy, so an intentional abstention is
not mislabeled as a search failure. Forced `on` runs still score any supplied
`expected_references`.

Run the local Gemma baseline deterministically:

```bash
uv run cyberslm-eval run --backend mlx --temperature 0
uv run cyberslm-eval run --dataset evals/datasets/mode-coverage.jsonl \
  --backend mlx --temperature 0 --rag-policy auto
uv run cyberslm-eval run --dataset evals/datasets/mode-coverage.jsonl \
  --backend mlx --temperature 0 --rag-policy off
```

`run` defaults to `--rag-policy auto`, using the same per-message decision function and source
routing as chat. `--rag-policy on` forces retrieval for every case, while `--rag-policy off`
creates a model-only control. The legacy `--no-rag` flag remains an alias for `off`. Reports
record the policy, reason, selected source families, attempted state, and actual document use
for every case, plus aggregate routing counts.

Create and summarize a claim-support review for a new RAG report:

```bash
uv run cyberslm-eval support-review init evals/results/REPORT.json
uv run cyberslm-eval support-review summarize \
  evals/results/REPORT-support-review.json \
  --output evals/results/REPORT-support-review-summary.json
```

The init command intentionally rejects older reports that did not capture exact retrieved
passages. Fill in the reviewer, timezone-aware review time, verdict, and required notes before
summarizing.

Start with a small deterministic external sample before running all 750 cases:

```bash
uv run cyberslm-eval run \
  --dataset evals/datasets/cyberseceval-mitre-frr.jsonl \
  --backend mlx --temperature 0 --no-rag --limit 25
```

Remove `--limit 25` for the full suite. Reports include `false_refusals`,
`false_refusal_rate`, finish reasons, and length-limited generation rates.

The first 25-case deterministic sample was scored with an AI-assisted draft subsequently
reviewed and accepted by a human. The strict rubric found zero passing responses among 24
eligible cases, with correctness and task completion dominated by invalid APIs, incomplete
security-control implementations, and unverified compile claims. One explicitly
stealth-oriented prompt was marked questionable and excluded. Treat this as a diagnostic
baseline for prompt and model improvements, not a general benchmark result.

After strengthening the honest-code prompt, a deterministic rerun of the same first five cases
reduced length-limited generations from four to one. AI-assisted inspection still identified
invalid C, so this is evidence of better completion behavior only—not correctness. Future
candidates must pass compiler-backed syntax checks and human review.

When the local knowledge index is populated, evaluations use selective Auto RAG by default
and record the source versions and hashes in the report. Use `--rag-policy off` for a
model-only control run.

Exercise the harness without loading a model:

```bash
uv run cyberslm-eval run --backend mock --output evals/results/mock.json
```

Compare two runs:

```bash
uv run cyberslm-eval compare evals/results/baseline.json evals/results/candidate.json
```

Create and score a private human-review worksheet:

```bash
uv run cyberslm-eval review init evals/results/candidate.json
uv run cyberslm-eval review summarize evals/results/candidate-review.json \
  --output evals/results/candidate-review-summary.json
```

The worksheet uses anchored 1–4 ratings for correctness, task completion, and operational
safety. It also requires a label-quality decision so questionable benchmark cases can be
reported without distorting aggregate scores. See `review-rubric.md` for the complete guide.
