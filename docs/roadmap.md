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

## Active backlog

Work should proceed in this order:

1. **Add cross-platform local inference.** Keep MLX acceleration on Apple Silicon, define a
   backend interface, add a local backend suitable for Linux and Windows, add PowerShell and
   portable launch/setup paths, update the doctor command, and exercise supported platforms in
   CI. Do not add a required hosted-model service.
2. **Broaden model-quality evaluation.** Add independently sourced coverage beyond the current
   false-refusal suite, use the existing non-executing compiler check for generated C candidates,
   and retain human review for correctness and operational safety.
3. **Run one controlled adapter experiment.** Assemble a separately licensed, provenance-tracked,
   human-approved training corpus. Adopt a LoRA adapter only if it beats the RAG-only baseline on
   held-out quality, citation, safety, and refusal evaluations.
4. **Harden upgrades and releases.** Add explicit backup restoration tests and database migration
   matrices. Enable private-repository provenance attestations only if the project moves to GitHub
   Enterprise Cloud.

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
