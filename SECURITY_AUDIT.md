# Security Audit — pii-redactor

**Date:** 2026-05-31
**Auditor:** Claude Code
**Scope:** Full codebase (production source, scripts, config, packaging),
dependency tree, and network-isolation guarantee. Read-only pass — no
production files were modified.
**Threat model:** supply-chain compromise, accidental data exfiltration,
malicious or misconfigured dependencies, and unsafe code patterns. The tool
processes real client PII for an accounting firm and ships to non-technical
users on Windows (primary) and macOS.

---

## Summary

The application's own code is in good shape. It does what it claims: the
redaction engine loads its language model from a local folder, never reaches
out to the network at runtime, properly escapes text before showing it in the
browser, and cleans up the temporary files it creates. We found **no
hardcoded passwords or keys**, **no dangerous code-execution patterns in the
project's own files**, and **no signs that real client data was ever committed
to version history**.

The real risks are in **third-party libraries**, not in the code written for
this project. The most serious is a known flaw in the PDF-reading library
(`pdfminer.six`) that, in its current pinned version, can let a **booby-trapped
PDF run arbitrary code on the machine that opens it.** Because this tool's whole
purpose is to open documents that staff received from elsewhere, that flaw sits
directly in the line of fire and should be fixed before the tool is distributed
more widely. A second known flaw affects Streamlit on Windows (the primary
target platform). Both are fixed simply by updating the pinned versions.

There is also one code-level gap worth tightening: the uploaded file's name is
trusted as-is when writing a temporary copy to disk, which in principle could
let a crafted name write outside the intended temporary folder.

**Bottom line:** safe to keep using internally today, but **update the flagged
dependencies (especially `pdfminer.six`) before the next distribution build**,
and re-run the dependency check after.

---

## Remediation status (2026-05-31, same day)

All findings below were addressed in a follow-up pass. **Every known CVE is now
cleared** (`pip-audit` reports 0 vulnerabilities across 118 packages) and the
full test suite passes (**205 passed, 1 skipped**, up from 194 — new regression
tests in [tests/test_security_hardening.py](tests/test_security_hardening.py)).

| Finding | Severity | Status | What changed |
|---|---|---|---|
| C-1 pdfminer.six RCE | Critical | ✅ Fixed | `pdfplumber` 0.11.4→0.11.9 pulls patched `pdfminer.six` 20251230; pinned explicitly in [requirements.txt](requirements.txt) |
| H-1 Streamlit Windows path traversal | High | ✅ Fixed | `streamlit` 1.39.0→1.58.0 (clears CVE-2026-33682). Toolbar-hiding `data-testid` selectors re-verified present in the 1.58 JS bundle; all `st.*` APIs used by the app confirmed to still exist; config keys validated. **Needs a final ~2-min visual UI check on your hardware before distribution.** |
| H-2 Upload filename traversal | High | ✅ Fixed | [app.py](app.py) reduces the upload name to a bare basename (strips POSIX + Windows separators) before any path join |
| M-1 pillow parsing flaws | Medium | ✅ Fixed | `pillow` 10.4.0→12.2.0 (pinned; was coupled to the Streamlit bump via the old `pillow<11` cap) |
| M-2 Extension-only validation | Medium | ✅ Fixed | Magic-byte signature check in [extractors.py](extractors.py) `_verify_file_signature()`, run before any parser; lenient enough never to reject a genuine document |
| M-3 No upload size cap | Medium | ✅ Fixed | `maxUploadSize = 50` added to [.streamlit/config.toml](.streamlit/config.toml) |
| L-7 pytest temp-dir flaw | Low | ✅ Fixed | `pytest` 8.3.3→9.0.3 (dev-only) |
| L-1 No requirements hashes | Low | ⏸ Deferred | Optional supply-chain hardening for distribution builds; not blocking |
| L-2 firm_config.py trust boundary | Info | ✓ Accepted | By design (IT-curated, shipped in zip) — documented, no change |

**New server stack note (H-1 side effect):** Streamlit 1.54+ replaced its Tornado
server with `starlette`/`uvicorn`/`websockets`/`httptools`/`anyio`/`h11`/
`python-multipart`/`itsdangerous`. These were scanned by `pip-audit` and carry no
known vulnerabilities at the installed versions. The offline guarantee is
unaffected (no outbound calls; server still binds to 127.0.0.1 only).

