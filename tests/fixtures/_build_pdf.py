"""
One-shot builder for tests/fixtures/sample_with_pii.pdf.

Run this to regenerate the PDF fixture used by test_extractors.py / the
PDF round-trip tests. The output is committed to the repo so tests never
need reportlab at runtime.

Usage (from repo root):
    .venv/bin/python tests/fixtures/_build_pdf.py
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


HERE = Path(__file__).resolve().parent

# Synthetic data only -- no real PII. See tests/fixtures/README.md.
LINES = [
    "Client engagement note",
    "",
    "Jane Doe filed her 1099 on time. Her email is jane.doe@example.com",
    "and the office phone is 415-555-0199.",
    "",
    "Tax IDs on file:",
    "  SSN: 456-78-9012",
    "  EIN: 12-3456789",
    "",
    "Project codes: ACCT-9988776 and routing 021000021.",
    "Spoke with Strassler about the K-1 distribution.",
    "Plain paragraph with no PII at all.",
]


def main() -> None:
    out = HERE / "sample_with_pii.pdf"
    c = canvas.Canvas(str(out), pagesize=letter)
    c.setFont("Helvetica", 11)
    y = 740
    for line in LINES:
        c.drawString(50, y, line)
        y -= 16
    c.showPage()
    c.save()
    print(f"wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
