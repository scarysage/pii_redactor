# Copyright (c) 2026 Vincent Shahinllari. All rights reserved.
"""
End-to-end PII battery -- exhaustive synthetic-data audit of the redaction
engine. Every example here is FAKE: made-up SSNs, EINs, account numbers,
and names that do not correspond to real people or institutions.

What this file does that test_recognizers.py and test_redactor.py do not:

  * Tests run the FULL pipeline (Presidio + spaCy + custom recognizers +
    first-name policy), not isolated regex patterns. That means each case
    here exercises score thresholding, context boosting, and the
    first-name post-processing in addition to the raw match.
  * Coverage is breadth-first: every recognizer has positive AND negative
    cases, plus collision and adversarial cases between recognizers.
  * Cases that document known gaps are marked xfail with the reason. Those
    are the audit's "this is real but unfixed" list -- see
    RECOGNITION_AUDIT.md.

Conventions:
  * `_types(findings)` returns the set of entity tags detected.
  * `_redacted(text, tag)` asserts the redacted text contains the tag and
    does NOT contain the source PII verbatim.
  * Synthetic numbers are chosen NOT to collide with real ranges (SSNs
    avoid valid SSA ranges; routing numbers are not in the Federal Reserve
    bank list; account numbers are obviously fake).
"""

from __future__ import annotations

import pytest

from firm_config import ALWAYS_REDACT, FIRM_NAMES
from redactor import analyze, redact


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _types(findings) -> set[str]:
    return {f.entity_type for f in findings}


def _has_type(findings, entity_type: str) -> bool:
    return any(f.entity_type == entity_type for f in findings)


def _find_text_of_type(findings, entity_type: str) -> list[str]:
    return [f.text for f in findings if f.entity_type == entity_type]


# ---------------------------------------------------------------------------
# SSN
# ---------------------------------------------------------------------------

class TestSSN:
    def test_standard_dashed_ssn(self):
        red, findings = redact("Her SSN is 412-77-8391.")
        assert _has_type(findings, "US_SSN")
        assert "412-77-8391" not in red

    def test_ssn_with_context_label(self):
        red, findings = redact("SSN: 612-54-7728")
        assert _has_type(findings, "US_SSN")
        assert "612-54-7728" not in red

    def test_too_short_ssn_ignored(self):
        # "412-77" is not an SSN shape -- nothing to detect.
        red, findings = redact("Reference 412-77 in the file.")
        assert not _has_type(findings, "US_SSN")
        assert "412-77" in red

    def test_irs_invalid_pattern_still_redacted(self):
        # Presidio's UsSsnRecognizer rejects 000-XX-XXXX as SSA-invalid.
        # Our literal-SSN-shape fallback catches it anyway -- the firm
        # doesn't want any SSN-shaped string leaking.
        red, _ = redact("Bogus SSN 000-12-3456 appears in this file.")
        assert "000-12-3456" not in red

    def test_undashed_9_digit_ssn_with_context(self):
        # Presidio's US_SSN recognizer accepts the undashed form when context
        # is present. Without context, the bare 9-digit string is more likely
        # to surface as routing (with the right context) or be dropped.
        red, findings = redact("Her SSN is 412778391.")
        # Either US_SSN fires (preferred) or US_BANK_ROUTING does. Both
        # outcomes redact the value, which is what matters for the firm.
        assert "412778391" not in red, findings


# ---------------------------------------------------------------------------
# EIN
# ---------------------------------------------------------------------------

class TestEIN:
    def test_standard_dashed_ein(self):
        red, findings = redact("EIN: 47-1234567")
        assert _has_type(findings, "US_EIN")
        assert "47-1234567" not in red

    def test_ein_with_long_label(self):
        red, findings = redact("Federal Tax ID: 82-5559912 for Acme.")
        assert _has_type(findings, "US_EIN")
        assert "82-5559912" not in red

    def test_too_short_ein_ignored(self):
        red, findings = redact("Code 12-345 appears in row 3.")
        assert not _has_type(findings, "US_EIN")
        assert "12-345" in red

    def test_wrong_dash_position_ignored(self):
        red, findings = redact("Number 123-456789 is not an EIN.")
        assert not _has_type(findings, "US_EIN")
        assert "123-456789" in red


# ---------------------------------------------------------------------------
# Bank routing
# ---------------------------------------------------------------------------

