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

ROUTING_CONTEXT = [
    "routing",
    "aba",
    "rtn",
    "bank",
    "ach",
    "wire",
    "transit",
]


def build_routing_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="US_BANK_ROUTING",
        name="UsBankRoutingRecognizer",
        patterns=[ROUTING_PATTERN],
        context=ROUTING_CONTEXT,
    )


# ---------------------------------------------------------------------------
# US bank account number: 6-17 digits, no separators.
# ---------------------------------------------------------------------------
# This one is the loosest of the bunch on purpose. Account number formats are
# not standardized -- length varies wildly across banks. We rely almost
# entirely on context words. Without "account"/"acct"/"checking"/"savings"
# nearby the score will not clear Presidio's default threshold.
BANK_ACCT_PATTERN = Pattern(
    name="us_bank_acct_digits",
    regex=r"\b\d{6,17}\b",
    score=0.2,
)

BANK_ACCT_CONTEXT = [
    "account",
    "acct",
    "checking",
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

US_STREET_ADDRESS_PATTERN = Pattern(
    name="us_street_address",
    regex=(
        r"\b\d{1,6}\s+"                              # house number
        r"(?:[NSEW]\.?\s+)?"                         # optional N/S/E/W
        r"(?:[\w.'\-]+\s+){1,4}"                     # 1-4 street name words
        rf"(?:{_STREET_SUFFIXES})"
        r"\.?\b"                                     # optional trailing period
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
    "live",
    "lives",
    "located",
    "location",
    "mailing",
    "residence",
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
        build_routing_recognizer(),
        build_bank_account_recognizer(),
        build_address_recognizer(),
    ]
    firm = build_firm_names_recognizer()
    if firm is not None:
        recognizers.append(firm)
    always = build_always_redact_recognizer()
    if always is not None:
        recognizers.append(always)
    return recognizers
