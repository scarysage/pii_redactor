# pii-redactor

Fully local, offline desktop tool that strips PII from documents before they go
into any external AI tool. Built for a small accounting firm. Detected PII is
replaced with type tags (e.g. `<US_SSN>`). Auto-redacts on upload, then shows a
human review screen before download.

> **The one rule that overrides everything:** nothing leaves the local machine.
> No network calls at runtime, ever.

---

## What's in the box

| File / folder              | Role                                                                 |
| -------------------------- | -------------------------------------------------------------------- |
| `recognizers.py`           | Custom Presidio regex recognizers (EIN, routing, account, names)     |
| `firm_config.py`           | IT-curated baseline lists: `FIRM_NAMES` and `ALWAYS_REDACT`          |
| `user_additions.py`        | Read/write helpers for `user_additions.txt` (UI-managed)             |
| `user_additions.txt`       | UI-added persistent terms (created on first add; gitignored)         |
| `CUSTOMIZING.md`           | Plain-language guide: in-app box + editing `firm_config.py`          |
| `redactor.py`              | Presidio analyzer + anonymizer; loads vendored spaCy model           |
| `extractors.py`            | File → redacted file pipeline for `.txt`, `.pdf`, `.docx`, `.xlsx`   |
| `app.py`                   | Streamlit UI: upload → auto-redact → review → download               |
| `en_core_web_lg/`          | **Vendored** spaCy model (~620 MB). Loaded by path, never downloaded |
| `.streamlit/config.toml`   | Disables telemetry, binds Streamlit to `127.0.0.1`                   |
| `setup_once.bat`           | Windows one-time setup (creates venv, installs deps)                 |
| `START_HERE.bat`           | Windows launcher (activates venv, opens browser to the app)          |
| `setup_once.command`       | macOS one-time setup (double-clickable from Finder)                  |
| `START_HERE.command`       | macOS launcher (double-clickable from Finder)                        |
| `requirements.txt`         | Pinned dependencies                                                  |
| `tests/`                   | pytest suite (205 passing, 1 skipped, ~5 s)                          |
| `CLAUDE.md`                | Source of truth for design decisions and scope                       |
| `SECURITY_AUDIT.md`        | 2026-05-31 security audit + remediation status (CVEs, isolation)     |
| `ABOUT_PII_REDACTOR.html`  | Plain-language explainer for a non-technical reader (the boss)       |

---

## What's been built

### 1. Detection engine (`recognizers.py` + `redactor.py`)

Custom regex recognizers with context-word boosting:

| Entity tag         | Pattern                          | Notes                                   |
| ------------------ | -------------------------------- | --------------------------------------- |
| `US_EIN`           | `NN-NNNNNNN`                     | Dashed form only (undashed = SSN-shape) |
| `US_BANK_ROUTING`  | 9 digits                         | Leans on context: routing/aba/wire/...  |
| `US_BANK_ACCOUNT`  | 6–17 digits                      | Loose — context-dependent               |
| `PERSON` (firm)    | Alternation over `FIRM_NAMES`    | Strassler, Herbstman — see `firm_config.py` |
| `REDACTED` (firm)  | Alternation over `ALWAYS_REDACT` | Empty by default; firm-editable         |

Plus Presidio's built-in recognizers for `US_SSN`, `EMAIL_ADDRESS`,
`PHONE_NUMBER`, `PERSON`, `CREDIT_CARD`, `US_ITIN`, `LOCATION`,
`IBAN_CODE`, `US_PASSPORT`, `US_DRIVER_LICENSE`.

Free-text `DATE_TIME` detection is intentionally **off** (firm decision
2026-05-31): the firm does not treat prose dates as PII, and the date
detector mislabeled redacted bank numbers. A spreadsheet/table column
explicitly headed *DOB* / *Date of Birth* is still masked wholesale.

**Firm-editable lists** live in `firm_config.py`:
- `FIRM_NAMES` — names the language model misses. Currently: `Strassler`, `Herbstman`. Matched case-insensitively, whole-word, tagged `PERSON`.
- `ALWAYS_REDACT` — literal strings to always strip (account numbers, project codes, etc.). Empty by default, tagged `REDACTED`.

**End-user "Add" box** in the UI (`➕ Add a specific item to redact` expander above the uploader):
- Session-only terms — held in `st.session_state`, lost on tab close.
- Permanently-saved terms — appended to `user_additions.txt`, persist across restarts.

**First-name policy** (per firm directive — first names are NOT redacted):
- `FIRM_NAMES` matches → full redact (curated surnames).
- Multi-word PERSON spans → shrunk to the last word ("Jane Doe" → "Jane `<PERSON>`").
- Single-word PERSON spans not in `FIRM_NAMES` → dropped. If a specific surname must be caught, add it to `FIRM_NAMES`.

