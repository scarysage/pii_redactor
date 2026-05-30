# Copyright (c) 2026 Vincent Shahinllari. All rights reserved.
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

APP_VERSION = "v1.0"


def _state_key(filename: str, suffix: str) -> str:
    return f"{filename}::{suffix}"


# ---------------------------------------------------------------------------
# Visual style ("Midnight" -- near-black canvas, cream text, amber CTA)
# ---------------------------------------------------------------------------
# All CSS lives inline here so the app stays offline-safe (no external
# stylesheet fetch). Streamlit's native theme handles the basic palette;
# this block tightens button shape, hover behavior, vertical rhythm,
# adds the offline-status badge, and paints a faint redaction-bar
# pattern across the page background as a thematic watermark.
#
# If you tweak the palette in .streamlit/config.toml, update the variables
# below to match -- they are duplicated intentionally so the CSS works even
# if Streamlit's theme variables aren't exposed via CSS custom properties
# in the version we ship with.
_BG_MAIN = "#0F172A"        # slate-900 (page background)
_BG_PANEL = "#1E293B"       # slate-800 (expander, preview panel, alt bg)
_BG_PANEL_2 = "#334155"     # slate-700 (subtle panel divider)
_TEXT_PRIMARY = "#F8FAFC"   # slate-50 (body text)
_TEXT_MUTED = "#94A3B8"     # slate-400 (captions, helper text)
_BORDER = "#334155"         # slate-700 (1px borders on dark)
_AMBER = "#F59E0B"          # amber-500 (primary CTA)
_AMBER_HOVER = "#D97706"    # amber-600 (CTA hover)
_OFFLINE_GREEN = "#34D399"  # emerald-400 (brighter green for dark bg)
_OFFLINE_GREEN_BG = "rgba(16,185,129,0.12)"  # emerald-500 @ 12% alpha
_OFFLINE_GREEN_BORDER = "rgba(52,211,153,0.40)"

# Background watermark: faint redaction bars tiled across the page. Inline
# SVG data URI so nothing is fetched at runtime. fill-opacity is small
# enough (~6% white on slate-900) that the bars register as texture, not
# content. Pattern is intentionally irregular so tiled seams don't read
# as obvious grid lines.
_REDACTION_BAR_SVG = (
    "data:image/svg+xml;utf8,"
    "<svg xmlns='http://www.w3.org/2000/svg' width='300' height='180' "
    "viewBox='0 0 300 180'>"
    "<g fill='%23FFFFFF' fill-opacity='0.06'>"
    "<rect x='10' y='28' width='80' height='8' rx='1'/>"
    "<rect x='100' y='28' width='40' height='8' rx='1'/>"
    "<rect x='150' y='28' width='60' height='8' rx='1'/>"
    "<rect x='220' y='28' width='50' height='8' rx='1'/>"
    "<rect x='30' y='68' width='50' height='8' rx='1'/>"
    "<rect x='90' y='68' width='90' height='8' rx='1'/>"
    "<rect x='190' y='68' width='40' height='8' rx='1'/>"
    "<rect x='240' y='68' width='45' height='8' rx='1'/>"
    "<rect x='0' y='108' width='70' height='8' rx='1'/>"
    "<rect x='80' y='108' width='40' height='8' rx='1'/>"
    "<rect x='130' y='108' width='80' height='8' rx='1'/>"
    "<rect x='220' y='108' width='60' height='8' rx='1'/>"
    "<rect x='40' y='148' width='60' height='8' rx='1'/>"
    "<rect x='110' y='148' width='70' height='8' rx='1'/>"
    "<rect x='190' y='148' width='50' height='8' rx='1'/>"
    "<rect x='250' y='148' width='30' height='8' rx='1'/>"
    "</g></svg>"
)

