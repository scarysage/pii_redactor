# Recognition Audit — 2026-05-29

A breadth-first audit of the PII recognition layer. Synthetic-data battery
in `tests/test_pii_battery.py` exercises every recognizer end-to-end through
the full Presidio + spaCy pipeline (not isolated regexes).

**Result:** 50 pass, 1 skip, 0 xfail. Full suite: **186 passed, 1 skipped,
0 xfailed**, up from a 118-test baseline. No regressions. All three
originally-flagged gaps closed in the same pass.

---

## Recognizers that are now solid

These have positive AND negative cases passing end-to-end and are safe to
rely on:

| Recognizer | Tag | Notes |
|---|---|---|
| `US_SSN` (Presidio default) | `US_SSN` | Catches `412-77-8391`, `SSN: 612-54-7728`, and the undashed form (`412778391`) when context is present. |
| `US_EIN` (custom) | `US_EIN` | Catches `47-1234567`, `EIN: 82-5559912`, `Federal Tax ID: 82-5559912`. Rejects `12-345` and `123-456789`. |
| `US_BANK_ROUTING` (custom) | `US_BANK_ROUTING` | Catches the 9-digit shape with routing context. **Fix landed:** context list now uses lemmatized forms (`route` in addition to `routing`) so spaCy's lemma-based context enhancer actually boosts the score. Without this fix the recognizer was silently below threshold. |
| `US_BANK_ACCOUNT` (custom) | `US_BANK_ACCOUNT` | 6–8 or 10–17 digits with account context. **9-digit is now excluded by design** — owned by routing to resolve the collision flagged in CLAUDE.md Open Work #2. |
| `LOCATION` — street addresses (custom) | `LOCATION` | `123 Main Street`, `100 West 42nd Street`, `200 N. Lake Shore Drive` all match. Rejects `5 Year Plan`, `100 Days of Code`, `1500 mg dose`. |
| `LOCATION` — PO Box (custom) | `LOCATION` | `PO Box 4892`, `P.O. Box 5512`, `P O Box 89` all match. |
| `LOCATION` — ZIP (new) | `LOCATION` | New recognizer added per Open Work #3. `Newark NJ 07102` and `07102-1234` after state prefix score high (0.7). Bare 5-digit with no state/context (`12345 employees`) stays below threshold. |
| `PHONE_NUMBER` (custom, replaces Presidio default) | `PHONE_NUMBER` | **Replaced** the predefined `PhoneRecognizer` per Open Work #4. Now requires phone-shaped formatting: parens, dashes, dots, or spaces. `(415) 555-0123`, `415-555-0123`, `415.555.0123`, `415-555-0123 x42`, `+1 415-555-0123` all match. **Bare `4155550123` no longer mistags** as phone. |
| `PERSON` — particle trim (custom post-processing) | `PERSON` | `_enforce_no_first_names()` now walks past Dutch/German/Spanish/Italian/Irish particles. `Lars van der Berg` → trims to `van der Berg`, leaves `Lars`. Open Work #1 closed. |
| `PERSON` — firm-name deny list (custom) | `PERSON` | `Strassler`, `Herbstman` (per `firm_config.FIRM_NAMES`) caught case-insensitively, whole-word. |
| `REDACTED` — ALWAYS_REDACT (custom) | `REDACTED` | Pipeline cleanly skips when the list is empty. Populated entries get tagged whole-word, case-insensitively. |

---

## Originally-flagged gaps — all closed

### 1. ~~`000-XX-XXXX` SSNs leak~~ — CLOSED

**Status:** Closed. Added `UsSsnLiteralShapeRecognizer` — a low-score
(0.4) recognizer matching the literal `\d{3}-\d{2}-\d{4}` shape and
tagged as `US_SSN`. Catches SSA-invalid patterns the predefined
`UsSsnRecognizer` rejects. Test
`TestSSN::test_irs_invalid_pattern_still_redacted` flipped from xfail
to passing.

### 2. ~~9-digit account leak with only "account" context~~ — CLOSED

**Status:** Closed. `account` and `acct` added to `ROUTING_CONTEXT` so
a 9-digit value near "account" wording boosts the routing recognizer
above threshold. Trade-off accepted: a real 9-digit account will
mislabel as `<US_BANK_ROUTING>`, which is the correct trade per the
firm's risk ranking (missed PII > mislabeling). Test
`TestBankAccount::test_9_digit_NOT_tagged_as_account` flipped from
xfail to passing.

### 3. ~~`Apt 3B` / `Suite 200` trailing riders not captured~~ — CLOSED

**Status:** Closed. `US_STREET_ADDRESS_PATTERN` extended with an
optional unit rider covering `Apt | Apartment | Suite | Ste | Unit |
Rm | Room | Floor | Fl | Bldg | Building | #` followed by a token.
The rider only fires AFTER a street-suffix has already matched, so
free prose like `Suite 100 of this report` cannot trigger it (test:
`TestAddresses::test_address_negative_suite_in_prose` confirms). Two
new positive cases added (`test_address_with_suite_comma_separated`,
`test_address_with_pound_unit`).

