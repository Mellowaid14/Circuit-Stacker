from __future__ import annotations

import json
from typing import Any

from .paths import user_data_dir


MAPPINGS_PATH = user_data_dir() / "live_name_mappings.json"
LEGACY_AMS2_MAPPINGS_PATH = user_data_dir() / "ams2_name_mappings.json"


def load_ams2_player_name_mappings() -> dict[str, str]:
    return load_player_name_mappings("AMS2")


def save_ams2_player_name_mappings(mappings: dict[str, str]) -> None:
    save_player_name_mappings("AMS2", mappings)


def load_iracing_player_name_mappings() -> dict[str, str]:
    return load_player_name_mappings("iRacing")


def save_iracing_player_name_mappings(mappings: dict[str, str]) -> None:
    save_player_name_mappings("iRacing", mappings)


def load_player_name_mappings(game: str) -> dict[str, str]:
    if not MAPPINGS_PATH.exists():
        if _game_key(game) == "ams2":
            return _load_legacy_ams2_mappings()
        return {}
    try:
        payload = json.loads(MAPPINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    game_key = _game_key(game)
    mappings = payload.get(game_key, payload.get("player_screen_names", {} if game_key == "ams2" else {}))
    if not isinstance(mappings, dict):
        return {}
    return {
        str(app_name).strip(): str(screen_name).strip()
        for app_name, screen_name in mappings.items()
        if str(app_name).strip() and str(screen_name).strip()
    }


def _load_legacy_ams2_mappings() -> dict[str, str]:
    if not LEGACY_AMS2_MAPPINGS_PATH.exists():
        return {}
    try:
        payload = json.loads(LEGACY_AMS2_MAPPINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    mappings = payload.get("player_screen_names", {})
    if not isinstance(mappings, dict):
        return {}
    return {
        str(app_name).strip(): str(screen_name).strip()
        for app_name, screen_name in mappings.items()
        if str(app_name).strip() and str(screen_name).strip()
    }


def save_player_name_mappings(game: str, mappings: dict[str, str]) -> None:
    MAPPINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload = json.loads(MAPPINGS_PATH.read_text(encoding="utf-8")) if MAPPINGS_PATH.exists() else {}
    except (OSError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload[_game_key(game)] = {
            str(app_name).strip(): str(screen_name).strip()
            for app_name, screen_name in mappings.items()
            if str(app_name).strip() and str(screen_name).strip()
    }
    MAPPINGS_PATH.write_text(json.dumps(payload, indent=4), encoding="utf-8")


def _game_key(game: str) -> str:
    return "ams2" if str(game).strip().casefold() == "ams2" else "iracing"
