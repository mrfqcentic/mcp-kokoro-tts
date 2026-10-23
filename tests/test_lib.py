from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from mcp_kokoro_tts import lib
from mcp_kokoro_tts.lib import (
    ModelPaths,
    resolve_default_voice,
    resolve_voice_path,
    verify_model,
)


def test_resolve_default_voice_prefers_env() -> None:
    package = [Path("/pkg/a.pt"), Path("/pkg/b.pt")]
    model = [Path("/model/af_heart.pt")]
    assert (
        resolve_default_voice(
            env_voice="af_heart",
            package_voices=package,
            model_voices=model,
        )
        == "af_heart"
    )


def test_resolve_default_voice_prefers_default_pin(tmp_path: Path) -> None:
    package = [tmp_path / "b.pt", tmp_path / "default-x.pt", tmp_path / "a.pt"]
    for path in package:
        path.write_bytes(b"x")
    model = [tmp_path / "af_heart.pt"]
    model[-1].write_bytes(b"x")

    assert (
        resolve_default_voice(
            env_voice=None,
            package_voices=sorted(package),
            model_voices=model,
        )
        == str(tmp_path / "default-x.pt")
    )


def test_resolve_default_voice_falls_back_to_model_default(tmp_path: Path) -> None:
    model = [tmp_path / "af_heart.pt"]
    model[0].write_bytes(b"x")
    assert (
        resolve_default_voice(
            env_voice=None,
            package_voices=[],
            model_voices=model,
        )
        == str(model[0])
    )


def test_spacy_english_model_wheel_url_matches_minor_series() -> None:
    assert lib.spacy_english_model_wheel_url("3.8.15") == (
        "https://github.com/explosion/spacy-models/releases/download/"
        "en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl"
    )


def test_install_wheel_uses_pip_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(lib.importlib.util, "find_spec", lambda name: object() if name == "pip" else None)

    def fake_run(command, capture_output=True, text=True):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(lib.subprocess, "run", fake_run)
    lib.install_wheel_into_this_python("https://example.com/model.whl")
    assert calls[0][0] == sys.executable
    assert calls[0][1:4] == ["-m", "pip", "install"]
    assert calls[0][-1] == "https://example.com/model.whl"


def test_install_wheel_uses_uv_python_when_pip_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(lib.importlib.util, "find_spec", lambda name: None)
    monkeypatch.setattr(lib.shutil, "which", lambda name: "/opt/uv" if name == "uv" else None)

    def fake_run(command, capture_output=True, text=True):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(lib.subprocess, "run", fake_run)
    lib.install_wheel_into_this_python("https://example.com/model.whl")
    assert calls[0][:4] == ["/opt/uv", "pip", "install", "--python"]
    assert calls[0][4] == sys.executable
    assert calls[0][-1] == "https://example.com/model.whl"


def test_install_wheel_errors_when_no_installer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lib.importlib.util, "find_spec", lambda name: None)
    monkeypatch.setattr(lib.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="no pip"):
        lib.install_wheel_into_this_python("https://example.com/model.whl")


def test_ensure_spacy_english_model_skips_when_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lib, "spacy_english_model_installed", lambda: True)

    def should_not_install(_url: str) -> None:
        raise AssertionError("should not install")

    monkeypatch.setattr(lib, "install_wheel_into_this_python", should_not_install)
    lib.ensure_spacy_english_model(log=lambda _message: None)


def test_verify_model_reports_missing(tmp_path: Path) -> None:
    missing = verify_model(tmp_path)
    assert "config.json" in missing
    assert "kokoro-v1_0.pth" in missing


def test_resolve_voice_path_from_model_dir(tmp_path: Path) -> None:
    voices = tmp_path / "voices"
    voices.mkdir()
    voice = voices / "af_heart.pt"
    voice.write_bytes(b"x")

    resolved = resolve_voice_path(
        "af_heart",
        model_dir=tmp_path,
        package_voices=tmp_path / "package-voices",
    )
    assert resolved == voice


def test_format_voice_listing_mentions_model_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from mcp_kokoro_tts import lib

    voices = tmp_path / "voices"
    voices.mkdir()
    (voices / "af_heart.pt").write_bytes(b"x")
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    (tmp_path / "kokoro-v1_0.pth").write_bytes(b"x")

    paths = ModelPaths(
        model_dir=tmp_path,
        config_path=tmp_path / "config.json",
        weights_path=tmp_path / "kokoro-v1_0.pth",
        voices_dir=voices,
    )
    monkeypatch.setattr(lib, "package_voices_dir", lambda: tmp_path / "package-voices")
    text = lib.format_voice_listing(paths)
    assert str(tmp_path) in text
    assert "af_heart" in text


def test_playback_queue_serializes_in_call_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    log = tmp_path / "order.log"
    files = []
    for name in ("a", "b", "c"):
        path = tmp_path / f"{name}.wav"
        path.write_bytes(b"x")
        files.append(path)

    def fake_player(file: str) -> tuple[str, list[str]]:
        script = f"echo start {file} >> {log}; sleep 0.1; echo end {file} >> {log}"
        return ("/bin/sh", ["-c", script])

    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr(lib, "pick_player", fake_player)

    assert [lib.enqueue_audio(path).ok for path in files] == [True, True, True]
    lib._playback_queue.join()

    events = [line.split() for line in log.read_text().splitlines()]
    assert [(kind, file) for kind, file in events] == [
        (kind, str(path)) for path in files for kind in ("start", "end")
    ]