st.markdown(
    f"""
    <style>
      /* --------------------------------------------------------------
         HIDE STREAMLIT'S BUILT-IN TOOLBAR (Deploy button + 3-dot menu)
         --------------------------------------------------------------
         This is non-negotiable for an offline-only tool:
           * The "Deploy" button pushes to Streamlit Community Cloud,
             which is a network operation and an out-of-scope feature
             for a tool that promises local-only execution.
           * The 3-dot main menu exposes "Get help" and "Report a bug"
             links that hit streamlit.io over the network.
           * The "Running" status widget is engine-internal noise that
             confuses non-technical users.
         Hiding the entire stHeader is the cleanest path -- nothing in
         it serves an end user of an offline desktop tool. */
      [data-testid="stHeader"],
      [data-testid="stToolbar"],
      [data-testid="stAppDeployButton"],
      [data-testid="stMainMenu"],
      [data-testid="stStatusWidget"] {{
          display: none !important;
          visibility: hidden !important;
      }}

      /* --------------------------------------------------------------
         PAGE BACKGROUND -- inline-SVG redaction-bar watermark on the
         slate-900 canvas. The SVG is a data URI so nothing is fetched
         at runtime (offline guarantee preserved).
         -------------------------------------------------------------- */
      .stApp {{
          background-color: {_BG_MAIN} !important;
          background-image: url("{_REDACTION_BAR_SVG}");
          background-repeat: repeat;
          background-attachment: fixed;
      }}

      /* Tighter top padding -- Streamlit's default leaves a lot of dead space. */
      .main .block-container {{
          padding-top: 1.5rem;
          padding-bottom: 3rem;
          max-width: 1100px;
      }}

      /* Title sits closer to the badge row. Explicit normalization so
         Streamlit's default heading styles (which can vary between
         theme versions) don't force uppercase / extreme letter-spacing. */
      h1 {{
          margin-top: 0 !important;
          margin-bottom: 0.25rem !important;
          color: {_TEXT_PRIMARY};
          font-weight: 600;
          font-size: 2rem;
          letter-spacing: -0.015em;
          text-transform: none !important;
          font-variant: normal !important;
      }}

      /* Section headers (st.subheader / st.markdown bold) -- restrained. */
      h2, h3 {{
          color: {_TEXT_PRIMARY};
          font-weight: 600;
          margin-top: 1.5rem;
      }}

      /* Body text inherits Streamlit's textColor, but reinforce here so
         elements that render in different DOM contexts (markdown spans,
         caption text inside expanders) stay legible on the dark canvas. */
      p, label, span {{
          color: {_TEXT_PRIMARY};
      }}

      /* Captions and helper text in muted slate. */
      .stCaption, [data-testid="stCaptionContainer"] p,
      [data-testid="stCaptionContainer"] span {{
          color: {_TEXT_MUTED} !important;
      }}

      /* All Streamlit buttons: 6px radius, snappier hover. The native
         theme sets the amber primary via primaryColor in config.toml. */
      .stButton > button, .stDownloadButton > button {{
          border-radius: 6px;
          font-weight: 500;
          padding: 0.45rem 1rem;
          transition: background-color 120ms ease, transform 80ms ease,
                      border-color 120ms ease, color 120ms ease;
      }}
      .stButton > button:hover, .stDownloadButton > button:hover {{
          transform: translateY(-1px);
      }}

      /* DEFAULT (non-primary) buttons get a ghost / outlined treatment
         tuned for the dark canvas. Streamlit doesn't reliably set a
         `kind="secondary"` attribute on every button --
         :not([kind="primary"]) catches both labeled secondary and the
         default unmarked ones. */
      .stButton > button:not([kind="primary"]) {{
          background-color: {_BG_PANEL} !important;
          color: {_TEXT_PRIMARY} !important;
          border: 1px solid {_BORDER} !important;
      }}
      .stButton > button:not([kind="primary"]):hover {{
          background-color: {_BG_PANEL_2} !important;
          border-color: {_AMBER} !important;
          color: {_AMBER} !important;
      }}

      /* Primary buttons (type="primary") get a deeper amber hover. */
      .stButton > button[kind="primary"]:hover,
      .stDownloadButton > button[kind="primary"]:hover {{
          background-color: {_AMBER_HOVER} !important;
          border-color: {_AMBER_HOVER} !important;
          color: {_BG_MAIN} !important;
      }}

      /* Findings checkboxes: a touch more vertical breathing room so the
         list reads cleanly on docs with 20+ items. */
      [data-testid="stCheckbox"] {{
          margin-bottom: 0.35rem;
      }}

      /* Divider lines blend into the dark canvas with a subtle slate. */
      hr {{
          border-color: {_BORDER} !important;
          margin: 1.25rem 0 !important;
      }}

      /* The offline-status pill sitting top-right of the header.
         On the dark canvas we use an emerald-tinted background + brighter
         text/dot so the pill stays readable but doesn't shout. */
      .pii-badge {{
          display: inline-flex;
          align-items: center;
          gap: 0.45rem;
          padding: 0.35rem 0.75rem;
          background-color: {_OFFLINE_GREEN_BG};
          border: 1px solid {_OFFLINE_GREEN_BORDER};
          border-radius: 999px;
          color: {_OFFLINE_GREEN};
          font-size: 0.85rem;
          font-weight: 600;
          letter-spacing: 0.01em;
      }}
      .pii-badge::before {{
          content: "";
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background-color: {_OFFLINE_GREEN};
          box-shadow: 0 0 6px {_OFFLINE_GREEN};
      }}
      .pii-badge-sub {{
          color: {_TEXT_MUTED};
          font-size: 0.78rem;
          margin-top: 0.25rem;
          text-align: right;
      }}
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Header: title (left) + offline badge (right)
# ---------------------------------------------------------------------------

_header_left, _header_right = st.columns([3, 2])
with _header_left:
    st.title("PII Redactor")
    st.caption(
        "Upload a document, review what was caught, and download the "
        "redacted copy."
    )
with _header_right:
    st.markdown(
        f"""
        <div style="text-align: right; padding-top: 0.5rem;">
          <span class="pii-badge">Offline · {APP_VERSION}</span>
          <div class="pii-badge-sub">
            Your data stays on this computer
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.divider()


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
            # Preview panel inherits the dark secondary-bg palette so it
            # sits quietly inside the page; monospace keeps redacted-text
            # spans from reflowing as the user toggles findings. The
            # text color is forced to slate-50 so the unredacted content
            # stays legible -- the redacted spans still get their #C00000
            # styling from preview.render_preview, which now reads as a
            # bright signal against the dark panel.
            st.markdown(
                f"<div style='white-space:pre-wrap; font-family:ui-monospace, "
                f"SFMono-Regular, Menlo, Consolas, monospace; "
                f"background:{_BG_PANEL}; color:{_TEXT_PRIMARY}; "
                f"padding:1rem; "
                f"border:1px solid {_BORDER}; "
                f"border-radius:8px; max-height:520px; overflow:auto; "
                f"font-size:0.9rem; line-height:1.55;'>"
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
        type="primary",
        use_container_width=False,
    )
