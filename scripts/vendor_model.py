# Copyright (c) 2026 Vincent Shahinllari. All rights reserved.
"""
Dev-only: download the spaCy en_core_web_lg model and copy its data into
./en_core_web_lg/ at the repo root so redactor.py can load it by path.

WHY THIS EXISTS:
    The model is 620 MB (588 MB vectors file) -- it cannot live in git
    (GitHub caps files at 100 MB). It ships with the production zip, so
    IT machines never need this script. But a fresh git clone has no
    model, and redactor.py refuses to start without one.

WHEN TO RUN:
    Once, after `git clone`. Idempotent -- re-running is a no-op once the
    model directory exists.

WHEN *NOT* TO RUN:
    Never from production / the distributed zip. This script downloads
    from PyPI; that is a network call. CLAUDE.md forbids any network
    call at *runtime* on the accountant's PC. This is a *dev setup*
    step on a developer machine -- different context.

USAGE:
    .venv/bin/python scripts/vendor_model.py            # mac / linux
    .venv\\Scripts\\python.exe scripts\\vendor_model.py # windows dev only
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET = REPO_ROOT / "en_core_web_lg"
MODEL_NAME = "en_core_web_lg"


def _model_already_vendored() -> bool:
    # The cheapest "is the model usable" check: config.cfg must exist.
    # redactor.py uses the same file as its presence test.
    return (TARGET / "config.cfg").exists()


def _pip_install_model() -> None:
    """Install the model wheel from PyPI into the current Python's site-packages."""
    print(f"Downloading {MODEL_NAME} (this is a one-time dev step) ...")
    subprocess.check_call(
        [sys.executable, "-m", "spacy", "download", MODEL_NAME]
    )


def _find_installed_model_data_dir() -> Path:
    """
    After `spacy download`, the model wheel installs to site-packages/en_core_web_lg/
    and the actual data sits in a versioned subfolder, e.g.
    site-packages/en_core_web_lg/en_core_web_lg-3.7.1/. We want that inner dir.
    """
    import en_core_web_lg  # imported lazily so this script can run before install

    pkg_dir = Path(en_core_web_lg.__file__).resolve().parent
    candidates = sorted(pkg_dir.glob(f"{MODEL_NAME}-*"))
    if not candidates:
        raise SystemExit(
            f"Could not find a {MODEL_NAME}-* data dir under {pkg_dir}. "
            f"Is the model wheel installed?"
        )
    # If multiple versions are installed (unlikely), pick the newest.
    return candidates[-1]


def main() -> int:
    if _model_already_vendored():
        print(f"Model already vendored at {TARGET} -- nothing to do.")
        return 0

    _pip_install_model()
    src = _find_installed_model_data_dir()
    print(f"Copying model data from {src} -> {TARGET} ...")
    shutil.copytree(src, TARGET)

    if not _model_already_vendored():
        raise SystemExit(
            f"Copy completed but {TARGET / 'config.cfg'} is missing. "
            "Something went wrong; check the source dir."
        )

    print("Done. redactor.py will now load the vendored model from disk.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