See [`CUSTOMIZING.md`](CUSTOMIZING.md) for the plain-language guide.

Threshold for surfacing a finding: `0.35` (empirical — low enough to catch our
context-boosted custom recognizers, high enough to drop noise).

### 2. File handlers (`extractors.py`)

| Format  | Input handling                                | Output                                           |
| ------- | --------------------------------------------- | ------------------------------------------------ |
| `.txt`  | UTF-8 read                                    | Plain text with `<TYPE>` tags                    |
| `.pdf`  | `pdfplumber` page-by-page text extract        | **Plain `.txt`** (per CLAUDE.md, keep PDFs simple) |
| `.docx` | Walk paragraphs + table cells via python-docx | `.docx` with redacted runs styled **bold + red** |
| `.xlsx` | openpyxl, per-sheet                           | `.xlsx` with redacted cells styled bold + red on pale yellow |

**Excel handling** (the hard part — per CLAUDE.md):

1. Headers in row 1.
2. Columns flagged as sensitive by either:
   - header keyword (`SSN`, `EIN`, `Routing`, `Account #`, `Client ID`, `Name`, `DOB`, `Address`, `Email`, `Phone`, ...), or
   - sample-scan of up to 20 non-empty cells, ≥ 40% PII hits **and** ≥ 3 absolute hits (the latter avoids over-flagging on tiny sheets).
3. Free-text columns (`Notes`, `Comments`, `Description`, `Memo`, ...) are **exempt** from wholesale masking and get cell-level scans instead.
4. Flagged columns are masked wholesale (`<US_SSN>`, `<COLUMN_REDACTED>`, ...).
5. Other columns get per-cell span detection.
6. Leading zeros / text-formatted numbers preserved — values are read as strings, never coerced to int, and modified cells are set to text format (`@`).

### 3. UI (`app.py`)

Streamlit web app, served on `127.0.0.1` only:

- Multi-file drop zone (`.txt`, `.pdf`, `.docx`, `.xlsx`).
- Auto-redacts on upload, caches the result in session state so checkbox clicks don't re-run the engine.
- Two-pane review screen: findings checklist on the left, live preview on the right.
- Uncheck any finding to **keep** the original text (false positive). Re-checking re-redacts.
- Redacted spans rendered **bold + red** to match the in-document style.
- Download button returns the rewritten document (or plain text for PDF input).

### 4. Tests (`tests/`, **205 passing, 1 skipped in ~5 s**)

- `test_recognizers.py` — regex-only tests for the custom recognizers. Fast, no spaCy load.
- `test_redactor.py` — end-to-end: Presidio + vendored model detects each entity type, output contains `<TYPE>` tags, original PII absent, `apply_decisions()` honors "keep" choices.
- `test_extractors.py` — round-trips for `.txt`, `.docx` (incl. bold+red styling), `.xlsx` (header-flag, free-text cell-level, leading-zero preservation, unsupported-ext error).
- Plus deeper suites: `test_pii_battery.py` (breadth-first recognizer battery + adversarial cases), `test_offline_guarantee.py` (network-isolation), `test_security_hardening.py` (magic-byte upload check + filename sanitization — see the 2026-05-31 security pass), `test_preview.py`, `test_labels.py` (review-screen display names), `test_missing_model.py`, and the `*_deep.py` extractor/redactor tests.

Synthetic data only. See [`tests/fixtures/README.md`](tests/fixtures/README.md).

### 5. Offline guarantee — how it's enforced

- spaCy model loaded by **absolute path** to `./en_core_web_lg/` (resolved relative to `redactor.py`, not CWD). No `spacy.cli.download` anywhere in runtime code.
- `redactor.py` raises a clear error if the vendored model folder is missing — instead of silently trying to download one.
- `.streamlit/config.toml` disables Streamlit's usage-stats telemetry and binds the server to `127.0.0.1`.
- `setup_once.bat` aborts if the vendored model is missing rather than fetching it.
- `requirements.txt` is pinned and minimal.

A full security audit ran 2026-05-31 (`SECURITY_AUDIT.md`): all known dependency
CVEs were cleared (pinned `pdfminer.six 20251230`, `streamlit 1.58.0`,
`pillow 12.2.0`), and the upload path was hardened — a magic-byte signature
check (`extractors._verify_file_signature`) rejects files whose bytes don't
match their extension, uploaded filenames are reduced to a bare basename before
any path join, and `maxUploadSize` is capped at 100 MB. `pip-audit` now reports
zero known vulnerabilities.

### 6. Packaging — Windows (primary) + macOS (secondary)

Both platforms share the same logic: script-dir anchoring, vendored-model
presence check, venv creation, pinned-deps install, browser auto-open at
launch. Neither downloads the spaCy model — it must ship in the zip.

