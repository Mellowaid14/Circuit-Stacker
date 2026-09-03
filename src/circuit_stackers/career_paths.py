"""Portable career-path metadata and storage."""

from __future__ import annotations

import json
import re
from pathlib import Path
from uuid import uuid4

from .paths import user_data_dir


CAREER_PATHS_DIR = user_data_dir() / "career_paths"
DEFAULT_CAREER_PATH_ID = "default"


def _slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    return value or "career_path"


def default_career_path(game: str = "iRacing") -> dict[str, object]:
    normalized_game = "AMS2" if str(game).casefold() == "ams2" else "iRacing"
    return {
        "schema_version": 1,
        "path_id": DEFAULT_CAREER_PATH_ID,
        "title": "Default Career Path",
        "author": "Circuit Stackers",
        "description": "The built-in career progression from the current championship data.",
        "game": normalized_game,
        "source": "built-in",
        "championship_ids": [],
    }


def list_career_paths(game: str | None = None) -> list[dict[str, object]]:
    paths = [default_career_path(game or "iRacing")]
    try:
        files = sorted(CAREER_PATHS_DIR.glob("*.circuitstacker.json"))
    except OSError:
        files = []
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or not str(payload.get("title", "")).strip():
            continue
        if not str(payload.get("path_id", "")).strip():
            payload["path_id"] = f"path_{_slug(str(payload.get('title', path.stem)))}"
        if game and str(payload.get("game", "")).casefold() not in {"", str(game).casefold()}:
            continue
        paths.append(payload)
    return paths


def load_career_path(path_id: str, game: str = "iRacing") -> dict[str, object]:
    target = str(path_id).strip() or DEFAULT_CAREER_PATH_ID
    if target == DEFAULT_CAREER_PATH_ID:
        return default_career_path(game)
    return next((path for path in list_career_paths(game) if str(path.get("path_id", "")) == target), default_career_path(game))


def save_career_path(payload: dict[str, object]) -> Path:
    normalized = dict(payload)
    normalized.setdefault("schema_version", 1)
    if not str(normalized.get("path_id", "")).strip():
        normalized["path_id"] = f"path_{uuid4().hex[:10]}"
    normalized.setdefault("package_type", "career_path")
    title = str(normalized.get("title", "Career Path")).strip() or "Career Path"
    normalized["title"] = title
    CAREER_PATHS_DIR.mkdir(parents=True, exist_ok=True)
    path = CAREER_PATHS_DIR / f"{_slug(title)}.circuitstacker.json"
    path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
    return path


def delete_career_path(path_id: str) -> tuple[bool, str]:
    target = str(path_id).strip()
    if not target or target == DEFAULT_CAREER_PATH_ID:
        return False, "The built-in Default Career Path cannot be deleted."
    try:
        files = sorted(CAREER_PATHS_DIR.glob("*.circuitstacker.json"))
    except OSError as exc:
        return False, f"Could not find career paths: {exc}"
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and str(payload.get("path_id", "")).strip() == target:
            try:
                path.unlink()
            except OSError as exc:
                return False, f"Could not delete career path: {exc}"
            return True, "Career path deleted."
    return False, "Career path not found."


def import_career_path(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("package_type", "career_path") != "career_path":
        raise ValueError("This file is not a Circuit Stackers career path.")
    payload.setdefault("schema_version", 1)
    payload.setdefault("path_id", f"path_{uuid4().hex[:10]}")
    save_career_path(payload)
    return payload


def export_career_path(payload: dict[str, object], destination: Path) -> Path:
    normalized = dict(payload)
    normalized.setdefault("schema_version", 1)
    normalized["package_type"] = "career_path"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
    return destination
