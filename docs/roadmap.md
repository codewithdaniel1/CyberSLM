# CyberSLM roadmap

Status: 2026-09-07

This is the single prioritized backlog for CyberSLM. Detailed evaluation notes remain in
`evals/`, but they do not define the order of product work.

## Current checkpoint

The v0.5 local RAG phase is complete for now. The production path uses only the pinned MITRE
ATT&CK, CWE, and CAPEC sources. It includes selective Auto/On/Off routing, hybrid FTS5 and local
embedding retrieval, source previews, source-disclosure footers, citation diagnostics, verified
rebuilds, and reproducible evaluations.

The closeout checks on 2026-09-07 reported:

- all three source files and index manifests verified;
- 2,200 documents, 4,096 passages, and 4,096/4,096 local embeddings present;
- 48/48 selective-routing cases correct; and
- the established hybrid retrieval baseline unchanged at 15/20 expected-reference cases (75%).

The retrieval suite is synthetic regression coverage, not a claim of broad production quality.
OWASP remains an isolated opt-in pilot and is not used by normal chat, sync, verification, or
background rebuilds.

## Alpha finish line

The immediate goal is a good working local CyberSLM on the current Apple Silicon development
machine. Work should proceed in this order:

1. **Validate the real model.** Current evidence is recorded in
   [`alpha-validation.md`](alpha-validation.md).
   - [x] Run the full `mlx-community/gemma-3-4b-it-4bit` checkpoint against the six-case cyber
     benchmark at the normal 1,024-token limit.
   - [x] Run the same cases through the production Auto-RAG path.
   - [x] Inspect every response for correctness, completion, safety, retrieval use, and citation
     behavior.
   - [x] Compare the temporary Gemma 3 12B MLX checkpoint and remove its isolated 7.5 GB cache.
     Its higher automatic score did not survive manual factual review, so the default remains 4B.
   - [x] Resolve the reproduced safety and factual-accuracy blockers and approve the guarded 4B
     model-response baseline for end-to-end alpha verification.
2. **Fix demonstrated release blockers.**
   - [x] Prevent artificial 128-token benchmark truncation.
   - [x] Add bounded deterministic Base64 analysis after confirming that the 4B model decoded the
     test value incorrectly even with a minimal prompt.
   - [x] Remove upstream CWE `[REF-*]` bibliography markers from model context so they cannot be
     mistaken for CyberSLM citations.
   - [x] Block the demonstrated sensitive-target SSRF instructions before answer release; prompt
     wording alone did not.
   - [x] Correct the demonstrated failed-SSH ATT&CK mapping, Python SQL fix, and PowerShell 4104
     interpretation with narrow, transparent deterministic rules.
   - [x] Re-run the guarded production Auto-RAG suite with the default 4B model and manually
     approve all six released responses. The result was 5/6 automatic passes and 6/6 accepted by
     manual review; the remaining miss was a Base64 phrasing false negative.
3. **Ship a local alpha.**
   - [ ] Verify setup and startup on this Mac.
   - [ ] Verify text chat, image chat, selective RAG, conversation persistence, and deletion.
   - [ ] Verify clean shutdown and restart with saved data.
   - [ ] Update the final user documentation and tag the first usable local alpha.

The alpha is complete when these three steps pass. It does not require fine-tuning, additional
knowledge sources, exhaustive external evaluations, or validation on every supported platform.

## Post-alpha backlog

These projects are useful, but they do not block the local alpha:

1. Validate the full Gemma 3 4B Transformers runtime on representative Linux and Windows hardware
   and compare unquantized, 8-bit, and 4-bit performance and quality. The portable implementation,
   CI smoke coverage, memory modes, and benchmark tooling are already complete.
2. Broaden independently sourced model-quality evaluations beyond the current suites, including
   generated-code checks and retained human review.
3. Run one controlled LoRA experiment with a separately licensed, provenance-tracked,
   human-approved corpus. Adopt an adapter only if it beats the RAG-only baseline without weakening
   safety, citation, or refusal behavior.
4. Add exhaustive backup-restoration tests, database migration matrices, clean-machine release
   testing, and any future enterprise provenance attestations.

## Deferred RAG backlog

These items are deliberately postponed and do not block other work:

1. Review or revise the 24 OWASP pilot labels and the six-case claim-support draft.
2. Run a broader held-out OWASP answer-quality comparison and decide whether to admit it or keep
   it as a developer-only pilot.
3. Pilot MITRE D3FEND as a pinned defensive-technique source.
4. Pilot CISA KEV as an exact-CVE local lookup rather than default semantic context.
5. Revisit NVD, OSV, Sigma, EPSS, or NIST OSCAL only when a concrete product mode needs them.

When RAG work resumes, every new source must still pass the provenance, licensing, parser,
held-out retrieval, attribution, safety, and regression gates in
[`knowledge-source-evaluation.md`](knowledge-source-evaluation.md).

## Explicitly out of scope for now

- Training on private conversations or uploads
- Automatically enabling experimental knowledge sources
- Requiring an MCP or agent harness for normal chat
- Requiring a hosted model or external request during chat
