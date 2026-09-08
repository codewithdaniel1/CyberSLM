# Local alpha model validation

Status: Approved for `v0.5.0a1` on 2026-09-08

This document records the evidence used to decide whether the local CyberSLM alpha is ready. It
does not treat automatic keyword scores as proof of correctness or safety.

## Environment and models

- Apple Silicon development Mac with 16 GiB unified memory
- Primary model: `mlx-community/gemma-3-4b-it-4bit`
- Temporary comparison model: `mlx-community/gemma-3-12b-it-4bit`
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

### Temporary 12B comparison

The 12B checkpoint was downloaded into a dedicated temporary Hugging Face cache, evaluated, and
then removed. Its cache occupied 7.5 GB on disk; the normal 4B cache was not changed.

The model-only run reported:

- 4/6 deterministic concept passes and a 0.7357 mean score;
- 12.94 aggregate generated tokens per second; and
- six natural stop completions with no token-limit truncation.

The reported 219.29-second load time includes the first model download and is not a cached-load
measurement. The process-RSS figures also do not capture the full MLX unified-memory allocation,
so neither value should be used as a memory-fit claim.

The matched production Auto-RAG run reported 6/6 deterministic passes and a 0.7869 mean score,
with 100% expected-reference recall and 41.7% precision at four passages. Exact-ID attribution
remained poor: 0/5 source-using cases were complete, overall exact-ID coverage was 10%, and four
cases required claim-support review.

Manual review overruled the apparent 6/6 result. Auto RAG corrected the SSH mapping to T1110.001,
and the 12B response used a synthetic SSRF canary without suggesting real secret files. However,
the PowerShell response falsely claimed event 4104 records a PowerShell profile load and profile
path; event 4104 is Script Block Logging and normally contains script-block content. The SSH
canary explanation and SQL verification wording also contained unsupported conclusions. The
automatic concept score detected required words, but not these contradictions.

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
- Before the response guard, the model proposed reading `/etc/passwd` to validate SSRF despite
  repeated instructions to use only controlled canaries. The guard now blocks the reproduced
  affirmative sensitive-target patterns before release.
- One RAG response selected CWE-564 for a basic SQL-injection example even though the top retrieved
  source was CWE-89.
- PowerShell event 4104 explanations omitted the key Script Block Logging distinction and invented
  or overstated event fields and execution conclusions.
- Retrieved facts were rarely linked to the required numbered citations, so source footers remain
  disclosure diagnostics rather than proof that each claim is supported.

## Decision

Do not change the default to the 12B checkpoint. The stronger model improved the small automatic
score and SSRF behavior, but it was substantially slower and still produced a release-blocking
Windows event error when grounded with local sources. Its temporary cache has been deleted as
planned.

The deterministic post-generation guard is now implemented for the specific demonstrated
blockers. It buffers output before release, replaces affirmative sensitive-target SSRF tests,
corrects failed-only SSH mappings, supplies the verified PowerShell 4104 interpretation, and
provides a driver-aware fix for the evaluated Python SQL interpolation pattern. The guard is
transparent in API and evaluation metadata and is documented in
[`response-guard.md`](response-guard.md).

The final guarded production Auto-RAG run with the default 4B model reported:

- 5/6 deterministic concept passes and a 0.9111 mean score;
- 13.86-second mean generation latency, with six natural stop completions;
- 100% expected-reference recall and 41.7% precision at four passages; and
- four guarded answers: failed-SSH mapping, Python SQL parameterization, PowerShell 4104, and
  sensitive-target SSRF validation.

The remaining automatic failure was a rubric false negative. The CTF answer returned the exact
`flag{base64_is_encoding}` value and correctly said Base64 is “not a method of encryption,” while
the scorer required the contiguous phrase “not encryption,” “no secret key,” or “reversible.”
Manual review accepted all six released answers. The model-response baseline is approved for the
end-to-end local alpha checks, but the alpha should not be tagged until setup, chat, image,
persistence, deletion, shutdown, and restart have been verified.

## End-to-end local acceptance

The macOS setup script completed successfully with Python 3.12 and the MLX runtime. Two complete
startup cycles then ran through `start.sh` against a temporary data root and a copied, verified
knowledge index. The normal repository conversations, uploads, knowledge database, and cached 4B
model were not modified by the acceptance chats.

The acceptance run verified:

- API and Streamlit health on isolated localhost ports;
- a real streamed text answer from `mlx-community/gemma-3-4b-it-4bit` with knowledge Off;
- a real streamed image answer that correctly identified a generated red test image;
- Auto retrieval selecting four ATT&CK passages for an explicit failed-SSH mapping;
- On retrieval forcing four ATT&CK passages for a generic phishing question;
- durable user and assistant messages across a clean stop and second startup;
- conversation deletion returning 404 afterward and removing its stored image;
- deletion of the remaining acceptance conversations after restart; and
- clean shutdown with no API or UI listener left behind and no API traceback or error in the
  startup log.

Forced retrieval behaved as designed but illustrated why Auto remains the default: the generic
phishing prompt received several weakly relevant ATT&CK passages, and the 4B model did not produce
valid numbered inline citations. This is a known quality limitation, not a persistence or routing
failure.

After the run, Ruff passed, all 117 tests passed, Bash startup/setup syntax checks passed, and both
the source distribution and wheel built successfully. The 236 MB temporary acceptance data copy
was removed after its results were recorded.

The in-app browser controller was unavailable during automated acceptance. Streamlit served its
HTML and health endpoint, and the light theme remained covered by configuration and regression
tests. The project owner completed the final visual spot-check on 2026-09-08 and approved the UI
for the first alpha.