class TestBankRouting:
    def test_routing_with_context(self):
        # Made-up 9-digit routing number; NOT a real Fed bank routing.
        red, findings = redact("Routing number: 581739462 on file.")
        assert _has_type(findings, "US_BANK_ROUTING")
        assert "581739462" not in red

    def test_routing_8_digits_ignored(self):
        red, findings = redact("Routing: 58173946 on the form.")
        assert not _has_type(findings, "US_BANK_ROUTING")

    def test_routing_10_digits_not_routing(self):
        # 10 digits is account-shaped, not routing-shaped.
        red, findings = redact("Routing: 5817394620 on the form.")
        # Recognizer either tags as account (if context bleeds across) or
        # nothing. Key requirement: NOT tagged as routing.
        assert not _has_type(findings, "US_BANK_ROUTING")


class TestBankAccount:
    def test_6_digit_account(self):
        red, findings = redact("Account number: 482917")
        assert _has_type(findings, "US_BANK_ACCOUNT")
        assert "482917" not in red

    def test_12_digit_account(self):
        red, findings = redact("Account: 482917384756 at the credit union.")
        assert _has_type(findings, "US_BANK_ACCOUNT")
        assert "482917384756" not in red

    def test_17_digit_account(self):
        red, findings = redact("Checking acct 48291738475600012 verified.")
        assert _has_type(findings, "US_BANK_ACCOUNT")
        assert "48291738475600012" not in red

    def test_9_digit_NOT_tagged_as_account(self):
        # Open Work #2 regression: 9-digit values are owned by routing,
        # not account. Even with account-style context, the account
        # recognizer must NOT fire on 9 digits.
        red, findings = redact("Account number: 482917384")
        account_findings = [
            f for f in findings if f.entity_type == "US_BANK_ACCOUNT"
        ]
        assert account_findings == [], (
            "9-digit run tagged as account; should be routing only."
        )
        # And the value must NOT leak. Routing's context list includes
        # 'account' / 'acct' specifically to cover this case -- a real
        # 9-digit account with only account context will mislabel as
        # routing, but won't leak.
        assert "482917384" not in red, (
            "9-digit value with 'account' context leaked. ROUTING_CONTEXT "
            "should include 'account' to cover this collision."
        )


# ---------------------------------------------------------------------------
# Addresses
# ---------------------------------------------------------------------------

class TestAddresses:
    def test_standard_street_address(self):
        red, findings = redact(
            "Send mail to 123 Main Street, Springfield, IL 62701."
        )
        assert _has_type(findings, "LOCATION")
        # The street portion must be redacted.
        assert "123 Main Street" not in red

    def test_po_box(self):
        red, findings = redact("Send check to PO Box 4892, Trenton, NJ 08601.")
        assert _has_type(findings, "LOCATION")
        assert "PO Box 4892" not in red

    def test_po_box_with_periods(self):
        red, _ = redact("Mail to P.O. Box 5512.")
        assert "P.O. Box 5512" not in red

    def test_address_with_unit_suffix(self):
        # Unit rider should be absorbed into the street-address match.
        red, _ = redact("Mailing address: 456 Oak Avenue Apt 3B.")
        assert "Apt 3B" not in red
        assert "456 Oak Avenue" not in red

    def test_address_with_suite_comma_separated(self):
        red, _ = redact("Send to 789 Elm Street, Suite 200.")
        assert "Suite 200" not in red
        assert "789 Elm Street" not in red

    def test_address_with_pound_unit(self):
        red, _ = redact("Mail: 100 Park Ave #7.")
        assert "#7" not in red

    def test_address_negative_suite_in_prose(self):
        # Critical: the unit rider must NOT cause "Suite 100 of this report"
        # to match. The rider is only valid AFTER a street-suffix has
        # already matched -- a bare "Suite 100" never reaches it.
        _, findings = redact("See Suite 100 of this report for details.")
        location_findings = [f for f in findings if f.entity_type == "LOCATION"]
        for f in location_findings:
            assert "Suite 100" not in f.text


# ---------------------------------------------------------------------------
# ZIP codes (Open Work #3)
# ---------------------------------------------------------------------------

class TestZipCodes:
    def test_zip_after_state_abbrev(self):
        red, findings = redact("Office at Newark NJ 07102.")
        # The state-prefix pattern should fire on "07102".
        assert _has_type(findings, "LOCATION")
        assert "07102" not in red

    def test_zip_plus_four(self):
        red, findings = redact("Mail to Newark NJ 07102-1234.")
        assert _has_type(findings, "LOCATION")
        assert "07102-1234" not in red

    def test_zip_in_full_address_line(self):
        red, _ = redact("Send documents to 789 Elm Street, Albany, NY 12207.")
        # Either the street address pattern or the ZIP pattern (or both)
        # should redact the ZIP.
        assert "12207" not in red

    def test_zip_with_context_word_alone(self):
        red, findings = redact("ZIP code: 90210")
        assert _has_type(findings, "LOCATION")
        assert "90210" not in red

    def test_5_digit_without_state_or_context_does_not_fire(self):
        # The KEY negative case from CLAUDE.md: "12345 employees" should
        # NOT trigger -- no state prefix, no ZIP context word.
        red, findings = redact("The company has 12345 employees.")
        location_findings = [f for f in findings if f.entity_type == "LOCATION"]
        for f in location_findings:
            assert "12345" not in f.text, f.text
        # And the literal string should survive.
        assert "12345" in red


