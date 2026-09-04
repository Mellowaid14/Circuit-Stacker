from __future__ import annotations

import csv
import json
import random
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .custom_championships import championship_rows
from .driver_pool import (
    add_ai_drivers_from_standings,
    advance_world_year,
    active_driver_rows_for_selection,
    active_world_ai_rows,
    assign_teams_to_standings,
    best_driver_in_world,
    build_ai_world_standings,
    championship_storyline_drivers,
    championship_pool_display_name,
    build_world_championship_instances,
    build_standings_from_pool,
    existing_team_seats_by_championship,
    finalize_driver_season,
    get_world_year,
    initialize_driver_pool,
    latest_close_title_battles,
    latest_tier_champions,
    list_drivers,
    notable_retirements,
    player_entry_prestige_for_style,
    populate_world_sim_instances,
    recent_team_seat_storylines,
    recent_team_storylines,
    record_driver_race_results,
    run_offseason_team_seat_market,
    set_world_year,
    set_ai_primary_style_on_first_championship,
    set_current_championship_for_standings,
    set_human_primary_style_if_unassigned,
    sync_human_drivers,
    top_rookies_for_year,
    team_reputation_map,
    update_ratings_after_race,
    world_simulated_finish_order,
    world_championship_field_size,
)
from .game_adapters import get_game_adapter
from .paths import resource_path
from .player_profiles import profile_refs, shared_owned_assets
from .save_manager import create_save, load_save, update_save
from .season_exporter import update_exported_season_difficulty
from .settings_manager import (
    list_all_cars,
    list_all_tracks,
    load_settings,
    owned_car_id_set_for_game,
    owned_track_id_set_for_game,
)
from .weather import generate_ams2_weather


TRACKS_CSV = resource_path("data", "Tracks.csv")
TIME_OF_DAY = ["Morning", "Afternoon", "Evening", "Night"]
MONTHS = ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct"]
POINTS_MAP = {1: 25, 2: 18, 3: 15, 4: 12, 5: 10, 6: 8, 7: 6, 8: 4, 9: 2, 10: 1}


class ResultsImportMappingRequired(ValueError):
    def __init__(self, app_names: list[str], imported_names: list[str]) -> None:
        self.app_names = app_names
        self.imported_names = imported_names
        super().__init__("Imported results need name mapping before they can be applied.")


def _track_style_for_championship(style: str) -> str:
    normalized = style.strip().casefold()
    if normalized in {"sports car", "open wheel"}:
        return "road"
    if normalized == "80r/20o":
        return "mixed_open_wheel"
    if normalized == "20r/80o":
        return "mixed_oval"
    if normalized == "oval":
        return "oval"
    return style.strip().casefold()


def _championship_discipline_style(style: str) -> str:
    normalized = str(style).strip().casefold()
    if normalized == "80r/20o":
        return "Open Wheel"
    if normalized == "20r/80o":
        return "Oval"
    return str(style).strip()


def _normalize_unlocked_tier(value: Any, fallback_tier: int = 1) -> int:
    """Read both the new global tier and older per-discipline tier saves."""
    max_tier = _max_available_tier()
    if isinstance(value, dict):
        tiers: list[int] = []
        for raw_tier in value.values():
            try:
                tiers.append(int(raw_tier))
            except (TypeError, ValueError):
                continue
        value = max(tiers) if tiers else fallback_tier
    try:
        tier = int(value)
    except (TypeError, ValueError):
        tier = int(fallback_tier)
    return max(1, min(max_tier, tier))


def _owned_assets_for_save(game: str, save_name: str | None = None) -> tuple[set[str], set[str]]:
    normalized_game = "AMS2" if str(game).strip().casefold() == "ams2" else "iRacing"
    if save_name:
        save_data = load_save(save_name) or {}
        profile_ids = [str(value).strip() for value in save_data.get("player_profile_ids", []) if str(value).strip()]
        snapshot = save_data.get("owned_content_snapshot")
        if profile_ids and isinstance(snapshot, dict) and str(snapshot.get("game", "")).casefold() == normalized_game.casefold():
            car_ids = {str(value).strip() for value in snapshot.get("car_ids", []) if str(value).strip()}
            track_names = {str(value).strip() for value in snapshot.get("track_names", []) if str(value).strip()}
            if normalized_game == "AMS2":
                car_ids.update(
                    str(row.get("id", "")).strip()
                    for row in list_all_cars()
                    if str(row.get("Game", "")).strip().casefold() == "ams2"
                    and str(row.get("DLC", "")).strip().casefold() in {"", "base game"}
                )
                track_names.update(
                    str(row.get("Track", "")).strip()
                    for row in list_all_tracks()
                    if str(row.get("Game", "")).strip().casefold() == "ams2"
                    and str(row.get("DLC", "")).strip().casefold() in {"", "base game"}
                )
            return car_ids, track_names
    return owned_car_id_set_for_game(normalized_game), owned_track_id_set_for_game(normalized_game)


def refresh_shared_content_snapshot(save_name: str) -> dict[str, Any] | None:
    save_data = load_save(save_name) or {}
    profile_ids = [str(value).strip() for value in save_data.get("player_profile_ids", []) if str(value).strip()]
    if not profile_ids:
        return None
    game = str(save_data.get("game", "iRacing"))
    car_ids, track_names = shared_owned_assets(profile_ids, game)
    snapshot = {
        "game": "AMS2" if game.strip().casefold() == "ams2" else "iRacing",
        "car_ids": car_ids,
        "track_names": track_names,
        "season_year": int(save_data.get("world_year", datetime.now().year) or datetime.now().year),
    }
    update_save(save_name, {"owned_content_snapshot": snapshot})
    return snapshot


def load_owned_cars(game: str = "iRacing", save_name: str | None = None) -> list[dict[str, str]]:
    owned_ids, _owned_tracks = _owned_assets_for_save(game, save_name)
    normalized_game = str(game).strip().casefold()
    return [
        row
        for row in list_all_cars()
        if str(row.get("id", "")).strip() in owned_ids
        and str(row.get("Game", "")).strip().casefold() in {"", normalized_game}
    ]


def _championship_rows_for_game(game: str = "iRacing", career_path_id: str | None = None) -> list[dict[str, str]]:
    return championship_rows(game, career_path_id)


def _championship_group_rows(
    championship: dict[str, Any],
    game: str = "iRacing",
) -> list[dict[str, str]]:
    existing_rows = championship.get("_entry_rows")
    if isinstance(existing_rows, list) and existing_rows:
        return [dict(row) for row in existing_rows if isinstance(row, dict)]

    championship_group_id = str(
        championship.get("Championship_ID", "")
        or championship.get("id", "")
    ).strip()
    if not championship_group_id:
        return [dict(championship)]

    grouped_rows = [
        row
        for row in _championship_rows_for_game(game)
        if str(row.get("Championship_ID", "")).strip() == championship_group_id
    ]
    return grouped_rows or [dict(championship)]


def _player_entry_rows(
    championship: dict[str, Any],
    game: str = "iRacing",
) -> list[dict[str, str]]:
    entry_rows = championship.get("_player_entry_rows")
    if isinstance(entry_rows, list) and entry_rows:
        return [dict(row) for row in entry_rows if isinstance(row, dict)]

    selected_row_id = str(championship.get("id", "")).strip()
    if selected_row_id:
        exact_rows = [
            row
            for row in _championship_rows_for_game(game)
            if str(row.get("id", "")).strip() == selected_row_id
        ]
        if exact_rows:
            return exact_rows

    return _championship_group_rows(championship, game)


def _cars_for_championship_rows(rows: list[dict[str, str]], game: str = "iRacing") -> list[dict[str, str]]:
    normalized_game = str(game).strip().casefold()
    matched: list[dict[str, str]] = []
    seen_car_ids: set[str] = set()
    all_cars = list_all_cars()
    for row in rows:
        target_class_id = str(row.get("Car_Class", "")).strip()
        target_car_id = str(row.get("Car_ID", "")).strip()
        for car in all_cars:
            if str(car.get("Game", "")).strip().casefold() not in {"", normalized_game}:
                continue
            car_id = str(car.get("id", "")).strip()
            if car_id in seen_car_ids:
                continue
            if target_class_id:
                if str(car.get("Car_Class_ID", "")).strip() != target_class_id:
                    continue
            elif target_car_id:
                if car_id != target_car_id:
                    continue
            else:
                continue
            seen_car_ids.add(car_id)
            matched.append(car)
    return matched


def _class_names_for_rows(rows: list[dict[str, str]], game: str = "iRacing") -> list[str]:
    class_names: list[str] = []
    seen: set[str] = set()
    for row in rows:
        custom_name = str(row.get("Class_Name", "")).strip()
        matching_cars = _cars_for_championship_rows([row], game)
        fallback = str(matching_cars[0].get("Car class", "")) if matching_cars else ""
        sub_champ = str(row.get("Sub_Champ", "")).strip()
        if sub_champ.casefold().startswith("class ") and ":" in sub_champ:
            sub_champ = sub_champ.split(":", 1)[1].strip()
        class_name = custom_name or sub_champ or fallback or "Overall"
        if class_name and class_name.casefold() not in seen:
            seen.add(class_name.casefold())
            class_names.append(class_name)
    return class_names


def _class_name_for_car_rows(
    rows: list[dict[str, str]], player_car: dict[str, str], game: str = "iRacing"
) -> str:
    """Resolve a player's class from the championship entry, not the catalog label."""
    player_id = str(player_car.get("id", "")).strip()
    player_class_id = str(player_car.get("Car_Class_ID", "")).strip()
    matching_rows = []
    for row in rows:
        row_car_id = str(row.get("Car_ID", "")).strip()
        row_class_id = str(row.get("Car_Class", "")).strip()
        if (row_car_id and row_car_id == player_id) or (row_class_id and row_class_id == player_class_id):
            matching_rows.append(row)
    return (_class_names_for_rows(matching_rows, game) or _class_names_for_rows(rows, game)[:1] or [""])[0]


def _build_world_championship_group(rows: list[dict[str, str]], game: str = "iRacing") -> dict[str, Any]:
    base_row = dict(rows[0])
    tiers = [int(str(row.get("Tier", "1")).strip() or 1) for row in rows]
    prestiges = [int(str(row.get("Prestige", "0")).strip() or 0) for row in rows]
    class_names = _class_names_for_rows(rows, game)
    highest_tier_row = max(rows, key=lambda row: int(str(row.get("Tier", "1")).strip() or 1))
    highest_prestige_row = max(rows, key=lambda row: int(str(row.get("Prestige", "0")).strip() or 0))
    group_id = str(base_row.get("Championship_ID", "")).strip() or str(base_row.get("id", "")).strip()

    championship = dict(base_row)
    championship["id"] = group_id
    championship["Championship_ID"] = group_id
    championship["Tier"] = str(max(tiers) if tiers else int(str(base_row.get("Tier", "1")).strip() or 1))
    championship["Prestige"] = str(max(prestiges) if prestiges else int(str(base_row.get("Prestige", "0")).strip() or 0))
    championship["_schedule_style"] = str(base_row.get("Style", "")).strip()
    championship["Style"] = _championship_discipline_style(str(base_row.get("Style", "")))
    championship["Multiclass"] = "yes" if len(class_names) > 1 else "no"
    championship["_entry_rows"] = [dict(row) for row in rows]
    championship["_class_names"] = class_names
    class_tiers: dict[str, int] = {}
    class_prestiges: dict[str, int] = {}
    class_car_counts: dict[str, int] = {}
    for row in rows:
        row_tier = int(str(row.get("Tier", "1")).strip() or 1)
        row_prestige = int(str(row.get("Prestige", "0")).strip() or 0)
        for class_name in _class_names_for_rows([row], game):
            class_tiers[class_name] = row_tier
            class_prestiges[class_name] = row_prestige
            try:
                class_cars = int(str(row.get("Class_Cars", "")).strip())
            except (TypeError, ValueError):
                class_cars = 0
            if class_cars > 0:
                class_car_counts[class_name] = class_cars
    championship["_class_tiers"] = class_tiers
    championship["_class_prestiges"] = class_prestiges
    if class_car_counts:
        championship["_class_car_counts"] = class_car_counts
    championship["_headline_class_name"] = (
        _class_names_for_rows([highest_prestige_row], game)[:1] or _class_names_for_rows([highest_tier_row], game)[:1] or class_names[:1] or [""]
    )[0]
    return championship


def load_world_championships(game: str = "iRacing", career_path_id: str | None = None) -> list[dict[str, Any]]:
    championships: list[dict[str, Any]] = []
    grouped_rows: dict[str, list[dict[str, str]]] = {}
    for row in _championship_rows_for_game(game, career_path_id):
        championship_group_id = str(row.get("Championship_ID", "")).strip() or str(row.get("id", "")).strip()
        grouped_rows.setdefault(championship_group_id, []).append(row)
    for rows in grouped_rows.values():
        championships.append(_build_world_championship_group(rows, game))
    return championships


def _empty_world_sim_summary() -> dict[str, int]:
    return {
        "championships": 0,
        "races": 0,
        "drivers": 0,
        "retired": 0,
        "forced_retired": 0,
        "rookies_added": 0,
        "teams": 0,
        "team_seasons": 0,
    }


def _merge_world_sim_summary(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, int]:
    summary = _empty_world_sim_summary()
    for key in summary:
        summary[key] = int(base.get(key, 0) or 0) + int(extra.get(key, 0) or 0)
    return summary


def _date_to_ordinal(date_text: str) -> int:
    try:
        day_str, month_str = str(date_text).split(maxsplit=1)
        month_index = MONTHS.index(month_str.strip())
        day = int(day_str)
        return month_index * 31 + day
    except (ValueError, IndexError):
        return -1


def _active_championship_group_id(championship: dict[str, Any], game: str) -> str:
    explicit_group_id = str(championship.get("Championship_ID", "")).strip()
    if explicit_group_id:
        return explicit_group_id

    row_id = str(championship.get("id", "")).strip()
    championship_name = str(championship.get("Championship", "")).strip()
    sub_champ = str(championship.get("Sub_Champ", "")).strip()
    rows = _championship_rows_for_game(game)
    for row in rows:
        if row_id and str(row.get("id", "")).strip() == row_id:
            return str(row.get("Championship_ID", "")).strip() or row_id
    for row in rows:
        names_match = str(row.get("Championship", "")).strip().casefold() == championship_name.casefold()
        sub_matches = not sub_champ or str(row.get("Sub_Champ", "")).strip().casefold() == sub_champ.casefold()
        if names_match and sub_matches:
            return str(row.get("Championship_ID", "")).strip() or str(row.get("id", "")).strip() or championship_name
    return row_id or championship_name


def _next_world_event_ordinal(instances: list[dict[str, Any]]) -> int:
    next_dates = []
    for instance in instances:
        schedule = instance.get("schedule") or []
        current_race = int(instance.get("current_race", 0) or 0)
        if current_race >= len(schedule):
            continue
        next_dates.append(_date_to_ordinal(str(schedule[current_race].get("date", ""))))
    return min(next_dates) if next_dates else 9999


