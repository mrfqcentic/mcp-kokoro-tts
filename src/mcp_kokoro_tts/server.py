from __future__ import annotations

import sys

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from mcp_kokoro_tts import __version__
from mcp_kokoro_tts.lib import (
    ModelPaths,
    SpeechEngine,
    ensure_provisioned,
    format_voice_listing,
    speak_text,
)

_server = MCPServer("mcp-kokoro-tts", version=__version__)
_model_paths: ModelPaths | None = None
_engine: SpeechEngine | None = None


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
    _engine = None
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
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        raise ToolError(str(exc)) from exc

    parts = [
        f"Synthesized speech to: {result.output_path}",
        f"Voice: {result.voice}",
    ]
    if result.played:
        parts.append("Played audio on the local machine")
    elif result.play_error:
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


def run() -> None:
    initialize()
    _log(f"mcp-kokoro-tts: ready on stdio (v{__version__})")
    _server.run(transport="stdio")
