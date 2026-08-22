from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

REPO_ID = "hexgrad/Kokoro-82M"
DEFAULT_VOICE_ID = "af_heart"
DEFAULT_LANG_CODE = "a"
SAMPLE_RATE = 24_000
TEXT_MAX_LEN = 500
SOUND_FAIL_FAST_MS = 1500
SPACY_EN_MODEL = "en_core_web_sm"

REQUIRED_MODEL_FILES = (
    "config.json",
    "kokoro-v1_0.pth",
    f"voices/{DEFAULT_VOICE_ID}.pt",
)

VOICE_FILE_EXT = re.compile(r"\.pt$", re.IGNORECASE)


@dataclass(frozen=True)
class Result:
    ok: bool
    error: str | None = None


@dataclass(frozen=True)
class ModelPaths:
    model_dir: Path
    config_path: Path
    weights_path: Path
    voices_dir: Path


@dataclass(frozen=True)
class SpeakResult:
    output_path: Path
    voice: str
    segment_count: int
    played: bool
    play_error: str | None = None


def project_root() -> Path:
    return Path(__file__).resolve().parent


def package_voices_dir() -> Path:
    return project_root() / "voices"


def default_model_dir() -> Path:
    override = os.environ.get("TTS_MODEL_DIR")
    if override:
        return Path(override)
    cache_home = os.environ.get("XDG_CACHE_HOME")
    base = Path(cache_home) if cache_home else Path.home() / ".cache"
    return base / "mcp-kokoro-tts" / "Kokoro-82M"


def default_cache_dir() -> Path:
    override = os.environ.get("TTS_HF_CACHE_DIR")
    if override:
        return Path(override)
    return default_model_dir().parent / "hf-hub-cache"


def default_output_dir() -> Path:
    override = os.environ.get("TTS_OUTPUT_DIR")
    if override:
        return Path(override)
    return Path(tempfile.gettempdir()) / "mcp-kokoro-tts"


def is_file(path: Path | str) -> bool:
    try:
        return Path(path).is_file()
    except OSError:
        return False


def check_espeak() -> bool:
    return shutil.which("espeak-ng") is not None


def list_voice_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        (path for path in directory.iterdir() if path.is_file() and VOICE_FILE_EXT.search(path.name)),
        key=lambda path: path.name.lower(),
    )


def list_voice_ids(model_dir: Path, package_voices: Path | None = None) -> list[str]:
    voices: dict[str, Path] = {}
    model_voices = model_dir / "voices"
    for path in list_voice_files(model_voices):
        voices[path.stem] = path
    if package_voices is not None:
        for path in list_voice_files(package_voices):
            voices[path.stem] = path
    return sorted(voices)


def resolve_default_voice(
    *,
    env_voice: str | None,
    package_voices: list[Path],
    model_voices: list[Path],
    fallback_voice_id: str = DEFAULT_VOICE_ID,
) -> str:
    """
    Default voice resolution order:
    1. TTS_VOICE env var (voice id or absolute .pt path)
    2. A voice in the package voices/ folder whose basename starts with "default"
    3. First .pt file in the package voices/ folder (alphabetical)
    4. The bundled Kokoro default voice id in the downloaded model
    """
    if env_voice:
        return env_voice

    pinned = next(
        (path for path in package_voices if path.stem.lower().startswith("default")),
        None,
    )
    if pinned is not None:
        return str(pinned)

    if package_voices:
        return str(package_voices[0])

    model_default = next(
        (path for path in model_voices if path.stem == fallback_voice_id),
        None,
    )
    if model_default is not None:
        return str(model_default)

    if model_voices:
        return str(model_voices[0])

    return fallback_voice_id


def resolve_voice_path(voice: str, *, model_dir: Path, package_voices: Path) -> Path:
    candidate = Path(voice)
    if candidate.is_absolute():
        if not is_file(candidate):
            raise FileNotFoundError(f"voice file not found: {candidate}")
        return candidate

    package_path = package_voices / f"{voice}.pt"
    if is_file(package_path):
        return package_path

    package_named = package_voices / voice
    if is_file(package_named):
        return package_named

    model_path = model_dir / "voices" / f"{voice}.pt"
    if is_file(model_path):
        return model_path

    raise FileNotFoundError(f"voice not found: {voice}")


def verify_model(model_dir: Path) -> list[str]:
    missing = [relative for relative in REQUIRED_MODEL_FILES if not (model_dir / relative).exists()]
    voices_dir = model_dir / "voices"
    if not voices_dir.is_dir() or not list_voice_files(voices_dir):
        missing.append("voices/*.pt")
    return missing


def model_is_provisioned(model_dir: Path) -> bool:
    return not verify_model(model_dir)


