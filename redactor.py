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

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig, RecognizerResult

from recognizers import all_custom_recognizers


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
    "CLIENT_ID",
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
    findings.sort(key=lambda f: (f.start, f.end))
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
