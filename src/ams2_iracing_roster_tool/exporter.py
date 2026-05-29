from __future__ import annotations

import json
import random
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from circuit_stackers.settings_manager import list_all_cars


DEFAULT_APPDATA_ROOT = Path(r"C:\Users\hfaur\AppData\Roaming\race-pace-career-app")
DEFAULT_JSON_EXPORT_DIR_NAME = "roster_exports"
DB_EXPORT_RE = re.compile(
    r"^rxdb-dexie-(?P<slot>career-sim-(?:main-db|slot-\d+))--\d+--(?P<collection>[A-Za-z0-9_-]+)\.json$",
    re.IGNORECASE,
)
CHAMPIONSHIP_COLLECTIONS = ("championships", "championshipSeasons", "championshipEntry")
RELATION_COLLECTIONS = ("championshipSeasons", "championshipEntry", "teamSeats", "driverContracts")
DRIVER_ID_KEY_HINTS = (
    "driver_id",
    "driverid",
    "assigned_driver_id",
    "occupant_driver_id",
    "reserve_driver_id",
    "primary_driver_id",
    "secondary_driver_id",
)
IGNORE_RELATION_KEYS = {
    "_rev",
    "_meta",
    "_deleted",
    "_attachments",
    "_deletedTime",
    "_modified",
    "_created",
    "_updated",
}
COLOR_SETS = [
    "FFFFFF,000000,FFFFFF",
    "E10600,000000,FFFFFF",
    "005AFF,FFFFFF,000000",
    "FFD700,000000,1C1C1C",
    "00AEEF,FFFFFF,003366",
    "FF6600,000000,FFFFFF",
    "2E8B57,FFFFFF,000000",
    "800020,FFFFFF,000000",
]


@dataclass(frozen=True)
class ChampionshipOption:
    slot_key: str
    championship_id: str
    label: str
    season_ids: tuple[str, ...]
    source_doc: dict[str, Any]


class ExportError(ValueError):
    pass


def default_source_folder() -> Path:
    export_dir = DEFAULT_APPDATA_ROOT / DEFAULT_JSON_EXPORT_DIR_NAME
    if export_dir.exists():
        return export_dir
    return DEFAULT_APPDATA_ROOT


def slot_label(slot_key: str) -> str:
    if slot_key == "career-sim-main-db":
        return "Main DB"
    if slot_key.startswith("career-sim-slot-"):
        return f"Save Slot {slot_key.removeprefix('career-sim-slot-')}"
    return slot_key


def load_export_bundle(folder: str | Path) -> dict[str, dict[str, list[dict[str, Any]]]]:
    base = Path(folder)
    if not base.exists():
        raise ExportError("Selected export folder does not exist.")

    if base.is_dir():
        nested_export_dir = base / DEFAULT_JSON_EXPORT_DIR_NAME
        if nested_export_dir.exists():
            base = nested_export_dir

    slots: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for path in sorted(base.glob("*.json")):
        match = DB_EXPORT_RE.match(path.name)
        if not match:
            continue
        raw_payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw_payload, list):
            continue
        slot_key = match.group("slot")
        collection = match.group("collection")
        slots.setdefault(slot_key, {})[collection] = [doc for doc in raw_payload if isinstance(doc, dict)]

    if not slots:
        if _looks_like_raw_appdata_dir(base):
            raise ExportError(
                "This is the raw race-pace-career-app folder. Put the exported RxDB JSON files into a "
                f"'{DEFAULT_JSON_EXPORT_DIR_NAME}' folder here, then reopen the tool."
            )
        raise ExportError(
            "No RxDB export JSON files were found. Export the collections from DevTools first and point this app at that folder."
        )
    return slots


def list_slot_keys(bundle: dict[str, dict[str, list[dict[str, Any]]]]) -> list[str]:
    return sorted(bundle, key=lambda value: (0 if value == "career-sim-main-db" else 1, value))


