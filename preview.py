# Copyright (c) 2026 Vincent Shahinllari. All rights reserved.
"""
Render the live HTML preview shown in the review pane of the Streamlit UI.

Extracted from app.py so the rendering logic is testable without importing
Streamlit (which fires page setup / sidebar / etc. on import).

Public API:
    render_preview(text, findings, keep_indices) -> HTML string
    escape(s) -> HTML-escaped string
"""

from __future__ import annotations

from redactor import Finding


# Style applied to redacted spans in the live preview. Matches the in-document
# style used in DOCX/XLSX output (see extractors.REDACT_COLOR_HEX).
REVIEW_STYLE = "font-weight:700; color:#C00000;"

# Cap on how much text we render in the live preview. Beyond this the browser
# starts to lag with every checkbox click. The downloaded file is not affected.
PREVIEW_BYTE_LIMIT = 12_000


def escape(s: str) -> str:
    """Minimal HTML escape so user text does not break the preview pane."""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render_preview(
    text: str,
    findings: list[Finding],
    keep_indices: list[int],
) -> str:
    """Build the HTML for the review preview.

    Redacted spans are wrapped in a styled <span> with the `<TYPE>` tag;
    kept spans (those whose index is in `keep_indices`) are shown verbatim
    with no styling, so the user sees exactly what will survive into the
    output.

    Overlap handling: findings are processed in (start, end) order. Any
    finding whose start lies before the end of the last rendered span is
    skipped, matching the rule used by apply_decisions().
    """
    truncated = len(text) > PREVIEW_BYTE_LIMIT
    if truncated:
        text = text[:PREVIEW_BYTE_LIMIT]
        findings = [f for f in findings if f.end <= PREVIEW_BYTE_LIMIT]

    keep = set(keep_indices)
    sorted_pairs = sorted(
        enumerate(findings), key=lambda kv: (kv[1].start, kv[1].end)
    )

    out: list[str] = []
    cursor = 0
    last_end = -1
    for idx, f in sorted_pairs:
        if f.start < last_end:
            # Overlapping with a finding we already rendered. Skip.
            continue
        if f.start > cursor:
            out.append(escape(text[cursor:f.start]))
        if idx in keep:
            out.append(escape(text[f.start:f.end]))
        else:
            out.append(
                f"<span style='{REVIEW_STYLE}'>"
                f"&lt;{escape(f.entity_type)}&gt;</span>"
            )
        cursor = f.end
        last_end = f.end
    if cursor < len(text):
        out.append(escape(text[cursor:]))
    if truncated:
        out.append(
            # slate-400 -- matches the app's muted-text token (_TEXT_MUTED)
            # and clears contrast on the dark preview panel.
            "<div style='color:#94A3B8; margin-top:0.5rem;'>"
            "[preview truncated -- download to see full file]</div>"
        )
    return "".join(out)
