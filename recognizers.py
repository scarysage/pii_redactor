# Copyright (c) 2026 Vincent Shahinllari. All rights reserved.
"""
Custom Presidio regex recognizers for entities Presidio does not catch out of the box.

What lives here:
    - EIN (Employer Identification Number)        -> entity tag US_EIN
    - ABA routing numbers (US bank routing)       -> entity tag US_BANK_ROUTING
    - US bank account numbers (best-effort)       -> entity tag US_BANK_ACCOUNT
    - Firm-specific names (FIRM_NAMES list)       -> entity tag PERSON
    - Always-redact strings (ALWAYS_REDACT list)  -> entity tag REDACTED

The two LISTS that the firm edits (FIRM_NAMES and ALWAYS_REDACT) live in
firm_config.py, NOT here. This file is logic; that file is configuration.
See CUSTOMIZING.md for the editing instructions we hand the firm.

Design notes (read before changing the regexes):

* Each numeric recognizer uses *context words* in addition to the regex.
  Presidio boosts the confidence score when a context word appears near the
  match. This is what keeps a bare 9-digit number from flagging on every
  random invoice line.

* Scores are deliberately middling (0.3 - 0.5). The analyzer combines them
  with the context boost. If you push the base score too high, you get a lot
  of false positives on free-form numeric data in spreadsheets. Too low and
  you miss things.

* EIN format is NN-NNNNNNN (2 digits, dash, 7 digits). Some EINs appear
  without a dash, which collides with SSN format -- we only match the dashed
  form to keep the false-positive rate sane. Context words help.

* ABA routing numbers are exactly 9 digits and have a checksum. We could
  validate the checksum here for higher precision; right now we lean on
  context words and let the review screen catch misses.
  [TODO: add checksum validation if false positives bite.]
"""

from __future__ import annotations

import re

from presidio_analyzer import Pattern, PatternRecognizer

from firm_config import ALWAYS_REDACT, FIRM_NAMES


# ---------------------------------------------------------------------------
# EIN: Employer Identification Number, formatted NN-NNNNNNN.
# ---------------------------------------------------------------------------
# We REQUIRE the dash. A raw 9-digit number with no dash is indistinguishable
# from a stripped SSN or random account number; Presidio's US_SSN recognizer
# handles the undashed 9-digit case better than we can here.
EIN_PATTERN = Pattern(
    name="ein_dashed",
    regex=r"\b\d{2}-\d{7}\b",
    score=0.5,
)

EIN_CONTEXT = [
    "ein",
    "employer",
    "identification",
    "tax id",
    "taxpayer",
    "federal id",
    "fein",
]


def build_ein_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="US_EIN",
        name="EinRecognizer",
        patterns=[EIN_PATTERN],
        context=EIN_CONTEXT,
    )


# ---------------------------------------------------------------------------
# Literal-SSN-shape fallback: \d{3}-\d{2}-\d{4}.
# ---------------------------------------------------------------------------
# Presidio's predefined UsSsnRecognizer rejects SSA-invalid patterns
# (area number 000, group 00, serial 0000, the 666 area, the 9xx range, etc.).
# That's the right call for "is this a valid SSN" but the wrong call for
# "does this look SSN-shaped enough that we should redact it just in case".
# Synthetic/test/placeholder data often uses 000-style numbers, and the
# firm doesn't want any SSN-shaped string leaking even if it's not a valid
# real SSN.
#
# We tag this as US_SSN to keep the output label consistent with the
# predefined recognizer. Score is low (0.4) so that real Presidio US_SSN
# hits (which score higher) win the overlap and remain the primary
# detection path; this only fires when Presidio's strict recognizer
# refused to.
LITERAL_SSN_PATTERN = Pattern(
    name="us_ssn_literal_shape",
    regex=r"\b\d{3}-\d{2}-\d{4}\b",
    score=0.4,
)