def list_championship_options(bundle: dict[str, dict[str, list[dict[str, Any]]]], slot_key: str) -> list[ChampionshipOption]:
    collections = bundle.get(slot_key, {})
    championships = collections.get("championships", [])
    seasons = collections.get("championshipSeasons", [])
    entries = collections.get("championshipEntry", [])

    season_ids_by_championship: dict[str, set[str]] = {}
    for season in seasons:
        season_id = _doc_id(season)
        for championship_id in _championship_reference_values(season):
            if season_id:
                season_ids_by_championship.setdefault(championship_id, set()).add(season_id)

    options: dict[str, ChampionshipOption] = {}
    for doc in championships:
        championship_id = _best_championship_id(doc)
        if not championship_id:
            continue
        label = _best_championship_label(doc)
        options[championship_id] = ChampionshipOption(
            slot_key=slot_key,
            championship_id=championship_id,
            label=label,
            season_ids=tuple(sorted(season_ids_by_championship.get(championship_id, set()))),
            source_doc=doc,
        )

    if not options:
        for season in seasons:
            championship_id = next(iter(_championship_reference_values(season)), "") or _doc_id(season)
            if not championship_id or championship_id in options:
                continue
            label = _best_championship_label(season)
            season_id = _doc_id(season)
            options[championship_id] = ChampionshipOption(
                slot_key=slot_key,
                championship_id=championship_id,
                label=label,
                season_ids=(season_id,) if season_id else (),
                source_doc=season,
            )

    if not options:
        entry_groups: dict[str, dict[str, Any]] = {}
        for entry in entries:
            championship_id = next(iter(_championship_reference_values(entry)), "")
            if not championship_id:
                continue
            entry_groups.setdefault(championship_id, entry)
        for championship_id, entry in entry_groups.items():
            options[championship_id] = ChampionshipOption(
                slot_key=slot_key,
                championship_id=championship_id,
                label=_best_championship_label(entry),
                season_ids=(),
                source_doc=entry,
            )

    return sorted(options.values(), key=lambda option: option.label.casefold())


def resolve_roster_drivers(
    bundle: dict[str, dict[str, list[dict[str, Any]]]],
    option: ChampionshipOption,
) -> list[dict[str, Any]]:
    collections = bundle.get(option.slot_key, {})
    drivers = collections.get("drivers", [])
    if not drivers:
        raise ExportError(f"No driver export was found for {slot_label(option.slot_key)}.")

    refs = {option.championship_id, *option.season_ids}
    matched_ids: set[tuple[str, str]] = set()
    matched_docs: list[dict[str, Any]] = []
    driver_ids: set[str] = set()

    changed = True
    while changed:
        changed = False
        for collection_name in RELATION_COLLECTIONS:
            for doc in collections.get(collection_name, []):
                doc_id = _doc_id(doc)
                doc_key = (collection_name, doc_id or str(id(doc)))
                if doc_key in matched_ids:
                    continue
                if not _doc_references_any(doc, refs):
                    continue
                matched_ids.add(doc_key)
                matched_docs.append(doc)
                doc_refs = _relation_values(doc)
                new_refs = doc_refs - refs
                new_driver_ids = _driver_reference_values(doc) - driver_ids
                if new_refs or new_driver_ids:
                    refs |= doc_refs
                    driver_ids |= new_driver_ids
                    changed = True

    if not driver_ids:
        driver_ids = _driver_ids_from_championship_entries(collections.get("championshipEntry", []), refs)

    if not driver_ids:
        raise ExportError(
            f"Could not find assigned drivers for '{option.label}'. Export the championship, seasons, entry, teamSeats, and driverContracts collections for this slot."
        )

    drivers_by_id = {_doc_id(driver): driver for driver in drivers if _doc_id(driver)}
    selected = [drivers_by_id[driver_id] for driver_id in sorted(driver_ids) if driver_id in drivers_by_id]
    if not selected:
        raise ExportError(f"Resolved driver ids for '{option.label}', but could not match them to driver documents.")
    return selected


