from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .roster_exporter import build_roster_drivers
from .settings_manager import load_settings


MONTH_LOOKUP = {
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
}

TIME_TO_HOUR = {
    "Morning": 9,
    "Afternoon": 14,
    "Evening": 18,
    "Night": 21,
}

TIME_OF_DAY_VALUE = {
    "Morning": 0,
    "Afternoon": 2,
    "Evening": 4,
    "Night": 6,
}

SESSION_TIME_OFFSETS = [60, 120]

WEATHER_TO_SKIES = {
    "Sunny": 0,
    "Cloudy": 1,
    "Overcast": 2,
    "Light Rain": 3,
    "Heavy Rain": 3,
    "Foggy": 1,
}

WEATHER_TO_PRECIP = {
    "Sunny": 8,
    "Cloudy": 8,
    "Overcast": 8,
    "Light Rain": 1,
    "Heavy Rain": 0,
    "Foggy": 8,
}

WEATHER_TO_WATER = {
    "Sunny": 0,
    "Cloudy": 0,
    "Overcast": 0,
    "Light Rain": 12,
    "Heavy Rain": 35,
    "Foggy": 0,
}

WEATHER_TIMELINES = {
    # iRacing event types:
    # 0 clear, 1 partly cloudy, 2 mostly cloudy, 3 overcast,
    # 4 light fog, 5 dense fog, 6 light rain, 7 moderate rain,
    # 8 heavy rain, 9 spotty rain.
    "Sunny": [0, 1, 0, 1, 0, 1, 0, 1],
    "Cloudy": [1, 2, 1, 2, 3, 2, 1, 2],
    "Overcast": [2, 3, 2, 3, 2, 3, 2, 3],
    "Light Rain": [3, 6, 9, 6, 3, 9, 6, 3],
    "Heavy Rain": [3, 6, 7, 8, 7, 6, 3, 7],
    "Foggy": [4, 5, 4, 3, 4, 5, 4, 3],
}

IRACING_MAX_SKILL_SPREAD = 25
IRACING_MIN_SKILL_SPREAD = 15
IRACING_MIN_PRESTIGE = 1
IRACING_MAX_PRESTIGE = 100


def _category_id(style: str) -> int:
    normalized = str(style).strip().casefold()
    if normalized in {"oval", "20r/80o"}:
        return 1
    if normalized in {"open wheel", "80r/20o"}:
        return 2
    return 5


def _pace_car(style: str) -> dict[str, Any]:
    normalized = str(style).strip().casefold()
    if normalized in {"oval", "20r/80o"}:
        return {
            "category_id": 1,
            "car_id": 136,
            "is_oval": True,
            "is_dirt": False,
            "car_name": "Pace Car - Sedan",
            "car_class_id": 11,
            "order": 3,
        }
    if normalized in {"open wheel", "80r/20o"}:
        return {
            "category_id": 2,
            "car_id": 136,
            "is_oval": False,
            "is_dirt": False,
            "car_name": "Pace Car - Sedan",
            "car_class_id": 11,
            "order": 3,
        }
    return {
        "category_id": 2,
        "car_id": 90,
        "is_oval": False,
        "is_dirt": False,
        "car_name": "Pace Car - Truck",
        "car_class_id": 11,
        "order": 5,
    }


def _rolling_starts(championship: dict[str, Any]) -> bool:
    return str(championship.get("Start_Type", "")).strip().casefold() == "rolling"


def _race_length(championship: dict[str, Any]) -> int:
    try:
        return max(5, int(championship.get("Race_Time", 15)))
    except (TypeError, ValueError):
        return 15


def _scheduled_race_datetime(race: dict[str, Any]) -> datetime:
    date_bits = str(race.get("date", "15 May")).split()
    day = int(date_bits[0]) if date_bits and str(date_bits[0]).isdigit() else 15
    month = MONTH_LOOKUP.get(date_bits[1], 5) if len(date_bits) > 1 else 5
    hour = TIME_TO_HOUR.get(str(race.get("time_of_day", "Afternoon")), 14)
    return datetime(2026, month, day, hour, 0, 0)


def _simulated_start_time(race: dict[str, Any]) -> str:
    practice_start = _scheduled_race_datetime(race) - timedelta(hours=2)
    return practice_start.strftime("%Y-%m-%dT%H:%M:%S")


