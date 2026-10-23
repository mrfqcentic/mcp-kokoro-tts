from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_kokoro_tts import hotkey

CTRL = hotkey.MODIFIER_MASKS["ctrl"]
SHIFT = hotkey.MODIFIER_MASKS["shift"]
ALT = hotkey.MODIFIER_MASKS["alt"]
CMD = hotkey.MODIFIER_MASKS["cmd"]


def test_normalize_keys_dedupes_and_orders() -> None:
    assert hotkey.normalize_keys(["shift", "ctrl", "control"]) == ("ctrl", "shift")
    assert hotkey.label_for(["control", "shift"]) == "Ctrl+Shift"


def test_normalize_keys_rejects_unknown_and_empty() -> None:
    with pytest.raises(ValueError, match="unknown modifier"):
        hotkey.normalize_keys(["space"])
    with pytest.raises(ValueError, match="at least one"):
        hotkey.normalize_keys([])


def test_mask_for_combines_modifier_bits() -> None:
    assert hotkey.mask_for(["ctrl", "shift"]) == CTRL | SHIFT
    assert hotkey.mask_for(["cmd"]) == CMD


def test_matcher_fires_once_per_exact_chord() -> None:
    matcher = hotkey.HotkeyMatcher(hotkey.mask_for(["ctrl", "shift"]))

    assert matcher.update(CTRL) is False            # ctrl pressed first
    assert matcher.update(CTRL | SHIFT) is True     # chord complete -> fire
    assert matcher.update(CTRL | SHIFT) is False    # still held
    assert matcher.update(SHIFT) is False           # ctrl released
    assert matcher.update(CTRL | SHIFT) is True     # pressed again -> fire
    assert matcher.update(CTRL | SHIFT | ALT) is False
    assert matcher.update(CTRL | SHIFT) is True     # recovered after extra modifier


def test_matcher_ignores_non_modifier_bits() -> None:
    matcher = hotkey.HotkeyMatcher(hotkey.mask_for(["ctrl", "shift"]))
    assert matcher.update(CTRL | SHIFT | 0x1) is True  # alpha-shift bit is not a modifier


def test_config_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "hotkey.json"
    assert hotkey.load_config(path).keys == ("ctrl", "shift")

    hotkey.save_config(hotkey.HotkeyConfig(("cmd", "shift")), path)
    assert hotkey.load_config(path).keys == ("shift", "cmd")


def test_load_config_falls_back_on_garbage(tmp_path: Path) -> None:
    path = tmp_path / "hotkey.json"
    path.write_text("not json", encoding="utf-8")
    assert hotkey.load_config(path).keys == hotkey.DEFAULT_KEYS

    path.write_text(json.dumps({"keys": ["nope"]}), encoding="utf-8")
    assert hotkey.load_config(path).keys == hotkey.DEFAULT_KEYS


def test_listener_apply_persists_and_swaps_chord(tmp_path: Path) -> None:
    path = tmp_path / "hotkey.json"
    listener = hotkey.HotkeyListener(lambda: None, config_path=path, prompt_for_access=False)

    config = listener.apply(["alt"])
    assert config.keys == ("alt",)
    assert listener.config.keys == ("alt",)
    assert hotkey.load_config(path).keys == ("alt",)

    with pytest.raises(ValueError):
        listener.apply(["bogus"])
    assert listener.config.keys == ("alt",)