def download_model(
    *,
    model_dir: Path,
    cache_dir: Path,
    token: str | None,
    force: bool,
    log: Callable[[str], None] = print,
) -> Path:
    from huggingface_hub import snapshot_download

    model_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HUB_CACHE", str(cache_dir))

    log(f"mcp-kokoro-tts: downloading {REPO_ID} to {model_dir}")
    return Path(
        snapshot_download(
            repo_id=REPO_ID,
            local_dir=model_dir,
            cache_dir=cache_dir,
            token=token,
            force_download=force,
        )
    )


def spacy_english_model_wheel_url(spacy_version: str, *, name: str = SPACY_EN_MODEL) -> str:
    parts = spacy_version.split(".")
    if len(parts) < 2:
        raise ValueError(f"unrecognized spaCy version: {spacy_version}")
    tag = f"{name}-{parts[0]}.{parts[1]}.0"
    return (
        "https://github.com/explosion/spacy-models/releases/download/"
        f"{tag}/{tag}-py3-none-any.whl"
    )


def spacy_english_model_installed(name: str = SPACY_EN_MODEL) -> bool:
    import spacy.util

    return spacy.util.is_package(name)


def install_wheel_into_this_python(url: str) -> None:
    """Install a wheel into the running interpreter.

    uv tool / uvx environments do not include pip and are launched without
    VIRTUAL_ENV. spaCy's built-in download then runs `uv pip install` against
    the client's cwd and exits 2, killing the MCP process. Target this
    interpreter explicitly instead.
    """
    if importlib.util.find_spec("pip") is not None:
        command = [sys.executable, "-m", "pip", "install", url]
    else:
        uv = shutil.which("uv")
        if uv is None:
            raise RuntimeError(
                "Cannot install the spaCy English model: this environment has no pip, "
                "and uv is not on PATH."
            )
        command = [uv, "pip", "install", "--python", sys.executable, url]

    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"spaCy English model install failed: {detail}")


def ensure_spacy_english_model(*, log: Callable[[str], None], force: bool = False) -> None:
    if not force and spacy_english_model_installed():
        return

    import spacy

    url = spacy_english_model_wheel_url(spacy.__version__)
    log(f"mcp-kokoro-tts: installing spaCy model {SPACY_EN_MODEL} into {sys.prefix}")
    install_wheel_into_this_python(url)
    if not spacy_english_model_installed():
        raise RuntimeError(
            f"Installed {SPACY_EN_MODEL} but spaCy still cannot load it from {sys.prefix}"
        )


def ensure_provisioned(
    *,
    model_dir: Path | None = None,
    cache_dir: Path | None = None,
    token: str | None = None,
    force: bool = False,
    log: Callable[[str], None] | None = None,
) -> ModelPaths:
    resolved_model_dir = model_dir or default_model_dir()
    resolved_cache_dir = cache_dir or default_cache_dir()
    logger = log or (lambda message: print(message, file=sys.stderr))

    if not model_is_provisioned(resolved_model_dir) or force:
        download_model(
            model_dir=resolved_model_dir,
            cache_dir=resolved_cache_dir,
            token=token
            or os.environ.get("HF_TOKEN")
            or os.environ.get("HUGGINGFACE_HUB_TOKEN"),
            force=force,
            log=logger,
        )

    missing = verify_model(resolved_model_dir)
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"Kokoro model provision incomplete: {joined}")

    ensure_spacy_english_model(log=logger, force=force)

    resolved_config = resolved_model_dir / "config.json"
    resolved_weights = resolved_model_dir / "kokoro-v1_0.pth"
    return ModelPaths(
        model_dir=resolved_model_dir,
        config_path=resolved_config,
        weights_path=resolved_weights,
        voices_dir=resolved_model_dir / "voices",
    )


def find_in_path(command: str) -> str | None:
    return shutil.which(command)


def pick_player(file: str) -> tuple[str, list[str]] | None:
    path = str(Path(file))
    platform = sys.platform

    if platform == "darwin":
        if find_in_path("afplay"):
            return ("afplay", [path])
        return None

    if platform == "win32":
        escaped = path.replace("'", "''")
        command = (
            "Add-Type -AssemblyName System.Windows.Media; "
            f"$m = New-Object System.Windows.Media.MediaPlayer; "
            f"$m.Open([uri]'{escaped}'); $m.Play()"
        )
        return ("powershell", ["-NoProfile", "-NonInteractive", "-Command", command])

    if platform.startswith("linux"):
        ffplay = find_in_path("ffplay")
        if ffplay:
            return (ffplay, ["-nodisp", "-autoexit", "-loglevel", "quiet", path])
        paplay = find_in_path("paplay")
        if paplay:
            return (paplay, [path])
        aplay = find_in_path("aplay")
        if aplay and path.lower().endswith(".wav"):
            return (aplay, [path])
        return None

    return None


