"""Launch Automobilista 2 with its built-in livery-ID display enabled."""

from __future__ import annotations

import os


AMS2_STEAM_APP = "steam://run/1066890//-showLiveryIDs"


def main() -> int:
    if os.name != "nt":
        raise SystemExit("This launcher is intended for Windows/Steam.")
    os.startfile(AMS2_STEAM_APP)  # type: ignore[attr-defined]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
