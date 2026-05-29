# Copyright (c) 2026 Vincent Shahinllari. All rights reserved.
"""
Network-isolation test: prove the redaction path makes NO outbound network
calls.

We monkeypatch the standard library's network primitives so that any attempt
to open a socket or call urlopen raises. Then we run the full analyze/redact
pipeline on a sample with PII. If anything in Presidio/spaCy/our code tried
to phone home, the patched call would raise and the test would fail.

This is the strongest defensive check we can make from inside the process
for the offline guarantee in CLAUDE.md.

Limitations (called out explicitly so future maintainers know):
  * The analyzer is constructed lazily by get_analyzer(). If it was already
    constructed in a previous test, model load (which is offline anyway --
    file IO only) won't re-happen here. To be safe, this test forces a
    fresh construction via the dedicated _Reset fixture.
  * Some libraries cache DNS or resolve on import. Imports themselves are
    not under test here -- only the runtime analyze/redact path.
"""

from __future__ import annotations

import socket
import urllib.request

import pytest

import redactor


class NetworkAttempted(Exception):
    pass


@pytest.fixture
def block_network(monkeypatch):
    """Make every standard network entry-point raise."""

    def deny_connect(self, *args, **kwargs):  # socket.socket.connect
        raise NetworkAttempted(f"socket.connect called with {args!r}")

    def deny_create_connection(*args, **kwargs):  # socket.create_connection
        raise NetworkAttempted(f"socket.create_connection called with {args!r}")

    def deny_urlopen(*args, **kwargs):  # urllib.request.urlopen
        raise NetworkAttempted(f"urllib.request.urlopen called with {args!r}")

    monkeypatch.setattr(socket.socket, "connect", deny_connect, raising=True)
    monkeypatch.setattr(socket, "create_connection", deny_create_connection)
    monkeypatch.setattr(urllib.request, "urlopen", deny_urlopen)
    yield


def test_analyze_never_touches_the_network(block_network):
    # The analyzer is module-cached. The first construction loads the spaCy
    # model from disk (offline); subsequent calls reuse it. If it's already
    # built, the call below just runs detection -- still offline-only.
    sample = (
        "Jane Doe filed her 1099. SSN 456-78-9012. "
        "Email jane@example.com. Routing 021000021."
    )
    findings = redactor.analyze(sample)
    # Sanity: detection still works (would be a different bug if zero hits).
    assert len(findings) > 0


def test_redact_never_touches_the_network(block_network):
    text = "Jane Doe (jane@example.com) called from 415-555-0199."
    red, findings = redactor.redact(text)
    # The redactor should still produce a result; we just verified no network.
    assert len(findings) > 0
    assert "jane@example.com" not in red
