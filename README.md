# mcp-kokoro-tts

<!-- mcp-name: io.github.mrfqcentic/mcp-kokoro-tts -->

Local Kokoro-82M text-to-speech MCP server. When your agent calls `speak`, it synthesizes speech and plays it on your machine so you can hear the harness talk.

Works with any MCP client: Claude Desktop, Claude Code, Cursor, VS Code, opencode, Cline, and more. One short config block, no API keys — synthesis runs locally with [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M).

On first start, the server downloads the model (~312 MB) into your local cache. Model weights are not bundled in the package.

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

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/). The first server start provisions the Kokoro model automatically.

To pre-download the model without starting the MCP server:

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

Synthesizes speech, writes a WAV file, and plays it locally.

| Param | Required | Description |
|---|---|---|
| `text` | yes | Text to speak (max 500 chars) |
| `voice` | no | Voice id (e.g. `af_heart`) or absolute path to a `.pt` voice file |
| `speed` | no | Playback speed multiplier (default `1.0`) |

### `list_voices`

Lists available Kokoro voices and the currently selected default.

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
| `HF_TOKEN` | Optional Hugging Face token for faster downloads |

## Platforms

| OS | Synthesis | Playback |
|---|---|---|
| macOS | yes | `afplay` |
| Linux | yes | `ffplay`, `paplay`, or `aplay` |
| Windows | yes | PowerShell `MediaPlayer` |

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
