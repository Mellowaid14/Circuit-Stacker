"""Fetch the current AMS2 class catalog and print a package match report."""

from __future__ import annotations

import sys
import argparse
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from circuit_stackers.ams2_catalog import update_metadata_files  # noqa: E402
from circuit_stackers.ams2_content_scanner import discover_roots  # noqa: E402
from circuit_stackers.settings_manager import game_directory  # noqa: E402


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "output" / "ams2_catalog_report.json",
        help="JSON report path (default: output/ams2_catalog_report.json)",
    )
    args = parser.parse_args()
    roots = discover_roots(game_directory("AMS2"))
    report_path, metadata_path, source, failed_count = update_metadata_files(roots.install, args.output.parent)
    print(f"Wrote {report_path}")
    print(f"Wrote {metadata_path}")
    print(f"Catalog source: {source} | Failed pages: {failed_count}")
