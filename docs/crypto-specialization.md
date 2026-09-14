# CyberSLM-Crypto specialization contract

CyberSLM-Crypto complements CyberWorkbench by being intentionally narrow. Its purpose is applied
cryptography engineering, not broad cyber analysis.

## In scope

- Primitive selection: AEAD, hashing, MACs, signatures, KDFs, key agreement, and CSPRNG use.
- Safe use of established libraries such as `cryptography`, libsodium, and platform crypto APIs.
- Protocol reasoning: authentication, replay and downgrade resistance, transcript/context binding,
  key confirmation, algorithm agility, and interoperability.
- Key lifecycle: generation, storage boundaries, separation, rotation, backup/recovery, revocation,
  and destruction.
- Post-quantum transition planning based on current standards and deployment constraints.
- Clear explanations of cryptographic concepts, including what a mechanism does *not* guarantee.
- Cryptography CTFs and educational challenge solving from supplied or synthetic challenge data.

## Out of scope

- General application-security or vulnerability auditing.
- SOC triage, malware analysis, incident response, forensics, and ATT&CK mapping.
- Penetration testing, exploit development, credential theft, decryption of data without authority,
  traffic interception, or cryptographic backdoors.
- Non-cryptography CTFs, general exploitation, and live-target work.

For these requests, the model should state that the issue is outside its specialty and direct the
user to CyberWorkbench or a suitable security process.

## Model behavior

CyberSLM-Crypto should prefer a mature standard or existing protocol over a custom construction.
It must distinguish encryption, encoding, hashing, MACs, signatures, and key agreement; surface
nonce, salt, associated-data, key-separation, and error-handling requirements when relevant; and
state assumptions instead of inventing missing protocol details or test outcomes.

The model must not claim that a cryptographic implementation is production-ready solely because a
snippet looks plausible. It should recommend an established library and a focused test-vector or
round-trip/interoperability check where appropriate.

## Crypto CTF coverage

Crypto CTFs are a first-class training and evaluation area. The corpus will use original,
human-reviewed challenge/solution pairs or material with explicit terms permitting the intended
use—never unreviewed scraped writeups. Each example must label the exercise as synthetic or CTF
and distinguish the intentionally weak construction from production guidance.

Initial taxonomy:

- encodings and classical ciphers;
- XOR, frequency analysis, and known-plaintext reasoning;
- toy RSA, Diffie-Hellman, and elliptic-curve arithmetic with challenge-provided parameters;
- block-cipher modes, nonce reuse, padding, and authenticated-encryption pitfalls;
- hashes, MACs, KDFs, signatures, and protocol puzzles;
- CTF-scale PRNG weaknesses; and
- post-quantum and lattice concepts when the task is educational and self-contained.

The model may derive a flag or plaintext only from challenge-supplied or synthetic inputs. A CTF
claim never authorizes recovering third-party secrets, decrypting intercepted traffic, or building
a production backdoor.

The repository provides `cyberslm-train generate-crypto-ctf-drafts` to create 60 deterministic,
original draft examples. It exists to seed review, not to bypass it: every record is explicitly
unapproved and must be promoted into a separately hashed, reviewed corpus before training.

## Initial knowledge and data plan

The first corpus is intentionally smaller and more curated than the former AppSec corpus. Before
any document enters training, record its immutable source URL, version, SHA-256, terms, extraction
method, and human approval in a manifest.

Initial candidates for review:

| Area | Authoritative starting material | Intended use |
| --- | --- | --- |
| Key lifecycle | NIST SP 800-57 and related NIST key-management publications | Concepts and reviewed instruction examples |
| Modern symmetric crypto | Relevant final NIST FIPS and SP publications | Primitive-selection and implementation context |
| Post-quantum KEM | NIST FIPS 203 (ML-KEM) | Standards-grounded migration and terminology |
| Post-quantum signatures | NIST FIPS 204 (ML-DSA) and FIPS 205 (SLH-DSA) | Standards-grounded signature migration |
| Library use | Documentation with terms explicitly permitting the proposed use | Reviewed API examples, never unreviewed scraped text |

NIST’s FIPS 203 specifies ML-KEM and its parameter sets; NIST’s PQC program identifies FIPS 203,
204, and 205 as its first three final PQC standards. NIST SP 800-57 provides general key-management
guidance. [FIPS 203](https://csrc.nist.gov/pubs/fips/203/final),
[PQC standards announcement](https://csrc.nist.gov/News/2024/postquantum-cryptography-fips-approved),
[SP 800-57 Part 1 Rev. 5](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final).

No raw document is automatically converted into training data. The old CWE/CAPEC export remains
historical and is explicitly disallowed for CyberSLM-Crypto training.

## Acceptance gate

The first candidate is `gemma3-4b-cyberslm-crypto`. It must be compared with untouched Gemma 3 4B
on a held-out crypto suite. Promotion requires human review and must demonstrate:

1. Correct primitive and library guidance without inventing a construction.
2. Correct handling of nonce, salt, key separation, authenticated data, encoding, and failure
   behavior where applicable.
3. Evidence restraint when protocol or threat-model details are missing.
4. Better crypto usefulness than the base without increased unsafe assistance or false refusals.
5. Parity across PEFT, merged Safetensors, and GGUF/Ollama before release.
