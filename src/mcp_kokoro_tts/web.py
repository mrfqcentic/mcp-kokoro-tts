"""Loopback settings page for the stop hotkey.

Only a tiny HTTP server on 127.0.0.1: it reads and writes the hotkey config and
can trigger `stop_playback`. Nothing leaves the machine.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from typing import Any, Callable

from mcp_kokoro_tts.hotkey import (
    HotkeyListener,
    default_config_path,
    listen_access_granted,
)

DEFAULT_PORT = 8765


def default_port() -> int:
    try:
        return int(os.environ.get("TTS_WEB_PORT", DEFAULT_PORT))
    except ValueError:
        return DEFAULT_PORT


def _page() -> str:
    return files(__package__).joinpath("settings.html").read_text(encoding="utf-8")


class SettingsServer:
    def __init__(
        self,
        *,
        listener: HotkeyListener,
        stop_playback: Callable[[], int],
        port: int | None = None,
    ) -> None:
        self.listener = listener
        self.stop_playback = stop_playback
        self.port = default_port() if port is None else port
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    @property
    def running(self) -> bool:
        return self._httpd is not None

    def start(self) -> bool:
        handler = type("SettingsHandler", (_Handler,), {"settings": self})
        try:
            self._httpd = ThreadingHTTPServer(("127.0.0.1", self.port), handler)
        except OSError as exc:
            print(
                f"mcp-kokoro-tts: settings page unavailable at {self.url}: {exc}",
                file=sys.stderr,
            )
            return False
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="mcp-kokoro-tts-settings",
            daemon=True,
        )
        self._thread.start()
        # port 0 asks the OS for a free port; report the one we actually got.
        self.port = int(self._httpd.server_address[1])
        print(f"mcp-kokoro-tts: settings page at {self.url}", file=sys.stderr)
        return True

    def status(self) -> dict[str, Any]:
        config = self.listener.config
        return {
            "keys": list(config.keys),
            "label": config.label,
            "status": self.listener.status,
            "listening": self.listener.listening,
            "url": self.url,
            "config_path": str(default_config_path()),
            "input_monitoring": listen_access_granted(),
        }


class _Handler(BaseHTTPRequestHandler):
    settings: SettingsServer
    server_version = "mcp-kokoro-tts"
    sys_version = ""

    def log_message(self, format: str, *args: Any) -> None:  # keep stderr clean
        return

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        if self.path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", _page().encode("utf-8"))
            return
        if self.path == "/api/status":
            self._json(self.settings.status())
            return
        self._json({"error": "not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802 (http.server API)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._json({"error": "invalid JSON"}, status=400)
            return
        if not isinstance(payload, dict):
            self._json({"error": "expected a JSON object"}, status=400)
            return

        if self.path == "/api/hotkey":
            keys = payload.get("keys")
            if not isinstance(keys, list):
                self._json({"error": "`keys` must be a list of modifiers"}, status=400)
                return
            try:
                config = self.settings.listener.apply([str(key) for key in keys])
            except ValueError as exc:
                self._json({"error": str(exc)}, status=400)
                return
            except OSError as exc:
                self._json({"error": f"could not save the config: {exc}"}, status=500)
                return
            self._json({"ok": True, **config.to_json()})
            return

        if self.path == "/api/stop":
            self._json({"ok": True, "drained": self.settings.stop_playback()})
            return

        self._json({"error": "not found"}, status=404)

    def _json(self, payload: dict[str, Any], *, status: int = 200) -> None:
        self._send(
            status, "application/json", json.dumps(payload).encode("utf-8")
        )

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