**Windows**
- `setup_once.bat` — finds Python via `py -3` or `python`, creates `.venv\`, installs `requirements.txt`. Refuses to run if the vendored model is missing.
- `START_HERE.bat` — runs Streamlit from the venv, opens the default browser.

**macOS**
- `setup_once.command` — finds `python3` (Homebrew or python.org), enforces Python 3.10+, creates `.venv/`, installs `requirements.txt`. Refuses to run if the vendored model is missing.
- `START_HERE.command` — runs Streamlit from the venv, opens the default browser via `open`.

> ⚠️ Per CLAUDE.md's packaging test gate: `requirements.txt` is now a **fully
> pinned lock** (every transitive dependency pinned to a verified version, not
> just the top-level packages), so a fresh install gets the exact versions
> tested here — no silent drift. A cache-less `pip install -r requirements.txt`
> from that lock was verified to install cleanly and pass the full suite (205
> tests) in a clean virtualenv on **Python 3.12 / Linux** (2026-05-31). Still
> outstanding before distribution: the `.bat` / `.command` launcher scripts on
> **real Windows / macOS hardware**, and a fresh install on **Python 3.10 / 3.11**
> (the pinned versions were chosen for 3.10–3.12 compatibility but not yet
> exercised there).

---

## Running the app (dev: macOS / Linux)

```bash
# One-time after `git clone`
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/vendor_model.py   # downloads + copies the spaCy model into ./en_core_web_lg/

# Run the app
.venv/bin/streamlit run app.py
# Browse to http://127.0.0.1:8501

# Tests
.venv/bin/python -m pytest -q
```

`scripts/vendor_model.py` is **dev-only** — it pulls the model from PyPI.
It is *never* run on a distributed installation; the Windows IT path gets
the model pre-vendored inside the distribution zip.

## Running on Windows (primary distribution target)

1. Unzip to a **permanent** location — `C:\pii-redactor\` recommended. *Not* Downloads or a temp folder.
2. If Windows blocks the `.bat` files (Mark of the Web), right-click → Properties → tick "Unblock".
3. Double-click `setup_once.bat` (once per PC).
4. Double-click `START_HERE.bat` to launch.

## Running on macOS (secondary)

1. Unzip to a **permanent** location — `~/Applications/pii-redactor/` or `~/Documents/pii-redactor/` works. *Not* Downloads.
2. The first time you double-click a `.command` file, macOS Gatekeeper will block it ("cannot be opened because the developer cannot be verified"). Right-click the file → **Open** → click **Open** in the dialog. After that, normal double-click works.
3. Double-click `setup_once.command` (once per Mac).
4. Double-click `START_HERE.command` to launch.
5. Requires Python 3.10+ installed. If you don't have it: `brew install python@3.12` or download from [python.org/downloads](https://www.python.org/downloads/).

---

## Known limitations / scope notes (v1)

- **PERSON detection is the weak link.** spaCy NER misses unusual names and over-flags some common words. The human review screen is the safety net — don't let it become a rubber stamp.
- **PDF output is plain text.** Per CLAUDE.md, "keep PDF output simple" — no in-place PDF rewriting in v1.
- **DOCX inline formatting inside a redacted paragraph is lost** (bold/italic the user applied gets dropped when we rewrite runs). Acceptable trade-off for v1: redaction correctness > inline formatting.
- **Test SSNs** like `123-45-6789` are filtered out by Presidio's "obvious sample" check — use realistic-looking-but-fake numbers (e.g. `456-78-9012`) in fixtures.

## Out of scope for v1

Batch processing, audit logs, reversible tokens, multi-user/server modes, any networked feature. See CLAUDE.md.

---

## Open `[TODO]` items from CLAUDE.md

These are marked in CLAUDE.md and still need a real answer from the firm/maintainer:

- ~~Confirm the exact bold + red hex~~ — **`#C00000` confirmed.**
- ~~Decide whether `en_core_web_lg/` is tracked in git~~ — **out-of-band: ships in the distribution zip; `.gitignore`d in the repo.** `scripts/vendor_model.py` does the dev fetch.
- ~~Add firm-specific names that spaCy misses~~ — **Strassler & Herbstman added** to `firm_config.FIRM_NAMES`.
- ~~Confirm the exact `CLIENT_ID` format~~ — **no separate client ID concept; tax IDs only, already covered.** `CLIENT_ID` recognizer removed.
- ~~Make customization easy for the firm~~ — **`firm_config.py` + `CUSTOMIZING.md` added.** Firm edits two lists; no code changes needed.
- Confirm fixtures directory layout (currently `tests/fixtures/`).
- Confirm git workflow (branching, commit message style).
- Confirm `RUNBOOK.md` ownership.

---

## License

Proprietary. Distribution and use are governed by the commercial EULA in
[`LICENSE`](LICENSE) (as-is, no warranty; NJ governing law). That file is a
starter template and **needs lawyer review before the first paid sale.**
Third-party components are attributed in
[`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md).
