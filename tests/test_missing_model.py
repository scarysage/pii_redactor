"""
Defensive: if the vendored spaCy model is missing, the engine must refuse to
start with a clear error -- NOT silently attempt to download it.

CLAUDE.md is explicit: no network calls at runtime, ever. This test
guarantees the fail-loud behavior survives future refactors.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import redactor


def test_missing_vendored_model_raises_clearly(monkeypatch, tmp_path: Path):
    # Point VENDORED_MODEL_PATH at a directory that does NOT exist.
    fake = tmp_path / "no_model_here"
    monkeypatch.setattr(redactor, "VENDORED_MODEL_PATH", fake)
    # And clear the cached analyzer so the next call triggers _build_nlp_engine.
    monkeypatch.setattr(redactor, "_analyzer", None)

    with pytest.raises(RuntimeError) as exc:
        redactor.get_analyzer()

    msg = str(exc.value)
    # The message should be informative -- mention the missing path AND the
    # offline-only rule, so a maintainer knows not to "fix" it with a download.
    assert "model" in msg.lower()
    assert "offline" in msg.lower() or "vendored" in msg.lower()
