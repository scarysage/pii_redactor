"""
Custom Presidio regex recognizers for entities Presidio does not catch out of the box.

What lives here:
    - EIN (Employer Identification Number)        -> entity tag US_EIN
    - ABA routing numbers (US bank routing)       -> entity tag US_BANK_ROUTING
    - US bank account numbers (best-effort)       -> entity tag US_BANK_ACCOUNT
    - Internal client IDs (firm-specific format)  -> entity tag CLIENT_ID

Design notes (read before changing the regexes):

* Each recognizer uses *context words* in addition to the regex. Presidio boosts the
  confidence score when one of those words appears near the match. This is what keeps
  a bare 9-digit number from flagging on every random invoice line.

* Scores are deliberately middling (0.3 - 0.5). The analyzer combines them with the
  context boost. If you push the base score too high, you get a lot of false positives
  on free-form numeric data in spreadsheets. Too low and you miss things.

* The CLIENT_ID format is firm-specific. Confirm with the firm before changing it.
  Current assumption: 3 uppercase letters + dash + 4-6 digits (e.g. ABC-12345).
  [TODO: confirm exact format with the firm.]

* EIN format is NN-NNNNNNN (2 digits, dash, 7 digits). Some EINs appear without a
  dash, which collides with SSN format -- we only match the dashed form to keep the
  false-positive rate sane. Context words help.

* ABA routing numbers are exactly 9 digits and have a checksum. We could validate the
  checksum here for higher precision; right now we lean on context words and let the
  review screen catch misses. [TODO: add checksum validation if false positives bite.]
"""

from __future__ import annotations

from presidio_analyzer import Pattern, PatternRecognizer


# ---------------------------------------------------------------------------
# EIN: Employer Identification Number, formatted NN-NNNNNNN.
# ---------------------------------------------------------------------------
# We REQUIRE the dash. A raw 9-digit number with no dash is indistinguishable from
# a stripped SSN or random account number; Presidio's US_SSN recognizer handles the
# undashed 9-digit case better than we can here.
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
# The 9-digit constraint alone is way too loose -- spreadsheets are full of 9-digit
# numbers. The context words ("routing", "aba", "rtn", "bank") are what make this
# usable in practice. The base score is intentionally low.
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
# US bank account number: 6-17 digits, no separators (banks vary 6-17).
# ---------------------------------------------------------------------------
# This one is the loosest of the bunch on purpose. Account number formats are not
# standardized -- length varies wildly across banks. We rely almost entirely on
# context words. Without "account"/"acct"/"checking"/"savings" nearby the score
# will not clear Presidio's default threshold.
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
# Internal client ID: firm-specific format.
# ---------------------------------------------------------------------------
# Assumption: 3 uppercase letters, dash, 4-6 digits. Example: ABC-12345.
# This is a placeholder -- confirm with the firm and update if their schema
# differs. Score is high because the format is distinctive enough that we want
# it to fire even without context words.
CLIENT_ID_PATTERN = Pattern(
    name="client_id_abc_12345",
    regex=r"\b[A-Z]{3}-\d{4,6}\b",
    score=0.7,
)

CLIENT_ID_CONTEXT = [
    "client",
    "customer",
    "account",
    "case",
    "matter",
    "file",
    "id",
]


def build_client_id_recognizer() -> PatternRecognizer:
    return PatternRecognizer(
        supported_entity="CLIENT_ID",
        name="ClientIdRecognizer",
        patterns=[CLIENT_ID_PATTERN],
        context=CLIENT_ID_CONTEXT,
    )


def all_custom_recognizers() -> list[PatternRecognizer]:
    """Return every custom recognizer in this module. Used by redactor.py."""
    return [
        build_ein_recognizer(),
        build_routing_recognizer(),
        build_bank_account_recognizer(),
        build_client_id_recognizer(),
    ]
