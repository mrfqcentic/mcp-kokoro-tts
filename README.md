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

This package uses **PyPI Trusted Publishing** (OpenID Connect). You do **not** need a long-lived `PYPI_TOKEN` secret in GitHub.

### One-time PyPI setup

Because `mcp-kokoro-tts` may not exist on PyPI yet, register a **pending publisher** on your PyPI account:

1. Sign in at [pypi.org](https://pypi.org)
2. Open your account menu → **Publishing** (account-level, not a project page)
3. Add a **GitHub** trusted publisher with:

| Field | Value |
|---|---|
| PyPI project name | `mcp-kokoro-tts` |
| Owner | `mrfqcentic` |
| Repository name | `mcp-kokoro-tts` |
| Workflow name | `publish.yml` |
| Environment name | *(leave blank)* |

The project name must match `pyproject.toml` exactly. The first tagged release creates the PyPI project automatically.

Docs: [PyPI trusted publishers](https://docs.pypi.org/trusted-publishers/), [GitHub OIDC in PyPI](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-pypi)

### Release

1. Bump `version` in `pyproject.toml`
2. Commit and tag: `git tag v0.1.0 && git push origin v0.1.0`
3. GitHub Actions runs `publish.yml`:
   - `release` — test, build wheel/sdist
   - `pypi-publish` — OIDC → short-lived PyPI token → upload (no secrets)
   - `mcp-registry` — OIDC → MCP Registry publish (same as `mcp-notify`)

Optional hardening: create a GitHub **environment** named `pypi`, add it to the `pypi-publish` job, and set the same environment name in the PyPI trusted publisher form.

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
