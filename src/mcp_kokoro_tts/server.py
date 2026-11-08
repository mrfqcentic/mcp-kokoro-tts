from __future__ import annotations

import os
import sys

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from mcp_kokoro_tts import __version__
from mcp_kokoro_tts.hotkey import HotkeyListener
from mcp_kokoro_tts.lib import (
    ModelPaths,
    SpeechEngine,
    ensure_provisioned,
    format_voice_listing,
    speak_text,
    stop_playback,
)
from mcp_kokoro_tts.web import SettingsServer

_server = MCPServer("mcp-kokoro-tts", version=__version__)
_model_paths: ModelPaths | None = None
_engine: SpeechEngine | None = None
_listener: HotkeyListener | None = None
_settings: SettingsServer | None = None


def _log(message: str) -> None:
    print(message, file=sys.stderr)


def _paths() -> ModelPaths:
    global _model_paths
    if _model_paths is None:
        raise RuntimeError("model is not provisioned")
    return _model_paths


def _speech_engine() -> SpeechEngine:
    global _engine
    if _engine is None:
        _engine = SpeechEngine(_paths())
    return _engine


def initialize(*, force_provision: bool = False) -> ModelPaths:
    global _model_paths, _engine
    _log("mcp-kokoro-tts: ensuring Kokoro-82M model is provisioned")
    _model_paths = ensure_provisioned(force=force_provision, log=_log)
    _log("mcp-kokoro-tts: loading speech engine")
    try:
        _engine = SpeechEngine(_model_paths)
    except SystemExit as exc:
        raise RuntimeError(
            f"speech engine failed to start (spaCy model install aborted): {exc}"
        ) from exc
    return _model_paths


@_server.tool(
    name="speak",
    title="Speak",
    description=(
        "Synthesize speech with Kokoro-82M and play it on the user's machine. "
        "Call this when the user wants the harness to talk, read something aloud, "
        "or hear a spoken response. Always pass clear, natural text to speak. "
        "Default voice resolution: TTS_VOICE env var, voices/default* in the package, "
        "first file in voices/, then the bundled af_heart voice from the model."
    ),
)
def speak(text: str, voice: str | None = None, speed: float = 1.0) -> str:
    try:
        result = speak_text(
            text,
            voice=voice,
            speed=speed,
            model_paths=_paths(),
            engine=_speech_engine(),
        )
    except (FileNotFoundError, ValueError, RuntimeError, SystemExit) as exc:
        raise ToolError(str(exc)) from exc

    parts = [
        f"Synthesized speech to: {result.output_path}",
        f"Voice: {result.voice}",
    ]
    if result.queue_position is not None:
        parts.append(f"Queued for playback (position {result.queue_position} in the audio queue)")
    if result.play_error:
        parts.append(f"Could not play audio: {result.play_error}")
    return ". ".join(parts) + "."


@_server.tool(
    name="list_voices",
    title="List voices",
    description=(
        "List Kokoro voices available to the speak tool and the currently selected default voice. "
        "Resolution order: TTS_VOICE env var, voices/default* file, first file in voices/, "
        "then the model's default af_heart voice."
    ),
)
def list_voices() -> str:
    return format_voice_listing(_paths())


@_server.tool(
    name="stop",
    title="Stop speaking",
    description=(
        "Stop the utterance playing right now and drop everything queued behind it. "
        "Use it when the user asks the harness to be quiet or starts talking over it."
    ),
)
def stop() -> str:
    dropped = stop_playback()
    return f"Playback stopped. Dropped {dropped} queued utterance(s)."


@_server.tool(
    name="settings",
    title="Hotkey settings",
    description=(
        "Return the local settings page URL, the current stop hotkey, and whether the "
        "hotkey listener is active. The page lets the user change the key combination."
    ),
)
def settings() -> str:
    config = _listener.config if _listener is not None else None
    label = config.label if config is not None else "Ctrl+Shift"
    status = _listener.status if _listener is not None else "not started"
    url = _settings.url if _settings is not None else "unavailable"
    return (
        f"Stop hotkey: {label}. Listener: {status}. Settings page: {url}"
    )


def _on_hotkey() -> None:
    dropped = stop_playback()
    _log(f"mcp-kokoro-tts: hotkey pressed - stopped playback ({dropped} queued dropped)")


def _start_controls() -> None:
    global _listener, _settings
    _listener = HotkeyListener(_on_hotkey)
    _listener.start()
    _settings = SettingsServer(listener=_listener, stop_playback=stop_playback)
    _settings.start()


DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8766


def transport_settings(
    argv: list[str] | None = None, env: dict[str, str] | None = None
) -> tuple[str, str, int]:
    """Pick the transport: stdio (one server per client) or shared HTTP.

    `--http` or TTS_TRANSPORT=http runs one streamable-HTTP server that many
    clients share, so the model loads once and every client feeds the same
    playback queue. TTS_HTTP_HOST / TTS_HTTP_PORT (or `--port N`) set the address.
    """
    argv = sys.argv[1:] if argv is None else argv
    env = dict(os.environ) if env is None else env
    transport = env.get("TTS_TRANSPORT", "stdio").strip().lower()
    host = env.get("TTS_HTTP_HOST", DEFAULT_HTTP_HOST)
    port_text = env.get("TTS_HTTP_PORT", str(DEFAULT_HTTP_PORT))
    args = iter(argv)
    for arg in args:
        if arg == "--http":
            transport = "http"
        elif arg == "--stdio":
            transport = "stdio"
        elif arg == "--port":
            port_text = next(args, port_text)
        elif arg.startswith("--port="):
            port_text = arg.split("=", 1)[1]
    if transport in ("http", "streamable-http"):
        transport = "streamable-http"
    elif transport != "stdio":
        raise ValueError(f"unknown TTS_TRANSPORT {transport!r}; use 'stdio' or 'http'")
    try:
        port = int(port_text)
    except ValueError as exc:
        raise ValueError(f"invalid HTTP port {port_text!r}") from exc
    return transport, host, port


def run() -> None:
    transport, host, port = transport_settings()
    initialize()
    _start_controls()
    if transport == "stdio":
        _log(f"mcp-kokoro-tts: ready on stdio (v{__version__})")
        _server.run(transport="stdio")
        return
    _log(f"mcp-kokoro-tts: ready on http://{host}:{port}/mcp (v{__version__})")
    _server.run(transport="streamable-http", host=host, port=port)
