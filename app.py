"""
Streamlit UI: upload -> auto-redact -> review screen -> download.

Flow:
    1. User drops one or more files.
    2. We auto-run the redactor on each upload immediately.
    3. The review screen shows the redacted preview with every finding listed.
       The user can uncheck any finding to *keep* the original text (false
       positive). Re-checking re-redacts on the spot.
    4. User downloads the redacted file. PDFs come back as .txt (v1 limit --
       see CLAUDE.md "keep PDF output simple").

Offline guarantee:
    Streamlit itself runs purely as a local web server. Do NOT add any st.*
    component that fetches remote assets. Telemetry is disabled in
    .streamlit/config.toml. If you ever need to add an icon or image, vendor
    it locally.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from extractors import ExtractionResult, redact_file
from redactor import Finding


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="PII Redactor (offline)",
    page_icon="🔒",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Style for redacted spans in the live preview. Matches the in-document style
# used in DOCX/XLSX output (see extractors.REDACT_COLOR_HEX).
REVIEW_STYLE = "font-weight:700; color:#C00000;"

SUPPORTED_TYPES = ["txt", "pdf", "docx", "xlsx"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state_key(filename: str, suffix: str) -> str:
    return f"{filename}::{suffix}"


def _esc(s: str) -> str:
    """Minimal HTML escape so user text does not break the preview pane."""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _render_preview(
    text: str, findings: list[Finding], keep_indices: list[int]
) -> str:
    """
    Build the HTML for the review preview. Redacted spans are wrapped in a
    styled <span> with the `<TYPE>` tag; kept spans are shown verbatim (no
    styling) so the user sees exactly what survives into the output.
    """
    # Defensive: text could be huge. Cap the preview at ~12 KB so the browser
    # doesn't grind. The download still gets the full redacted file.
    LIMIT = 12_000
    truncated = len(text) > LIMIT
    if truncated:
        text = text[:LIMIT]
        findings = [f for f in findings if f.end <= LIMIT]

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
            out.append(_esc(text[cursor:f.start]))
        if idx in keep:
            out.append(_esc(text[f.start:f.end]))
        else:
            out.append(
                f"<span style='{REVIEW_STYLE}'>&lt;{_esc(f.entity_type)}&gt;</span>"
            )
        cursor = f.end
        last_end = f.end
    if cursor < len(text):
        out.append(_esc(text[cursor:]))
    if truncated:
        out.append(
            "<div style='color:#999; margin-top:0.5rem;'>"
            "[preview truncated -- download to see full file]</div>"
        )
    return "".join(out)


# ---------------------------------------------------------------------------
# Page body
# ---------------------------------------------------------------------------

st.title("PII Redactor")
st.caption(
    "Fully offline. Files never leave this machine. "
    "Upload a document, review what was caught, and download the redacted copy."
)

uploaded = st.file_uploader(
    "Drop files here",
    type=SUPPORTED_TYPES,
    accept_multiple_files=True,
    help=(
        "Supported: .txt, .pdf, .docx, .xlsx. "
        "Nothing is uploaded -- processing is local."
    ),
)

if not uploaded:
    st.info("Drop one or more files to begin.")
    st.stop()


# Streamlit reruns the whole script on every interaction. We stash the
# ExtractionResult per file in session_state so we do not re-run the heavy
# analyzer on every checkbox click.
for upload in uploaded:
    st.divider()
    st.subheader(f"📄 {upload.name}")

    cache_key = _state_key(upload.name, "result")

    if cache_key not in st.session_state:
        # Write the upload to a temp file so extractors can read by path.
        # We read the bytes out BEFORE the tempdir is cleaned up.
        with tempfile.TemporaryDirectory() as tmpdir:
            src_path = Path(tmpdir) / upload.name
            src_path.write_bytes(upload.getbuffer())

            dst_suffix = src_path.suffix.lower()
            # PDFs are output as .txt -- see extractors.redact_pdf docstring.
            if dst_suffix == ".pdf":
                dst_suffix = ".txt"
            dst_path = Path(tmpdir) / f"redacted_{src_path.stem}{dst_suffix}"

            try:
                result = redact_file(src_path, dst_path)
                redacted_bytes = dst_path.read_bytes()
                redacted_name = dst_path.name
            except Exception as e:
                st.error(f"Could not process this file: {e}")
                continue

        st.session_state[cache_key] = {
            "result": result,
            "bytes": redacted_bytes,
            "name": redacted_name,
        }

    cached = st.session_state[cache_key]
    result: ExtractionResult = cached["result"]
    redacted_bytes: bytes = cached["bytes"]
    redacted_name: str = cached["name"]

    if result.notes:
        for n in result.notes:
            st.warning(n)

    if not result.findings:
        st.success("No PII detected. Original is available for download as-is.")
    else:
        st.write(
            f"**{len(result.findings)} potential PII item"
            f"{'s' if len(result.findings) != 1 else ''} found.** "
            "Uncheck anything that's a false positive -- it will be kept as-is."
        )

        left, right = st.columns([1, 2])

        with left:
            st.markdown("**Review findings**")
            keep_indices: list[int] = []
            for i, f in enumerate(result.findings):
                key = _state_key(upload.name, f"keep::{i}")
                # Default state: checked = redact. Uncheck = keep original.
                checked = st.checkbox(
                    f"`{f.entity_type}` — {f.text!r} "
                    f"(score {f.score:.2f})",
                    value=st.session_state.get(key, True),
                    key=key,
                )
                if not checked:
                    keep_indices.append(i)

        with right:
            st.markdown("**Redacted preview**")
            preview = _render_preview(
                result.text, result.findings, keep_indices
            )
            st.markdown(
                f"<div style='white-space:pre-wrap; font-family:monospace; "
                f"background:#fafafa; padding:0.75rem; border:1px solid #eee; "
                f"border-radius:4px; max-height:480px; overflow:auto;'>"
                f"{preview}</div>",
                unsafe_allow_html=True,
            )

    # The downloaded bytes are the file produced by redact_file(). For .docx
    # and .xlsx that is a real rewritten document; for .txt/.pdf inputs it is
    # the redacted plain text.
    mime = {
        ".txt": "text/plain",
        ".docx": (
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        ".xlsx": (
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    }.get(Path(redacted_name).suffix.lower(), "application/octet-stream")

    st.download_button(
        label=f"⬇ Download redacted {redacted_name}",
        data=redacted_bytes,
        file_name=redacted_name,
        mime=mime,
        key=_state_key(upload.name, "download"),
    )
