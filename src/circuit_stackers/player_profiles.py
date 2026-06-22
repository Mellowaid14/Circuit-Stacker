from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .json_storage import read_json_object, write_json_atomic
from .paths import user_data_dir
from .settings_manager import (
    default_owned_car_ids,
    default_owned_track_ids,
    legacy_cross_game_iracing_track_defaults,
    list_all_cars,
    list_all_tracks,
    load_settings,
)


PROFILES_PATH = user_data_dir() / "player_profiles.json"
PROFILES_SCHEMA_VERSION = 2
PROFILE_EXPORT_FORMAT = "circuit_stacker_player_profile"
PROFILE_EXPORT_VERSION = 1


def _clean_values(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _ownership(car_ids: Any = None, track_names: Any = None) -> dict[str, list[str]]:
    return {
        "car_ids": _clean_values(car_ids),
        "track_names": _clean_values(track_names),
    }


def _legacy_default_profile() -> dict[str, Any]:
    settings = load_settings()
    return {
        "id": uuid4().hex,
        "name": "Default Player",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "ownership": {
            "iracing": _ownership(
                settings.get("iracing_owned_car_ids", settings.get("owned_car_ids", default_owned_car_ids())),
                settings.get(
                    "iracing_owned_track_names",
                    settings.get("owned_track_names", default_owned_track_ids()),
                ),
            ),
            "ams2": _ownership(
                settings.get("ams2_owned_car_ids", []),
                settings.get("ams2_owned_track_names", []),
            ),
        },
    }


def _normalize_profile(raw: dict[str, Any]) -> dict[str, Any]:
    ownership = raw.get("ownership") if isinstance(raw.get("ownership"), dict) else {}
    return {
        "id": str(raw.get("id", "")).strip() or uuid4().hex,
        "name": str(raw.get("name", "")).strip() or "Player",
        "created_at": str(raw.get("created_at", "")).strip() or datetime.now().isoformat(timespec="seconds"),
        "ownership": {
            "iracing": _ownership(**_ownership_kwargs(ownership.get("iracing"))),
            "ams2": _ownership(**_ownership_kwargs(ownership.get("ams2"))),
        },
    }


def _ownership_kwargs(raw: Any) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    return {
        "car_ids": data.get("car_ids", []),
        "track_names": data.get("track_names", []),
    }


def _write_profiles(profiles: list[dict[str, Any]], default_profile_id: str) -> None:
    PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": PROFILES_SCHEMA_VERSION,
        "default_profile_id": default_profile_id,
        "profiles": profiles,
    }
    write_json_atomic(PROFILES_PATH, payload)


def _load_payload() -> dict[str, Any]:
    if not PROFILES_PATH.exists():
        profile = _legacy_default_profile()
        _write_profiles([profile], profile["id"])
        return {
            "schema_version": PROFILES_SCHEMA_VERSION,
            "default_profile_id": profile["id"],
            "profiles": [profile],
        }

    raw = read_json_object(PROFILES_PATH) or {}
    profiles = [
        _normalize_profile(profile)
        for profile in raw.get("profiles", [])
        if isinstance(profile, dict)
    ]
    if not profiles:
        profiles = [_legacy_default_profile()]
    default_id = str(raw.get("default_profile_id", "")).strip()
    if default_id not in {profile["id"] for profile in profiles}:
        default_id = profiles[0]["id"]
    try:
        schema_version = int(raw.get("schema_version", 1) or 1)
    except (TypeError, ValueError):
        schema_version = 1
    if schema_version < PROFILES_SCHEMA_VERSION:
        erroneous_defaults = legacy_cross_game_iracing_track_defaults()
        for profile in profiles:
            if profile["id"] != default_id:
                continue
            tracks = profile["ownership"]["iracing"]["track_names"]
            profile["ownership"]["iracing"]["track_names"] = [
                track for track in tracks if track not in erroneous_defaults
            ]
    normalized = {
        "schema_version": PROFILES_SCHEMA_VERSION,
        "default_profile_id": default_id,
        "profiles": profiles,
    }
    if (
        raw.get("schema_version") != PROFILES_SCHEMA_VERSION
        or raw.get("default_profile_id") != default_id
        or raw.get("profiles") != profiles
    ):
        _write_profiles(profiles, default_id)
    return normalized


def list_player_profiles() -> list[dict[str, Any]]:
    payload = _load_payload()
    return [dict(profile) for profile in payload["profiles"]]


