# Auto-RAG routing review v3

Status: **Pending project-owner review**

Dataset SHA-256: `8d1707a84ddffc669053af15dd92ee8971aa46edfe240cd8e5d1ebf3c34b8ded`

This review covers only the 18 AI-authored version-3 additions to
`datasets/selective-rag.jsonl`. Check that each prompt's mode and expected Auto-RAG decision
match the intended product behavior. The deterministic gate currently predicts every proposed
label correctly; that is a regression result, not evidence that the labels are valid.

| ID | Mode | Expected | Prompt | Rationale |
| --- | --- | --- | --- | --- |
| `gate-v3-attack-comparison` | General | Retrieve | Compare the ATT&CK techniques relevant to password spraying and credential dumping for a defensive briefing. | An explicit ATT&CK comparison requires authoritative ATT&CK background. |
| `gate-v3-phishing-monitoring` | General | Retrieve | Explain how phishing commonly supports credential access and what defenders should monitor. | Phishing and credential-access behavior have direct ATT&CK coverage. |
| `gate-v3-scheduled-task` | Defensive | Retrieve | A Windows host unexpectedly created a scheduled task that launches an unknown binary. Triage the persistence behavior. | Scheduled-task persistence has direct ATT&CK coverage. |
| `gate-v3-powershell-4104` | Forensics | Retrieve | Event ID 4104 contains an encoded PowerShell command. Explain what artifacts should be correlated during the investigation. | PowerShell and Event ID 4104 have direct ATT&CK relevance. |
| `gate-v3-authorized-abuse-case` | Offensive | Retrieve | For an authorized web assessment, build an abuse case for account-recovery manipulation and list defensive assumptions. | An explicit abuse-case analysis benefits from CAPEC attack-pattern background. |
| `gate-v3-ctf-command-injection` | CTF | Retrieve | A sandboxed web challenge passes a query parameter into os.system. Identify the likely command-injection weakness and safe test boundaries. | The code pattern and named command-injection weakness have direct CWE coverage. |
| `gate-v3-xss-template` | Secure Code | Retrieve | Review a template that renders an untrusted query parameter without escaping for cross-site scripting risk. | Cross-site scripting has direct CWE coverage for secure-code review. |
| `gate-v3-csrf-profile` | Secure Code | Retrieve | A profile update accepts cookie-authenticated POST requests without a CSRF token. Recommend the primary remediation. | The explicitly named CSRF weakness has direct CWE coverage. |
| `gate-v3-hash-encoding` | General | Skip | Explain the difference between hashing, encoding, and encryption with one short example of each. | This general conceptual explanation does not require ATT&CK, CWE, or CAPEC. |
| `gate-v3-lateral-movement-no-evidence` | Defensive | Skip | A dashboard labels one event as lateral movement but provides no logs, hosts, users, or timestamps. What can we conclude? | ATT&CK examples must not fill an explicitly stated incident-evidence gap. |
| `gate-v3-shift-handoff` | Defensive | Skip | Turn these three analyst bullet points into a concise shift-handoff note without adding facts. | Editing a supplied handoff note needs no framework background. |
| `gate-v3-malware-no-artifacts` | Forensics | Skip | We suspect a malware infection but have no disk image, logs, timeline, or host details. State what evidence is needed next. | Retrieved malware examples must not substitute for explicitly missing forensic evidence. |
| `gate-v3-unix-timestamp` | Forensics | Skip | Convert Unix timestamp 1704067200 to UTC and show the calculation. | Timestamp conversion does not need ATT&CK background. |
| `gate-v3-bounded-command-injection` | Offensive | Skip | Describe how to validate suspected command injection without changing data or executing operating-system commands. | A bounded validation request should avoid retrieving payload-rich weakness background by default. |
| `gate-v3-rules-of-engagement-summary` | Offensive | Skip | Summarize the supplied rules of engagement into scope, timing, contacts, and stop conditions. | Summarizing user-supplied engagement constraints needs no framework lookup. |
| `gate-v3-bounded-ssrf` | CTF | Skip | Give a conservative process to validate suspected SSRF without accessing internal services or extracting data. | A bounded operational-validation request should not retrieve exploit-oriented weakness context by default. |
| `gate-v3-rot13` | CTF | Skip | Decode the ROT13 text PloyreFYZ and explain the letter substitution. | Simple cipher decoding does not require indexed cyber frameworks. |
| `gate-v3-list-comprehension` | Secure Code | Skip | Refactor this ordinary Python loop into a list comprehension without changing its behavior. | A non-security code refactor does not need CWE context. |

## Review decision

- Reviewer: pending
- Reviewed at: pending
- Decision: pending
- Notes: Confirm, revise, or reject any mode, expected decision, prompt, or rationale above.
