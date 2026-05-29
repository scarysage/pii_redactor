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

import redactor
from extractors import ExtractionResult, redact_file
from preview import render_preview
from user_additions import (
    add_user_addition,
    load_user_additions,
    remove_user_addition,
)


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="PII Redactor (offline)",
    page_icon="🔒",
    layout="wide",
    initial_sidebar_state="collapsed",
)

SUPPORTED_TYPES = ["txt", "pdf", "docx", "xlsx"]


def _state_key(filename: str, suffix: str) -> str:
    return f"{filename}::{suffix}"


# ---------------------------------------------------------------------------
# Page body
# ---------------------------------------------------------------------------

st.title("PII Redactor")
st.caption(
    "Fully offline. Files never leave this machine. "
    "Upload a document, review what was caught, and download the redacted copy."
)


# ---------------------------------------------------------------------------
# "Add a specific item to redact" expander
# ---------------------------------------------------------------------------
# Lives above the uploader so the user can configure custom items BEFORE
# dropping their file. Two modes:
#   * "Just for this session" -- stored in st.session_state["session_terms"];
#     applies until the browser tab is closed.
#   * "Save permanently" -- appended to user_additions.txt; applies on every
#     future run until removed.
#
# We clear any cached redaction results when the list changes so the next
# render reprocesses every uploaded file with the new term list.

if "session_terms" not in st.session_state:
    st.session_state["session_terms"] = []


def _clear_result_cache() -> None:
    """Drop any cached ExtractionResult so files are re-redacted on next render."""
    for k in [k for k in st.session_state.keys() if k.endswith("::result")]:
        del st.session_state[k]


with st.expander("➕ Add a specific item to redact"):
    st.caption(
        "Add any text you want stripped out -- a name, account number, "
        "project code, or phrase. Items are matched case-insensitively, "
        "whole-word."
    )
    col_input, col_mode, col_btn = st.columns([3, 2, 1])
    with col_input:
        new_term = st.text_input(
            "Term",
            key="new_term_input",
            placeholder="e.g. ACME-12345",
            label_visibility="collapsed",
        )
    with col_mode:
        mode = st.radio(
            "When to apply",
            options=["Just for this session", "Save permanently"],
            horizontal=False,
            key="new_term_mode",
            label_visibility="collapsed",
        )
    with col_btn:
        if st.button("Add", use_container_width=True):
            cleaned = (new_term or "").strip()
            if not cleaned:
                st.warning("Type something first.")
            elif mode == "Just for this session":
                if cleaned.lower() in {
                    t.lower() for t in st.session_state["session_terms"]
                }:
                    st.info(f"'{cleaned}' is already in the session list.")
                else:
                    st.session_state["session_terms"].append(cleaned)
                    _clear_result_cache()
                    st.success(f"Added '{cleaned}' for this session.")
            else:
                if add_user_addition(cleaned):
                    _clear_result_cache()
                    st.success(f"Saved '{cleaned}' permanently.")
                else:
                    st.info(f"'{cleaned}' is already saved.")

    session_terms = st.session_state["session_terms"]
    persistent_terms = load_user_additions()

    if session_terms or persistent_terms:
        st.markdown("---")

    if session_terms:
        st.markdown("**This session**")
        for i, term in enumerate(list(session_terms)):
            col_t, col_x = st.columns([5, 1])
            col_t.write(f"• {term}")
            if col_x.button("Remove", key=f"rm_sess_{i}_{term}"):
                st.session_state["session_terms"].remove(term)
                _clear_result_cache()
                st.rerun()

    if persistent_terms:
        st.markdown("**Saved permanently**")
        for i, term in enumerate(persistent_terms):
            col_t, col_x = st.columns([5, 1])
            col_t.write(f"• {term}")
            if col_x.button("Remove", key=f"rm_perm_{i}_{term}"):
                remove_user_addition(term)
                _clear_result_cache()
                st.rerun()


# Hand the engine the current session list. Persistent terms are read from
# disk by the engine itself on every analyze() call, so they don't need to be
# pushed here.
redactor.set_session_terms(st.session_state["session_terms"])


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
            # Bulk-action buttons: "Keep all <TYPE>" / "Redact all <TYPE>".
            # Useful for big documents where unchecking 30 individual SSN
            # checkboxes would be tedious. One button per entity type that
            # appears in this file's findings.
            type_counts: dict[str, int] = {}
            for f in result.findings:
                type_counts[f.entity_type] = type_counts.get(f.entity_type, 0) + 1

            with st.expander(
                f"Bulk actions ({len(type_counts)} type"
                f"{'s' if len(type_counts) != 1 else ''} present)"
            ):
                # Master "Reset" puts everything back to redacted (checked).
                if st.button(
                    "Redact everything (reset)",
                    key=_state_key(upload.name, "bulk_reset"),
                    use_container_width=True,
                ):
                    for i in range(len(result.findings)):
                        st.session_state[
                            _state_key(upload.name, f"keep::{i}")
                        ] = True
                    st.rerun()

                st.caption(
                    "Uncheck every finding of a single type with one click:"
                )
                # Sort by count desc so the most common types appear first.
                for etype, count in sorted(
                    type_counts.items(), key=lambda kv: -kv[1]
                ):
                    cols = st.columns([3, 2])
                    if cols[0].button(
                        f"Keep all `{etype}` ({count})",
                        key=_state_key(upload.name, f"bulk_keep::{etype}"),
                        use_container_width=True,
                    ):
                        for i, f in enumerate(result.findings):
                            if f.entity_type == etype:
                                st.session_state[
                                    _state_key(upload.name, f"keep::{i}")
                                ] = False
                        st.rerun()
                    if cols[1].button(
                        f"Redact all `{etype}`",
                        key=_state_key(upload.name, f"bulk_redact::{etype}"),
                        use_container_width=True,
                    ):
                        for i, f in enumerate(result.findings):
                            if f.entity_type == etype:
                                st.session_state[
                                    _state_key(upload.name, f"keep::{i}")
                                ] = True
                        st.rerun()

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
            preview = render_preview(
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
