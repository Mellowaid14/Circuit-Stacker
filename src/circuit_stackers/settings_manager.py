from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .paths import resource_path, user_data_dir

SETTINGS_PATH = user_data_dir() / "settings.json"
DEFAULT_IRACING_DIR = ""
DEFAULT_AMS2_DIR = ""

_CARS_CACHE: list[dict[str, str]] | None = None
_TRACKS_CACHE: list[dict[str, str]] | None = None


def _load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as file_obj:
        return list(csv.DictReader(file_obj))


def refresh_asset_caches() -> None:
    global _CARS_CACHE, _TRACKS_CACHE
    _CARS_CACHE = None
    _TRACKS_CACHE = None


def list_all_cars() -> list[dict[str, str]]:
    global _CARS_CACHE
    if _CARS_CACHE is None:
        _CARS_CACHE = _load_csv(resource_path("data", "Cars.csv"))
    return [dict(row) for row in _CARS_CACHE]


def list_all_tracks() -> list[dict[str, str]]:
    global _TRACKS_CACHE
    if _TRACKS_CACHE is None:
        _TRACKS_CACHE = _load_csv(resource_path("data", "Tracks.csv"))
    return [dict(row) for row in _TRACKS_CACHE]


def default_owned_car_ids() -> list[str]:
    return sorted(str(row["id"]).strip() for row in list_all_cars() if row.get("Owned", "").strip().casefold() == "yes")


def default_owned_track_ids() -> list[str]:
    return sorted(
        {
            str(row.get("Track", "")).strip()
            for row in list_all_tracks()
            if row.get("Owned", "").strip().casefold() == "yes" and str(row.get("Track", "")).strip()
        }
    )


def _game_prefix(game: str) -> str:
    return "ams2" if str(game).strip().casefold() == "ams2" else "iracing"


def _ams2_base_car_ids() -> set[str]:
    return {
        str(row.get("id", "")).strip()
        for row in list_all_cars()
        if str(row.get("Game", "")).strip().casefold() == "ams2"
        and str(row.get("id", "")).strip()
        and str(row.get("DLC", "")).strip().casefold() in {"", "base game"}
    }


def _ams2_base_track_names() -> set[str]:
    return {
        str(row.get("Track", "")).strip()
        for row in list_all_tracks()
        if str(row.get("Game", "")).strip().casefold() == "ams2"
        and str(row.get("Track", "")).strip()
        and str(row.get("DLC", "")).strip().casefold() in {"", "base game"}
    }


def default_settings() -> dict[str, Any]:
    return {
        "iracing_directory": DEFAULT_IRACING_DIR,
        "owned_car_ids": default_owned_car_ids(),
        "owned_track_names": default_owned_track_ids(),
        "iracing_owned_car_ids": default_owned_car_ids(),
        "iracing_owned_track_names": default_owned_track_ids(),
        "ams2_directory": DEFAULT_AMS2_DIR,
        "ams2_owned_car_ids": [],
        "ams2_owned_track_names": [],
        "custom_overlay_enabled": False,
        "custom_overlay_defaulted_off": True,
        "ams2_leaderboard_overlay_geometry": "520x520+80+80",
        "check_for_updates_on_launch": True,
        "menu_music_volume": 0.45,
    }


def load_settings() -> dict[str, Any]:
    defaults = default_settings()
    if not SETTINGS_PATH.exists():
        return defaults

    saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    return {
        "iracing_directory": saved.get("iracing_directory", defaults["iracing_directory"]),
        "owned_car_ids": sorted(saved.get("owned_car_ids", defaults["owned_car_ids"])),
        "owned_track_names": sorted(
            saved.get("owned_track_names", saved.get("owned_track_ids", defaults["owned_track_names"]))
        ),
        "iracing_owned_car_ids": sorted(
            saved.get("iracing_owned_car_ids", saved.get("owned_car_ids", defaults["iracing_owned_car_ids"]))
        ),
        "iracing_owned_track_names": sorted(
            saved.get(
                "iracing_owned_track_names",
                saved.get("owned_track_names", saved.get("owned_track_ids", defaults["iracing_owned_track_names"])),
            )
        ),
        "ams2_directory": saved.get("ams2_directory", defaults["ams2_directory"]),
        "ams2_owned_car_ids": sorted(saved.get("ams2_owned_car_ids", defaults["ams2_owned_car_ids"])),
        "ams2_owned_track_names": sorted(
            saved.get("ams2_owned_track_names", saved.get("ams2_owned_track_ids", defaults["ams2_owned_track_names"]))
        ),
        "custom_overlay_enabled": (
            bool(saved.get("custom_overlay_enabled", defaults["custom_overlay_enabled"]))
            if bool(saved.get("custom_overlay_defaulted_off", False))
            else False
        ),
        "custom_overlay_defaulted_off": True,
        "ams2_leaderboard_overlay_geometry": str(
            saved.get("ams2_leaderboard_overlay_geometry", defaults["ams2_leaderboard_overlay_geometry"])
        ),
        "check_for_updates_on_launch": bool(
            saved.get("check_for_updates_on_launch", defaults["check_for_updates_on_launch"])
        ),
        "menu_music_volume": _clamp_float(saved.get("menu_music_volume", defaults["menu_music_volume"]), 0.0, 1.0),
    }