The original findings are retained below for the record.

---

## Critical findings

> Anything that could leak PII or allow code execution — fix before distribution.

### C-1. `pdfminer.six` 20231228 — arbitrary code execution from a malicious PDF
- **CVE-2025-64512** (and the closely related **CVE-2025-70559**).
- **What it is:** `pdfminer.six` loads internal "CMap" font files using Python's
  `pickle` mechanism, which can execute code while it loads. A specially
  crafted PDF can point the loader at an attacker-controlled `.pickle.gz` file,
  causing **code in that file to run automatically when the PDF is processed.**
- **Why it matters here:** this is not a theoretical corner. `pdfplumber` →
  `pdfminer.six` is exactly the code path [extractors.py:167](extractors.py#L167)
  (`_pdf_to_text`) runs on **every uploaded PDF**, and PDFs are documents the
  firm receives from outside parties. A single malicious PDF run through the
  tool could compromise the accountant's machine — the worst possible outcome
  for software that handles client PII.
- **Fix:** upgrade `pdfminer.six` to **20251230 or later** (the `20231228` pin
  in [requirements.txt](requirements.txt) is the vulnerable version). Pin it
  explicitly so `pdfplumber` cannot resolve a vulnerable version. Re-run
  `pip-audit` after.

---

## High findings

> Significant weaknesses worth fixing soon.

### H-1. Streamlit 1.39.0 — path-handling flaw on Windows
- **CVE-2026-33682.** Streamlit before **1.54.0**, running on **Windows**,
  improperly validates filesystem paths in component request handling
  (server-side path traversal).
- **Why it matters here:** Windows is the **primary distribution target**, and
  the server, while bound to `127.0.0.1`, is still reachable by anything running
  on the same machine. CLAUDE.md also pins `streamlit==1.39.0` *exactly* (to keep
  the toolbar-hiding CSS working), so this will not get picked up by a routine
  upgrade — it needs a deliberate bump.
- **Fix:** upgrade to **streamlit ≥ 1.54.0**. Because the version is pinned for
  UI reasons, re-verify after upgrading that the built-in toolbar is still
  hidden (the `data-testid` selectors in [app.py:129](app.py#L129) may have been
  renamed across versions — CLAUDE.md's "Boundaries" section already documents
  this risk).

### H-2. Uploaded filename is trusted when writing the temp copy (path handling)
- **Where:** [app.py:430-431](app.py#L430).
  ```python
  src_path = Path(tmpdir) / upload.name
  src_path.write_bytes(upload.getbuffer())
  ```
- **What it is:** `upload.name` comes from the uploading browser and is joined
  directly onto the temp directory path with no check that it is a plain
  filename. A name containing `../` (e.g. `../../something.txt`) would resolve
  **outside** the intended temporary folder, so the uploaded bytes could be
  written to an unintended location. The download name (`redacted_name`) is
  derived from the same untrusted value and flows into the download response.
- **Why it's High and not Critical:** exploiting it requires sending a crafted
  request to the local server (XSRF protection is enabled, and the server binds
  to localhost only), and the file-type filter still applies. But it is the one
  place in the project's own code where untrusted input touches a filesystem
  path, so it deserves a real fix.
- **Fix:** reduce the name to its basename and reject anything else before
  using it, e.g. `safe_name = Path(upload.name).name` and validate it contains
  no path separators; build both `src_path` and `dst_path` from `safe_name`.

---

## Medium findings

> Worth addressing in a follow-up pass.

### M-1. `pillow` 10.4.0 — multiple image/PDF parsing flaws
- **CVE-2026-42311** (PSD memory corruption → possible code execution),
  **CVE-2026-25990** (PSD out-of-bounds write), **CVE-2026-40192** (FITS
  decompression bomb → memory-exhaustion denial of service),
  **CVE-2026-42310** (malicious PDF → 100% CPU infinite loop),
  **PYSEC-2026-165** (font integer overflow).
- **Exposure here is partial, not zero.** `pillow` is pulled in by `pdfplumber`,
  `reportlab`, and `streamlit`. The tool's PDF path uses `pdfplumber`'s
  *text* extraction, which does not deliberately open embedded images, and the
  tool never opens PSD/FITS files — so the most severe (PSD code-execution) flaws
  are unlikely to be reachable through normal use. But the PDF-CPU-hang
  (CVE-2026-42310) is in Pillow's own PDF parser and is the kind of thing a
  malformed document could brush against.
- **Fix:** upgrade `pillow` to **≥ 12.2.0**. Add `pillow` as an explicit pin so
  the version is controlled rather than left to transitive resolution.

### M-2. Upload validation is by file extension only (no content/type check)
- **Where:** [app.py:402-410](app.py#L402) (`type=SUPPORTED_TYPES`) and the
  extension dispatch in [extractors.py:109](extractors.py#L109).
- **What it is:** a file is accepted and routed to a parser based purely on its
  `.txt/.pdf/.docx/.xlsx` extension. There is no magic-byte / content-type
  check. A malicious file renamed to `.pdf` is still handed to `pdfminer.six`
  — which is the parser with the Critical flaw above (C-1). Extension-only
  validation is the weakest form and effectively widens the C-1 attack surface.
- **Fix (defense in depth):** after fixing C-1/M-1, optionally verify the file's
  leading magic bytes match the claimed type before parsing. Full hardening is
  reasonably out of scope for v1, but it pairs naturally with the dependency
  upgrades.

### M-3. No upload size cap configured (malformed-document denial of service)
- **Where:** no `maxUploadSize` is set in [.streamlit/config.toml](.streamlit/config.toml),
  so Streamlit's default 200 MB applies.
- **What it is:** a large or malformed `.docx`/`.xlsx`/`.pdf` could make
  `openpyxl` / `python-docx` / `pdfminer` consume excessive memory or CPU. This
  is a stability/availability concern (a hang or crash), not a data-leak one.
  The app already wraps parsing in a try/except with a friendly error
  ([app.py:446](app.py#L446)), which softens but does not prevent a resource
  exhaustion mid-parse.
- **Fix:** set a sensible `maxUploadSize` (e.g. 25–50 MB) in config. Document
  parser-level resource limits as a known v1 limitation.

---

## Low / informational

> Known gaps, accepted risks, and minor notes.

### L-1. `requirements.txt` has no integrity hashes
- The pins are version-locked but use no `--hash=sha256:...` entries, so `pip`
  does not verify that the downloaded artifact matches a known-good hash. This
  is a supply-chain integrity gap: a compromised mirror or a hijacked package
  version could be installed without detection. Not a v1 blocker, but worth
  adding `--require-hashes` for distribution builds.

### L-2. `firm_config.py` is executable Python (trust boundary)
- [recognizers.py:44](recognizers.py#L44) and [redactor.py:32](redactor.py#L32)
  `import firm_config`. That means a tampered `firm_config.py` would run as code.
  This is **by design** — the file is curated by the firm's IT person and shipped
  inside the zip, not user-writable at runtime — but it is worth recording as a
  trust boundary: whoever can edit that file can run code in the app. The
  user-facing equivalent, `user_additions.txt`, does **not** share this risk
  (see L-3).

### L-3. (Positive) User-supplied terms are handled safely
- `user_additions.txt` is read as plain text lines
  ([user_additions.py:31](user_additions.py#L31)) and every term is passed
  through `re.escape()` before being used in a pattern
  ([redactor.py:331](redactor.py#L331),
  [recognizers.py:469](recognizers.py#L469)). It is **never** `exec`/`import`ed.
  This means a user (or a tampered additions file) **cannot inject code or a
  malicious regex** — the most they can do is add literal strings to redact.
  This is the correct design.

### L-4. (Positive) Live preview escapes user text — no HTML/script injection
- [preview.py:27-33](preview.py#L27) HTML-escapes both the document text and the
  entity tags before they are injected via `unsafe_allow_html`
  ([app.py:614](app.py#L614)). A document containing `<script>` renders as inert
  text. No cross-site-scripting exposure in the preview pane.

### L-5. (Positive) Regexes are not vulnerable to catastrophic backtracking
- Every custom recognizer pattern in [recognizers.py](recognizers.py) uses
  bounded quantifiers (`{1,4}`, `{1,6}`) with no nested unbounded repetition.
  Empirical timing on adversarial inputs (100k-digit runs, 5k repeated tokens)
  stayed in the low-millisecond range. **No ReDoS risk.**

### L-6. (Positive) Temp-file hygiene is correct
- Uploads are written into a `tempfile.TemporaryDirectory()`
  ([app.py:429](app.py#L429)) that is automatically deleted when the block
  exits; the redacted bytes are read into memory before cleanup. No unredacted
  content is written to a predictable or persistent location. The only on-disk
  writes are inside the auto-cleaned temp dir; the user's download is the only
  intentional output, and it is the redacted copy.

### L-7. `pytest` 8.3.3 — local temp-dir flaw (dev-only, not shipped)
- **CVE-2025-71176** (predictable `/tmp/pytest-of-<user>` path on UNIX). `pytest`
  is a development/test dependency and is **not invoked at runtime or shipped**
  in the distribution zip, so the practical risk to end users is nil. Bump to
  9.0.3 on dev machines when convenient.

### L-8. Dormant network-capable transitive dependencies
- `requests` (via spacy/streamlit), `azure-core` (pulled in by
  `presidio-anonymizer`), `tldextract`, and `requests-file` are installed but
  are **not called** by any project code. They are latent capability, not active
  exfiltration. The network-isolation test (see below) is what keeps them
  honest. Worth being aware of when reviewing future code changes.

### L-9. Offline test covers the engine but not the file-parser paths
- [tests/test_offline_guarantee.py](tests/test_offline_guarantee.py) blocks the
  network and exercises `analyze()` / `redact()`. The socket patch is
  process-wide, so it *would* catch a network call from the extractors too — but
  the test never actually runs `redact_file()` on a `.pdf/.docx/.xlsx`. Consider
  adding a case that runs each extractor under the same network block, for
  completeness.

---

## Dependency inventory

Direct (declared in [requirements.txt](requirements.txt)):

| Package | Version | Used for | Known CVEs (this version) |
|---|---|---|---|
| presidio-analyzer | 2.2.355 | Core PII detection engine ([redactor.py](redactor.py)) | none found |
| presidio-anonymizer | 2.2.355 | Replaces detected spans with `<TYPE>` tags ([redactor.py](redactor.py)); pulls in `azure-core` | none found |
| spacy | 3.7.5 | NLP / NER model engine for `en_core_web_lg` | none found |
| pdfplumber | 0.11.4 | PDF text extraction ([extractors.py](extractors.py)); pulls in `pdfminer.six` + `pillow` | none found (but see transitive) |
| python-docx | 1.1.2 | Read/write `.docx` ([extractors.py](extractors.py)); uses `lxml` | none found |
| openpyxl | 3.1.5 | Read/write `.xlsx` ([extractors.py](extractors.py)) | none found |
| streamlit | 1.39.0 | Web UI ([app.py](app.py)) | **CVE-2026-33682** (High, Windows) → fix 1.54.0 |
| pytest | 8.3.3 | Dev/test only — not shipped | CVE-2025-71176 (Low, dev-only) → fix 9.0.3 |

Notable transitive (relevant to security):

| Package | Pulled in by | Used for | Known CVEs (this version) |
|---|---|---|---|
| pdfminer.six | pdfplumber | Low-level PDF parsing (runs on every uploaded PDF) | **CVE-2025-64512 (Critical, RCE)**, CVE-2025-70559 → fix 20251230 |
| pillow | pdfplumber, reportlab, streamlit | Image handling | CVE-2026-42311, -25990, -40192, -42310, PYSEC-2026-165 (Medium) → fix 12.2.0 |
| lxml | python-docx | XML parsing for DOCX | none found |
| azure-core | presidio-anonymizer | Cloud SDK — **dormant, not called** | none found |
| requests | spacy, streamlit, others | HTTP — **dormant, not called** | none found |
| reportlab | (test fixture builder) | Builds the sample PDF fixture | none found |

**Typosquatting check:** all eight declared package names match their canonical
PyPI names exactly (`presidio-analyzer`, `presidio-anonymizer`, `spacy`,
`pdfplumber`, `python-docx`, `openpyxl`, `streamlit`, `pytest`). None are within
one edit of a different well-known package; none have suspicious publishers. The
vendored model `en_core_web_lg` is installed from Explosion's official GitHub
release URL (visible in the environment metadata) — the canonical source. **No
typosquatting indicators.**

**Hashes:** none present — see L-1.

---

## Network isolation verification

**Result: confirmed clean in the project's own code.**

- **Static scan** of all production code (excluding `.venv/`, the model folder,
  and tests) for network primitives (`socket`, `urllib`, `requests`, `httpx`,
  `aiohttp`, `smtplib`, `boto3`, `azure`, `openai`, `subprocess`, etc.) returned
  **one hit**: `subprocess` in [scripts/vendor_model.py](scripts/vendor_model.py),
  a **dev-only** one-time model-fetch script that is explicitly never shipped or
  run on end-user machines (and documents this itself). No network primitives in
  any runtime code path.
- **Model loading:** [redactor.py:134](redactor.py#L134) points the spaCy engine
  at the absolute path of the vendored `en_core_web_lg/` folder
  (`str(VENDORED_MODEL_PATH)`), **never** a registered model name — so there is
  no code path that could trigger a download. If the folder is missing the app
  raises a clear error ([redactor.py:124](redactor.py#L124)) rather than
  attempting to fetch it.
- **Streamlit telemetry:** [.streamlit/config.toml](.streamlit/config.toml) sets
  `gatherUsageStats = false`, binds the server to `127.0.0.1` (not `0.0.0.0`),
  runs headless, and keeps XSRF protection on. Fonts use the system stack (no
  Google Fonts fetch); the background watermark is an inline SVG data URI (no
  remote asset).
- **Runtime proof:** [tests/test_offline_guarantee.py](tests/test_offline_guarantee.py)
  monkeypatches `socket.connect`, `socket.create_connection`, and
  `urllib.request.urlopen` to raise, then runs the full analyze/redact pipeline.
  Any phone-home would fail the test. (Coverage gap noted in L-9: the file
  extractors aren't exercised under the block, though the patch would still
  catch them.)
- **spaCy / Presidio:** neither library makes outbound calls on model load or
  inference in this configuration. `presidio-anonymizer` pulls in `azure-core`,
  but only the local `"replace"` operator is used ([redactor.py:373](redactor.py#L373));
  no Azure/cloud operator is configured, so `azure-core` stays dormant (L-8).

---

## Recommended next steps

Ranked by risk:

1. **Fix the PDF code-execution flaw (C-1).** Upgrade `pdfminer.six` to ≥ 20251230
   and pin it explicitly. This is the single most important change — do it before
   the next distribution build. Re-run `pip-audit` to confirm it clears.
2. **Upgrade Streamlit (H-1)** to ≥ 1.54.0 (Windows path-traversal fix), then
   re-verify the built-in toolbar is still hidden and re-test the UI on the
   target OS.
3. **Sanitize the uploaded filename (H-2)** — reduce `upload.name` to a basename
   and reject path separators before joining it to any path.
4. **Upgrade `pillow` to ≥ 12.2.0 (M-1)** and add it as an explicit pin.
5. **Add a magic-byte content check on uploads (M-2)** and a `maxUploadSize` cap
   (M-3) as defense-in-depth around the document parsers.
6. **Adopt hashed requirements (L-1)** for distribution builds (`--require-hashes`),
   and bump dev `pytest` (L-7) when convenient.
7. **Re-run `pip-audit` as a standing pre-release step** so new advisories in the
   (large, mostly transitive) dependency tree are caught before each build.

---

*Audit method: manual source review of all production files; full installed-tree
and `requirements.txt` scans via `pip-audit` 2.10.0 (installed into the project
venv for this audit); static greps for network primitives, dangerous calls, and
secrets; empirical ReDoS timing on every custom regex; git-history review. No
production files were modified; the only file written was this report. No URLs
were fetched beyond the dependency-advisory lookups performed by `pip-audit`.*
