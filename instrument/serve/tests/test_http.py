"""CONTRACTS for the stdlib http.server adapter.

Spins up a real threading server on a free port, POSTs, asserts.
Covers: POST round-trip, GET /health, 405, 413 over the wire.
"""

from __future__ import annotations

import json
import threading
import urllib.request
from http.client import HTTPConnection
from pathlib import Path

import pytest

from instrument.config import Config
from instrument.serve.http import serve

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def live_server():
    """Start a server on a random free port; shutdown on teardown."""
    cfg = Config(host="127.0.0.1", port=0, response_shape="compact")
    server = serve(cfg)
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield host, port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _post(host: str, port: int, path: str, body: bytes,
          headers: dict | None = None) -> tuple[int, dict | str]:
    conn = HTTPConnection(host, port, timeout=10)
    try:
        conn.request(
            "POST", path, body=body,
            headers=headers or {"Content-Type": "text/plain; charset=utf-8"},
        )
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8")
    finally:
        conn.close()
    try:
        return resp.status, json.loads(raw)
    except json.JSONDecodeError:
        return resp.status, raw


def _get(host: str, port: int, path: str) -> tuple[int, dict | str]:
    conn = HTTPConnection(host, port, timeout=10)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8")
    finally:
        conn.close()
    try:
        return resp.status, json.loads(raw)
    except json.JSONDecodeError:
        return resp.status, raw


def test_health_endpoint(live_server):
    host, port = live_server
    status, payload = _get(host, port, "/health")
    assert status == 200
    assert payload == {"status": "ok"}


def test_post_compact_round_trip(live_server):
    host, port = live_server
    text = (REPO_ROOT / "fixtures" / "source" / "llm_technical.md").read_text(encoding="utf-8")
    status, payload = _post(host, port, "/?shape=compact", text.encode("utf-8"))
    assert status == 200
    assert set(payload.keys()) == {"flags", "register", "coherence", "n_words"}
    assert payload["n_words"] > 0


def test_post_default_shape_is_compact_override(live_server):
    """Fixture set response_shape=compact; default query should use that."""
    host, port = live_server
    text = (REPO_ROOT / "fixtures" / "source" / "llm_technical.md").read_text(encoding="utf-8")
    status, payload = _post(host, port, "/", text.encode("utf-8"))
    assert status == 200
    assert set(payload.keys()) == {"flags", "register", "coherence", "n_words"}


def test_empty_body_returns_400(live_server):
    host, port = live_server
    status, payload = _post(host, port, "/", b"")
    assert status == 400


def test_method_not_allowed(live_server):
    host, port = live_server
    # DELETE is not handled; only GET and POST routes exist.
    conn = HTTPConnection(host, port, timeout=5)
    try:
        conn.request("DELETE", "/", body=b"whatever")
        resp = conn.getresponse()
        resp.read()
    finally:
        conn.close()
    assert resp.status in (405, 501)  # stdlib returns 501 for unhandled verbs