def _weather_payload(
    race: dict[str, Any],
    *,
    event_id: str | None = None,
    top_level: bool = False,
) -> dict[str, Any]:
    weather_name = str(race.get("weather", "Sunny"))
    time_name = str(race.get("time_of_day", "Afternoon"))
    style_name = str(race.get("style", "")).strip().casefold()
    if style_name == "oval" and "Rain" in weather_name:
        weather_name = "Overcast"
    weather_id = f"712588_{uuid.uuid4()}"
    keyframes = _weather_keyframes(weather_name)
    weather_timeline: dict[str, Any] = {
        "keyframes": [dict(frame) for frame in keyframes],
        "wind_direction_option": 0,
        "wind_speed_option": 0,
        "temperature_option": 0,
        "weatherId": weather_id,
    }
    if event_id:
        weather_timeline["eventId"] = event_id

    payload: dict[str, Any] = {
        "type": 3,
        "temp_units": 0,
        "temp_value": random.randint(58, 82),
        "rel_humidity": random.choice([35, 45, 55, 65]),
        "fog": 0,
        "wind_dir": 0,
        "wind_units": 0,
        "wind_value": random.randint(1, 4),
        "skies": WEATHER_TO_SKIES.get(weather_name, 1),
        "simulated_start_time": _simulated_start_time(race),
        "simulated_time_multiplier": 1,
        "simulated_time_offsets": SESSION_TIME_OFFSETS[:],
        "version": 3,
        "weather_var_initial": 0,
        "weather_var_ongoing": 0,
        "weather_id": weather_id,
        "weather_timeline": weather_timeline,
        "keyframes": [dict(frame) for frame in keyframes],
    }
    if top_level:
        payload["time_of_day"] = TIME_OF_DAY_VALUE.get(time_name, 2)
        payload["track_water"] = WEATHER_TO_WATER.get(weather_name, 0)
        payload["guided_parameters"] = {
            "temperature": 0,
            "wind_dir": 0,
            "wind_speed": 0,
            "skies": 0,
            "precipitation": 0,
            "stop_precip": 0,
            "allow_fog": False,
        }
    return payload


def _weather_keyframes(weather_name: str) -> list[dict[str, int]]:
    base_event_types = WEATHER_TIMELINES.get(weather_name, WEATHER_TIMELINES["Sunny"])
    max_blocks = min(8, len(base_event_types))
    block_options = list(range(1, max_blocks + 1))
    weighted_block_counts = [1, 10, 10, 8, 4, 3, 2, 1][:max_blocks]
    if weather_name in {"Light Rain", "Heavy Rain"} and max_blocks >= 2:
        # Wet events should still use at least a small timeline arc.
        block_options = [count for count in block_options if count >= 3]
        weighted_block_counts = weighted_block_counts[2:]
    block_count = random.choices(block_options, weights=weighted_block_counts, k=1)[0]
    event_types = base_event_types[:block_count]
    offsets = _timeline_offsets(block_count)
    frames: list[dict[str, int]] = []
    for index, (event_type, time_offset) in enumerate(zip(event_types, offsets)):
        frames.append(
            {
                "event_type": event_type,
                "index": index,
                "time_offset": time_offset,
            }
        )
    return frames


def iracing_skill_spread_for_prestige(prestige: int | str | None) -> int:
    try:
        normalized_prestige = int(prestige or IRACING_MIN_PRESTIGE)
    except (TypeError, ValueError):
        normalized_prestige = IRACING_MIN_PRESTIGE
    normalized_prestige = max(IRACING_MIN_PRESTIGE, min(IRACING_MAX_PRESTIGE, normalized_prestige))
    scale = (normalized_prestige - IRACING_MIN_PRESTIGE) / (IRACING_MAX_PRESTIGE - IRACING_MIN_PRESTIGE)
    spread_range = IRACING_MAX_SKILL_SPREAD - IRACING_MIN_SKILL_SPREAD
    return int(round(IRACING_MAX_SKILL_SPREAD - (spread_range * scale)))


def _difficulty_bounds(starting_difficulty: int, prestige: int | str | None) -> tuple[int, int]:
    max_skill = max(0, min(125, int(starting_difficulty)))
    min_skill = max(0, max_skill - iracing_skill_spread_for_prestige(prestige))
    return min_skill, max_skill


def _timeline_offsets(block_count: int) -> list[int]:
    if block_count <= 1:
        return [-120]
    if block_count == 2:
        return [-120, 30]

    middle_slots = sorted(random.sample(range(-105, 16), block_count - 2))
    return [-120, *middle_slots, 30]


def _track_state(style: str) -> dict[str, Any]:
    if str(style).strip().casefold() == "oval":
        return {
            "leave_marbles": False,
            "practice_rubber": 50,
            "qualify_rubber": -1,
            "race_rubber": 80,
            "warmup_rubber": -1,
        }
    return {
        "leave_marbles": True,
        "practice_rubber": -1,
        "qualify_rubber": -1,
        "race_rubber": -1,
        "warmup_rubber": -1,
    }


