"""serve — L4 deployment adapters.

Two entry points over one shared pure handler:

    instrument/serve/http.py    stdlib http.server for container /
                                on-prem deploys (primary).
                                (kept portable; not primary).

Both share `serve.shape.handle(method, path, body, config) ->
(status, payload)` so the request-handling logic has exactly one
implementation.

This is the ONLY layer allowed to read env vars (via
`instrument.config.from_env`).
"""

from __future__ import annotations
