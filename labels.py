# Copyright (c) 2026 Vincent Shahinllari. All rights reserved.
"""
Plain-English display names for the internal entity tags.

Why this exists:
    The engine speaks in machine tags -- US_SSN, US_BANK_ROUTING, LOCATION,
    REDACTED. Those are the right thing to write INTO the redacted document
    (unambiguous, greppable, stable across versions) and the tests depend on
    that `<TYPE>` form. But they are jargon to the people who actually use the
    review screen: HR, legal, and compliance staff who have never seen a
    Presidio entity name. This module maps each tag to a label a non-technical
    reviewer understands at a glance.

    Used by the Streamlit review screen ONLY (findings list, summary card,
    bulk-action buttons). The redacted file itself still carries the raw
    `<TYPE>` tags, and the live preview stays faithful to that output -- so the
    reviewer always sees exactly what will land in the downloaded file.

Kept as a standalone, Streamlit-free module so it can be unit-tested the same
way preview.py is.

Public API:
    friendly_label(entity_type)            -> str   (singular, title case)
    friendly_count(entity_type, count)     -> str   ("3 Social Security Numbers")
"""

from __future__ import annotations


# Singular display name per entity tag. Keep aligned with
# redactor.DEFAULT_ENTITIES and the tags produced by extractors.py
# (DATE_TIME and COLUMN_REDACTED only ever come from the spreadsheet/table
# column-masking path, but we label them too so the review screen never
# shows a raw tag).
_LABELS: dict[str, str] = {
    "US_SSN": "Social Security Number",
    "US_ITIN": "Taxpayer ID (ITIN)",
    "CREDIT_CARD": "Credit Card Number",
    "EMAIL_ADDRESS": "Email Address",
    "PHONE_NUMBER": "Phone Number",
    "PERSON": "Name",
    "LOCATION": "Address or Location",
    "IBAN_CODE": "Bank Account (IBAN)",
    "US_PASSPORT": "Passport Number",
    "US_DRIVER_LICENSE": "Driver's License",
    "US_EIN": "Employer ID (EIN)",
    "US_BANK_ROUTING": "Bank Routing Number",
    "US_BANK_ACCOUNT": "Bank Account Number",
    "DATE_TIME": "Date of Birth",
    "REDACTED": "Custom Item",
    "COLUMN_REDACTED": "Sensitive Column",
}

# Plurals that a bare "+ s" gets wrong: labels ending in "s" (Address ->
# Addresses), labels with a trailing parenthetical (the "s" must go on the
# noun, not after the paren), and irregulars. Anything not listed just gets
# an "s" appended, which is correct for the rest ("Names", "Phone Numbers",
# "Bank Routing Numbers", "Custom Items").
_PLURALS: dict[str, str] = {
    "US_ITIN": "Taxpayer IDs (ITIN)",
    "EMAIL_ADDRESS": "Email Addresses",
    "LOCATION": "Addresses or Locations",
    "IBAN_CODE": "Bank Accounts (IBAN)",
    "US_DRIVER_LICENSE": "Driver's Licenses",
    "US_EIN": "Employer IDs (EIN)",
    "DATE_TIME": "Dates of Birth",
}


def friendly_label(entity_type: str) -> str:
    """Plain-English singular name for an entity tag.

    Falls back to a tidied-up version of the raw tag (underscores to spaces,
    title-cased) for any tag we have not explicitly mapped, so a future
    recognizer can never surface a raw `SOME_NEW_TAG` to the reviewer.
    """
    if entity_type in _LABELS:
        return _LABELS[entity_type]
    return entity_type.replace("_", " ").title()


def friendly_count(entity_type: str, count: int) -> str:
    """Plain-English count, e.g. "3 Social Security Numbers" / "1 Email Address"."""
    if count == 1:
        return f"1 {friendly_label(entity_type)}"
    plural = _PLURALS.get(entity_type)
    if plural is None:
        plural = friendly_label(entity_type) + "s"
    return f"{count} {plural}"
