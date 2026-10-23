"""Global modifier-only hotkey that interrupts speech playback.

The tap is *listen-only* so it never steals the key chord from another app that
is already using it (FluidVoice dictation, for instance). macOS gates keyboard
taps behind the Accessibility permission; without it the listener degrades to
"not listening" and the settings page and the `stop` tool still work.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

# CGEventFlags values, kept as plain integers so the matching logic below stays
# importable (and testable) without PyObjC installed.
MODIFIER_MASKS: dict[str, int] = {
    "ctrl": 0x00040000,
    "shift": 0x00020000,
    "alt": 0x00080000,
    "cmd": 0x00100000,
    "fn": 0x00800000,
}
MODIFIER_MASK = 0
for _modifier_mask in MODIFIER_MASKS.values():
    MODIFIER_MASK |= _modifier_mask

DEFAULT_KEYS: tuple[str, ...] = ("ctrl", "shift")

_KEY_ALIASES = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "shift": "shift",
    "alt": "alt",
    "option": "alt",
    "opt": "alt",
    "cmd": "cmd",
    "command": "cmd",
    "meta": "cmd",
    "super": "cmd",
    "fn": "fn",
}


def normalize_keys(keys: Iterable[str]) -> tuple[str, ...]:
    """Validate, dedupe and canonically order a modifier list."""
    normalized: list[str] = []
    for raw in keys:
        key = _KEY_ALIASES.get(str(raw).strip().lower())
        if key is None:
            raise ValueError(
                f"unknown modifier {raw!r}; use one of: {', '.join(MODIFIER_MASKS)}"
            )
        if key not in normalized:
            normalized.append(key)
    if not normalized:
        raise ValueError("at least one modifier is required")
    order = list(MODIFIER_MASKS)
    return tuple(sorted(normalized, key=order.index))


def mask_for(keys: Iterable[str]) -> int:
    mask = 0
    for key in normalize_keys(keys):
        mask |= MODIFIER_MASKS[key]
    return mask


def label_for(keys: Iterable[str]) -> str:
    return "+".join(key.capitalize() for key in normalize_keys(keys))


def default_config_dir() -> Path:
    override = os.environ.get("TTS_CONFIG_DIR")
    if override:
        return Path(override)
    return Path.home() / ".config" / "mcp-kokoro-tts"


def default_config_path() -> Path:
    return default_config_dir() / "hotkey.json"


@dataclass(frozen=True)
class HotkeyConfig:
    keys: tuple[str, ...] = DEFAULT_KEYS

    @property
    def mask(self) -> int:
        return mask_for(self.keys)

    @property
    def label(self) -> str:
        return label_for(self.keys)

    def to_json(self) -> dict[str, object]:
        return {"keys": list(self.keys), "label": self.label}


def load_config(path: Path | None = None) -> HotkeyConfig:
    target = path or default_config_path()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        return HotkeyConfig(normalize_keys(payload.get("keys") or DEFAULT_KEYS))
    except (OSError, ValueError, TypeError, AttributeError):
        return HotkeyConfig()


def save_config(config: HotkeyConfig, path: Path | None = None) -> Path:
    target = path or default_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(config.to_json(), indent=2) + "\n", encoding="utf-8")
    return target


class HotkeyMatcher:
    """Fires once per press of exactly the configured modifier set.

    A chord like Ctrl+Shift is pressed one key at a time, so only the state where
    the pressed set *equals* the configured set triggers; the intermediate Ctrl
    window and any extra modifier are ignored.
    """

    def __init__(self, mask: int) -> None:
        self._mask = mask
        self._held = False

    @property
    def mask(self) -> int:
        return self._mask

    def update(self, flags: int) -> bool:
        pressed = flags & MODIFIER_MASK
        if pressed != self._mask:
            self._held = False
            return False
        if self._held:
            return False
        self._held = True
        return self._mask != 0


def listen_access_granted() -> bool:
    """Whether macOS has granted Input Monitoring to this process."""
    if sys.platform != "darwin":
        return False
    try:
        import Quartz
    except ImportError:
        return False
    try:
        return bool(Quartz.CGPreflightListenEventAccess())
    except Exception:
        return False


def request_listen_access() -> bool:
    """Ask macOS for Input Monitoring; the system shows the consent dialog."""
    if sys.platform != "darwin":
        return False
    try:
        import Quartz
    except ImportError:
        return False
    try:
        return bool(Quartz.CGRequestListenEventAccess())
    except Exception:
        return False


class HotkeyListener:
    """Runs the Quartz tap on its own thread and calls `on_trigger` per press."""

    def __init__(
        self,
        on_trigger: Callable[[], None],
        *,
        config_path: Path | None = None,
        prompt_for_access: bool = True,
    ) -> None:
        self._on_trigger = on_trigger
        self._config_path = config_path or default_config_path()
        self._prompt_for_access = prompt_for_access
        self._lock = threading.Lock()
        self._config = load_config(self._config_path)
        self._matcher = HotkeyMatcher(self._config.mask)
        self._thread: threading.Thread | None = None
        self.status = "stopped"

    @property
    def config(self) -> HotkeyConfig:
        with self._lock:
            return self._config

    @property
    def listening(self) -> bool:
        return self.status == "listening"

    def apply(self, keys: Sequence[str]) -> HotkeyConfig:
        """Persist a new chord and use it immediately."""
        config = HotkeyConfig(normalize_keys(keys))
        save_config(config, self._config_path)
        with self._lock:
            self._config = config
            self._matcher = HotkeyMatcher(config.mask)
        return config

    def start(self) -> None:
        if self._thread is not None:
            return
        thread = threading.Thread(
            target=self._run, name="mcp-kokoro-tts-hotkey", daemon=True
        )
        self._thread = thread
        thread.start()

    def _run(self) -> None:
        if sys.platform != "darwin":
            self.status = "unsupported"
            self._log("global hotkey is macOS-only; the settings page still works")
            return

        try:
            import Quartz
        except ImportError:
            self.status = "no_quartz"
            self._log(
                "PyObjC Quartz is missing; global hotkey disabled "
                "(pip install pyobjc-framework-Quartz)"
            )
            return

        granted = listen_access_granted()
        if not granted and self._prompt_for_access:
            request_listen_access()
            granted = listen_access_granted()
        if not granted:
            self._log(
                "Input Monitoring is not granted - enable the app running this server "
                "(System Settings > Privacy & Security > Input Monitoring), then "
                "restart. The settings page and `stop` tool still work without it."
            )

        callback = self._make_callback(Quartz)
        tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly,
            Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged),
            callback,
            None,
        )
        if tap is None:
            self.status = "tap_failed"
            self._log("could not create the keyboard event tap (permission denied)")
            return

        source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
        Quartz.CFRunLoopAddSource(
            Quartz.CFRunLoopGetCurrent(), source, Quartz.kCFRunLoopCommonModes
        )
        Quartz.CGEventTapEnable(tap, True)
        # Keep both references alive for as long as the run loop spins.
        self._tap = tap
        self._source = source
        self.status = "listening" if granted else "needs_input_monitoring"
        if granted:
            self._log(f"hold {self.config.label} to stop playback")
        Quartz.CFRunLoopRun()

    def _make_callback(self, quartz: Any) -> Callable[..., Any]:
        def callback(proxy, event_type, event, refcon):
            try:
                with self._lock:
                    matcher = self._matcher
                if matcher.update(quartz.CGEventGetFlags(event)):
                    self._on_trigger()
            except Exception as exc:  # a bad event must never kill the tap
                self._log(f"hotkey handling failed: {exc}")
            return event

        return callback

    @staticmethod
    def _log(message: str) -> None:
        print(f"mcp-kokoro-tts: {message}", file=sys.stderr)
