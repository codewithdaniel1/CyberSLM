# Deterministic response guard

Status: Enabled for the local alpha

CyberSLM runs a small, deterministic guard after local model generation and before any answer
text is released to the UI, API caller, database, code validator, or evaluation scorer. It exists
to contain specific failures reproduced during the 4B and 12B alpha evaluations. It is not a
general fact-checker and does not make arbitrary model output trustworthy.

## Current rules

| Rule | Trigger | Result |
| --- | --- | --- |
| `ssrf-sensitive-target` | An SSRF/URL-fetch answer affirmatively recommends accessing a system file or known cloud metadata target | Replaces the draft with controlled-canary verification, redirect revalidation, URL canonicalization, resolved-IP checks, and egress controls |
| `powershell-4104` | The user asks about PowerShell event 4104 | Supplies the verified Script Block Logging interpretation, multipart reconstruction checks, and limits on conclusions |
| `failed-ssh-mapping` | Failed-only SSH triage is mapped to T1078 or T1021.004 | Replaces the unsupported mapping with T1110/T1110.001 and requires a separate check for successful authentication |
| `python-sql-parameterization` | The supplied Python example interpolates a value into `cursor.execute(...)` | Supplies CWE-89, a driver-aware parameter binding fix, and verification that treats attack-shaped input as data |

The SSRF detector distinguishes affirmative instructions from protective statements. For
example, it blocks “request this system file” but does not rewrite “disable the `file` scheme.”
Corrected answers rebuild their local-source footer so citation diagnostics describe the released
text instead of the discarded draft.

## Streaming and API behavior

The streaming endpoint still sends a start event immediately and supports cancellation during
model generation. It buffers model text, applies the guard, and then emits only the checked answer
as token events. This trades live token display for a meaningful pre-release boundary; a guard
that ran after raw tokens were displayed would not provide containment.

Every completed API response includes:

```json
{
  "response_guard": {
    "enabled": true,
    "version": 1,
    "triggered": true,
    "rules": ["ssrf-sensitive-target"]
  }
}
```

`GET /api/health` reports the enabled rules and the `buffered_until_verified` release policy.
Evaluation reports record guard metadata per case and summarize how many answers were corrected.

## Factual basis

- [Microsoft PowerShell logging documentation](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_logging?view=powershell-5.1)
  identifies event 4104 as the Script Block Logging event and states that the feature records the
  content of script blocks PowerShell processes.
- [MITRE ATT&CK T1110.001](https://attack.mitre.org/techniques/T1110/001/) identifies Password
  Guessing and explicitly includes repeated failed SSH login attempts in its detection strategy.
- [MITRE CWE-89](https://cwe.mitre.org/data/definitions/89.html) recommends prepared statements
  or parameterized queries that keep data separate from SQL commands.
- The [OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
  covers allowlisting, DNS resolution risks, redirect handling, and network-layer controls.

## Limits

- Rules are deliberately narrow. A non-matching answer can still be wrong or unsafe.
- Static corrections cannot incorporate every case-specific detail from a discarded draft.
- Source-disclosure footers and automatic concept scores still do not prove claim support.
- New rules require a reproduced failure, a primary factual source, false-positive tests, replay
  against saved responses, and human review.
