from __future__ import annotations

import sys

from mcp_kokoro_tts.lib import ensure_provisioned
from mcp_kokoro_tts.server import run


def _log(message: str) -> None:
    print(message, file=sys.stderr)


def provision_main() -> None:
    try:
        ensure_provisioned(log=_log)
    except Exception as exc:  # noqa: BLE001 - CLI entrypoint
        print(f"mcp-kokoro-tts: provision failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    print("mcp-kokoro-tts: model provisioned", file=sys.stderr)


def main() -> None:
    try:
        run()
    except KeyboardInterrupt:
        raise SystemExit(0) from None
    except Exception as exc:  # noqa: BLE001 - CLI entrypoint
        print(f"mcp-kokoro-tts: fatal error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
