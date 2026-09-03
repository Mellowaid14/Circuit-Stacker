"""Print a current AMS2 package/content report as JSON."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from circuit_stackers.ams2_content_scanner import scan_ams2_content  # noqa: E402
from circuit_stackers.settings_manager import game_directory  # noqa: E402


if __name__ == "__main__":
    report = scan_ams2_content(game_directory("AMS2"))
    print(json.dumps(report, indent=2, default=str))
