"""CONTRACTS for transport-layer request hygiene.

Covers the Content-Length validation added for deployment safety:
a negative Content-Length previously passed the `length > limit`
body cap and turned `rfile.read(length)` into read-until-EOF — an
unbounded read bypassing `max_body_bytes`. Non-integer values raised
an uncaught ValueError inside the handler.
"""

from __future__ import annotations

import json
import socket
import threading

import pytest

from instrument.config import Config
from instrument.serve.http import serve


@pytest.fixture
def live_server():
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


def _raw_request(host: str, port: int, content_length: str,
                 body: bytes = b"hello") -> tuple[int, dict]:
    """Send a request with a hand-built Content-Length header.

    http.client refuses to send malformed Content-Length, so this
    speaks raw HTTP over a socket.
    """
    req = (
        f"POST / HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n"
        f"Content-Length: {content_length}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    ).encode("ascii") + body
    with socket.create_connection((host, port), timeout=10) as sock:
        sock.sendall(req)
        sock.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            data = sock.recv(65536)
            if not data:
                break
            chunks.append(data)
    raw = b"".join(chunks).decode("utf-8", errors="replace")
    status_line, _, rest = raw.partition("\r\n")
    status = int(status_line.split(" ", 2)[1])
    _, _, payload = rest.partition("\r\n\r\n")
    try:
        return status, json.loads(payload)
    except json.JSONDecodeError:
        return status, {"_raw": payload}


def test_negative_content_length_is_400(live_server):
    host, port = live_server
    status, payload = _raw_request(host, port, "-5")
    assert status == 400
    assert payload.get("error") == "invalid_content_length"


def test_garbage_content_length_is_400(live_server):
    host, port = live_server
    status, payload = _raw_request(host, port, "abc")
    assert status == 400
    assert payload.get("error") == "invalid_content_length"


def test_normal_request_still_round_trips(live_server):
    host, port = live_server
    body = ("The committee reviewed the proposal carefully and concluded "
            "that the evidence was incomplete. " * 12).encode("utf-8")
    status, payload = _raw_request(host, port, str(len(body)), body=body)
    assert status == 200
    assert payload["n_words"] > 0


def test_request_id_header_and_500_correlation(live_server):
    """Every response carries X-Request-Id; structured support story."""
    import urllib.request
    host, port = live_server
    body = ("The committee reviewed the proposal and concluded the "
            "evidence was incomplete. " * 12).encode("utf-8")
    req = urllib.request.Request(
        f"http://{host}:{port}/?shape=compact", data=body, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        rid = resp.headers.get("X-Request-Id")
        assert rid and len(rid) == 12