SSN_CONTEXT = [
    "ssn",
    "social",
    "security",
    "taxpayer",
    "tin",
]


def build_literal_ssn_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="US_SSN",
        name="UsSsnLiteralShapeRecognizer",
        patterns=[LITERAL_SSN_PATTERN],
        context=SSN_CONTEXT,
    )


# ---------------------------------------------------------------------------
# ABA routing number: exactly 9 digits, no separators.
# ---------------------------------------------------------------------------
# The 9-digit constraint alone is way too loose -- spreadsheets are full of
# 9-digit numbers. The context words ("routing", "aba", "rtn", "bank") are
# what make this usable in practice. The base score is intentionally low.
ROUTING_PATTERN = Pattern(
    name="aba_routing_9digit",
    regex=r"\b\d{9}\b",
    score=0.3,
)

# IMPORTANT: Presidio's LemmaContextAwareEnhancer lemmatizes the surrounding
# words via spaCy before comparing to this list. The recognizer's context
# list is NOT lemmatized -- comparison is exact-string. So we put LEMMA
# forms here: "route" (not "routing"), "wire" matches both "wire" and
# "wiring" → "wire". Include both word forms only when ambiguous.
#
# NOTE: "account" / "acct" are intentionally included here even though
# they're more naturally associated with the account recognizer. Reason:
# the account regex deliberately excludes 9-digit strings (those belong
# to routing). When a real 9-digit account number appears with ONLY
# account context (no routing keyword), this list ensures routing still
# fires and the value gets redacted. Trade-off: a real 9-digit account
# will be mislabeled as routing -- but per the firm's risk policy,
# mislabeling is preferable to a leak.
ROUTING_CONTEXT = [
    "route",     # lemma of "routing"
    "routing",   # bare form (kept in case lemmatization differs)
    "aba",
    "rtn",
    "bank",
    "ach",
    "wire",
    "transit",
    # Cross-coverage for 9-digit values to prevent leakage; see note above.
    "account",
    "acct",
]


def build_routing_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="US_BANK_ROUTING",
        name="UsBankRoutingRecognizer",
        patterns=[ROUTING_PATTERN],
        context=ROUTING_CONTEXT,
    )


# ---------------------------------------------------------------------------
# US bank account number: 6-8 or 10-17 digits, no separators.
# ---------------------------------------------------------------------------
# This one is the loosest of the bunch on purpose. Account number formats are
# not standardized -- length varies wildly across banks. We rely almost
# entirely on context words. Without "account"/"acct"/"checking"/"savings"
# nearby the score will not clear Presidio's default threshold.
#
# Length 9 is deliberately EXCLUDED: a 9-digit number is an ABA routing
# number by convention, and the routing recognizer above owns that shape.
# Before this carve-out, a 9-digit account number would get matched by BOTH
# recognizers and the wrong tag often won (account, because it scored
# higher with "account" context nearby). The fix gives 9 digits
# unambiguously to routing -- if a real-world account is exactly 9 digits,
# it will be mistagged as routing rather than under-redacted, which is the
# safer failure mode for the firm.
BANK_ACCT_PATTERN = Pattern(
    name="us_bank_acct_digits",
    regex=r"\b(?:\d{6,8}|\d{10,17})\b",
    score=0.2,
)

BANK_ACCT_CONTEXT = [
    "account",
    "acct",
    "check",      # lemma of "checking"
    "checking",
    "saving",     # lemma of "savings"
    "savings",
    "deposit",
    "bank",
    "acc#",
    "acct#",
    "account#",
]


def build_bank_account_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="US_BANK_ACCOUNT",
        name="UsBankAccountRecognizer",
        patterns=[BANK_ACCT_PATTERN],
        context=BANK_ACCT_CONTEXT,
    )


