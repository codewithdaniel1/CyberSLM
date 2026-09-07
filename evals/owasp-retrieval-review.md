# OWASP pilot retrieval review

Status: **Pending project-owner review**

Dataset SHA-256: `39367fd4020d5aa29b82a4544d2cb3bfd504f16e42be8f7463a6597015ee0793`

This worksheet covers the 24 AI-authored cases in
[`datasets/owasp-retrieval-pilot.jsonl`](datasets/owasp-retrieval-pilot.jsonl). Each case targets
one allowlisted OWASP Cheat Sheet. Review whether the prompt is natural, the expected document
is the best primary reference, the rationale is sound, and the case does not disclose its answer
through a synthetic identifier.

The cases intentionally use General mode so the benchmark can search the temporary candidate
alongside all three admitted sources without changing production routing. The evaluation expects
one primary OWASP document but retrieves four potentially complementary results, so 25% precision
is the maximum possible under this single-reference labeling when all four slots are populated.
Each case also has a provisional `expected_retrieval: true` label so the pilot router can be
measured. These labels remain AI-authored and pending project-owner review.

## Proposed labels

| ID | Intended primary reference |
| --- | --- |
| `owasp-authentication-enumeration` | Authentication Cheat Sheet |
| `owasp-authorization-server-side` | Authorization Cheat Sheet |
| `owasp-business-logic-order` | Business Logic Security Cheat Sheet |
| `owasp-csrf-cookie-post` | Cross-Site Request Forgery Prevention Cheat Sheet |
| `owasp-xss-context-encoding` | Cross Site Scripting Prevention Cheat Sheet |
| `owasp-crypto-storage-keys` | Cryptographic Storage Cheat Sheet |
| `owasp-untrusted-deserialization` | Deserialization Cheat Sheet |
| `owasp-error-stack-trace` | Error Handling Cheat Sheet |
| `owasp-file-upload-images` | File Upload Cheat Sheet |
| `owasp-forgot-password-token` | Forgot Password Cheat Sheet |
| `owasp-security-headers` | HTTP Security Response Headers Cheat Sheet |
| `owasp-injection-code-data` | Injection Prevention Cheat Sheet |
| `owasp-input-validation-allowlist` | Input Validation Cheat Sheet |
| `owasp-jwt-validation` | JSON Web Token Cheat Sheet |
| `owasp-security-logging` | Logging Cheat Sheet |
| `owasp-command-injection-api` | OS Command Injection Defense Cheat Sheet |
| `owasp-password-storage-argon2` | Password Storage Cheat Sheet |
| `owasp-rest-api-baseline` | REST Security Cheat Sheet |
| `owasp-sql-parameterization` | SQL Injection Prevention Cheat Sheet |
| `owasp-secrets-lifecycle` | Secrets Management Cheat Sheet |
| `owasp-ssrf-url-fetcher` | Server Side Request Forgery Prevention Cheat Sheet |
| `owasp-session-cookie-rotation` | Session Management Cheat Sheet |
| `owasp-tls-server-config` | Transport Layer Security Cheat Sheet |
| `owasp-xxe-parser` | XML External Entity Prevention Cheat Sheet |

## Provisional A/B result

Both indexes used the same dataset, four-result limit, source hashes, chunking, and local BGE
embedding model. The candidate was an SQLite backup of the baseline plus the pinned OWASP pilot;
the configured live database was not modified.

| Retrieval | Three-source baseline | Baseline + OWASP | Change |
| --- | ---: | ---: | ---: |
| Lexical recall / expected-reference pass | 0/24 (0%) | 24/24 (100%) | +100 points |
| Hybrid recall / expected-reference pass | 0/24 (0%) | 24/24 (100%) | +100 points |
| Lexical mean precision | 0% | 25% | +25 points |
| Hybrid mean precision | 0% | 25% | +25 points |

Candidate hybrid report SHA-256:
`b33dc82529083a89086a4244a493edfc550cac0d9e4dfe155fc92bdec042a0cf`.

This proves that the candidate index can retrieve the intended documents for this synthetic
source-specific slice. It does not establish answer quality, independent real-world retrieval
quality, safe context use, or model-authored attribution.

## Provisional routing result

The evaluation-only `--additional-source owasp` switch routed all 24/24 source-specific cases
to OWASP. With the same switch, the existing balanced and human-approved 48-case routing suite
also remained at 48/48: 24 true positives, 24 true negatives, and no false positives or false
negatives. Without that explicit switch, normal chat and evaluation routing continue to use only
ATT&CK, CWE, and CAPEC.

- OWASP routing report SHA-256:
  `9233eaa7a01fded20da1f2187c41a9373d30c2369078000b442c717b865d85af`
- Balanced routing report SHA-256:
  `f78f0518de6743ad498a0b75ce1cb11dd62f0e751a2c771aaaf250deb2c48420`

## Initial model-use sample

A deterministic six-case Gemma sample used the isolated candidate index and the application's
default four-result limit. It retrieved the expected OWASP document in 6/6 cases, passed the
transparent concept checks in 5/6, and routed all 6/6 cases correctly. Only 1/6 responses cited
every retrieved reference, with 41.7% mean inline-citation coverage. The source-linked claim
extractor produced 15 candidates across five responses; they still require human support review.

Before routing-aware title preference, only 2/6 intended OWASP documents ranked first and no
response used an inline citation in the initial one-result model sample.
The exact-ID attribution score is not suitable for OWASP prose because its `OWASP-CS-*` identifiers
are internal dataset keys rather than public identifiers shown to the model; inline citation and
human claim-support review remain the relevant checks.

## Routing-aware rank and citation candidate

A routing-aware retrieval mode now measures the same source filtering used by chat. On the full
24-case pilot, the unmodified hybrid rank placed the intended document first in 18/24 cases. A
bounded title-topic preference for explicitly enabled pilot sources improved this synthetic slice
to 24/24 at one result. The preference is inactive unless the caller supplies an opt-in preferred
source, so normal ATT&CK/CWE/CAPEC retrieval is unchanged.

On the same first six cases, the improved top rank retrieved the intended document in 6/6 cases.
The production citation prompt cited the single source in only 1/6 responses. An experimental
strict prompt reached 6/6 but produced four unsupported source links in AI-assisted review. A
safer case-aware revision cited 4/6 sources and passed 5/6 concept checks. Its AI-assisted draft
classified 9/11 linked claims as supported and two as partially supported, with none unsupported;
two responses still used retrieved guidance without an inline citation.

These are small, synthetic, AI-reviewed diagnostics, not an admission result. The case-aware
worksheet still requires project-owner approval, broader held-out testing is needed, and the
strict profile remains evaluation-only. OWASP therefore stays out of production routing.

## Review decision

- Reviewer: Pending
- Reviewed at: Pending
- Decision: Pending
- Notes: Pending