def _active_world_championship_entries(save_data: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(save_data, dict):
        return []

    save_game = str(save_data.get("game", "iRacing"))
    raw_entries: list[dict[str, Any]] = []
    championship = save_data.get("championship") or {}
    standings = list(save_data.get("standings") or [])
    schedule = list(save_data.get("schedule") or [])
    if championship and standings:
        raw_entries.append(
            {
                "championship": championship,
                "standings": standings,
                "schedule": schedule,
                "current_race": int(save_data.get("current_race", 0) or 0),
                "is_player": True,
            }
        )

    progress = save_data.get("world_sim_progress") or {}
    for instance in progress.get("instances") or []:
        instance_championship = instance.get("championship") or {}
        instance_standings = list(instance.get("standings") or [])
        if not instance_championship or not instance_standings:
            continue
        raw_entries.append(
            {
                "championship": instance_championship,
                "standings": instance_standings,
                "schedule": list(instance.get("schedule") or []),
                "current_race": int(instance.get("current_race", 0) or 0),
                "is_player": False,
            }
        )
    grouped_entries: dict[tuple[str, str, bool], list[dict[str, Any]]] = {}
    for entry in raw_entries:
        entry_championship = entry.get("championship") or {}
        entry_game = str(entry_championship.get("Game", "") or save_game)
        championship_group_id = _active_championship_group_id(entry_championship, entry_game)
        grouped_entries.setdefault(
            (
                championship_group_id,
                str(entry_championship.get("Style", "")).strip(),
                bool(entry.get("is_player")),
            ),
            [],
        ).append(entry)

    entries: list[dict[str, Any]] = []
    for group_key, group in grouped_entries.items():
        sorted_group = sorted(
            group,
            key=lambda item: (
                -int((item.get("championship") or {}).get("Prestige", 0) or 0),
                -int((item.get("championship") or {}).get("Tier", 1) or 1),
                str((item.get("championship") or {}).get("Sub_Champ", "")).strip(),
            ),
        )
        primary = dict(sorted_group[0])
        championship = dict(primary.get("championship") or {})
        championship["id"] = group_key[0]
        championship["Championship_ID"] = group_key[0]
        championship["Tier"] = str(max(int((item.get("championship") or {}).get("Tier", 1) or 1) for item in sorted_group))
        championship["Prestige"] = str(max(int((item.get("championship") or {}).get("Prestige", 0) or 0) for item in sorted_group))

        standings: list[dict[str, Any]] = []
        seen_driver_keys: set[str] = set()
        for item in sorted_group:
            for driver in list(item.get("standings") or []):
                driver_key = str(driver.get("driver_id", "")).strip() or str(driver.get("name", "")).strip()
                if driver_key and driver_key in seen_driver_keys:
                    continue
                if driver_key:
                    seen_driver_keys.add(driver_key)
                standings.append(dict(driver))

        entry = dict(primary)
        entry["championship"] = championship
        entry["standings"] = standings
        entry["name"] = str(championship.get("Championship", "")).strip() or championship_pool_display_name(championship)
        entry["key"] = f"{group_key[0]}::{group_key[1]}::{1 if group_key[2] else 0}"
        entries.append(entry)
    return entries


def list_active_world_championships(save_name: str) -> list[dict[str, Any]]:
    save_data = load_save(save_name) or {}
    entries = _active_world_championship_entries(save_data)
    summaries: list[dict[str, Any]] = []
    for entry in entries:
        championship = entry.get("championship") or {}
        standings = entry.get("standings") or []
        schedule = entry.get("schedule") or []
        current_race = int(entry.get("current_race", 0) or 0)
        summaries.append(
            {
                "key": entry.get("key"),
                "name": entry.get("name"),
                "tier": int(championship.get("Tier", 1) or 1),
                "prestige": int(championship.get("Prestige", 0) or 0),
                "style": str(championship.get("Style", "")).strip(),
                "drivers": len(standings),
                "round_label": f"{min(current_race + 1, len(schedule))}/{len(schedule)}" if schedule else "-",
                "is_player": bool(entry.get("is_player")),
            }
        )
    return sorted(
        summaries,
        key=lambda item: (
            str(item.get("style", "")).strip(),
            -int(item.get("prestige", 0) or 0),
            0 if bool(item.get("is_player")) else 1,
            str(item.get("name", "")).strip(),
        ),
    )


def get_active_world_championship_detail(save_name: str, championship_key: str) -> dict[str, Any] | None:
    target_key = str(championship_key).strip()
    if not target_key:
        return None
    save_data = load_save(save_name) or {}
    for entry in _active_world_championship_entries(save_data):
        if str(entry.get("key", "")).strip() != target_key:
            continue
        championship = dict(entry.get("championship") or {})
        standings = list(entry.get("standings") or [])
        schedule = list(entry.get("schedule") or [])
        current_race = int(entry.get("current_race", 0) or 0)
        return {
            "key": entry.get("key"),
            "name": entry.get("name"),
            "championship": championship,
            "standings": standings,
            "schedule": schedule,
            "current_race": current_race,
            "is_player": bool(entry.get("is_player")),
        }
    return None


def current_team_championships(save_name: str, team_key: str) -> list[dict[str, Any]]:
    target_key = str(team_key).strip()
    if not target_key:
        return []
    save_data = load_save(save_name) or {}
    current_rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for entry in _active_world_championship_entries(save_data):
        championship = entry.get("championship") or {}
        standings = list(entry.get("standings") or [])
        schedule = list(entry.get("schedule") or [])
        current_race = int(entry.get("current_race", 0) or 0)
        matching_drivers = [
            driver
            for driver in standings
            if str(driver.get("team_key", "")).strip() == target_key
        ]
        if not matching_drivers:
            continue

        by_class: dict[str, list[dict[str, Any]]] = {}
        for driver in matching_drivers:
            class_name = str(driver.get("class_name", "Overall")).strip() or "Overall"
            by_class.setdefault(class_name, []).append(driver)

        for class_name, drivers in by_class.items():
            championship_name = championship_pool_display_name(championship)
            key = (str(entry.get("key", "")), class_name, championship_name)
            if key in seen:
                continue
            seen.add(key)
            current_rows.append(
                {
                    "championship_name": championship_name,
                    "style": str(championship.get("Style", "")).strip(),
                    "class_name": class_name,
                    "drivers": " | ".join(sorted(str(driver.get("name", "")).strip() for driver in drivers if str(driver.get("name", "")).strip())),
                    "points": sum(int(driver.get("points", 0) or 0) for driver in drivers),
                    "wins": sum(int(driver.get("wins", 0) or 0) for driver in drivers),
                    "round_label": f"{min(current_race + 1, len(schedule))}/{len(schedule)}" if schedule else "-",
                    "is_player": bool(entry.get("is_player")),
                }
            )

    return sorted(
        current_rows,
        key=lambda row: (
            str(row.get("style", "")),
            str(row.get("championship_name", "")),
            str(row.get("class_name", "")),
        ),
    )


def _news_entries(save_data: dict[str, Any], player_championship: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    entries = _active_world_championship_entries(save_data)
    if player_championship and save_data.get("schedule") and save_data.get("standings"):
        entries.append(
            {
                "championship": player_championship,
                "schedule": list(save_data.get("schedule") or []),
                "standings": list(save_data.get("standings") or []),
                "current_race": int(save_data.get("current_race", 0) or 0),
                "is_player": True,
            }
        )
    return entries


def _driver_lookup(save_name: str) -> dict[str, dict[str, Any]]:
    try:
        return {
            str(driver.get("name", "")).strip(): driver
            for driver in list_drivers(save_name, include_retired=True)
            if str(driver.get("name", "")).strip()
        }
    except Exception:
        return {}


def _championship_entry_name(entry: dict[str, Any]) -> str:
    championship = entry.get("championship") or {}
    return championship_pool_display_name(championship) or str(championship.get("Championship", "")).strip() or "World Championship"


def _entry_completed_race_count(entry: dict[str, Any]) -> int:
    completed = 0
    for race in entry.get("schedule") or []:
        if not bool(race.get("completed")):
            continue
        full_results = race.get("full_results") or []
        if isinstance(full_results, list) and full_results:
            completed += 1
    return completed


def _world_news_is_season_opening(
    save_data: dict[str, Any],
    player_championship: dict[str, Any] | None = None,
) -> bool:
    entries = _news_entries(save_data, player_championship=player_championship)
    if not entries:
        return int(save_data.get("current_race", 0) or 0) <= 0
    return all(_entry_completed_race_count(entry) <= 0 for entry in entries)


def _recent_race_news_candidates(
    save_data: dict[str, Any],
    player_championship: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    raw_entries = _news_entries(save_data, player_championship=player_championship)

    for entry in raw_entries:
        championship_name = _championship_entry_name(entry)
        for race in entry.get("schedule") or []:
            if not bool(race.get("completed")):
                continue
            full_results = race.get("full_results") or []
            if not isinstance(full_results, list) or not full_results:
                continue

            winning_row = None
            for row in full_results:
                if not isinstance(row, dict):
                    continue
                if winning_row is None or int(row.get("overall_pos", 9999) or 9999) < int(winning_row.get("overall_pos", 9999) or 9999):
                    winning_row = row
            if not isinstance(winning_row, dict):
                continue

            driver_name = str(winning_row.get("driver_name", "")).strip()
            if not driver_name:
                continue
            track_name = str(race.get("track", "")).strip() or "the circuit"
            class_name = str(winning_row.get("class_name", "")).strip()
            class_note = f" in {class_name}" if class_name and class_name.casefold() != "overall" else ""
            candidates.append(
                {
                    "title": championship_name,
                    "body": f"**{driver_name}** had an impressive day{class_note}, driving to victory at {track_name}.",
                }
            )

    return candidates


def _incident_news_candidates(
    save_data: dict[str, Any],
    player_championship: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    raw_entries = _news_entries(save_data, player_championship=player_championship)

    for entry in raw_entries:
        standings = list(entry.get("standings") or [])
        if len(standings) < 5:
            continue
        top_names = {
            str(driver.get("name", "")).strip()
            for driver in sorted(
                standings,
                key=lambda driver: (int(driver.get("points", 0) or 0), int(driver.get("wins", 0) or 0)),
                reverse=True,
            )[:5]
            if str(driver.get("name", "")).strip()
        }
        if not top_names:
            continue

        championship_name = _championship_entry_name(entry)

        for race in entry.get("schedule") or []:
            if not bool(race.get("completed")):
                continue
            full_results = race.get("full_results") or []
            if not isinstance(full_results, list) or len(full_results) < 2:
                continue

            out_of_points = [
                row
                for row in full_results
                if isinstance(row, dict) and int(row.get("points_awarded", 0) or 0) <= 0 and str(row.get("driver_name", "")).strip()
            ]
            if len(out_of_points) < 2:
                continue

            headline_driver = next(
                (row for row in out_of_points if str(row.get("driver_name", "")).strip() in top_names),
                None,
            )
            if headline_driver is None:
                continue

            second_driver = next(
                (
                    row
                    for row in out_of_points
                    if str(row.get("driver_name", "")).strip()
                    and str(row.get("driver_name", "")).strip() != str(headline_driver.get("driver_name", "")).strip()
                ),
                None,
            )
            if second_driver is None:
                continue

            driver_one = str(headline_driver.get("driver_name", "")).strip()
            driver_two = str(second_driver.get("driver_name", "")).strip()
            track_name = str(race.get("track", "")).strip() or "the circuit"
            candidates.append(
                {
                    "title": championship_name,
                    "body": (
                        f"**{driver_two}** made contact with **{driver_one}** and took both drivers out of a points finish at {track_name}."
                    ),
                }
            )

    return candidates


def _title_fight_news_candidates(
    save_data: dict[str, Any],
    player_championship: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    raw_entries = _news_entries(save_data, player_championship=player_championship)

    for entry in raw_entries:
        standings = list(entry.get("standings") or [])
        schedule = list(entry.get("schedule") or [])
        completed_races = _entry_completed_race_count(entry)
        current_race = int(entry.get("current_race", 0) or 0)
        remaining_races = max(0, len(schedule) - current_race)
        if completed_races <= 0 or remaining_races <= 0 or remaining_races > 2 or len(standings) < 2:
            continue

        sorted_standings = sorted(
            standings,
            key=lambda driver: (int(driver.get("points", 0) or 0), int(driver.get("wins", 0) or 0)),
            reverse=True,
        )
        leader = sorted_standings[0]
        challenger = sorted_standings[1]
        gap = int(leader.get("points", 0) or 0) - int(challenger.get("points", 0) or 0)
        if gap <= 0 or gap > 15:
            continue

        championship_name = _championship_entry_name(entry)
        candidates.append(
            {
                "title": f"{championship_name} Title Fight",
                "body": (
                    f"With {remaining_races} race{'s' if remaining_races != 1 else ''} left, "
                    f"**{leader.get('name', 'Unknown')}** leads **{challenger.get('name', 'Unknown')}** by just {gap} points."
                ),
            }
        )

    return candidates


def _performance_news_candidates(
    save_name: str,
    save_data: dict[str, Any],
    player_championship: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    driver_map = _driver_lookup(save_name)

    for entry in _news_entries(save_data, player_championship=player_championship):
        standings = list(entry.get("standings") or [])
        schedule = [race for race in (entry.get("schedule") or []) if bool(race.get("completed")) and isinstance(race.get("full_results"), list)]
        if not standings or not schedule:
            continue

        championship_name = _championship_entry_name(entry)
        latest_race = schedule[-1]
        latest_results = list(latest_race.get("full_results") or [])
        latest_by_name = {
            str(row.get("driver_name", "")).strip(): row
            for row in latest_results
            if isinstance(row, dict) and str(row.get("driver_name", "")).strip()
        }
        sorted_standings = sorted(
            standings,
            key=lambda driver: (int(driver.get("points", 0) or 0), int(driver.get("wins", 0) or 0)),
            reverse=True,
        )
        leader = sorted_standings[0]
        leader_row = latest_by_name.get(str(leader.get("name", "")).strip())
        if leader_row and int(leader_row.get("points_awarded", 0) or 0) <= 0:
            if len(sorted_standings) > 1:
                challenger = sorted_standings[1]
                gap = int(leader.get("points", 0) or 0) - int(challenger.get("points", 0) or 0)
                candidates.append(
                    {
                        "title": f"{championship_name} Under Pressure",
                        "body": (
                            f"Points leader **{leader.get('name', 'Unknown')}** came away empty-handed at "
                            f"{latest_race.get('track', 'the latest round')}, and the gap to **{challenger.get('name', 'Unknown')}** is down to {gap}."
                        ),
                    }
                )

        latest_winner = next(
            (
                row
                for row in latest_results
                if int(row.get("overall_pos", 9999) or 9999) == 1
            ),
            None,
        )
        if isinstance(latest_winner, dict):
            winner_name = str(latest_winner.get("driver_name", "")).strip()
            winner_profile = driver_map.get(winner_name, {})
            standings_position = next(
                (
                    pos
                    for pos, driver in enumerate(sorted_standings, start=1)
                    if str(driver.get("name", "")).strip() == winner_name
                ),
                999,
            )
            if winner_name and standings_position > 5:
                candidates.append(
                    {
                        "title": "Shock Winner",
                        "body": (
                            f"**{winner_name}** stunned {championship_name} with a surprise win at "
                            f"{latest_race.get('track', 'the latest round')}."
                        ),
                    }
                )
            if winner_name and int(winner_profile.get("wins", 0) or 0) == 1:
                candidates.append(
                    {
                        "title": "First Career Win",
                        "body": (
                            f"**{winner_name}** broke through for a first career victory in {championship_name} at "
                            f"{latest_race.get('track', 'the latest round')}."
                        ),
                    }
                )
            if winner_name and int(winner_profile.get("driver_age", 0) or 0) >= 35:
                candidates.append(
                    {
                        "title": "Veteran Still Has It",
                        "body": (
                            f"Veteran **{winner_name}** showed there is still plenty left in the tank with a big result at "
                            f"{latest_race.get('track', 'the latest round')}."
                        ),
                    }
                )

        podium_names = [
            str(row.get("driver_name", "")).strip()
            for row in latest_results
            if isinstance(row, dict) and 1 <= int(row.get("class_pos", 9999) or 9999) <= 3 and str(row.get("driver_name", "")).strip()
        ]
        for podium_name in podium_names:
            profile = driver_map.get(podium_name, {})
            if int(profile.get("podiums", 0) or 0) == 1:
                candidates.append(
                    {
                        "title": "Breakthrough Podium",
                        "body": (
                            f"**{podium_name}** landed a breakthrough podium in {championship_name} at "
                            f"{latest_race.get('track', 'the latest round')}."
                        ),
                    }
                )
                break

        if len(schedule) >= 2:
            prior_results = list(schedule[-2].get("full_results") or [])
            prior_by_name = {
                str(row.get("driver_name", "")).strip(): row
                for row in prior_results
                if isinstance(row, dict) and str(row.get("driver_name", "")).strip()
            }
            for podium_name in podium_names:
                prior_row = prior_by_name.get(podium_name)
                latest_row = latest_by_name.get(podium_name)
                if prior_row and latest_row and int(prior_row.get("points_awarded", 0) or 0) <= 0 and int(latest_row.get("class_pos", 9999) or 9999) <= 3:
                    candidates.append(
                        {
                            "title": "Bounce Back",
                            "body": (
                                f"After a rough previous round, **{podium_name}** bounced back with a podium at "
                                f"{latest_race.get('track', 'the latest round')}."
                            ),
                        }
                    )
                    break

        if len(schedule) >= 3:
            recent_races = schedule[-3:]
            recent_winners = []
            for race in recent_races:
                race_winner = next(
                    (
                        row
                        for row in (race.get("full_results") or [])
                        if isinstance(row, dict) and int(row.get("overall_pos", 9999) or 9999) == 1
                    ),
                    None,
                )
                recent_winners.append(str((race_winner or {}).get("driver_name", "")).strip())
            if recent_winners[0] and recent_winners.count(recent_winners[0]) == len(recent_winners):
                candidates.append(
                    {
                        "title": "Winning Streak",
                        "body": f"**{recent_winners[0]}** is on a three-race tear in {championship_name}.",
                    }
                )

            for driver_name in {name for name in recent_winners if name}:
                podium_run = True
                for race in recent_races:
                    row = next(
                        (
                            item
                            for item in (race.get("full_results") or [])
                            if isinstance(item, dict) and str(item.get("driver_name", "")).strip() == driver_name
                        ),
                        None,
                    )
                    if row is None or int(row.get("class_pos", 9999) or 9999) > 3:
                        podium_run = False
                        break
                if podium_run:
                    candidates.append(
                        {
                            "title": "Podium Run",
                            "body": f"**{driver_name}** has put together a serious podium run in {championship_name}.",
                        }
                    )
                    break

        if len(schedule) >= 2:
            rivalry_pairs: dict[tuple[str, str], int] = {}
            for race in schedule[-2:]:
                ordered = sorted(
                    [row for row in (race.get("full_results") or []) if isinstance(row, dict)],
                    key=lambda row: int(row.get("overall_pos", 9999) or 9999),
                )
                for left, right in zip(ordered, ordered[1:]):
                    left_name = str(left.get("driver_name", "")).strip()
                    right_name = str(right.get("driver_name", "")).strip()
                    if not left_name or not right_name:
                        continue
                    pair = tuple(sorted((left_name, right_name)))
                    rivalry_pairs[pair] = rivalry_pairs.get(pair, 0) + 1
            hot_pair = next((pair for pair, count in rivalry_pairs.items() if count >= 2), None)
            if hot_pair:
                candidates.append(
                    {
                        "title": "Rivalry Brewing",
                        "body": f"**{hot_pair[0]}** and **{hot_pair[1]}** keep finding each other on track in {championship_name}.",
                    }
                )

        if len(sorted_standings) >= 2 and int(entry.get("championship", {}).get("Tier", 1) or 1) < 5:
            leader_gap = int(sorted_standings[0].get("points", 0) or 0) - int(sorted_standings[1].get("points", 0) or 0)
            if leader_gap >= 20:
                candidates.append(
                    {
                        "title": "Promotion Watch",
                        "body": f"**{sorted_standings[0].get('name', 'Unknown')}** is starting to look ready for the next rung after opening a {leader_gap}-point gap in {championship_name}.",
                    }
                )

        remaining_races = max(0, len(entry.get("schedule") or []) - int(entry.get("current_race", 0) or 0))
        if remaining_races <= 2 and len(sorted_standings) >= 2:
            bottom = sorted(standings, key=lambda driver: (int(driver.get("points", 0) or 0), int(driver.get("wins", 0) or 0)))
            if len(bottom) >= 2:
                danger_driver = bottom[0]
                safe_driver = bottom[1]
                gap = int(safe_driver.get("points", 0) or 0) - int(danger_driver.get("points", 0) or 0)
                candidates.append(
                    {
                        "title": "Relegation Trouble",
                        "body": f"**{danger_driver.get('name', 'Unknown')}** is in real trouble at the bottom of {championship_name}, sitting {gap} points behind safety.",
                    }
                )

        grouped_by_class: dict[str, list[dict[str, Any]]] = {}
        for driver in standings:
            class_name = str(driver.get("class_name", "")).strip() or "Overall"
            grouped_by_class.setdefault(class_name, []).append(driver)
        if len(grouped_by_class) > 1:
            for class_name, class_drivers in grouped_by_class.items():
                if len(class_drivers) < 2:
                    continue
                class_sorted = sorted(
                    class_drivers,
                    key=lambda driver: (int(driver.get("points", 0) or 0), int(driver.get("wins", 0) or 0)),
                    reverse=True,
                )
                gap = int(class_sorted[0].get("points", 0) or 0) - int(class_sorted[1].get("points", 0) or 0)
                if gap >= 20:
                    candidates.append(
                        {
                            "title": "Class Domination",
                            "body": f"**{class_sorted[0].get('name', 'Unknown')}** is starting to dominate the {class_name} fight in {championship_name}.",
                        }
                    )
                    break

    return candidates


def _championship_clinch_news_candidates(save_name: str, world_year: int) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    recent_champions = latest_tier_champions(save_name, world_year, tier=5) + latest_tier_champions(save_name, world_year, tier=4)
    for champion in recent_champions[:3]:
        candidates.append(
            {
                "title": "Title Clinched",
                "body": f"**{champion.get('driver_name', 'Unknown')}** has already locked up {champion.get('championship_name', 'a championship')} for {world_year}.",
            }
        )
    return candidates


def _season_opening_wrap_news_candidates(
    save_name: str,
    save_data: dict[str, Any],
    world_year: int,
    completed_year: int,
    player_championship: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    if completed_year <= 0 or not _world_news_is_season_opening(save_data, player_championship=player_championship):
        return []

    candidates: list[dict[str, str]] = []
    close_battles = latest_close_title_battles(save_name, completed_year, max_gap=8, limit=4)
    for battle in close_battles:
        championship_name = str(battle.get("championship_name", "")).strip() or "a championship"
        class_name = str(battle.get("class_name", "Overall")).strip()
        class_note = "" if not class_name or class_name.casefold() == "overall" else f" in {class_name}"
        gap = int(battle.get("gap", 0) or 0)
        candidates.append(
            {
                "title": "Last Season Went To The Wire",
                "body": (
                    f"Before the {world_year} opener, the paddock is still talking about {championship_name}{class_note}: "
                    f"**{battle.get('champion_name', 'Unknown')}** beat **{battle.get('runner_up_name', 'Unknown')}** "
                    f"by just {gap} point{'s' if gap != 1 else ''} last season."
                ),
            }
        )

    if not candidates:
        champions = latest_tier_champions(save_name, completed_year, tier=5) + latest_tier_champions(save_name, completed_year, tier=4)
        if champions:
            champion = champions[0]
            candidates.append(
                {
                    "title": "Last Season Recap",
                    "body": (
                        f"The {world_year} season opens with **{champion.get('driver_name', 'Unknown')}** carrying the momentum "
                        f"from a {completed_year} title in {champion.get('championship_name', 'a championship')}."
                    ),
                }
            )

    return candidates


def _team_form_news_candidates(
    save_data: dict[str, Any],
    player_championship: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for entry in _news_entries(save_data, player_championship=player_championship):
        standings = list(entry.get("standings") or [])
        schedule = [race for race in (entry.get("schedule") or []) if bool(race.get("completed")) and isinstance(race.get("full_results"), list)]
        if len(standings) < 4 or not schedule:
            continue

        championship_name = _championship_entry_name(entry)
        team_rows: dict[str, list[dict[str, Any]]] = {}
        for driver in standings:
            team_name = str(driver.get("team_name", "")).strip()
            if not team_name:
                continue
            team_rows.setdefault(team_name, []).append(driver)

        team_scores = []
        for team_name, drivers in team_rows.items():
            if len(drivers) < 2:
                continue
            points = sum(int(driver.get("points", 0) or 0) for driver in drivers)
            wins = sum(int(driver.get("wins", 0) or 0) for driver in drivers)
            podiums = sum(int(driver.get("podiums", 0) or 0) for driver in drivers)
            team_scores.append((points, wins, podiums, team_name, drivers))
        if team_scores:
            team_scores.sort(reverse=True)
            points, wins, podiums, team_name, drivers = team_scores[0]
            if wins >= 2 or points >= 80:
                candidates.append(
                    {
                        "title": "Team Form",
                        "body": f"**{team_name}** is becoming the benchmark in {championship_name} with {wins} wins and {podiums} podiums.",
                    }
                )

        for team_name, drivers in team_rows.items():
            if len(drivers) < 2:
                continue
            sorted_drivers = sorted(drivers, key=lambda driver: int(driver.get("points", 0) or 0), reverse=True)
            gap = abs(int(sorted_drivers[0].get("points", 0) or 0) - int(sorted_drivers[1].get("points", 0) or 0))
            if gap <= 5:
                candidates.append(
                    {
                        "title": "Teammate Battle",
                        "body": (
                            f"**{sorted_drivers[0].get('name', 'Unknown')}** and **{sorted_drivers[1].get('name', 'Unknown')}** "
                            f"are separated by only {gap} points inside **{team_name}**."
                        ),
                    }
                )
                break

        if schedule:
            latest_results = list(schedule[-1].get("full_results") or [])
            team_podiums: dict[str, int] = {}
            for row in latest_results:
                if not isinstance(row, dict) or int(row.get("class_pos", 9999) or 9999) > 3:
                    continue
                team_name = str(row.get("team_name", "")).strip()
                if team_name:
                    team_podiums[team_name] = team_podiums.get(team_name, 0) + 1
            sweep_team = next((team_name for team_name, count in team_podiums.items() if count >= 2), "")
            if sweep_team:
                candidates.append(
                    {
                        "title": "Team Podium Haul",
                        "body": f"**{sweep_team}** stacked multiple podium finishes in the latest {championship_name} round.",
                    }
                )

    return candidates


def _upcoming_pressure_news_candidates(
    save_data: dict[str, Any],
    player_championship: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for entry in _news_entries(save_data, player_championship=player_championship):
        standings = list(entry.get("standings") or [])
        schedule = list(entry.get("schedule") or [])
        completed_races = _entry_completed_race_count(entry)
        current_race = int(entry.get("current_race", 0) or 0)
        if completed_races <= 0 or current_race >= len(schedule) or len(standings) < 2:
            continue

        championship_name = _championship_entry_name(entry)
        next_race = schedule[current_race]
        track_name = str(next_race.get("track", "")).strip() or "the next round"
        sorted_standings = sorted(
            standings,
            key=lambda driver: (int(driver.get("points", 0) or 0), int(driver.get("wins", 0) or 0)),
            reverse=True,
        )
        leader = sorted_standings[0]
        challenger = sorted_standings[1]
        gap = int(leader.get("points", 0) or 0) - int(challenger.get("points", 0) or 0)
        if 0 < gap <= 10:
            candidates.append(
                {
                    "title": "Pressure Round",
                    "body": (
                        f"{championship_name} heads to {track_name} with **{leader.get('name', 'Unknown')}** only "
                        f"{gap} points ahead of **{challenger.get('name', 'Unknown')}**."
                    ),
                }
            )

        weather = str(next_race.get("weather", "")).strip()
        if any(term in weather.casefold() for term in ("rain", "storm", "fog")):
            candidates.append(
                {
                    "title": "Weather Watch",
                    "body": f"Weather could complicate {championship_name} at {track_name}: {weather}.",
                }
            )

        midfield = sorted_standings[3:8]
        if len(midfield) >= 3:
            spread = int(midfield[0].get("points", 0) or 0) - int(midfield[-1].get("points", 0) or 0)
            if 0 < spread <= 8:
                candidates.append(
                    {
                        "title": "Midfield Squeeze",
                        "body": f"The middle of the {championship_name} table is packed tight, with five drivers covered by {spread} points.",
                    }
                )

    return candidates


def _underdog_news_candidates(
    save_data: dict[str, Any],
    player_championship: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for entry in _news_entries(save_data, player_championship=player_championship):
        standings = list(entry.get("standings") or [])
        schedule = [race for race in (entry.get("schedule") or []) if bool(race.get("completed")) and isinstance(race.get("full_results"), list)]
        if len(standings) < 8 or not schedule:
            continue

        sorted_standings = sorted(
            standings,
            key=lambda driver: (int(driver.get("points", 0) or 0), int(driver.get("wins", 0) or 0)),
            reverse=True,
        )
        standing_position = {str(driver.get("name", "")).strip(): index for index, driver in enumerate(sorted_standings, 1)}
        latest_race = schedule[-1]
        for row in latest_race.get("full_results") or []:
            if not isinstance(row, dict):
                continue
            driver_name = str(row.get("driver_name", "")).strip()
            if not driver_name:
                continue
            position = standing_position.get(driver_name, 0)
            if position > max(5, len(sorted_standings) // 2) and int(row.get("class_pos", 9999) or 9999) <= 5:
                candidates.append(
                    {
                        "title": "Underdog Points",
                        "body": (
                            f"**{driver_name}** punched above their place in the standings with a strong run at "
                            f"{latest_race.get('track', 'the latest round')}."
                        ),
                    }
                )
                break

    return candidates


def _interview_news_candidates(
    watch_drivers: list[str] | None = None,
    rising_driver: str | None = None,
    recent_race_items: list[dict[str, str]] | None = None,
    best_driver: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    watch_names = [str(name).strip() for name in (watch_drivers or []) if str(name).strip()]

    quote_templates = [
        "{name} says the team just needs to stay calm and keep stacking strong finishes.",
        "{name} says confidence is building and the results are starting to follow.",
        "{name} says there is still more pace to unlock before the season is over.",
        "{name} says clean weekends matter more than chasing one perfect lap right now.",
        "{name} says the pressure is real, but the group around them is ready for the fight.",
        "{name} says the next race could tell everyone where the season is really headed.",
    ]

    interview_names: list[str] = []
    if watch_names:
        interview_names.append(watch_names[0])
    if rising_driver:
        interview_names.append(str(rising_driver).strip())
    if best_driver and str(best_driver.get("name", "")).strip():
        interview_names.append(str(best_driver.get("name", "")).strip())

    seen: set[str] = set()
    for name in interview_names:
        if not name or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        candidates.append(
            {
                "title": "Driver Interview",
                "body": f"\"{random.choice(quote_templates).format(name=f'**{name}**')}\"",
            }
        )

    if recent_race_items:
        item = random.choice(recent_race_items)
        body = str(item.get("body", "")).replace("**", "")
        if body:
            candidates.append(
                {
                    "title": "Post-Race Reaction",
                    "body": f"\"That was a big result for us today,\" came the reaction after {body.lower()}",
                }
            )

    return candidates


def _team_market_news_candidates(save_name: str, world_year: int) -> list[dict[str, str]]:
    if world_year <= 0:
        return []
    candidates: list[dict[str, str]] = []
    for item in recent_team_seat_storylines(save_name, world_year, limit=8):
        team_name = str(item.get("team_name", "Independent")).strip() or "Independent"
        championship_name = str(item.get("championship_name", "a championship")).strip() or "a championship"
        event_type = str(item.get("event_type", "")).strip().casefold()
        reason = str(item.get("reason", "the offseason market")).strip() or "the offseason market"
        if event_type == "acquired":
            candidates.append(
                {
                    "title": "Team Market",
                    "body": f"**{team_name}** has acquired a seat in {championship_name}. {reason}.",
                }
            )
        elif event_type in {"sold", "lost", "moved"}:
            candidates.append(
                {
                    "title": "Team Market",
                    "body": f"**{team_name}** has {event_type} its seat in {championship_name}. {reason}.",
                }
            )
    for item in recent_team_storylines(save_name, world_year, limit=10):
        team_name = str(item.get("team_name", "Independent")).strip() or "Independent"
        driver_name = str(item.get("driver_name", "Unknown")).strip() or "Unknown"
        championship_name = str(item.get("championship_name", "a championship")).strip() or "a championship"
        reason = str(item.get("reason", "season performance")).strip() or "season performance"
        decision = str(item.get("decision", "")).strip().casefold()
        reputation = item.get("reputation", "-")
        if decision == "released":
            candidates.append(
                {
                    "title": "Team Market",
                    "body": (
                        f"**{team_name}** has released **{driver_name}** after {reason} in "
                        f"{championship_name}. Team reputation: {reputation}."
                    ),
                }
            )
        elif decision == "retained":
            candidates.append(
                {
                    "title": "Team Retention",
                    "body": (
                        f"**{team_name}** is retaining **{driver_name}** after {reason} in "
                        f"{championship_name}. Team reputation: {reputation}."
                    ),
                }
            )
    return candidates


def build_world_news_items(
    save_name: str,
    player_championship: dict[str, Any] | None = None,
    watch_drivers: list[str] | None = None,
    rising_driver: str | None = None,
) -> list[dict[str, str]]:
    save_data = load_save(save_name) or {}
    world_year = get_world_year(save_name)
    completed_year = max(0, int(world_year) - 1)
    items: list[dict[str, str]] = []

    best_driver = best_driver_in_world(save_name)
    if best_driver:
        items.append(
            {
                "title": "Best Driver In The World",
                "body": (
                    f"**{best_driver.get('name', 'Unknown')}** leads the world right now with MMR "
                    f"{best_driver.get('mmr', '-')} in {best_driver.get('primary_style', 'Unassigned')}."
                ),
            }
        )

    tier_five_champions = latest_tier_champions(save_name, completed_year, tier=5) if completed_year > 0 else []
    if tier_five_champions:
        champion = tier_five_champions[0]
        items.append(
            {
                "title": f"{champion.get('championship_name', 'Tier 5')} Champion",
                "body": (
                    f"**{champion.get('driver_name', 'Unknown')}** is the latest top-tier champion, carrying "
                    f"{champion.get('style', 'Unknown')} momentum into {world_year}."
                ),
            }
        )

    tier_four_champions = latest_tier_champions(save_name, completed_year, tier=4) if completed_year > 0 else []
    if tier_four_champions:
        champion = tier_four_champions[0]
        items.append(
            {
                "title": f"{champion.get('championship_name', 'Tier 4')} Winner",
                "body": (
                    f"**{champion.get('driver_name', 'Unknown')}** broke through in "
                    f"{champion.get('championship_name', 'Tier 4')} and is pushing toward the top rung."
                ),
            }
        )

    rookies = top_rookies_for_year(save_name, world_year, limit=5)
    if rookies:
        rookie = rookies[0]
        items.append(
            {
                "title": "Top Rookie Entering",
                "body": (
                    f"**{rookie.get('name', 'Unknown')}** is one of the most talked-about first-year drivers entering "
                    f"the world this season."
                ),
            }
        )

    if len(rookies) > 1:
        items.append(
            {
                "title": "Rookie Class",
                "body": (
                    f"**{rookies[0].get('name', 'Unknown')}** headlines a rookie group that also includes "
                    f"**{rookies[1].get('name', 'Unknown')}** entering the ladder this year."
                ),
            }
        )

    retiring_drivers = notable_retirements(save_name, completed_year, limit=5) if completed_year > 0 else []
    if retiring_drivers:
        retirement = retiring_drivers[0]
        items.append(
            {
                "title": "Retirement Watch",
                "body": (
                    f"**{retirement.get('name', 'Unknown')}** steps away after {retirement.get('seasons_completed', 0)} seasons, "
                    f"{retirement.get('championships', 0)} titles, and {retirement.get('wins', 0)} wins."
                ),
            }
        )

    season_opening_items = _season_opening_wrap_news_candidates(
        save_name,
        save_data,
        world_year,
        completed_year,
        player_championship=player_championship,
    )
    if season_opening_items:
        items.extend(season_opening_items)

    recent_race_items = _recent_race_news_candidates(save_data, player_championship=player_championship)
    if recent_race_items:
        items.append(random.choice(recent_race_items))

    incident_items = _incident_news_candidates(save_data, player_championship=player_championship)
    if incident_items:
        items.append(random.choice(incident_items))

    title_fight_items = _title_fight_news_candidates(save_data, player_championship=player_championship)
    if title_fight_items:
        items.extend(title_fight_items)

    performance_items = _performance_news_candidates(save_name, save_data, player_championship=player_championship)
    if performance_items:
        items.extend(performance_items)

    team_form_items = _team_form_news_candidates(save_data, player_championship=player_championship)
    if team_form_items:
        items.extend(team_form_items)

    pressure_items = _upcoming_pressure_news_candidates(save_data, player_championship=player_championship)
    if pressure_items:
        items.extend(pressure_items)

    underdog_items = _underdog_news_candidates(save_data, player_championship=player_championship)
    if underdog_items:
        items.extend(underdog_items)

    team_market_items = _team_market_news_candidates(save_name, completed_year)
    if team_market_items:
        items.extend(random.sample(team_market_items, min(2, len(team_market_items))))

    clinched_items = _championship_clinch_news_candidates(save_name, completed_year)
    if clinched_items:
        items.extend(clinched_items)

    active_championships = list_active_world_championships(save_name)
    if active_championships:
        top_series = active_championships[0]
        items.append(
            {
                "title": "World Calendar",
                "body": (
                    f"The world is carrying {len(active_championships)} active championships this season. "
                    f"One of the headline series is **{top_series.get('name', 'Unknown')}**."
                ),
            }
        )

    player_team_offer = save_data.get("player_team_offer") if isinstance(save_data.get("player_team_offer"), dict) else {}
    player_team_name = str(player_team_offer.get("team_name", "")).strip()
    player_team_philosophy = str(player_team_offer.get("team_philosophy", "")).strip()
    player_team_trajectory = str(player_team_offer.get("team_trajectory", "")).strip()
    player_team_reason = str(player_team_offer.get("team_offer_reason", "")).strip()
    if player_team_name:
        items.append(
            {
                "title": "Inside Your Garage",
                "body": _player_team_identity_news_body(
                    player_team_name,
                    player_team_philosophy,
                    player_team_trajectory,
                    player_team_reason,
                ),
            }
        )

    if watch_drivers:
        watch_names = [str(name).strip() for name in watch_drivers if str(name).strip()]
        if watch_names:
            if len(watch_names) >= 2:
                body = (
                    f"**{watch_names[0]}** and **{watch_names[1]}** look like the biggest threats in your current championship."
                )
            else:
                body = f"**{watch_names[0]}** looks like the biggest threat in your current championship."
            items.append({"title": "Championship Threats", "body": body})

    if rising_driver:
        items.append(
            {
                "title": "Driver On The Way Up",
                "body": f"**{rising_driver}** has just climbed into this level and could shake up the order quickly.",
            }
        )

    interview_items = _interview_news_candidates(
        watch_drivers=watch_drivers,
        rising_driver=rising_driver,
        recent_race_items=recent_race_items,
        best_driver=best_driver,
    )
    if interview_items:
        items.extend(interview_items)

    if not items:
        items.append(
            {
                "title": "World News",
                "body": f"The {world_year} season is getting underway across the ladder.",
            }
        )

    deduped: list[dict[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for item in items:
        key = (str(item.get("title", "")).strip(), str(item.get("body", "")).strip())
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        deduped.append(item)

    if len(deduped) <= 3:
        return deduped
    return random.sample(deduped, 3)


def _player_team_identity_news_body(
    team_name: str,
    philosophy: str,
    trajectory: str,
    offer_reason: str,
) -> str:
    normalized = str(philosophy).strip().casefold()
    trend = str(trajectory).strip().casefold()
    trend_text = {
        "rising": "The mood is that the program is moving forward.",
        "falling": "There is pressure to stop the slide quickly.",
        "rebuilding": "The team is treating this phase as a reset and rebuild.",
        "stable": "The garage looks calm and measured heading into the next round.",
    }.get(trend, "")
    bodies = {
        "win now": f"**{team_name}** is carrying a win-now tone inside the garage. Every clean chance to score big matters immediately.",
        "driver continuity": f"**{team_name}** is leaning into continuity. The message is trust the process, keep the group together, and let the season build.",
        "technical excellence": f"**{team_name}** is talking about execution more than noise. Precision, feedback, and detail are setting the tone.",
        "underdog grit": f"**{team_name}** is embracing the underdog role. The goal is to make larger teams uncomfortable over a full weekend.",
        "rookie pipeline": f"**{team_name}** is framing the season around growth. Development and upside are being treated as real competitive assets.",
        "balanced": f"**{team_name}** is aiming for a measured season. The focus is clean weekends, solid points, and building momentum without forcing it.",
    }
    base = bodies.get(normalized, f"**{team_name}** is setting the tone for your season from inside the garage.")
    additions = []
    if trend_text:
        additions.append(trend_text)
    if offer_reason:
        additions.append(offer_reason)
    return " ".join([base, *additions]).strip()


def create_world_sim_progress(save_name: str, championship: dict[str, Any], player_schedule: list[dict[str, Any]]) -> dict[str, Any]:
    save_data = load_save(save_name) or {}
    game = str(save_data.get("game", "iRacing"))
    excluded_id = str(championship.get("id", "")).strip()
    instances = build_world_championship_instances(load_world_championships(game, save_data.get("career_path_id")), excluded_id)
    progress_instances: list[dict[str, Any]] = []

    for instance in instances:
        tier = int(instance.get("Tier", 1) or 1)
        style = str(instance.get("Style", "Sports Car"))
        schedule_style = str(instance.get("_schedule_style", style)).strip()
        num_races = int(instance.get("Num of Races", 4) or 4)
        field_size = world_championship_field_size(instance)
        schedule = build_schedule(
            load_tracks(
                schedule_style,
                tier,
                game,
                save_name,
                _custom_track_selection(instance.get("championship") or instance),
            ),
            num_races,
            game=game,
            championship_style=schedule_style,
            minimum_garages=field_size,
        )
        progress_instances.append(
            {
                "championship": instance,
                "schedule": schedule,
                "standings": [],
                "current_race": 0,
                "finalized": False,
                "field_size": field_size,
            }
        )

    progress_instances, summary = populate_world_sim_instances(save_name, progress_instances)
    for instance in progress_instances:
        championship_data = instance.get("championship") or {}
        standings = instance.get("standings") or []
        style = str(championship_data.get("Style", "Sports Car"))
        set_ai_primary_style_on_first_championship(save_name, standings, style)
        set_current_championship_for_standings(save_name, standings, championship_data)

    return {
        "instances": progress_instances,
        "complete": not progress_instances,
        "summary": summary,
        "last_summary": _empty_world_sim_summary(),
    }


def prepare_offseason_championship_select(save_name: str, player_names: list[str]) -> list[dict[str, Any]]:
    refresh_shared_content_snapshot(save_name)
    save_data = load_save(save_name) or {}
    game = str(save_data.get("game", "iRacing"))
    career_path_id = save_data.get("career_path_id")
    championship_rows = _championship_rows_for_game(game, career_path_id)
    championships = load_world_championships(game, career_path_id)
    current_team_offer = save_data.get("player_team_offer") if isinstance(save_data.get("player_team_offer"), dict) else {}
    protected_team_keys = {
        str(current_team_offer.get("team_key", "")).strip()
    } if current_team_offer else set()
    current_world_year = get_world_year(save_name)
    if int(save_data.get("team_market_year", 0) or 0) == current_world_year:
        market_summary = save_data.get("team_market_summary", {})
    else:
        market_summary = run_offseason_team_seat_market(save_name, championships, protected_team_keys=protected_team_keys)
        update_save(save_name, {"team_market_year": current_world_year, "team_market_summary": market_summary})
    selection_driver_rows = active_driver_rows_for_selection(save_name)
    available_ai_rows = active_world_ai_rows(save_name)
    reputation_map = team_reputation_map(save_name)
    existing_seats = existing_team_seats_by_championship(save_name)
    style_limits = {
        style: player_entry_prestige_for_style(
            save_name,
            player_names,
            style,
            championship_rows=championship_rows,
            game=game,
            driver_rows=selection_driver_rows,
            reputation_map=reputation_map,
            existing_seats_by_championship=existing_seats,
        )
        for style in ("Sports Car", "Oval", "Open Wheel", "Rallycross")
    }
    reserved_instances: list[dict[str, Any]] = []
    used_driver_ids: set[str] = set()
    used_driver_names: set[str] = set()

    for instance in build_world_championship_instances(championships, ""):
        championship = dict(instance)
        style = str(championship.get("Style", "")).strip()
        championship_prestige = int(championship.get("Prestige", 0) or 0)
        player_limit = max(1, int(style_limits.get(style, 0) or 0))
        if championship_prestige <= player_limit:
            continue

        tier = int(championship.get("Tier", 1) or 1)
        schedule_style = str(championship.get("_schedule_style", style)).strip()
        num_races = int(championship.get("Num of Races", 4) or 4)
        field_size = world_championship_field_size(championship)
        schedule = build_schedule(
            load_tracks(
                schedule_style,
                tier,
                game,
                save_name,
                _custom_track_selection(instance.get("championship") or instance),
            ),
            num_races,
            game=game,
            championship_style=schedule_style,
            minimum_garages=field_size,
        )
        standings, generated_rookies = build_ai_world_standings(
            save_name,
            championship,
            field_size,
            used_driver_ids,
            used_driver_names,
            available_ai_rows,
        )
        if generated_rookies:
            available_ai_rows = active_world_ai_rows(save_name)
        standings = assign_teams_to_standings(standings, championship, save_name)
        set_ai_primary_style_on_first_championship(save_name, standings, style)
        set_current_championship_for_standings(save_name, standings, championship)
        reserved_instances.append(
            {
                "championship": championship,
                "schedule": schedule,
                "standings": standings,
                "current_race": 0,
                "finalized": False,
                "field_size": field_size,
                "reserved_preseason": True,
            }
        )

    update_save(
        save_name,
        {
            "offseason_world_instances": reserved_instances,
            "offseason_player_style_limits": style_limits,
            "team_market_summary": market_summary,
        },
    )
    return reserved_instances


def _populate_world_with_player_championship(
    save_name: str,
    player_championship: dict[str, Any],
    player_schedule: list[dict[str, Any]],
    player_standings: list[dict[str, Any]],
    player_field_size: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    save_data = load_save(save_name) or {}
    game = str(save_data.get("game", "iRacing"))
    excluded_id = str(player_championship.get("id", "")).strip()
    world_instances = build_world_championship_instances(load_world_championships(game, save_data.get("career_path_id")), excluded_id)
    progress_instances: list[dict[str, Any]] = []
    preseason_reserved_instances = [
        instance
        for instance in list(save_data.get("offseason_world_instances") or [])
        if str((instance.get("championship") or {}).get("id", "")).strip() != excluded_id
    ]
    reserved_ids = {
        str((instance.get("championship") or {}).get("id", "")).strip()
        for instance in preseason_reserved_instances
    }

    player_instance = {
        "championship": dict(player_championship),
        "schedule": list(player_schedule),
        "standings": list(player_standings),
        "current_race": 0,
        "finalized": False,
        "field_size": player_field_size,
        "player_instance": True,
    }
    progress_instances.append(player_instance)
    progress_instances.extend(preseason_reserved_instances)

    for instance in world_instances:
        if str((instance.get("championship") or instance).get("id", "")).strip() in reserved_ids:
            continue
        tier = int(instance.get("Tier", 1) or 1)
        style = str(instance.get("Style", "Sports Car"))
        schedule_style = str(instance.get("_schedule_style", style)).strip()
        num_races = int(instance.get("Num of Races", 4) or 4)
        field_size = world_championship_field_size(instance)
        schedule = build_schedule(
            load_tracks(
                schedule_style,
                tier,
                game,
                save_name,
                _custom_track_selection(instance.get("championship") or instance),
            ),
            num_races,
            game=game,
            championship_style=schedule_style,
            minimum_garages=field_size,
        )
        progress_instances.append(
            {
                "championship": instance,
                "schedule": schedule,
                "standings": [],
                "current_race": 0,
                "finalized": False,
                "field_size": field_size,
            }
        )

    populated_instances, summary = populate_world_sim_instances(save_name, progress_instances)
    for instance in populated_instances:
        championship_data = instance.get("championship") or {}
        instance["standings"] = assign_teams_to_standings(
            list(instance.get("standings") or []),
            championship_data,
            save_name,
        )

    populated_player = next((instance for instance in populated_instances if instance.get("player_instance")), None)
    player_result_standings = list((populated_player or {}).get("standings") or player_standings)

    world_only_instances: list[dict[str, Any]] = []
    for instance in populated_instances:
        championship_data = instance.get("championship") or {}
        standings = instance.get("standings") or []
        style = str(championship_data.get("Style", "Sports Car"))
        set_ai_primary_style_on_first_championship(save_name, standings, style)
        set_current_championship_for_standings(save_name, standings, championship_data)
        if not instance.get("player_instance"):
            world_only_instances.append(instance)

    return player_result_standings, {
        "instances": world_only_instances,
        "complete": not world_only_instances,
        "summary": summary,
        "last_summary": _empty_world_sim_summary(),
    }


def run_world_simulation_step(state: dict[str, Any], finish_remaining: bool = False) -> dict[str, Any]:
    championship = state.get("championship") or {}
    if not state.get("save_name"):
        return state
    progress = state.get("world_sim_progress")
    if not progress:
        progress = create_world_sim_progress(state["save_name"], championship, state.get("schedule") or [])
    instances = list(progress.get("instances") or [])
    if not instances:
        progress["complete"] = True
        progress["last_summary"] = _empty_world_sim_summary()
        state["world_sim_progress"] = progress
        _persist_active_state(state)
        return state

    if finish_remaining:
        target_ordinal = 9999
    else:
        player_schedule = state.get("schedule") or []
        if int(state.get("current_race", 0)) >= len(player_schedule):
            finish_remaining = True
            target_ordinal = 9999
        else:
            target_index = min(max(0, int(state.get("current_race", 0))), len(player_schedule) - 1)
            target_ordinal = _date_to_ordinal(str(player_schedule[target_index].get("date", "")))

    step_summary = _empty_world_sim_summary()
    all_complete = True
    for instance in instances:
        schedule = instance.get("schedule") or []
        standings = instance.get("standings") or []
        current_race = int(instance.get("current_race", 0) or 0)
        was_complete = current_race >= len(schedule)
        while current_race < len(schedule):
            race = schedule[current_race]
            race_ordinal = _date_to_ordinal(str(race.get("date", "")))
            if not finish_remaining and race_ordinal > target_ordinal:
                break

            finish_order = world_simulated_finish_order(
                state["save_name"],
                standings,
                str(state.get("game", "iRacing") or "iRacing"),
            )
            _, result_rows = apply_points_by_class(standings, finish_order)
            update_ratings_after_race(state["save_name"], instance["championship"], standings, result_rows)
            record_driver_race_results(state["save_name"], instance["championship"], race, standings, result_rows)
            schedule[current_race]["completed"] = True
            schedule[current_race]["full_results"] = result_rows
            current_race += 1
            step_summary["races"] += 1

        instance["schedule"] = schedule
        instance["standings"] = standings
        instance["current_race"] = current_race
        if current_race < len(schedule):
            all_complete = False
        elif not was_complete:
            step_summary["championships"] += 1

    progress["instances"] = instances
    progress["complete"] = all_complete
    progress["last_summary"] = step_summary
    progress["summary"] = _merge_world_sim_summary(progress.get("summary", {}), step_summary)
    state["world_sim_progress"] = progress
    _persist_active_state(state)
    return state


def simulate_world_history_year(save_name: str, record_race_history: bool = False) -> dict[str, int]:
    progress = create_world_sim_progress(save_name, {}, [])
    summary = dict(progress.get("summary", _empty_world_sim_summary()))

    for instance in progress.get("instances", []):
        schedule = instance.get("schedule") or []
        standings = instance.get("standings") or []
        current_race = int(instance.get("current_race", 0) or 0)

        while current_race < len(schedule):
            finish_order = world_simulated_finish_order(
                save_name,
                standings,
                str((instance.get("championship") or {}).get("Game", "iRacing") or "iRacing"),
            )
            _, result_rows = apply_points_by_class(standings, finish_order)
            update_ratings_after_race(save_name, instance.get("championship") or {}, standings, result_rows, persist=False)
            if record_race_history:
                record_driver_race_results(save_name, instance.get("championship") or {}, schedule[current_race], standings, result_rows)
            schedule[current_race]["completed"] = True
            schedule[current_race]["full_results"] = result_rows
            current_race += 1
            summary["races"] += 1

        instance_summary = finalize_driver_season(
            save_name,
            instance.get("championship") or {},
            standings,
            advance_world_year=False,
        )
        summary = _merge_world_sim_summary(summary, instance_summary)
        summary["championships"] += 1

    advance_world_year(save_name, 1)
    return summary


def save_needs_world_setup(save_data: dict[str, Any] | None) -> bool:
    if not isinstance(save_data, dict):
        return True
    return not bool(save_data.get("world_setup_complete", False))


def championship_cars(championship: dict[str, Any], game: str = "iRacing") -> list[dict[str, str]]:
    return _cars_for_championship_rows(_championship_group_rows(championship, game), game)


def championship_classes(championship: dict[str, Any], game: str = "iRacing") -> list[str]:
    configured_classes = championship.get("_class_names")
    if isinstance(configured_classes, list) and configured_classes:
        return [str(class_name).strip() for class_name in configured_classes if str(class_name).strip()]
    return _class_names_for_rows(_championship_group_rows(championship, game), game)


def driver_class_name(driver: dict[str, Any]) -> str:
    return str(driver.get("class_name", "")).strip() or "Overall"


def get_eligible_player_cars(
    championship: dict[str, Any],
    game: str = "iRacing",
    save_name: str | None = None,
) -> list[dict[str, str]]:
    owned_cars = load_owned_cars(game, save_name)
    eligible_ids = {
        str(car.get("id", "")).strip()
        for car in _cars_for_championship_rows(_player_entry_rows(championship, game), game)
    }
    return [car for car in owned_cars if str(car.get("id", "")).strip() in eligible_ids]


def select_player_car(
    championship: dict[str, Any],
    game: str = "iRacing",
    save_name: str | None = None,
) -> dict[str, str] | None:
    eligible_cars = get_eligible_player_cars(championship, game, save_name)
    if not eligible_cars:
        return None
    return random.choice(eligible_cars)


def championship_has_eligible_player_car(
    championship: dict[str, Any],
    game: str = "iRacing",
    save_name: str | None = None,
) -> bool:
    return select_player_car(championship, game, save_name) is not None


def _choose_weather(style: str) -> str:
    if str(style).strip().casefold() == "oval":
        roll = random.random()
        if roll < 0.45:
            return "Sunny"
        if roll < 0.70:
            return "Cloudy"
        if roll < 0.90:
            return "Overcast"
        return "Foggy"

    roll = random.random()
    if roll < 0.38:
        return "Sunny"
    if roll < 0.69:
        return "Cloudy"
    if roll < 0.90:
        return "Overcast"
    if roll < 0.97:
        return "Foggy"
    if roll < 0.995:
        return "Light Rain"
    return "Heavy Rain"


def _time_slots_for_style(style: str) -> list[str]:
    normalized = str(style).strip().casefold()
    if normalized == "sports car":
        return TIME_OF_DAY
    return ["Morning", "Afternoon", "Evening"]


def load_tracks(
    style: str,
    tier: int,
    game: str = "iRacing",
    save_name: str | None = None,
    selected_track_keys: set[str] | None = None,
) -> list[dict[str, str]]:
    """Load owned tracks matching the championship's mapped track style and tier."""
    tracks = []
    target_style = _track_style_for_championship(style)
    _owned_cars, owned_tracks = _owned_assets_for_save(game, save_name)
    owned_track_names = {value.casefold() for value in owned_tracks}
    normalized_game = str(game).strip().casefold()
    with TRACKS_CSV.open(newline="", encoding="utf-8") as file_obj:
        reader = csv.DictReader(file_obj)
        for row in reader:
            if str(row.get("Game", "")).strip().casefold() not in {"", normalized_game}:
                continue
            if str(row.get("Track", "")).strip().casefold() not in owned_track_names:
                continue
            track_key = f"{row.get('Track', '').strip()}::{row.get('Layout', '').strip()}"
            if selected_track_keys and track_key not in selected_track_keys:
                continue
            row_style = row["Style"].strip().casefold()
            if not selected_track_keys:
                if target_style == "mixed_open_wheel":
                    if row_style not in {"road", "oval"}:
                        continue
                elif target_style == "mixed_oval":
                    if row_style not in {"road", "oval"}:
                        continue
                elif row_style != target_style:
                    continue
            tiers_raw = row.get("My_Tiers", "")
            tier_list = [value.strip() for value in tiers_raw.split(".") if value.strip()]
            if selected_track_keys or str(tier) in tier_list:
                tracks.append(row)

    return tracks


def _max_available_tier() -> int:
    return 5


def _custom_track_selection(championship: dict[str, Any]) -> set[str] | None:
    raw = str(championship.get("Track_Selection", "")).strip()
    if not raw:
        return None
    selected = {value.strip() for value in raw.split("||") if value.strip()}
    return selected or None


def build_schedule(
    tracks: list[dict[str, str]],
    num_races: int,
    game: str = "iRacing",
    championship_style: str = "",
    minimum_garages: int = 0,
) -> list[dict[str, Any]]:
    """Pick tracks randomly and assign race details."""
    if minimum_garages > 0:
        tracks = [track for track in tracks if _track_has_enough_garages(track, minimum_garages)]
    if not tracks:
        return []

    style_key = _track_style_for_championship(championship_style)
    if style_key in {"mixed_open_wheel", "mixed_oval"}:
        road_tracks = [track for track in tracks if str(track.get("Style", "")).strip().casefold() == "road"]
        oval_tracks = [track for track in tracks if str(track.get("Style", "")).strip().casefold() == "oval"]
        major_pool = road_tracks if style_key == "mixed_open_wheel" else oval_tracks
        minor_pool = oval_tracks if style_key == "mixed_open_wheel" else road_tracks
        major_count = max(0, min(num_races, round(num_races * 0.8)))
        minor_count = max(0, num_races - major_count)

        def _pick_tracks(pool: list[dict[str, str]], count: int) -> list[dict[str, str]]:
            if not pool or count <= 0:
                return []
            picked = pool.copy()
            random.shuffle(picked)
            while len(picked) < count:
                extra = pool.copy()
                random.shuffle(extra)
                picked.extend(extra)
            return picked[:count]

        selected = _pick_tracks(major_pool, major_count) + _pick_tracks(minor_pool, minor_count)
        if len(selected) < num_races:
            fallback = tracks.copy()
            random.shuffle(fallback)
            while len(selected) < num_races:
                if not fallback:
                    fallback = tracks.copy()
                    random.shuffle(fallback)
                selected.append(fallback.pop(0))
        random.shuffle(selected)
    else:
        pool = tracks.copy()
        random.shuffle(pool)

        while len(pool) < num_races:
            pool.extend(tracks)

        selected = pool[:num_races]
    schedule = []
    season_slots = len(MONTHS) * 28
    if num_races <= season_slots:
        date_slots = sorted(random.sample(range(season_slots), num_races))
    else:
        date_slots = list(range(season_slots))
        while len(date_slots) < num_races:
            date_slots.extend(range(season_slots))
        date_slots = sorted(date_slots[:num_races])

    for index, (track, date_slot) in enumerate(zip(selected, date_slots)):
        month_index = min(len(MONTHS) - 1, date_slot // 28)
        day = (date_slot % 28) + 1
        is_ams2 = str(game).strip().casefold() == "ams2"
        race_weather = generate_ams2_weather(track.get("Style", "")) if is_ams2 else _choose_weather(track.get("Style", ""))
        schedule.append(
            {
                "race_num": index + 1,
                "track": track["Track"],
                "layout": track["Layout"],
                "track_id": int(track.get("Iracing_ID", 0) or 0),
                "country": track.get("Country", ""),
                "garages": _track_garage_count(track),
                "time_of_day": random.choice(_time_slots_for_style(track.get("Style", ""))),
                "weather": race_weather,
                "practice_weather": generate_ams2_weather(track.get("Style", "")) if is_ams2 else race_weather,
                "qualifying_weather": generate_ams2_weather(track.get("Style", "")) if is_ams2 else race_weather,
                "date": f"{day} {MONTHS[month_index]}",
                "completed": False,
                "result": None,
            }
        )

    return schedule


def _track_garage_count(track: dict[str, str]) -> int:
    garages_raw = str(track.get("Garages", "")).strip()
    if not garages_raw:
        return 0
    try:
        return int(float(garages_raw))
    except ValueError:
        return 0


def _track_has_enough_garages(track: dict[str, str], total_drivers: int) -> bool:
    if not str(track.get("Garages", "")).strip():
        return True
    garages = _track_garage_count(track)
    if garages <= 0:
        return True
    return garages >= total_drivers


def assign_driver_classes(
    standings: list[dict[str, Any]], championship: dict[str, Any], player_names: list[str], player_car: dict[str, str]
) -> list[dict[str, Any]]:
    multiclass = str(championship.get("Multiclass", "no")).strip().casefold() == "yes"
    if not multiclass:
        class_name = str(championship.get("_player_class_name", "")).strip() or str(player_car.get("Car class", "")).strip() or str(player_car.get("Car", "")).strip() or "Overall"
        for driver in standings:
            driver["class_name"] = class_name
        return standings

    classes = championship_classes(championship)
    player_class = str(championship.get("_player_class_name", "")).strip() or str(player_car.get("Car class", "")).strip() or str(player_car.get("Car", "")).strip()
    class_tiers = championship.get("_class_tiers", {})
    if isinstance(class_tiers, dict) and len(class_tiers) > 1:
        player_set = set(player_names)
        for driver in standings:
            if driver["name"] in player_set:
                driver["class_name"] = player_class
            else:
                driver["class_name"] = str(driver.get("class_name", "")).strip() or player_class or "Overall"
        return standings

    all_classes = classes or [player_class]
    if player_class and all(class_name.casefold() != player_class.casefold() for class_name in all_classes):
        all_classes.insert(0, player_class)

    player_set = set(player_names)
    class_targets = _random_multiclass_class_targets(
        all_classes,
        len(standings),
        player_class,
        len(player_set),
        championship.get("_class_car_counts"),
    )
    class_slots: list[str] = []
    for class_name in all_classes:
        human_count = len(player_set) if class_name == player_class else 0
        class_slots.extend([class_name] * max(0, class_targets.get(class_name, 0) - human_count))
    random.shuffle(class_slots)

    ai_index = 0
    for driver in standings:
        if driver["name"] in player_set:
            driver["class_name"] = player_class
        else:
            driver["class_name"] = class_slots[ai_index] if ai_index < len(class_slots) else random.choice(all_classes)
            ai_index += 1
    return standings


def _random_multiclass_class_targets(
    class_names: list[str],
    total_drivers: int,
    player_class: str,
    player_count: int,
    class_car_counts: dict[str, Any] | None = None,
) -> dict[str, int]:
    unique_classes = []
    seen: set[str] = set()
    for class_name in class_names:
        cleaned = class_name.strip()
        if cleaned and cleaned.casefold() not in seen:
            seen.add(cleaned.casefold())
            unique_classes.append(cleaned)

    if not unique_classes:
        return {player_class or "Overall": total_drivers}

    configured_targets = {
        class_name: int(class_car_counts.get(class_name, 0) or 0)
        for class_name in unique_classes
        if isinstance(class_car_counts, dict) and int(class_car_counts.get(class_name, 0) or 0) > 0
    }
    if configured_targets:
        targets = {class_name: max(0, configured_targets.get(class_name, 0)) for class_name in unique_classes}
        if player_class:
            matching_player_class = next(
                (class_name for class_name in unique_classes if class_name.casefold() == player_class.casefold()),
                player_class,
            )
            targets[matching_player_class] = max(targets.get(matching_player_class, 0), player_count)
        assigned = sum(targets.values())
        while assigned > total_drivers:
            reducible = [class_name for class_name, count in targets.items() if count > 1 and count > player_count]
            if not reducible:
                break
            class_name = max(reducible, key=lambda name: targets[name])
            targets[class_name] -= 1
            assigned -= 1
        return targets

    class_count = len(unique_classes)
    minimum_per_class = 8 if total_drivers >= class_count * 8 else max(1, total_drivers // class_count)
    targets = {class_name: minimum_per_class for class_name in unique_classes}
    max_per_class = max(minimum_per_class, (total_drivers + class_count - 1) // class_count)

    if player_class:
        matching_player_class = next(
            (class_name for class_name in unique_classes if class_name.casefold() == player_class.casefold()),
            player_class,
        )
        targets[matching_player_class] = max(targets.get(matching_player_class, 0), player_count)
        max_per_class = max(max_per_class, targets[matching_player_class])

    assigned = sum(targets.values())
    while assigned > total_drivers:
        reducible = [class_name for class_name, count in targets.items() if count > 1]
        if not reducible:
            break
        class_name = random.choice(reducible)
        targets[class_name] -= 1
        assigned -= 1

    remaining = max(0, total_drivers - assigned)
    for _ in range(remaining):
        expandable = [class_name for class_name, count in targets.items() if count < max_per_class]
        if not expandable:
            break
        targets[random.choice(expandable)] += 1

    return targets


def _opponent_count_for_championship(
    championship: dict[str, Any],
    player_names: list[str],
    player_car: dict[str, str],
) -> int:
    player_count = len([name for name in player_names if str(name).strip()])
    class_car_counts = championship.get("_class_car_counts")
    if isinstance(class_car_counts, dict):
        configured_total = sum(
            max(0, int(value or 0))
            for value in class_car_counts.values()
            if str(value).strip().lstrip("-").isdigit()
        )
        if configured_total > 0:
            return max(0, min(40, max(player_count, configured_total)) - player_count)
    try:
        max_grid_size = int(championship.get("Max_Opp", 4))
    except (TypeError, ValueError):
        max_grid_size = 4
    max_grid_size = max(player_count, max_grid_size)
    max_grid_size = min(40, max_grid_size)
    return max(0, max_grid_size - player_count)


def _apply_player_team_offer(
    standings: list[dict[str, Any]],
    player_names: list[str],
    player_team_offer: dict[str, Any] | None,
    game: str = "Any",
) -> list[dict[str, Any]]:
    if not standings or not isinstance(player_team_offer, dict):
        return standings
    team_name = str(player_team_offer.get("team_name", "")).strip()
    if not team_name:
        return standings
    team_id = str(player_team_offer.get("team_id", "")).strip()
    team_prestige = int(player_team_offer.get("team_prestige", 0) or 0)
    team_reputation = int(player_team_offer.get("team_reputation", team_prestige) or team_prestige)
    offer_game = str(player_team_offer.get("game", "") or player_team_offer.get("Game", "") or game or "Any").strip()
    team_key = str(player_team_offer.get("team_key", "")).strip() or (
        f"{offer_game.casefold()}|{team_id.casefold() or team_name.casefold()}"
    )
    player_set = {str(name).strip() for name in player_names if str(name).strip()}
    team_seat = 1
    for driver in standings:
        if str(driver.get("name", "")).strip() not in player_set:
            continue
        driver["team_id"] = team_id
        driver["team_key"] = team_key
        driver["team_name"] = team_name
        driver["team_seat"] = team_seat
        driver["team_prestige"] = team_prestige
        driver["team_reputation"] = team_reputation
        team_seat += 1
    return standings


def apply_points_by_class(
    standings: list[dict[str, Any]], finish_order_names: list[str]
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    standings_by_name = {driver["name"]: driver for driver in standings}
    class_positions: dict[str, int] = {}
    overall_positions: dict[str, int] = {}
    result_rows: list[dict[str, Any]] = []

    for overall_pos, driver_name in enumerate(finish_order_names, 1):
        driver = standings_by_name[driver_name]
        class_name = driver_class_name(driver)
        class_positions[class_name] = class_positions.get(class_name, 0) + 1
        class_pos = class_positions[class_name]
        points = POINTS_MAP.get(class_pos, 0)
        driver["points"] += points
        if class_pos == 1:
            driver["wins"] += 1
        overall_positions[driver_name] = overall_pos
        result_rows.append(
            {
                "overall_pos": overall_pos,
                "class_pos": class_pos,
                "driver_name": driver_name,
                "class_name": class_name,
                "team_name": str(driver.get("team_name", "")).strip(),
                "team_id": str(driver.get("team_id", "")).strip(),
                "team_key": str(driver.get("team_key", "")).strip(),
                "points_awarded": points,
            }
        )

    for row in result_rows:
        row["class_size"] = class_positions.get(str(row.get("class_name", "")).strip(), 0)

    return overall_positions, result_rows


def _player_class_results(result_rows: list[dict[str, Any]], player_names: list[str]) -> dict[str, int]:
    player_set = {str(name).strip() for name in player_names if str(name).strip()}
    results: dict[str, int] = {}
    for row in result_rows:
        driver_name = str(row.get("driver_name", "")).strip()
        if driver_name in player_set:
            results[driver_name] = int(row.get("class_pos", row.get("overall_pos", 0)) or 0)
    return results


def _player_class_sizes(result_rows: list[dict[str, Any]], player_names: list[str]) -> dict[str, int]:
    player_set = {str(name).strip() for name in player_names if str(name).strip()}
    sizes: dict[str, int] = {}
    for row in result_rows:
        driver_name = str(row.get("driver_name", "")).strip()
        if driver_name in player_set:
            sizes[driver_name] = int(row.get("class_size", 0) or 0)
    return sizes


def _rivalry_heat(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    heat: dict[str, int] = {}
    for raw_name, raw_stage in value.items():
        driver_name = str(raw_name).strip()
        if not driver_name:
            continue
        try:
            stage = int(raw_stage)
        except (TypeError, ValueError):
            continue
        if 1 <= stage <= 3:
            heat[driver_name] = stage
    return heat


def _career_mode(value: Any, player_names: list[str] | None = None) -> str:
    normalized = str(value or "").strip().casefold()
    if normalized == "rivals":
        return "Rivals"
    if normalized in {"co-op", "coop", "co op"}:
        return "Co-op"
    if normalized == "solo":
        return "Solo"
    return "Co-op" if len(player_names or []) > 1 else "Solo"


def _active_player_name(value: Any, player_names: list[str]) -> str:
    cleaned = str(value or "").strip()
    if cleaned in player_names:
        return cleaned
    return player_names[0] if player_names else ""


def _all_player_names(state: dict[str, Any], save_name: str = "") -> list[str]:
    return _normalize_player_names(state.get("all_players") or state.get("players"), save_name)


def _career_player_names(state: dict[str, Any], save_name: str = "") -> list[str]:
    if _career_mode(state.get("career_mode"), _all_player_names(state, save_name)) == "Rivals":
        active_player = _active_player_name(state.get("active_player_name"), _all_player_names(state, save_name))
        return [active_player] if active_player else []
    return _normalize_player_names(state.get("players"), save_name)


def _normalize_player_perspectives(
    value: Any,
    player_names: list[str],
    fallback_heat: Any = None,
) -> dict[str, dict[str, Any]]:
    raw = value if isinstance(value, dict) else {}
    perspectives: dict[str, dict[str, Any]] = {}
    fallback = _rivalry_heat(fallback_heat)
    for index, player_name in enumerate(player_names):
        existing = raw.get(player_name) if isinstance(raw.get(player_name), dict) else {}
        heat = _rivalry_heat(existing.get("rivalry_heat"))
        if not heat and index == 0:
            heat = dict(fallback)
        messages = [
            dict(message)
            for message in list(existing.get("messages") or [])
            if isinstance(message, dict)
        ]
        perspectives[player_name] = {
            "rivalry_heat": heat,
            "messages": messages,
        }
    return perspectives


def _merged_perspective_rivalry_heat(player_perspectives: dict[str, dict[str, Any]]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for perspective in player_perspectives.values():
        for driver_name, stage in _rivalry_heat(perspective.get("rivalry_heat")).items():
            merged[driver_name] = max(int(stage), int(merged.get(driver_name, 0) or 0))
    return merged


CAREER_SNAPSHOT_KEYS = (
    "players",
    "starting_difficulty",
    "tier",
    "unlocked_tier",
    "score",
    "championship",
    "player_car",
    "player_team_offer",
    "player_liveries",
    "watch_drivers",
    "rising_driver",
    "roster_path",
    "season_path",
    "schedule",
    "standings",
    "current_race",
    "world_sim_progress",
    "offseason_world_instances",
    "offseason_player_style_limits",
)


def _rivals_career_snapshot(state: dict[str, Any], player_name: str) -> dict[str, Any]:
    snapshot = {key: state.get(key) for key in CAREER_SNAPSHOT_KEYS if key in state}
    snapshot["players"] = [player_name] if player_name else _career_player_names(state, str(state.get("save_name", "")))
    snapshot["updated_at"] = datetime.now().isoformat(timespec="seconds")
    return snapshot


def _normalized_player_careers(value: Any, player_names: list[str]) -> dict[str, dict[str, Any]]:
    raw = value if isinstance(value, dict) else {}
    careers: dict[str, dict[str, Any]] = {}
    for player_name in player_names:
        existing = raw.get(player_name)
        careers[player_name] = dict(existing) if isinstance(existing, dict) else {}
    return careers


def hydrate_active_rivals_state(save_data: dict[str, Any] | None) -> dict[str, Any]:
    state = dict(save_data or {})
    all_players = _normalize_player_names(state.get("all_players") or state.get("players"), str(state.get("save_name", "")))
    if _career_mode(state.get("career_mode"), all_players) != "Rivals" or not all_players:
        return state

    active_player = _active_player_name(state.get("active_player_name"), all_players)
    raw_careers = state.get("player_careers")
    has_existing_career_slots = isinstance(raw_careers, dict) and any(
        isinstance(career, dict) and bool(career)
        for career in raw_careers.values()
    )
    careers = _normalized_player_careers(raw_careers, all_players)
    active_career = dict(careers.get(active_player) or {})
    if not active_career and not has_existing_career_slots and state.get("championship"):
        active_career = _rivals_career_snapshot({**state, "players": [active_player]}, active_player)
        careers[active_player] = active_career

    defaults = {
        "players": [active_player],
        "starting_difficulty": state.get("starting_difficulty", 75),
        "tier": 1,
        "unlocked_tier": 1,
        "score": 0,
        "championship": None,
        "player_car": None,
        "player_team_offer": None,
        "player_liveries": [],
        "watch_drivers": [],
        "rising_driver": None,
        "roster_path": "",
        "season_path": "",
        "schedule": [],
        "standings": [],
        "current_race": 0,
        "world_sim_progress": None,
        "offseason_world_instances": [],
        "offseason_player_style_limits": {},
    }
    for key in CAREER_SNAPSHOT_KEYS:
        state[key] = active_career.get(key, defaults.get(key))

    state["all_players"] = all_players
    state["players"] = [active_player]
    state["active_player_name"] = active_player
    state["player_careers"] = careers
    state["player_perspectives"] = _normalize_player_perspectives(
        state.get("player_perspectives"),
        all_players,
        state.get("rivalry_heat"),
    )
    state["rivalry_heat"] = _merged_perspective_rivalry_heat(state["player_perspectives"])
    state.setdefault("championship", None)
    state.setdefault("schedule", [])
    state.setdefault("standings", [])
    state.setdefault("current_race", 0)
    return state


def _rivals_save_payload(state: dict[str, Any]) -> dict[str, Any]:
    save_name = str(state.get("save_name", "")).strip()
    save_data = load_save(save_name) or {}
    all_players = _all_player_names(state, save_name) or _normalize_player_names(save_data.get("players"), save_name)
    active_player = _active_player_name(state.get("active_player_name") or save_data.get("active_player_name"), all_players)
    careers = _normalized_player_careers(save_data.get("player_careers"), all_players)
    careers[active_player] = _rivals_career_snapshot(state, active_player)
    player_perspectives = _normalize_player_perspectives(
        state.get("player_perspectives") or save_data.get("player_perspectives"),
        all_players,
        state.get("rivalry_heat") or save_data.get("rivalry_heat"),
    )
    payload = {
        "game": str(state.get("game") or save_data.get("game", "iRacing") or "iRacing"),
        "career_mode": "Rivals",
        "players": all_players,
        "all_players": all_players,
        "active_player_name": active_player,
        "player_careers": careers,
        "player_perspectives": player_perspectives,
        "rivalry_heat": _merged_perspective_rivalry_heat(player_perspectives),
        "messages": state.get("messages", save_data.get("messages", [])),
        "starting_difficulty": state.get("starting_difficulty", save_data.get("starting_difficulty", 75)),
        "world_setup_complete": state.get("world_setup_complete", save_data.get("world_setup_complete", True)),
        "world_year": state.get("world_year", save_data.get("world_year")),
    }
    active_career = careers.get(active_player) or {}
    for key in CAREER_SNAPSHOT_KEYS:
        if key == "players":
            continue
        payload[key] = active_career.get(key)
    payload.setdefault("championship", None)
    payload.setdefault("schedule", [])
    payload.setdefault("standings", [])
    payload.setdefault("current_race", 0)
    return payload


def _career_has_active_season(career: dict[str, Any]) -> bool:
    return isinstance(career.get("championship"), dict) and bool(career.get("schedule"))


def _career_season_is_complete(career: dict[str, Any]) -> bool:
    schedule = list(career.get("schedule") or [])
    if not schedule:
        return False
    current_race = int(career.get("current_race", 0) or 0)
    return current_race >= len(schedule) or all(bool(race.get("completed")) for race in schedule if isinstance(race, dict))


def rivals_waiting_for_drivers(save_name: str) -> list[str]:
    save_data = load_save(save_name) or {}
    all_players = _normalize_player_names(save_data.get("all_players") or save_data.get("players"), save_name)
    if _career_mode(save_data.get("career_mode"), all_players) != "Rivals":
        return []
    careers = _normalized_player_careers(save_data.get("player_careers"), all_players)
    waiting: list[str] = []
    for player_name in all_players:
        career = careers.get(player_name) or {}
        if not _career_has_active_season(career) or not _career_season_is_complete(career):
            waiting.append(player_name)
    return waiting


def rivals_all_active_seasons_complete(save_name: str) -> bool:
    save_data = load_save(save_name) or {}
    all_players = _normalize_player_names(save_data.get("all_players") or save_data.get("players"), save_name)
    if _career_mode(save_data.get("career_mode"), all_players) != "Rivals":
        return False
    careers = _normalized_player_careers(save_data.get("player_careers"), all_players)
    return bool(all_players) and all(
        _career_has_active_season(careers.get(player_name) or {})
        and _career_season_is_complete(careers.get(player_name) or {})
        for player_name in all_players
    )


def _season_outcome_for_player(state: dict[str, Any], player_names: list[str]) -> dict[str, Any]:
    standings = list(state.get("standings") or [])
    sorted_standings = sorted(standings, key=lambda driver: (driver["points"], driver["wins"]), reverse=True)
    player_positions = []
    for player_name in player_names:
        for position, driver in enumerate(sorted_standings, 1):
            if driver["name"] == player_name:
                player_positions.append(position)
                break

    average_position = sum(player_positions) / len(player_positions) if player_positions else float("inf")
    current_tier = int(state.get("tier", 1))
    unlocked_tier = _normalize_unlocked_tier(
        state.get("unlocked_tier", state.get("unlocked_tiers")),
        current_tier,
    )
    max_tier = _max_available_tier()

    if average_position <= 5:
        new_tier = min(current_tier + 1, max_tier)
        outcome = "promoted" if new_tier > current_tier else "stayed"
    elif average_position <= 10:
        new_tier = current_tier
        outcome = "stayed"
    else:
        new_tier = max(current_tier - 1, 1)
        outcome = "demoted" if new_tier < current_tier else "stayed"

    return {
        "average_position": average_position,
        "player_positions": player_positions,
        "old_tier": current_tier,
        "new_tier": new_tier,
        "old_unlocked_tier": unlocked_tier,
        "new_unlocked_tier": max(unlocked_tier, new_tier),
        "outcome": outcome,
    }


def _update_player_rivalry_perspectives(
    state: dict[str, Any],
    result_rows: list[dict[str, Any]],
    player_names: list[str],
) -> None:
    normalized_players = _normalize_player_names(player_names, str(state.get("save_name", "")))
    if not normalized_players:
        return

    perspectives = _normalize_player_perspectives(
        state.get("player_perspectives"),
        normalized_players,
        state.get("rivalry_heat"),
    )
    include_humans_as_opponents = _career_mode(state.get("career_mode"), normalized_players) == "Rivals"
    for player_name in normalized_players:
        perspective = perspectives.setdefault(player_name, {"rivalry_heat": {}, "messages": []})
        if include_humans_as_opponents:
            perspective_result_rows = result_rows
        else:
            perspective_result_rows = [
                row
                for row in result_rows
                if str(row.get("driver_name", "")).strip() == player_name
                or str(row.get("driver_name", "")).strip() not in normalized_players
            ]
        perspective_state = {
            **state,
            "rivalry_heat": perspective.get("rivalry_heat", {}),
            "messages": perspective.get("messages", []),
        }
        _update_rivalry_heat(perspective_state, perspective_result_rows, [player_name])
        perspective["rivalry_heat"] = _rivalry_heat(perspective_state.get("rivalry_heat"))
        perspective["messages"] = [
            dict(message)
            for message in list(perspective_state.get("messages") or [])
            if isinstance(message, dict)
        ]

    state["player_perspectives"] = perspectives
    state["rivalry_heat"] = _merged_perspective_rivalry_heat(perspectives)
    state["active_player_name"] = _active_player_name(state.get("active_player_name"), normalized_players)


def _rivalry_message_body(
    rival_name: str,
    player_name: str,
    championship_name: str,
    track_name: str,
    rival_finished_ahead: bool,
) -> str:
    context = f" after {track_name}" if track_name else ""
    championship_context = f" in {championship_name}" if championship_name else ""
    templates = [
        (
            f"{player_name},",
            "",
            f"We keep finding each other on track{championship_context}, and I do not think that is a coincidence.",
            "",
            f"{'I had you covered' if rival_finished_ahead else 'You got the better of me'}{context}, but this is not finished. "
            "Next time we are close, I am not leaving anything on the table.",
            "",
            rival_name,
        ),
        (
            f"{player_name},",
            "",
            f"That was another tight one{context}. You have my attention now.",
            "",
            f"The rest of the field can talk about points. I know exactly where you are on the timing screen, "
            f"and I expect we will be seeing plenty more of each other{championship_context}.",
            "",
            rival_name,
        ),
        (
            f"{player_name},",
            "",
            "Consider this a friendly warning from the other side of the garage lane.",
            "",
            "We are officially racing each other now. If you want position, you are going to have to earn every inch of it.",
            "",
            rival_name,
        ),
    ]
    seed_value = sum(ord(char) for char in rival_name) + len(championship_name) + len(track_name)
    return "\n".join(templates[seed_value % len(templates)])


def _add_rivalry_message(
    state: dict[str, Any],
    rival_name: str,
    player_name: str,
    rival_finished_ahead: bool,
) -> None:
    if "messages" not in state:
        return
    messages = [dict(message) for message in list(state.get("messages") or []) if isinstance(message, dict)]
    dedupe_key = f"rivalry-red:{rival_name.casefold()}"
    if any(str(message.get("dedupe_key", "")).strip() == dedupe_key for message in messages):
        return

    championship = state.get("championship") or {}
    championship_name = championship_pool_display_name(championship)
    schedule = list(state.get("schedule") or [])
    current_race = int(state.get("current_race", 0) or 0)
    race = schedule[current_race] if 0 <= current_race < len(schedule) else {}
    track_name = str(race.get("track", "")).strip()
    messages.append(
        {
            "id": uuid4().hex,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "category": "Rivalry",
            "sender": rival_name,
            "title": f"Message from {rival_name}",
            "body": _rivalry_message_body(
                rival_name,
                player_name,
                championship_name,
                track_name,
                rival_finished_ahead,
            ),
            "read": False,
            "dedupe_key": dedupe_key,
        }
    )
    state["messages"] = messages


def _update_rivalry_heat(
    state: dict[str, Any],
    result_rows: list[dict[str, Any]],
    player_names: list[str],
) -> None:
    player_set = {str(name).strip() for name in player_names if str(name).strip()}
    if not player_set:
        return

    heat = _rivalry_heat(state.get("rivalry_heat"))
    player_positions: dict[str, list[tuple[int, str]]] = {}
    class_opponents: dict[str, list[tuple[int, str]]] = {}
    race_opponents: set[str] = set()
    for row in result_rows:
        driver_name = str(row.get("driver_name", "")).strip()
        class_name = str(row.get("class_name", "")).strip() or "Overall"
        try:
            class_pos = int(row.get("class_pos", 0) or 0)
        except (TypeError, ValueError):
            class_pos = 0
        if not driver_name or class_pos <= 0:
            continue
        if driver_name in player_set:
            player_positions.setdefault(class_name, []).append((class_pos, driver_name))
        else:
            race_opponents.add(driver_name)
            class_opponents.setdefault(class_name, []).append((class_pos, driver_name))

    close_opponents: set[str] = set()
    adjacent_opponents: set[str] = set()
    rival_context: dict[str, tuple[str, bool]] = {}
    for class_name, class_player_positions in player_positions.items():
        ordered_opponents = sorted(class_opponents.get(class_name, []))
        for player_pos, player_name in class_player_positions:
            for class_pos, driver_name in ordered_opponents:
                if abs(class_pos - player_pos) == 1:
                    adjacent_opponents.add(driver_name)
                    rival_context[driver_name] = (player_name, class_pos < player_pos)
            ahead = [
                (class_pos, driver_name)
                for class_pos, driver_name in ordered_opponents
                if class_pos < player_pos
            ][-2:]
            behind = [
                (class_pos, driver_name)
                for class_pos, driver_name in ordered_opponents
                if class_pos > player_pos
            ][:2]
            selected = ahead + behind
            if len(selected) < 4:
                selected_names = {driver_name for _class_pos, driver_name in selected}
                remaining = sorted(
                    (
                        (abs(class_pos - player_pos), class_pos, driver_name)
                        for class_pos, driver_name in ordered_opponents
                        if driver_name not in selected_names
                    ),
                    key=lambda item: (item[0], item[1], item[2]),
                )
                selected.extend(
                    (class_pos, driver_name)
                    for _distance, class_pos, driver_name in remaining[: 4 - len(selected)]
                )
            close_opponents.update(driver_name for _class_pos, driver_name in selected)

    for driver_name in close_opponents:
        current_stage = heat.get(driver_name, 0)
        if current_stage == 0:
            heat[driver_name] = 1
        elif current_stage in {1, 2} and driver_name in adjacent_opponents:
            heat[driver_name] = current_stage + 1
            if current_stage == 2 and heat.get(driver_name) == 3:
                player_name, rival_finished_ahead = rival_context.get(driver_name, (next(iter(player_set)), False))
                _add_rivalry_message(state, driver_name, player_name, rival_finished_ahead)

    for driver_name in race_opponents - close_opponents:
        if heat.get(driver_name) == 2:
            heat[driver_name] = 1
        elif heat.get(driver_name) == 1:
            heat.pop(driver_name, None)

    state["rivalry_heat"] = heat


def _team_post_race_message_body(
    *,
    team_name: str,
    philosophy: str,
    trajectory: str,
    championship_name: str,
    track_name: str,
    summary_text: str,
    pressure_round: bool,
    teammate_note: str,
) -> str:
    normalized = str(philosophy).strip().casefold()
    trend = str(trajectory).strip().casefold()
    pressure_line = " This part of the season carries extra weight in the garage." if pressure_round else ""
    trend_line = {
        "rising": " The team feels like it is building momentum.",
        "falling": " The feedback will be sharper until the trend turns.",
        "rebuilding": " Even small gains still matter during this phase.",
    }.get(trend, "")
    base_lines = {
        "win now": f"{summary_text} {team_name} is not in the mood to let good opportunities drift away.",
        "driver continuity": f"{summary_text} {team_name} is leaning on trust, steadiness, and staying connected as a group.",
        "technical excellence": f"{summary_text} {team_name} is looking at the details, the execution, and where the lap-by-lap edge can improve.",
        "underdog grit": f"{summary_text} {team_name} is treating every point like something that had to be earned.",
        "rookie pipeline": f"{summary_text} {team_name} is focused on what was learned and how quickly it turns into a stronger next round.",
        "balanced": f"{summary_text} {team_name} is aiming to turn weekends like this into steady season momentum.",
    }
    opening = base_lines.get(normalized, f"{summary_text} {team_name} is reviewing the weekend and looking ahead.")
    track_clause = f" after {track_name}" if track_name else ""
    teammate_clause = f" {teammate_note}" if teammate_note else ""
    return f"{opening}{pressure_line}{trend_line}{teammate_clause} The attention now shifts back to {championship_name}{track_clause}.".strip()


def _add_team_post_race_message(
    state: dict[str, Any],
    result_rows: list[dict[str, Any]],
    player_names: list[str],
    player_results: dict[str, int],
    player_class_sizes: dict[str, int],
) -> None:
    messages = [dict(message) for message in list(state.get("messages") or []) if isinstance(message, dict)]
    team_offer = state.get("player_team_offer")
    if not isinstance(team_offer, dict):
        return
    team_name = str(team_offer.get("team_name", "")).strip() or "Team Management"
    philosophy = str(team_offer.get("team_philosophy", "")).strip() or "Balanced"
    trajectory = str(team_offer.get("team_trajectory", "")).strip() or "stable"
    dedupe_key = f"team-post-race:{int(state.get('current_race', 0) or 0)}"
    if any(str(message.get("dedupe_key", "")).strip() == dedupe_key for message in messages):
        return

    normalized_players = [str(name).strip() for name in player_names if str(name).strip()]
    if not normalized_players or not player_results:
        return
    best_finish = min(int(position) for position in player_results.values())
    best_class_size = max(1, max(int(player_class_sizes.get(name, 0) or 0) for name in player_results))
    if best_finish == 1:
        summary_text = "That was a proper statement result."
    elif best_finish <= 3:
        summary_text = "That was a podium-level weekend the garage can really use."
    elif best_finish <= 5:
        summary_text = "That was a competitive points run with useful pace underneath it."
    elif best_finish <= max(6, round(best_class_size * 0.5)):
        summary_text = "There were respectable points available, even if the weekend never fully opened up."
    else:
        summary_text = "That landed short of the level the garage wanted."

    championship = state.get("championship") or {}
    championship_name = championship_pool_display_name(championship)
    schedule = list(state.get("schedule") or [])
    current_race = int(state.get("current_race", 0) or 0)
    race = schedule[current_race] if 0 <= current_race < len(schedule) else {}
    track_name = str(race.get("track", "")).strip()
    pressure_round = bool(schedule) and current_race >= max(0, len(schedule) - 2)

    player_set = set(normalized_players)
    team_key = str(team_offer.get("team_key", "")).strip()
    teammate_rows = [
        row
        for row in result_rows
        if str(row.get("team_key", "")).strip() == team_key
        and str(row.get("driver_name", "")).strip() not in player_set
    ]
    teammate_note = ""
    if teammate_rows:
        best_teammate = min(teammate_rows, key=lambda row: int(row.get("class_pos", row.get("overall_pos", 999)) or 999))
        teammate_name = str(best_teammate.get("driver_name", "")).strip()
        teammate_pos = int(best_teammate.get("class_pos", best_teammate.get("overall_pos", 999)) or 999)
        if teammate_name and teammate_pos < best_finish:
            teammate_note = f"{teammate_name} set the benchmark on the other side of the garage this time."
        elif teammate_name and teammate_pos > best_finish:
            teammate_note = f"You came back ahead of teammate {teammate_name} this weekend."

    messages.append(
        {
            "id": uuid4().hex,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "category": "Team Message",
            "sender": team_name,
            "title": f"{team_name} Debrief",
            "body": _team_post_race_message_body(
                team_name=team_name,
                philosophy=philosophy,
                trajectory=trajectory,
                championship_name=championship_name,
                track_name=track_name,
                summary_text=summary_text,
                pressure_round=pressure_round,
                teammate_note=teammate_note,
            ),
            "read": False,
            "dedupe_key": dedupe_key,
        }
    )
    state["messages"] = messages


def _rivalry_explainer_message(player_label: str = "Driver") -> dict[str, Any]:
    lines = [
        f"{player_label},",
        "",
        "Close racing can turn another driver into a career rival.",
        "",
        "Yellow heat: the four closest class drivers around you will be highlighted for the next event.",
        "Orange heat: if that yellow driver finishes directly ahead of or behind you, the rivalry pressure rises.",
        "Red heat: if an orange driver finishes directly ahead of or behind you, they become a true rival and keep that status.",
        "",
        "Yellow heat clears if the driver falls outside that closest-four group in the next race. Orange heat drops back to yellow. Watch the standings colors to see who is starting to matter.",
        "",
        "Race Control",
    ]
    return {
        "id": uuid4().hex,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "category": "Race Control",
        "sender": "Race Control",
        "title": "Rivalry Heat System",
        "body": "\n".join(lines),
        "read": False,
    }


def migrate_loaded_rivalry_state(save_data: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(save_data, dict):
        return {}

    migrated = dict(save_data)
    changed = False
    player_names = _normalize_player_names(migrated.get("all_players") or migrated.get("players"), str(migrated.get("save_name", "")).strip())
    save_name = str(migrated.get("save_name", "")).strip()
    if save_name:
        sync_human_drivers(save_name, player_names)
    migrated["career_mode"] = _career_mode(migrated.get("career_mode"), player_names)
    migrated["active_player_name"] = _active_player_name(migrated.get("active_player_name"), player_names)
    migrated["player_perspectives"] = _normalize_player_perspectives(
        migrated.get("player_perspectives"),
        player_names,
        migrated.get("rivalry_heat"),
    )
    migrated["rivalry_heat"] = _merged_perspective_rivalry_heat(migrated["player_perspectives"])
    changed = True
    if "rivalry_heat" not in migrated or not _rivalry_heat(migrated.get("rivalry_heat")):
        rebuilt_state: dict[str, Any] = {"rivalry_heat": {}}
        for race in migrated.get("schedule") or []:
            if not isinstance(race, dict) or not bool(race.get("completed")):
                continue
            result_rows = race.get("full_results")
            if isinstance(result_rows, list):
                _update_rivalry_heat(rebuilt_state, result_rows, player_names)
        rebuilt_heat = _rivalry_heat(rebuilt_state.get("rivalry_heat"))
        if rebuilt_heat:
            migrated["player_perspectives"] = _normalize_player_perspectives(
                migrated.get("player_perspectives"),
                player_names,
                rebuilt_heat,
            )
            migrated["rivalry_heat"] = _merged_perspective_rivalry_heat(migrated["player_perspectives"])
        changed = True

    messages = [dict(message) for message in migrated.get("messages") or [] if isinstance(message, dict)]
    if not any(str(message.get("title", "")).strip() == "Rivalry Heat System" for message in messages):
        player_label = ", ".join(name for name in player_names if name) or "Driver"
        messages.append(_rivalry_explainer_message(player_label))
        migrated["messages"] = messages
        changed = True

    if changed and save_name:
        update_save(
            save_name,
            {
                "rivalry_heat": _rivalry_heat(migrated.get("rivalry_heat")),
                "career_mode": migrated.get("career_mode"),
                "active_player_name": migrated.get("active_player_name"),
                "player_perspectives": migrated.get("player_perspectives", {}),
                "messages": migrated.get("messages", []),
            },
        )
    return hydrate_active_rivals_state(migrated)


def _normalize_player_names(player_names: list[str] | None, save_name: str) -> list[str]:
    cleaned = [name.strip() for name in (player_names or []) if name and name.strip()]
    return cleaned or [save_name]


def _normalize_import_name(name: str) -> str:
    return " ".join(str(name).strip().casefold().split())


def _resolve_imported_finish_order(
    state: dict[str, Any],
    imported_names_in_order: list[str],
    name_map: dict[str, str] | None = None,
) -> list[str]:
    standings_names = [driver["name"] for driver in state["standings"]]
    standings_set = set(standings_names)
    normalized_standings = {_normalize_import_name(name): name for name in standings_names}
    manual_name_map = {
        str(key).strip(): str(value).strip()
        for key, value in (name_map or {}).items()
        if str(key).strip() and str(value).strip()
    }

    resolved_names: list[str] = []
    unresolved_imported: list[str] = []
    used_standings: set[str] = set()

    for imported_name in imported_names_in_order:
        imported_name = str(imported_name).strip()
        if not imported_name:
            continue

        mapped_name = manual_name_map.get(imported_name)
        if mapped_name:
            if mapped_name not in standings_set:
                raise ValueError(f"Mapped driver is not in this championship: {mapped_name}")
            if mapped_name in used_standings:
                raise ValueError(f"Driver was matched more than once: {mapped_name}")
            resolved_names.append(mapped_name)
            used_standings.add(mapped_name)
            continue

        if imported_name in standings_set and imported_name not in used_standings:
            resolved_names.append(imported_name)
            used_standings.add(imported_name)
            continue

        normalized_name = _normalize_import_name(imported_name)
        matched_name = normalized_standings.get(normalized_name)
        if matched_name and matched_name not in used_standings:
            resolved_names.append(matched_name)
            used_standings.add(matched_name)
            continue

        unresolved_imported.append(imported_name)

    missing_names = [name for name in standings_names if name not in used_standings]
    if unresolved_imported or missing_names:
        if name_map:
            unresolved_preview = ", ".join(unresolved_imported[:5])
            missing_preview = ", ".join(missing_names[:5])
            parts = []
            if unresolved_imported:
                parts.append(f"unmatched imported names: {unresolved_preview}{'...' if len(unresolved_imported) > 5 else ''}")
            if missing_names:
                parts.append(f"missing championship drivers: {missing_preview}{'...' if len(missing_names) > 5 else ''}")
            raise ValueError("Results import still has unresolved names: " + "; ".join(parts))
        raise ResultsImportMappingRequired(missing_names, unresolved_imported)

    if len(resolved_names) != len(standings_names):
        raise ValueError("Imported results did not produce a complete finishing order.")
    return resolved_names


def _clamp_difficulty(value: int) -> int:
    return max(0, min(125, int(value)))


def difficulty_range_for_game(game: str) -> tuple[int, int]:
    if str(game).strip().casefold() == "ams2":
        return 70, 120
    return 0, 125


def set_manual_difficulty(save_name: str, difficulty: int) -> tuple[int, bool]:
    save_data = load_save(save_name) or {}
    game = str(save_data.get("game", "iRacing"))
    min_difficulty, max_difficulty = difficulty_range_for_game(game)
    clamped_difficulty = max(min_difficulty, min(max_difficulty, int(difficulty)))

    update_save(save_name, {"starting_difficulty": clamped_difficulty})

    season_synced = False
    if game.strip().casefold() == "iracing":
        championship = save_data.get("championship")
        season_path = _iracing_season_path_for_sync(save_name, save_data, {}, championship)
        if season_path and isinstance(championship, dict):
            season_synced = update_exported_season_difficulty(
                season_path,
                championship,
                clamped_difficulty,
            )
            if season_synced:
                update_save(save_name, {"season_path": season_path})

    return clamped_difficulty, season_synced


def _adjust_difficulty_after_race(
    current_difficulty: int,
    player_results: dict[str, int],
    player_class_sizes: dict[str, int] | None = None,
) -> int:
    if not player_results:
        return _clamp_difficulty(current_difficulty)

    average_finish = sum(player_results.values()) / len(player_results)
    top_finish_threshold = max(1, len(player_results) * 2)
    if average_finish <= top_finish_threshold:
        return _clamp_difficulty(current_difficulty + 1)

    class_sizes = {
        name: int(size)
        for name, size in (player_class_sizes or {}).items()
        if name in player_results and int(size or 0) > 0
    }
    if class_sizes:
        bottom_half_threshold = sum(size / 2 for size in class_sizes.values()) / len(class_sizes)
        if average_finish > bottom_half_threshold:
            return _clamp_difficulty(current_difficulty - 1)
        return _clamp_difficulty(current_difficulty)

    if average_finish > 10:
        return _clamp_difficulty(current_difficulty - 1)
    return _clamp_difficulty(current_difficulty)


def create_new_save(
    save_name: str,
    player_names: list[str] | None = None,
    starting_difficulty: int = 75,
    world_history_years: int = 5,
    game: str = "iRacing",
    career_mode: str = "",
    player_profile_ids: list[str] | None = None,
    career_path_id: str = "default",
) -> tuple[bool, str]:
    selected_profile_ids = [str(value).strip() for value in (player_profile_ids or []) if str(value).strip()]
    selected_profile_refs = profile_refs(selected_profile_ids)
    if selected_profile_refs:
        normalized_players = _normalize_player_names([ref["name"] for ref in selected_profile_refs], save_name)
        selected_profile_ids = [ref["profile_id"] for ref in selected_profile_refs]
    else:
        normalized_players = _normalize_player_names(player_names, save_name)
    current_year = datetime.now().year
    normalized_history_years = max(5, min(20, int(world_history_years)))
    normalized_game = "AMS2" if str(game).strip().casefold() == "ams2" else "iRacing"
    normalized_mode = _career_mode(career_mode, normalized_players)
    player_label = ", ".join(normalized_players) or "Driver"
    player_perspectives = _normalize_player_perspectives({}, normalized_players, {})
    shared_car_ids, shared_track_names = shared_owned_assets(selected_profile_ids, normalized_game)
    success, message = create_save(
        save_name,
        {
            "game": normalized_game,
            "career_path_id": str(career_path_id).strip() or "default",
            "career_mode": normalized_mode,
            "players": normalized_players,
            "all_players": normalized_players,
            "player_careers": {player_name: {} for player_name in normalized_players} if normalized_mode == "Rivals" else {},
            "player_profiles": selected_profile_refs,
            "player_profile_ids": selected_profile_ids,
            "owned_content_snapshot": {
                "game": normalized_game,
                "car_ids": shared_car_ids,
                "track_names": shared_track_names,
                "season_year": current_year,
            },
            "active_player_name": _active_player_name("", normalized_players),
            "player_perspectives": player_perspectives,
            "starting_difficulty": _clamp_difficulty(starting_difficulty),
            "world_history_years": normalized_history_years,
            "world_year": current_year,
            "world_setup_complete": False,
            "tier": 1,
            "unlocked_tier": 1,
            "score": 0,
            "championship": None,
            "player_car": None,
            "schedule": [],
            "standings": [],
            "current_race": 0,
            "rivalry_heat": _merged_perspective_rivalry_heat(player_perspectives),
            "messages": [_rivalry_explainer_message(player_label)],
        },
    )
    if success:
        initialize_driver_pool(save_name, world_year=current_year - normalized_history_years)
        set_world_year(save_name, current_year - normalized_history_years)
    return success, message


def start_championship(
    save_name: str,
    championship: dict[str, Any],
    player_names: list[str] | None = None,
    player_car: dict[str, str] | None = None,
    starting_difficulty: int = 75,
) -> dict[str, Any]:
    save_data = load_save(save_name) or {}
    game = str(save_data.get("game", "iRacing"))
    all_player_names = _normalize_player_names(save_data.get("players") or player_names, save_name)
    career_mode = _career_mode(save_data.get("career_mode"), all_player_names)
    if career_mode == "Rivals" and all_player_names:
        active_player = _active_player_name(save_data.get("active_player_name"), all_player_names)
        player_names = [active_player]
    else:
        active_player = _active_player_name(save_data.get("active_player_name"), all_player_names)
        player_names = _normalize_player_names(player_names, save_name)
    num_races = int(championship.get("Num of Races", 4))
    tier = int(championship.get("Tier", 1))
    style = championship.get("Style", "")
    unlocked_tier = max(
        tier,
        _normalize_unlocked_tier(championship.get("unlocked_tier"), tier),
        _normalize_unlocked_tier(championship.get("unlocked_tiers"), tier),
    )
    player_car = player_car or select_player_car(championship, game, save_name)

    if player_car is None:
        raise ValueError("No owned car is eligible for this championship.")

    championship_group_rows = _championship_group_rows(championship, game)
    class_tiers = dict(championship.get("_class_tiers", {}))
    class_prestiges = dict(championship.get("_class_prestiges", {}))
    if not class_tiers or not class_prestiges:
        for row in championship_group_rows:
            row_tier = int(str(row.get("Tier", "1")).strip() or 1)
            row_prestige = int(str(row.get("Prestige", "0")).strip() or 0)
            for class_name in _class_names_for_rows([row], game):
                class_tiers[class_name] = row_tier
                class_prestiges[class_name] = row_prestige
    championship_for_state = dict(championship)
    championship_for_state["id"] = str(championship.get("Championship_ID", "")).strip() or str(championship.get("id", "")).strip()
    championship_for_state["_entry_rows"] = [dict(row) for row in championship_group_rows]
    championship_for_state["_class_names"] = _class_names_for_rows(championship_group_rows, game)
    championship_for_state["_class_tiers"] = class_tiers
    championship_for_state["_class_prestiges"] = class_prestiges
    class_car_counts: dict[str, int] = {}
    for row in championship_group_rows:
        try:
            class_cars = int(str(row.get("Class_Cars", "")).strip())
        except (TypeError, ValueError):
            class_cars = 0
        if class_cars > 0:
            for class_name in _class_names_for_rows([row], game):
                class_car_counts[class_name] = class_cars
    if class_car_counts:
        championship_for_state["_class_car_counts"] = class_car_counts
    championship_for_state["Multiclass"] = "yes" if len(championship_for_state["_class_names"]) > 1 else "no"
    championship_for_state["_field_tier"] = max(int(str(row.get("Tier", "1")).strip() or 1) for row in championship_group_rows)
    championship_for_state["_field_prestige"] = max(int(str(row.get("Prestige", "0")).strip() or 0) for row in championship_group_rows)
    championship_for_state["_schedule_style"] = str(championship.get("Style", "")).strip()
    championship_for_state["Style"] = _championship_discipline_style(str(championship.get("Style", "")))
    championship_for_state["_player_class_name"] = _class_name_for_car_rows(
        championship_group_rows, player_car, game
    ) or str(player_car.get("Car class", "")).strip() or str(player_car.get("Car", "")).strip()
    player_team_offer = championship.get("player_team_offer")
    if isinstance(player_team_offer, dict):
        championship_for_state["player_team_offer"] = dict(player_team_offer)
    num_opponents = _opponent_count_for_championship(championship_for_state, player_names, player_car)
    total_drivers = len(player_names) + num_opponents
    schedule_tier = int(championship_for_state.get("_field_tier", tier) or tier)

    schedule = build_schedule(
        load_tracks(style, schedule_tier, game, save_name, _custom_track_selection(championship_for_state)),
        num_races,
        game=game,
        championship_style=style,
        minimum_garages=total_drivers,
    )
    if not schedule:
        ownership_label = "shared owned" if len(player_names) > 1 else "owned"
        raise ValueError(
            f"No {ownership_label} tracks with enough garage spaces are available for this championship."
        )
    set_human_primary_style_if_unassigned(save_name, player_names, str(championship_for_state.get("Style", "Sports Car")))
    player_seed_standings = assign_driver_classes(
        build_standings_from_pool(save_name, player_names, 0, championship_for_state),
        championship_for_state,
        player_names,
        player_car,
    )
    player_seed_standings = _apply_player_team_offer(player_seed_standings, player_names, player_team_offer, game)
    standings, world_sim_progress = _populate_world_with_player_championship(
        save_name,
        championship_for_state,
        schedule,
        player_seed_standings,
        total_drivers,
    )
    standings = _apply_player_team_offer(standings, player_names, player_team_offer, game)
    standings = assign_teams_to_standings(standings, championship_for_state, save_name)
    add_ai_drivers_from_standings(save_name, standings, player_names, championship_for_state)
    set_ai_primary_style_on_first_championship(save_name, standings, str(championship_for_state.get("Style", "Sports Car")))
    championship_for_pool = dict(championship_for_state)
    championship_for_pool["Pool_Championship"] = championship_pool_display_name(championship_for_state)
    set_current_championship_for_standings(save_name, standings, championship_for_pool)
    championship_for_export = dict(championship_for_state)
    championship_for_export["_championship_car_ids"] = ",".join(
        sorted(str(car.get("id", "")).strip() for car in championship_cars(championship_for_state, game))
    )
    adapter = get_game_adapter(game)
    preferred_player_liveries = []
    if game.strip().casefold() == "ams2":
        preferred_livery = str(player_car.get("_preview_livery_name", "")).strip()
        preferred_roster = str(player_car.get("_preview_roster_name", "")).strip()
        preferred_class = (
            str(player_car.get("Car class", "")).strip()
            or str(player_car.get("Car", "")).strip()
            or str(player_car.get("_preview_livery_class", "")).strip()
        )
        if preferred_livery and preferred_roster and preferred_class:
            preferred_player_liveries = [
                {
                    "driver_name": str(player_name),
                    "class_name": preferred_class,
                    "roster_name": preferred_roster,
                    "livery_name": preferred_livery,
                    "car_name": str(player_car.get("_preview_livery_car_name", "") or player_car.get("Car", "")).strip(),
                    "car_id": str(player_car.get("id", "")).strip(),
                }
                for player_name in player_names
            ]
    roster_path, season_path, player_liveries = adapter.export_championship_assets(
        save_name,
        championship_for_export,
        standings,
        player_names,
        player_car,
        schedule,
        starting_difficulty=_clamp_difficulty(starting_difficulty),
        existing_player_liveries=preferred_player_liveries or None,
    )
    storyline = championship_storyline_drivers(save_name, standings, game, tier, player_names)
    existing_save_data = load_save(save_name) or {}
    existing_messages = list(existing_save_data.get("messages") or [])
    player_perspectives = _normalize_player_perspectives(
        existing_save_data.get("player_perspectives"),
        all_player_names if career_mode == "Rivals" else player_names,
        existing_save_data.get("rivalry_heat"),
    )

    state = {
        "save_name": save_name,
        "players": player_names,
        "all_players": all_player_names,
        "game": game,
        "career_mode": career_mode,
        "active_player_name": active_player if career_mode == "Rivals" else _active_player_name(existing_save_data.get("active_player_name"), player_names),
        "player_perspectives": player_perspectives,
        "starting_difficulty": _clamp_difficulty(starting_difficulty),
        "world_setup_complete": True,
        "tier": tier,
        "unlocked_tier": unlocked_tier,
        "score": 0,
        "championship": championship_for_state,
        "player_car": player_car,
        "player_team_offer": player_team_offer,
        "player_liveries": player_liveries,
        "watch_drivers": storyline.get("watch_drivers", []),
        "rising_driver": storyline.get("rising_driver"),
        "rivalry_heat": _merged_perspective_rivalry_heat(player_perspectives),
        "messages": existing_messages,
        "roster_path": str(roster_path),
        "season_path": str(season_path),
        "schedule": schedule,
        "standings": standings,
        "current_race": 0,
        "world_sim_progress": world_sim_progress,
        "offseason_world_instances": [],
        "offseason_player_style_limits": {},
    }
    if career_mode == "Rivals":
        update_save(save_name, _rivals_save_payload(state))
    else:
        update_save(save_name, state)
    return state


def reexport_championship_assets(state: dict[str, Any]) -> dict[str, Any]:
    save_name = str(state.get("save_name", "")).strip()
    championship = state.get("championship")
    standings = state.get("standings") or []
    schedule = state.get("schedule") or []
    if not save_name or not isinstance(championship, dict):
        raise ValueError("No active championship is available to export.")
    if not standings:
        raise ValueError("No active championship field is available to export.")

    save_data = load_save(save_name) or {}
    game = str(state.get("game") or save_data.get("game", "iRacing"))
    player_names = _career_player_names(state, save_name)
    player_car = state.get("player_car")
    starting_difficulty = _clamp_difficulty(int(state.get("starting_difficulty", 75)))

    championship_for_export = dict(championship)
    championship_for_export["_championship_car_ids"] = ",".join(
        sorted(str(car.get("id", "")).strip() for car in championship_cars(championship_for_export, game))
    )
    adapter = get_game_adapter(game)
    if game.strip().casefold() == "iracing":
        from .roster_exporter import export_roster

        roster_path = export_roster(save_name, championship_for_export, standings, player_names, player_car)
        season_path = str(state.get("season_path") or save_data.get("season_path", "")).strip()
        player_liveries = []
    else:
        roster_path, season_path, player_liveries = adapter.export_championship_assets(
            save_name,
            championship_for_export,
            standings,
            player_names,
            player_car,
            schedule,
            starting_difficulty=starting_difficulty,
            existing_player_liveries=state.get("player_liveries", []),
        )

    updated_state = dict(state)
    updated_state["game"] = game
    updated_state["roster_path"] = str(roster_path)
    updated_state["season_path"] = str(season_path)
    if game.strip().casefold() == "ams2":
        updated_state["player_liveries"] = player_liveries

    if _career_mode(updated_state.get("career_mode"), _all_player_names(updated_state, save_name)) == "Rivals":
        update_save(save_name, _rivals_save_payload(updated_state))
    else:
        update_save(
            save_name,
            {
                "game": game,
                "player_liveries": updated_state.get("player_liveries", []),
                "roster_path": str(roster_path),
                "season_path": str(season_path),
            },
        )
    return updated_state


def _world_roster_export_championship_name(championship: dict[str, Any], display_name: str) -> str:
    base_name = str(championship.get("Championship", "")).strip() or "World Championship"
    clean_display = "".join(
        ch if ch.isalnum() or ch in {" ", "-", "_"} else "_"
        for ch in str(display_name).strip()
    ).strip()
    if not clean_display or clean_display.casefold() == base_name.casefold():
        clean_display = "World Roster"
    return f"{base_name} {clean_display}"


def export_world_championship_roster(save_name: str, championship_key: str) -> str:
    detail = get_active_world_championship_detail(save_name, championship_key)
    if not detail:
        raise ValueError("Championship not found.")

    championship = dict(detail.get("championship") or {})
    standings = list(detail.get("standings") or [])
    if not championship or not standings:
        raise ValueError("No championship roster is available to export.")

    save_data = load_save(save_name) or {}
    game = str(championship.get("Game") or save_data.get("game") or "iRacing")
    championship_for_export = dict(championship)
    championship_for_export["Championship"] = _world_roster_export_championship_name(
        championship,
        str(detail.get("name", "")),
    )
    championship_for_export["_championship_car_ids"] = ",".join(
        sorted(str(car.get("id", "")).strip() for car in championship_cars(championship_for_export, game))
    )

    if game.strip().casefold() == "ams2":
        from .ams2_exporter import export_ams2_roster

        roster_path, _player_liveries = export_ams2_roster(
            save_name,
            championship_for_export,
            standings,
            [],
            None,
            existing_player_liveries=None,
        )
        return str(roster_path)

    from .roster_exporter import export_roster

    return str(export_roster(save_name, championship_for_export, standings, [], None))


def continue_or_initialize_season(
    save_name: str,
    championship: dict[str, Any],
    player_names: list[str] | None,
    player_car: dict[str, Any] | None,
    starting_difficulty: int,
    schedule: list[dict[str, Any]] | None,
    standings: list[dict[str, Any]] | None,
    current_race: int,
    unlocked_tier: int | None = None,
    world_sim_progress: dict[str, Any] | None = None,
) -> dict[str, Any]:
    save_data = hydrate_active_rivals_state(load_save(save_name) or {})
    current_game = str(save_data.get("game", "iRacing"))
    all_players = _all_player_names(save_data, save_name)
    normalized_players = _career_player_names(save_data, save_name) or _normalize_player_names(player_names, save_name)
    career_mode = _career_mode(save_data.get("career_mode"), normalized_players)
    active_player_name = _active_player_name(save_data.get("active_player_name"), all_players or normalized_players)
    player_perspectives = _normalize_player_perspectives(
        save_data.get("player_perspectives"),
        all_players or normalized_players,
        save_data.get("rivalry_heat"),
    )
    player_liveries = save_data.get("player_liveries", [])
    player_team_offer = save_data.get("player_team_offer")
    watch_drivers = save_data.get("watch_drivers", [])
    rising_driver = save_data.get("rising_driver")
    messages = save_data.get("messages", [])
    rivalry_heat = _merged_perspective_rivalry_heat(player_perspectives)
    if schedule and standings:
        standings = assign_teams_to_standings(list(standings), championship, save_name)
        standings = _apply_player_team_offer(
            standings,
            _normalize_player_names(player_names, save_name),
            player_team_offer,
            current_game,
        )
        normalized_unlocked_tier = max(
            int(championship.get("Tier", 1)),
            _normalize_unlocked_tier(unlocked_tier, int(championship.get("Tier", 1))),
            _normalize_unlocked_tier(championship.get("unlocked_tier"), int(championship.get("Tier", 1))),
            _normalize_unlocked_tier(championship.get("unlocked_tiers"), int(championship.get("Tier", 1))),
        )
        return {
            "save_name": save_name,
            "game": current_game,
            "career_mode": career_mode,
            "players": normalized_players,
            "all_players": all_players or normalized_players,
            "active_player_name": active_player_name,
            "player_perspectives": player_perspectives,
            "starting_difficulty": _clamp_difficulty(starting_difficulty),
            "world_setup_complete": bool(world_sim_progress is not None) or bool(championship.get("world_setup_complete", True)),
            "tier": int(championship.get("Tier", 1)),
            "unlocked_tier": normalized_unlocked_tier,
            "score": 0,
            "championship": championship,
            "player_car": player_car,
            "player_team_offer": player_team_offer,
            "player_liveries": player_liveries,
            "watch_drivers": watch_drivers,
            "rising_driver": rising_driver,
            "rivalry_heat": rivalry_heat,
            "messages": messages,
            "roster_path": save_data.get("roster_path", ""),
            "season_path": save_data.get("season_path", ""),
            "schedule": schedule,
            "standings": standings,
            "current_race": current_race,
            "world_sim_progress": world_sim_progress,
        }

    return start_championship(
        save_name,
        championship,
        player_names=player_names,
        player_car=player_car,
        starting_difficulty=starting_difficulty,
    )


def _persist_active_state(state: dict[str, Any]) -> None:
    save_name = str(state.get("save_name", "")).strip()
    if _career_mode(state.get("career_mode"), _all_player_names(state, save_name)) == "Rivals":
        update_save(save_name, _rivals_save_payload(state))
        return

    update_save(
        state["save_name"],
        {
            "game": str(state.get("game", "iRacing") or "iRacing"),
            "career_mode": _career_mode(state.get("career_mode"), _normalize_player_names(state.get("players"), state["save_name"])),
            "players": _normalize_player_names(state.get("players"), state["save_name"]),
            "active_player_name": _active_player_name(
                state.get("active_player_name"),
                _normalize_player_names(state.get("players"), state["save_name"]),
            ),
            "player_perspectives": _normalize_player_perspectives(
                state.get("player_perspectives"),
                _normalize_player_names(state.get("players"), state["save_name"]),
                state.get("rivalry_heat"),
            ),
            "starting_difficulty": state.get("starting_difficulty", 75),
            "world_setup_complete": state.get("world_setup_complete", True),
            "tier": state.get("tier", 1),
            "unlocked_tier": _normalize_unlocked_tier(
                state.get("unlocked_tier", state.get("unlocked_tiers")),
                state.get("tier", 1),
            ),
            "score": state.get("score", 0),
            "championship": state["championship"],
            "player_car": state.get("player_car"),
            "player_team_offer": state.get("player_team_offer"),
            "player_liveries": state.get("player_liveries", []),
            "watch_drivers": state.get("watch_drivers", []),
            "rising_driver": state.get("rising_driver"),
            "rivalry_heat": _merged_perspective_rivalry_heat(
                _normalize_player_perspectives(
                    state.get("player_perspectives"),
                    _normalize_player_names(state.get("players"), state["save_name"]),
                    state.get("rivalry_heat"),
                )
            ),
            "messages": state.get("messages", []),
            "schedule": state["schedule"],
            "standings": state["standings"],
            "current_race": state["current_race"],
            "world_sim_progress": state.get("world_sim_progress"),
        },
    )


def _expected_iracing_season_path(save_name: str, championship: dict[str, Any]) -> str:
    championship_name = str(championship.get("Championship", "")).strip()
    if not save_name or not championship_name:
        return ""
    try:
        settings = load_settings()
    except Exception:
        return ""
    iracing_directory = str(settings.get("iracing_directory", "")).strip()
    if not iracing_directory:
        return ""
    return str(Path(iracing_directory) / "aiseasons" / f"CS-{championship_name}-{save_name}.json")


def _iracing_season_path_for_sync(
    save_name: str,
    save_data: dict[str, Any],
    state: dict[str, Any],
    championship: dict[str, Any] | None,
) -> str:
    candidates = [
        str(state.get("season_path", "")).strip(),
        str(save_data.get("season_path", "")).strip(),
    ]
    if isinstance(championship, dict):
        candidates.append(_expected_iracing_season_path(save_name, championship))

    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return ""


def _sync_iracing_season_difficulty(state: dict[str, Any]) -> None:
    if str(state.get("game", "iRacing")).strip().casefold() != "iracing":
        return

    save_name = str(state.get("save_name", "")).strip()
    if not save_name:
        return

    save_data = load_save(save_name) or {}
    championship = state.get("championship")
    season_path = _iracing_season_path_for_sync(save_name, save_data, state, championship)
    if not season_path or not isinstance(championship, dict):
        return

    synced = update_exported_season_difficulty(
        season_path,
        championship,
        int(state.get("starting_difficulty", 75) or 75),
    )
    if synced and str(save_data.get("season_path", "")).strip() != season_path:
        update_save(save_name, {"season_path": season_path})


def simulate_race(state: dict[str, Any]) -> dict[str, Any]:
    schedule = state["schedule"]
    current_race = state["current_race"]
    standings = state["standings"]

    if current_race >= len(schedule):
        return state

    player_names = _career_player_names(state, state["save_name"])
    finish_order_names = world_simulated_finish_order(
        state["save_name"],
        standings,
        str(state.get("game", "iRacing") or "iRacing"),
    )
    _, result_rows = apply_points_by_class(standings, finish_order_names)
    update_ratings_after_race(state["save_name"], state["championship"], standings, result_rows)
    record_driver_race_results(state["save_name"], state["championship"], schedule[current_race], standings, result_rows)
    _update_player_rivalry_perspectives(state, result_rows, player_names)
    player_results = _player_class_results(result_rows, player_names)
    player_class_sizes = _player_class_sizes(result_rows, player_names)
    _add_team_post_race_message(state, result_rows, player_names, player_results, player_class_sizes)
    state["starting_difficulty"] = _adjust_difficulty_after_race(
        state.get("starting_difficulty", 75),
        player_results,
        player_class_sizes,
    )

    schedule[current_race]["completed"] = True
    schedule[current_race]["result"] = player_results
    schedule[current_race]["full_results"] = result_rows
    state["current_race"] = current_race + 1

    _persist_active_state(state)
    _sync_iracing_season_difficulty(state)
    return state


def apply_manual_race_results(state: dict[str, Any], player_positions: dict[str, int]) -> dict[str, Any]:
    schedule = state["schedule"]
    current_race = state["current_race"]
    standings = state["standings"]

    if current_race >= len(schedule):
        return state

    total_drivers = len(standings)
    valid_positions = set(range(1, total_drivers + 1))
    submitted_positions = list(player_positions.values())

    if not submitted_positions:
        raise ValueError("Enter at least one player result.")
    if any(position not in valid_positions for position in submitted_positions):
        raise ValueError(f"Positions must be between 1 and {total_drivers}.")
    if len(set(submitted_positions)) != len(submitted_positions):
        raise ValueError("Player finishing positions must be unique.")

    standings_by_name = {driver["name"]: index for index, driver in enumerate(standings)}
    player_names = set(_career_player_names(state, state["save_name"]))

    for player_name in player_positions:
        if player_name not in player_names or player_name not in standings_by_name:
            raise ValueError(f"Unknown player: {player_name}")

    remaining_positions = [position for position in range(1, total_drivers + 1) if position not in player_positions.values()]
    remaining_driver_indexes = [
        index for index, driver in enumerate(standings) if driver["name"] not in player_positions
    ]
    random.shuffle(remaining_positions)

    finishing_by_driver_index: dict[int, int] = {}
    for player_name, finish_pos in player_positions.items():
        finishing_by_driver_index[standings_by_name[player_name]] = finish_pos
    for driver_index, finish_pos in zip(remaining_driver_indexes, remaining_positions):
        finishing_by_driver_index[driver_index] = finish_pos

    finish_order_pairs = sorted(finishing_by_driver_index.items(), key=lambda item: item[1])
    finish_order_names = [standings[driver_index]["name"] for driver_index, _ in finish_order_pairs]
    _, result_rows = apply_points_by_class(standings, finish_order_names)
    update_ratings_after_race(state["save_name"], state["championship"], standings, result_rows)
    record_driver_race_results(state["save_name"], state["championship"], schedule[current_race], standings, result_rows)
    _update_player_rivalry_perspectives(
        state,
        result_rows,
        _career_player_names(state, state["save_name"]),
    )

    ordered_player_results = _player_class_results(
        result_rows,
        _career_player_names(state, state["save_name"]),
    )
    player_class_sizes = _player_class_sizes(
        result_rows,
        _career_player_names(state, state["save_name"]),
    )
    _add_team_post_race_message(
        state,
        result_rows,
        _career_player_names(state, state["save_name"]),
        ordered_player_results,
        player_class_sizes,
    )
    state["starting_difficulty"] = _adjust_difficulty_after_race(
        state.get("starting_difficulty", 75),
        ordered_player_results,
        player_class_sizes,
    )

    schedule[current_race]["completed"] = True
    schedule[current_race]["result"] = ordered_player_results
    schedule[current_race]["full_results"] = result_rows
    state["current_race"] = current_race + 1

    _persist_active_state(state)
    _sync_iracing_season_difficulty(state)
    return state


def apply_finish_order(state: dict[str, Any], finish_order_names: list[str]) -> dict[str, Any]:
    schedule = state["schedule"]
    current_race = state["current_race"]
    standings = state["standings"]

    if current_race >= len(schedule):
        return state

    expected_names = [driver["name"] for driver in standings]
    if len(finish_order_names) != len(expected_names):
        raise ValueError("Finish order must include every driver exactly once.")
    if set(finish_order_names) != set(expected_names):
        raise ValueError("Finish order contains unknown or duplicate drivers.")

    player_names = _career_player_names(state, state["save_name"])
    player_results: dict[str, int] = {}
    _, result_rows = apply_points_by_class(standings, finish_order_names)
    update_ratings_after_race(state["save_name"], state["championship"], standings, result_rows)
    record_driver_race_results(state["save_name"], state["championship"], schedule[current_race], standings, result_rows)
    _update_player_rivalry_perspectives(state, result_rows, player_names)
    player_results = _player_class_results(result_rows, player_names)
    player_class_sizes = _player_class_sizes(result_rows, player_names)
    _add_team_post_race_message(state, result_rows, player_names, player_results, player_class_sizes)
    state["starting_difficulty"] = _adjust_difficulty_after_race(
        state.get("starting_difficulty", 75),
        player_results,
        player_class_sizes,
    )

    schedule[current_race]["completed"] = True
    schedule[current_race]["result"] = player_results
    schedule[current_race]["full_results"] = result_rows
    state["current_race"] = current_race + 1

    _persist_active_state(state)
    _sync_iracing_season_difficulty(state)
    return state


def import_iracing_results(state: dict[str, Any], json_path: str, name_map: dict[str, str] | None = None) -> list[str]:
    json_file = Path(json_path)
    if not json_file.exists():
        raise ValueError("Selected results file could not be found.")

    try:
        payload = json.loads(json_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("Selected file is not valid JSON.") from error

    sessions = payload.get("session_results")
    if not isinstance(sessions, list):
        raise ValueError("Results JSON does not contain any session results.")

    race_session = next(
        (
            session
            for session in sessions
            if str(session.get("simsession_type_name", "")).strip().casefold() == "race"
            and isinstance(session.get("results"), list)
        ),
        None,
    )
    if race_session is None:
        raise ValueError("Results JSON does not contain a race session.")

    raw_results = sorted(
        race_session.get("results", []),
        key=lambda row: int(row.get("position", 0)),
    )
    if not raw_results:
        raise ValueError("Race session does not contain any driver results.")

    imported_names_in_order = [str(row.get("display_name", "")).strip() for row in raw_results if str(row.get("display_name", "")).strip()]
    return _resolve_imported_finish_order(state, imported_names_in_order, name_map=name_map)


def import_ams2_results(state: dict[str, Any], json_path: str, name_map: dict[str, str] | None = None) -> list[str]:
    json_file = Path(json_path)
    if not json_file.exists():
        raise ValueError("Selected results file could not be found.")

    try:
        payload = json.loads(json_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("Selected file is not valid JSON.") from error

    drivers = payload.get("Drivers")
    if not isinstance(drivers, list):
        raise ValueError("Results JSON does not contain any driver results.")

    raw_results = sorted(
        [row for row in drivers if isinstance(row, dict)],
        key=lambda row: int(row.get("FinishingPosition", 0) or 0),
    )
    if not raw_results:
        raise ValueError("Results JSON does not contain any driver results.")
    all_imported_names = [
        str(row.get("DriverLongName", "")).strip()
        for row in raw_results
        if str(row.get("DriverLongName", "")).strip()
    ]

    player_names = _career_player_names(state, state["save_name"])
    if len(player_names) <= 1:
        imported_names_in_order = all_imported_names
        if not imported_names_in_order:
            raise ValueError("Results JSON does not contain any driver names.")
        return _resolve_imported_finish_order(state, imported_names_in_order, name_map=name_map)

    player_set = set(player_names)
    standings = state.get("standings") or []
    standings_by_name = {str(driver.get("name", "")).strip(): driver for driver in standings}
    class_groups: dict[str, list[dict[str, Any]]] = {}
    for driver in standings:
        class_name = str(driver.get("class_name", "")).strip() or "Overall"
        class_groups.setdefault(class_name, []).append(driver)

    manual_name_map = {
        str(key).strip(): str(value).strip()
        for key, value in (name_map or {}).items()
        if str(key).strip() and str(value).strip()
    }
    normalized_players = {_normalize_import_name(name): name for name in player_names}
    imported_player_rows = [row for row in raw_results if bool(row.get("IsPlayer", False))]
    matched_player_rows = [
        row
        for row in raw_results
        if (
            str(row.get("DriverLongName", "")).strip() in player_set
            or _normalize_import_name(str(row.get("DriverLongName", "")).strip()) in normalized_players
            or str(row.get("DriverLongName", "")).strip() in manual_name_map
        )
    ]
    if imported_player_rows:
        seen_imported_names: set[str] = set()
        combined_rows: list[dict[str, Any]] = []
        for row in imported_player_rows + matched_player_rows:
            imported_name = str(row.get("DriverLongName", "")).strip()
            if not imported_name or imported_name in seen_imported_names:
                continue
            seen_imported_names.add(imported_name)
            combined_rows.append(row)
        imported_player_rows = combined_rows
    else:
        imported_player_rows = matched_player_rows

    resolved_player_positions: dict[str, int] = {}
    unresolved_imported: list[str] = []

    for row in imported_player_rows:
        imported_name = str(row.get("DriverLongName", "")).strip()
        if not imported_name:
            continue
        mapped_name = manual_name_map.get(imported_name)
        if mapped_name:
            if mapped_name not in player_set:
                raise ValueError(f"Mapped player is not in this save: {mapped_name}")
            resolved_name = mapped_name
        elif imported_name in player_set:
            resolved_name = imported_name
        else:
            resolved_name = normalized_players.get(_normalize_import_name(imported_name), "")

        if not resolved_name:
            unresolved_imported.append(imported_name)
            continue
        if resolved_name in resolved_player_positions:
            raise ValueError(f"Player was matched more than once: {resolved_name}")

        resolved_player_positions[resolved_name] = int(
            row.get("FinishingPositionInClass", row.get("FinishingPosition", 0)) or 0
        )

    missing_players = [name for name in player_names if name not in resolved_player_positions]
    if unresolved_imported or missing_players:
        if name_map:
            unresolved_preview = ", ".join(unresolved_imported[:5])
            missing_preview = ", ".join(missing_players[:5])
            parts = []
            if unresolved_imported:
                parts.append(f"unmatched imported names: {unresolved_preview}{'...' if len(unresolved_imported) > 5 else ''}")
            if missing_players:
                parts.append(f"missing save players: {missing_preview}{'...' if len(missing_players) > 5 else ''}")
            raise ValueError("Results import still has unresolved player names: " + "; ".join(parts))
        raise ResultsImportMappingRequired(missing_players, all_imported_names)

    finish_order_names: list[str] = []
    for class_name, class_drivers in class_groups.items():
        class_player_positions = {
            player_name: position
            for player_name, position in resolved_player_positions.items()
            if (str(standings_by_name.get(player_name, {}).get("class_name", "")).strip() or "Overall") == class_name
        }
        total_drivers = len(class_drivers)
        valid_positions = set(range(1, total_drivers + 1))
        submitted_positions = list(class_player_positions.values())
        if any(position not in valid_positions for position in submitted_positions):
            raise ValueError(f"Imported AMS2 class positions must be between 1 and {total_drivers} for {class_name}.")
        if len(set(submitted_positions)) != len(submitted_positions):
            raise ValueError(f"Imported AMS2 class positions are duplicated for {class_name}.")

        ai_drivers = [driver for driver in class_drivers if str(driver.get("name", "")).strip() not in class_player_positions]
        ai_finish_order = world_simulated_finish_order(
            state["save_name"],
            ai_drivers,
            "AMS2",
        )
        remaining_positions = [position for position in range(1, total_drivers + 1) if position not in class_player_positions.values()]
        finishing_by_position: dict[int, str] = {}
        for player_name, position in class_player_positions.items():
            finishing_by_position[position] = player_name
        for ai_name, position in zip(ai_finish_order, remaining_positions):
            finishing_by_position[position] = ai_name

        if len(finishing_by_position) != total_drivers:
            raise ValueError(f"AMS2 import could not build a complete finish order for {class_name}.")
        finish_order_names.extend([finishing_by_position[position] for position in sorted(finishing_by_position)])

    if len(finish_order_names) != len(standings):
        raise ValueError("AMS2 import did not produce a complete finishing order.")
    return finish_order_names


def finalize_season(state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if _career_mode(state.get("career_mode"), _all_player_names(state, state["save_name"])) == "Rivals":
        return finalize_rivals_seasons(state)

    standings = state["standings"]
    player_names = _career_player_names(state, state["save_name"])
    player_championship = state.get("championship") or {}
    state = run_world_simulation_step(state, finish_remaining=True)
    world_simulation_summary = (state.get("world_sim_progress") or {}).get("summary", {})
    for instance in (state.get("world_sim_progress") or {}).get("instances", []):
        if instance.get("finalized"):
            continue
        instance_summary = finalize_driver_season(
            state["save_name"],
            instance.get("championship") or {},
            instance.get("standings") or [],
            advance_world_year=False,
        )
        world_simulation_summary = _merge_world_sim_summary(world_simulation_summary, instance_summary)
        instance["finalized"] = True
    driver_pool_summary = finalize_driver_season(state["save_name"], player_championship, standings)
    driver_pool_summary["world_simulation"] = world_simulation_summary
    sorted_standings = sorted(standings, key=lambda driver: (driver["points"], driver["wins"]), reverse=True)
    player_positions = []
    for player_name in player_names:
        for position, driver in enumerate(sorted_standings, 1):
            if driver["name"] == player_name:
                player_positions.append(position)
                break

    average_position = sum(player_positions) / len(player_positions) if player_positions else float("inf")
    current_tier = int(state.get("tier", 1))
    unlocked_tier = _normalize_unlocked_tier(
        state.get("unlocked_tier", state.get("unlocked_tiers")),
        current_tier,
    )
    max_tier = _max_available_tier()

    if average_position <= 5:
        new_tier = min(current_tier + 1, max_tier)
        outcome = "promoted" if new_tier > current_tier else "stayed"
    elif average_position <= 10:
        new_tier = current_tier
        outcome = "stayed"
    else:
        new_tier = max(current_tier - 1, 1)
        outcome = "demoted" if new_tier < current_tier else "stayed"

    new_unlocked_tier = max(unlocked_tier, new_tier)
    new_state = {
        "save_name": state["save_name"],
        "game": str(state.get("game", "iRacing") or "iRacing"),
        "career_mode": _career_mode(state.get("career_mode"), player_names),
        "players": player_names,
        "all_players": _all_player_names(state, state["save_name"]) or player_names,
        "active_player_name": _active_player_name(state.get("active_player_name"), player_names),
        "player_perspectives": _normalize_player_perspectives(
            state.get("player_perspectives"),
            player_names,
            state.get("rivalry_heat"),
        ),
        "starting_difficulty": state.get("starting_difficulty", 75),
        "world_setup_complete": True,
        "tier": new_tier,
        "unlocked_tier": new_unlocked_tier,
        "score": state.get("score", 0),
        "championship": None,
        "player_car": None,
        "watch_drivers": [],
        "rising_driver": None,
        "rivalry_heat": _merged_perspective_rivalry_heat(
            _normalize_player_perspectives(
                state.get("player_perspectives"),
                player_names,
                state.get("rivalry_heat"),
            )
        ),
        "messages": state.get("messages", []),
        "schedule": [],
        "standings": [],
        "current_race": 0,
    }
    if _career_mode(state.get("career_mode"), _all_player_names(state, state["save_name"]) or player_names) == "Rivals":
        new_state["career_mode"] = "Rivals"
        new_state["active_player_name"] = _active_player_name(
            state.get("active_player_name"),
            _all_player_names(state, state["save_name"]) or player_names,
        )
        update_save(state["save_name"], _rivals_save_payload(new_state))
    else:
        update_save(state["save_name"], new_state)
    summary = {
        "average_position": average_position,
        "player_positions": player_positions,
        "career_mode": _career_mode(state.get("career_mode"), player_names),
        "active_player_name": _active_player_name(state.get("active_player_name"), player_names),
        "player_team_offer": dict(state.get("player_team_offer") or {}) if isinstance(state.get("player_team_offer"), dict) else {},
        "player_perspectives": _normalize_player_perspectives(
            state.get("player_perspectives"),
            player_names,
            state.get("rivalry_heat"),
        ),
        "old_tier": current_tier,
        "new_tier": new_tier,
        "old_unlocked_tier": unlocked_tier,
        "new_unlocked_tier": new_unlocked_tier,
        "outcome": outcome,
        "driver_pool": driver_pool_summary,
    }
    return new_state, summary


def finalize_rivals_seasons(state: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    save_name = str(state.get("save_name", "")).strip()
    save_data = load_save(save_name) or {}
    all_players = _normalize_player_names(save_data.get("all_players") or save_data.get("players"), save_name)
    if not all_players:
        return state, {}

    waiting = rivals_waiting_for_drivers(save_name)
    if waiting:
        raise ValueError("Rivals season cannot finalize until all drivers finish: " + ", ".join(waiting))

    careers = _normalized_player_careers(save_data.get("player_careers"), all_players)
    player_perspectives = _normalize_player_perspectives(
        save_data.get("player_perspectives"),
        all_players,
        save_data.get("rivalry_heat"),
    )
    active_player = _active_player_name(state.get("active_player_name") or save_data.get("active_player_name"), all_players)
    current_game = str(state.get("game") or save_data.get("game", "iRacing") or "iRacing")
    messages = list(state.get("messages") or save_data.get("messages") or [])

    combined_driver_pool_summary = _empty_world_sim_summary()
    player_summaries: dict[str, dict[str, Any]] = {}
    active_summary: dict[str, Any] = {}
    active_final_standings: list[dict[str, Any]] = []
    active_championship_name = "Season Recap"

    for player_name in all_players:
        career = dict(careers.get(player_name) or {})
        career_state = {
            **save_data,
            **career,
            "save_name": save_name,
            "game": current_game,
            "career_mode": "Rivals",
            "players": [player_name],
            "all_players": all_players,
            "active_player_name": player_name,
            "player_perspectives": player_perspectives,
            "messages": messages,
        }
        player_names = [player_name]
        standings = list(career_state.get("standings") or [])
        player_championship = career_state.get("championship") or {}
        career_state = run_world_simulation_step(career_state, finish_remaining=True)
        world_simulation_summary = (career_state.get("world_sim_progress") or {}).get("summary", {})
        for instance in (career_state.get("world_sim_progress") or {}).get("instances", []):
            if instance.get("finalized"):
                continue
            instance_summary = finalize_driver_season(
                save_name,
                instance.get("championship") or {},
                instance.get("standings") or [],
                advance_world_year=False,
            )
            world_simulation_summary = _merge_world_sim_summary(world_simulation_summary, instance_summary)
            instance["finalized"] = True

        driver_pool_summary = finalize_driver_season(
            save_name,
            player_championship,
            standings,
            advance_world_year=False,
        )
        driver_pool_summary["world_simulation"] = world_simulation_summary
        combined_driver_pool_summary = _merge_world_sim_summary(combined_driver_pool_summary, driver_pool_summary)
        combined_driver_pool_summary = _merge_world_sim_summary(combined_driver_pool_summary, world_simulation_summary)

        outcome = _season_outcome_for_player(career_state, player_names)
        summary = {
            **outcome,
            "career_mode": "Rivals",
            "active_player_name": player_name,
            "player_team_offer": dict(career_state.get("player_team_offer") or {})
            if isinstance(career_state.get("player_team_offer"), dict)
            else {},
            "player_perspectives": player_perspectives,
            "driver_pool": driver_pool_summary,
        }
        player_summaries[player_name] = summary

        new_career_state = {
            "players": [player_name],
            "starting_difficulty": career_state.get("starting_difficulty", save_data.get("starting_difficulty", 75)),
            "tier": outcome["new_tier"],
            "unlocked_tier": outcome["new_unlocked_tier"],
            "score": career_state.get("score", 0),
            "championship": None,
            "player_car": None,
            "player_team_offer": None,
            "player_liveries": [],
            "watch_drivers": [],
            "rising_driver": None,
            "schedule": [],
            "standings": [],
            "current_race": 0,
            "world_sim_progress": None,
        }
        careers[player_name] = _rivals_career_snapshot(
            {
                **new_career_state,
                "save_name": save_name,
                "career_mode": "Rivals",
                "all_players": all_players,
                "active_player_name": player_name,
            },
            player_name,
        )

        if player_name == active_player:
            active_summary = summary
            active_final_standings = standings
            active_championship_name = str(player_championship.get("Championship", "Season Recap"))

    next_world_year = advance_world_year(save_name, 1)
    combined_driver_pool_summary["next_world_year"] = next_world_year
    if active_summary:
        active_summary["driver_pool"] = {
            **dict(active_summary.get("driver_pool") or {}),
            "world_simulation": combined_driver_pool_summary,
            "next_world_year": next_world_year,
        }
        active_summary["rivals_player_summaries"] = player_summaries

    payload = {
        "game": current_game,
        "career_mode": "Rivals",
        "players": all_players,
        "all_players": all_players,
        "active_player_name": active_player,
        "player_careers": careers,
        "player_perspectives": player_perspectives,
        "rivalry_heat": _merged_perspective_rivalry_heat(player_perspectives),
        "messages": messages,
        "world_setup_complete": True,
    }
    hydrated_payload = hydrate_active_rivals_state({**save_data, **payload})
    update_save(save_name, payload | {key: hydrated_payload.get(key) for key in CAREER_SNAPSHOT_KEYS if key != "players"})

    new_state = hydrate_active_rivals_state(load_save(save_name) or {})
    active_summary.setdefault("championship_name", active_championship_name)
    active_summary.setdefault("final_standings", active_final_standings)
    return new_state, active_summary