# ---------------------------------------------------------------------------
# US street addresses + PO Boxes (tagged as LOCATION).
# ---------------------------------------------------------------------------
# spaCy's NER catches city / state / country names well but is unreliable on
# US-style street addresses (it was trained mostly on geopolitical names).
# These two patterns close that gap.
#
# Design notes:
#
# * The house-number-then-suffix shape ("123 Main Street") is the strongest
#   signal we have. We require BOTH a leading 1-6 digit house number AND a
#   trailing street-type suffix from a fixed list. Without the suffix the
#   pattern would over-fire on things like "5 Year Plan" or "100 Days of Code".
#
# * {1,4} street-name words between number and suffix lets us catch one-word
#   ("Main"), two-word ("East Main"), or multi-word ("North Lake Shore")
#   street names, but bounds the match so a long sentence happening to end
#   in "Street" does not get swept whole.
#
# * The suffix list covers the common US Postal Service street types plus
#   common abbreviations. Edit it if real-world docs reveal misses.
#
# * The tag is LOCATION so the output is consistent with spaCy's own
#   location detections -- the user does not see two different tags for
#   "address" depending on which detector fired.

# Street suffix alternation -- kept on its own line for readability.
_STREET_SUFFIXES = (
    "Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|"
    "Drive|Dr|Lane|Ln|Way|Court|Ct|Place|Pl|Square|Sq|"
    "Parkway|Pkwy|Circle|Cir|Terrace|Ter|Trail|Trl|"
    "Highway|Hwy|Route|Rte|Plaza|Plz|Loop|Run|Pike|"
    "Crossing|Xing|Alley|Pass|Crescent|Cres"
)

# Unit/apartment riders that may appear after the street suffix:
#   "Apt 3B", "Apartment 4", "Suite 200", "Ste. 5C", "Unit 12", "# 7"
#
# The rider is OPTIONAL -- a plain "123 Main Street" still matches; if a
# unit follows, we extend the matched span to cover it so the whole
# address gets redacted as one finding. The leading separator allows
# either a comma + space ("123 Main Street, Apt 3B") or just whitespace
# ("123 Main Street Apt 3B").
#
# Why the rider must be tightly anchored: free prose like "Suite 100 of
# this report" should NOT trigger -- but that's protected by the fact
# that the rider only fires AFTER the street-suffix has already matched.
# A bare "Suite 100" with no preceding street address never reaches this
# branch.
_UNIT_KEYWORDS = (
    "Apt|Apartment|Suite|Ste|Unit|Rm|Room|Floor|Fl|Bldg|Building|#"
)
_UNIT_RIDER = (
    rf"(?:,?\s+(?:{_UNIT_KEYWORDS})\.?\s*[\w\-]+)?"
)

US_STREET_ADDRESS_PATTERN = Pattern(
    name="us_street_address",
    regex=(
        r"\b\d{1,6}\s+"                              # house number
        r"(?:[NSEW]\.?\s+)?"                         # optional N/S/E/W
        r"(?:[\w.'\-]+\s+){1,4}"                     # 1-4 street name words
        rf"(?:{_STREET_SUFFIXES})"
        r"\.?"                                       # optional trailing period
        + _UNIT_RIDER                                # optional unit suffix
        + r"\b"
    ),
    score=0.7,
)

PO_BOX_PATTERN = Pattern(
    name="po_box",
    # Match the canonical "PO Box <digits>" shape with the common
    # punctuation variants: PO Box, P.O. Box, P O Box, POBox.
    regex=r"\bP\.?\s?O\.?\s?Box\s+\d+\b",
    score=0.85,
)

ADDRESS_CONTEXT = [
    "address",
    "addresses",
    "live",          # lemma of "lives"
    "lives",
    "locate",        # lemma of "located"
    "located",
    "location",
    "mail",          # lemma of "mailing"
    "mailing",
    "residence",
    "reside",        # lemma of "resides"
    "resides",
    "street",
    "city",
    "zip",
    "postal",
]


def build_address_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="LOCATION",
        name="UsAddressRecognizer",
        patterns=[US_STREET_ADDRESS_PATTERN, PO_BOX_PATTERN],
        context=ADDRESS_CONTEXT,
    )


