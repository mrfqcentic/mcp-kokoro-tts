from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from mcp_kokoro_tts import hotkey, web


class _StubStop:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> int:
        self.calls += 1
        return 2


def _request(url: str, payload: dict | None = None) -> tuple[int, str]:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, response.read().decode("utf-8")


@pytest.fixture
def settings(tmp_path: Path):
    listener = hotkey.HotkeyListener(
        lambda: None, config_path=tmp_path / "hotkey.json", prompt_for_access=False
    )
    stop = _StubStop()
    server = web.SettingsServer(listener=listener, stop_playback=stop, port=0)
    assert server.start()
    try:
        yield server, listener, stop
    finally:
        server._httpd.shutdown()
        server._httpd.server_close()


def test_serves_the_settings_page(settings) -> None:
    server, _, _ = settings
    status, body = _request(server.url)
    assert status == 200
    assert "Stop hotkey" in body
    assert "Save" in body


def test_status_reports_the_current_chord(settings) -> None:
    server, _, _ = settings
    status, body = _request(f"{server.url}api/status")
    assert status == 200
    payload = json.loads(body)
    assert payload["keys"] == ["ctrl", "shift"]
    assert payload["label"] == "Ctrl+Shift"
    assert payload["listening"] is False


def test_post_hotkey_persists_the_new_chord(settings, tmp_path: Path) -> None:
    server, listener, _ = settings
    status, body = _request(f"{server.url}api/hotkey", {"keys": ["cmd", "shift"]})
    assert status == 200
    assert json.loads(body)["keys"] == ["shift", "cmd"]
    assert listener.config.keys == ("shift", "cmd")
    assert hotkey.load_config(tmp_path / "hotkey.json").keys == ("shift", "cmd")


def test_post_hotkey_rejects_a_bad_chord(settings) -> None:
    server, listener, _ = settings
    with pytest.raises(urllib.error.HTTPError) as error:
        _request(f"{server.url}api/hotkey", {"keys": ["space"]})
    assert error.value.code == 400
    assert listener.config.keys == ("ctrl", "shift")


def test_post_stop_drains_playback(settings) -> None:
    server, _, stop = settings
    status, body = _request(f"{server.url}api/stop", {})
    assert status == 200
    assert json.loads(body)["drained"] == 2
    assert stop.calls == 1
