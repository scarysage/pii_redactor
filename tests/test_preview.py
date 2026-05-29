# Copyright (c) 2026 Vincent Shahinllari. All rights reserved.
"""
Tests for preview.render_preview -- the HTML produced by the review pane.

These are pure-function tests: no Streamlit, no Presidio. We hand-craft
Finding objects, run them through render_preview, and assert on the
output HTML.

Coverage goals:
  - Basic redaction wraps the tag in the styled span.
  - Kept findings (keep_indices) are shown verbatim, unwrapped.
  - HTML-special characters in the source text are escaped.
  - Overlapping findings are de-duplicated.
  - Adjacent (non-overlapping) findings both render.
  - Truncation appends the "preview truncated" marker.
"""

from __future__ import annotations

from preview import PREVIEW_BYTE_LIMIT, escape, render_preview
from redactor import Finding


def _f(start: int, end: int, entity: str, text: str) -> Finding:
    return Finding(start=start, end=end, entity_type=entity, score=1.0, text=text)


def test_escape_handles_html_specials():
    assert escape("<b>&</b>") == "&lt;b&gt;&amp;&lt;/b&gt;"


def test_renders_redaction_with_tag_span():
    text = "SSN is 456-78-9012 here."
    findings = [_f(7, 18, "US_SSN", "456-78-9012")]
    html = render_preview(text, findings, keep_indices=[])
    assert "&lt;US_SSN&gt;" in html
    assert "456-78-9012" not in html
    assert "font-weight:700" in html


def test_kept_finding_is_unwrapped():
    text = "SSN is 456-78-9012 here."
    findings = [_f(7, 18, "US_SSN", "456-78-9012")]
    html = render_preview(text, findings, keep_indices=[0])
    # User chose to keep -> show the literal text, no tag span.
    assert "456-78-9012" in html
    assert "&lt;US_SSN&gt;" not in html


def test_escapes_html_in_surrounding_text():
    text = "value <hacker>injection</hacker>"
    findings: list[Finding] = []
    html = render_preview(text, findings, keep_indices=[])
    # The raw '<' must be escaped.
    assert "<hacker>" not in html
    assert "&lt;hacker&gt;" in html


def test_overlapping_findings_dedupe():
    """If two findings cover the same span, only the first renders."""
    text = "Strassler called."
    findings = [
        _f(0, 9, "PERSON", "Strassler"),
        _f(0, 9, "PERSON", "Strassler"),  # duplicate
    ]
    html = render_preview(text, findings, keep_indices=[])
    # The tag should appear exactly once.
    assert html.count("&lt;PERSON&gt;") == 1


def test_adjacent_findings_both_render():
    """Findings touching at their boundaries should both render."""
    text = "456-78-90121234567890"  # SSN then phone, abutting
    findings = [
        _f(0, 11, "US_SSN", "456-78-9012"),
        _f(11, 21, "PHONE_NUMBER", "1234567890"),
    ]
    html = render_preview(text, findings, keep_indices=[])
    assert html.count("&lt;US_SSN&gt;") == 1
    assert html.count("&lt;PHONE_NUMBER&gt;") == 1


def test_truncation_marker_when_text_too_large():
    long_text = "x" * (PREVIEW_BYTE_LIMIT + 100)
    html = render_preview(long_text, [], keep_indices=[])
    assert "preview truncated" in html


def test_no_truncation_marker_under_limit():
    text = "short"
    html = render_preview(text, [], keep_indices=[])
    assert "preview truncated" not in html


def test_empty_text_returns_empty_string():
    assert render_preview("", [], keep_indices=[]) == ""


def test_findings_outside_text_are_skipped_when_truncated():
    text = "a" * (PREVIEW_BYTE_LIMIT + 50)
    findings = [
        _f(0, 1, "REDACTED", "a"),
        _f(PREVIEW_BYTE_LIMIT + 10, PREVIEW_BYTE_LIMIT + 20, "REDACTED", "aaaaaaaaaa"),
    ]
    html = render_preview(text, findings, keep_indices=[])
    # Only the in-range finding should render.
    assert html.count("&lt;REDACTED&gt;") == 1