# ---------------------------------------------------------------------------
# US ZIP codes (tagged as LOCATION, same as street addresses).
# ---------------------------------------------------------------------------
# Why ZIPs need their own recognizer:
#   * spaCy NER catches city+state ("Newark NJ") but routinely drops the
#     trailing 5-digit ZIP.
#   * Our street-address recognizer requires a leading house number and a
#     street-type suffix -- a bare "07102" after a state abbreviation has
#     neither.
#
# Two patterns layered for confidence:
#
# 1. STATE_ZIP_PATTERN: 5-digit (or ZIP+4) preceded by a 2-letter state
#    abbreviation and whitespace, via a fixed-width lookbehind. Strong
#    signal -- score 0.7. Lookbehind keeps the matched span to just the
#    ZIP itself, so we don't double-tag with spaCy's state detection.
#    NOTE: Presidio compiles patterns with re.IGNORECASE, so the [A-Z]{2}
#    in the lookbehind also matches lowercase. That's fine -- "nj 07102"
#    is still a strong ZIP signal.
#
# 2. ZIP_PATTERN: bare 5-digit (or ZIP+4). Score 0.3 -- below
#    redactor.SCORE_THRESHOLD (0.35) on its own. Only surfaces when boosted
#    by a context word ("zip", "postal", etc.), which prevents bare invoice
#    or item numbers from getting tagged.
#
# Negative case the design guards against: "12345 employees" -- no state
# prefix, no context word nearby, so neither pattern clears threshold.

STATE_ZIP_PATTERN = Pattern(
    name="us_zip_after_state",
    regex=r"(?<=\b[A-Z]{2}\s)\d{5}(?:-\d{4})?\b",
    score=0.7,
)

ZIP_PATTERN = Pattern(
    name="us_zip_bare",
    regex=r"\b\d{5}(?:-\d{4})?\b",
    score=0.3,
)

ZIP_CONTEXT = [
    "zip",
    "postal",
    "postcode",
    "address",
    "mail",          # lemma of "mailing"
    "mailing",
    "residence",
]


def build_zip_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="LOCATION",
        name="UsZipRecognizer",
        patterns=[STATE_ZIP_PATTERN, ZIP_PATTERN],
        context=ZIP_CONTEXT,
    )


# ---------------------------------------------------------------------------
# US phone numbers (replaces Presidio's default PhoneRecognizer).
# ---------------------------------------------------------------------------
# Why we override the default:
#   Presidio's PhoneRecognizer uses google's `phonenumbers` library with
#   leniency=1, which happily flags bare 10-digit strings (e.g. a 10-digit
#   account number "4155550123") as PHONE_NUMBER. That gets the value
#   redacted, but with the WRONG tag -- a reviewer trying to validate
#   against the engagement letter sees "<PHONE_NUMBER>" where they expected
#   an account number, and may incorrectly "Keep" it.
#
# Our replacement requires phone-shaped FORMATTING -- at least one of
# parens, hyphens, dots, or whitespace separating the area code, exchange,
# and subscriber. Bare 10-digit runs are NOT matched.
#
# Shapes we accept:
#   (415) 555-0123     -- parens around area code
#   415-555-0123       -- hyphens
#   415.555.0123       -- dots
#   415 555 0123       -- spaces
#   +1 415-555-0123    -- with country code
#   415-555-0123 x42   -- with extension
#
# Shapes we reject:
#   4155550123         -- bare 10 digits, no separators
#   555-0123           -- 7 digits only (too ambiguous)
#
# The leading (?<!\d) and trailing (?!\d) prevent matching a 10-digit
# substring inside a longer numeric run.

