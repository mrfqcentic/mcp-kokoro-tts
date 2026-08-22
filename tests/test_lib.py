from __future__ import annotations

from pathlib import Path

import pytest

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
