"""Fetch AMS2 track/layout metadata from the Wiki and write a review report."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from circuit_stackers.ams2_content_scanner import discover_roots  # noqa: E402
from circuit_stackers.ams2_tracks_catalog import update_track_metadata  # noqa: E402
from circuit_stackers.settings_manager import game_directory  # noqa: E402


if __name__ == "__main__":
    output_dir = PROJECT_ROOT / "output"
    roots = discover_roots(game_directory("AMS2"))
    report_path, source, failed = update_track_metadata(output_dir, roots.install)
    print(f"Wrote {report_path}")
    print(f"Track catalog source: {source} | Failed pages: {failed}")
