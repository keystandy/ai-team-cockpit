from __future__ import annotations

import argparse
import json
import sys

from .api import build_server
from .config import Settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI Team local control plane")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    settings = Settings.load()
    if args.host or args.port:
        settings = settings.__class__(
            **{
                **settings.__dict__,
                "host": args.host or settings.host,
                "port": args.port or settings.port,
            }
        )
    if args.check:
        print(
            json.dumps(
                {
                    "ok": True,
                    "host": settings.host,
                    "port": settings.port,
                    "database": str(settings.db_path),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    server = build_server(settings)
    print(f"AI Team control plane: http://{settings.host}:{settings.port}")
    print(f"Database: {settings.db_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

