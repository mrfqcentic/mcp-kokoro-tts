"""Local Kokoro-82M text-to-speech MCP server."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("mcp-kokoro-tts")
except PackageNotFoundError:
    __version__ = "0.0.0"
