# CLAUDE.md — pii-redactor

Fully local, offline desktop tool that strips PII (SSNs, EINs, bank/routing
numbers, names, addresses) from documents before they go into any external
AI tool. Built for a small accounting firm. Detected PII is replaced with
type tags (e.g. `<US_SSN>`). Auto-redacts on upload, then shows a human
review screen before download.

**The one rule that overrides everything: nothing leaves the local machine.
No network calls at runtime, ever.** See "Offline guarantee" below.

---

## ✅ Resolved 2026-05-31: security audit + remediation

A full security audit ran this session — report in `SECURITY_AUDIT.md`
(threat model: supply-chain compromise, accidental exfiltration, malicious
dependencies, unsafe code). Every finding was fixed the same day. After the
pass, `pip-audit` reports **0 known CVEs** and the suite is **205 passing,
1 skipped**.

**Dependency bumps (all security-driven; engine deliberately held):**

* `pdfplumber` 0.11.4 → **0.11.9**, which pulls patched **`pdfminer.six`
  20251230** (now pinned explicitly in `requirements.txt`). Fixes a
  Critical pickle-based RCE (CVE-2025-64512) that a malicious PDF could
  trigger — and PDFs are exactly what this tool parses.
* `streamlit` 1.39.0 → **1.58.0** (clears CVE-2026-33682, a Windows
  path-traversal). **This swapped Streamlit's Tornado server for a
  starlette/uvicorn/websockets stack.** The toolbar-hiding `data-testid`
  selectors were re-verified present in the 1.58 JS bundle, all `st.*`
  APIs used by `app.py` confirmed to still exist, and config keys
  validated. See "Boundaries" for the (now 1.58) pin.
* `pillow` 10.4.0 → **12.2.0** (pinned; was coupled to the Streamlit bump
  because the old `streamlit` capped `pillow<11`). Clears several
  image/PDF parsing flaws.
* `pytest` 8.3.3 → **9.0.3** (dev-only).
* **spaCy 3.7.5 / numpy 1.26.4 were held fixed** through all of the above
  — the redaction engine is untouched. `pip check` is clean.

**Code/config hardening:**

* `app.py` upload handler reduces the browser-supplied filename to a bare
  basename (strips POSIX *and* Windows separators) before any path join,
  so a crafted name can't escape the temp dir.
* `extractors._verify_file_signature()` runs a magic-byte check before any
  parser sees the file: `.pdf` must contain `%PDF` in its first 1 KB,
  `.docx`/`.xlsx` must start with the ZIP header `PK\x03\x04`, `.txt` is
  unchecked. Deliberately lenient — it never rejects a genuine document.
  Backstops the extension-only upload filter.
* `.streamlit/config.toml` sets `maxUploadSize = 100` (MB) — a DoS guard so
  one oversized/malformed file can't exhaust parser memory. (Was the
  Streamlit default of 200; briefly 50 during the pass, raised to 100 so
  large scanned PDFs still upload.)

**New files:** `SECURITY_AUDIT.md` (full report + remediation-status table),
`tests/test_security_hardening.py` (11 regression tests: magic-byte check +
filename sanitization).

**Still open (low priority):** hashed requirements (`--require-hashes`) for
distribution builds — optional supply-chain hardening, not blocking. The
new starlette/uvicorn server stack carries no known CVEs but widens the
dependency surface; re-run `pip-audit` before each release.

---

## ✅ Resolved 2026-05-31: DATE_TIME vs routing/account label collision

**Decision: Fix B.** Vincent chose to drop `DATE_TIME` from
`redactor.DEFAULT_ENTITIES` rather than raise routing's base score. spaCy's
free-text date detector no longer runs, so it can't out-score (0.85) or
mislabel our context-boosted routing/account recognizers (~0.65). Bank
numbers now carry their correct labels on the review screen.

