import pytest

from mcp_kokoro_tts.server import DEFAULT_HTTP_PORT, transport_settings


def test_default_is_stdio():
    assert transport_settings([], {}) == ("stdio", "127.0.0.1", DEFAULT_HTTP_PORT)


def test_http_flag_and_port():
    assert transport_settings(["--http", "--port", "9001"], {}) == (
        "streamable-http",
        "127.0.0.1",
        9001,
    )


def test_env_selects_http():
    env = {"TTS_TRANSPORT": "http", "TTS_HTTP_PORT": "9100", "TTS_HTTP_HOST": "127.0.0.1"}
    assert transport_settings([], env) == ("streamable-http", "127.0.0.1", 9100)


def test_stdio_flag_overrides_env():
    assert transport_settings(["--stdio"], {"TTS_TRANSPORT": "http"})[0] == "stdio"


def test_rejects_unknown_transport():
    with pytest.raises(ValueError):
        transport_settings([], {"TTS_TRANSPORT": "carrier-pigeon"})
