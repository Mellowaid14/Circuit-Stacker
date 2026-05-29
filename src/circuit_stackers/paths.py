from __future__ import annotations

import sys
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
APP_NAME = "Circuit Stackers"


def _configured_data_dir() -> Path | None:
    candidate_roots = []

    if getattr(sys, "frozen", False):
        candidate_roots.append(Path(sys.executable).resolve().parent)
    candidate_roots.append(PACKAGE_DIR.parent.parent)

    for root in candidate_roots:
        config_path = root / "data_root.txt"
        try:
            raw_value = config_path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not raw_value:
            continue
        configured = Path(raw_value).expanduser()
        configured.mkdir(parents=True, exist_ok=True)
        return configured
    return None


def user_data_dir() -> Path:
    configured = _configured_data_dir()
    if configured is not None:
        return configured

    base = Path.home() / "AppData" / "Local"
    if sys.platform == "win32":
        import os

        base = Path(os.environ.get("LOCALAPPDATA", base))
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def resource_path(*parts: str) -> Path:
    """Return a resource path that works in source and PyInstaller builds."""
    relative_path = Path(*parts)
    candidates = []

    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.extend(
            [
                Path(bundle_root) / relative_path,
                Path(bundle_root) / "circuit_stackers" / relative_path,
            ]
        )

    executable_root = Path(sys.executable).resolve().parent
    candidates.extend(
        [
            executable_root / relative_path,
            executable_root / "circuit_stackers" / relative_path,
            PACKAGE_DIR / relative_path,
        ]
    )

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return PACKAGE_DIR / relative_path
