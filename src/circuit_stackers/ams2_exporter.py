from __future__ import annotations

import csv
import hashlib
import random
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from .driver_pool import driver_profile_map, get_team_profile, get_team_snapshot_for_identity
from .paths import resource_path
from .settings_manager import game_directory


AMS2_LIVERIES_CSV = resource_path("data", "AMS2liveries.csv")
AMS2_CARS_CSV = resource_path("data", "Cars.csv")
_AMS2_LIVERY_ROWS_CACHE: list[dict[str, str]] | None = None
_AMS2_CAR_ROWS_CACHE: list[dict[str, str]] | None = None
_CUSTOM_LIVERY_ROWS_CACHE: dict[str, list[dict[str, str]]] = {}


@dataclass(frozen=True)
class Ams2RosterValidation:
    ok: bool
    message: str
    roster_paths: tuple[Path, ...] = ()
    missing_files: tuple[str, ...] = ()
    mismatched_rosters: tuple[str, ...] = ()


def _driver_class_name(driver: dict[str, Any]) -> str:
    return str(driver.get("class_name", "")).strip() or "Overall"


def _load_livery_rows() -> list[dict[str, str]]:
    global _AMS2_LIVERY_ROWS_CACHE
    if _AMS2_LIVERY_ROWS_CACHE is not None:
        return [dict(row) for row in _AMS2_LIVERY_ROWS_CACHE]
    with AMS2_LIVERIES_CSV.open(newline="", encoding="utf-8") as file_obj:
        _AMS2_LIVERY_ROWS_CACHE = [dict(row) for row in csv.DictReader(file_obj)]
    return [dict(row) for row in _AMS2_LIVERY_ROWS_CACHE]


def _load_ams2_car_rows() -> list[dict[str, str]]:
    global _AMS2_CAR_ROWS_CACHE
    if _AMS2_CAR_ROWS_CACHE is not None:
        return [dict(row) for row in _AMS2_CAR_ROWS_CACHE]
    with AMS2_CARS_CSV.open(newline="", encoding="utf-8") as file_obj:
        _AMS2_CAR_ROWS_CACHE = [
            dict(row)
            for row in csv.DictReader(file_obj)
            if str(row.get("Game", "")).strip().casefold() == "ams2"
        ]
    return [dict(row) for row in _AMS2_CAR_ROWS_CACHE]


def _custom_livery_root() -> Path | None:
    ams2_root = Path(game_directory("AMS2"))
    if not str(ams2_root).strip():
        return None
    overrides = ams2_root / "Vehicles" / "Textures" / "CustomLiveries" / "Overrides"
    return overrides if overrides.exists() else None


def _add_unique_livery_name(names: list[str], seen: set[str], livery_name: str) -> None:
    cleaned_name = str(livery_name).strip()
    if not cleaned_name or cleaned_name.casefold() in seen:
        return
    seen.add(cleaned_name.casefold())
    names.append(cleaned_name)


def _custom_ai_livery_names_for_roster(roster_name: str) -> list[str]:
    ams2_root = Path(game_directory("AMS2"))
    if not str(ams2_root).strip():
        return []
    custom_ai_dir = ams2_root / "UserData" / "CustomAIDrivers"
    if not custom_ai_dir.exists():
        return []

    roster_stem = Path(str(roster_name).strip()).stem.casefold()
    names: list[str] = []
    seen: set[str] = set()
    for xml_path in custom_ai_dir.glob("*.xml"):
        # Match related roster files, like F-Ultimate_Gen2_2025.xml for F-Ultimate_Gen2.xml.
        if roster_stem and roster_stem not in xml_path.stem.casefold():
            continue
        try:
            tree = ET.parse(xml_path)
        except ET.ParseError:
            continue
        for node in tree.iter():
            if str(node.tag).split("}")[-1].casefold() != "driver":
                continue
            if str(node.attrib.get("tracks", "")).strip():
                continue
            _add_unique_livery_name(names, seen, str(node.attrib.get("livery_name", "")))
    return names