def infer_iracing_car(championship: ChampionshipOption) -> dict[str, str] | None:
    all_iracing_cars = [
        row for row in list_all_cars() if str(row.get("Game", "")).strip().casefold() == "iracing"
    ]
    hints = {
        str(value).strip()
        for value in _possible_car_hints(championship.source_doc)
        if str(value).strip()
    }
    if not hints:
        hints = {championship.label}

    for hint in hints:
        hint_cf = hint.casefold()
        for car in all_iracing_cars:
            car_name = str(car.get("Car", "")).strip()
            class_name = str(car.get("Car class", "")).strip()
            if hint_cf in {car_name.casefold(), class_name.casefold()}:
                return car
            if hint_cf and (hint_cf in car_name.casefold() or hint_cf in class_name.casefold()):
                return car
    return None


def list_iracing_cars() -> list[dict[str, str]]:
    return [
        row for row in list_all_cars() if str(row.get("Game", "")).strip().casefold() == "iracing"
    ]


def build_iracing_roster_payload(
    drivers: list[dict[str, Any]],
    championship: ChampionshipOption,
    iracing_car: dict[str, str] | None,
) -> dict[str, Any]:
    roster_rows: list[dict[str, Any]] = []
    for index, driver in enumerate(sorted(drivers, key=lambda item: _best_driver_name(item).casefold())):
        colors = random.choice(COLOR_SETS)
        skill = _pct_value(_value_for_keys(driver, "race_skill", "raceSkill", "skill"))
        aggression = _pct_value(_value_for_keys(driver, "aggression"))
        consistency = _pct_value(_value_for_keys(driver, "consistency"))
        stamina = _pct_value(_value_for_keys(driver, "stamina"))
        fuel_management = _pct_value(_value_for_keys(driver, "fuel_management", "fuelManagement"))
        tyre_management = _pct_value(_value_for_keys(driver, "tyre_management", "tire_management", "tyreManagement", "tireManagement"))
        forced_mistake_avoidance = _pct_value(
            _value_for_keys(
                driver,
                "avoidance_of_forced_mistakes",
                "avoidanceOfForcedMistakes",
                "forced_mistake_avoidance",
                "forcedMistakeAvoidance",
            )
        )
        optimism = _avg_pct(consistency, stamina)
        pit_crew_skill = _avg_pct(fuel_management, tyre_management)

        roster_rows.append(
            {
                "driverName": _best_driver_name(driver),
                "carDesign": f"{random.randint(0, 24)},{colors}",
                "carNumber": str(_value_for_keys(driver, "number", "car_number", "carNumber") or random.randint(0, 99)),
                "suitDesign": f"{random.randint(0, 24)},{colors}",
                "helmetDesign": f"{random.randint(0, 24)},{colors}",
                "carPath": str(iracing_car.get("FILEPATH", "")) if iracing_car else "",
                "carId": int(_int_value(iracing_car.get("Iracing_ID")) if iracing_car else 0),
                "sponsor1": 0,
                "sponsor2": 0,
                "numberDesign": f"{random.randint(0, 24)},{random.randint(0, 24)},{colors}",
                "driverSkill": skill,
                "driverAggression": aggression,
                "driverOptimism": optimism,
                "driverSmoothness": consistency,
                "pitCrewSkill": pit_crew_skill,
                "strategyRiskiness": forced_mistake_avoidance,
                "driverAge": _driver_age(driver),
                "id": str(uuid.uuid4()),
                "rowIndex": index,
                "carClassId": int(_int_value(iracing_car.get("Car_Class_ID")) if iracing_car else 0),
            }
        )
    return {"drivers": roster_rows}


def export_roster_json(
    output_dir: str | Path,
    championship: ChampionshipOption,
    payload: dict[str, Any],
) -> Path:
    base = Path(output_dir)
    base.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", championship.label).strip("-") or "championship"
    roster_dir = base / f"AMS2-{slot_label(championship.slot_key).replace(' ', '-')}-{safe_name}"
    roster_dir.mkdir(parents=True, exist_ok=True)
    roster_path = roster_dir / "roster.json"
    roster_path.write_text(json.dumps(payload, indent=4), encoding="utf-8")
    return roster_path


