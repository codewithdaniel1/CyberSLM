# Local alpha model validation

Status: In progress as of 2026-09-07

This document records the evidence used to decide whether the local CyberSLM alpha is ready. It
does not treat automatic keyword scores as proof of correctness or safety.

## Environment and model

- Apple Silicon development Mac with 16 GiB unified memory
- `mlx-community/gemma-3-4b-it-4bit`
- MLX backend, temperature 0, maximum 1,024 generated tokens
- Six-case `evals/datasets/smoke.jsonl` suite

Generated reports remain private under `evals/results/` because they contain complete model
responses and machine details.

## Baselines

The model-only benchmark completed all six responses without truncation:

- 3/6 deterministic concept passes, 0.5520 mean score;
- 7.34-second cached model load;
- 34.72 aggregate generated tokens per second; and
- approximately 0.95 GB process-RSS increase immediately after model loading.

The matched production Auto-RAG run retrieved for five of six cases:

- 5/6 deterministic concept passes, 0.6758 mean score;
- 100% expected-reference recall, with 41.7% precision at four passages; and
- 0/5 cases with complete exact-ID citation attribution.

A focused prompt-contract candidate retained 5/6 deterministic passes and raised the mean score
to 0.7091. It improved the XSS/CSRF distinction and failed-login triage, and it prevented upstream
CWE bibliography labels from being copied as if they were CyberSLM citations. It did not solve
the remaining SSRF or exact-transformation failures by prompt wording alone.

Reducing RAG from four passages to two raised expected-reference precision to 66.7%, but lowered
the deterministic pass rate to 4/6 and produced a worse SQL-injection verification instruction.
The production default therefore remains four passages.

## Manual findings

Useful behavior:

- Auto RAG corrected the primary failed-login mapping to ATT&CK T1110 and prompted a check for
  successful authentication.
- The model identified SQL injection and gave a parameterized-query fix.
- Responses stopped naturally at the normal token limit and performance was usable on this Mac.

Release blockers:

- The 4B model failed to return a simple Base64 result and produced the wrong decoded value even
  under a minimal model-only prompt. A bounded local decoder now supplies the exact inert result;
  a focused generation correctly returned `flag{base64_is_encoding}` afterward.
- The model proposed reading `/etc/passwd` to validate SSRF despite repeated instructions to use
  only controlled canaries. This remains an unresolved safety blocker.
- One RAG response selected CWE-564 for a basic SQL-injection example even though the top retrieved
  source was CWE-89.
- PowerShell event 4104 explanations omitted the key Script Block Logging distinction and invented
  or overstated event fields and execution conclusions.
- Retrieved facts were rarely linked to the required numbered citations, so source footers remain
  disclosure diagnostics rather than proof that each claim is supported.

## Decision

Do not tag the alpha yet. The next decision is whether to add a deterministic output safety gate
for the 4B model or evaluate a stronger local checkpoint. More prompt wording is not considered a
credible fix because matched focused tests repeatedly ignored the no-secret-file constraint.
