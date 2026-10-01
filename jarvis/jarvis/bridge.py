"""Browser mode: serves the UI on 127.0.0.1 and exposes the Api over HTTP.

Used when pywebview is unavailable (`python main.py --browser`) and for UI testing. Requests must
carry a per-run secret token (embedded into index.html), so other web pages cannot call the API.
"""
from __future__ import annotations

import json
import logging
import mimetypes
import secrets
import threading
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .paths import WEB_DIR

log = logging.getLogger("jarvis.bridge")

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")


class BridgeServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, api, bus, port: int = 0):
        self.api = api
        self.bus = bus
        self.token = secrets.token_urlsafe(24)
        super().__init__(("127.0.0.1", port), _Handler)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/"

    def start_background(self) -> threading.Thread:
        thread = threading.Thread(target=self.serve_forever, name="bridge", daemon=True)
        thread.start()
        return thread


class _Handler(BaseHTTPRequestHandler):
    server: BridgeServer
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:  # quiet
        log.debug("%s - %s", self.address_string(), fmt % args)

    # --- helpers ----------------------------------------------------------------------------
    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def _send(self, status: int, body: bytes, ctype: str, extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, data: Any) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _authorized(self, query: dict[str, list[str]] | None = None) -> bool:
        token = self.headers.get("X-Jarvis-Token") or ((query or {}).get("token") or [""])[0]
        return secrets.compare_digest(token, self.server.token)

    # --- routes -----------------------------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        if not self._host_ok():
            self._send(HTTPStatus.FORBIDDEN, b"forbidden", "text/plain")
            return
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/api/events":
            query = urllib.parse.parse_qs(parsed.query)
            if not self._authorized(query):
                self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "forbidden"})
                return
            try:
                after = int((query.get("after") or ["0"])[0])
            except ValueError:
                after = 0
            if after > self.server.bus.last_id:  # backend restarted
                after = 0
            events = self.server.bus.wait(after, timeout=20)
            self._json(HTTPStatus.OK, {"ok": True, "events": events, "last": self.server.bus.last_id})
            return
        self._static(parsed.path)

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if not self._host_ok():
            self._send(HTTPStatus.FORBIDDEN, b"forbidden", "text/plain")
            return
        parsed = urllib.parse.urlsplit(self.path)
        if not parsed.path.startswith("/api/") or not self._authorized():
            self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "forbidden"})
            return
        name = parsed.path[len("/api/"):]
        method = getattr(self.server.api, name, None)
        if name.startswith("_") or not callable(method):
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": f"unknown method {name}"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}") if length else {}
            args = payload.get("args") or []
            result = method(*args)
            self._json(HTTPStatus.OK, {"ok": True, "result": result})
        except Exception as exc:  # report to the UI
            log.warning("API %s failed: %s", name, exc)
            self._json(HTTPStatus.OK, {"ok": False, "error": str(exc) or type(exc).__name__})

    def _static(self, path: str) -> None:
        rel = urllib.parse.unquote(path).lstrip("/") or "index.html"
        root = WEB_DIR.resolve()
        target = (root / rel).resolve()
        if root not in target.parents and target != root:
            self._send(HTTPStatus.FORBIDDEN, b"forbidden", "text/plain")
            return
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")
            return
        body = target.read_bytes()
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if target.name == "index.html":
            boot = f'<script>window.__JARVIS_TOKEN__ = "{self.server.token}";</script>'
            body = body.replace(b"<!--JARVIS_BOOT-->", boot.encode("utf-8"))
        if ctype.startswith("text/") or ctype in ("application/json", "image/svg+xml"):
            ctype += "; charset=utf-8"
        self._send(HTTPStatus.OK, body, ctype)


def serve_forever(server: BridgeServer, stop: threading.Event | None = None) -> None:
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()


__all__ = ["BridgeServer", "serve_forever", "Path"]
