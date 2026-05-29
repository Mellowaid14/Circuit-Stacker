from __future__ import annotations

import csv
from pathlib import Path
from uuid import uuid4

from .paths import resource_path, user_data_dir


CHAMPIONSHIP_FIELDNAMES = [
    "id",
    "Tier",
    "Championship",
    "Sub_Champ",
    "Championship_ID",
    "Car_Class",
    "Car_ID",
    "Style",
    "Num of Races",
    "Race_Time",
    "Game",
    "Max_Opp",
    "Min_Opp",
    "Start_Type",
    "Prestige",
]

CUSTOM_CHAMPIONSHIPS_CSV = user_data_dir() / "custom_championships.csv"


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as file_obj:
        return [dict(row) for row in csv.DictReader(file_obj)]


def built_in_championship_rows(game: str | None = None) -> list[dict[str, str]]:
    return _filter_rows_for_game(_read_csv(resource_path("data", "Championships.csv")), game)


def custom_championship_rows(game: str | None = None) -> list[dict[str, str]]:
    return _filter_rows_for_game(_read_csv(CUSTOM_CHAMPIONSHIPS_CSV), game)


def championship_rows(game: str | None = None) -> list[dict[str, str]]:
    return built_in_championship_rows(game) + custom_championship_rows(game)


def infer_tier_for_car(car: dict[str, str], game: str | None = None) -> str:
    car_id = str(car.get("id", "")).strip()
    class_id = str(car.get("Car_Class_ID", "")).strip()
    matching_rows = []
    for row in built_in_championship_rows(game):
        row_car_id = str(row.get("Car_ID", "")).strip()
        row_class_id = str(row.get("Car_Class", "")).strip()
        if row_car_id and car_id and row_car_id == car_id:
            matching_rows.append(row)
        elif row_class_id and class_id and row_class_id == class_id:
            matching_rows.append(row)
    if not matching_rows:
        return "1"
    best_row = max(
        matching_rows,
        key=lambda row: (
            _safe_int(row.get("Prestige"), 0),
            _safe_int(row.get("Tier"), 1),
        ),
    )
    return str(max(1, min(5, _safe_int(best_row.get("Tier"), 1))))


def _filter_rows_for_game(rows: list[dict[str, str]], game: str | None) -> list[dict[str, str]]:
    if not game:
        return rows
    normalized_game = str(game).strip().casefold()
    return [
        dict(row)
        for row in rows
        if str(row.get("Game", "")).strip().casefold() in {"", normalized_game}
    ]


def append_custom_championship(rows: list[dict[str, str]]) -> Path:
    CUSTOM_CHAMPIONSHIPS_CSV.parent.mkdir(parents=True, exist_ok=True)
    existing_rows = _read_csv(CUSTOM_CHAMPIONSHIPS_CSV)
    _write_custom_rows(existing_rows + [_normalized_row(row) for row in rows])
    return CUSTOM_CHAMPIONSHIPS_CSV


def update_custom_championship(championship_id: str, updated_rows: list[dict[str, str]]) -> Path:
    target_id = str(championship_id).strip()
    existing_rows = [
        row
        for row in _read_csv(CUSTOM_CHAMPIONSHIPS_CSV)
        if str(row.get("Championship_ID", "") or row.get("id", "")).strip() != target_id
    ]
    _write_custom_rows(existing_rows + [_normalized_row(row) for row in updated_rows])
    return CUSTOM_CHAMPIONSHIPS_CSV


def delete_custom_championship(championship_id: str) -> Path:
    target_id = str(championship_id).strip()
    existing_rows = [
        row
        for row in _read_csv(CUSTOM_CHAMPIONSHIPS_CSV)
        if str(row.get("Championship_ID", "") or row.get("id", "")).strip() != target_id
    ]
    _write_custom_rows(existing_rows)
    return CUSTOM_CHAMPIONSHIPS_CSV


def grouped_custom_championships() -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in custom_championship_rows():
        group_id = str(row.get("Championship_ID", "") or row.get("id", "")).strip()
        if not group_id:
            continue
        grouped.setdefault(group_id, []).append(dict(row))

    summaries: list[dict[str, object]] = []
    for group_id, rows in grouped.items():
        rows = sorted(rows, key=lambda row: (str(row.get("Tier", "")), str(row.get("Sub_Champ", "")), str(row.get("id", ""))))
        first = rows[0]
        summaries.append(
            {
                "championship_id": group_id,
                "name": str(first.get("Championship", "")).strip() or group_id,
                "game": str(first.get("Game", "")).strip(),
                "style": str(first.get("Style", "")).strip(),
                "tier": str(first.get("Tier", "")).strip(),
                "prestige": str(first.get("Prestige", "")).strip(),
                "rows": rows,
            }
        )
    return sorted(summaries, key=lambda item: (str(item.get("game", "")), str(item.get("name", "")).casefold()))


def _write_custom_rows(rows: list[dict[str, str]]) -> None:
    CUSTOM_CHAMPIONSHIPS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with CUSTOM_CHAMPIONSHIPS_CSV.open("w", newline="", encoding="utf-8") as file_obj:
        writer = csv.DictWriter(file_obj, fieldnames=CHAMPIONSHIP_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(_normalized_row(row))


def new_custom_championship_id(name: str) -> str:
    base = "".join(char.lower() if char.isalnum() else "_" for char in str(name).strip()).strip("_")
    while "__" in base:
        base = base.replace("__", "_")
    return f"custom_{base or 'championship'}_{uuid4().hex[:8]}"


def _normalized_row(row: dict[str, str]) -> dict[str, str]:
    return {field: str(row.get(field, "")).strip() for field in CHAMPIONSHIP_FIELDNAMES}


def _safe_int(value: object, fallback: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return fallback
