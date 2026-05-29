# Copyright (c) 2026 Vincent Shahinllari. All rights reserved.
"""
Deeper redactor.py coverage.

Focus areas:
  * Overlapping findings in apply_decisions
  * Adjacent findings
  * Unicode and special characters
  * apply_decisions with keep_indices and out-of-range indices
  * Operators dictionary builds correctly for new entity types
  * User-additions plumbing: persistent reload-each-call behavior
"""

from __future__ import annotations

from pathlib import Path

import pytest

from redactor import (
    Finding,
    DEFAULT_ENTITIES,
    analyze,
    apply_decisions,
    redact,
    set_session_terms,
)


# ---------------------------------------------------------------------------
# apply_decisions: overlap, adjacency, kept items
# ---------------------------------------------------------------------------

def test_apply_decisions_overlapping_findings_resolved():
    """If two findings overlap, only the earlier (in start order) renders.

    This mirrors how the live preview handles the case and is also what
    Presidio's anonymizer does.
    """
    text = "Smith Doe lives there."
    findings = [
        Finding(0, 9, "PERSON", 0.9, "Smith Doe"),
        Finding(6, 9, "PERSON", 0.9, "Doe"),
    ]
    out = apply_decisions(text, findings, keep_indices=[])
    # The longer outer span replaces; the inner shouldn't double-replace.
    assert out.count("<PERSON>") == 1
    assert "Smith Doe" not in out


def test_apply_decisions_adjacent_findings_both_render():
    """Findings that abut at their boundaries each render."""
    text = "ABCDEFGHIJ"
    findings = [
        Finding(0, 5, "REDACTED", 1.0, "ABCDE"),
        Finding(5, 10, "REDACTED", 1.0, "FGHIJ"),
    ]
    out = apply_decisions(text, findings, keep_indices=[])
    assert out.count("<REDACTED>") == 2
    assert "ABCDE" not in out
    assert "FGHIJ" not in out


def test_apply_decisions_keep_all_means_text_unchanged():
    text = "Jane Doe filed."
    findings = analyze(text)
    out = apply_decisions(
        text, findings, keep_indices=list(range(len(findings)))
    )
    assert out == text


def test_apply_decisions_with_no_findings_returns_text():
    text = "Nothing to see."
    assert apply_decisions(text, [], keep_indices=[]) == text


# ---------------------------------------------------------------------------
# Unicode + special characters
# ---------------------------------------------------------------------------

def test_analyze_handles_unicode_text():
    """Multi-byte chars in surrounding text must not break span offsets."""
    text = "Café meeting — Strassler called from 415-555-0199. 🔒"
    red, findings = redact(text)
    assert "Strassler" not in red
    assert "415-555-0199" not in red
    # Café and emoji should survive verbatim.
    assert "Café" in red
    assert "🔒" in red


def test_user_term_with_regex_metacharacters():
    """User-added terms containing regex specials must be escaped."""
    try:
        set_session_terms(["A.C-12$"])
        red, _ = redact("ref A.C-12$ closed")
        assert "A.C-12$" not in red
        assert "<REDACTED>" in red
        # But the metacharacters should NOT be interpreted as a pattern:
        # 'AXC-12X' must NOT be matched by the literal "A.C-12$" entry.
        red2, _ = redact("not the same: AXC-12Y")
        assert "AXC-12Y" in red2
        assert "<REDACTED>" not in red2
    finally:
        set_session_terms([])


# ---------------------------------------------------------------------------
# Operators / DEFAULT_ENTITIES coverage
# ---------------------------------------------------------------------------

def test_default_entities_includes_all_custom_types():
    """If we added a custom recognizer but forgot to wire its entity tag into
    DEFAULT_ENTITIES, Presidio would silently drop it. Catch that here."""
    for tag in ("US_EIN", "US_BANK_ROUTING", "US_BANK_ACCOUNT", "REDACTED"):
        assert tag in DEFAULT_ENTITIES, f"{tag} missing from DEFAULT_ENTITIES"


def test_redact_produces_unique_tag_for_each_entity():
    """Each entity_type should get its own `<TYPE>` replacement string."""
    text = (
        "Jane Doe SSN 456-78-9012 EIN 12-3456789 "
        "email jane@example.com phone 415-555-0199."
    )
    red, _ = redact(text)
    # Spot-check a few distinct tags appear.
    assert "<US_SSN>" in red
    assert "<US_EIN>" in red
    assert "<EMAIL_ADDRESS>" in red


# ---------------------------------------------------------------------------
# Persistent user-additions: reloaded on every analyze() call
# ---------------------------------------------------------------------------

def test_persistent_user_additions_picked_up_live(
    tmp_path: Path, monkeypatch
):
    """Writing to user_additions.txt during a session takes effect on the
    NEXT analyze() call, with no engine restart -- because we re-read the
    file each call."""
    import user_additions

    p = tmp_path / "user_additions.txt"
    monkeypatch.setattr(user_additions, "USER_ADDITIONS_PATH", p)

    text = "Reference Hippogriff-7 in the matter."

    # Step 1: nothing in the file -> no REDACTED finding.
    red_before, findings_before = redact(text)
    assert "Hippogriff-7" in red_before
    assert not any(f.entity_type == "REDACTED" for f in findings_before)

    # Step 2: add the term to the persistent file.
    user_additions.add_user_addition("Hippogriff-7")

    # Step 3: analyze again -- it should now be redacted.
    red_after, findings_after = redact(text)
    assert "Hippogriff-7" not in red_after
    assert "<REDACTED>" in red_after
    assert any(f.entity_type == "REDACTED" for f in findings_after)


# ---------------------------------------------------------------------------
# First-name policy edge cases
# ---------------------------------------------------------------------------

def test_three_word_person_trims_to_last_token():
    """e.g. 'Mary J. Doe' -> 'Mary J. <PERSON>'."""
    red, _ = redact("Mary J. Doe filed the return.")
    assert "Mary" in red
    # We do not assert "J." survives because spaCy may include or exclude it
    # depending on tokenization; we only require the LAST token disappears.
    assert "Doe" not in red
    assert "<PERSON>" in red


def test_first_name_only_inside_full_sentence_left_alone():
    """A bare first name in a normal sentence isn't redacted (no FIRM_NAMES hit)."""
    red, _ = redact("Maria approved the engagement letter.")
    assert "Maria" in red


# ---------------------------------------------------------------------------
# session-terms reset hygiene
# ---------------------------------------------------------------------------

def test_set_session_terms_replaces_not_appends():
    try:
        set_session_terms(["First"])
        set_session_terms(["Second"])
        red, _ = redact("First then Second item.")
        # "First" should NOT be redacted because we overwrote with ["Second"].
        assert "First" in red
        assert "Second" not in red
    finally:
        set_session_terms([])


def test_set_session_terms_drops_empty_strings():
    try:
        set_session_terms(["", "   ", "Real"])
        red, _ = redact("Real entry plus other stuff.")
        assert "Real" not in red
    finally:
        set_session_terms([])