def _event_payload(
    race: dict[str, Any],
    championship: dict[str, Any],
    style: str,
    *,
    include_weather: bool = True,
) -> dict[str, Any]:
    event_id = str(uuid.uuid4())
    race_with_style = dict(race)
    race_with_style["style"] = style
    event = {
        "trackId": int(race.get("track_id", 0) or 0),
        "num_opt_laps": 0,
        "paceCar": _pace_car(style),
        "short_parade_lap": False,
        "must_use_diff_tire_types_in_race": False,
        "subsessions": [3, 4, 6],
        "eventId": event_id,
    }

    if _rolling_starts(championship):
        event["rolling_starts"] = True
    if str(style).strip().casefold() == "oval":
        event["race_laps"] = _race_length(championship)

    if include_weather:
        event["weather"] = _weather_payload(race_with_style, event_id=event_id)
    event["track_state"] = {
        **_track_state(style),
        "practice_grip_compound": None,
        "qualify_grip_compound": None,
        "warmup_grip_compound": None,
        "race_grip_compound": None,
    }
    return event


def export_season(
    save_name: str,
    championship: dict[str, Any],
    standings: list[dict[str, Any]],
    player_names: list[str],
    player_car: dict[str, str] | None,
    schedule: list[dict[str, Any]],
    starting_difficulty: int = 75,
) -> Path:
    settings = load_settings()
    iracing_dir = Path(settings["iracing_directory"])
    season_dir = iracing_dir / "aiseasons"
    season_dir.mkdir(parents=True, exist_ok=True)

    roster_name = f"CS-{championship['Championship']}-{save_name}"
    roster_drivers = build_roster_drivers(save_name, standings, championship, player_names, player_car)
    ai_class_ids = sorted({int(driver.get("carClassId", 0) or 0) for driver in roster_drivers if int(driver.get("carClassId", 0) or 0) > 0})
    min_skill, max_skill = _difficulty_bounds(starting_difficulty, championship.get("Prestige", 1))
    style = championship.get("Style", "")
    category_id = _category_id(style)
    player_car_id = int((player_car or {}).get("Iracing_ID", 0) or 0)
    player_class_id = int((player_car or {}).get("Car_Class_ID", 0) or 0)
    rolling = _rolling_starts(championship)
    events = [
        _event_payload(race, championship, style, include_weather=index > 0)
        for index, race in enumerate(schedule)
    ]
    if schedule:
        first_race = dict(schedule[0])
        first_race["style"] = style
        top_level_weather = _weather_payload(first_race, top_level=True)
    else:
        top_level_weather = _weather_payload({}, top_level=True)

    payload: dict[str, Any] = {
        "adaptiveAIEnabled": False,
        "adaptiveAIDifficulty": 0,
        "aiCarClassIds": ai_class_ids,
        "avoidUser": False,
        "carId": player_car_id,
        "carSettings": [
            {
                "car_id": player_car_id,
                "max_pct_fuel_fill": 100,
                "max_dry_tire_sets": 0,
            }
        ],
        "category_id": category_id,
        "damage_model": 0,
        "do_not_count_caution_laps": False,
        "full_course_cautions": category_id == 1,
        "gridPosition": 1,
        "incident_limit": 0 if category_id != 1 else 17,
        "incident_warn_mode": 0,
        "incident_warn_param1": 0,
        "incident_warn_param2": 0,
        "lucky_dog": category_id == 1,
        "max_drivers": len(roster_drivers) + 1,
        "maxSkill": max_skill,
        "minSkill": min_skill,
        "max_visor_tearoffs": -1,
        "multiclassType": 2,
        "must_use_diff_tire_types_in_race": False,
        "no_lapper_wave_arounds": False,
        "num_fast_tows": -1 if category_id == 1 else 1,
        "practice_length": 20,
        "qualify_laps": 2,
        "qualify_length": 10,
        "race_laps": _race_length(championship) if category_id == 1 else 0,
        "race_length_type": 3 if category_id == 1 else 2,
        "race_length": _race_length(championship),
        "restarts": 2,
        "rolling_starts": rolling,
        "rosterName": roster_name,
        "short_parade_lap": False,
        "start_on_qual_tire": False,
        "startZone": 1 if category_id == 1 else 0,
        "subsessions": [3, 4, 6],
        "time_of_day": 0,
        "track_state": _track_state(style),
        "unsport_conduct_rule_mode": 0,
        "userCarClassId": player_class_id,
        "weather": top_level_weather,
        "events": events,
        "points_system_id": 4,
        "name": roster_name,
    }

    season_path = season_dir / f"{roster_name}.json"
    season_path.write_text(json.dumps(payload, indent=4), encoding="utf-8")
    return season_path


def update_exported_season_difficulty(
    season_path: str | Path,
    championship: dict[str, Any],
    starting_difficulty: int,
) -> bool:
    path = Path(season_path)
    if not path.exists():
        return False

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False

    min_skill, max_skill = _difficulty_bounds(starting_difficulty, championship.get("Prestige", 1))
    payload["minSkill"] = min_skill
    payload["maxSkill"] = max_skill

    try:
        path.write_text(json.dumps(payload, indent=4), encoding="utf-8")
    except OSError:
        return False
    return True
