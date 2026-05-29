"""
PDF round-trip tests.

The fixture PDF is built by tests/fixtures/_build_pdf.py and committed to
the repo so tests do NOT need reportlab installed at runtime. If the file
is missing, the test fails with a clear message asking the maintainer to
regenerate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from extractors import extract_text, redact_file


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "sample_with_pii.pdf"


@pytest.fixture(scope="module")
def fixture_pdf() -> Path:
    if not FIXTURE.exists():
        pytest.fail(
            f"PDF fixture missing: {FIXTURE}. "
            "Regenerate with: .venv/bin/python tests/fixtures/_build_pdf.py"
        )
    return FIXTURE


def test_extract_text_returns_pii_content(fixture_pdf):
    text = extract_text(fixture_pdf)
    assert "Jane Doe" in text
    assert "456-78-9012" in text
    assert "jane.doe@example.com" in text


def test_redact_pdf_writes_txt_with_pii_stripped(fixture_pdf, tmp_path: Path):
    dst = tmp_path / "out.txt"
    result = redact_file(fixture_pdf, dst)

    out = dst.read_text(encoding="utf-8")
    # SSN must be gone, replaced with the tag.
    assert "456-78-9012" not in out
    assert "<US_SSN>" in out
    # Email must be gone.
    assert "jane.doe@example.com" not in out
    assert "<EMAIL_ADDRESS>" in out
    # EIN must be gone.
    assert "12-3456789" not in out
    assert "<US_EIN>" in out
    # The firm-name "Strassler" must be gone (FIRM_NAMES catches it).
    assert "Strassler" not in out
    # Per the first-name policy, "Jane" should survive on its own.
    assert "Jane" in out
    # The harmless paragraph must survive.
    assert "Plain paragraph with no PII at all." in out

    # Findings list should be non-empty and cover the major types.
    types = {f.entity_type for f in result.findings}
    assert "US_SSN" in types
    assert "EMAIL_ADDRESS" in types
    assert "US_EIN" in types


def test_redact_pdf_with_pdf_dst_writes_txt_instead(fixture_pdf, tmp_path: Path):
    """Per CLAUDE.md, PDFs are output as plain text. If the caller asks for a
    .pdf output, we silently retarget to .txt and surface a note."""
    dst = tmp_path / "out.pdf"
    result = redact_file(fixture_pdf, dst)
    written_txt = tmp_path / "out.txt"
    assert written_txt.exists()
    assert not dst.exists()  # the .pdf path was NOT created
    # And we got a user-facing note explaining the rename.
    assert any("PDF" in n for n in result.notes)
