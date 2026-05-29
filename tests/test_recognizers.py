"""
Unit tests for the custom Presidio recognizers in recognizers.py.

We test each recognizer in isolation (no spaCy / no Presidio engine) by
running its compiled patterns directly. This keeps the tests fast and
deterministic -- they do not need the vendored model loaded.
"""

from __future__ import annotations

import re

from firm_config import FIRM_NAMES
from recognizers import (
    BANK_ACCT_PATTERN,
    EIN_PATTERN,
    ROUTING_PATTERN,
    build_always_redact_recognizer,
    build_firm_names_recognizer,
)


def _matches(pattern, text: str) -> list[str]:
    return [m.group(0) for m in re.finditer(pattern.regex, text)]


class TestEinRegex:
    def test_matches_dashed_ein(self):
        assert "12-3456789" in _matches(EIN_PATTERN, "EIN: 12-3456789")

    def test_ignores_undashed_9digit(self):
        # We intentionally do NOT match 9 bare digits -- it would collide with SSN.
        # That's covered by the bank account / routing recognizers instead.
        assert _matches(EIN_PATTERN, "123456789") == []

    def test_rejects_wrong_dash_position(self):
        assert _matches(EIN_PATTERN, "123-456789") == []


class TestRoutingRegex:
    def test_matches_9_digits(self):
        assert "021000021" in _matches(ROUTING_PATTERN, "Routing 021000021")

    def test_does_not_match_8_or_10(self):
        assert _matches(ROUTING_PATTERN, "12345678") == []
        assert _matches(ROUTING_PATTERN, "1234567890") == []


class TestBankAcctRegex:
    def test_matches_typical_account(self):
        # 6-17 digits inclusive.
        assert "123456" in _matches(BANK_ACCT_PATTERN, "Acct 123456")
        assert "12345678901234567" in _matches(
            BANK_ACCT_PATTERN, "Acct 12345678901234567"
        )

    def test_rejects_too_short(self):
        assert _matches(BANK_ACCT_PATTERN, "12345") == []


class TestFirmNamesRecognizer:
    """The firm-names deny-list catches names spaCy NER routinely misses."""

    def test_configured_names_present(self):
        # Sanity: the firm explicitly asked for these to always be caught.
        assert "Strassler" in FIRM_NAMES
        assert "Herbstman" in FIRM_NAMES

    def test_recognizer_builds(self):
        rec = build_firm_names_recognizer()
        assert rec is not None
        assert rec.supported_entities == ["PERSON"]

    def test_regex_matches_case_variants(self):
        rec = build_firm_names_recognizer()
        pattern = rec.patterns[0].regex
        # Presidio compiles patterns with re.IGNORECASE at runtime, so we
        # pass the flag explicitly here too.
        for variant in ("Strassler", "STRASSLER", "strassler",
                        "Herbstman", "HERBSTMAN", "herbstman"):
            assert re.search(pattern, variant, flags=re.IGNORECASE), variant

    def test_regex_respects_word_boundaries(self):
        rec = build_firm_names_recognizer()
        pattern = rec.patterns[0].regex
        assert not re.search(
            pattern, "preStrasslerSuffix", flags=re.IGNORECASE
        )


class TestAlwaysRedactRecognizer:
    """The ALWAYS_REDACT list is empty by default; the recognizer skips cleanly."""

    def test_empty_list_returns_none(self):
        # Default firm_config.ALWAYS_REDACT is empty -> recognizer is skipped.
        # If a maintainer ever populates it, the all_custom_recognizers()
        # wiring will pick it up automatically.
        rec = build_always_redact_recognizer()
        assert rec is None
