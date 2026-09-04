from __future__ import annotations

import random
import uuid
from hashlib import sha256
from pathlib import Path
from typing import Any

from .driver_pool import driver_profile_map, team_colors_for_identity
from .json_storage import write_json_atomic
from .settings_manager import list_all_cars, load_settings


COLOR_SETS = [
    "1E90FF,111111,FFFFFF",
    "E10600,000000,FFFFFF",
    "005AFF,FFFFFF,000000",
    "FFD700,000000,1C1C1C",
    "00AEEF,FFFFFF,003366",
    "FF6600,000000,FFFFFF",
    "2E8B57,FFFFFF,000000",
    "800020,FFFFFF,000000",
    "6A0DAD,FFFFFF,000000",
    "FF1493,000000,FFFFFF",
    "0033A0,FFFFFF,C8102E",
    "009739,FFFFFF,FFCC00",
    "00247D,FFFFFF,CF142B",
    "CE1126,FFFFFF,002868",
    "FF0000,FFFF00,000000",
    "00FF00,000000,FFFFFF",
    "FF4500,1C1C1C,FFFFFF",
    "00CED1,000000,FFFFFF",
    "B22222,000000,FFFFFF",
    "708090,FFFFFF,000000",
]


def _color_set() -> str:
    return random.choice(COLOR_SETS)


def _driver_team_colors(driver: dict[str, Any]) -> str:
    return (
        team_colors_for_identity(
            str(driver.get("team_id", "")).strip(),
            str(driver.get("team_name", "")).strip(),
            "iRacing",
        )
        or _color_set()
    )


def team_color_set(seed: str) -> str:
    cleaned_seed = str(seed).strip() or "Independent"
    digest = sha256(cleaned_seed.encode("utf-8")).hexdigest()
    index = int(digest[:8], 16) % len(COLOR_SETS)
    return COLOR_SETS[index]


def _number_design(colors: str) -> str:
    return f"{random.randint(0, 24)},{random.randint(0, 24)},{colors}"


def _driver_class_name(driver: dict[str, Any]) -> str:
    return str(driver.get("class_name", "")).strip() or "Overall"


def _championship_cars(championship: dict[str, Any]) -> list[dict[str, str]]:
    car_ids = set(str(value).strip() for value in str(championship.get("_championship_car_ids", "")).split(",") if str(value).strip())
    if not car_ids:
        return []
    return [car for car in list_all_cars() if str(car.get("id", "")).strip() in car_ids]