def _custom_livery_names_for_folder(folder_name: str) -> list[str]:
    cleaned_folder = str(folder_name).strip()
    if not cleaned_folder:
        return []
    root = _custom_livery_root()
    if root is None:
        return []
    folder_path = root / cleaned_folder
    if not folder_path.exists():
        return []

    names: list[str] = []
    seen: set[str] = set()
    for xml_path in folder_path.rglob("*.xml"):
        if xml_path.name.casefold().endswith("_dist.xml"):
            continue
        try:
            tree = ET.parse(xml_path)
        except ET.ParseError:
            continue
        for node in tree.iter():
            if str(node.tag).split("}")[-1].casefold() != "livery_override":
                continue
            _add_unique_livery_name(names, seen, str(node.attrib.get("NAME", "") or node.attrib.get("Name", "")))
    return names


def _car_ids_for_class(class_name: str) -> set[str]:
    normalized_class = str(class_name).strip().casefold()
    return {
        str(row.get("id", "")).strip()
        for row in _load_ams2_car_rows()
        if str(row.get("id", "")).strip()
        and str(row.get("Car class", "")).strip().casefold() == normalized_class
    }


def _custom_livery_rows_for_class(class_name: str, default_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    cache_key = str(class_name).strip().casefold()
    if cache_key in _CUSTOM_LIVERY_ROWS_CACHE:
        return [dict(row) for row in _CUSTOM_LIVERY_ROWS_CACHE[cache_key]]

    class_car_ids = _car_ids_for_class(class_name)
    if not class_car_ids:
        _CUSTOM_LIVERY_ROWS_CACHE[cache_key] = []
        return []

    default_by_car_id: dict[str, dict[str, str]] = {}
    fallback_row = default_rows[0] if default_rows else {}
    for row in default_rows:
        for car_id in str(row.get("car_id", "")).replace("|", ";").replace(",", ";").split(";"):
            cleaned_car_id = car_id.strip()
            if cleaned_car_id:
                default_by_car_id.setdefault(cleaned_car_id, row)

    custom_rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    custom_ai_names = _custom_ai_livery_names_for_roster(str(fallback_row.get("Roster_Name", "")).strip())
    for car in _load_ams2_car_rows():
        car_id = str(car.get("id", "")).strip()
        if car_id not in class_car_ids:
            continue
        folder_name = str(car.get("ams2_livery_folder", "")).strip()
        if not folder_name:
            continue
        template = default_by_car_id.get(car_id, fallback_row)
        if not template:
            continue
        livery_names = _custom_livery_names_for_folder(folder_name) + custom_ai_names
        for livery_name in livery_names:
            key = (car_id, livery_name.casefold())
            if key in seen:
                continue
            seen.add(key)
            row = dict(template)
            row["car_id"] = car_id
            row["Car_Name"] = str(car.get("Car", "")).strip() or str(template.get("Car_Name", "")).strip()
            row["Class"] = str(template.get("Class", "")).strip()
            row["livery_name"] = livery_name
            row["Roster_Name"] = str(template.get("Roster_Name", "")).strip()
            row["_custom_livery"] = "yes"
            row["_override_folder"] = folder_name
            custom_rows.append(row)

    _CUSTOM_LIVERY_ROWS_CACHE[cache_key] = [dict(row) for row in custom_rows]
    return custom_rows


def _livery_rows_for_class(class_name: str) -> list[dict[str, str]]:
    normalized_class = str(class_name).strip().casefold()
    rows = [
        row
        for row in _load_livery_rows()
        if str(row.get("Car_Name", "")).strip().casefold() == normalized_class
    ]
    if rows:
        return _custom_livery_rows_for_class(class_name, rows) + rows
    class_rows = [
        row
        for row in _load_livery_rows()
        if str(row.get("Class", "")).strip().casefold() == normalized_class
    ]
    return _custom_livery_rows_for_class(class_name, class_rows) + class_rows


def _compact_text(value: Any) -> str:
    return "".join(ch for ch in str(value).casefold() if ch.isalnum())


def _livery_rows_for_player_car(
    player_car: dict[str, str] | None,
    class_name: str,
    class_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    if not player_car:
        return class_rows

    selected_class = str(player_car.get("Car class", "")).strip()
    if selected_class and selected_class.casefold() != str(class_name).strip().casefold():
        return class_rows

    car_id = str(player_car.get("id", "")).strip()
    if car_id:
        id_rows = [
            row
            for row in class_rows
            if car_id in {
                value.strip()
                for value in str(row.get("car_id", "")).replace("|", ";").replace(",", ";").split(";")
                if value.strip()
            }
        ]
        if id_rows:
            return id_rows

    car_name = str(player_car.get("Car", "")).strip()
    normalized_car = _compact_text(car_name)
    if not normalized_car:
        return class_rows

    exact_rows = [
        row
        for row in class_rows
        if _compact_text(row.get("Car_Name", "")) == normalized_car
    ]
    if exact_rows:
        return exact_rows

    name_rows = [
        row
        for row in class_rows
        if normalized_car in _compact_text(row.get("livery_name", ""))
    ]
    if name_rows:
        return name_rows

    return class_rows


def preview_player_livery_for_car(
    player_car: dict[str, str] | None,
    assignment_key: str = "",
    reserved_livery_names: set[str] | None = None,
) -> dict[str, str]:
    if not player_car:
        return {}
    class_name = str(player_car.get("Car class", "")).strip() or str(player_car.get("Car", "")).strip()
    if not class_name:
        return {}
    rows = _livery_rows_for_class(class_name)
    if not rows:
        return {}
    player_rows = _livery_rows_for_player_car(player_car, class_name, rows)
    if not player_rows:
        return {}
    reserved = {
        str(name).strip().casefold()
        for name in (reserved_livery_names or set())
        if str(name).strip()
    }
    available_rows = [
        row
        for row in player_rows
        if str(row.get("livery_name", "")).strip().casefold() not in reserved
    ] or player_rows
    if assignment_key:
        ordered_rows = sorted(
            available_rows,
            key=lambda row: (
                str(row.get("livery_name", "")).strip().casefold(),
                str(row.get("Car_Name", "")).strip().casefold(),
                str(row.get("car_id", "")).strip(),
            ),
        )
        seed = int(hashlib.sha256(str(assignment_key).encode("utf-8")).hexdigest()[:16], 16)
        return dict(ordered_rows[seed % len(ordered_rows)])
    return dict(random.choice(available_rows))


def _general_ams2_skill(profile: dict[str, Any], fallback_skill: int) -> float:
    try:
        general_skill = float(profile.get("ams2_general_skill", -1))
    except (TypeError, ValueError):
        general_skill = -1
    if general_skill >= 0:
        return max(0.0, min(100.0, general_skill))

    try:
        race_skill = float(profile.get("ams2_race_skill", 0) or 0)
    except (TypeError, ValueError):
        race_skill = 0
    if race_skill > 0:
        return max(0.0, min(100.0, race_skill * 100.0))
    return max(0.0, min(100.0, float(fallback_skill)))


def ams2_export_skill_floor_for_prestige(prestige: int | str | None) -> float:
    try:
        normalized_prestige = int(prestige or 1)
    except (TypeError, ValueError):
        normalized_prestige = 1
    normalized_prestige = max(1, min(100, normalized_prestige))
    scale = (normalized_prestige - 1) / 99
    return round(0.40 + (scale * 0.30), 2)


def _scale_roster_ams2_skills(
    drivers: list[dict[str, Any]],
    profiles: dict[str, dict[str, Any]],
    low: float = 0.40,
    high: float = 0.90,
) -> dict[str, float]:
    driver_skills: dict[str, float] = {}
    for driver in drivers:
        driver_name = str(driver.get("name", "")).strip()
        if not driver_name:
            continue
        profile = profiles.get(driver_name, {})
        fallback_skill = int(driver.get("skill", 60) or 60)
        driver_skills[driver_name] = _general_ams2_skill(profile, fallback_skill)

    if not driver_skills:
        return {}

    # Drivers above the normal AMS2 export ceiling should read as true outliers in-game.
    elite_skills = {
        name: round(skill / 100.0, 2)
        for name, skill in driver_skills.items()
        if skill >= 93.0
    }
    scaled_driver_skills = {
        name: skill
        for name, skill in driver_skills.items()
        if name not in elite_skills
    }
    if not scaled_driver_skills:
        return elite_skills

    min_skill = min(scaled_driver_skills.values())
    max_skill = max(scaled_driver_skills.values())
    if max_skill == min_skill:
        midpoint = round((low + high) / 2.0, 2)
        return {**{name: midpoint for name in scaled_driver_skills}, **elite_skills}

    spread = max_skill - min_skill
    ranked_drivers = sorted(scaled_driver_skills.items(), key=lambda item: (item[1], item[0]))
    max_rank = max(1, len(ranked_drivers) - 1)
    scaled: dict[str, float] = {}
    for rank, (name, skill) in enumerate(ranked_drivers):
        rank_percent = rank / max_rank
        skill_percent = (skill - min_skill) / spread
        # Blend true skill with roster rank, then use an easing curve to avoid a bottom-heavy AMS2 field.
        blended_percent = (rank_percent * 0.70) + (skill_percent * 0.30)
        curved_percent = blended_percent ** 0.70
        scaled[name] = round(low + curved_percent * (high - low), 2)
    scaled.update(elite_skills)
    return scaled


def _normalized_qualifying_skill(
    profile: dict[str, Any],
    normalized_race_skill: float,
    low: float = 0.40,
) -> float:
    try:
        raw_qualifying = float(profile.get("ams2_qualifying_skill", normalized_race_skill) or normalized_race_skill)
        raw_race = float(profile.get("ams2_race_skill", normalized_race_skill) or normalized_race_skill)
    except (TypeError, ValueError):
        return normalized_race_skill
    offset = max(-0.2, min(0.2, raw_qualifying - raw_race))
    high = 1.00 if normalized_race_skill > 0.90 else 0.90
    return round(max(low, min(high, normalized_race_skill + offset)), 2)


def _build_driver_stats(
    profile: dict[str, Any],
    fallback_skill: int,
    normalized_race_skill: float | None = None,
    normalized_skill_floor: float = 0.40,
    team_bop: dict[str, float] | None = None,
) -> dict[str, str]:
    race_skill = (
        normalized_race_skill
        if normalized_race_skill is not None
        else float(profile.get("ams2_race_skill", fallback_skill / 100.0) or fallback_skill / 100.0)
    )
    qualifying_skill = (
        _normalized_qualifying_skill(profile, race_skill, normalized_skill_floor)
        if normalized_race_skill is not None
        else float(profile.get("ams2_qualifying_skill", fallback_skill / 100.0) or fallback_skill / 100.0)
    )
    team_bop = dict(team_bop or {})
    return {
        "aggression": f"{float(profile.get('ams2_aggression', 0.5) or 0.5):.2f}",
        "avoidance_of_forced_mistakes": f"{float(profile.get('ams2_avoidance_of_forced_mistakes', 0.8) or 0.8):.2f}",
        "avoidance_of_mistakes": f"{float(profile.get('ams2_avoidance_of_mistakes', 0.8) or 0.8):.2f}",
        "blue_flag_conceding": f"{float(profile.get('ams2_blue_flag_conceding', 0.8) or 0.8):.2f}",
        "consistency": f"{float(profile.get('ams2_consistency', 0.8) or 0.8):.2f}",
        "defending": f"{float(profile.get('ams2_defending', 0.5) or 0.5):.2f}",
        "drag_scalar": f"{float(team_bop.get('drag_scalar', profile.get('ams2_drag_scalar', 1.0) or 1.0)):.3f}",
        "fuel_management": f"{float(profile.get('ams2_fuel_management', 0.8) or 0.8):.2f}",
        "power_scalar": f"{float(team_bop.get('power_scalar', profile.get('ams2_power_scalar', 1.0) or 1.0)):.3f}",
        "qualifying_skill": f"{qualifying_skill:.2f}",
        "race_skill": f"{race_skill:.2f}",
        "setup_downforce": f"{float(profile.get('ams2_setup_downforce', 0.5) or 0.5):.3f}",
        "setup_downforce_randomness": f"{float(profile.get('ams2_setup_downforce_randomness', 0.35) or 0.35):.3f}",
        "stamina": f"{float(profile.get('ams2_stamina', 0.8) or 0.8):.2f}",
        "start_reactions": f"{float(profile.get('ams2_start_reactions', 0.8) or 0.8):.2f}",
        "tyre_management": f"{float(profile.get('ams2_tyre_management', 0.8) or 0.8):.2f}",
        "vehicle_reliability": f"{float(profile.get('ams2_vehicle_reliability', 0.85) or 0.85):.2f}",
        "weather_tyre_changes": f"{float(profile.get('ams2_weather_tyre_changes', 0.8) or 0.8):.2f}",
        "weight_scalar": f"{float(team_bop.get('weight_scalar', profile.get('ams2_weight_scalar', 1.0) or 1.0)):.3f}",
        "wet_skill": f"{float(profile.get('ams2_wet_skill', fallback_skill / 100.0) or fallback_skill / 100.0):.2f}",
    }


def _clamp_bop_scalar(value: float) -> float:
    return round(max(0.9, min(1.1, float(value))), 3)


def _team_bop_for_driver(
    save_name: str,
    driver: dict[str, Any],
    team_sizes: dict[str, int],
    team_profile_cache: dict[str, dict[str, Any] | None],
) -> dict[str, float]:
    team_key = str(driver.get("team_key", "")).strip()
    if not team_key:
        return {}
    if team_key not in team_profile_cache:
        team_profile_cache[team_key] = get_team_profile(save_name, team_key)
    team_profile = team_profile_cache.get(team_key) or {}
    if team_profile:
        team_profile = dict(team_profile.get("team") or {})
    else:
        team_profile = get_team_snapshot_for_identity(
            save_name,
            team_id=str(driver.get("team_id", "")).strip(),
            team_name=str(driver.get("team_name", "")).strip(),
            game=str(driver.get("game", "AMS2") or "AMS2").strip(),
            fallback_prestige=int(driver.get("team_prestige", 50) or 50),
            team_key=team_key,
        )
    current_strength = int(
        team_profile.get(
            "current_strength",
            driver.get("team_reputation", driver.get("team_prestige", 50)),
        )
        or driver.get("team_reputation", driver.get("team_prestige", 50))
        or 50
    )
    pressure = int(team_profile.get("team_pressure", 50) or 50)
    stability = int(team_profile.get("team_stability", 50) or 50)
    financial_strength = int(team_profile.get("team_financial_strength", 50) or 50)
    philosophy = str(team_profile.get("team_philosophy", "Balanced")).strip().casefold()
    trajectory = str(team_profile.get("trajectory", "stable")).strip().casefold()
    team_seat = max(1, int(driver.get("team_seat", 1) or 1))
    team_size = max(1, int(team_sizes.get(team_key, 1) or 1))
    team_reputation = int(driver.get("team_reputation", current_strength) or current_strength)
    team_prestige = int(driver.get("team_prestige", team_reputation) or team_reputation)

    strength_delta = (current_strength - 50) / 50.0
    seat_penalty = max(0.0, (team_seat - 1) * 0.006)
    support_recovery = 0.0
    if team_size >= 2 and team_seat == 2:
        support_recovery += max(0.0, (stability - 55) / 500.0)
        support_recovery += max(0.0, (financial_strength - 55) / 500.0)

    if not team_profile:
        prestige_delta = (team_reputation - team_prestige) / 100.0
        strength_delta += prestige_delta * 0.35
        if team_reputation >= team_prestige + 6:
            trajectory = "rising"
        elif team_reputation <= team_prestige - 6:
            trajectory = "falling"

    power_scalar = 1.0 + (strength_delta * 0.025)
    weight_scalar = 1.0 - (strength_delta * 0.020)
    drag_scalar = 1.0 - (strength_delta * 0.018)

    if trajectory == "rising":
        power_scalar += 0.006
        weight_scalar -= 0.004
        drag_scalar -= 0.004
    elif trajectory == "falling":
        power_scalar -= 0.006
        weight_scalar += 0.004
        drag_scalar += 0.004
    elif trajectory == "rebuilding":
        power_scalar -= 0.003
        drag_scalar += 0.003

    if philosophy == "technical excellence":
        power_scalar += 0.004
        drag_scalar -= 0.008
    elif philosophy == "win now":
        power_scalar += 0.006
        weight_scalar -= 0.003
    elif philosophy == "driver continuity":
        weight_scalar -= 0.003
        drag_scalar -= 0.003
    elif philosophy == "underdog grit":
        weight_scalar -= 0.004
    elif philosophy == "rookie pipeline":
        power_scalar -= 0.003
        drag_scalar += 0.003

    pressure_drag = max(0.0, (pressure - 60) / 1000.0)
    power_scalar -= pressure_drag
    drag_scalar += pressure_drag / 2.0

    seat_adjustment = max(0.0, seat_penalty - support_recovery)
    power_scalar -= seat_adjustment
    weight_scalar += seat_adjustment * 0.75
    drag_scalar += seat_adjustment * 0.75

    return {
        "weight_scalar": _clamp_bop_scalar(weight_scalar),
        "power_scalar": _clamp_bop_scalar(power_scalar),
        "drag_scalar": _clamp_bop_scalar(drag_scalar),
    }


def _indent_xml(element: ET.Element, level: int = 0) -> None:
    indent = "\n" + ("    " * level)
    if len(element):
        if not element.text or not element.text.strip():
            element.text = indent + "    "
        for child in element:
            _indent_xml(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = indent
    elif level and (not element.tail or not element.tail.strip()):
        element.tail = indent


def _write_roster_xml(path: Path, drivers: list[dict[str, str]]) -> None:
    root = ET.Element("custom_ai_drivers")
    for driver in drivers:
        driver_node = ET.SubElement(root, "driver", {"livery_name": driver["livery_name"]})
        for tag in [
            "name",
            "country",
            "race_skill",
            "qualifying_skill",
            "aggression",
            "defending",
            "stamina",
            "consistency",
            "start_reactions",
            "wet_skill",
            "tyre_management",
            "fuel_management",
            "blue_flag_conceding",
            "weather_tyre_changes",
            "avoidance_of_mistakes",
            "avoidance_of_forced_mistakes",
            "setup_downforce",
            "setup_downforce_randomness",
            "vehicle_reliability",
            "weight_scalar",
            "power_scalar",
            "drag_scalar",
        ]:
            node = ET.SubElement(driver_node, tag)
            node.text = driver[tag]
    _indent_xml(root)
    tree = ET.ElementTree(root)
    tree.write(path, encoding="utf-8", xml_declaration=True)


def validate_ams2_roster_files(
    championship: dict[str, Any],
    standings: list[dict[str, Any]],
    player_names: list[str],
) -> Ams2RosterValidation:
    ams2_root = Path(game_directory("AMS2"))
    if not str(ams2_root).strip():
        return Ams2RosterValidation(False, "AMS2 folder is not set in Settings.")

    custom_ai_dir = ams2_root / "UserData" / "CustomAIDrivers"
    if not custom_ai_dir.exists():
        return Ams2RosterValidation(False, "AMS2 driver roster is not exported yet. Re-export roster before entering race.")

    expected_by_roster: dict[str, set[str]] = defaultdict(set)
    for driver in standings:
        driver_name = str(driver.get("name", "")).strip()
        if not driver_name:
            continue
        class_name = _driver_class_name(driver)
        rows = _livery_rows_for_class(class_name)
        if not rows:
            return Ams2RosterValidation(
                False,
                f"AMS2 roster could not be checked because class '{class_name}' has no livery mapping.",
            )
        roster_name = str(rows[0].get("Roster_Name", "")).strip()
        if not roster_name:
            return Ams2RosterValidation(
                False,
                f"AMS2 roster could not be checked because class '{class_name}' has no roster file mapping.",
            )
        expected_by_roster[roster_name].add(driver_name)

    if not expected_by_roster:
        return Ams2RosterValidation(True, "AMS2 driver roster is up to date.")

    missing_files: list[str] = []
    mismatched_rosters: list[str] = []
    checked_paths: list[Path] = []

    for roster_name, expected_names in sorted(expected_by_roster.items(), key=lambda item: item[0].casefold()):
        xml_path = custom_ai_dir / roster_name
        checked_paths.append(xml_path)
        if not xml_path.exists():
            missing_files.append(roster_name)
            continue
        exported_names = _read_ams2_roster_driver_names(xml_path)
        if exported_names != expected_names:
            mismatched_rosters.append(roster_name)

    if missing_files or mismatched_rosters:
        return Ams2RosterValidation(
            False,
            "AMS2 driver roster does not seem to match this race. Re-export roster before entering race.",
            roster_paths=tuple(checked_paths),
            missing_files=tuple(missing_files),
            mismatched_rosters=tuple(mismatched_rosters),
        )

    return Ams2RosterValidation(
        True,
        "AMS2 driver roster is up to date.",
        roster_paths=tuple(checked_paths),
    )


def _read_ams2_roster_driver_names(xml_path: Path) -> set[str]:
    try:
        tree = ET.parse(xml_path)
    except (OSError, ET.ParseError):
        return set()

    names: set[str] = set()
    for driver_node in tree.iter():
        if str(driver_node.tag).split("}")[-1].casefold() != "driver":
            continue
        for child in list(driver_node):
            if str(child.tag).split("}")[-1].casefold() != "name":
                continue
            driver_name = str(child.text or "").strip()
            if driver_name:
                names.add(driver_name)
            break
    return names


def export_ams2_roster(
    save_name: str,
    championship: dict[str, Any],
    standings: list[dict[str, Any]],
    player_names: list[str],
    player_car: dict[str, str] | None,
    existing_player_liveries: list[dict[str, str]] | None = None,
) -> tuple[Path, list[dict[str, str]]]:
    ams2_root = Path(game_directory("AMS2"))
    if not str(ams2_root).strip():
        raise ValueError("AMS2 folder is not set in Settings.")

    custom_ai_dir = ams2_root / "UserData" / "CustomAIDrivers"
    custom_ai_dir.mkdir(parents=True, exist_ok=True)

    player_set = {str(name).strip() for name in player_names if str(name).strip()}
    grouped_drivers: dict[str, list[dict[str, Any]]] = defaultdict(list)
    profiles = driver_profile_map(save_name)
    reserved_player_rows: list[dict[str, str]] = []
    roster_to_queue: dict[str, deque[dict[str, str]]] = {}
    roster_to_all_rows: dict[str, list[dict[str, str]]] = {}
    roster_to_player_liveries: dict[str, set[str]] = defaultdict(set)
    existing_livery_map: dict[tuple[str, str, str], str] = {}
    team_sizes: dict[str, int] = defaultdict(int)
    team_profile_cache: dict[str, dict[str, Any] | None] = {}

    for driver in standings:
        team_key = str(driver.get("team_key", "")).strip()
        if team_key:
            team_sizes[team_key] += 1

    for row in existing_player_liveries or []:
        if not isinstance(row, dict):
            continue
        driver_name = str(row.get("driver_name", "")).strip()
        class_name = str(row.get("class_name", "")).strip()
        roster_name = str(row.get("roster_name", "")).strip()
        livery_name = str(row.get("livery_name", "")).strip()
        if driver_name and class_name and roster_name and livery_name:
            existing_livery_map[(driver_name, class_name, roster_name)] = livery_name

    def ensure_roster_pool(class_name: str) -> tuple[str, list[dict[str, str]]]:
        rows = _livery_rows_for_class(class_name)
        if not rows:
            raise ValueError(f"No AMS2 livery rows were found for class '{class_name}'.")
        roster_name = str(rows[0].get("Roster_Name", "")).strip()
        if not roster_name:
            raise ValueError(f"AMS2 livery rows for class '{class_name}' are missing Roster_Name.")
        if roster_name not in roster_to_queue:
            custom_rows = [row for row in rows if str(row.get("_custom_livery", "")).strip().casefold() == "yes"]
            default_rows = [row for row in rows if str(row.get("_custom_livery", "")).strip().casefold() != "yes"]
            random.shuffle(custom_rows)
            random.shuffle(default_rows)
            roster_to_queue[roster_name] = deque(custom_rows + default_rows)
            roster_to_all_rows[roster_name] = rows[:]
        return roster_name, rows

    def reserve_player_livery(driver_name: str, class_name: str, roster_name: str, rows: list[dict[str, str]]) -> dict[str, str]:
        reserved = roster_to_player_liveries.get(roster_name, set())
        existing_livery = existing_livery_map.get((driver_name, class_name, roster_name), "")
        if existing_livery:
            matching_row = next(
                (
                    row
                    for row in rows
                    if str(row.get("livery_name", "")).strip() == existing_livery
                    and str(row.get("livery_name", "")).strip() not in reserved
                ),
                None,
            )
            if matching_row is not None:
                roster_to_player_liveries[roster_name].add(existing_livery)
                return matching_row
        available_rows = [
            row for row in rows if str(row.get("livery_name", "")).strip() not in reserved
        ]
        if not available_rows:
            raise ValueError(f"Not enough unique AMS2 player liveries are available for roster '{roster_name}'.")
        chosen = random.choice(available_rows)
        roster_to_player_liveries[roster_name].add(str(chosen.get("livery_name", "")).strip())
        return chosen

    for driver in standings:
        class_name = _driver_class_name(driver)
        roster_name, rows = ensure_roster_pool(class_name)
        if driver["name"] in player_set:
            player_rows = _livery_rows_for_player_car(player_car, class_name, rows)
            player_choice = reserve_player_livery(str(driver["name"]), class_name, roster_name, player_rows)
            reserved_player_rows.append(
                {
                    "driver_name": str(driver["name"]),
                    "class_name": class_name,
                    "roster_name": roster_name,
                    "livery_name": str(player_choice.get("livery_name", "")).strip(),
                    "car_name": str(player_choice.get("Car_Name", "")).strip(),
                    "car_id": str(player_choice.get("car_id", "")).strip(),
                    "team_key": str(driver.get("team_key", "")).strip(),
                    "team_seat": str(driver.get("team_seat", 1) or 1),
                }
            )
            continue
        grouped_drivers[roster_name].append(driver)

    player_livery_rows: list[dict[str, str]] = []
    roster_to_player_entries: dict[str, list[dict[str, str]]] = defaultdict(list)
    for reserved in reserved_player_rows:
        player_livery_rows.append(dict(reserved))
        driver_name = str(reserved.get("driver_name", "")).strip()
        class_name = str(reserved.get("class_name", "")).strip()
        roster_name = str(reserved.get("roster_name", "")).strip()
        fallback_skill = next(
            (
                int(driver.get("skill", 60) or 60)
                for driver in standings
                if str(driver.get("name", "")).strip() == driver_name
                and _driver_class_name(driver) == class_name
            ),
            60,
        )
        profile = profiles.get(driver_name, {})
        stats = _build_driver_stats(
            profile,
            fallback_skill,
            team_bop=_team_bop_for_driver(
                save_name,
                {
                    "team_key": str(reserved.get("team_key", "")).strip(),
                    "team_seat": str(reserved.get("team_seat", 1) or 1),
                },
                team_sizes,
                team_profile_cache,
            ),
        )
        roster_to_player_entries[roster_name].append(
            {
                "livery_name": str(reserved.get("livery_name", "")).strip(),
                "country": str(profile.get("country_code", "USA") or "USA"),
                "name": driver_name or "Player",
                **stats,
            }
        )

    export_skill_floor = ams2_export_skill_floor_for_prestige(championship.get("Prestige", 1))
    export_skill_map = _scale_roster_ams2_skills(
        [
            driver
            for drivers in grouped_drivers.values()
            for driver in drivers
        ],
        profiles,
        low=export_skill_floor,
    )

    for roster_name in sorted(roster_to_all_rows.keys(), key=str.casefold):
        drivers = grouped_drivers.get(roster_name, [])
        roster_rows = roster_to_all_rows.get(roster_name, [])
        if not roster_rows:
            continue
        available_queue = roster_to_queue[roster_name]
        player_liveries = roster_to_player_liveries.get(roster_name, set())
        used_liveries = set(player_liveries)
        roster_entries: list[dict[str, str]] = list(roster_to_player_entries.get(roster_name, []))

        for driver in drivers:
            chosen_row: dict[str, str] | None = None
            checked = 0
            while available_queue and checked < len(available_queue):
                candidate = available_queue.popleft()
                checked += 1
                livery_name = str(candidate.get("livery_name", "")).strip()
                if livery_name in used_liveries:
                    available_queue.append(candidate)
                    continue
                chosen_row = candidate
                break
            if chosen_row is None:
                fallback_rows = [
                    row
                    for row in roster_rows
                    if str(row.get("livery_name", "")).strip() not in used_liveries
                ]
                if fallback_rows:
                    chosen_row = random.choice(fallback_rows)
                else:
                    fallback_rows = [
                        row
                        for row in roster_rows
                        if str(row.get("livery_name", "")).strip() not in player_liveries
                    ]
                    if not fallback_rows:
                        raise ValueError(
                            f"No AMS2 liveries are available for roster '{roster_name}' after reserving player skins."
                        )
                    chosen_row = random.choice(fallback_rows)

            used_liveries.add(str(chosen_row.get("livery_name", "")).strip())
            profile = profiles.get(str(driver.get("name", "")), {})
            fallback_skill = int(driver.get("skill", 60) or 60)
            stats = _build_driver_stats(
                profile,
                fallback_skill,
                export_skill_map.get(str(driver.get("name", "")).strip()),
                normalized_skill_floor=export_skill_floor,
                team_bop=_team_bop_for_driver(
                    save_name,
                    driver,
                    team_sizes,
                    team_profile_cache,
                ),
            )
            roster_entries.append(
                {
                    "livery_name": str(chosen_row.get("livery_name", "")).strip(),
                    "country": str(profile.get("country_code", "USA") or "USA"),
                    "name": str(driver.get("name", "AI Driver")).strip(),
                    **stats,
                }
            )
        xml_path = custom_ai_dir / roster_name
        _write_roster_xml(xml_path, roster_entries)
    return custom_ai_dir, player_livery_rows
