# CLAUDE.md — pii-redactor

Fully local, offline desktop tool that strips PII (SSNs, EINs, bank/routing
numbers, names, addresses) from documents before they go into any external
AI tool. Built for a small accounting firm. Detected PII is replaced with
type tags (e.g. `<US_SSN>`). Auto-redacts on upload, then shows a human
review screen before download.

**The one rule that overrides everything: nothing leaves the local machine.
No network calls at runtime, ever.** See "Offline guarantee" below.

---

## Status & handoff (last session: 2026-05-29)

The tool is functional end-to-end on Mac and ready for further round-trip
testing against the firm's synthetic engagement-letter / 1099 / roster docs.

**What's been built and verified locally:**

* All four file formats round-trip (`.txt`, `.pdf`, `.docx`, `.xlsx`).
* Engine: Presidio + vendored spaCy `en_core_web_lg` (loaded by path).
* Custom recognizers in `recognizers.py`:
  - `US_EIN` (dashed `NN-NNNNNNN`)
  - `US_BANK_ROUTING` (9-digit, context-boosted)
  - `US_BANK_ACCOUNT` (6–17 digit, context-boosted)
  - US street addresses + PO Boxes, tagged `LOCATION`
  - `FIRM_NAMES` deny-list (currently `Strassler`, `Herbstman`), tagged `PERSON`
  - `ALWAYS_REDACT` literal-match list, tagged `REDACTED`
* First-name policy enforced post-Presidio: full-name spans trim to the
  last token, single-word non-firm PERSON spans drop. (See
  `redactor._enforce_no_first_names`.)
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
* Tests: **110 passing in ~4s.** Coverage includes regex isolation,
  end-to-end Presidio detection, DOCX/XLSX/PDF round-trips, DOCX table
  column-masking regression, overlap/adjacency handling, Unicode + regex
  metachar safety, network-isolation guarantee (socket / urllib patched),
  preview render, missing-model defensive path, and user-additions live
  reload.

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

**Local uncommitted state (NEEDS COMMIT + PUSH if next session is
continuing the work):**

* DOCX table column masking (`_redact_docx_table` in `extractors.py`).
* Bulk Keep/Redact-by-type UI buttons in `app.py`.
* Corresponding tests in `tests/test_extractors_deep.py`.

The most recent pushed commit is `f846710` (deep-test pass). Anything
beyond that on disk has not been pushed yet — including this CLAUDE.md
update. **First action of next session: review the diff, commit, push.**

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

# Full test suite (currently 110 tests, ~4s)
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
  by both DOCX tables and XLSX sheets.
* `firm_config.py` — IT-curated `FIRM_NAMES` and `ALWAYS_REDACT` lists.
  Pure data. The firm's IT person edits this directly. **No logic here.**
* `user_additions.py` — read/write helpers for `user_additions.txt`.
  Used by the UI's "Save permanently" path; also reloaded by
  `redactor.analyze()` on every call (no caching) so adds take effect
  immediately.
* `preview.py` — HTML rendering for the live preview pane. Extracted
  from `app.py` for testability (Streamlit fires page setup on import).
* `app.py` — Streamlit UI. Upload → auto-redact → review → download.
  Includes the `➕` expander and bulk Keep/Redact buttons.
* `.streamlit/config.toml` — telemetry off, bound to 127.0.0.1.
* `scripts/` — `vendor_model.py` (dev-only), `package.sh` (build a
  distribution zip).
* `tests/` — pytest. `fixtures/sample_with_pii.pdf` is a committed
  binary; `_build_pdf.py` regenerates it if needed.

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

ONE consistent style for redacted items: **bold + `#C00000`** (deep
red). Applied in:
* The Streamlit live preview (HTML span)
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
* `RUNBOOK.md` — does not exist yet. [TODO: write one if/when distribution
  ramps up.]
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

Items 1–3 are quick wins directly tied to issues spotted in the first Mac
test pass. 4–6 are improvements to consider after 1–3.

### 1. Name particles in the first-name trim

**Problem:** Multi-word names with Dutch/German/Spanish particles get
trimmed too aggressively. "Lars van der Berg" → output is "Lars van der
`<PERSON>`" instead of "Lars `<PERSON>`". Same for "Mary del Rio", "Hans
von Trapp", etc.

**Fix:** In `_enforce_no_first_names()`, when trimming to the last
token, walk backwards past any common particle tokens and include them
in the trimmed span. Particle list to consider: `van, von, der, den,
de, del, di, da, la, le, el, al, bin, ben, ibn, mac, mc, o', fitz, st,
saint`. Lowercase comparison, strip trailing periods.

### 2. Account vs Routing collision on 9-digit numbers

**Problem:** Routing numbers are 9 digits. Our account-number regex is
6–17 digits — also matches 9-digit. When both fire, the wrong tag often
wins, leading to `<US_BANK_ACCOUNT>` on what should be
`<US_BANK_ROUTING>` (or vice versa). Observed in the test doc.

**Fix:** Tighten the account regex to skip 9 specifically:
`\b(\d{6,8}|\d{10,17})\b`. Routing then owns the 9-digit shape
unambiguously. Behavioral change is invisible to the user except that
tags become accurate. Add a regression test.

### 3. ZIP code recognizer

**Problem:** `Newark NJ 07102` — spaCy catches `Newark NJ` as LOCATION,
the ZIP `07102` slips through.

**Fix:** Add `US_ZIP` recognizer in `recognizers.py`:
* Pattern: `\b\d{5}(?:-\d{4})?\b`, score ~0.3, context words: `zip,
  postal, postcode`. Also boost when preceded by a 2-letter all-caps
  state abbreviation.
* Tag as `LOCATION` (consistent with addresses) OR a new `US_ZIP` tag
  if the firm prefers per-type accounting. Default to `LOCATION` for
  output consistency.
* Add `tests/test_recognizers.py` cases including the
  `07102` → captured, plus a `12345 employees` negative-case test.

### 4. Phone-number false positives on bare numerics

**Problem:** Presidio's predefined `UsPhoneRecognizer` is permissive
enough that a bare 10-digit account number can be tagged
`<PHONE_NUMBER>`. The data is redacted but mislabeled.

**Fix:** Either (a) raise the score threshold specifically for
PHONE_NUMBER by overriding the predefined recognizer with one that
requires phone-shaped formatting (parens, dashes, dots), or (b) drop
the very-weak PHONE_NUMBER patterns from the predefined recognizer.
Option (a) is safer. Validate against the engagement-letter test doc.

### 5. Cross-paragraph context for DOCX

**Problem:** A doc reading `"account number:\n0048291756"` across two
paragraphs loses the context word — per-paragraph analysis can't see
the header.

**Fix:** When DOCX paragraphs are short and adjacent, glue them for
analysis. Higher regression risk; only worth doing if the firm's real
docs actually show this pattern. **Do not implement unless we see it in
test docs.**

### 6. Address detection riders (units, ZIP, state)

**Problem:** My address pattern catches `123 Main Street` but not the
trailing `Apt 4B` or `, NJ 07102` part. spaCy catches city/state
separately.

**Fix:** Extend `US_STREET_ADDRESS_PATTERN` (or add a second pattern)
to optionally consume `(?:,?\s+(?:Apt|Apartment|Suite|Ste|Unit|#)\s*\S+)`
and a trailing `,?\s+[A-Z]{2}\s+\d{5}` rider. Watch for false positives
on `Suite 100 of` patterns. If (3) lands first, the ZIP recognizer
already handles the trailing ZIP, so this becomes smaller in scope.

### 7. Windows VM test pass

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