def save_settings(settings: dict[str, Any]) -> None:
    payload = {
        "iracing_directory": settings.get("iracing_directory", DEFAULT_IRACING_DIR),
        "owned_car_ids": sorted(str(value) for value in settings.get("owned_car_ids", [])),
        "owned_track_names": sorted(str(value) for value in settings.get("owned_track_names", [])),
        "iracing_owned_car_ids": sorted(str(value) for value in settings.get("iracing_owned_car_ids", settings.get("owned_car_ids", []))),
        "iracing_owned_track_names": sorted(
            str(value) for value in settings.get("iracing_owned_track_names", settings.get("owned_track_names", []))
        ),
        "ams2_directory": settings.get("ams2_directory", DEFAULT_AMS2_DIR),
        "ams2_owned_car_ids": sorted(str(value) for value in settings.get("ams2_owned_car_ids", [])),
        "ams2_owned_track_names": sorted(str(value) for value in settings.get("ams2_owned_track_names", [])),
        "custom_overlay_enabled": bool(settings.get("custom_overlay_enabled", False)),
        "custom_overlay_defaulted_off": True,
        "ams2_leaderboard_overlay_geometry": str(settings.get("ams2_leaderboard_overlay_geometry", "520x520+80+80")),
        "check_for_updates_on_launch": bool(settings.get("check_for_updates_on_launch", True)),
        "menu_music_volume": _clamp_float(settings.get("menu_music_volume", 0.45), 0.0, 1.0),
    }
    SETTINGS_PATH.write_text(json.dumps(payload, indent=4), encoding="utf-8")


def _clamp_float(value: Any, minimum: float, maximum: float) -> float:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return minimum
    return max(minimum, min(maximum, numeric_value))


def update_custom_overlay_enabled(enabled: bool) -> None:
    settings = load_settings()
    settings["custom_overlay_enabled"] = bool(enabled)
    save_settings(settings)


def update_ams2_leaderboard_overlay_geometry(geometry: str) -> None:
    settings = load_settings()
    settings["ams2_leaderboard_overlay_geometry"] = str(geometry).strip() or "520x520+80+80"
    save_settings(settings)


def update_check_for_updates_on_launch(enabled: bool) -> None:
    settings = load_settings()
    settings["check_for_updates_on_launch"] = bool(enabled)
    save_settings(settings)


def update_menu_music_volume(volume: float) -> None:
    settings = load_settings()
    settings["menu_music_volume"] = _clamp_float(volume, 0.0, 1.0)
    save_settings(settings)


def game_directory(game: str) -> str:
    settings = load_settings()
    return str(settings.get(f"{_game_prefix(game)}_directory", "")).strip()


def update_game_directory(game: str, path: str) -> None:
    settings = load_settings()
    settings[f"{_game_prefix(game)}_directory"] = path.strip()
    save_settings(settings)


def update_iracing_directory(path: str) -> None:
    update_game_directory("iRacing", path)


def update_ams2_directory(path: str) -> None:
    update_game_directory("AMS2", path)


def owned_asset_lists(game: str) -> tuple[list[str], list[str]]:
    settings = load_settings()
    prefix = _game_prefix(game)
    return (
        sorted(str(value) for value in settings.get(f"{prefix}_owned_car_ids", [])),
        sorted(str(value) for value in settings.get(f"{prefix}_owned_track_names", [])),
    )


def update_owned_assets_for_game(game: str, car_ids: list[str], track_names: list[str]) -> None:
    settings = load_settings()
    prefix = _game_prefix(game)
    settings[f"{prefix}_owned_car_ids"] = sorted(str(value) for value in car_ids)
    settings[f"{prefix}_owned_track_names"] = sorted(str(value) for value in track_names)
    save_settings(settings)


def reset_owned_assets_to_default_for_game(game: str) -> None:
    settings = load_settings()
    prefix = _game_prefix(game)
    if prefix == "ams2":
        settings[f"{prefix}_owned_car_ids"] = []
        settings[f"{prefix}_owned_track_names"] = []
    else:
        settings[f"{prefix}_owned_car_ids"] = default_owned_car_ids()
        settings[f"{prefix}_owned_track_names"] = default_owned_track_ids()
    save_settings(settings)


def update_owned_assets(car_ids: list[str], track_names: list[str]) -> None:
    update_owned_assets_for_game("iRacing", car_ids, track_names)


def reset_owned_assets_to_default() -> None:
    reset_owned_assets_to_default_for_game("iRacing")


def owned_car_id_set() -> set[str]:
    return owned_car_id_set_for_game("iRacing")


def owned_car_id_set_for_game(game: str) -> set[str]:
    prefix = _game_prefix(game)
    settings = load_settings()
    if prefix == "iracing":
        return set(settings.get("iracing_owned_car_ids", settings.get("owned_car_ids", [])))
    return set(settings.get(f"{prefix}_owned_car_ids", [])) | _ams2_base_car_ids()


def owned_track_id_set() -> set[str]:
    return owned_track_id_set_for_game("iRacing")


def owned_track_id_set_for_game(game: str) -> set[str]:
    prefix = _game_prefix(game)
    settings = load_settings()
    if prefix == "iracing":
        return set(settings.get("iracing_owned_track_names", settings.get("owned_track_names", [])))
    return set(settings.get(f"{prefix}_owned_track_names", [])) | _ams2_base_track_names()