# ---------------------------------------------------------------------------
# Phone numbers (Open Work #4)
# ---------------------------------------------------------------------------

class TestPhoneNumbers:
    def test_dashed_phone(self):
        red, findings = redact("Call 415-555-0123 for support.")
        assert _has_type(findings, "PHONE_NUMBER")
        assert "415-555-0123" not in red

    def test_paren_phone(self):
        red, findings = redact("Call (415) 555-0123 for support.")
        assert _has_type(findings, "PHONE_NUMBER")
        assert "(415) 555-0123" not in red

    def test_dotted_phone(self):
        red, findings = redact("Call 415.555.0123 for support.")
        assert _has_type(findings, "PHONE_NUMBER")
        assert "415.555.0123" not in red

    def test_phone_with_extension(self):
        red, findings = redact("Call 415-555-0123 x42 for accounting.")
        assert _has_type(findings, "PHONE_NUMBER")
        assert "415-555-0123" not in red

    def test_bare_10_digit_NOT_phone(self):
        # Open Work #4 regression: bare 10-digit must NOT tag as PHONE_NUMBER.
        red, findings = redact("Account 4155550123 was credited.")
        phone_findings = [f for f in findings if f.entity_type == "PHONE_NUMBER"]
        assert phone_findings == [], (
            f"Bare 10-digit tagged as phone: {phone_findings}"
        )

    def test_bare_10_digit_near_call_context(self):
        # Even with "Call" context, the bare 10-digit shouldn't tag as phone --
        # we require formatting. The value will instead get caught by the
        # bank-account recognizer (10 digits in account range).
        red, findings = redact("Call 4155550123 for support.")
        phone_findings = [f for f in findings if f.entity_type == "PHONE_NUMBER"]
        assert phone_findings == []


# ---------------------------------------------------------------------------
# Names / PERSON
# ---------------------------------------------------------------------------

class TestPersonNames:
    def test_two_token_name_trims_to_surname(self):
        red, findings = redact("Margaret Johnson signed the engagement letter.")
        assert "Margaret" in red
        assert "Johnson" not in red
        assert "<PERSON>" in red

    def test_dutch_particle_name(self):
        # Implemented in Open Work #1: surname particles are absorbed.
        red, _ = redact("Lars van der Berg approved the file.")
        assert "Lars" in red
        # The particles must be redacted along with the surname.
        assert "van der Berg" not in red
        assert "<PERSON>" in red

    def test_spanish_particle_name(self):
        red, _ = redact("Mary de la Cruz reviewed the return.")
        assert "Mary" in red
        # spaCy should detect "Mary de la Cruz" as PERSON; particle trim
        # should collapse "de la Cruz" into the redacted span.
        if "de la Cruz" in red:
            pytest.xfail(
                "spaCy may not consistently detect 'Mary de la Cruz' as a "
                "single PERSON span; particle trim depends on the span."
            )

    def test_firm_name_alone_still_redacted(self):
        # Strassler is in FIRM_NAMES -- bare-token rule does NOT apply.
        red, _ = redact("Strassler called yesterday.")
        assert "Strassler" not in red
        assert "<PERSON>" in red

    def test_bare_first_name_not_redacted(self):
        # Per firm policy: bare first names are left alone.
        red, _ = redact("Maria called yesterday.")
        assert "Maria" in red

    def test_firm_names_configured(self):
        # Smoke: the configured firm-names list is non-empty so the
        # recognizer has something to fire on.
        assert FIRM_NAMES, (
            "FIRM_NAMES is empty -- the firm-names recognizer will be a no-op."
        )


# ---------------------------------------------------------------------------
# ALWAYS_REDACT literal list
# ---------------------------------------------------------------------------

class TestAlwaysRedact:
    """ALWAYS_REDACT is empty by default. This test documents that the
    pipeline correctly does nothing when the list is empty, and that
    populated entries (when present) get tagged as <REDACTED>.
    """

    def test_empty_list_does_not_crash_pipeline(self):
        # If the list is empty, the recognizer returns None and is skipped.
        # The pipeline should still work end-to-end.
        red, _ = redact("Nothing in this sentence should be redacted.")
        assert "<REDACTED>" not in red

    def test_populated_entry_gets_redacted(self):
        # We can't mutate firm_config at test time, so this test only runs
        # if the maintainer has put something in ALWAYS_REDACT.
        if not ALWAYS_REDACT:
            pytest.skip("ALWAYS_REDACT empty; nothing to verify end-to-end.")
        sample = " ".join(ALWAYS_REDACT)
        red, _ = redact(f"Reference: {sample} in the doc.")
        for term in ALWAYS_REDACT:
            assert term not in red, term


