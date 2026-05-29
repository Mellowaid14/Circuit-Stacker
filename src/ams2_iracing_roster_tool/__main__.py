from __future__ import annotations

from .app import launch_app


def main() -> int:
    launch_app()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