PHONE_PATTERN = Pattern(
    name="us_phone_formatted",
    regex=(
        r"(?<!\d)"
        r"(?:\+?1[\s.\-]?)?"                  # optional country code
        r"(?:\(\d{3}\)\s*|\d{3}[\s.\-])"      # area code with required trailing format
        r"\d{3}[\s.\-]"                       # exchange + required separator
        r"\d{4}"                              # subscriber
        r"(?:\s*(?:ext|x|extension)\.?\s*\d{1,5})?"  # optional extension
        r"(?!\d)"
    ),
    score=0.7,
)

PHONE_CONTEXT = [
    "phone",
    "telephone",
    "cell",
    "cellphone",
    "mobile",
    "call",
    "fax",
    "number",
    "dial",
    "reach",
]


def build_phone_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="PHONE_NUMBER",
        name="UsFormattedPhoneRecognizer",
        patterns=[PHONE_PATTERN],
        context=PHONE_CONTEXT,
    )


# ---------------------------------------------------------------------------
# Firm-specific names (FIRM_NAMES from firm_config.py).
# ---------------------------------------------------------------------------
# Per CLAUDE.md, PERSON detection is the known weak link -- spaCy misses
# unusual names. Anything the firm tells us "this should always be redacted"
# goes into firm_config.FIRM_NAMES. Matching is case-insensitive (Presidio
# compiles patterns with re.IGNORECASE by default), whole-word, and tagged
# as PERSON so the output style is consistent with spaCy's PERSON hits.
def build_firm_names_recognizer() -> PatternRecognizer | None:
    """Build a recognizer that catches every name in firm_config.FIRM_NAMES.

    Returns None if the list is empty so callers can skip cleanly.
    """
    if not FIRM_NAMES:
        return None
    # re.escape handles names with regex-special chars (apostrophes, hyphens).
    # We use lookarounds rather than \b so terms ending in punctuation still
    # match cleanly -- see redactor._match_user_terms for the same rationale.
    regex = (
        r"(?<!\w)(?:"
        + "|".join(re.escape(n) for n in FIRM_NAMES)
        + r")(?!\w)"
    )
    return PatternRecognizer(
        supported_entity="PERSON",
        name="FirmNamesRecognizer",
        patterns=[Pattern(name="firm_names", regex=regex, score=0.95)],
    )


# ---------------------------------------------------------------------------
# Always-redact strings (ALWAYS_REDACT from firm_config.py).
# ---------------------------------------------------------------------------
# Catch-all for "this exact string should disappear whenever it appears".
# Useful for one-off account numbers, project codes, or any literal phrase
# the firm wants gone every time. Tagged as REDACTED (not PERSON) so the
# review screen distinguishes "this matched the always-redact list" from
# "this matched a name". Score is 1.0 -- if it's on the list, redact.
def build_always_redact_recognizer() -> PatternRecognizer | None:
    """Build a recognizer for every literal string in firm_config.ALWAYS_REDACT.

    Returns None if the list is empty so callers can skip cleanly.
    """
    if not ALWAYS_REDACT:
        return None
    regex = (
        r"(?<!\w)(?:"
        + "|".join(re.escape(s) for s in ALWAYS_REDACT)
        + r")(?!\w)"
    )
    return PatternRecognizer(
        supported_entity="REDACTED",
        name="AlwaysRedactRecognizer",
        patterns=[Pattern(name="always_redact", regex=regex, score=1.0)],
    )


def all_custom_recognizers() -> list[PatternRecognizer]:
    """Return every custom recognizer in this module. Used by redactor.py."""
    recognizers: list[PatternRecognizer] = [
        build_ein_recognizer(),
        build_literal_ssn_recognizer(),
        build_routing_recognizer(),
        build_bank_account_recognizer(),
        build_address_recognizer(),
        build_zip_recognizer(),
        build_phone_recognizer(),
    ]
    firm = build_firm_names_recognizer()
    if firm is not None:
        recognizers.append(firm)
    always = build_always_redact_recognizer()
    if always is not None:
        recognizers.append(always)
    return recognizers