def spawn_and_settle(command: str, args: list[str], fail_fast_ms: int) -> Result:
    if os.environ.get("CI"):
        return Result(ok=True)

    try:
        process = subprocess.Popen(
            [command, *args],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except OSError as exc:
        return Result(ok=False, error=str(exc))

    try:
        process.wait(timeout=fail_fast_ms / 1000)
        if process.returncode == 0:
            return Result(ok=True)
        stderr = (process.stderr.read() if process.stderr else b"").decode("utf-8", "replace").strip()
        return Result(ok=False, error=stderr or f"command exited with code {process.returncode}")
    except subprocess.TimeoutExpired:
        return Result(ok=True)


def play_audio(file: Path) -> Result:
    if not is_file(file):
        return Result(ok=False, error="file not found (or not a regular file)")

    player = pick_player(str(file))
    if player is None:
        return Result(ok=False, error="no audio player found for this platform")
    command, args = player
    return spawn_and_settle(command, args, SOUND_FAIL_FAST_MS)


class SpeechEngine:
    def __init__(self, paths: ModelPaths, *, device: str = "cpu") -> None:
        from kokoro import KModel, KPipeline

        self.paths = paths
        self.device = device
        self._model = KModel(
            repo_id=REPO_ID,
            config=str(paths.config_path),
            model=str(paths.weights_path),
        ).to(device).eval()
        self._pipeline = KPipeline(
            lang_code=DEFAULT_LANG_CODE,
            repo_id=REPO_ID,
            model=self._model,
            device=device,
        )

    def synthesize(
        self,
        text: str,
        *,
        voice_path: Path,
        speed: float = 1.0,
        output_dir: Path,
    ) -> Path:
        import numpy as np
        import soundfile as sf

        cleaned = text.strip()
        if not cleaned:
            raise ValueError("text must not be empty")
        if len(cleaned) > TEXT_MAX_LEN:
            raise ValueError(f"text must be at most {TEXT_MAX_LEN} characters")

        output_dir.mkdir(parents=True, exist_ok=True)
        segments = list(self._pipeline(cleaned, voice=str(voice_path), speed=speed))
        if not segments:
            raise RuntimeError("no audio segments were generated")

        chunks: list = []
        for _, _, audio in segments:
            chunks.append(audio)

        merged = np.concatenate(chunks) if len(chunks) > 1 else chunks[0]
        output_path = output_dir / f"speech_{uuid.uuid4().hex}.wav"
        sf.write(output_path, merged, SAMPLE_RATE)
        return output_path


def speak_text(
    text: str,
    *,
    voice: str | None = None,
    speed: float = 1.0,
    model_paths: ModelPaths,
    engine: SpeechEngine | None = None,
    output_dir: Path | None = None,
    play: bool = True,
) -> SpeakResult:
    package_voices = list_voice_files(package_voices_dir())
    model_voices = list_voice_files(model_paths.voices_dir)
    selected_voice = resolve_default_voice(
        env_voice=voice or os.environ.get("TTS_VOICE"),
        package_voices=package_voices,
        model_voices=model_voices,
    )
    voice_path = resolve_voice_path(selected_voice, model_dir=model_paths.model_dir, package_voices=package_voices_dir())

    active_engine = engine or SpeechEngine(model_paths)
    output_path = active_engine.synthesize(
        text,
        voice_path=voice_path,
        speed=speed,
        output_dir=output_dir or default_output_dir(),
    )

    played = False
    play_error: str | None = None
    if play and os.environ.get("TTS_PLAY", "1") != "0":
        play_result = play_audio(output_path)
        played = play_result.ok
        play_error = play_result.error

    return SpeakResult(
        output_path=output_path,
        voice=voice_path.stem,
        segment_count=1,
        played=played,
        play_error=play_error,
    )


def format_voice_listing(model_paths: ModelPaths) -> str:
    package_voices = package_voices_dir()
    voice_ids = list_voice_ids(model_paths.model_dir, package_voices)
    default_voice = resolve_default_voice(
        env_voice=os.environ.get("TTS_VOICE"),
        package_voices=list_voice_files(package_voices),
        model_voices=list_voice_files(model_paths.voices_dir),
    )
    default_label = Path(default_voice).stem if default_voice else DEFAULT_VOICE_ID
    if os.environ.get("TTS_VOICE"):
        default_label += " (from TTS_VOICE)"

    lines = [
        f"Default voice: {default_label}",
        f"Model directory: {model_paths.model_dir}",
        f"Package voices in {package_voices}:",
    ]
    package_files = list_voice_files(package_voices)
    if package_files:
        lines.extend(f"  - {path}" for path in package_files)
    else:
        lines.append("  (none — pin one as voices/default-<name>.pt or set TTS_VOICE)")

    lines.append("Available voice ids:")
    if voice_ids:
        lines.extend(f"  - {voice_id}" for voice_id in voice_ids)
    else:
        lines.append("  (none — run mcp-kokoro-tts-provision)")

    if not check_espeak():
        lines.append("Note: espeak-ng not found. English still works; other languages may be limited.")

    return "\n".join(lines)
