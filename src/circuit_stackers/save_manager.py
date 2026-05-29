from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from .paths import user_data_dir

SAVES_DIR = user_data_dir() / "saves"


def _save_path(save_name: str) -> Path:
    return SAVES_DIR / f"{save_name}.json"


def _legacy_world_db_path(save_name: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", save_name.strip()) or "career"
    return SAVES_DIR / f"{safe}_world.db"


def _new_world_db_name(save_name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", save_name.strip()) or "career"
    return f"{safe}_{uuid4().hex[:12]}_world.db"


def world_db_path(save_name: str) -> Path:
    """Return the world DB owned by this save, with legacy fallback."""
    path = _save_path(save_name)
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        db_name = Path(str(payload.get("world_db_name", "")).strip()).name
        if db_name:
            return SAVES_DIR / db_name
    return _legacy_world_db_path(save_name)


def create_save(save_name: str, data: dict[str, Any]) -> tuple[bool, str]:
    """Create a new save file."""
    SAVES_DIR.mkdir(parents=True, exist_ok=True)
    path = _save_path(save_name)

    if path.exists():
        return False, "A save with that name already exists."

    # Give each newly created save a DB identity instead of reusing a
    # name-derived world file that may be left behind by an older career.
    payload = {"save_name": save_name, "world_db_name": _new_world_db_name(save_name), **data}
    path.write_text(json.dumps(payload, indent=4), encoding="utf-8")
    return True, "Save created!"


def load_save(save_name: str) -> dict[str, Any] | None:
    """Load a save file by name."""
    path = _save_path(save_name)
    if not path.exists():
        return None

    payload = json.loads(path.read_text(encoding="utf-8"))
    if "game" not in payload:
        payload["game"] = "iRacing"
    return payload


def list_saves() -> list[str]:
    """Return a sorted list of save names."""
    if not SAVES_DIR.exists():
        return []

    return sorted(path.stem for path in SAVES_DIR.glob("*.json"))


def update_save(save_name: str, data: dict[str, Any]) -> bool:
    """Overwrite an existing save with new data."""
    path = _save_path(save_name)
    if not path.exists():
        return False

    try:
        existing_payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        existing_payload = {}
    payload = {**existing_payload, "save_name": save_name, **data}
    if "game" not in payload:
        payload["game"] = "iRacing"
    path.write_text(json.dumps(payload, indent=4), encoding="utf-8")
    return True


def delete_save(save_name: str) -> bool:
    """Delete a save file."""
    path = _save_path(save_name)
    if not path.exists():
        return False

    world_path = world_db_path(save_name)
    path.unlink()
    if world_path.exists():
        world_path.unlink()
    return True
