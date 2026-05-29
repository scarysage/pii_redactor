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
| `recognizers.py`           | Custom Presidio regex recognizers (EIN, routing, account, client ID) |
| `redactor.py`              | Presidio analyzer + anonymizer; loads vendored spaCy model           |
| `extractors.py`            | File → redacted file pipeline for `.txt`, `.pdf`, `.docx`, `.xlsx`   |
| `app.py`                   | Streamlit UI: upload → auto-redact → review → download               |
| `en_core_web_lg/`          | **Vendored** spaCy model (~620 MB). Loaded by path, never downloaded |
| `.streamlit/config.toml`   | Disables telemetry, binds Streamlit to `127.0.0.1`                   |
| `setup_once.bat`           | Windows one-time setup (creates venv, installs deps)                 |
| `START_HERE.bat`           | Windows launcher (activates venv, opens browser to the app)          |
| `requirements.txt`         | Pinned dependencies                                                  |
| `tests/`                   | pytest suite (31 tests, ~3 s)                                        |
| `CLAUDE.md`                | Source of truth for design decisions and scope                       |

---

## What's been built

### 1. Detection engine (`recognizers.py` + `redactor.py`)

Custom regex recognizers with context-word boosting:

| Entity tag         | Pattern                          | Notes                                   |
| ------------------ | -------------------------------- | --------------------------------------- |
| `US_EIN`           | `NN-NNNNNNN`                     | Dashed form only (undashed = SSN-shape) |
| `US_BANK_ROUTING`  | 9 digits                         | Leans on context: routing/aba/wire/...  |
| `US_BANK_ACCOUNT`  | 6–17 digits                      | Loose — context-dependent               |
| `CLIENT_ID`        | `[A-Z]{3}-\d{4,6}` (e.g. ABC-123)| Firm-specific format — **confirm**      |

Plus Presidio's built-in recognizers for `US_SSN`, `EMAIL_ADDRESS`,
`PHONE_NUMBER`, `PERSON`, `CREDIT_CARD`, `US_ITIN`, `LOCATION`, `DATE_TIME`,
`IBAN_CODE`, `US_PASSPORT`, `US_DRIVER_LICENSE`.

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

### 4. Tests (`tests/`, **31 passing in ~3 s**)

- `test_recognizers.py` — regex-only tests for the four custom recognizers. Fast, no spaCy load.
- `test_redactor.py` — end-to-end: Presidio + vendored model detects each entity type, output contains `<TYPE>` tags, original PII absent, `apply_decisions()` honors "keep" choices.
- `test_extractors.py` — round-trips for `.txt`, `.docx` (incl. bold+red styling), `.xlsx` (header-flag, free-text cell-level, leading-zero preservation, unsupported-ext error).

Synthetic data only. See [`tests/fixtures/README.md`](tests/fixtures/README.md).

### 5. Offline guarantee — how it's enforced

- spaCy model loaded by **absolute path** to `./en_core_web_lg/` (resolved relative to `redactor.py`, not CWD). No `spacy.cli.download` anywhere in runtime code.
- `redactor.py` raises a clear error if the vendored model folder is missing — instead of silently trying to download one.
- `.streamlit/config.toml` disables Streamlit's usage-stats telemetry and binds the server to `127.0.0.1`.
- `setup_once.bat` aborts if the vendored model is missing rather than fetching it.
- `requirements.txt` is pinned and minimal.

### 6. Windows packaging (built, **not yet Windows-validated**)

- `setup_once.bat` — anchors to its own directory (not CWD), finds Python via `py -3` or `python`, creates `.venv\`, installs `requirements.txt`. Refuses to run if the vendored model is missing.
- `START_HERE.bat` — anchors to its own directory, opens browser to `http://127.0.0.1:8501`, runs Streamlit from the venv.

> ⚠️ Per CLAUDE.md's packaging test gate: these scripts have only been written, not run on a Windows VM. They must be validated on Windows before being relied on for distribution.

---

## Running the app (dev: macOS / Linux)

```bash
# One-time
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# Vendor the spaCy model (one-time dev setup; not at runtime)
.venv/bin/python -m spacy download en_core_web_lg
# Then copy the model data into ./en_core_web_lg/ (see CLAUDE.md offline guarantee)

# Run the app
.venv/bin/streamlit run app.py
# Browse to http://127.0.0.1:8501

# Tests
.venv/bin/python -m pytest -q
```

## Running on Windows (target)

1. Unzip to a **permanent** location — `C:\pii-redactor\` recommended. *Not* Downloads or a temp folder.
2. If Windows blocks the `.bat` files (Mark of the Web), right-click → Properties → tick "Unblock".
3. Double-click `setup_once.bat` (once per PC).
4. Double-click `START_HERE.bat` to launch.

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

- Confirm the exact `CLIENT_ID` format used internally (currently assuming `ABC-12345`).
- Confirm the exact bold + red hex (currently `#C00000`).
- Confirm fixtures directory layout (currently `tests/fixtures/`).
- Decide whether `en_core_web_lg/` is tracked in git (LFS) or distributed out-of-band — currently *not* `.gitignore`d, so it would be committed as-is.
- Confirm git workflow (branching, commit message style).
- Confirm `RUNBOOK.md` ownership.

---

## License

Internal tool. Not for redistribution outside the firm.