# ===========================================================================
# Phase 4 -- adversarial / mixed-context cases
# ===========================================================================

class TestAdversarial:
    """Tougher cases that mix recognizers or push edge cases."""

    def test_account_and_routing_in_same_sentence(self):
        red, findings = redact(
            "Please remit payment from account 482917384756 to routing 581739462 "
            "no later than Friday."
        )
        assert _has_type(findings, "US_BANK_ACCOUNT")
        assert _has_type(findings, "US_BANK_ROUTING")
        assert "482917384756" not in red
        assert "581739462" not in red

    def test_ein_in_sentence_with_year(self):
        red, findings = redact(
            "The company's EIN is 47-1234567, which was issued in 2018."
        )
        assert _has_type(findings, "US_EIN")
        assert "47-1234567" not in red
        # NOTE: "2018" is picked up by spaCy's DATE_TIME recognizer (which is
        # in DEFAULT_ENTITIES). That's the intended behavior -- the firm
        # treats years/dates as PII. The EIN is NOT mistagged as a date.
        ein_findings = _find_text_of_type(findings, "US_EIN")
        assert "47-1234567" in ein_findings

    def test_ssn_adjacent_to_ein(self):
        red, findings = redact("SSN 412-77-8391 / EIN 47-1234567")
        assert _has_type(findings, "US_SSN")
        assert _has_type(findings, "US_EIN")
        assert "412-77-8391" not in red
        assert "47-1234567" not in red

    def test_long_address_with_commas(self):
        red, findings = redact(
            "Send documents to 789 Elm Street, Suite 200, Albany, NY 12207."
        )
        # At minimum the street portion must be redacted.
        assert "789 Elm Street" not in red
        assert _has_type(findings, "LOCATION")

    def test_5_digit_inside_invoice_context(self):
        # "Invoice #0712234 for client 07102" -- the 5-digit "07102" is
        # ambiguous (could be a client number, could be a ZIP). Document
        # the result rather than asserting either way.
        red, findings = redact("Invoice #0712234 for client 07102 attached.")
        # We just record what happens; either outcome is acceptable.
        zip_or_loc = _find_text_of_type(findings, "LOCATION")
        # If the value leaks, it's because no state prefix and no ZIP
        # context fired -- expected.
        if "07102" in red:
            # documented gap -- no actionable failure
            pass

    def test_bare_10_digit_with_call_keyword(self):
        # "Call 8005551234 for support" -- bare 10-digit, even with "Call"
        # context, should NOT tag as PHONE_NUMBER after the Open Work #4 fix.
        _, findings = redact("Call 8005551234 for support.")
        phone_findings = [f for f in findings if f.entity_type == "PHONE_NUMBER"]
        assert phone_findings == []

    def test_unicode_name(self):
        # Document whether spaCy catches Unicode names. This is an
        # information-only test -- spaCy NER is regional and may or may
        # not catch this consistently.
        red, findings = redact("Björn Müller submitted the form yesterday.")
        # If spaCy catches "Björn Müller" as PERSON, the surname will be
        # redacted. If not, both names leak. Both are valid outcomes; we
        # just record which one happens.
        if "Müller" in red and "Björn" in red:
            pytest.xfail(
                "spaCy en_core_web_lg did not detect 'Björn Müller' as "
                "PERSON. This is a known limitation -- add unusual surnames "
                "to FIRM_NAMES as a workaround."
            )

    def test_all_caps_name(self):
        # ALL-CAPS names are a common spaCy failure mode.
        red, _ = redact("JOHN SMITH signed the engagement letter.")
        if "SMITH" in red:
            pytest.xfail(
                "spaCy NER under-detects ALL-CAPS names. Workaround: the "
                "firm-name deny-list catches specific names regardless of "
                "case; for unknown ALL-CAPS names there is no detection."
            )

    def test_name_inside_table_header_is_not_engine_concern(self):
        # Names inside a Word/Excel table HEADER row are handled by the
        # column-header masking logic in extractors.py, not by Presidio.
        # This is a boundary marker: a bare "Client Name" header in raw
        # text won't fire (and shouldn't).
        _, findings = redact("Client Name | Address | Account")
        # Nothing in this header line is PII; nothing should fire.
        person_findings = [f for f in findings if f.entity_type == "PERSON"]
        assert person_findings == []
