"""First-pass local web UI for the umpire.

Stdlib only (``http.server``), so there is nothing to install: ::

    python -m kstycoon.web                 # serves http://127.0.0.1:8000
    python -m kstycoon.web --port 9000 --state mygame.json

The server holds one game state in memory, persisted to a JSON file. The
browser shows the current year's economy/pops/forces, lets the umpire key in
this year's directives (tax, budget split, readiness, projects, procurement),
and runs the financial year — returning the handoff report.
"""

from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import bridge
from . import serialize
from ._ui import PAGE
from .scenarios import south_korea_y0

# The server's data layer: talk to the local API via fetch.
_SERVER_API = """
const api = {
  async newState(){ return await (await fetch('/api/state')).json(); },
  async tick(state, d){ const r = await fetch('/api/tick',{method:'POST',
    headers:{'Content-Type':'application/json'}, body:JSON.stringify(d)}); return await r.json(); },
  async reset(){ return await (await fetch('/api/reset',{method:'POST'})).json(); },
};
"""
INDEX_HTML = PAGE.replace("__HEAD_EXTRA__", "").replace("__API__", _SERVER_API)


class _App:
    """Tiny in-memory holder for the game state + its save path."""

    def __init__(self, path: str):
        self.path = path
        if os.path.exists(path):
            self.state = serialize.load(path)
        else:
            self.state = south_korea_y0.build()
            self.save()

    def save(self) -> None:
        serialize.save(self.state, self.path)

    def reset(self) -> None:
        self.state = south_korea_y0.build()
        self.save()

    def apply_and_tick(self, decisions: dict) -> dict:
        self.state, payload = bridge.run_year(self.state, decisions)
        self.save()
        return payload


def _make_handler(app: _App):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200):
            self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
            elif self.path == "/api/state":
                self._json(serialize.to_dict(app.state))
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                self._json({"error": "bad json"}, 400)
                return
            if self.path == "/api/tick":
                try:
                    self._json(app.apply_and_tick(body))
                except Exception as exc:  # surface engine errors to the UI
                    self._json({"error": str(exc)}, 500)
            elif self.path == "/api/reset":
                app.reset()
                self._json(serialize.to_dict(app.state))
            else:
                self._json({"error": "not found"}, 404)

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kstycoon.web")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--state", default="state.json")
    args = parser.parse_args(argv)

    app = _App(args.state)
    server = ThreadingHTTPServer((args.host, args.port), _make_handler(app))
    print(f"KS-Tycoon umpire UI -> http://{args.host}:{args.port}  (state: {args.state})")
    print("Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
