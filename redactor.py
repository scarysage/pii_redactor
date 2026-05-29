# Copyright (c) 2026 Vincent Shahinllari. All rights reserved.
"""
Redaction engine: wraps Presidio analyzer + anonymizer.

Public API:
    analyze(text)            -> list[Finding]
    redact(text)             -> (redacted_text, list[Finding])
    apply_decisions(text, findings, keep_set) -> redacted_text

`Finding` is our own small dataclass so the UI/extractors do not need to import
Presidio's types directly. Each finding carries the original span, the entity
tag, and a confidence score so the review screen can sort / filter.

Loading the spaCy model:
    We point Presidio's NlpEngine at the *vendored* en_core_web_lg/ directory.
    Never call spacy.cli.download from runtime code -- that would be a network
    call, and CLAUDE.md is explicit: no outbound network calls, ever.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig, RecognizerResult

from firm_config import FIRM_NAMES
from recognizers import all_custom_recognizers
from user_additions import load_user_additions


# Path to the vendored spaCy model. Resolved relative to THIS file so the app
# works regardless of CWD (matters on Windows where users may launch the .bat
# from anywhere).
VENDORED_MODEL_PATH = (Path(__file__).parent / "en_core_web_lg").resolve()

# Entities we care about. Order is informational only -- Presidio scores each
# match independently. Keeping this list explicit (rather than "all entities")
# means we will not silently start redacting new entity types when we upgrade
# Presidio.
DEFAULT_ENTITIES = [
    # Presidio built-ins
    "US_SSN",
    "US_ITIN",
    "CREDIT_CARD",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "PERSON",
    "LOCATION",
    "DATE_TIME",
    "IBAN_CODE",
    "US_PASSPORT",
    "US_DRIVER_LICENSE",
    # Our custom recognizers (see recognizers.py)
    "US_EIN",
    "US_BANK_ROUTING",
    "US_BANK_ACCOUNT",
    "REDACTED",  # used by the firm's ALWAYS_REDACT list in firm_config.py
]

# Anything below this score is dropped before the user ever sees it. Presidio's
# default is 0 (no filter). 0.35 is empirical -- low enough to catch our custom
# recognizers that lean on context boosts, high enough to drop pure noise.
SCORE_THRESHOLD = 0.35


@dataclass(frozen=True)
class Finding:
    """One detected PII span. Frozen so it can live in sets/dicts safely."""

    start: int
    end: int
    entity_type: str
    score: float
    text: str  # original text that was matched (snapshot at detection time)


# Module-level singleton. AnalyzerEngine is expensive to construct (loads
# spaCy). Streamlit reruns the script on every interaction, so we cache it.
_analyzer: AnalyzerEngine | None = None
_anonymizer: AnonymizerEngine | None = None

# Session-only terms. The Streamlit UI calls set_session_terms() each rerun
# with whatever the user typed into the "Add for this session" box. These are
# matched as literal strings (case-insensitive, whole-word) on top of
# whatever Presidio finds, and tagged `<REDACTED>`.
#
# Persistent terms live in user_additions.txt and are reloaded from disk on
# every analyze() call -- no caching, so adds via the UI take effect
# immediately without restarting the engine.
_session_terms: list[str] = []


def set_session_terms(terms: Iterable[str]) -> None:
    """UI hook: replace the in-memory session-only term list.

    Streamlit reruns the script on every interaction; the UI should call this
    once per rerun with the current session-state list of terms.
    """
    global _session_terms
    _session_terms = [t for t in terms if t and t.strip()]


def _build_nlp_engine():
    """
    Build the spaCy-backed NLP engine, pointing at the vendored model directory.

    The string we pass as model_name is the *path* to the model folder. spaCy
    accepts a path here as well as a registered model name.
    """
    if not VENDORED_MODEL_PATH.exists():
        raise RuntimeError(
            f"Vendored spaCy model not found at {VENDORED_MODEL_PATH}. "
            "This tool is offline-only -- the model must be present on disk. "
            "Do NOT add a download step."
        )

    config = {
        "nlp_engine_name": "spacy",
        "models": [
            {"lang_code": "en", "model_name": str(VENDORED_MODEL_PATH)},
        ],
    }
    return NlpEngineProvider(nlp_configuration=config).create_engine()


def _build_analyzer() -> AnalyzerEngine:
    nlp_engine = _build_nlp_engine()

    registry = RecognizerRegistry()
    # Load the predefined English recognizers (SSN, credit card, email, etc.).
    registry.load_predefined_recognizers(languages=["en"])

    # Drop Presidio's default PhoneRecognizer -- it flags bare 10-digit
    # strings (e.g. an account number "4155550123") as PHONE_NUMBER, which
    # mislabels them in the review screen. Our custom phone recognizer
    # (added below) only matches phone-shaped formatted numbers.
    registry.remove_recognizer("PhoneRecognizer")

    # Layer our custom regex recognizers on top.
    for rec in all_custom_recognizers():
        registry.add_recognizer(rec)

    return AnalyzerEngine(
        nlp_engine=nlp_engine,
        registry=registry,
        supported_languages=["en"],
    )


def get_analyzer() -> AnalyzerEngine:
    global _analyzer
    if _analyzer is None:
        _analyzer = _build_analyzer()
    return _analyzer


def get_anonymizer() -> AnonymizerEngine:
    global _anonymizer
    if _anonymizer is None:
        _anonymizer = AnonymizerEngine()
    return _anonymizer


def analyze(text: str, entities: Iterable[str] | None = None) -> list[Finding]:
    """
    Run Presidio over `text` and return Findings above SCORE_THRESHOLD.

    On top of Presidio, we:
      1. Apply the firm's "no first names" policy -- multi-word PERSON spans
         get shrunk to their last word; single-word PERSON spans that are NOT
         in FIRM_NAMES get dropped. See _enforce_no_first_names() for the
         full rules.
      2. Add literal-match findings for any user-supplied terms (session
         and persistent). Tagged `REDACTED`.

    Findings are sorted by start offset. Overlapping findings can occur (e.g.
    a phone number that also looks like an account number) -- we leave them
    in so the user can decide; apply_decisions() resolves overlaps.
    """
    if not text or not text.strip():
        return []

    analyzer = get_analyzer()
    raw = analyzer.analyze(
        text=text,
        language="en",
        entities=list(entities) if entities else DEFAULT_ENTITIES,
        score_threshold=SCORE_THRESHOLD,
    )

    findings = [
        Finding(
            start=r.start,
            end=r.end,
            entity_type=r.entity_type,
            score=r.score,
            text=text[r.start:r.end],
        )
        for r in raw
    ]

    findings = _enforce_no_first_names(findings)
    findings.extend(_match_user_terms(text, _all_extra_terms()))
    findings.sort(key=lambda f: (f.start, f.end))
    return findings


# ---------------------------------------------------------------------------
# First-name policy
# ---------------------------------------------------------------------------

_TOKEN_SPAN_RE = re.compile(r"\S+")

# Common multi-part surname particles (Dutch/German/Spanish/Italian/Irish/etc.).
# When a PERSON span ends in "<particle(s)> <surname>" we want the redacted
# region to cover the particles too, so "Lars van der Berg" trims to
# "Lars <PERSON>" rather than "Lars van der <PERSON>". Comparison is
# lowercased and trailing periods (e.g. "St.") are stripped.
_NAME_PARTICLES = {
    "van", "von", "der", "den", "de", "del", "di", "da",
    "la", "le", "el", "al",
    "bin", "ben", "ibn",
    "mac", "mc", "o'", "fitz",
    "st", "saint",
}


def _enforce_no_first_names(findings: list[Finding]) -> list[Finding]:
    """Apply the firm's "do not redact first names" rule.

    Policy:
        * Finding text that matches a name in FIRM_NAMES (case-insensitive)
          -> keep the full span. These are curated surnames the firm wants
          redacted every time, even on their own.
        * Other PERSON spans with multiple whitespace-separated tokens
          -> shrink the span to cover the last token plus any preceding
          surname particles ("van", "der", "de", "St.", ...). Output goes
          from "Jane Doe" to "Jane <PERSON>", and from "Lars van der Berg"
          to "Lars <PERSON>".
        * Other PERSON spans that are a single token -> drop. We can't tell
          first from last without context, and the firm directive is to err
          on the side of leaving first names alone.
        * If trimming would consume every token in the span (e.g. "Van
          Halen" where "Van" is itself a particle), drop the whole finding
          rather than redact what might be a first name.
        * Non-PERSON findings -> unchanged.
    """
    firm_lower = {n.lower() for n in FIRM_NAMES}
    out: list[Finding] = []
    for f in findings:
        if f.entity_type != "PERSON":
            out.append(f)
            continue

        if f.text.lower() in firm_lower:
            out.append(f)
            continue

        tokens = list(_TOKEN_SPAN_RE.finditer(f.text))
        if not tokens:
            # Defensive: empty or whitespace-only -- drop.
            continue

        # Single-token span -- drop, per policy.
        if len(tokens) == 1:
            continue

        # Start with the last token, then walk backwards as long as the
        # immediately preceding token looks like a surname particle.
        start_idx = len(tokens) - 1
        while start_idx > 0:
            prev = tokens[start_idx - 1].group(0).rstrip(".").lower()
            if prev in _NAME_PARTICLES:
                start_idx -= 1
            else:
                break

        # If we walked all the way back to the first token, there's no
        # first name to preserve -- drop, matching the single-token policy.
        if start_idx == 0:
            continue

        new_text_start = tokens[start_idx].start()
        new_start = f.start + new_text_start
        out.append(Finding(
            start=new_start,
            end=f.end,
            entity_type=f.entity_type,
            score=f.score,
            text=f.text[new_text_start:],
        ))
    return out


# ---------------------------------------------------------------------------
# User-added literal terms (session + persistent)
# ---------------------------------------------------------------------------

def _all_extra_terms() -> list[str]:
    """Session terms (set by UI) + persistent terms (from user_additions.txt)."""
    return list(_session_terms) + load_user_additions()


def _match_user_terms(text: str, terms: list[str]) -> list[Finding]:
    """Whole-word, case-insensitive literal match for each term in `terms`.

    We use (?<!\\w)...(?!\\w) rather than \\b at the boundaries so that
    terms which start or end with non-word characters (e.g. "A.C-12$" or
    "$300") still match correctly. \\b requires a word/non-word transition,
    which fails when the term itself ends in punctuation surrounded by more
    non-word characters.
    """
    if not terms:
        return []
    pattern = (
        r"(?<!\w)(?:"
        + "|".join(re.escape(t) for t in terms)
        + r")(?!\w)"
    )
    findings: list[Finding] = []
    for m in re.finditer(pattern, text, flags=re.IGNORECASE):
        findings.append(Finding(
            start=m.start(),
            end=m.end(),
            entity_type="REDACTED",
            score=1.0,
            text=m.group(0),
        ))
    return findings


def _findings_to_results(findings: Iterable[Finding]) -> list[RecognizerResult]:
    """Convert our Findings back into Presidio's RecognizerResult."""
    return [
        RecognizerResult(
            entity_type=f.entity_type,
            start=f.start,
            end=f.end,
            score=f.score,
        )
        for f in findings
    ]


def _operators(findings: Iterable[Finding]) -> dict[str, OperatorConfig]:
    """
    Build per-entity-type operators that replace matches with `<TYPE>` tags.

    Presidio's anonymizer takes a mapping of entity_type -> OperatorConfig.
    A "replace" operator with new_value="<US_SSN>" gives us the tag style the
    spec asks for.
    """
    seen: set[str] = set()
    ops: dict[str, OperatorConfig] = {}
    for f in findings:
        if f.entity_type in seen:
            continue
        seen.add(f.entity_type)
        ops[f.entity_type] = OperatorConfig(
            "replace", {"new_value": f"<{f.entity_type}>"}
        )
    # Default for anything we didn't enumerate (shouldn't happen, but safe).
    ops.setdefault("DEFAULT", OperatorConfig("replace", {"new_value": "<REDACTED>"}))
    return ops


def redact(text: str) -> tuple[str, list[Finding]]:
    """
    One-shot: analyze and anonymize.

    Returns (redacted_text, findings). Use this for the auto-redact pass on
    upload. For the human-review pass, call analyze() to get findings, let the
    user toggle which to keep, then call apply_decisions().
    """
    findings = analyze(text)
    if not findings:
        return text, []

    anonymizer = get_anonymizer()
    result = anonymizer.anonymize(
        text=text,
        analyzer_results=_findings_to_results(findings),
        operators=_operators(findings),
    )
    return result.text, findings


def apply_decisions(
    text: str,
    findings: Iterable[Finding],
    keep_indices: Iterable[int],
) -> str:
    """
    Re-render `text` redacting only the findings whose index in `findings` is
    NOT in keep_indices. Used by the review screen: the user un-checks any
    finding they want to keep as-is (false positive), and this rebuilds the
    output.

    Why we rebuild manually instead of calling Presidio's anonymizer here:
    we already have the spans, and overlapping/adjacent spans need careful
    handling. Doing it by hand (right-to-left, skipping kept items) is simpler
    and avoids surprises from the anonymizer's overlap resolution.
    """
    keep = set(keep_indices)
    # Sort right-to-left so earlier offsets are not invalidated as we splice.
    indexed = sorted(enumerate(findings), key=lambda kv: kv[1].start, reverse=True)

    out = text
    last_end = len(text) + 1  # tracks the leftmost edge of already-processed span
    for idx, f in indexed:
        if idx in keep:
            continue
        # Skip if this finding overlaps one we already redacted on this pass.
        if f.end > last_end:
            continue
        tag = f"<{f.entity_type}>"
        out = out[: f.start] + tag + out[f.end:]
        last_end = f.start
    return out
