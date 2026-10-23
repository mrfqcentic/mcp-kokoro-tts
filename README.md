# mcp-kokoro-tts

<!-- mcp-name: io.github.mrfqcentic/mcp-kokoro-tts -->

Local Kokoro-82M text-to-speech MCP server. When your agent calls `speak`, it synthesizes speech and plays it on your machine so you can hear the harness talk.

Works with any MCP client: Claude Desktop, Claude Code, Cursor, VS Code, opencode, Cline, and more. One short config block, no API keys — synthesis runs locally with [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M).

On first start, the server provisions two things that are not on PyPI: the Kokoro-82M weights (~312 MB) into a local cache, and spaCy's English model (`en_core_web_sm`) into the same Python environment the server is running in. That second install is required because Kokoro's G2P pipeline loads spaCy, and a `uvx` / `uv tool` environment will not have the model unless this package puts it there.

## Install

Add to your client's MCP config:

```json
{
  "mcpServers": {
    "mcp-kokoro-tts": {
      "command": "uvx",
      "args": ["mcp-kokoro-tts"]
    }
  }
}
```

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/). The first server start provisions Kokoro weights and the spaCy English model automatically.

To pre-download both without starting the MCP server:

```bash
uvx mcp-kokoro-tts-provision
```

## Make the agent call it

Add one line to your `AGENTS.md` / `CLAUDE.md` / system prompt:

```
When the user wants to hear something spoken aloud, call the `speak` tool with clear, natural text.
```

## Tools

### `speak`

Synthesizes speech, writes a WAV file, and plays it locally. Playback goes through a
single queue: the call returns as soon as its audio is queued, and utterances play back
to back in call order instead of overlapping.

| Param | Required | Description |
|---|---|---|
| `text` | yes | Text to speak (max 500 chars) |
| `voice` | no | Voice id (e.g. `af_heart`) or absolute path to a `.pt` voice file |
| `speed` | no | Playback speed multiplier (default `1.0`) |

### `list_voices`

Lists available Kokoro voices and the currently selected default.

### `stop`

Cuts the utterance playing right now and drops everything queued behind it.
Same thing the hotkey below does, for clients that cannot press keys.

### `settings`

Returns the local settings page URL, the current stop hotkey, and whether the
keyboard listener is armed.

## Stop hotkey (barge-in)

Hold **Ctrl + Shift** and playback stops immediately: the current sentence is
cut and every queued utterance is discarded, so you can talk over the agent.

Change the chord on the local settings page the server prints at startup —
`http://127.0.0.1:8765/` by default — where you press the new combination and
save. It is written to `~/.config/mcp-kokoro-tts/hotkey.json` and picked up
without a restart.

A global keyboard listener needs **Input Monitoring** permission on macOS: the
server asks for it on startup, so the app running it shows up under System
Settings → Privacy & Security → Input Monitoring — switch it on and restart.
Without it the hotkey reports `needs_input_monitoring`; the `stop` tool and the
page's "Stop audio now" button keep working.

## Choosing your voice

Resolution order:

1. `TTS_VOICE` env var — voice id or absolute `.pt` path
2. A file in the package `voices/` folder whose name starts with `default`
3. First `.pt` file in `voices/` (alphabetical)
4. The model's bundled `af_heart` voice

```json
{
  "mcpServers": {
    "mcp-kokoro-tts": {
      "command": "uvx",
      "args": ["mcp-kokoro-tts"],
      "env": {
        "TTS_VOICE": "af_heart"
      }
    }
  }
}
```

## Environment variables

| Variable | Description |
|---|---|
| `TTS_VOICE` | Default voice id or absolute `.pt` path |
| `TTS_MODEL_DIR` | Override model cache directory |
| `TTS_HF_CACHE_DIR` | Override Hugging Face hub cache directory |
| `TTS_OUTPUT_DIR` | Directory for generated WAV files |
| `TTS_PLAY` | Set to `0` to synthesize without local playback |
| `TTS_CONFIG_DIR` | Directory holding `hotkey.json` (default `~/.config/mcp-kokoro-tts`) |
| `TTS_WEB_PORT` | Port for the local settings page (default `8765`) |
| `HF_TOKEN` | Optional Hugging Face token for faster downloads |

## Platforms

| OS | Synthesis | Playback | Stop hotkey |
|---|---|---|---|
| macOS | yes | `afplay` | yes (Quartz tap, needs Input Monitoring) |
| Linux | yes | `ffplay`, `paplay`, or `aplay` | no |
| Windows | yes | PowerShell `MediaPlayer` | no |

`espeak-ng` is optional. English works without it; install it for better out-of-vocabulary coverage and some non-English languages.

## Publishing

Tagging a version runs GitHub Actions `publish.yml`, which uploads to **PyPI** then the **MCP Registry**.

Publishing to PyPI uses the repo secret `PYPI_TOKEN` (a PyPI API token). GitHub trusted publishing can also be configured on the PyPI project; this workflow authenticates with the token so a first release does not depend on pending-publisher matching.

### Release

1. Bump `version` in `pyproject.toml` (and `server.json` if you are not tagging yet)
2. Commit and tag: `git tag v0.1.2 && git push origin v0.1.2`
3. GitHub Actions runs `publish.yml`:
   - `release` — typecheck, test, build wheel/sdist
   - `pypi-publish` — upload to PyPI with `PYPI_TOKEN`
   - `mcp-registry` — OIDC → MCP Registry (after PyPI succeeds)

## Development

```bash
cd mcps-tts
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pyright
pytest
python -m mcp_kokoro_tts
```

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE). Kokoro-82M model weights are downloaded separately under their Apache-2.0 license.
