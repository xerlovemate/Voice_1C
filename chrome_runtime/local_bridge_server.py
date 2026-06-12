from __future__ import annotations

import json
import logging
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse


SpeechEventCallback = Callable[[str, dict], None]


class LocalBridgeServer:
    def __init__(
        self,
        bridge_dir: Path,
        on_event: SpeechEventCallback,
        logger: logging.Logger | None = None,
        port: int = 0,
    ):
        self.bridge_dir = Path(bridge_dir)
        self.on_event = on_event
        self.logger = logger or logging.getLogger("voice1c.chrome.bridge")
        self.port = int(port or 0)
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        if not self._server:
            return ""
        host, port = self._server.server_address
        return f"http://127.0.0.1:{port}/speech_bridge.html"

    def start(self) -> str:
        if self._server:
            return self.url

        bridge_dir = self.bridge_dir
        on_event = self.on_event
        logger = self.logger

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):  # noqa: A002
                logger.debug("[CHROME_BRIDGE] " + format, *args)

            def _send_json(self, payload: dict, status: int = 200) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Headers", "content-type")
                self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError, OSError) as exc:
                    logger.debug("[CHROME_BRIDGE] client disconnected before response: %s", exc)

            def do_OPTIONS(self) -> None:
                self._send_json({"ok": True})

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path in {"/", "/speech_bridge.html"}:
                    target = bridge_dir / "speech_bridge.html"
                else:
                    name = Path(parsed.path.lstrip("/")).name
                    target = bridge_dir / name

                if not target.exists() or not target.is_file():
                    self._send_json({"ok": False, "error": "not found"}, 404)
                    return

                data = target.read_bytes()
                content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self) -> None:
                parsed = urlparse(self.path)
                length = int(self.headers.get("content-length") or 0)
                try:
                    payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                except Exception:
                    payload = {}

                mapping = {
                    "/api/state": "state",
                    "/api/speech/state": "state",
                    "/api/speech/interim": "interim",
                    "/api/speech/final": "final",
                    "/api/speech/error": "error",
                    "/api/speech/level": "level",
                }
                event = mapping.get(parsed.path)
                if not event:
                    self._send_json({"ok": False, "error": "unknown endpoint"}, 404)
                    return
                try:
                    on_event(event, payload)
                except Exception as exc:
                    logger.exception("[CHROME_BRIDGE] event handler failed")
                    self._send_json({"ok": False, "error": str(exc)}, 500)
                    return
                self._send_json({"ok": True})

        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, name="Voice1CChromeBridge", daemon=True)
        self._thread.start()
        self.logger.info("[CHROME] bridge server url: %s", self.url)
        return self.url

    def stop(self) -> None:
        if not self._server:
            return
        self._server.shutdown()
        self._server.server_close()
        self._server = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None