def _championship_cars_by_class(championship: dict[str, Any]) -> dict[str, set[str]]:
    """Map the championship's display classes to its actual iRacing cars.

    Custom championships can use names such as ``LMP2`` or ``GT3`` while the
    catalog uses more specific labels (for example, ``LMP2 Gen 2``). Matching
    by the catalog's display label therefore sends every unmatched class to
    the fallback pool. The championship entry rows are the authoritative
    class-to-car mapping.
    """
    rows = championship.get("_entry_rows") or championship.get("_player_entry_rows")
    if not isinstance(rows, list):
        return {}

    cars = {str(car.get("id", "")).strip(): car for car in list_all_cars()}
    mapping: dict[str, set[str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        class_name = str(row.get("Class_Name", "")).strip()
        if not class_name:
            class_name = str(row.get("Sub_Champ", "")).strip()
            if class_name.casefold().startswith("class ") and ":" in class_name:
                class_name = class_name.split(":", 1)[1].strip()
        if not class_name:
            continue

        car_ids: set[str] = set()
        car_id = str(row.get("Car_ID", "")).strip()
        if car_id and car_id in cars:
            car_ids.add(car_id)
        class_id = str(row.get("Car_Class", "")).strip()
        if class_id:
            car_ids.update(
                candidate_id
                for candidate_id, car in cars.items()
                if str(car.get("Car_Class_ID", "")).strip() == class_id
            )
        if car_ids:
            mapping.setdefault(class_name.casefold(), set()).update(car_ids)
    return mapping


def _car_for_driver(
    driver: dict[str, Any], championship: dict[str, Any], player_car: dict[str, str] | None
) -> dict[str, str] | None:
    if player_car and driver["name"] in set(championship.get("_player_names", [])):
        return player_car

    class_name = _driver_class_name(driver)
    championship_cars = _championship_cars(championship)
    class_car_ids = _championship_cars_by_class(championship).get(class_name.casefold(), set())
    eligible = [
        car for car in championship_cars
        if str(car.get("id", "")).strip() in class_car_ids
    ]
    if not eligible:
        eligible = []
    for car in championship_cars:
        car_class = str(car.get("Car class", "")).strip() or str(car.get("Car", "")).strip()
        if not class_car_ids and car_class.casefold() == class_name.casefold():
            eligible.append(car)

    if eligible:
        return random.choice(eligible)

    if player_car:
        return player_car

    cars = _championship_cars(championship)
    return random.choice(cars) if cars else None


def build_roster_drivers(
    save_name: str,
    standings: list[dict[str, Any]],
    championship: dict[str, Any],
    player_names: list[str],
    player_car: dict[str, str] | None,
) -> list[dict[str, Any]]:
    championship_with_players = dict(championship)
    championship_with_players["_player_names"] = list(player_names)
    player_set = set(player_names)
    profiles = driver_profile_map(save_name)

    roster_drivers = []
    for index, driver in enumerate(standings):
        if driver["name"] in player_set:
            continue
        colors = _driver_team_colors(driver)
        car = _car_for_driver(driver, championship_with_players, player_car)
        profile = profiles.get(str(driver["name"]), {})
        base_skill = int(profile.get("iracing_relative_skill", driver.get("skill", 75)) or 75)
        roster_drivers.append(
            {
                "driverName": driver["name"],
                "carDesign": f"{random.randint(0, 24)},{colors}",
                "carNumber": str(random.randint(0, 99)),
                "suitDesign": f"{random.randint(0, 24)},{colors}",
                "helmetDesign": f"{random.randint(0, 24)},{colors}",
                "carPath": str(car.get("FILEPATH", "")) if car else "",
                "carId": int(car.get("Iracing_ID", 0) or 0) if car else 0,
                "sponsor1": int(profile.get("iracing_sponsor1", 0) or 0),
                "sponsor2": int(profile.get("iracing_sponsor2", 0) or 0),
                "numberDesign": _number_design(colors),
                "driverSkill": base_skill,
                "driverAggression": int(profile.get("iracing_aggression", base_skill) or base_skill),
                "driverOptimism": int(profile.get("iracing_optimism", base_skill) or base_skill),
                "driverSmoothness": int(profile.get("iracing_smoothness", base_skill) or base_skill),
                "pitCrewSkill": int(profile.get("iracing_pit_crew_skill", base_skill) or base_skill),
                "strategyRiskiness": int(profile.get("iracing_strategy_riskiness", base_skill) or base_skill),
                "driverAge": int(profile.get("driver_age", 28) or 28),
                "id": str(uuid.uuid4()),
                "rowIndex": index,
                "carClassId": int(car.get("Car_Class_ID", 0) or 0) if car else 0,
            }
        )
    return roster_drivers


def export_roster(
    save_name: str,
    championship: dict[str, Any],
    standings: list[dict[str, Any]],
    player_names: list[str],
    player_car: dict[str, str] | None,
) -> Path:
    settings = load_settings()
    iracing_dir = Path(settings["iracing_directory"])
    roster_dir = iracing_dir / "airosters" / f"CS-{championship['Championship']}-{save_name}"
    roster_dir.mkdir(parents=True, exist_ok=True)

    payload = {"drivers": build_roster_drivers(save_name, standings, championship, player_names, player_car)}
    roster_path = roster_dir / "roster.json"
    write_json_atomic(roster_path, payload)
    return roster_path
