"""
Unit tests for the custom Presidio recognizers in recognizers.py.

We test each recognizer in isolation (no spaCy / no Presidio engine) by
running its compiled patterns directly. This keeps the tests fast and
deterministic -- they do not need the vendored model loaded.
"""

from __future__ import annotations

import re

from recognizers import (
    BANK_ACCT_PATTERN,
    CLIENT_ID_PATTERN,
    EIN_PATTERN,
    ROUTING_PATTERN,
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


class TestClientIdRegex:
    def test_matches_canonical(self):
        assert "ABC-12345" in _matches(CLIENT_ID_PATTERN, "Client ABC-12345 owes")

    def test_rejects_lowercase(self):
        assert _matches(CLIENT_ID_PATTERN, "abc-12345") == []

    def test_rejects_wrong_letter_count(self):
        assert _matches(CLIENT_ID_PATTERN, "AB-12345") == []
        assert _matches(CLIENT_ID_PATTERN, "ABCD-12345") == []
