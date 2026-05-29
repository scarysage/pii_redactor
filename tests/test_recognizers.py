# Copyright (c) 2026 Vincent Shahinllari. All rights reserved.
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
    PHONE_PATTERN,
    PO_BOX_PATTERN,
    ROUTING_PATTERN,
    STATE_ZIP_PATTERN,
    US_STREET_ADDRESS_PATTERN,
    ZIP_PATTERN,
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
        # 6-8 OR 10-17 digits (9 excluded; owned by routing).
        assert "123456" in _matches(BANK_ACCT_PATTERN, "Acct 123456")
        assert "12345678901234567" in _matches(
            BANK_ACCT_PATTERN, "Acct 12345678901234567"
        )

    def test_rejects_too_short(self):
        assert _matches(BANK_ACCT_PATTERN, "12345") == []

    def test_excludes_9_digits(self):
        # Open Work #2: 9-digit numbers are owned exclusively by the
        # routing recognizer. The account regex must NOT match exactly 9.
        assert _matches(BANK_ACCT_PATTERN, "123456789") == []
        # Surrounding text shouldn't help -- still no match.
        assert _matches(BANK_ACCT_PATTERN, "Acct 123456789 here") == []

    def test_8_digits_still_matches(self):
        # Boundary check on the lower half of the range.
        assert "12345678" in _matches(BANK_ACCT_PATTERN, "Acct 12345678")

    def test_10_digits_still_matches(self):
        # Boundary check on the upper half of the range.
        assert "1234567890" in _matches(BANK_ACCT_PATTERN, "Acct 1234567890")


class TestRoutingVsAccountCollision:
    """Open Work #2 regression: a 9-digit number must tag ONLY as routing,
    never as account. We test both patterns in isolation against the same
    9-digit value.
    """

    def test_routing_pattern_owns_9_digits(self):
        # Made-up fake routing number -- NOT a real ABA value.
        assert _matches(ROUTING_PATTERN, "Routing 581739462") == ["581739462"]

    def test_account_pattern_skips_9_digits(self):
        assert _matches(BANK_ACCT_PATTERN, "Account 581739462") == []


class TestZipRegex:
    """Open Work #3: ZIP recognition for the 'NJ 07102' shape that spaCy
    drops and the street-address regex can't catch.
    """

    def test_state_prefix_pattern_matches_5_digit(self):
        # Lookbehind keeps only the ZIP itself in the match (not the state).
        assert "07102" in _matches(STATE_ZIP_PATTERN, "Newark NJ 07102")

    def test_state_prefix_pattern_matches_zip_plus_four(self):
        assert "07102-1234" in _matches(STATE_ZIP_PATTERN, "Newark NJ 07102-1234")

    def test_state_prefix_pattern_ignores_no_state(self):
        # Without the 2-letter state prefix, this pattern shouldn't fire.
        assert _matches(STATE_ZIP_PATTERN, "ZIP code 07102") == []

    def test_bare_zip_pattern_matches(self):
        # Lower-score pattern; the recognizer relies on context to surface it.
        assert "07102" in _matches(ZIP_PATTERN, "ZIP 07102")
        assert "07102-1234" in _matches(ZIP_PATTERN, "Code 07102-1234")

    def test_bare_zip_pattern_ignores_4_or_6_digits(self):
        assert _matches(ZIP_PATTERN, "Code 1234") == []
        assert _matches(ZIP_PATTERN, "Item #123456 list") == []