**Trade-off the firm accepted:** real prose dates (`January 5, 2024`,
`04/15/2024`, `Q3 2023`) are no longer redacted. An explicitly *DOB* /
*Date of Birth* spreadsheet/table **column** is still masked wholesale —
that path is in `extractors.py` and is independent of `DEFAULT_ENTITIES`.

**Review-screen labeling:** the DOB column path still emits the raw
`<DATE_TIME>` tag into the file, and `labels.py` maps `DATE_TIME` →
"Date of Birth" so the review screen shows that friendly label rather than
a bare tag. This is consistent with the fix — free-text dates stay
un-redacted, DOB columns read correctly. If `DATE_TIME` is ever re-added to
`DEFAULT_ENTITIES` (don't, without asking Vincent — see memory), revisit
that label, since it would then also cover prose dates, not just DOB.

Regression coverage: `tests/test_redactor.py::TestDateTimePolicy` and an
updated `test_pii_battery.py::test_ein_in_sentence_with_year`. Full detail
in `RECOGNITION_AUDIT.md` (DATE_TIME section, marked CLOSED).

---

## Status & handoff (last session: 2026-05-29, post-audit)

The tool is functional end-to-end on Mac. A breadth-first recognition audit
landed in this session — see `RECOGNITION_AUDIT.md` for the full report.

**What's been built and verified locally:**

* All four file formats round-trip (`.txt`, `.pdf`, `.docx`, `.xlsx`).
* Engine: Presidio + vendored spaCy `en_core_web_lg` (loaded by path).
* Custom recognizers in `recognizers.py`:
  - `US_EIN` (dashed `NN-NNNNNNN`)
  - `US_BANK_ROUTING` (9-digit, context-boosted)
  - `US_BANK_ACCOUNT` (6–8 or 10–17 digit; **9-digit excluded by design**
    to resolve the collision with routing — see Open Work #2 below)
  - US street addresses + PO Boxes, tagged `LOCATION`
  - `US_ZIP` (new this session; tagged `LOCATION`) — high-confidence after
    a 2-letter state prefix (`NJ 07102`), low-confidence with ZIP context
    word, silent on bare 5-digit numbers like `12345 employees`
  - `PHONE_NUMBER` (custom replacement for Presidio's default) — requires
    phone-shaped formatting (parens / dashes / dots / spaces); bare
    10-digit strings like `4155550123` are NOT tagged as phone
  - `FIRM_NAMES` deny-list (currently `Strassler`, `Herbstman`), tagged `PERSON`
  - `ALWAYS_REDACT` literal-match list, tagged `REDACTED`
* First-name policy enforced post-Presidio: full-name spans trim to the
  last token (with multi-part surname particles absorbed — `Lars van der
  Berg` trims to `Lars <PERSON>`, not `Lars van der <PERSON>`); single-word
  non-firm PERSON spans drop. (See `redactor._enforce_no_first_names`.)
* User-editable knobs:
  - `firm_config.py` — IT-curated `FIRM_NAMES` and `ALWAYS_REDACT` lists
  - `user_additions.txt` — UI-managed persistent terms (per-installation,
    gitignored)
  - In-UI session-only terms via the `➕ Add a specific item to redact`
    expander; persistent terms also added through that UI write to
    `user_additions.txt`
  - Bulk "Keep all `<TYPE>`" / "Redact all `<TYPE>`" / "Redact everything
    (reset)" buttons in the review pane
* Excel: hybrid column-header masking (sensitive headers → wholesale mask;
  free-text columns → cell-level scan; leading-zero preservation).
* DOCX: per-paragraph scan **plus** table column-header masking (same
  hybrid logic as XLSX — added because account/routing-number cells with
  no surrounding context were being missed or mis-tagged in real test
  docs).
* Launchers: `setup_once.bat` / `START_HERE.bat` (Windows) and
  `setup_once.command` / `START_HERE.command` (macOS). All four search
  for Python 3.10–3.12, reject 3.13+ with a clear "install 3.12" message
  (spaCy 3.7.5 has no cp313 wheels), and refuse to run if the vendored
  model is missing.
* Packaging: `scripts/package.sh` builds a clean zip (excludes `.venv`,
  `.git`, caches, `user_additions.txt`), verifies critical files are
  present, and reports size.
* Docs for end users: `SETUP_GUIDE.md` (two-section, Mac + Windows, with
  full Gatekeeper / Mark-of-the-Web walkthroughs) and `CUSTOMIZING.md`
  (in-app box first, edit-`firm_config.py` second).
* Licensing artifacts for commercial distribution:
  - `LICENSE` — proprietary commercial EULA (as-is, no warranty,
    liability capped at fees paid in prior 12 months, NJ governing law).
    Starter template, **needs lawyer review before first paid sale**.
  - `THIRD_PARTY_LICENSES.md` — required attribution for Presidio,
    spaCy, Streamlit, pdfplumber, python-docx, openpyxl, and the
    vendored `en_core_web_lg` model. Full MIT + Apache 2.0 texts
    included.
  - Copyright header `# Copyright (c) 2026 Vincent Shahinllari. All
    rights reserved.` on every owned `.py` file (21 files).
  - `scripts/package.sh` verifies both license files ship in the zip.
* UI: "Midnight" dark theme. Slate-900 canvas, slate-50 text, amber
  primary CTA (#F59E0B), emerald-tinted offline-status pill in the
  top-right (`● Offline · v1.0` + `Your data stays on this computer`
  subtitle). Faint redaction-bar SVG watermark tiled across the page
  at 6% opacity — inline data URI, no network fetch.
  - Streamlit's built-in toolbar (Deploy button, 3-dot menu, running
    indicator) is **hidden via CSS** — the Deploy button pushes to
    Streamlit Community Cloud and the 3-dot menu links hit
    streamlit.io. Both must stay hidden in any future version. See
    "Boundaries" below.
* Tests: **205 passing, 1 skipped, 0 xfail in ~5s.** Coverage includes
  regex isolation, end-to-end Presidio detection, DOCX/XLSX/PDF
  round-trips, DOCX table column-masking regression, overlap/adjacency
  handling, Unicode + regex metachar safety, network-isolation guarantee
  (socket / urllib patched), preview render, missing-model defensive
  path, user-additions live reload, surname-particle trimming, the
  security-hardening regression set (`tests/test_security_hardening.py`:
  magic-byte signature check + upload-filename basename sanitization),
  and the full breadth-first PII battery (`tests/test_pii_battery.py`)
  covering every recognizer with synthetic data plus adversarial
  cross-recognizer cases.

**What's resolved from the original TODO list:**

* Color/hex: `#C00000`, applied in DOCX runs, XLSX cell fills (pale-yellow
  background `#FFF2CC`), and the HTML preview span.
* `CLIENT_ID` recognizer: removed. The firm has no separate client ID
  beyond tax IDs.
* spaCy model in git: **not tracked.** The 588 MB vectors file exceeds
  GitHub's 100 MB per-file cap. `.gitignore` excludes `en_core_web_lg/`.
  Distribution carries the model inside the zip; dev clones run
  `scripts/vendor_model.py` to fetch + place it.
* Fixtures dir: `tests/fixtures/`. Includes a committed
  `sample_with_pii.pdf` (generated once by `_build_pdf.py`).
* Pytest is wired up — see commands below.

**Local state: clean.** All session work pushed to `main`. Most recent
commits, newest first:

* `755d1ff` — Midnight dark UI + redaction-bar background
* `c0ba7c4` — Streamlit toolbar hidden, button styling fixed
* `0fc28d2` — first UI restyle pass ("Quiet Professional" light theme,
  superseded by `755d1ff`)
* `b64e98a` — DATE_TIME open-question pinned at top of CLAUDE.md
* `59bbd3d` — recognition audit (all originally-flagged gaps closed)
* `22729e5` — licensing files + particle trim
* `702696c` — DOCX table column masking + bulk UI buttons + packaging

**Visually verified by Vincent in browser as of session end** —
screenshot of the Midnight UI looked correct (header, badge, button
styling, redaction-bar background all rendered as designed).

**Cross-cutting finding from this audit (read before adding more
recognizers):**

Presidio's `LemmaContextAwareEnhancer` lemmatizes surrounding-text words
via spaCy before comparing them to the recognizer's context list. The
context list itself is NOT lemmatized — comparison is exact-string. We
had `"routing"` in the list, but spaCy lemmatizes `"Routing"` → `"route"`,
so no match, no boost, the routing recognizer stayed below threshold and
got crowded out by DATE_TIME. **When you write a context word in a
recognizer, put the lemma form**, optionally alongside the bare form.
Verbs: use the base form (`route`, not `routing`; `live`, not `lives`).
Nouns: usually fine as-is. If unsure, do a quick `spacy.load(...)("your
word")[0].lemma_` check.

**Where testing stands:**

* Mac: one round of testing completed against the firm's synthetic
  engagement letter. Surfaced the two issues above (now fixed locally).
  Next test pass needs a fresh zip via `scripts/package.sh`.
* Windows: **never tested on real Windows hardware.** This is the
  remaining test gate before distribution to anyone but the user.

---

## Commands

Dev runs on macOS or Linux. Distribution targets are Windows (primary) and
macOS (secondary, added for one user). See "Packaging".

```bash
# Run the app during dev
.venv/bin/streamlit run app.py

# Full test suite (currently 189 pass / 1 skip / 0 xfail, ~5s)
.venv/bin/python -m pytest -q

# Install / refresh deps (pinned)
.venv/bin/pip install -r requirements.txt

# Vendor the spaCy model into ./en_core_web_lg/ after a fresh git clone
.venv/bin/python scripts/vendor_model.py

# Build a distribution zip
scripts/package.sh
```

* Lint/format: **not wired up.** `ruff`/`black` would be welcome
  additions but neither is currently configured. The codebase follows
  standard PEP-8 informally.
* `START_HERE.bat` + `setup_once.bat` are **Windows-only**. Don't run
  them on Mac/Linux.
* `START_HERE.command` + `setup_once.command` are **macOS-only**.
  Double-clickable from Finder. Same offline / vendored-model guarantees
  as the `.bat` files.

---

## Architecture

Flat single-package layout. Files (top of repo):

* `recognizers.py` — custom Presidio regex recognizers (EIN, routing,
  account, US street addresses + PO Box, firm-names from FIRM_NAMES,
  always-redact from ALWAYS_REDACT).
* `redactor.py` — Presidio analyzer + anonymizer; loads vendored spaCy
  model by path. Adds the first-name policy, literal-match for user
  terms (session + persistent), and the `Finding` dataclass exposed to
  callers.
* `extractors.py` — file → redacted file. `.txt`, `.pdf` (text-only
  output), `.docx` (in-place run rewrite + table column masking),
  `.xlsx` (hybrid column + cell-level redaction). Also the
  `SENSITIVE_HEADER_KEYWORDS` and `FREETEXT_HEADER_KEYWORDS` lists used
  by both DOCX tables and XLSX sheets. `redact_file()` calls
  `_verify_file_signature()` first — a magic-byte check that rejects a
  file whose bytes don't match its extension before any parser runs
  (defense in depth; see `SECURITY_AUDIT.md` M-2).
* `firm_config.py` — IT-curated `FIRM_NAMES` and `ALWAYS_REDACT` lists.
  Pure data. The firm's IT person edits this directly. **No logic here.**
* `user_additions.py` — read/write helpers for `user_additions.txt`.
  Used by the UI's "Save permanently" path; also reloaded by
  `redactor.analyze()` on every call (no caching) so adds take effect
  immediately.
* `preview.py` — HTML rendering for the live preview pane. Extracted
  from `app.py` for testability (Streamlit fires page setup on import).
* `labels.py` — plain-English display names for the internal entity tags
  (`US_SSN` → "Social Security Number", etc.). Review-screen presentation
  ONLY: the redacted file and the live preview still carry the raw `<TYPE>`
  tags so the reviewer sees exactly what lands in the download. Standalone /
  Streamlit-free so it unit-tests like `preview.py`. **Add a mapping here
  whenever you add an entity to `redactor.DEFAULT_ENTITIES`** —
  `tests/test_labels.py` fails if one is missing.
* `app.py` — Streamlit UI. Upload → auto-redact → review → download.
  Includes the `➕` expander, bulk Keep/Redact buttons, a per-file
  redaction-summary card (plain-English count by type), a processing
  spinner, friendly entity labels via `labels.py`, a "lower confidence,
  please double-check" nudge on findings scoring < 0.5, and the inline
  CSS block that paints the Midnight theme + redaction-bar background
  and hides Streamlit's built-in toolbar. File-read failures show an
  actionable message (with a "Technical details (for IT)" expander), not
  a raw stack trace.
* `.streamlit/config.toml` — telemetry off, bound to 127.0.0.1,
  `base = "dark"` + Midnight palette tokens.
* `scripts/` — `vendor_model.py` (dev-only), `package.sh` (build a
  distribution zip).
* `tests/` — pytest. `fixtures/sample_with_pii.pdf` is a committed
  binary; `_build_pdf.py` regenerates it if needed.
* `LICENSE`, `THIRD_PARTY_LICENSES.md` — commercial-distribution
  artifacts. See "Licensing artifacts" in the status block above.
* `RECOGNITION_AUDIT.md` — 2026-05-29 breadth-first audit report of
  every recognizer's status, cross-cutting findings, and ranked next
  steps. Read this when adding or modifying recognizers.
* `SECURITY_AUDIT.md` — 2026-05-31 security audit (dependency CVEs,
  network isolation, code review) with a remediation-status table. Read
  this before bumping dependencies or touching the upload/file-handling
  path.

Build order is preserved from the original spec: engine (1–2) → file
handling (3) → UI (4) → packaging. Modify in that order if making big
changes; the next layer assumes the layer below.

### Excel handling

Hybrid approach, per sheet, looping all sheets:

* Auto-flag sensitive columns by header keyword **or** by sample-scan
  (≥ 40% PII hits AND ≥ 3 absolute hits to avoid over-flagging tiny
  sheets).
* Flagged columns: wholesale mask with the column's tag.
* Free-text columns (Notes, Comments, Description, Memo, Remarks,
  Details): **exempt** from sample-scan-based wholesale masking —
  cell-level scan instead.
* Preserve leading zeros / text-formatted numbers: read cells as their
  stored string form; do not let openpyxl coerce `0123` → `123`. Modified
  cells get number_format `'@'` (text).

### DOCX handling

Per-paragraph scan everywhere PLUS table column-header masking. The
table pass mirrors XLSX: row 1 headers checked against
`SENSITIVE_HEADER_KEYWORDS`, flagged columns get every data cell
wholesale-replaced with a styled bold + red tag. Free-text headers
exempt, same as XLSX.

**Why both passes:** per-paragraph alone misses bare numeric cells —
e.g. an Account # cell containing only `0048291756` has no surrounding
context word, so the recognizer can't fire, and the value either leaks
or gets mis-tagged as `<PHONE_NUMBER>` by Presidio's permissive 10-digit
matcher. The column-header pass catches these reliably.

### First-name policy

Per firm directive: do not redact first names. Implemented in
`redactor._enforce_no_first_names()`, applied after Presidio:

* PERSON span text in `FIRM_NAMES` (case-insensitive) → kept fully.
* Multi-word PERSON span → trim to the last whitespace-separated token.
  "Jane Doe" → "Jane `<PERSON>`".
* Single-word PERSON span not in `FIRM_NAMES` → drop entirely. The
  tradeoff: a bare surname like "Doe" in a sentence is *not* caught
  unless added to `FIRM_NAMES`. This was the firm's explicit choice.

### Review-screen visual style

The app uses a **Midnight** dark palette for UI chrome (see "UI" in
the status block above): slate-900 canvas, slate-50 text, amber CTA,
emerald offline pill. CSS lives inline in `app.py` so nothing is
fetched from a CDN at runtime (offline guarantee).

`#C00000` (deep red) is **reserved exclusively for redacted-content
markers** — it never appears as UI chrome, button color, or accent.
That reservation is what keeps the red a meaningful signal rather
than noise. Applied as **bold + `#C00000`** in:
* The Streamlit live preview (HTML span — pops against the slate-800
  preview-panel background)
* DOCX output (run-level styling)
* XLSX output (bold + red text, pale-yellow `#FFF2CC` fill)
* PDF output is plain text with `<TYPE>` tags only — no styling, per
  the "keep PDF output simple" rule.

### Customization model

Three layers, narrowest to widest scope:

1. **Session-only terms** — `st.session_state["session_terms"]`. Pushed
   to `redactor.set_session_terms()` on every Streamlit rerun. Lost on
   tab close.
2. **Per-installation persistent terms** — `user_additions.txt`. Added
   via the UI's "Save permanently" path or hand-edited. Reloaded by
   `redactor.analyze()` on every call so adds take effect without
   restarting the engine. Tagged `REDACTED`. Gitignored.
3. **Firm-wide curated lists** — `firm_config.FIRM_NAMES` and
   `firm_config.ALWAYS_REDACT`. Edited by IT, distributed via the zip.

All three feed into the same matching engine. The UI surfaces (1) and
(2); (3) is invisible to end users.

---

## Offline guarantee (non-negotiable)

* **No outbound network calls of any kind at runtime.** No telemetry, no
  cloud APIs, no analytics, no update checks, no model downloads.
* The spaCy model `en_core_web_lg/` is **vendored** — loaded by absolute
  path from `redactor.VENDORED_MODEL_PATH`. Never call `spacy.cli.download`
  or `spacy.load("en_core_web_lg")` (registered-name lookup) from runtime
  code.
* Verified by `tests/test_offline_guarantee.py`: monkeypatches
  `socket.socket.connect`, `socket.create_connection`, and
  `urllib.request.urlopen` to raise, then runs `analyze()` and `redact()`.
  If either ever tries the network, the test fails.
* If a task seems to need a network call, stop and flag it.
* Streamlit telemetry is off via `.streamlit/config.toml`. Server binds
  only to `127.0.0.1`.

---

## Boundaries — do NOT touch

* `en_core_web_lg/` — vendored model. Read-only. Never edit, regenerate,
  or re-download from runtime code.
* `*.bat` / `*.command` files — propose changes in chat; do not silently
  rewrite. They're fragile and OS-specific.
* **Streamlit's built-in toolbar must stay hidden.** The CSS block at
  the top of `app.py` hides `stHeader`, `stToolbar`, `stAppDeployButton`,
  `stMainMenu`, and `stStatusWidget`. The Deploy button pushes to
  Streamlit Community Cloud (a paid network operation, out of scope for
  an offline tool); the 3-dot menu's "Get help" / "Report a bug" items
  link to streamlit.io. If a future Streamlit version renames any of
  these `data-testid` attributes, the toolbar will reappear silently —
  grep `static/static/js/main.*.js` in the venv for the new IDs and
  update the selectors. **Pin `streamlit==1.58.0` in `requirements.txt`
  exactly** so this can't break on a `pip install -U`. (Bumped from
  1.39.0 on 2026-05-31 to clear CVE-2026-33682; the five `data-testid`
  selectors above were re-verified present in the 1.58 JS bundle. 1.54+
  also swapped Streamlit's Tornado server for a starlette/uvicorn stack —
  see SECURITY_AUDIT.md.)
* `RUNBOOK.md` — does not exist yet. [TODO: write one if/when distribution
  ramps up.]
* `LICENSE` (proprietary EULA) — needs lawyer review before the first
  paid sale. Don't ship in a paid distribution without that review.
* Never read, create, or commit real client documents or any file
  containing real PII. Test only against synthetic fixtures in
  `tests/fixtures/`.

---

## Code style

Maintainer is a Python-comfortable but inconsistent in-house IT person.
Optimize for someone else picking this up, not for cleverness.

* Simple, readable, low-cleverness Python. No one-liners that need
  decoding.
* **Add comments here** (unlike past projects) — explain *why*, especially
  in the Excel / DOCX-table logic and the recognizer regexes.
* Type hints on function signatures.
* Prefer stdlib and existing deps over adding new ones.
* No formatter currently enforced; informally PEP-8 + black-style.

---

## Packaging

Targets: Windows (primary), macOS (secondary).

The tool ships as a zip built by `scripts/package.sh`. The IT person /
boss downloads it, unzips to a **permanent** location (`C:\pii-redactor\`
on Windows, `~/Documents/pii-redactor/` on Mac, NOT Downloads), runs
`setup_once.{bat,command}` once per machine, then uses
`START_HERE.{bat,command}`.

Known failure modes — design against all of them:

* Must work on a machine that has never had Python installed. Both setup
  scripts check for Python 3.10–3.12 specifically (3.13+ rejected because
  the pinned spaCy/thinc don't have cp313 wheels) and print a clear
  install-link message if missing.
* Must not assume the script is run from Downloads or a temp folder — use
  paths anchored to `${BASH_SOURCE[0]}` / `%~dp0`, not CWD.
* Windows "Mark of the Web" can block downloaded `.bat` files. Covered in
  `SETUP_GUIDE.md`.
* macOS Gatekeeper blocks first-run of `.command` files with a "can't
  verify it doesn't have malware" dialog. The Privacy & Security → Open
  Anyway path is documented in `SETUP_GUIDE.md`, with a Terminal
  `bash setup_once.command` fallback for the case where Gatekeeper keeps
  fighting back.
* Updates re-zip via `scripts/package.sh`; the model stays vendored,
  never fetched.

**Test gate:** before relying on a packaging change for distribution, it
must be validated on the target OS. **Windows has NOT been validated
yet.** macOS has been validated once (round 1 — surfaced the DOCX-table
bug, now fixed locally).

---

## Scope (v1 — resist creep)

In scope: the redaction pipeline, the four file types, the review screen,
offline packaging, the in-app custom-redaction box, the bulk
Keep/Redact-by-type UI, the customization model (3-layer).

**Out of scope for v1** (do not build unless asked): batch processing,
audit logs, reversible tokens, multi-user/server modes, any networked
feature, in-place PDF rewriting (PDFs export as `.txt`).

PERSON-name detection is the known weak link (misses unusual names,
over-flags common words). The human review screen + the `FIRM_NAMES`
deny-list are the safety nets.

---

## Open work (prioritized for next session)

Items 1–4 from the original handoff are **closed in this session.** See
`RECOGNITION_AUDIT.md` for the full report. The remaining items are
re-numbered below.

### Closed in 2026-05-29 audit pass

* ~~**1. Name particles in the first-name trim.**~~ Shipped. See
  `redactor._enforce_no_first_names` and
  `tests/test_redactor.py::TestNameParticles` (8 tests).
* ~~**2. Account vs Routing collision on 9-digit numbers.**~~ Shipped.
  Account regex tightened to `\b(?:\d{6,8}|\d{10,17})\b`. Tests in
  `tests/test_recognizers.py::TestRoutingVsAccountCollision`. **Known
  downstream gap:** a real 9-digit account number with only "account"
  context (no "routing" nearby) now leaks. See item 1 below.
* ~~**3. ZIP code recognizer.**~~ Shipped. `US_ZIP` patterns in
  `recognizers.py` (two-layer: state-prefix high confidence + bare ZIP
  with context). Tagged `LOCATION`. Tests in
  `tests/test_recognizers.py::TestZipRegex` and
  `tests/test_pii_battery.py::TestZipCodes`.
* ~~**4. Phone-number false positives on bare numerics.**~~ Shipped.
  Presidio's default `PhoneRecognizer` is removed from the registry in
  `redactor._build_analyzer`; our `UsFormattedPhoneRecognizer` only
  matches phone-shaped formatting. Tests in
  `tests/test_recognizers.py::TestPhoneRegex` and
  `tests/test_pii_battery.py::TestPhoneNumbers`.

### Newly identified, prioritized

* ~~**9-digit-account leak when only "account" context is present.**~~
  Closed in the same audit pass: `account` / `acct` added to
  `ROUTING_CONTEXT`. The test that was xfail now passes; the value gets
  redacted as `<US_BANK_ROUTING>` (mislabeling-not-leak, per policy).
* ~~**SSNs starting with `000` leak.**~~ Closed: new
  `UsSsnLiteralShapeRecognizer` catches any `\d{3}-\d{2}-\d{4}` shape
  regardless of SSA validity (low score 0.4 so real Presidio US_SSN
  hits still win).
* ~~**Address detection riders (units).**~~ Closed:
  `US_STREET_ADDRESS_PATTERN` now absorbs an optional
  `Apt | Apartment | Suite | Ste | Unit | Rm | Room | Floor | Fl |
  Bldg | Building | #` rider. Rider is anchored AFTER the street suffix
  so `Suite 100 of this report` cannot trigger.

### ~~1. DATE_TIME crowding out routing/account labels~~ — CLOSED 2026-05-31

Resolved via Fix B: `DATE_TIME` dropped from `redactor.DEFAULT_ENTITIES`.
See the "✅ Resolved" section near the top of this file and the CLOSED
DATE_TIME section in `RECOGNITION_AUDIT.md`. Trade accepted by the firm:
prose dates no longer redacted; explicit DOB columns still masked.

### 2. Cross-paragraph context for DOCX (deferred)

**Problem:** A doc reading `"account number:\n0048291756"` across two
paragraphs loses the context word — per-paragraph analysis can't see
the header.

**Fix:** When DOCX paragraphs are short and adjacent, glue them for
analysis. Higher regression risk; only worth doing if the firm's real
docs actually show this pattern. **Do not implement unless we see it in
test docs.**

### 3. Windows VM test pass

**Outstanding from the start.** Build a fresh zip with
`scripts/package.sh`, transfer to a Windows VM, run `setup_once.bat`
end-to-end, then `START_HERE.bat`. Document any failure modes. This is
the gating step before anyone except the user can run on Windows.

---

## Git workflow

* Tracked in git. Remote: `github.com:scarysage/pii_redactor.git`.
* Commits go straight to `main`. No branching/PR flow established.
* Commit message style observed: leading-line summary + body explaining
  the *why*. Co-author trailers included on Claude-authored commits.
* `en_core_web_lg/` is **not tracked** (588 MB vectors file > GitHub's
  100 MB cap). `.gitignore` excludes it.
* `user_additions.txt` is **not tracked** — per-installation file, each
  user has their own.
* Never commit real client docs, real PII fixtures, or anything revealing
  client structure.

---

## Compliance background (context, not a task)

Accounting firm handling real client PII — IRS §7216 and the FTC
Safeguards Rule are relevant background. They reinforce the offline
guarantee; they are not features to build.
