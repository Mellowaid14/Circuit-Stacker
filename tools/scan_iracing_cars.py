"""Scan installed iRacing car packages and report missing CSV/image mappings."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from circuit_stackers.iracing_content_scanner import compare_iracing_car_images  # noqa: E402


if __name__ == "__main__":
    report = compare_iracing_car_images(Path(r"C:\Program Files (x86)\iRacing"))
    print(json.dumps(report, indent=2))
