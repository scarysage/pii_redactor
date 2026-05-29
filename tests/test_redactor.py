"""
End-to-end tests for redactor.py.

These DO spin up Presidio + the vendored spaCy model, so they are slower
(one-time load ~5s). The analyzer is cached at the module level after the
first call.

Synthetic data only. See tests/fixtures/README.md.
"""

from __future__ import annotations

import pytest

from redactor import analyze, apply_decisions, redact


SAMPLE = (
    "Jane Doe (jane.doe@example.com) called from 415-555-0199. "
    "Her SSN is 456-78-9012 and EIN 12-3456789. "
    "Client ID ABC-12345. Routing: 021000021."
)


@pytest.fixture(scope="module")
def red_result():
    return redact(SAMPLE)


def _types(findings) -> set[str]:
    return {f.entity_type for f in findings}


class TestRedactCoreEntities:
    def test_person_detected(self, red_result):
        _, findings = red_result
        assert "PERSON" in _types(findings)

    def test_email_detected(self, red_result):
        _, findings = red_result
        assert "EMAIL_ADDRESS" in _types(findings)

    def test_phone_detected(self, red_result):
        _, findings = red_result
        assert "PHONE_NUMBER" in _types(findings)

    def test_ssn_detected(self, red_result):
        _, findings = red_result
        assert "US_SSN" in _types(findings)

    def test_ein_detected(self, red_result):
        _, findings = red_result
        assert "US_EIN" in _types(findings)

    def test_client_id_detected(self, red_result):
        _, findings = red_result
        assert "CLIENT_ID" in _types(findings)

    def test_routing_detected(self, red_result):
        _, findings = red_result
        assert "US_BANK_ROUTING" in _types(findings)


class TestRedactOutput:
    def test_no_raw_email_remains(self, red_result):
        red, _ = red_result
        assert "jane.doe@example.com" not in red

    def test_no_raw_ssn_remains(self, red_result):
        red, _ = red_result
        assert "456-78-9012" not in red

    def test_tags_are_present(self, red_result):
        red, _ = red_result
        assert "<EMAIL_ADDRESS>" in red
        assert "<US_SSN>" in red

    def test_safe_text_survives(self, red_result):
        red, _ = red_result
        # Words like "called", "from", "owes" are not PII and should be intact.
        assert "called" in red


class TestApplyDecisions:
    def test_keeping_a_finding_leaves_it_intact(self):
        findings = analyze(SAMPLE)
        # Find the EIN finding and ask to keep it.
        ein_idx = next(
            i for i, f in enumerate(findings) if f.entity_type == "US_EIN"
        )
        out = apply_decisions(SAMPLE, findings, keep_indices=[ein_idx])
        assert "12-3456789" in out  # kept verbatim
        assert "<US_EIN>" not in out
        # Other PII still redacted.
        assert "<US_SSN>" in out

    def test_no_keeps_matches_full_redact(self):
        findings = analyze(SAMPLE)
        full, _ = redact(SAMPLE)
        assert apply_decisions(SAMPLE, findings, keep_indices=[]) == full


class TestEmptyInput:
    def test_empty_string(self):
        red, findings = redact("")
        assert red == ""
        assert findings == []

    def test_only_whitespace(self):
        red, findings = redact("   \n\t  ")
        assert findings == []
