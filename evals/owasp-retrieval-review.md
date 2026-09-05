# OWASP pilot retrieval review

Status: **Pending project-owner review**

Dataset SHA-256: `67a6bd741ce4d995872c535106e9a8324ff5e8151119598885be3e4f03f65255`

This worksheet covers the 24 AI-authored cases in
[`datasets/owasp-retrieval-pilot.jsonl`](datasets/owasp-retrieval-pilot.jsonl). Each case targets
one allowlisted OWASP Cheat Sheet. Review whether the prompt is natural, the expected document
is the best primary reference, the rationale is sound, and the case does not disclose its answer
through a synthetic identifier.

The cases intentionally use General mode so the benchmark can search the temporary candidate
alongside all three admitted sources without changing production routing. The evaluation expects
one primary OWASP document but retrieves four potentially complementary results, so 25% precision
is the maximum possible under this single-reference labeling when all four slots are populated.

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
`b22452e64ec1b7e8c39187dd56bfa9aed88fbe2b81646606288dc4f501c16102`.

This proves that the candidate index can retrieve the intended documents for this synthetic
source-specific slice. It does not establish answer quality, independent real-world retrieval
quality, safe context use, or model-authored attribution.

## Review decision

- Reviewer: Pending
- Reviewed at: Pending
- Decision: Pending
- Notes: Pending
