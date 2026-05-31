# Copyright (c) 2026 Vincent Shahinllari. All rights reserved.
"""
Tests for labels.py -- the plain-English display names shown on the review
screen. Pure-function tests: no Streamlit, no Presidio.

Coverage goals:
  - Every entity in redactor.DEFAULT_ENTITIES has a mapped (non-raw) label,
    so the review screen never shows an internal tag to a reviewer.
  - Singular vs plural counts read naturally, including the irregular plural.
  - Unknown tags degrade gracefully to a tidied-up form rather than a crash.
"""

from __future__ import annotations

from labels import _LABELS, friendly_count, friendly_label
from redactor import DEFAULT_ENTITIES


def test_every_default_entity_has_an_explicit_label():
    # Every tag the engine can emit must be explicitly mapped, so the review
    # screen never falls back to a tidied-up raw tag for a known entity.
    for tag in DEFAULT_ENTITIES:
        assert tag in _LABELS, (
            f"{tag} has no explicit friendly label -- add one to labels._LABELS"
        )
        assert "_" not in friendly_label(tag)


def test_known_labels_read_in_plain_english():
    assert friendly_label("US_SSN") == "Social Security Number"
    assert friendly_label("EMAIL_ADDRESS") == "Email Address"
    assert friendly_label("US_BANK_ROUTING") == "Bank Routing Number"
    assert friendly_label("PERSON") == "Name"
    assert friendly_label("REDACTED") == "Custom Item"


def test_unknown_tag_falls_back_without_crashing():
    assert friendly_label("SOME_NEW_TAG") == "Some New Tag"


def test_count_singular_vs_plural():
    assert friendly_count("US_SSN", 1) == "1 Social Security Number"
    assert friendly_count("US_SSN", 3) == "3 Social Security Numbers"
    assert friendly_count("EMAIL_ADDRESS", 2) == "2 Email Addresses"


def test_count_irregular_plural():
    assert friendly_count("US_DRIVER_LICENSE", 1) == "1 Driver's License"
    assert friendly_count("US_DRIVER_LICENSE", 2) == "2 Driver's Licenses"