def _best_driver_name(doc: dict[str, Any]) -> str:
    first_name = _first_non_empty_string(
        _nested_value_for_keys(
            doc,
            "name",
            "first_name",
            "firstName",
            "given_name",
            "givenName",
            "forename",
            "name.first",
            "name.first_name",
            "name.firstName",
            "name.given",
            "name.given_name",
            "profile.first_name",
            "profile.firstName",
        )
    )
    last_name = _first_non_empty_string(
        _nested_value_for_keys(
            doc,
            "surname",
            "last_name",
            "lastName",
            "family_name",
            "familyName",
            "name.last",
            "name.last_name",
            "name.lastName",
            "name.family",
            "name.family_name",
            "profile.last_name",
            "profile.lastName",
        )
    )
    full_name = f"{first_name} {last_name}".strip()
    if full_name:
        return full_name
    combined_name = _first_non_empty_string(
        _nested_value_for_keys(
            doc,
            "full_name",
            "fullName",
            "display_name",
            "displayName",
            "driver_name",
            "driverName",
            "name.full",
            "name.full_name",
            "name.display",
            "profile.full_name",
            "profile.display_name",
        )
    )
    if combined_name:
        return combined_name
    nested_name = _value_for_keys(doc, "name")
    if isinstance(nested_name, dict):
        nested_first = _first_non_empty_string(
            _nested_value_for_keys(
                nested_name,
                "first",
                "first_name",
                "firstName",
                "given",
                "given_name",
                "forename",
            )
        )
        nested_last = _first_non_empty_string(
            _nested_value_for_keys(
                nested_name,
                "last",
                "last_name",
                "lastName",
                "surname",
                "family",
                "family_name",
            )
        )
        nested_combined = f"{nested_first} {nested_last}".strip()
        if nested_combined:
            return nested_combined
        nested_full = _first_non_empty_string(
            _nested_value_for_keys(
                nested_name,
                "full",
                "full_name",
                "display",
                "display_name",
                "value",
            )
        )
        if nested_full:
            return nested_full
    short_name = _first_non_empty_string(_nested_value_for_keys(doc, "name", "short_name", "shortName", "nickname"))
    if short_name:
        return short_name
    return str(_doc_id(doc) or "Unknown Driver")


def _best_championship_id(doc: dict[str, Any]) -> str:
    return str(
        _value_for_keys(doc, "championship_id", "championshipId", "id", "series_id", "seriesId")
        or ""
    ).strip()


