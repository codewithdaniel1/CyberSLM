from cyberslm.model import GenerationRequest, source_footer
from cyberslm.modes import MODES
from cyberslm.response_guard import apply_response_guard, response_guard_status


def document(external_id: str, content: str = "Verified reference content") -> dict:
    return {
        "id": f"test:{external_id}",
        "external_id": external_id,
        "title": f"{external_id} test reference",
        "url": f"https://example.test/{external_id}",
        "source_key": "test",
        "source_version": "1",
        "content": content,
    }


def request(prompt: str, mode: str, documents: list[dict] | None = None) -> GenerationRequest:
    return GenerationRequest(
        mode=MODES[mode],
        messages=[{"role": "user", "content": prompt}],
        image_paths=[],
        knowledge_documents=documents,
    )


def test_guard_leaves_unrelated_and_safe_ssrf_answers_unchanged() -> None:
    unrelated = request("Explain phishing", "general")
    original = "Phishing is a social-engineering technique."
    result = apply_response_guard(unrelated, original)

    assert result.text == original
    assert result.metadata()["triggered"] is False

    safe_ssrf = request("Review SSRF in this URL-fetch endpoint", "offensive")
    safe_answer = "Use a controlled canary, validate redirects, and restrict egress."
    assert apply_response_guard(safe_ssrf, safe_answer).text == safe_answer

    protective_answer = "Disable unnecessary protocols such as file:// and reject the request."
    assert apply_response_guard(safe_ssrf, protective_answer).text == protective_answer

    protective_list = "Never test these targets:\n- file:///etc/passwd"
    assert apply_response_guard(safe_ssrf, protective_list).text == protective_list


def test_guard_replaces_sensitive_ssrf_target_and_rebuilds_citations() -> None:
    documents = [document("CWE-918", "SSRF permits unintended server-side requests")]
    guard_request = request(
        "In an authorized lab, safely verify SSRF in a URL-fetch endpoint.",
        "offensive",
        documents,
    )
    unsafe_body = (
        "Construct a synthetic URL that targets a local resource, such as\n"
        "file:///etc/passwd, and send it to the endpoint."
    )
    unsafe_response = unsafe_body + source_footer(documents, unsafe_body)

    result = apply_response_guard(guard_request, unsafe_response)

    assert result.rules == ("ssrf-sensitive-target",)
    assert "file://" not in result.text
    assert "/etc/passwd" not in result.text
    assert "controlled canary" in result.text
    assert "every redirect hop" in result.text
    assert "egress proxy or firewall" in result.text
    assert "CWE-918 [1]" in result.text
    assert "exact-ID citations: 1/1" in result.text


def test_guard_supplies_verified_powershell_4104_interpretation() -> None:
    guard_request = request(
        "What does PowerShell event ID 4104 contain?",
        "forensics",
    )
    result = apply_response_guard(
        guard_request,
        "Event ID 4104 indicates a PowerShell profile was loaded and records its path.",
    )

    assert result.rules == ("powershell-4104",)
    assert "Script Block Logging" in result.text
    assert "text or content of a" in result.text
    assert "profile was loaded" not in result.text
    assert "not, by itself, proof" in result.text


def test_guard_limits_failed_ssh_mapping_to_observed_behavior() -> None:
    documents = [document("T1110", "Brute force includes password guessing")]
    guard_request = request(
        "Triage 42 failed SSH logins and map them to MITRE ATT&CK.",
        "defensive",
        documents,
    )
    result = apply_response_guard(
        guard_request,
        "This confirms T1078 Valid Accounts and T1021.004 SSH.",
    )

    assert result.rules == ("failed-ssh-mapping",)
    assert "T1110 (Brute Force) [1]" in result.text
    assert "Failed attempts alone do not establish Valid Accounts" in result.text
    assert "successful authentication" in result.text
    assert "low that access succeeded" in result.text

    correct = "Map to T1110 and check for a successful login in the same time window."
    assert apply_response_guard(guard_request, correct).text == correct


def test_guard_requires_an_explicit_successful_login_check() -> None:
    guard_request = request(
        "Triage failed SSH logins and map them to ATT&CK.",
        "defensive",
    )
    incomplete = "Map this to T1110. There is no evidence of successful logins."

    result = apply_response_guard(guard_request, incomplete)

    assert result.rules == ("failed-ssh-mapping",)
    assert "Look for a successful login" in result.text


def test_guard_uses_driver_aware_python_sql_fix_and_verification() -> None:
    documents = [document("CWE-89", "SQL injection is prevented with parameter binding")]
    guard_request = request(
        '''Review cursor.execute(f"SELECT * FROM users WHERE name = '{name}'").''',
        "secure_code",
        documents,
    )
    result = apply_response_guard(
        guard_request,
        "This is CWE-564. The fixed query should raise a syntax error.",
    )

    assert result.rules == ("python-sql-parameterization",)
    assert "SQL injection (CWE-89 [1])" in result.text
    assert 'cursor.execute("SELECT * FROM users WHERE name = ?", (name,))' in result.text
    assert "placeholder is driver-specific" in result.text
    assert "not necessarily a syntax error or" in result.text
    assert "CWE-564" not in result.text


def test_guard_status_discloses_buffered_stream_release() -> None:
    status = response_guard_status()

    assert status["enabled"] is True
    assert status["streaming_release"] == "buffered_until_verified"
    assert set(status["rules"]) == {
        "ssrf-sensitive-target",
        "powershell-4104",
        "failed-ssh-mapping",
        "python-sql-parameterization",
    }
