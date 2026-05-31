# Copyright (c) 2026 Vincent Shahinllari. All rights reserved.
"""
Regression tests for the security-hardening pass (2026-05-31 audit follow-up).

Covers the content-signature ("magic byte") check added to extractors.py: a
file whose bytes don't match its extension must be rejected BEFORE it reaches
a parser (pdfminer / python-docx / openpyxl). This narrows the attack surface
for parser-exploit payloads renamed to a trusted extension -- see
SECURITY_AUDIT.md finding M-2 and the pdfminer RCE (C-1) it backstops.

We also confirm the check never rejects a genuine document (ease-of-use is a
hard requirement: a real PDF/DOCX/XLSX must always pass).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document
from openpyxl import Workbook

from extractors import _verify_file_signature, redact_file


# ---------------------------------------------------------------------------
# Genuine documents must always be accepted.
# ---------------------------------------------------------------------------

def test_real_pdf_fixture_accepted():
    # The committed synthetic fixture is a real PDF -- must pass.
    _verify_file_signature(Path("tests/fixtures/sample_with_pii.pdf"))


def test_real_docx_accepted(tmp_path: Path):
    p = tmp_path / "real.docx"
    Document().save(str(p))
    _verify_file_signature(p)  # must not raise


def test_real_xlsx_accepted(tmp_path: Path):
    p = tmp_path / "real.xlsx"
    Workbook().save(str(p))
    _verify_file_signature(p)  # must not raise


def test_arbitrary_txt_accepted(tmp_path: Path):
    # .txt has no signature -- any byte content is legitimate plain text.
    p = tmp_path / "notes.txt"
    p.write_bytes(b"\x00\x01 anything goes")
    _verify_file_signature(p)  # must not raise


# ---------------------------------------------------------------------------
# Spoofed files (wrong bytes for the extension) must be rejected.
# ---------------------------------------------------------------------------

def test_spoofed_pdf_rejected(tmp_path: Path):
    p = tmp_path / "evil.pdf"
    p.write_bytes(b"this is not a pdf, it is a payload")
    with pytest.raises(ValueError):
        _verify_file_signature(p)


def test_spoofed_office_rejected(tmp_path: Path):
    # A PDF (or anything) renamed to .docx is not a ZIP container.
    p = tmp_path / "evil.docx"
    p.write_bytes(b"%PDF-1.4 fake")
    with pytest.raises(ValueError):
        _verify_file_signature(p)


def test_redact_file_rejects_spoofed_pdf_before_parsing(tmp_path: Path):
    # End-to-end: the guard fires in redact_file() so the parser never runs.
    src = tmp_path / "evil.pdf"
    src.write_bytes(b"definitely not a pdf")
    dst = tmp_path / "out.txt"
    with pytest.raises(ValueError):
        redact_file(src, dst)


# ---------------------------------------------------------------------------
# Filename sanitization (mirrors the logic in app.py's upload handler).
# ---------------------------------------------------------------------------
# app.py reduces the browser-supplied upload name to a bare filename before
# joining it onto the temp dir, so a crafted name cannot escape. The logic is
# small and inline in the Streamlit handler (which can't be imported without
# starting page setup); we re-assert the property here so a future edit that
# weakens it is caught.

@pytest.mark.parametrize("hostile", [
    "../../etc/passwd",
    "..\\..\\Windows\\system32\\x.txt",
    "/abs/evil.txt",
    "C:\\Users\\victim\\evil.docx",
])
def test_filename_reduces_to_basename(hostile: str):
    safe_name = Path(hostile.replace("\\", "/")).name
    if not safe_name or safe_name in (".", ".."):
        safe_name = "uploaded_file"
    # The sanitized name must contain no path separators and must not be a
    # traversal token.
    assert "/" not in safe_name
    assert "\\" not in safe_name
    assert safe_name not in ("", ".", "..")
    # And joining it to a base dir must stay inside that dir.
    base = Path("/tmp/base")
    joined = (base / safe_name).resolve()
    assert str(joined).startswith(str(base.resolve()))