class TestPhoneRegex:
    """Open Work #4: phone regex must require formatting (parens/dashes/
    dots/spaces). Bare 10-digit strings must NOT match.
    """

    def test_dashed_phone_matches(self):
        assert "415-555-0123" in _matches(PHONE_PATTERN, "Call 415-555-0123")

    def test_dotted_phone_matches(self):
        assert "415.555.0123" in _matches(PHONE_PATTERN, "Call 415.555.0123")

    def test_paren_phone_matches(self):
        # Parens around area code, space then exchange.
        assert "(415) 555-0123" in _matches(PHONE_PATTERN, "Call (415) 555-0123")

    def test_country_code_phone_matches(self):
        assert _matches(PHONE_PATTERN, "Call +1 415-555-0123")

    def test_phone_with_extension(self):
        # The extension is OPTIONAL, so we just check the base shape captures.
        # The match may or may not include "x42" depending on regex greediness;
        # the important thing is the phone shape is detected.
        matches = _matches(PHONE_PATTERN, "Call 415-555-0123 x42")
        assert any("415-555-0123" in m for m in matches)

    def test_bare_10_digit_does_not_match(self):
        # The KEY regression: a bare 10-digit run is NOT a phone number.
        assert _matches(PHONE_PATTERN, "Call 4155550123 today") == []

    def test_seven_digit_does_not_match(self):
        # Too ambiguous to flag.
        assert _matches(PHONE_PATTERN, "Dial 555-0123") == []

    def test_inside_longer_digit_run_does_not_match(self):
        # A 10-formatted-digit pattern inside "id=14155550123" should NOT match
        # -- the leading "1" before "415..." would otherwise consume into the
        # area code. Our (?<!\d) lookbehind blocks this.
        assert _matches(PHONE_PATTERN, "id=14155550123end") == []


class TestUsStreetAddressRegex:
    """Positive cases the recognizer should catch."""

    def test_matches_basic_address(self):
        assert "123 Main Street" in _matches(
            US_STREET_ADDRESS_PATTERN, "Lives at 123 Main Street."
        )

    def test_matches_abbreviated_suffix(self):
        for ex in (
            "45 Oak Ave",
            "789 Park Rd",
            "1500 Pennsylvania Blvd",
            "12 Sunset Dr",
            "8 Lake Ln",
        ):
            assert _matches(US_STREET_ADDRESS_PATTERN, ex), ex

    def test_matches_directional_and_numbered_street(self):
        # "West 42nd Street" / "N. Lake Shore Drive" style.
        for ex in (
            "100 West 42nd Street",
            "200 N. Lake Shore Drive",
            "50 E Main St",
        ):
            assert _matches(US_STREET_ADDRESS_PATTERN, ex), ex

    def test_case_insensitive(self):
        # Presidio compiles patterns with IGNORECASE, but our raw regex test
        # passes the flag explicitly to mirror that.
        for ex in ("123 main street", "456 OAK AVE"):
            assert re.search(
                US_STREET_ADDRESS_PATTERN.regex, ex, flags=re.IGNORECASE
            ), ex


class TestUsStreetAddressRegexNegatives:
    """False-positive guards: things that look address-shaped but aren't."""

    def test_no_match_on_number_plus_noun_without_suffix(self):
        # "5 Year Plan" -- this is the classic over-matching trap.
        assert not _matches(US_STREET_ADDRESS_PATTERN, "Our 5 Year Plan")

    def test_no_match_on_days_of_code(self):
        assert not _matches(US_STREET_ADDRESS_PATTERN, "100 Days of Code")

    def test_no_match_on_dosage(self):
        assert not _matches(US_STREET_ADDRESS_PATTERN, "1500 mg dose")

    def test_no_match_on_invoice_line(self):
        assert not _matches(
            US_STREET_ADDRESS_PATTERN, "Item 42 quantity 3 total $100"
        )

    def test_no_match_without_house_number(self):
        # Pure street name, no number -> not an "address" in our sense.
        assert not _matches(US_STREET_ADDRESS_PATTERN, "Just Main Street.")


class TestPoBoxRegex:
    def test_matches_canonical_po_box(self):
        assert "PO Box 1234" in _matches(PO_BOX_PATTERN, "Mail to PO Box 1234.")

    def test_matches_periodic_variants(self):
        for ex in ("P.O. Box 567", "P O Box 89", "POBox 22"):
            assert _matches(PO_BOX_PATTERN, ex), ex

    def test_no_match_on_unrelated(self):
        assert not _matches(PO_BOX_PATTERN, "Open the box of 5")


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
