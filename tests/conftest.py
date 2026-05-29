# Copyright (c) 2026 Vincent Shahinllari. All rights reserved.
"""
Test bootstrap.

We run tests from the repo root so the package-style imports (`from redactor
import ...`) work without installing. conftest.py adds the project root to
sys.path so this works whether pytest is invoked from the root or tests/.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