def default_profile_id() -> str:
    return str(_load_payload()["default_profile_id"])


def get_player_profile(profile_id: str) -> dict[str, Any] | None:
    target = str(profile_id).strip()
    return next((profile for profile in list_player_profiles() if profile["id"] == target), None)


def create_player_profile(name: str) -> tuple[bool, str, dict[str, Any] | None]:
    cleaned = str(name).strip()
    if not cleaned:
        return False, "Enter a profile name.", None
    payload = _load_payload()
    if any(profile["name"].casefold() == cleaned.casefold() for profile in payload["profiles"]):
        return False, "A profile with that name already exists.", None
    profile = {
        "id": uuid4().hex,
        "name": cleaned,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "ownership": {
            "iracing": _ownership(default_owned_car_ids(), default_owned_track_ids()),
            "ams2": _ownership(),
        },
    }
    payload["profiles"].append(profile)
    _write_profiles(payload["profiles"], payload["default_profile_id"])
    return True, "Profile created.", profile


def export_player_profile(profile_id: str, path: Path) -> tuple[bool, str]:
    profile = get_player_profile(profile_id)
    if profile is None:
        return False, "Profile not found."
    export_payload = {
        "format": PROFILE_EXPORT_FORMAT,
        "version": PROFILE_EXPORT_VERSION,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "profile": {
            "name": profile["name"],
            "ownership": {
                "iracing": _ownership(**_ownership_kwargs(profile.get("ownership", {}).get("iracing"))),
                "ams2": _ownership(**_ownership_kwargs(profile.get("ownership", {}).get("ams2"))),
            },
        },
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(path, export_payload)
    except OSError as exc:
        return False, f"Could not export profile: {exc}"
    return True, f"Profile exported to {path.name}."


def import_player_profile(path: Path) -> tuple[bool, str, dict[str, Any] | None]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return False, "Profile file was not found.", None
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"Could not read profile file: {exc}", None
    if not isinstance(raw, dict) or raw.get("format") != PROFILE_EXPORT_FORMAT:
        return False, "This is not a Circuit Stacker player profile file.", None
    try:
        version = int(raw.get("version", 0) or 0)
    except (TypeError, ValueError):
        version = 0
    if version < 1 or version > PROFILE_EXPORT_VERSION:
        return False, "This profile file version is not supported by this build.", None
    imported = raw.get("profile")
    if not isinstance(imported, dict):
        return False, "The profile file does not contain profile data.", None
    source_name = str(imported.get("name", "")).strip()
    if not source_name:
        return False, "The imported profile does not have a name.", None

    payload = _load_payload()
    existing_names = {profile["name"].casefold() for profile in payload["profiles"]}
    imported_name = source_name
    suffix = 1
    while imported_name.casefold() in existing_names:
        suffix += 1
        label = "Imported" if suffix == 2 else f"Imported {suffix - 1}"
        imported_name = f"{source_name} ({label})"

    ownership = imported.get("ownership") if isinstance(imported.get("ownership"), dict) else {}
    profile = {
        "id": uuid4().hex,
        "name": imported_name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "ownership": {
            "iracing": _ownership(**_ownership_kwargs(ownership.get("iracing"))),
            "ams2": _ownership(**_ownership_kwargs(ownership.get("ams2"))),
        },
    }
    payload["profiles"].append(profile)
    _write_profiles(payload["profiles"], payload["default_profile_id"])
    return True, f"Profile imported as {imported_name}.", profile


def rename_player_profile(profile_id: str, name: str) -> tuple[bool, str]:
    cleaned = str(name).strip()
    if not cleaned:
        return False, "Enter a profile name."
    payload = _load_payload()
    if any(
        profile["id"] != profile_id and profile["name"].casefold() == cleaned.casefold()
        for profile in payload["profiles"]
    ):
        return False, "A profile with that name already exists."
    for profile in payload["profiles"]:
        if profile["id"] == profile_id:
            profile["name"] = cleaned
            _write_profiles(payload["profiles"], payload["default_profile_id"])
            return True, "Profile renamed."
    return False, "Profile not found."


def delete_player_profile(profile_id: str) -> tuple[bool, str]:
    payload = _load_payload()
    if profile_id == payload["default_profile_id"]:
        return False, "The default profile cannot be deleted."
    from .save_manager import list_saves, load_save

    for save_name in list_saves():
        save_data = load_save(save_name) or {}
        if profile_id in {str(value).strip() for value in save_data.get("player_profile_ids", [])}:
            return False, f"This profile is being used by the career '{save_name}'."
    remaining = [profile for profile in payload["profiles"] if profile["id"] != profile_id]
    if len(remaining) == len(payload["profiles"]):
        return False, "Profile not found."
    _write_profiles(remaining, payload["default_profile_id"])
    return True, "Profile deleted."


def profile_owned_assets(profile_id: str, game: str) -> tuple[list[str], list[str]]:
    profile = get_player_profile(profile_id)
    if profile is None:
        return [], []
    game_key = "ams2" if str(game).strip().casefold() == "ams2" else "iracing"
    ownership = profile.get("ownership", {}).get(game_key, {})
    return _clean_values(ownership.get("car_ids", [])), _clean_values(ownership.get("track_names", []))


def update_profile_owned_assets(
    profile_id: str,
    game: str,
    car_ids: list[str],
    track_names: list[str],
) -> bool:
    payload = _load_payload()
    game_key = "ams2" if str(game).strip().casefold() == "ams2" else "iracing"
    for profile in payload["profiles"]:
        if profile["id"] != profile_id:
            continue
        profile["ownership"][game_key] = _ownership(car_ids, track_names)
        _write_profiles(payload["profiles"], payload["default_profile_id"])
        return True
    return False


def reset_profile_owned_assets(profile_id: str, game: str) -> bool:
    if str(game).strip().casefold() == "ams2":
        return update_profile_owned_assets(profile_id, game, [], [])
    return update_profile_owned_assets(profile_id, game, default_owned_car_ids(), default_owned_track_ids())


def shared_owned_assets(profile_ids: list[str], game: str) -> tuple[list[str], list[str]]:
    profiles = {profile["id"]: profile for profile in list_player_profiles()}
    game_key = "ams2" if str(game).strip().casefold() == "ams2" else "iracing"
    selected: list[tuple[list[str], list[str]]] = []
    for profile_id in profile_ids:
        profile = profiles.get(profile_id)
        if profile is None:
            continue
        ownership = profile.get("ownership", {}).get(game_key, {})
        selected.append(
            (_clean_values(ownership.get("car_ids", [])), _clean_values(ownership.get("track_names", [])))
        )
    if not selected:
        return [], []
    shared_cars = set(selected[0][0])
    shared_tracks = set(selected[0][1])
    for car_ids, track_names in selected[1:]:
        shared_cars.intersection_update(car_ids)
        shared_tracks.intersection_update(track_names)
    normalized_game = str(game).strip().casefold()
    valid_car_ids = {
        str(row.get("id", "")).strip()
        for row in list_all_cars()
        if str(row.get("Game", "")).strip().casefold() in {"", normalized_game}
    }
    valid_track_names = {
        str(row.get("Track", "")).strip()
        for row in list_all_tracks()
        if str(row.get("Game", "")).strip().casefold() in {"", normalized_game}
    }
    shared_cars.intersection_update(valid_car_ids)
    shared_tracks.intersection_update(valid_track_names)
    return sorted(shared_cars), sorted(shared_tracks)


def effective_shared_owned_assets(profile_ids: list[str], game: str) -> tuple[list[str], list[str]]:
    car_ids, track_names = shared_owned_assets(profile_ids, game)
    if str(game).strip().casefold() != "ams2":
        return car_ids, track_names
    cars = set(car_ids)
    tracks = set(track_names)
    cars.update(
        str(row.get("id", "")).strip()
        for row in list_all_cars()
        if str(row.get("Game", "")).strip().casefold() == "ams2"
        and str(row.get("DLC", "")).strip().casefold() in {"", "base game"}
    )
    tracks.update(
        str(row.get("Track", "")).strip()
        for row in list_all_tracks()
        if str(row.get("Game", "")).strip().casefold() == "ams2"
        and str(row.get("DLC", "")).strip().casefold() in {"", "base game"}
    )
    return sorted(value for value in cars if value), sorted(value for value in tracks if value)


def profile_refs(profile_ids: list[str]) -> list[dict[str, str]]:
    profiles = {profile["id"]: profile for profile in list_player_profiles()}
    refs = []
    for profile_id in profile_ids:
        profile = profiles.get(profile_id)
        if profile:
            refs.append({"profile_id": profile["id"], "name": profile["name"]})
    return refs
