from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from .json_storage import read_json_object, write_json_atomic
from .paths import user_data_dir

SAVES_DIR = user_data_dir() / "saves"
INVALID_SAVE_NAME_CHARS = set('<>:"/\\|?*')
RESERVED_WINDOWS_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


def _save_path(save_name: str) -> Path:
    return SAVES_DIR / f"{save_name}.json"


def validate_save_name(save_name: str) -> tuple[bool, str]:
    cleaned = str(save_name).strip()
    if not cleaned:
        return False, "Please enter a save name."
    if len(cleaned) > 120:
        return False, "Save names must be 120 characters or fewer."
    if cleaned in {".", ".."} or any(character in INVALID_SAVE_NAME_CHARS for character in cleaned):
        return False, "Save names cannot contain path or filename characters such as /, \\, :, *, or ?."
    if cleaned.endswith((".", " ")):
        return False, "Save names cannot end with a period or space."
    if cleaned.split(".", 1)[0].upper() in RESERVED_WINDOWS_NAMES:
        return False, "That save name is reserved by Windows."
    return True, ""


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
        payload = read_json_object(path) or {}
        db_name = Path(str(payload.get("world_db_name", "")).strip()).name
        if db_name:
            return SAVES_DIR / db_name
    return _legacy_world_db_path(save_name)


def create_save(save_name: str, data: dict[str, Any]) -> tuple[bool, str]:
    """Create a new save file."""
    valid, validation_message = validate_save_name(save_name)
    if not valid:
        return False, validation_message
    SAVES_DIR.mkdir(parents=True, exist_ok=True)
    path = _save_path(save_name)

    if path.exists():
        return False, "A save with that name already exists."

    # Give each newly created save a DB identity instead of reusing a
    # name-derived world file that may be left behind by an older career.
    payload = {"save_name": save_name, "world_db_name": _new_world_db_name(save_name), **data}
    write_json_atomic(path, payload)
    return True, "Save created!"


def load_save(save_name: str) -> dict[str, Any] | None:
    """Load a save file by name."""
    path = _save_path(save_name)
    if not path.exists():
        return None

    payload = read_json_object(path)
    if payload is None:
        return None
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

    existing_payload = read_json_object(path)
    if existing_payload is None:
        return False
    payload = {**existing_payload, "save_name": save_name, **data}
    if "game" not in payload:
        payload["game"] = "iRacing"
    write_json_atomic(path, payload)
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
