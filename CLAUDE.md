# CLAUDE.md — pii-redactor

Fully local, offline desktop tool that strips PII (SSNs, EINs, bank/routing numbers,
client IDs, names) from documents before they go into any external AI tool. Built for a
small accounting firm. Detected PII is replaced with type tags (e.g. `<US_SSN>`).
Auto-redacts on upload, then shows a human review screen before download.

**The one rule that overrides everything: nothing leaves the local machine. No network
calls at runtime, ever.** See "Offline guarantee" below.

---

## Commands

Dev runs on macOS or Linux. Distribution targets are Windows (primary) and
macOS (secondary, added for one user). See "Packaging".

```bash
# Run the app during dev
streamlit run app.py

# Tests (redaction + extraction logic against fixtures)
pytest                          # [TODO: confirm pytest is wired up]

# Lint + format
ruff check .                    # [TODO: confirm ruff is wired up]
ruff format .                   # OR: black .   [TODO: confirm which]

# Install / refresh deps (pinned)
pip install -r requirements.txt
```

* `START_HERE.bat` + `setup_once.bat` are **Windows-only**. Run them only in
  the Windows VM, not on a Mac/Linux dev machine.
* `START_HERE.command` + `setup_once.command` are **macOS-only** equivalents
  (double-clickable from Finder). They share the same offline / vendored-model
  guarantees as the `.bat` files. Test on a real Mac before relying on them
  for distribution.

---

## Architecture

Flat single-package layout. Build and modify in this order; don't skip ahead.

1. `recognizers.py` — custom regex recognizers (EIN, routing numbers, client IDs).
2. `redactor.py` — Presidio analyzer + anonymizer config; wires in custom recognizers;
   maps detected entities to `<TYPE>` tags.
3. `extractors.py` — file → text/structured. PDF via pdfplumber, DOCX via python-docx,
   XLSX via openpyxl.
4. `app.py` — Streamlit UI: upload → auto-redact → review screen → download.

Engine (1–2) first, then file handling (3), then UI (4), then packaging.

### Excel handling (get this right — it's the hard part)

Hybrid approach, per sheet, looping all sheets:

* Auto-flag sensitive columns by header name **and** a sample-scan of cell values.
* Mask flagged columns wholesale.
* Run cell-level detection on free-text / notes columns.
* Preserve leading zeros / text-formatted numbers — read cells as their stored
  string form; do not let openpyxl coerce `0123` → `123` or strip formatting.

### Review-screen visual style

* ONE consistent style for redacted items:  **bold + color** . Apply it in the review UI
  for all file types.
* Bake it into output for DOCX and XLSX where it's clean.
* Keep PDF output simple (plain `<TYPE>` tags, no styling gymnastics).
* [TODO: confirm exact color/hex if you've already picked one.]

---

## Offline guarantee (non-negotiable)

* **No outbound network calls of any kind at runtime.** No telemetry, no cloud APIs,
  no analytics, no update checks, no model downloads.
* The spaCy model `en_core_web_lg/` is **vendored** in the repo. Never add code that
  downloads it (`spacy.cli.download`, `spacy.load("en_core_web_lg")` relying on a pip
  install, etc.). Load it from the local vendored path only.
* If a task seems to need a network call, stop and flag it — don't add one.
* Never add a dependency that phones home. Keep `requirements.txt` pinned and minimal.

---

## Boundaries — do NOT touch

* `en_core_web_lg/` — vendored model. Read-only. Never edit, regenerate, or re-download.
* `*.bat` files — propose changes in chat; do not silently rewrite. They're fragile and
  Windows-specific (path handling, venv activation, Mark-of-the-Web sensitivity).
* `RUNBOOK.md` — [TODO: confirm who maintains this. Default: don't edit without asking.]
* Never read, create, or commit real client documents or any file containing real PII.
  Test only against dummy fixtures. [TODO: confirm fixtures dir, e.g. `tests/fixtures/`.]

---

## Code style

Maintainer is a Python-comfortable but inconsistent in-house IT person. Optimize for
someone else picking this up, not for cleverness.

* Simple, readable, low-cleverness Python. No one-liners that need decoding.
* **Add comments here** (unlike past projects) — explain  *why* , especially in the Excel
  logic and the recognizer regexes. The next maintainer needs them.
* Type hints on function signatures.
* Prefer stdlib and the existing deps over adding new ones.
* Match `ruff`/`black` formatting; don't fight the formatter.
* [TODO: confirm any rules a formatter won't catch — max function length, docstring style.]

---

## Packaging (Windows is the real target)

The tool ships as a zip from a shared link. IT downloads it, unzips to a **permanent**
location (`C:\pii-redactor\`, NOT Downloads), runs `setup_once.bat` once per PC, then
uses `START_HERE.bat`.

Known failure modes — design against all of them:

* Must work on a Windows PC that has never had Python installed (`setup_once.bat`).
* Must not assume it's run from Downloads or a temp folder (use absolute/relative paths
  anchored to the script location, not the CWD).
* Windows "Mark of the Web" can block downloaded `.bat` files — account for this in
  RUNBOOK instructions.
* Updates re-upload to the same link; the model stays vendored, never fetched.

**Test gate:** before drafting/finalizing any packaging change for distribution, it must
be validated on Windows (a Windows VM is fine). macOS/Linux dev passing is NOT sufficient
proof it ships. Flag this if a packaging change hasn't been Windows-tested.

---

## Scope (v1 — resist creep)

In scope: the redaction pipeline, the four file types, the review screen, offline packaging.

**Out of scope for v1** (do not build unless asked): batch processing, audit logs,
reversible tokens, multi-user/server modes, any networked feature.

PERSON-name detection is the known weak link (misses unusual names, over-flags common
words). Treat the human review screen as the safety net, and make misses visually
obvious — don't let the spot-check become a rubber stamp.

---

## Git workflow

[TODO: confirm whether this project is in git at all, or version-controlled only via the
zip-on-a-share. If git exists, confirm: commit message convention, branch/PR flow vs
commit-to-main.]

If in git: never commit `en_core_web_lg/` if it bloats the repo (decide via `.gitignore`),
and **never** commit client docs, PII fixtures, or anything revealing client structure.

---

## Compliance background (context, not a task)

Accounting firm handling real client PII — IRS §7216 and the FTC Safeguards Rule are
relevant background. They reinforce the offline guarantee; they are not features to build.