---

## Cross-cutting issues found and fixed

### Context lemmatization mismatch (silent bug, biggest find of the audit)

Presidio's `LemmaContextAwareEnhancer` lemmatizes surrounding-text words via
spaCy before comparing to the recognizer's context list. The context list
itself is NOT lemmatized — comparison is exact-string. We had `"routing"`
in the list, but spaCy lemmatizes `"Routing"` → `"route"`, so no match,
no score boost, recognizer stayed below threshold.

**Impact before fix:** `US_BANK_ROUTING` was effectively dead in any text
where the trigger word was `Routing` (the most common phrasing). The value
got tagged as `DATE_TIME` instead (spaCy NER sees long numeric runs as
date-shaped) and redacted with the wrong label. No data leaked, but the
review screen showed the wrong tag.

**Fix:** added lemma forms alongside the bare forms in `ROUTING_CONTEXT`,
`BANK_ACCT_CONTEXT`, `ADDRESS_CONTEXT`, `ZIP_CONTEXT`, and `PHONE_CONTEXT`.

**Test that caught it:** `TestBankRouting::test_routing_with_context`.

### DATE_TIME vs numeric recognizer collisions — CLOSED (2026-05-31, Fix B)

spaCy NER tags long digit runs as `DATE_TIME` with a high score (0.85).
When our routing/account recognizer fired on the same span at a lower
boosted score (~0.65), `DATE_TIME` won the overlap during anonymization
and the output showed `<DATE_TIME>` instead of `<US_BANK_ROUTING>`.

**Impact (was):** the value IS redacted; the label is wrong. Review screen
UX degraded for routing numbers, with a restore-on-Keep risk.

**Resolution — Fix B (firm decision 2026-05-31):** `DATE_TIME` was removed
from `redactor.DEFAULT_ENTITIES`. spaCy's free-text date detector no longer
runs, so it can no longer out-score or mislabel our numeric recognizers.
Routing/account numbers now carry their correct labels.

**Trade-off accepted by the firm:** real prose dates (`January 5, 2024`,
`04/15/2024`, `Q3 2023`) are no longer redacted. A spreadsheet/table column
explicitly headed *DOB* / *Date of Birth* is still masked wholesale — that
path lives in `extractors.py` and is independent of `DEFAULT_ENTITIES`.

**Why not Fix A (raise routing base score to 0.55):** would have flagged
any bare 9-digit number anywhere as routing, adding spreadsheet false
positives. The firm chose to stop treating dates as PII instead.

**Regression coverage:** `tests/test_redactor.py::TestDateTimePolicy`
(prose date survives, numeric date survives, routing keeps its own label);
`tests/test_pii_battery.py::test_ein_in_sentence_with_year` updated to
assert `2018` survives.

---

## Recommended next steps, ranked by risk to the firm

| # | Item | Risk class | Effort | Notes |
|---|---|---|---|---|
| 1 | **Add a Windows VM test pass** (Open Work #5 in CLAUDE.md) | Distribution blocker | 1 day | Independent of this audit. Still the gating step before non-Mac distribution. |
| 2 | ~~**Decide on routing-vs-DATE_TIME mislabeling**~~ — DONE 2026-05-31. Firm chose Fix B: `DATE_TIME` dropped from `DEFAULT_ENTITIES`. See the CLOSED section above. | Mislabeling | — | Closed. |
| 3 | **Add address-recognizer ZIP riders** — fold `, NJ 07102` into the same span as the street | Mislabeling (currently two findings instead of one) | Half a day | Cosmetic improvement to the review screen. |
| 4 | **Investigate cross-paragraph context for DOCX** (CLAUDE.md Open Work #4) | Missed PII | 1 day, risky | Do only if a real firm test doc shows the pattern. |

---

## Test inventory

* `tests/test_recognizers.py`: 42 tests. Pattern-level isolation; fast.
* `tests/test_redactor.py`: end-to-end with full pipeline; includes
  particle-trim tests (Open Work #1).
* `tests/test_pii_battery.py`: **new in this audit.** 50 pass / 1 skip /
  0 xfail. Breadth-first synthetic-data coverage with adversarial cases.
* All other test files: unchanged, all passing.

**Total:** 186 passed, 1 skipped, 0 xfailed.

---

## How to re-run

```bash
# The PII battery alone
.venv/bin/python -m pytest tests/test_pii_battery.py -v

# Full suite
.venv/bin/python -m pytest -q
```

There are no `xfail` items currently. If a future change introduces one,
xfail items resolve to **XPASS** when accidentally fixed — that's a signal
to remove the `xfail` decorator and let the test pin the new behavior.
