# Copyright (c) 2026 Vincent Shahinllari. All rights reserved.
"""
Tests for user_additions.py (the persistent user-added redaction list).

We monkeypatch USER_ADDITIONS_PATH to a tmp file so the real file in the
repo is never touched.
"""

from __future__ import annotations

from pathlib import Path

import user_additions as ua


def _patch_path(tmp_path: Path, monkeypatch) -> Path:
    p = tmp_path / "user_additions.txt"
    monkeypatch.setattr(ua, "USER_ADDITIONS_PATH", p)
    return p


def test_load_missing_file_returns_empty(tmp_path: Path, monkeypatch):
    _patch_path(tmp_path, monkeypatch)
    assert ua.load_user_additions() == []


def test_add_creates_file(tmp_path: Path, monkeypatch):
    p = _patch_path(tmp_path, monkeypatch)
    assert ua.add_user_addition("ACME-12345") is True
    assert p.exists()
    assert ua.load_user_additions() == ["ACME-12345"]


def test_add_skips_empty(tmp_path: Path, monkeypatch):
    _patch_path(tmp_path, monkeypatch)
    assert ua.add_user_addition("   ") is False
    assert ua.load_user_additions() == []


def test_add_is_case_insensitive_dedupe(tmp_path: Path, monkeypatch):
    _patch_path(tmp_path, monkeypatch)
    ua.add_user_addition("ACME-12345")
    assert ua.add_user_addition("acme-12345") is False  # dupe
    assert ua.load_user_additions() == ["ACME-12345"]


def test_load_skips_blank_and_comment_lines(tmp_path: Path, monkeypatch):
    p = _patch_path(tmp_path, monkeypatch)
    p.write_text(
        "# a comment\n\nReal-Item\n  \n# another comment\nSecond\n",
        encoding="utf-8",
    )
    assert ua.load_user_additions() == ["Real-Item", "Second"]


def test_remove_works_case_insensitive(tmp_path: Path, monkeypatch):
    _patch_path(tmp_path, monkeypatch)
    ua.add_user_addition("ACME-12345")
    ua.add_user_addition("Other")
    assert ua.remove_user_addition("acme-12345") is True
    assert ua.load_user_additions() == ["Other"]


def test_remove_missing_returns_false(tmp_path: Path, monkeypatch):
    _patch_path(tmp_path, monkeypatch)
    ua.add_user_addition("Only")
    assert ua.remove_user_addition("Nope") is False
    assert ua.load_user_additions() == ["Only"]
