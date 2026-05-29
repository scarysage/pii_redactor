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
    "Routing: 021000021."
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


class TestFirmNameEndToEnd:
    """The firm-names recognizer is wired through the full Presidio pipeline."""

    def test_strassler_redacted_even_without_context(self):
        # Bare name in a low-context sentence: spaCy NER may or may not catch
        # this on its own. Our deny-list guarantees it does.
        red, findings = redact("Strassler called yesterday.")
        assert "Strassler" not in red
        assert any(f.entity_type == "PERSON" for f in findings)

    def test_herbstman_redacted_even_without_context(self):
        red, findings = redact("Herbstman signed off on the return.")
        assert "Herbstman" not in red
        assert any(f.entity_type == "PERSON" for f in findings)

    def test_strassler_redacted_lowercase(self):
        red, _ = redact("Spoke with strassler about the K-1.")
        assert "strassler" not in red
        assert "STRASSLER" not in red

    def test_other_capitalized_words_not_overflagged(self):
        # Sanity: the recognizer is name-specific, not a generic "any
        # capitalized word" trigger. Avoid words spaCy interprets as
        # date/location/org (e.g. weekday names, city names) -- those are
        # *correctly* flagged by other recognizers and unrelated to this test.
        red, _ = redact("The meeting covered Receipts and Reconciliations.")
        for word in ("Receipts", "Reconciliations"):
            assert word in red


class TestFirstNamePolicy:
    """The firm directive: first names should not get redacted.

    Policy (see redactor._enforce_no_first_names):
      - FIRM_NAMES match -> full redact (curated surnames).
      - Multi-word PERSON span -> shrink to last word.
      - Single-word PERSON span NOT in FIRM_NAMES -> drop entirely.
    """

    def test_full_name_keeps_first_name(self):
        red, findings = redact("Jane Doe filed the return.")
        # First name survives; surname is redacted as PERSON.
        assert "Jane" in red
        assert "Doe" not in red
        assert "<PERSON>" in red
        # The finding's matched text is now just the last token.
        person = [f for f in findings if f.entity_type == "PERSON"]
        assert any(f.text == "Doe" for f in person)

    def test_bare_first_name_is_left_alone(self):
        # "Maria" alone, not in FIRM_NAMES -> dropped per policy.
        red, findings = redact("Maria called yesterday.")
        assert "Maria" in red
        assert "<PERSON>" not in red

    def test_firm_name_alone_still_redacted(self):
        # Strassler is in FIRM_NAMES -> the single-token-drop rule does NOT apply.
        red, _ = redact("Strassler called yesterday.")
        assert "Strassler" not in red
        assert "<PERSON>" in red

    def test_firm_name_with_first_name(self):
        # Multi-token containing a curated surname: spaCy may detect the whole
        # "John Strassler" as PERSON; the firm-names recognizer also detects
        # "Strassler". Both findings get redacted -- final output keeps "John"
        # but loses "Strassler".
        red, _ = redact("John Strassler signed off.")
        assert "John" in red
        assert "Strassler" not in red


class TestUserAdditions:
    """Session-only and persistent user terms get matched as REDACTED."""

    def test_session_term_redacted(self):
        from redactor import set_session_terms
        try:
            set_session_terms(["FALCON-7"])
            red, findings = redact("Refer to project FALCON-7 for details.")
            assert "FALCON-7" not in red
            assert "<REDACTED>" in red
            assert any(f.entity_type == "REDACTED" for f in findings)
        finally:
            set_session_terms([])  # reset for other tests

    def test_session_term_case_insensitive(self):
        from redactor import set_session_terms
        try:
            set_session_terms(["FALCON-7"])
            red, _ = redact("note: falcon-7 update")
            assert "falcon-7" not in red.lower() or "<REDACTED>" in red
        finally:
            set_session_terms([])

    def test_empty_session_terms_noop(self):
        from redactor import set_session_terms
        set_session_terms([])
        red, _ = redact("Plain sentence with no PII.")
        assert "<REDACTED>" not in red


class TestEmptyInput:
    def test_empty_string(self):
        red, findings = redact("")
        assert red == ""
        assert findings == []

    def test_only_whitespace(self):
        red, findings = redact("   \n\t  ")
        assert findings == []