def _best_championship_label(doc: dict[str, Any]) -> str:
    for key in (
        "championship_name",
        "championshipName",
        "name",
        "display_name",
        "displayName",
        "series_name",
        "seriesName",
        "title",
    ):
        value = _value_for_keys(doc, key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return str(_best_championship_id(doc) or "Unknown Championship")


def _doc_id(doc: dict[str, Any]) -> str:
    return str(_value_for_keys(doc, "id", "_id", "doc_id", "docId") or "").strip()


def _value_for_keys(doc: Any, *keys: str) -> Any:
    if not isinstance(doc, dict):
        return None
    normalized = {str(key).replace("_", "").casefold(): value for key, value in doc.items()}
    for key in keys:
        match = normalized.get(str(key).replace("_", "").casefold())
        if match not in (None, ""):
            return match
    return None


def _nested_value_for_keys(doc: Any, *keys: str) -> Any:
    for key in keys:
        value = _nested_value(doc, key)
        if value not in (None, ""):
            return value
    return None


def _nested_value(doc: Any, path: str) -> Any:
    current = doc
    for part in str(path).split("."):
        if not isinstance(current, dict):
            return None
        current = _value_for_keys(current, part)
        if current in (None, ""):
            return None
    return current


def _first_non_empty_string(value: Any) -> str:
    if isinstance(value, list):
        for item in value:
            match = _first_non_empty_string(item)
            if match:
                return match
        return ""
    if isinstance(value, dict):
        return ""
    return str(value or "").strip()


def _championship_reference_values(doc: dict[str, Any]) -> set[str]:
    refs = set()
    for key, value in doc.items():
        normalized = str(key).replace("_", "").casefold()
        if "championship" not in normalized or "entry" in normalized:
            continue
        refs |= _scalar_strings(value)
    return refs


def _possible_car_hints(doc: dict[str, Any]) -> set[str]:
    hints: set[str] = set()
    for key, value in doc.items():
        normalized = str(key).replace("_", "").casefold()
        if any(token in normalized for token in ("car", "vehicle", "class")):
            hints |= _scalar_strings(value)
    return hints


def _relation_values(doc: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for key, value in doc.items():
        normalized = str(key).replace("_", "").casefold()
        if normalized in {item.replace("_", "").casefold() for item in IGNORE_RELATION_KEYS}:
            continue
        if normalized.endswith("id") or normalized.endswith("ids") or "seat" in normalized or "team" in normalized or "championship" in normalized:
            values |= _scalar_strings(value)
    doc_id = _doc_id(doc)
    if doc_id:
        values.add(doc_id)
    return {value for value in values if value}


def _driver_reference_values(doc: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for key, value in doc.items():
        normalized = str(key).replace("_", "").casefold()
        if "driver" not in normalized:
            continue
        if any(hint in normalized for hint in DRIVER_ID_KEY_HINTS) or normalized.endswith("driver") or normalized.endswith("drivers"):
            values |= _scalar_strings(value)
    return {value for value in values if value}


def _doc_references_any(doc: dict[str, Any], refs: set[str]) -> bool:
    if not refs:
        return False
    relation_values = _relation_values(doc) | _driver_reference_values(doc)
    return any(value in refs for value in relation_values)


def _driver_ids_from_championship_entries(entries: list[dict[str, Any]], refs: set[str]) -> set[str]:
    driver_ids: set[str] = set()
    for entry in entries:
        if _doc_references_any(entry, refs):
            driver_ids |= _driver_reference_values(entry)
    return driver_ids


def _scalar_strings(value: Any) -> set[str]:
    values: set[str] = set()
    if isinstance(value, (str, int, float)) and str(value).strip():
        values.add(str(value).strip())
        return values
    if isinstance(value, list):
        for item in value:
            values |= _scalar_strings(item)
        return values
    if isinstance(value, dict):
        for nested in value.values():
            values |= _scalar_strings(nested)
    return values


def _pct_value(value: Any, fallback: int = 50) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if number <= 1.0:
        number *= 100.0
    return max(0, min(100, int(round(number))))


def _avg_pct(left: int, right: int) -> int:
    return max(0, min(100, int(round((left + right) / 2))))


def _int_value(value: Any, fallback: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError, AttributeError):
        return fallback


def _driver_age(doc: dict[str, Any]) -> int:
    dob_age = _age_from_dob(
        _value_for_keys(
            doc,
            "dob",
            "date_of_birth",
            "dateOfBirth",
            "birth_date",
            "birthDate",
        )
    )
    if dob_age is not None:
        return dob_age
    age = _int_value(_value_for_keys(doc, "age", "driver_age", "driverAge"), fallback=28)
    return max(16, min(80, age))


def _age_from_dob(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        birth_date = datetime.fromisoformat(text).date()
    except (TypeError, ValueError):
        return None
    today = date.today()
    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    return max(16, min(80, age))


def _looks_like_raw_appdata_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    expected_children = {
        "IndexedDB",
        "Local Storage",
        "Session Storage",
        "blob_storage",
    }
    try:
        child_names = {child.name for child in path.iterdir()}
    except OSError:
        return False
    return bool(expected_children & child_names)
