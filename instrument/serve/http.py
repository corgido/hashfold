"""http — stdlib `http.server` adapter.

Primary deployment entry for Railway / container / on-prem runs.
Thin transport layer around `serve.shape.handle` — decode request,
call handler, encode response.

    python -m instrument.serve.http
    # => listens on 0.0.0.0:8000, POST /

Note: ThreadingHTTPServer uses OS threads. Because the instrument's
work is CPU-bound (pure-Python feature extraction), threads
serialise under the GIL. For production deployments requiring
concurrent request handling, run multiple processes behind a reverse
proxy (e.g. gunicorn --workers=N, or multiple container replicas).
The instrument is stateless; horizontal scaling is straightforward.

Deployment perimeter: this adapter does request hygiene (body cap,
Content-Length validation, read timeout, UTF-8 validation) but has
no authentication or rate limiting by design — it is meant to sit
on a private network / behind the deployment's own perimeter
(reverse proxy, service mesh, firewall), not on the public
internet.
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from instrument.config import Config, from_env
from instrument.serve.shape import handle_json


class _InstrumentHandler(BaseHTTPRequestHandler):
    """One request, one `handle_json` call."""

    # Populated by `serve()` before starting the server.
    config: Optional[Config] = None

    # Socket timeout (seconds) for reading the request. Without this a
    # client that opens a connection and never finishes sending headers
    # or body holds an OS thread forever (slowloris). 60s is generous
    # for a measurement POST; the deployment perimeter (reverse proxy /
    # private network) is still the primary defence — see module note.
    timeout = 60

    def _write(self, status: int, body: str, request_id: str = "-") -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Request-Id", request_id)
        self.end_headers()
        self.wfile.write(payload)

    def _handle(self, method: str) -> None:
        cfg = self.config or Config()
        t0 = time.monotonic()
        # Correlation id for support: echoed in the X-Request-Id header,
        # in the access log line, and in 500 bodies. NOT part of the
        # measurement record — determinism applies to emission content;
        # transport diagnostics may vary.
        rid = uuid.uuid4().hex[:12]
        raw_length = self.headers.get("Content-Length") or "0"
        try:
            length = int(raw_length)
        except ValueError:
            self._write(400, json.dumps({"error": "invalid_content_length"}), rid)
            self._log_access(method, self.path, 400, 0,
                             time.monotonic() - t0, rid)
            return
        if length < 0:
            # A negative Content-Length would pass the `> limit` cap and
            # turn rfile.read(length) into read-until-EOF — an unbounded
            # read that bypasses max_body_bytes. Reject it outright.
            self._write(400, json.dumps({"error": "invalid_content_length"}), rid)
            self._log_access(method, self.path, 400, 0,
                             time.monotonic() - t0, rid)
            return

        limit = cfg.max_body_bytes or (cfg.max_words * 8)
        if limit > 0 and length > limit:
            self._write(
                413,
                json.dumps({
                    "error": "body_too_large",
                    "max_bytes": limit,
                    "content_length": length,
                }),
                rid,
            )
            elapsed = time.monotonic() - t0
            self._log_access(method, self.path, 413, 0, elapsed, rid)
            return

        raw = self.rfile.read(length) if length else b""
        try:
            body = raw.decode("utf-8")
        except UnicodeDecodeError:
            self._write(400, json.dumps({"error": "invalid_utf8"}), rid)
            self._log_access(method, self.path, 400, length,
                             time.monotonic() - t0, rid)
            return
        status, response_body = handle_json(
            method, self.path, body, cfg, body_bytes=raw,
        )
        if status == 500:
            # Give the caller something to quote at support; pairs with
            # the traceback shape.py just wrote to stderr.
            try:
                payload = json.loads(response_body)
                payload["request_id"] = rid
                response_body = json.dumps(payload)
            except (json.JSONDecodeError, TypeError):
                pass
        self._write(status, response_body, rid)
        elapsed = time.monotonic() - t0
        self._log_access(method, self.path, status, length, elapsed, rid)

    def _log_access(
        self, method: str, path: str, status: int, body_size: int,
        elapsed: float, request_id: str = "-",
    ) -> None:
        """One JSON line per request to stderr — machine-parseable so the
        user's log shipper needs zero configuration beyond stderr
        capture."""
        print(
            json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "request_id": request_id,
                "method": method,
                "path": path,
                "status": status,
                "req_bytes": body_size,
                "dur_ms": round(elapsed * 1000, 1),
            }, separators=(",", ":")),
            file=sys.stderr,
            flush=True,
        )

    def do_GET(self) -> None:   # noqa: N802 — stdlib naming
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._handle("POST")

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


def serve(config: Optional[Config] = None) -> ThreadingHTTPServer:
    """Start a threading HTTP server and return it.

    Callers are expected to run `server.serve_forever()` themselves;
    this function returns the bound server so tests can call
    `server.shutdown()` / `server.server_close()` cleanly.
    """
    cfg = config or from_env()
    if cfg.references_dir:
        # Eager registration: a malformed user reference aborts boot
        # with ReferenceLoadError instead of surfacing mid-request.
        from instrument.routing.reference import load_reference, set_reference_dir
        found = set_reference_dir(cfg.references_dir)
        print(
            json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "event": "references_registered",
                "dir": str(cfg.references_dir),
                "references": [f"{n}_{v}" for n, v in found],
            }, separators=(",", ":")),
            file=sys.stderr, flush=True,
        )
        # Feature-schema compatibility warning (0.9.1): a reference whose
        # stat blocks use feature keys the running instrument no longer
        # emits (e.g. pre-rename rst.contrast_pressure) can never project
        # — every distance against it is silently None. Warn loudly at
        # boot; do not abort (mixed sets may be intentional).
        from instrument.reading.extended import ALL_FEATURE_KEYS
        from instrument.reading.flat import FEATURE_ORDER
        _live_keys = set(FEATURE_ORDER) | set(ALL_FEATURE_KEYS)
        for n, v in found:
            ref = load_reference(n, v)
            stale = {
                k for k in ref.pc_zscore_mean
                if not k.startswith("stylometry.") and k not in _live_keys
            }
            if stale:
                print(
                    json.dumps({
                        "ts": datetime.now(timezone.utc).isoformat(
                            timespec="milliseconds"),
                        "event": "reference_feature_schema_mismatch",
                        "reference": f"{n}_{v}",
                        "unknown_feature_keys": sorted(stale),
                        "consequence": (
                            "this reference cannot project under the "
                            "running instrument; its distances will be "
                            "null. Rebuild it with tools.build_reference "
                            "under this instrument version."
                        ),
                    }, separators=(",", ":")),
                    file=sys.stderr, flush=True,
                )
    _InstrumentHandler.config = cfg
    server = ThreadingHTTPServer((cfg.host, cfg.port), _InstrumentHandler)
    return server


def main() -> None:
    server = serve()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
