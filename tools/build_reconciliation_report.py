"""Build a read-only reconciliation report for installed sim content and app data."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from circuit_stackers.ams2_content_scanner import discover_roots  # noqa: E402
from circuit_stackers.ams2_tracks_catalog import update_track_metadata  # noqa: E402
from circuit_stackers.iracing_content_scanner import compare_iracing_car_images  # noqa: E402
from circuit_stackers.settings_manager import game_directory  # noqa: E402


def _load_json(path: Path) -> dict[str, object]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


if __name__ == "__main__":
    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    ams2_roots = discover_roots(game_directory("AMS2"))
    track_report_path, track_source, track_failed = update_track_metadata(output_dir, ams2_roots.install)
    ams2_cars = _load_json(output_dir / "ams2_catalog_report.json")
    ams2_tracks = _load_json(track_report_path)
    iracing = compare_iracing_car_images(Path(r"C:\Program Files (x86)\iRacing"))
    review_keys = {
        item.get("relative_path")
        for key in ("missing_csv_entries", "missing_images")
        for item in iracing.get(key, [])
    }
    report = {
        "schema_version": 1,
        "generated_from": {"cars_csv": str(SRC_ROOT / "circuit_stackers" / "data" / "Cars.csv"), "tracks_csv": str(SRC_ROOT / "circuit_stackers" / "data" / "Tracks.csv")},
        "ams2": {
            "cars": {"source": ams2_cars.get("catalog_source", ams2_cars.get("source", "")), "safe_matches": ams2_cars.get("matched_count", 0), "review_count": ams2_cars.get("unmatched_count", 0), "items": [item for item in ams2_cars.get("matches", []) if not item.get("package_name")]},
            "tracks": {"source": track_source, "safe_matches": ams2_tracks.get("matched_count", 0), "review_count": ams2_tracks.get("unmatched_count", 0), "items": [item for item in ams2_tracks.get("matches", []) if not item.get("local_track")]},
        },
        "iracing": {"safe_matches": iracing.get("installed_count", 0) - len(review_keys), "review_count": len(review_keys), "missing_csv_entries": iracing.get("missing_csv_entries", []), "missing_images": iracing.get("missing_images", [])},
        "summary": {"track_source_failures": track_failed, "note": "This report is read-only. Review items must be approved before CSV changes are made."},
    }
    report_path = output_dir / "content_reconciliation_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {report_path}")
    print(json.dumps({"ams2_car_review": report["ams2"]["cars"]["review_count"], "ams2_track_review": report["ams2"]["tracks"]["review_count"], "iracing_review": report["iracing"]["review_count"]}, indent=2))
