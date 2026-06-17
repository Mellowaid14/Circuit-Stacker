from __future__ import annotations

import math
import re
import random
import sqlite3
import uuid
import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from . import save_manager
from .custom_championships import championship_rows as load_championship_rows
from .paths import resource_path


BASELINE_MMR = 1000
RACE_K_FACTOR = 18.5
RACE_RATING_CHANGE_CAP = 35
NON_PRIMARY_STYLE_PENALTY = 90
SCHEMA_VERSION = "1"
STYLES = ("Sports Car", "Oval", "Open Wheel", "Rallycross")
_INITIALIZED_POOLS: set[str] = set()
_TEAMS_CACHE: list[dict[str, str]] | None = None
POINTS_MAP = {1: 25, 2: 18, 3: 15, 4: 12, 5: 10, 6: 8, 7: 6, 8: 4, 9: 2, 10: 1}
WORLD_SIM_MMR_WEIGHT = 0.72
WORLD_SIM_SEASON_FORM_STDDEV = 130
WORLD_SIM_RACE_STDDEV = 240
LOWEST_PRESTIGE_FILL_BATCH_SIZE = 6
STORYLINE_CROSSOVER_MIN_FIELD = 10
STORYLINE_CROSSOVER_BONUS = 120
COUNTRY_CODES = (
    "ARG",
    "AUS",
    "AUT",
    "BEL",
    "BRA",
    "CAN",
    "CHE",
    "CHL",
    "DEU",
    "DNK",
    "ESP",
    "FIN",
    "FRA",
    "GBR",
    "IRL",
    "ITA",
    "JPN",
    "MEX",
    "NLD",
    "NOR",
    "NZL",
    "PRT",
    "SWE",
    "USA",
)
TEAMS_CSV = resource_path("data", "Teams.csv")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _clamp_rating_stat(value: int, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, int(value)))


def _biased_rating_stat(base: int, spread: int = 18, low: int = 0, high: int = 100) -> int:
    return _clamp_rating_stat(int(random.gauss(base, max(4, spread / 2))), low, high)


def _random_rating_stat(low: int = 0, high: int = 100) -> int:
    return random.randint(low, high)


def _clamp_float_stat(value: float, low: float = 0.2, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _biased_float_stat(base: float, spread: float, low: float = 0.2, high: float = 1.0) -> float:
    return round(_clamp_float_stat(random.gauss(base, spread), low, high), 2)


def _random_ams2_race_skill() -> float:
    roll = random.random()
    if roll < 0.70:
        return round(random.uniform(0.45, 0.75), 2)
    if roll < 0.95:
        return round(random.uniform(0.75, 0.90), 2)
    return round(random.uniform(0.90, 1.0), 2)


def _random_ams2_general_skill() -> int:
    return random.randint(0, 100)


def _random_ams2_stat(low: float = 0.01, high: float = 1.0) -> float:
    return round(random.uniform(low, high), 2)


def _random_ams2_qualifying_skill(race_skill: float) -> float:
    return round(_clamp_float_stat(race_skill + random.uniform(-0.2, 0.2), 0.01, 1.0), 2)


def _age_skill_delta(age: int) -> int:
    if age < 35:
        if random.random() < 0.18:
            return 2 if random.random() < 0.15 else 1
        return 0
    if age > 35:
        if random.random() < 0.18:
            return -2 if random.random() < 0.15 else -1
        return 0
    return 0


def _sponsor_value() -> int:
    roll = random.randint(0, 100)
    if roll < 45:
        return 0
    return random.randint(1, 100)


def _generate_driver_profile(
    base_rating: int,
    age_range: tuple[int, int] = (18, 56),
) -> dict[str, Any]:
    age_low, age_high = age_range
    ams2_race_skill = _random_ams2_race_skill()
    return {
        "country_code": random.choice(COUNTRY_CODES),
        "iracing_relative_skill": _random_rating_stat(),
        "iracing_aggression": _random_rating_stat(60, 100),
        "iracing_optimism": _random_rating_stat(),
        "iracing_smoothness": _random_rating_stat(),
        "iracing_pit_crew_skill": _random_rating_stat(),
        "iracing_strategy_riskiness": _random_rating_stat(),
        "iracing_sponsor1": _sponsor_value(),
        "iracing_sponsor2": _sponsor_value(),
        "driver_age": random.randint(age_low, age_high),
        "ams2_aggression": _random_ams2_stat(0.75, 1.0),
        "ams2_avoidance_of_forced_mistakes": _random_ams2_stat(),
        "ams2_avoidance_of_mistakes": _random_ams2_stat(),
        "ams2_blue_flag_conceding": _random_ams2_stat(0.7, 1.0),
        "ams2_consistency": _random_ams2_stat(),
        "ams2_defending": _random_ams2_stat(),
        "ams2_fuel_management": _random_ams2_stat(),
        "ams2_general_skill": _random_ams2_general_skill(),
        "ams2_qualifying_skill": _random_ams2_qualifying_skill(ams2_race_skill),
        "ams2_race_skill": ams2_race_skill,
        "ams2_stamina": _random_ams2_stat(),
        "ams2_start_reactions": _random_ams2_stat(),
        "ams2_tyre_management": _random_ams2_stat(),
        "ams2_vehicle_reliability": _random_ams2_stat(0.5, 1.0),
        "ams2_weather_tyre_changes": _random_ams2_stat(),
        "ams2_wet_skill": _random_ams2_stat(),
    }


def _apply_profile_update(connection: sqlite3.Connection, driver_id: str, profile: dict[str, Any], now: str) -> None:
    connection.execute(
        """
        UPDATE drivers
        SET country_code = ?,
            iracing_relative_skill = ?,
            iracing_aggression = ?,
            iracing_optimism = ?,
            iracing_smoothness = ?,
            iracing_pit_crew_skill = ?,
            iracing_strategy_riskiness = ?,
            iracing_sponsor1 = ?,
            iracing_sponsor2 = ?,
            driver_age = ?,
            ams2_aggression = ?,
            ams2_avoidance_of_forced_mistakes = ?,
            ams2_avoidance_of_mistakes = ?,
            ams2_blue_flag_conceding = ?,
            ams2_consistency = ?,
            ams2_defending = ?,
            ams2_fuel_management = ?,
            ams2_general_skill = ?,
            ams2_qualifying_skill = ?,
            ams2_race_skill = ?,
            ams2_stamina = ?,
            ams2_start_reactions = ?,
            ams2_tyre_management = ?,
            ams2_vehicle_reliability = ?,
            ams2_weather_tyre_changes = ?,
            ams2_wet_skill = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            profile["country_code"],
            profile["iracing_relative_skill"],
            profile["iracing_aggression"],
            profile["iracing_optimism"],
            profile["iracing_smoothness"],
            profile["iracing_pit_crew_skill"],
            profile["iracing_strategy_riskiness"],
            profile["iracing_sponsor1"],
            profile["iracing_sponsor2"],
            profile["driver_age"],
            profile["ams2_aggression"],
            profile["ams2_avoidance_of_forced_mistakes"],
            profile["ams2_avoidance_of_mistakes"],
            profile["ams2_blue_flag_conceding"],
            profile["ams2_consistency"],
            profile["ams2_defending"],
            profile["ams2_fuel_management"],
            profile["ams2_general_skill"],
            profile["ams2_qualifying_skill"],
            profile["ams2_race_skill"],
            profile["ams2_stamina"],
            profile["ams2_start_reactions"],
            profile["ams2_tyre_management"],
            profile["ams2_vehicle_reliability"],
            profile["ams2_weather_tyre_changes"],
            profile["ams2_wet_skill"],
            now,
            driver_id,
        ),
    )


def world_db_path(save_name: str) -> Path:
    save_manager.SAVES_DIR.mkdir(parents=True, exist_ok=True)
    return save_manager.world_db_path(save_name)


def _connect(save_name: str) -> sqlite3.Connection:
    connection = sqlite3.connect(world_db_path(save_name))
    connection.row_factory = sqlite3.Row
    return connection


def initialize_driver_pool(save_name: str, world_year: int | None = None) -> Path:
    path = world_db_path(save_name)
    cache_key = str(path)
    if cache_key in _INITIALIZED_POOLS and path.exists() and world_year is None:
        return path
    with _connect(save_name) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS world_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS drivers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                is_human INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                primary_style TEXT NOT NULL,
                mmr INTEGER NOT NULL DEFAULT 1000,
                sports_car_rating INTEGER NOT NULL DEFAULT 1000,
                oval_rating INTEGER NOT NULL DEFAULT 1000,
                open_wheel_rating INTEGER NOT NULL DEFAULT 1000,
                seasons_completed INTEGER NOT NULL DEFAULT 0,
                retirement_after_seasons INTEGER,
                career_starts INTEGER NOT NULL DEFAULT 0,
                wins INTEGER NOT NULL DEFAULT 0,
                podiums INTEGER NOT NULL DEFAULT 0,
                championships INTEGER NOT NULL DEFAULT 0,
                current_tier INTEGER,
                current_style TEXT,
                current_championship TEXT,
                last_tier INTEGER,
                last_style TEXT,
                debut_year INTEGER,
                retired_year INTEGER,
                last_series_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS driver_championship_wins (
                id TEXT PRIMARY KEY,
                driver_id TEXT NOT NULL,
                championship_id TEXT NOT NULL,
                championship_name TEXT NOT NULL,
                season_year INTEGER NOT NULL,
                style TEXT NOT NULL,
                tier INTEGER NOT NULL,
                class_name TEXT NOT NULL DEFAULT 'Overall',
                created_at TEXT NOT NULL,
                FOREIGN KEY(driver_id) REFERENCES drivers(id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS driver_race_wins (
                id TEXT PRIMARY KEY,
                driver_id TEXT NOT NULL,
                championship_id TEXT NOT NULL,
                championship_name TEXT NOT NULL,
                race_num INTEGER NOT NULL,
                track TEXT NOT NULL,
                layout TEXT NOT NULL,
                season_year INTEGER NOT NULL,
                style TEXT NOT NULL,
                tier INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(driver_id) REFERENCES drivers(id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS driver_season_results (
                id TEXT PRIMARY KEY,
                driver_id TEXT NOT NULL,
                championship_id TEXT NOT NULL,
                championship_name TEXT NOT NULL,
                season_year INTEGER NOT NULL,
                style TEXT NOT NULL,
                tier INTEGER NOT NULL,
                class_name TEXT NOT NULL,
                finishing_place INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(driver_id) REFERENCES drivers(id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS driver_race_results (
                id TEXT PRIMARY KEY,
                driver_id TEXT NOT NULL,
                driver_name TEXT NOT NULL,
                championship_id TEXT NOT NULL,
                championship_name TEXT NOT NULL,
                season_year INTEGER NOT NULL,
                race_num INTEGER NOT NULL,
                track TEXT NOT NULL,
                layout TEXT NOT NULL,
                style TEXT NOT NULL,
                tier INTEGER NOT NULL,
                class_name TEXT NOT NULL DEFAULT 'Overall',
                overall_pos INTEGER NOT NULL,
                class_pos INTEGER NOT NULL,
                class_size INTEGER NOT NULL DEFAULT 0,
                team_name TEXT,
                points_awarded INTEGER NOT NULL DEFAULT 0,
                mmr_change INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(driver_id) REFERENCES drivers(id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS team_reputations (
                team_key TEXT PRIMARY KEY,
                team_id TEXT NOT NULL,
                team_name TEXT NOT NULL,
                game TEXT NOT NULL,
                base_prestige INTEGER NOT NULL DEFAULT 50,
                reputation INTEGER NOT NULL DEFAULT 50,
                seasons_completed INTEGER NOT NULL DEFAULT 0,
                championships INTEGER NOT NULL DEFAULT 0,
                wins INTEGER NOT NULL DEFAULT 0,
                podiums INTEGER NOT NULL DEFAULT 0,
                last_championship TEXT,
                last_style TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS team_driver_decisions (
                id TEXT PRIMARY KEY,
                team_key TEXT NOT NULL,
                team_id TEXT NOT NULL,
                team_name TEXT NOT NULL,
                driver_id TEXT NOT NULL,
                driver_name TEXT NOT NULL,
                championship_id TEXT NOT NULL,
                championship_name TEXT NOT NULL,
                season_year INTEGER NOT NULL,
                decision TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS team_season_results (
                id TEXT PRIMARY KEY,
                team_key TEXT NOT NULL,
                team_id TEXT NOT NULL,
                team_name TEXT NOT NULL,
                championship_id TEXT NOT NULL,
                championship_name TEXT NOT NULL,
                season_year INTEGER NOT NULL,
                game TEXT NOT NULL,
                style TEXT NOT NULL,
                class_name TEXT NOT NULL,
                drivers TEXT NOT NULL,
                driver_count INTEGER NOT NULL DEFAULT 0,
                points INTEGER NOT NULL DEFAULT 0,
                wins INTEGER NOT NULL DEFAULT 0,
                podiums INTEGER NOT NULL DEFAULT 0,
                championships INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS team_championship_seats (
                id TEXT PRIMARY KEY,
                championship_id TEXT NOT NULL,
                championship_name TEXT NOT NULL,
                game TEXT NOT NULL,
                style TEXT NOT NULL,
                seat_number INTEGER NOT NULL,
                team_key TEXT NOT NULL,
                team_id TEXT NOT NULL,
                team_name TEXT NOT NULL,
                team_seat INTEGER NOT NULL DEFAULT 1,
                team_prestige INTEGER NOT NULL DEFAULT 50,
                driver_id TEXT,
                driver_name TEXT,
                class_name TEXT,
                acquired_year INTEGER,
                last_active_year INTEGER,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS team_seat_history (
                id TEXT PRIMARY KEY,
                team_key TEXT NOT NULL,
                team_id TEXT NOT NULL,
                team_name TEXT NOT NULL,
                championship_id TEXT NOT NULL,
                championship_name TEXT NOT NULL,
                game TEXT NOT NULL,
                style TEXT NOT NULL,
                seat_number INTEGER NOT NULL,
                team_seat INTEGER NOT NULL DEFAULT 1,
                event_type TEXT NOT NULL,
                season_year INTEGER,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_drivers_name_human_status
            ON drivers(name, is_human, status)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_drivers_pool_sort
            ON drivers(status, is_human, mmr DESC, name)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_drivers_pool_style
            ON drivers(primary_style, current_style, status, mmr DESC)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_driver_race_results_driver
            ON driver_race_results(driver_id, season_year DESC, championship_name, race_num)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_team_decisions_year
            ON team_driver_decisions(season_year, decision, team_name)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_team_season_results_team
            ON team_season_results(team_key, season_year DESC, championship_name)
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_team_championship_seats_slot
            ON team_championship_seats(championship_id, game, seat_number)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_team_championship_seats_team
            ON team_championship_seats(team_key, status, championship_name)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_team_seat_history_team
            ON team_seat_history(team_key, season_year DESC, created_at DESC)
            """
        )
        _ensure_column(connection, "drivers", "mmr", "INTEGER NOT NULL DEFAULT 1000")
        connection.execute(
            """
            UPDATE drivers
            SET mmr = sports_car_rating
            WHERE mmr IS NULL
            """
        )
        connection.execute(
            """
            UPDATE drivers
            SET mmr = MAX(sports_car_rating, oval_rating, open_wheel_rating)
            WHERE mmr = ?
              AND (
                sports_car_rating != ?
                OR oval_rating != ?
                OR open_wheel_rating != ?
              )
            """,
            (BASELINE_MMR, BASELINE_MMR, BASELINE_MMR, BASELINE_MMR),
        )
        _ensure_column(connection, "drivers", "current_tier", "INTEGER")
        _ensure_column(connection, "drivers", "current_style", "TEXT")
        _ensure_column(connection, "drivers", "current_championship", "TEXT")
        _ensure_column(connection, "drivers", "last_tier", "INTEGER")
        _ensure_column(connection, "drivers", "last_style", "TEXT")
        _ensure_column(connection, "drivers", "podiums", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(connection, "drivers", "debut_year", "INTEGER")
        _ensure_column(connection, "drivers", "retired_year", "INTEGER")
        _ensure_column(connection, "drivers", "country_code", "TEXT")
        _ensure_column(connection, "drivers", "iracing_relative_skill", "INTEGER")
        _ensure_column(connection, "drivers", "iracing_aggression", "INTEGER")
        _ensure_column(connection, "drivers", "iracing_optimism", "INTEGER")
        _ensure_column(connection, "drivers", "iracing_smoothness", "INTEGER")
        _ensure_column(connection, "drivers", "iracing_pit_crew_skill", "INTEGER")
        _ensure_column(connection, "drivers", "iracing_strategy_riskiness", "INTEGER")
        _ensure_column(connection, "drivers", "iracing_sponsor1", "INTEGER")
        _ensure_column(connection, "drivers", "iracing_sponsor2", "INTEGER")
        _ensure_column(connection, "drivers", "driver_age", "INTEGER")
        _ensure_column(connection, "drivers", "ams2_aggression", "REAL")
        _ensure_column(connection, "drivers", "ams2_avoidance_of_forced_mistakes", "REAL")
        _ensure_column(connection, "drivers", "ams2_avoidance_of_mistakes", "REAL")
        _ensure_column(connection, "drivers", "ams2_blue_flag_conceding", "REAL")
        _ensure_column(connection, "drivers", "ams2_consistency", "REAL")
        _ensure_column(connection, "drivers", "ams2_defending", "REAL")
        _ensure_column(connection, "drivers", "ams2_fuel_management", "REAL")
        _ensure_column(connection, "drivers", "ams2_general_skill", "INTEGER")
        _ensure_column(connection, "drivers", "ams2_qualifying_skill", "REAL")
        _ensure_column(connection, "drivers", "ams2_race_skill", "REAL")
        _ensure_column(connection, "drivers", "ams2_stamina", "REAL")
        _ensure_column(connection, "drivers", "ams2_start_reactions", "REAL")
        _ensure_column(connection, "drivers", "ams2_tyre_management", "REAL")
        _ensure_column(connection, "drivers", "ams2_vehicle_reliability", "REAL")
        _ensure_column(connection, "drivers", "ams2_weather_tyre_changes", "REAL")
        _ensure_column(connection, "drivers", "ams2_wet_skill", "REAL")
        connection.execute(
            """
            UPDATE drivers
            SET ams2_general_skill = CASE
                WHEN ams2_race_skill IS NOT NULL THEN MAX(0, MIN(100, ROUND(ams2_race_skill * 100)))
                ELSE 60
            END
            WHERE ams2_general_skill IS NULL
            """
        )
        _ensure_column(connection, "driver_championship_wins", "class_name", "TEXT NOT NULL DEFAULT 'Overall'")
        _ensure_column(connection, "team_championship_seats", "driver_id", "TEXT")
        _ensure_column(connection, "team_championship_seats", "driver_name", "TEXT")
        _ensure_column(connection, "team_championship_seats", "class_name", "TEXT")
        _sync_team_reputations_from_csv(connection)
        missing_profile_rows = connection.execute(
            """
            SELECT id, mmr
            FROM drivers
            WHERE country_code IS NULL
               OR iracing_relative_skill IS NULL
               OR ams2_race_skill IS NULL
            """
        ).fetchall()
        if missing_profile_rows:
            now = _now()
            for row in missing_profile_rows:
                profile = _generate_driver_profile(_safe_int(row["mmr"], BASELINE_MMR))
                _apply_profile_update(connection, str(row["id"]), profile, now)
        connection.execute(
            "INSERT OR REPLACE INTO world_meta (key, value) VALUES (?, ?)",
            ("schema_version", SCHEMA_VERSION),
        )
        if world_year is not None:
            connection.execute(
                "INSERT OR IGNORE INTO world_meta (key, value) VALUES (?, ?)",
                ("world_year", str(world_year)),
            )
        connection.commit()
    _INITIALIZED_POOLS.add(cache_key)
    return path


def _ensure_column(connection: sqlite3.Connection, table_name: str, column_name: str, column_sql: str) -> None:
    columns = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    if column_name in {str(column["name"]) for column in columns}:
        return
    connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")


def add_human_drivers(save_name: str, player_names: list[str]) -> None:
    sync_human_drivers(save_name, player_names)
    initialize_driver_pool(save_name)
    for player_name in player_names:
        add_driver(
            save_name,
            name=player_name,
            is_human=True,
            primary_style="Unassigned",
            retirement_after_seasons=None,
        )


def sync_human_drivers(save_name: str, player_names: list[str]) -> None:
    initialize_driver_pool(save_name)
    clean_player_names = {str(player_name).strip() for player_name in player_names if str(player_name).strip()}
    if not clean_player_names:
        return

    now = _now()
    placeholders = ",".join("?" for _player_name in clean_player_names)
    with _connect(save_name) as connection:
        connection.execute(
            f"""
            UPDATE drivers
            SET is_human = 0,
                updated_at = ?
            WHERE is_human = 1
              AND name NOT IN ({placeholders})
            """,
            [now, *sorted(clean_player_names)],
        )
        connection.commit()


def set_human_primary_style_if_unassigned(save_name: str, player_names: list[str], style: str) -> None:
    initialize_driver_pool(save_name)
    now = _now()
    normalized_style = _normalize_style(style)
    with _connect(save_name) as connection:
        for player_name in player_names:
            connection.execute(
                """
                UPDATE drivers
                SET primary_style = ?, updated_at = ?
                WHERE name = ?
                  AND is_human = 1
                  AND status = 'active'
                  AND primary_style = 'Unassigned'
                """,
                (normalized_style, now, player_name),
            )
        connection.commit()


def set_ai_primary_style_on_first_championship(
    save_name: str,
    standings: list[dict[str, Any]],
    style: str,
) -> None:
    initialize_driver_pool(save_name)
    driver_ids = [str(driver.get("driver_id", "")).strip() for driver in standings if str(driver.get("driver_id", "")).strip()]
    if not driver_ids:
        return

    now = _now()
    normalized_style = _normalize_style(style)
    placeholders = ",".join("?" for _ in driver_ids)
    with _connect(save_name) as connection:
        connection.execute(
            f"""
            UPDATE drivers
            SET primary_style = ?,
                updated_at = ?
            WHERE is_human = 0
              AND status = 'active'
              AND id IN ({placeholders})
              AND (
                primary_style = 'Unassigned'
                OR (career_starts = 0 AND current_championship IS NULL)
              )
            """,
            [normalized_style, now, *driver_ids],
        )
        connection.commit()


def set_current_championship_for_standings(
    save_name: str,
    standings: list[dict[str, Any]],
    championship: dict[str, Any],
) -> None:
    initialize_driver_pool(save_name)
    championship_name = _championship_pool_display_name(championship)
    championship_id = str(championship.get("id", championship_name)).strip()
    if not championship_name:
        return

    now = _now()
    tier = _safe_int(championship.get("Tier"), 1)
    style = _normalize_style(str(championship.get("Style", "Sports Car")))
    driver_ids = [str(driver.get("driver_id", "")).strip() for driver in standings if str(driver.get("driver_id", "")).strip()]
    if not driver_ids:
        return

    placeholders = ",".join("?" for _ in driver_ids)
    with _connect(save_name) as connection:
        connection.execute(
            f"""
            UPDATE drivers
            SET current_championship = ?,
                current_tier = ?,
                current_style = ?,
                last_series_id = ?,
                updated_at = ?
            WHERE id IN ({placeholders})
            """,
            [championship_name, tier, style, championship_id, now, *driver_ids],
        )
        connection.commit()


def finalize_driver_season(
    save_name: str,
    championship: dict[str, Any],
    standings: list[dict[str, Any]],
    advance_world_year: bool = True,
) -> dict[str, Any]:
    initialize_driver_pool(save_name)
    if not standings:
        return {"champions": [], "retired": 0, "forced_retired": 0, "rookies_added": 0}

    championship_id = str(championship.get("id", "")).strip() or str(championship.get("Championship", "")).strip()
    championship_name = str(championship.get("Championship", "")).strip() or "Championship"
    style = _normalize_style(str(championship.get("Style", "Sports Car")))
    tier = _safe_int(championship.get("Tier"), 1)
    season_year = _world_year(save_name)
    driver_ids_by_name = _driver_ids_by_name(save_name)
    now = _now()

    standings = assign_teams_to_standings(list(standings), championship, save_name)

    for driver in standings:
        name = str(driver.get("name", "")).strip()
        driver_id = str(driver.get("driver_id", "") or driver_ids_by_name.get(name, "")).strip()
        if driver_id:
            driver["driver_id"] = driver_id

    champions = _class_champions(standings)
    champion_ids = [str(driver.get("driver_id", "")).strip() for driver in champions if str(driver.get("driver_id", "")).strip()]
    participant_ids = [str(driver.get("driver_id", "")).strip() for driver in standings if str(driver.get("driver_id", "")).strip()]
    forced_retire_ids = _forced_retirement_ids(standings, tier)
    season_results: list[tuple[str, str, int]] = []
    by_class: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for driver in standings:
        class_name = str(driver.get("class_name", "Overall")).strip() or "Overall"
        by_class[class_name].append(driver)
    for class_name, class_drivers in by_class.items():
        sorted_drivers = sorted(
            class_drivers,
            key=lambda driver: (int(driver.get("points", 0)), int(driver.get("wins", 0))),
            reverse=True,
        )
        for finishing_place, driver in enumerate(sorted_drivers, 1):
            driver_id = str(driver.get("driver_id", "")).strip()
            if driver_id:
                season_results.append((driver_id, class_name, finishing_place))

    retired_count = 0
    forced_retired_count = 0
    with _connect(save_name) as connection:
        for driver in standings:
            driver_id = str(driver.get("driver_id", "")).strip()
            pending_starts = _safe_int(driver.get("_pending_career_starts"), 0)
            if not driver_id or pending_starts <= 0:
                continue
            connection.execute(
                """
                UPDATE drivers
                SET mmr = ?,
                    career_starts = career_starts + ?,
                    wins = wins + ?,
                    podiums = podiums + ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    max(0, _safe_int(driver.get("mmr"), BASELINE_MMR)),
                    pending_starts,
                    _safe_int(driver.get("_pending_career_wins"), 0),
                    _safe_int(driver.get("_pending_career_podiums"), 0),
                    now,
                    driver_id,
                ),
            )
        for driver_id, class_name, finishing_place in season_results:
            connection.execute(
                """
                INSERT INTO driver_season_results (
                    id,
                    driver_id,
                    championship_id,
                    championship_name,
                    season_year,
                    style,
                    tier,
                    class_name,
                    finishing_place,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    driver_id,
                    championship_id,
                    championship_name,
                    season_year,
                    style,
                    tier,
                    class_name,
                    finishing_place,
                    now,
                ),
            )
        for champion in champions:
            driver_id = str(champion.get("driver_id", "")).strip()
            if not driver_id:
                continue
            class_name = str(champion.get("class_name", "Overall")).strip() or "Overall"
            connection.execute(
                """
                INSERT INTO driver_championship_wins (
                    id,
                    driver_id,
                    championship_id,
                    championship_name,
                    season_year,
                    style,
                    tier,
                    class_name,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    driver_id,
                    championship_id,
                    championship_name,
                    season_year,
                    style,
                    tier,
                    class_name,
                    now,
                ),
            )

        if champion_ids:
            placeholders = ",".join("?" for _ in champion_ids)
            connection.execute(
                f"""
                UPDATE drivers
                SET championships = championships + 1,
                    updated_at = ?
                WHERE id IN ({placeholders})
                """,
                [now, *champion_ids],
            )

        team_summary = _update_team_reputations_for_season(connection, championship, standings, season_year, now)

        if participant_ids:
            placeholders = ",".join("?" for _ in participant_ids)
            connection.execute(
                f"""
                UPDATE drivers
                SET seasons_completed = seasons_completed + 1,
                    last_tier = current_tier,
                    last_style = current_style,
                    current_championship = NULL,
                    current_tier = NULL,
                    current_style = NULL,
                    updated_at = ?
                WHERE id IN ({placeholders})
                """,
                [now, *participant_ids],
            )

        if forced_retire_ids:
            placeholders = ",".join("?" for _ in forced_retire_ids)
            connection.execute(
                f"""
                DELETE FROM drivers
                WHERE is_human = 0
                  AND id IN ({placeholders})
                """,
                forced_retire_ids,
            )
            forced_retired_count = len(forced_retire_ids)

        eligible_rows = connection.execute(
            """
            SELECT id
            FROM drivers
            WHERE is_human = 0
              AND status = 'active'
              AND retirement_after_seasons IS NOT NULL
              AND seasons_completed >= retirement_after_seasons
            """
        ).fetchall()
        retirement_ids = [str(row["id"]) for row in eligible_rows]
        if retirement_ids:
            placeholders = ",".join("?" for _ in retirement_ids)
            connection.execute(
                f"""
                UPDATE drivers
                SET status = 'retired',
                    current_championship = NULL,
                    current_tier = NULL,
                    current_style = NULL,
                    retired_year = ?,
                    updated_at = ?
                WHERE id IN ({placeholders})
                """,
                [season_year, now, *retirement_ids],
            )
            retired_count = len(retirement_ids)

        if advance_world_year:
            _age_all_drivers_one_year(connection, now)
            connection.execute(
                """
                INSERT OR REPLACE INTO world_meta (key, value)
                VALUES ('world_year', ?)
                """,
                (str(season_year + 1),),
            )
        connection.commit()

    rookies_to_add = retired_count + forced_retired_count
    _add_rookies(save_name, rookies_to_add, style)
    return {
        "champions": [str(driver.get("name", "")) for driver in champions],
        "retired": retired_count,
        "forced_retired": forced_retired_count,
        "rookies_added": rookies_to_add,
        "season_year": season_year,
        "next_world_year": season_year + 1 if advance_world_year else season_year,
        "teams": int(team_summary.get("teams", 0)),
        "team_seasons": int(team_summary.get("team_seasons", 0)),
    }


def update_ratings_after_race(
    save_name: str,
    championship: dict[str, Any],
    standings: list[dict[str, Any]],
    result_rows: list[dict[str, Any]],
    persist: bool = True,
) -> dict[str, int]:
    initialize_driver_pool(save_name)
    standings_by_name = {str(driver.get("name", "")).strip(): driver for driver in standings}
    driver_ids_by_name: dict[str, str] = {}
    driver_ids: dict[str, str] = {}
    for driver in standings:
        name = str(driver.get("name", "")).strip()
        driver_id = str(driver.get("driver_id", "")).strip()
        if not driver_id and name:
            if not driver_ids_by_name:
                driver_ids_by_name = _driver_ids_by_name(save_name)
            driver_id = str(driver_ids_by_name.get(name, "")).strip()
        if name and driver_id:
            driver["driver_id"] = driver_id
            driver_ids[name] = driver_id

    if not driver_ids:
        return {}

    if persist:
        current_ratings = _ratings_for_driver_ids(save_name, list(driver_ids.values()))
    else:
        current_ratings = {}
        for name, driver_id in driver_ids.items():
            standing = standings_by_name.get(name, {})
            current_ratings[driver_id] = _safe_int(standing.get("mmr"), BASELINE_MMR)
    finish_groups: dict[str, list[str]] = defaultdict(list)
    for row in sorted(result_rows, key=lambda value: int(value.get("class_pos", 0) or 0)):
        driver_name = str(row.get("driver_name", "")).strip()
        class_name = str(row.get("class_name", "Overall")).strip() or "Overall"
        if driver_name in driver_ids:
            finish_groups[class_name].append(driver_name)

    rating_changes: dict[str, int] = {}
    for class_finish_order in finish_groups.values():
        class_changes = _elo_changes_for_finish_order(class_finish_order, driver_ids, current_ratings)
        for driver_id, change in class_changes.items():
            rating_changes[driver_id] = rating_changes.get(driver_id, 0) + change

    if not rating_changes:
        return {}

    now = _now()
    winner_names = {
        str(row.get("driver_name", "")).strip()
        for row in result_rows
        if int(row.get("class_pos", 0) or 0) == 1
    }
    winner_ids = {driver_ids[name] for name in winner_names if name in driver_ids}
    podium_names = {
        str(row.get("driver_name", "")).strip()
        for row in result_rows
        if 1 <= int(row.get("class_pos", 0) or 0) <= 3
    }
    podium_ids = {driver_ids[name] for name in podium_names if name in driver_ids}

    if persist:
        with _connect(save_name) as connection:
            for driver_id, change in rating_changes.items():
                new_rating = max(0, int(current_ratings[driver_id]) + change)
                connection.execute(
                    f"""
                    UPDATE drivers
                    SET mmr = ?,
                        career_starts = career_starts + 1,
                        wins = wins + ?,
                        podiums = podiums + ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (new_rating, 1 if driver_id in winner_ids else 0, 1 if driver_id in podium_ids else 0, now, driver_id),
                )
            connection.commit()

    change_by_name = {name: rating_changes[driver_id] for name, driver_id in driver_ids.items() if driver_id in rating_changes}
    podium_name_set = set(podium_names)
    for driver in standings:
        name = str(driver.get("name", "")).strip()
        driver_id = str(driver.get("driver_id", "")).strip()
        if driver_id in rating_changes:
            driver["mmr_change"] = rating_changes[driver_id]
            driver["mmr"] = max(0, int(current_ratings[driver_id]) + rating_changes[driver_id])
            if not persist:
                driver["_pending_career_starts"] = int(driver.get("_pending_career_starts", 0) or 0) + 1
                if driver_id in winner_ids:
                    driver["_pending_career_wins"] = int(driver.get("_pending_career_wins", 0) or 0) + 1
                if driver_id in podium_ids:
                    driver["_pending_career_podiums"] = int(driver.get("_pending_career_podiums", 0) or 0) + 1
        if name in podium_name_set:
            driver["podiums"] = int(driver.get("podiums", 0) or 0) + 1
    for row in result_rows:
        driver_name = str(row.get("driver_name", "")).strip()
        if driver_name in change_by_name:
            row["mmr_change"] = change_by_name[driver_name]

    return change_by_name


def record_driver_race_results(
    save_name: str,
    championship: dict[str, Any],
    race: dict[str, Any],
    standings: list[dict[str, Any]],
    result_rows: list[dict[str, Any]],
) -> None:
    initialize_driver_pool(save_name)
    if not result_rows:
        return

    driver_ids_by_name = _driver_ids_by_name(save_name)
    standings_by_name = {str(driver.get("name", "")).strip(): driver for driver in standings}
    championship_id = str(championship.get("id", "")).strip() or str(championship.get("Championship", "")).strip()
    championship_name = str(championship.get("Championship", "")).strip() or "Championship"
    style = _normalize_style(str(championship.get("Style", "Sports Car")))
    tier = _safe_int(championship.get("Tier"), 1)
    season_year = _world_year(save_name)
    race_num = _safe_int(race.get("race_num"), 0)
    track = str(race.get("track", "")).strip()
    layout = str(race.get("layout", "")).strip()
    now = _now()

    with _connect(save_name) as connection:
        connection.execute(
            """
            DELETE FROM driver_race_results
            WHERE championship_id = ?
              AND season_year = ?
              AND race_num = ?
            """,
            (championship_id, season_year, race_num),
        )
        for row in result_rows:
            driver_name = str(row.get("driver_name", "")).strip()
            if not driver_name:
                continue
            standing = standings_by_name.get(driver_name, {})
            driver_id = str(standing.get("driver_id", "") or driver_ids_by_name.get(driver_name, "")).strip()
            if not driver_id:
                continue
            connection.execute(
                """
                INSERT INTO driver_race_results (
                    id,
                    driver_id,
                    driver_name,
                    championship_id,
                    championship_name,
                    season_year,
                    race_num,
                    track,
                    layout,
                    style,
                    tier,
                    class_name,
                    overall_pos,
                    class_pos,
                    class_size,
                    team_name,
                    points_awarded,
                    mmr_change,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    driver_id,
                    driver_name,
                    championship_id,
                    championship_name,
                    season_year,
                    race_num,
                    track,
                    layout,
                    style,
                    tier,
                    str(row.get("class_name", "Overall")).strip() or "Overall",
                    _safe_int(row.get("overall_pos"), 0),
                    _safe_int(row.get("class_pos"), 0),
                    _safe_int(row.get("class_size"), 0),
                    str(row.get("team_name", "")).strip() or None,
                    _safe_int(row.get("points_awarded"), 0),
                    None if row.get("mmr_change") is None else _safe_int(row.get("mmr_change"), 0),
                    now,
                ),
            )
        connection.commit()


def add_ai_drivers_from_standings(
    save_name: str,
    standings: list[dict[str, Any]],
    player_names: list[str],
    championship: dict[str, Any],
) -> None:
    initialize_driver_pool(save_name)
    player_set = set(player_names)
    for driver in standings:
        name = str(driver.get("name", "")).strip()
        if not name or name in player_set:
            continue
        driver_id = add_driver(
            save_name,
            name=name,
            is_human=False,
            primary_style="Unassigned",
            retirement_after_seasons=_retirement_target(),
        )
        driver["driver_id"] = driver_id


def build_standings_from_pool(
    save_name: str,
    player_names: list[str],
    num_opponents: int,
    championship: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build the active championship field from this save's persistent driver pool."""
    initialize_driver_pool(save_name)
    style = _normalize_style(str(championship.get("Style", "Sports Car")))
    tier = _safe_int(championship.get("_field_tier", championship.get("Tier")), 1)
    player_set = {name.strip() for name in player_names if name.strip()}
    human_ids = _human_driver_ids(save_name, player_set)
    human_ratings = _ratings_for_driver_ids(save_name, [driver_id for driver_id in human_ids.values() if driver_id])
    standings: list[dict[str, Any]] = [
        {
            "driver_id": human_ids.get(player_name),
            "name": player_name,
            "nationality": "Player",
            "skill": _skill_from_rating(human_ratings.get(human_ids.get(player_name), BASELINE_MMR)),
            "mmr": human_ratings.get(human_ids.get(player_name), BASELINE_MMR),
            "points": 0,
            "wins": 0,
            "podiums": 0,
        }
        for player_name in player_names
    ]

    _ensure_rookies_available(save_name, num_opponents, player_set, style)
    class_tiers = championship.get("_class_tiers", {})
    player_class_name = str(championship.get("_player_class_name", "")).strip()
    if isinstance(class_tiers, dict) and len(class_tiers) > 1:
        class_targets = _multiclass_target_counts(
            [str(name).strip() for name in class_tiers.keys() if str(name).strip()],
            len(standings) + num_opponents,
            player_class_name,
            len(player_names),
        )
        excluded_names = set(player_set)
        ai_drivers: list[dict[str, Any]] = []
        ordered_class_targets = sorted(
            class_targets.items(),
            key=lambda item: (-_safe_int(class_tiers.get(item[0]), tier), item[0]),
        )
        for class_name, target_count in ordered_class_targets:
            human_count = len(player_names) if class_name.casefold() == player_class_name.casefold() else 0
            ai_needed = max(0, target_count - human_count)
            if ai_needed <= 0:
                continue
            class_tier = _safe_int(class_tiers.get(class_name), tier)
            selected = _select_active_ai(save_name, ai_needed, excluded_names, style, class_tier, championship)
            if len(selected) < ai_needed:
                _ensure_rookies_available(save_name, num_opponents + max(1, ai_needed - len(selected)), excluded_names, style)
                selected = _select_active_ai(save_name, ai_needed, excluded_names, style, class_tier, championship)
            for driver in selected:
                driver["class_name"] = class_name
                ai_drivers.append(driver)
                excluded_names.add(str(driver.get("name", "")).strip())
        standings.extend(ai_drivers[:num_opponents])
    else:
        ai_drivers = _select_active_ai(save_name, num_opponents, player_set, style, tier, championship)
        if len(ai_drivers) < num_opponents:
            _ensure_rookies_available(save_name, num_opponents + max(1, num_opponents - len(ai_drivers)), player_set, style)
            ai_drivers = _select_active_ai(save_name, num_opponents, player_set, style, tier, championship)
        standings.extend(ai_drivers)
    return assign_teams_to_standings(standings, championship, save_name)


def simulate_ai_world_season(
    save_name: str,
    championships: list[dict[str, Any]],
    excluded_championship_id: str = "",
) -> dict[str, int]:
    """Simulate AI-only championships for the rest of the world in the current season."""
    initialize_driver_pool(save_name)
    used_driver_ids: set[str] = set()
    used_driver_names: set[str] = set()
    summary = {
        "championships": 0,
        "races": 0,
        "drivers": 0,
        "retired": 0,
        "forced_retired": 0,
        "rookies_added": 0,
        "teams": 0,
        "team_seasons": 0,
    }

    for championship in _world_championship_instances(championships, excluded_championship_id):
        field_size = _world_field_size(championship)
        standings, generated_rookies = _build_ai_world_standings(
            save_name,
            championship,
            field_size,
            used_driver_ids,
            used_driver_names,
        )
        summary["rookies_added"] += generated_rookies
        if len(standings) < 2:
            continue

        race_count = _safe_int(championship.get("Num of Races"), 4)
        for _race_index in range(race_count):
            finish_order = _weighted_finish_order(save_name, standings, str(championship.get("Game", "iRacing") or "iRacing"))
            _apply_world_points_by_class(standings, finish_order)
            _, result_rows = _world_result_rows(standings, finish_order)
            update_ratings_after_race(save_name, championship, standings, result_rows)

        season_summary = finalize_driver_season(save_name, championship, standings, advance_world_year=False)
        summary["championships"] += 1
        summary["races"] += race_count
        summary["drivers"] += len(standings)
        summary["retired"] += int(season_summary.get("retired", 0))
        summary["forced_retired"] += int(season_summary.get("forced_retired", 0))
        summary["rookies_added"] += int(season_summary.get("rookies_added", 0))
        summary["teams"] += int(season_summary.get("teams", 0))
        summary["team_seasons"] += int(season_summary.get("team_seasons", 0))

    return summary


def simulate_ai_world_chunk(
    save_name: str,
    championships: list[dict[str, Any]],
    progress: dict[str, Any] | None = None,
    chunk_size: int = 1,
    excluded_championship_id: str = "",
) -> tuple[dict[str, Any], dict[str, int]]:
    """Simulate a saved slice of the AI world season."""
    initialize_driver_pool(save_name)
    instances = _world_championship_instances(championships, excluded_championship_id)
    current_progress = _normalize_world_sim_progress(progress)
    current_progress["total_instances"] = len(instances)

    start_index = max(0, min(int(current_progress.get("next_index", 0)), len(instances)))
    end_index = max(start_index, min(len(instances), start_index + max(1, int(chunk_size))))
    used_driver_ids = set(current_progress.get("used_driver_ids", []))
    used_driver_names = set(current_progress.get("used_driver_names", []))
    summary = _empty_world_sim_summary()

    for championship in instances[start_index:end_index]:
        field_size = _world_field_size(championship)
        standings, generated_rookies = _build_ai_world_standings(
            save_name,
            championship,
            field_size,
            used_driver_ids,
            used_driver_names,
        )
        summary["rookies_added"] += generated_rookies
        if len(standings) < 2:
            continue

        race_count = _safe_int(championship.get("Num of Races"), 4)
        for _race_index in range(race_count):
            finish_order = _weighted_finish_order(save_name, standings, str(championship.get("Game", "iRacing") or "iRacing"))
            _apply_world_points_by_class(standings, finish_order)
            _, result_rows = _world_result_rows(standings, finish_order)
            update_ratings_after_race(save_name, championship, standings, result_rows)

        season_summary = finalize_driver_season(save_name, championship, standings, advance_world_year=False)
        summary["championships"] += 1
        summary["races"] += race_count
        summary["drivers"] += len(standings)
        summary["retired"] += int(season_summary.get("retired", 0))
        summary["forced_retired"] += int(season_summary.get("forced_retired", 0))
        summary["rookies_added"] += int(season_summary.get("rookies_added", 0))
        summary["teams"] += int(season_summary.get("teams", 0))
        summary["team_seasons"] += int(season_summary.get("team_seasons", 0))

    current_progress["next_index"] = end_index
    current_progress["used_driver_ids"] = sorted(used_driver_ids)
    current_progress["used_driver_names"] = sorted(used_driver_names)
    current_progress["complete"] = end_index >= len(instances)
    current_progress["last_summary"] = summary
    current_progress["summary"] = _merge_world_sim_summaries(
        current_progress.get("summary", _empty_world_sim_summary()),
        summary,
    )
    return current_progress, summary


def world_simulation_instance_count(championships: list[dict[str, Any]], excluded_championship_id: str = "") -> int:
    return len(_world_championship_instances(championships, excluded_championship_id))


def build_world_championship_instances(
    championships: list[dict[str, Any]],
    excluded_championship_id: str = "",
) -> list[dict[str, Any]]:
    return _world_championship_instances(championships, excluded_championship_id)


def world_championship_field_size(championship: dict[str, Any]) -> int:
    return _world_field_size(championship)


def build_ai_world_standings(
    save_name: str,
    championship: dict[str, Any],
    field_size: int,
    used_driver_ids: set[str],
    used_driver_names: set[str],
    available_ai_rows: list[sqlite3.Row] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    return _build_ai_world_standings(
        save_name,
        championship,
        field_size,
        used_driver_ids,
        used_driver_names,
        available_ai_rows,
    )


def populate_world_sim_instances(
    save_name: str,
    instances: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    used_driver_ids: set[str] = set()
    used_driver_names: set[str] = set()
    for instance in instances:
        for driver in list(instance.get("standings") or []):
            driver_id = str(driver.get("driver_id", "")).strip()
            driver_name = str(driver.get("name", "")).strip()
            if driver_id:
                used_driver_ids.add(driver_id)
            if driver_name:
                used_driver_names.add(driver_name)
    summary = _empty_world_sim_summary()

    prestige_bucket: set[int] = set()
    for instance in instances:
        championship = instance.get("championship") or {}
        prestige_bucket.add(_safe_int(championship.get("Prestige"), 0))
        class_prestiges = (championship.get("_class_prestiges", {}) or {}).values()
        for value in class_prestiges:
            prestige_bucket.add(_safe_int(value, 0))
    prestige_values = sorted(prestige_bucket, reverse=True)
    if not prestige_values:
        return instances, summary

    lowest_prestige = prestige_values[-1]
    for world_prestige in prestige_values:
        if world_prestige == lowest_prestige:
            while True:
                round_progress = False
                for instance in instances:
                    championship = instance.get("championship") or {}
                    field_size = int(instance.get("field_size", 0) or 0)
                    standings = list(instance.get("standings") or [])
                    before_count = len(standings)
                    updated_standings, rookies_added = _fill_world_instance_for_prestige(
                        save_name,
                        championship,
                        field_size,
                        world_prestige,
                        standings,
                        used_driver_ids,
                        used_driver_names,
                        max_new_drivers=LOWEST_PRESTIGE_FILL_BATCH_SIZE,
                    )
                    instance["standings"] = updated_standings
                    summary["rookies_added"] += rookies_added
                    if len(updated_standings) > before_count:
                        round_progress = True
                if not round_progress:
                    break
        else:
            for instance in instances:
                championship = instance.get("championship") or {}
                field_size = int(instance.get("field_size", 0) or 0)
                standings = list(instance.get("standings") or [])
                updated_standings, rookies_added = _fill_world_instance_for_prestige(
                    save_name,
                    championship,
                    field_size,
                    world_prestige,
                    standings,
                    used_driver_ids,
                    used_driver_names,
                )
                instance["standings"] = updated_standings
                summary["rookies_added"] += rookies_added

    summary["drivers"] = sum(len(instance.get("standings") or []) for instance in instances)
    return instances, summary


def add_driver(
    save_name: str,
    name: str,
    is_human: bool,
    primary_style: str,
    retirement_after_seasons: int | None,
    age_range: tuple[int, int] = (18, 56),
) -> str:
    initialize_driver_pool(save_name)
    cleaned_name = name.strip()
    if not cleaned_name:
        raise ValueError("Driver name cannot be blank.")

    now = _now()
    debut_year = _world_year(save_name)
    profile = _generate_driver_profile(BASELINE_MMR, age_range=age_range)
    insert_columns = (
        "id",
        "name",
        "is_human",
        "status",
        "primary_style",
        "mmr",
        "sports_car_rating",
        "oval_rating",
        "open_wheel_rating",
        "seasons_completed",
        "retirement_after_seasons",
        "career_starts",
        "wins",
        "championships",
        "last_tier",
        "last_style",
        "debut_year",
        "retired_year",
        "last_series_id",
        "country_code",
        "iracing_relative_skill",
        "iracing_aggression",
        "iracing_optimism",
        "iracing_smoothness",
        "iracing_pit_crew_skill",
        "iracing_strategy_riskiness",
        "iracing_sponsor1",
        "iracing_sponsor2",
        "driver_age",
        "ams2_aggression",
        "ams2_avoidance_of_forced_mistakes",
        "ams2_avoidance_of_mistakes",
        "ams2_blue_flag_conceding",
        "ams2_consistency",
        "ams2_defending",
        "ams2_fuel_management",
        "ams2_general_skill",
        "ams2_qualifying_skill",
        "ams2_race_skill",
        "ams2_stamina",
        "ams2_start_reactions",
        "ams2_tyre_management",
        "ams2_vehicle_reliability",
        "ams2_weather_tyre_changes",
        "ams2_wet_skill",
        "created_at",
        "updated_at",
    )
    with _connect(save_name) as connection:
        existing = connection.execute(
            """
            SELECT id FROM drivers
            WHERE name = ? AND is_human = ? AND status = 'active'
            """,
            (cleaned_name, 1 if is_human else 0),
        ).fetchone()
        if existing:
            return str(existing["id"])

        driver_id = str(uuid.uuid4())
        insert_values = (
            driver_id,
            cleaned_name,
            1 if is_human else 0,
            "active",
            primary_style if primary_style in (*STYLES, "Unassigned") else "Sports Car",
            BASELINE_MMR,
            BASELINE_MMR,
            BASELINE_MMR,
            BASELINE_MMR,
            0,
            retirement_after_seasons,
            0,
            0,
            0,
            None,
            None,
            debut_year,
            None,
            None,
            profile["country_code"],
            profile["iracing_relative_skill"],
            profile["iracing_aggression"],
            profile["iracing_optimism"],
            profile["iracing_smoothness"],
            profile["iracing_pit_crew_skill"],
            profile["iracing_strategy_riskiness"],
            profile["iracing_sponsor1"],
            profile["iracing_sponsor2"],
            profile["driver_age"],
            profile["ams2_aggression"],
            profile["ams2_avoidance_of_forced_mistakes"],
            profile["ams2_avoidance_of_mistakes"],
            profile["ams2_blue_flag_conceding"],
            profile["ams2_consistency"],
            profile["ams2_defending"],
            profile["ams2_fuel_management"],
            profile["ams2_general_skill"],
            profile["ams2_qualifying_skill"],
            profile["ams2_race_skill"],
            profile["ams2_stamina"],
            profile["ams2_start_reactions"],
            profile["ams2_tyre_management"],
            profile["ams2_vehicle_reliability"],
            profile["ams2_weather_tyre_changes"],
            profile["ams2_wet_skill"],
            now,
            now,
        )
        connection.execute(
            f"""
            INSERT INTO drivers ({", ".join(insert_columns)})
            VALUES ({", ".join("?" for _ in insert_columns)})
            """,
            insert_values,
        )
        connection.commit()
    return driver_id


def _ensure_rookies_available(
    save_name: str,
    needed_ai_count: int,
    player_names: set[str],
    style: str,
) -> None:
    current_count = _active_ai_count(save_name, player_names)
    if current_count >= needed_ai_count:
        return
    _add_rookies(save_name, needed_ai_count - current_count, style, player_names)


def _world_championship_instances(
    championships: list[dict[str, Any]],
    excluded_championship_id: str,
) -> list[dict[str, Any]]:
    instances: list[dict[str, Any]] = []
    excluded_id = str(excluded_championship_id).strip()
    for championship in championships:
        championship_id = str(championship.get("id", "")).strip()
        if excluded_id and championship_id == excluded_id:
            continue
        instance = dict(championship)
        instance["id"] = championship_id or str(uuid.uuid4())
        instance["Pool_Championship"] = _championship_group_display_name(championship, 0, 1)
        instances.append(instance)
    instances.sort(
        key=lambda row: (
            -_safe_int(row.get("Prestige"), 0),
            -_safe_int(row.get("Tier"), 1),
            str(row.get("Style", "")),
            str(row.get("Championship", "")),
        )
    )
    return instances


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


def _normalize_world_sim_progress(progress: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(progress, dict):
        progress = {}
    return {
        "next_index": _safe_int(progress.get("next_index"), 0),
        "total_instances": _safe_int(progress.get("total_instances"), 0),
        "used_driver_ids": list(progress.get("used_driver_ids") or []),
        "used_driver_names": list(progress.get("used_driver_names") or []),
        "complete": bool(progress.get("complete", False)),
        "summary": _merge_world_sim_summaries(_empty_world_sim_summary(), progress.get("summary", {})),
        "last_summary": _merge_world_sim_summaries(_empty_world_sim_summary(), progress.get("last_summary", {})),
    }


def _merge_world_sim_summaries(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, int]:
    merged = _empty_world_sim_summary()
    for key in merged:
        merged[key] = _safe_int(base.get(key), 0) + _safe_int(extra.get(key), 0)
    return merged


def _world_field_size(championship: dict[str, Any]) -> int:
    max_drivers = max(2, min(40, _safe_int(championship.get("Max_Opp"), 20)))
    return max_drivers


def _world_class_names(championship: dict[str, Any]) -> list[str]:
    raw_classes = championship.get("_class_names", [])
    if isinstance(raw_classes, str):
        class_names = [value.strip() for value in raw_classes.split("|") if value.strip()]
    else:
        class_names = [str(value).strip() for value in raw_classes if str(value).strip()]
    if class_names:
        return class_names
    return ["Overall"]


def _ensure_world_rookies_available(
    save_name: str,
    needed_count: int,
    excluded_names: set[str],
    style: str,
) -> int:
    available_count = _available_world_ai_count(save_name, excluded_names)
    if available_count >= needed_count:
        return 0
    return _add_rookies(save_name, needed_count - available_count, style, excluded_names)


def _available_world_ai_count(save_name: str, excluded_names: set[str]) -> int:
    with _connect(save_name) as connection:
        rows = connection.execute(
            """
            SELECT name
            FROM drivers
            WHERE is_human = 0
              AND status = 'active'
              AND current_championship IS NULL
            """
        ).fetchall()
    return sum(1 for row in rows if str(row["name"]) not in excluded_names)


def _build_ai_world_standings(
    save_name: str,
    championship: dict[str, Any],
    field_size: int,
    used_driver_ids: set[str],
    used_driver_names: set[str],
    available_ai_rows: list[sqlite3.Row] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    style = _normalize_style(str(championship.get("Style", "Sports Car")))
    tier = _safe_int(championship.get("Tier"), 1)
    remaining_field_size = field_size

    rookies_added = _ensure_world_rookies_available(save_name, remaining_field_size, used_driver_names, style)
    class_tiers = championship.get("_class_tiers", {})
    class_prestiges = championship.get("_class_prestiges", {})
    if isinstance(class_tiers, dict) and class_tiers and not class_prestiges:
        class_prestiges = {class_name: _safe_int(championship.get("Prestige"), 0) for class_name in class_tiers}
    standings: list[dict[str, Any]] = []
    if isinstance(class_tiers, dict) and len(class_tiers) > 1:
        class_targets = _multiclass_target_counts(
            [str(name).strip() for name in class_tiers.keys() if str(name).strip()],
            field_size,
        )
        reserved_driver_ids = set(used_driver_ids)
        reserved_driver_names = set(used_driver_names)
        selected_rows: list[tuple[int, sqlite3.Row, str]] = []
        ordered_class_targets = sorted(
            class_targets.items(),
            key=lambda item: (
                -_safe_int(class_prestiges.get(item[0]), 0),
                -_safe_int(class_tiers.get(item[0]), tier),
                item[0],
            ),
        )
        for class_name, target_count in ordered_class_targets:
            current_count = sum(
                1
                for driver in standings
                if str(driver.get("class_name", "")).strip().casefold() == str(class_name).strip().casefold()
            )
            needed = max(0, target_count - current_count)
            if needed <= 0:
                continue
            class_tier = _safe_int(class_tiers.get(class_name), tier)
            class_rows = _select_world_ai_rows(
                save_name,
                needed,
                style,
                class_tier,
                championship,
                reserved_driver_ids,
                reserved_driver_names,
                available_ai_rows,
            )
            if len(class_rows) < needed:
                rookies_added += _ensure_world_rookies_available(
                    save_name,
                    field_size + max(1, needed - len(class_rows)),
                    reserved_driver_names,
                    style,
                )
                available_ai_rows = _active_world_ai_rows(save_name)
                class_rows = _select_world_ai_rows(
                    save_name,
                    needed,
                    style,
                    class_tier,
                    championship,
                    reserved_driver_ids,
                    reserved_driver_names,
                    available_ai_rows,
                )
            for effective_mmr, row in class_rows:
                reserved_driver_ids.add(str(row["id"]))
                reserved_driver_names.add(str(row["name"]))
                selected_rows.append((effective_mmr, row, class_name))
        for effective_mmr, row, class_name in selected_rows[:remaining_field_size]:
            driver_id = str(row["id"])
            driver_name = str(row["name"])
            used_driver_ids.add(driver_id)
            used_driver_names.add(driver_name)
            standings.append(
                {
                    "driver_id": driver_id,
                    "name": driver_name,
                    "nationality": "AI",
                    "skill": _skill_from_rating(effective_mmr),
                    "mmr": int(row["mmr"]),
                    "points": 0,
                    "wins": 0,
                    "podiums": 0,
                    "primary_style": str(row["primary_style"]),
                    "class_name": class_name,
                    "season_form": round(random.gauss(0, WORLD_SIM_SEASON_FORM_STDDEV)),
                }
            )
    else:
        selected_rows = _select_world_ai_rows(
            save_name,
            remaining_field_size,
            style,
            tier,
            championship,
            used_driver_ids,
            used_driver_names,
            available_ai_rows,
        )
        if len(selected_rows) < remaining_field_size:
            rookies_added += _ensure_world_rookies_available(
                save_name,
                remaining_field_size + max(1, remaining_field_size - len(selected_rows)),
                used_driver_names,
                style,
            )
            available_ai_rows = _active_world_ai_rows(save_name)
            selected_rows = _select_world_ai_rows(
                save_name,
                remaining_field_size,
                style,
                tier,
                championship,
                used_driver_ids,
                used_driver_names,
                available_ai_rows,
            )

        class_assignments = _world_class_assignments(championship, len(selected_rows))
        for index, (effective_mmr, row) in enumerate(selected_rows):
            driver_id = str(row["id"])
            driver_name = str(row["name"])
            used_driver_ids.add(driver_id)
            used_driver_names.add(driver_name)
            standings.append(
                {
                    "driver_id": driver_id,
                    "name": driver_name,
                    "nationality": "AI",
                    "skill": _skill_from_rating(effective_mmr),
                    "mmr": int(row["mmr"]),
                    "points": 0,
                    "wins": 0,
                    "podiums": 0,
                    "primary_style": str(row["primary_style"]),
                    "class_name": class_assignments[index] if index < len(class_assignments) else "Overall",
                    "season_form": round(random.gauss(0, WORLD_SIM_SEASON_FORM_STDDEV)),
                }
            )
    return assign_teams_to_standings(standings, championship, save_name), rookies_added


def _driver_row_to_world_standing(effective_mmr: int, row: sqlite3.Row, class_name: str) -> dict[str, Any]:
    return {
        "driver_id": str(row["id"]),
        "name": str(row["name"]),
        "nationality": "AI",
        "skill": _skill_from_rating(effective_mmr),
        "mmr": int(row["mmr"]),
        "points": 0,
        "wins": 0,
        "podiums": 0,
        "primary_style": str(row["primary_style"]),
        "class_name": class_name,
        "season_form": round(random.gauss(0, WORLD_SIM_SEASON_FORM_STDDEV)),
    }


def _fill_world_instance_for_prestige(
    save_name: str,
    championship: dict[str, Any],
    field_size: int,
    world_prestige: int,
    standings: list[dict[str, Any]],
    used_driver_ids: set[str],
    used_driver_names: set[str],
    max_new_drivers: int | None = None,
) -> tuple[list[dict[str, Any]], int]:
    style = _normalize_style(str(championship.get("Style", "Sports Car")))
    championship_tier = _safe_int(championship.get("Tier"), 1)
    championship_prestige = _safe_int(championship.get("Prestige"), 0)
    rookies_added = 0

    class_tiers = championship.get("_class_tiers", {})
    class_prestiges = championship.get("_class_prestiges", {})
    if isinstance(class_tiers, dict) and class_tiers and not class_prestiges:
        class_prestiges = {class_name: championship_prestige for class_name in class_tiers}
    if isinstance(class_tiers, dict) and len(class_tiers) > 1:
        class_targets = _multiclass_target_counts(
            [str(name).strip() for name in class_tiers.keys() if str(name).strip()],
            field_size,
        )
        active_classes = sorted(
            [
                class_name
                for class_name, class_prestige in class_prestiges.items()
                if _safe_int(class_prestige, championship_prestige) == world_prestige
            ]
        )
        if not active_classes:
            return standings, rookies_added

        for class_name in active_classes:
            current_count = sum(
                1
                for driver in standings
                if str(driver.get("class_name", "")).strip().casefold() == str(class_name).strip().casefold()
            )
            target_count = int(class_targets.get(class_name, 0) or 0)
            needed = max(0, target_count - current_count)
            if max_new_drivers is not None:
                needed = min(needed, max_new_drivers)
            if needed <= 0:
                continue

            class_tier = _safe_int(class_tiers.get(class_name), championship_tier)
            selected_rows = _select_world_ai_rows(
                save_name,
                needed,
                style,
                class_tier,
                championship,
                used_driver_ids,
                used_driver_names,
            )
            if len(selected_rows) < needed:
                rookies_added += _ensure_world_rookies_available(
                    save_name,
                    needed + max(1, needed - len(selected_rows)),
                    used_driver_names,
                    style,
                )
                selected_rows = _select_world_ai_rows(
                    save_name,
                    needed,
                    style,
                    class_tier,
                    championship,
                    used_driver_ids,
                    used_driver_names,
                )

            for effective_mmr, row in selected_rows:
                driver_id = str(row["id"])
                driver_name = str(row["name"])
                used_driver_ids.add(driver_id)
                used_driver_names.add(driver_name)
                standings.append(_driver_row_to_world_standing(effective_mmr, row, class_name))
        return standings, rookies_added

    if championship_prestige != world_prestige or len(standings) >= field_size:
        return standings, rookies_added

    needed = max(0, field_size - len(standings))
    if max_new_drivers is not None:
        needed = min(needed, max_new_drivers)
    selected_rows = _select_world_ai_rows(
        save_name,
        needed,
        style,
        championship_tier,
        championship,
        used_driver_ids,
        used_driver_names,
    )
    if len(selected_rows) < needed:
        rookies_added += _ensure_world_rookies_available(
            save_name,
            needed + max(1, needed - len(selected_rows)),
            used_driver_names,
            style,
        )
        selected_rows = _select_world_ai_rows(
            save_name,
            needed,
            style,
            championship_tier,
            championship,
            used_driver_ids,
            used_driver_names,
        )

    class_assignments = _world_class_assignments(championship, len(selected_rows))
    for index, (effective_mmr, row) in enumerate(selected_rows):
        driver_id = str(row["id"])
        driver_name = str(row["name"])
        used_driver_ids.add(driver_id)
        used_driver_names.add(driver_name)
        standings.append(
            _driver_row_to_world_standing(
                effective_mmr,
                row,
                class_assignments[index] if index < len(class_assignments) else "Overall",
            )
        )
    return standings, rookies_added


def _select_world_ai_rows(
    save_name: str,
    count: int,
    style: str,
    tier: int,
    championship: dict[str, Any],
    excluded_ids: set[str],
    excluded_names: set[str],
    available_rows: list[sqlite3.Row] | None = None,
) -> list[tuple[int, sqlite3.Row]]:
    rows = available_rows if available_rows is not None else _active_world_ai_rows(save_name)

    preferred_rows: list[tuple[int, str, sqlite3.Row]] = []
    unassigned_rows: list[tuple[int, str, sqlite3.Row]] = []
    overflow_rows: list[tuple[int, str, sqlite3.Row]] = []
    for row in rows:
        driver_id = str(row["id"])
        driver_name = str(row["name"])
        if driver_id in excluded_ids or driver_name in excluded_names:
            continue
        effective_mmr = int(row["mmr"])
        primary_style = str(row["primary_style"])
        candidate = (effective_mmr, driver_name, row)
        if primary_style == style:
            preferred_rows.append(candidate)
        elif primary_style in {"", "Unassigned"}:
            unassigned_rows.append(candidate)
        else:
            effective_mmr -= NON_PRIMARY_STYLE_PENALTY
            overflow_rows.append((effective_mmr, driver_name, row))

    selected = _select_mixed_style_rows(
        preferred_rows,
        unassigned_rows,
        overflow_rows,
        tier,
        count,
        style,
        str(championship.get("id", "")).strip(),
    )

    return [(effective_mmr, row) for effective_mmr, _name, row in selected[:count]]


def _active_world_ai_rows(save_name: str) -> list[sqlite3.Row]:
    with _connect(save_name) as connection:
        return connection.execute(
            """
            SELECT id, name, primary_style, mmr, last_tier, last_style, last_series_id
            FROM drivers
            WHERE is_human = 0
              AND status = 'active'
              AND current_championship IS NULL
            """
        ).fetchall()


def active_world_ai_rows(save_name: str) -> list[sqlite3.Row]:
    initialize_driver_pool(save_name)
    return _active_world_ai_rows(save_name)


def _world_class_assignments(championship: dict[str, Any], field_size: int) -> list[str]:
    class_names = _world_class_names(championship)
    if len(class_names) <= 1:
        return [class_names[0] if class_names else "Overall"] * field_size

    class_count = len(class_names)
    minimum_per_class = 8 if field_size >= class_count * 8 else max(1, field_size // class_count)
    max_per_class = max(minimum_per_class, (field_size + class_count - 1) // class_count)
    targets = {class_name: minimum_per_class for class_name in class_names}
    assigned = sum(targets.values())
    while assigned > field_size:
        reducible = [class_name for class_name, count in targets.items() if count > 1]
        if not reducible:
            break
        class_name = random.choice(reducible)
        targets[class_name] -= 1
        assigned -= 1
    for _ in range(max(0, field_size - assigned)):
        expandable = [class_name for class_name, count in targets.items() if count < max_per_class]
        if not expandable:
            break
        targets[random.choice(expandable)] += 1

    assignments: list[str] = []
    for class_name, count in targets.items():
        assignments.extend([class_name] * count)
    random.shuffle(assignments)
    return assignments[:field_size]


def _multiclass_target_counts(
    class_names: list[str],
    total_drivers: int,
    player_class: str = "",
    player_count: int = 0,
) -> dict[str, int]:
    unique_classes: list[str] = []
    seen: set[str] = set()
    for class_name in class_names:
        cleaned = str(class_name).strip()
        if cleaned and cleaned.casefold() not in seen:
            seen.add(cleaned.casefold())
            unique_classes.append(cleaned)

    if not unique_classes:
        return {player_class or "Overall": total_drivers}

    class_count = len(unique_classes)
    minimum_per_class = 8 if total_drivers >= class_count * 8 else max(1, total_drivers // class_count)
    max_per_class = max(minimum_per_class, (total_drivers + class_count - 1) // class_count)
    targets = {class_name: minimum_per_class for class_name in unique_classes}

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

    for _ in range(max(0, total_drivers - assigned)):
        expandable = [class_name for class_name, count in targets.items() if count < max_per_class]
        if not expandable:
            break
        targets[random.choice(expandable)] += 1

    return targets


def _weighted_finish_order(save_name: str, standings: list[dict[str, Any]], game: str = "iRacing") -> list[str]:
    missing_rating_names = {
        str(driver.get("name", "")).strip()
        for driver in standings
        if str(driver.get("name", "")).strip() and driver.get("sim_rating") is None
    }
    sim_ratings = _sim_rating_lookup(save_name, missing_rating_names, game)

    mmr_values = []
    for driver in standings:
        try:
            driver_name = str(driver.get("name", "")).strip()
            sim_rating = sim_ratings.get(driver_name, int(driver.get("sim_rating", driver.get("mmr", BASELINE_MMR))))
            driver["sim_rating"] = sim_rating
            mmr_values.append(sim_rating)
        except (TypeError, ValueError):
            mmr_values.append(BASELINE_MMR)
    field_average = sum(mmr_values) / max(1, len(mmr_values))

    scored_drivers = []
    for driver in standings:
        try:
            driver_name = str(driver.get("name", "")).strip()
            mmr = sim_ratings.get(driver_name, int(driver.get("sim_rating", driver.get("mmr", BASELINE_MMR))))
        except (TypeError, ValueError):
            mmr = BASELINE_MMR
        season_form = int(driver.get("season_form", 0) or 0)
        compressed_mmr = field_average + ((mmr - field_average) * WORLD_SIM_MMR_WEIGHT)
        score = compressed_mmr + season_form + random.gauss(0, WORLD_SIM_RACE_STDDEV)
        scored_drivers.append((score, str(driver.get("name", ""))))
    scored_drivers.sort(key=lambda item: item[0], reverse=True)
    return [name for _score, name in scored_drivers if name]


def world_simulated_finish_order(save_name: str, standings: list[dict[str, Any]], game: str = "iRacing") -> list[str]:
    return _weighted_finish_order(save_name, standings, game)


def _apply_world_points_by_class(standings: list[dict[str, Any]], finish_order_names: list[str]) -> None:
    standings_by_name = {str(driver.get("name", "")): driver for driver in standings}
    class_positions: dict[str, int] = {}
    for driver_name in finish_order_names:
        driver = standings_by_name.get(driver_name)
        if not driver:
            continue
        class_name = str(driver.get("class_name", "Overall")).strip() or "Overall"
        class_positions[class_name] = class_positions.get(class_name, 0) + 1
        class_pos = class_positions[class_name]
        driver["points"] = int(driver.get("points", 0)) + POINTS_MAP.get(class_pos, 0)
        if class_pos == 1:
            driver["wins"] = int(driver.get("wins", 0)) + 1


def _world_result_rows(
    standings: list[dict[str, Any]],
    finish_order_names: list[str],
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    standings_by_name = {str(driver.get("name", "")): driver for driver in standings}
    class_positions: dict[str, int] = {}
    overall_positions: dict[str, int] = {}
    result_rows: list[dict[str, Any]] = []
    for overall_pos, driver_name in enumerate(finish_order_names, 1):
        driver = standings_by_name.get(driver_name)
        if not driver:
            continue
        class_name = str(driver.get("class_name", "Overall")).strip() or "Overall"
        class_positions[class_name] = class_positions.get(class_name, 0) + 1
        class_pos = class_positions[class_name]
        overall_positions[driver_name] = overall_pos
        result_rows.append(
            {
                "overall_pos": overall_pos,
                "class_pos": class_pos,
                "driver_name": driver_name,
                "class_name": class_name,
                "points_awarded": POINTS_MAP.get(class_pos, 0),
            }
        )
    return overall_positions, result_rows


def _add_rookies(save_name: str, needed: int, style: str, excluded_names: set[str] | None = None) -> int:
    if needed <= 0:
        return 0
    from .driver_generator import generate_drivers

    used_names = _all_driver_names(save_name) | (excluded_names or set())
    created = 0
    attempts = 0
    while created < needed and attempts < needed * 10 + 50:
        attempts += 1
        for rookie in generate_drivers(needed - created + 5, exclude_name=""):
            name = str(rookie.get("name", "")).strip()
            if not name or name in used_names:
                continue
            add_driver(
                save_name,
                name=name,
                is_human=False,
                primary_style="Unassigned",
                retirement_after_seasons=_retirement_target(),
                age_range=(18, 28),
            )
            used_names.add(name)
            created += 1
            if created >= needed:
                break

    while created < needed:
        name = f"Rookie {uuid.uuid4().hex[:8].upper()}"
        add_driver(
            save_name,
            name=name,
            is_human=False,
            primary_style="Unassigned",
            retirement_after_seasons=_retirement_target(),
            age_range=(18, 28),
        )
        created += 1
    return created


def _age_all_drivers_one_year(connection: sqlite3.Connection, now: str) -> None:
    rows = connection.execute(
        """
        SELECT id, driver_age, iracing_relative_skill, ams2_general_skill, ams2_race_skill
        FROM drivers
        """
    ).fetchall()
    for row in rows:
        new_age = int(row["driver_age"] or 0) + 1
        delta = _age_skill_delta(new_age)
        iracing_skill = _clamp_rating_stat(int(row["iracing_relative_skill"] or 0) + delta)
        ams2_general_skill = _clamp_rating_stat(int(row["ams2_general_skill"] or 0) + delta)
        ams2_race_skill = round(_clamp_float_stat(float(row["ams2_race_skill"] or 0.01) + (delta * 0.01), 0.01, 1.0), 2)
        connection.execute(
            """
            UPDATE drivers
            SET driver_age = ?,
                iracing_relative_skill = ?,
                ams2_general_skill = ?,
                ams2_race_skill = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (new_age, iracing_skill, ams2_general_skill, ams2_race_skill, now, str(row["id"])),
        )


def _class_champions(standings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_class: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for driver in standings:
        class_name = str(driver.get("class_name", "Overall")).strip() or "Overall"
        by_class[class_name].append(driver)
    return [
        sorted(class_drivers, key=lambda driver: (int(driver.get("points", 0)), int(driver.get("wins", 0))), reverse=True)[0]
        for class_drivers in by_class.values()
        if class_drivers
    ]


def _update_team_reputations_for_season(
    connection: sqlite3.Connection,
    championship: dict[str, Any],
    standings: list[dict[str, Any]],
    season_year: int,
    now: str,
) -> dict[str, int]:
    game = str(championship.get("Game", "") or "Any").strip() or "Any"
    championship_id = str(championship.get("id", "")).strip() or str(championship.get("Championship", "")).strip()
    championship_name = str(championship.get("Championship", "")).strip() or "Championship"
    style = _normalize_style(str(championship.get("Style", "Sports Car")))
    by_class: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for driver in standings:
        class_name = str(driver.get("class_name", "Overall")).strip() or "Overall"
        by_class[class_name].append(driver)

    class_positions: dict[str, tuple[int, int]] = {}
    champion_ids: set[str] = set()
    for class_drivers in by_class.values():
        sorted_drivers = sorted(
            class_drivers,
            key=lambda driver: (int(driver.get("points", 0) or 0), int(driver.get("wins", 0) or 0), str(driver.get("name", ""))),
            reverse=True,
        )
        class_size = len(sorted_drivers)
        if sorted_drivers:
            champion_id = str(sorted_drivers[0].get("driver_id", "")).strip()
            if champion_id:
                champion_ids.add(champion_id)
        for position, driver in enumerate(sorted_drivers, 1):
            driver_id = str(driver.get("driver_id", "")).strip()
            if driver_id:
                class_positions[driver_id] = (position, class_size)

    team_stats: dict[str, dict[str, Any]] = {}
    for driver in standings:
        team_name = str(driver.get("team_name", "")).strip()
        if not team_name:
            continue
        team_id = str(driver.get("team_id", "")).strip() or team_name
        key = _team_key(team_id, game)
        row = team_stats.setdefault(
            key,
            {
                "team_id": team_id,
                "team_name": team_name,
                "drivers": 0,
                "points": 0,
                "wins": 0,
                "podiums": 0,
                "top_half": 0,
                "bottom_quarter": 0,
                "championships": 0,
                "classes": defaultdict(lambda: {"drivers": [], "points": 0, "wins": 0, "podiums": 0, "championships": 0}),
                "decisions": [],
            },
        )
        driver_id = str(driver.get("driver_id", "")).strip()
        driver_name = str(driver.get("name", "")).strip()
        class_name = str(driver.get("class_name", "Overall")).strip() or "Overall"
        position, class_size = class_positions.get(driver_id, (0, 0))
        wins = int(driver.get("wins", 0) or 0)
        points = int(driver.get("points", 0) or 0)
        class_stats = row["classes"][class_name]
        if driver_name:
            class_stats["drivers"].append(driver_name)
        class_stats["points"] += points
        class_stats["wins"] += wins
        row["drivers"] += 1
        row["points"] += points
        row["wins"] += wins
        if position and position <= 3:
            row["podiums"] += 1
            class_stats["podiums"] += 1
        if driver_id in champion_ids:
            row["championships"] += 1
            class_stats["championships"] += 1
        if class_size and position <= max(1, class_size // 2):
            row["top_half"] += 1
        if class_size and position > max(1, int(class_size * 0.75)):
            row["bottom_quarter"] += 1

    released_driver_ids: set[str] = set()
    _sync_team_seat_occupants_for_season(connection, championship, standings, released_driver_ids, season_year, now)

    for key, stats in team_stats.items():
        base_reputation = _safe_int(championship.get("Prestige"), 50)
        existing = connection.execute(
            "SELECT reputation, base_prestige FROM team_reputations WHERE team_key = ?",
            (key,),
        ).fetchone()
        if existing:
            current_reputation = _safe_int(existing["reputation"], base_reputation)
            base_reputation = _safe_int(existing["base_prestige"], base_reputation)
        else:
            current_reputation = base_reputation

        delta = (
            int(stats["championships"]) * 4
            + min(3, int(stats["wins"]))
            + min(2, int(stats["top_half"]))
            - min(4, int(stats["bottom_quarter"]))
        )
        if int(stats["points"]) <= 0:
            delta -= 1
        delta = max(-5, min(7, delta))
        new_reputation = max(1, min(100, current_reputation + delta))

        for class_name, class_stats in stats["classes"].items():
            driver_names = sorted(str(name) for name in class_stats["drivers"] if str(name).strip())
            connection.execute(
                """
                INSERT INTO team_season_results (
                    id,
                    team_key,
                    team_id,
                    team_name,
                    championship_id,
                    championship_name,
                    season_year,
                    game,
                    style,
                    class_name,
                    drivers,
                    driver_count,
                    points,
                    wins,
                    podiums,
                    championships,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    key,
                    stats["team_id"],
                    stats["team_name"],
                    championship_id,
                    championship_name,
                    int(season_year),
                    game,
                    style,
                    str(class_name),
                    " | ".join(driver_names),
                    len(driver_names),
                    int(class_stats["points"]),
                    int(class_stats["wins"]),
                    int(class_stats["podiums"]),
                    int(class_stats["championships"]),
                    now,
                ),
            )

        connection.execute(
            """
            INSERT INTO team_reputations (
                team_key,
                team_id,
                team_name,
                game,
                base_prestige,
                reputation,
                seasons_completed,
                championships,
                wins,
                podiums,
                last_championship,
                last_style,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(team_key) DO UPDATE SET
                team_name = excluded.team_name,
                reputation = excluded.reputation,
                seasons_completed = seasons_completed + 1,
                championships = championships + excluded.championships,
                wins = wins + excluded.wins,
                podiums = podiums + excluded.podiums,
                last_championship = excluded.last_championship,
                last_style = excluded.last_style,
                updated_at = excluded.updated_at
            """,
            (
                key,
                stats["team_id"],
                stats["team_name"],
                game,
                base_reputation,
                new_reputation,
                int(stats["championships"]),
                int(stats["wins"]),
                int(stats["podiums"]),
                championship_name,
                style,
                now,
            ),
        )

        for driver_id, driver_name, decision, reason in stats["decisions"]:
            connection.execute(
                """
                INSERT INTO team_driver_decisions (
                    id,
                    team_key,
                    team_id,
                    team_name,
                    driver_id,
                    driver_name,
                    championship_id,
                    championship_name,
                    season_year,
                    decision,
                    reason,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    key,
                    stats["team_id"],
                    stats["team_name"],
                    driver_id,
                    driver_name,
                    championship_id,
                    championship_name,
                    int(season_year),
                    decision,
                    reason,
                    now,
                ),
            )

    return {
        "teams": len(team_stats),
        "team_seasons": sum(len(stats.get("classes", {})) for stats in team_stats.values()),
    }


def _forced_retirement_ids(standings: list[dict[str, Any]], tier: int) -> list[str]:
    if tier != 1:
        return []

    ai_drivers = [
        driver
        for driver in standings
        if str(driver.get("nationality", "")).casefold() != "player"
    ]
    if not ai_drivers:
        return []

    max_forced_count = max(0, len(ai_drivers) // 2)
    if max_forced_count <= 0:
        return []
    forced_count = min(max_forced_count, random.randint(6, 12))
    sorted_drivers = sorted(
        ai_drivers,
        key=lambda driver: (int(driver.get("points", 0)), int(driver.get("wins", 0)), str(driver.get("name", ""))),
    )
    forced_ids: list[str] = []
    for driver in sorted_drivers[:forced_count]:
        driver_id = str(driver.get("driver_id", "")).strip()
        if driver_id:
            forced_ids.append(driver_id)
    return forced_ids


def _world_year(save_name: str) -> int:
    with _connect(save_name) as connection:
        row = connection.execute("SELECT value FROM world_meta WHERE key = 'world_year'").fetchone()
    if row:
        return _safe_int(row["value"], datetime.now().year)
    return datetime.now().year


def get_world_year(save_name: str) -> int:
    initialize_driver_pool(save_name)
    return _world_year(save_name)


def advance_world_year(save_name: str, years: int = 1) -> int:
    initialize_driver_pool(save_name)
    current_year = _world_year(save_name)
    new_year = current_year + max(0, int(years))
    with _connect(save_name) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO world_meta (key, value)
            VALUES ('world_year', ?)
            """,
            (str(new_year),),
        )
        connection.commit()
    return new_year


def set_world_year(save_name: str, year: int) -> int:
    initialize_driver_pool(save_name)
    target_year = int(year)
    with _connect(save_name) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO world_meta (key, value)
            VALUES ('world_year', ?)
            """,
            (str(target_year),),
        )
        connection.commit()
    return target_year


def _safe_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _active_ai_count(save_name: str, excluded_names: set[str]) -> int:
    with _connect(save_name) as connection:
        rows = connection.execute(
            """
            SELECT name FROM drivers
            WHERE is_human = 0
              AND status = 'active'
            """
        ).fetchall()
    return sum(1 for row in rows if str(row["name"]) not in excluded_names)


def _all_driver_names(save_name: str) -> set[str]:
    with _connect(save_name) as connection:
        rows = connection.execute("SELECT name FROM drivers").fetchall()
    return {str(row["name"]) for row in rows}


def _human_driver_ids(save_name: str, player_names: set[str]) -> dict[str, str]:
    if not player_names:
        return {}

    with _connect(save_name) as connection:
        rows = connection.execute(
            """
            SELECT id, name FROM drivers
            WHERE is_human = 1
              AND status = 'active'
            """
        ).fetchall()
    return {str(row["name"]): str(row["id"]) for row in rows if str(row["name"]) in player_names}


def _select_active_ai(
    save_name: str,
    count: int,
    excluded_names: set[str],
    style: str,
    tier: int,
    championship: dict[str, Any],
) -> list[dict[str, Any]]:
    if count <= 0:
        return []

    with _connect(save_name) as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                name,
                primary_style,
                mmr,
                last_tier,
                last_style,
                last_series_id
            FROM drivers
            WHERE is_human = 0
              AND status = 'active'
            """
        ).fetchall()

    preferred_rows: list[tuple[int, str, sqlite3.Row]] = []
    unassigned_rows: list[tuple[int, str, sqlite3.Row]] = []
    overflow_rows: list[tuple[int, str, sqlite3.Row]] = []
    for row in rows:
        name = str(row["name"])
        if name in excluded_names:
            continue
        rating = int(row["mmr"])
        effective_mmr = rating
        primary_style = str(row["primary_style"])
        candidate = (effective_mmr, name, row)
        if primary_style == style:
            preferred_rows.append(candidate)
        elif primary_style in {"", "Unassigned"}:
            unassigned_rows.append(candidate)
        else:
            effective_mmr -= NON_PRIMARY_STYLE_PENALTY
            overflow_rows.append((effective_mmr, name, row))

    selected_drivers = _select_mixed_style_rows(
        preferred_rows,
        unassigned_rows,
        overflow_rows,
        tier,
        count,
        style,
        str(championship.get("id", "")).strip(),
    )

    return [
        {
            "driver_id": str(row["id"]),
            "name": str(row["name"]),
            "nationality": "AI",
            "skill": _skill_from_rating(effective_mmr),
            "points": 0,
            "wins": 0,
            "podiums": 0,
            "mmr": effective_mmr,
            "primary_style": str(row["primary_style"]),
        }
        for effective_mmr, _name, row in selected_drivers
    ]


def _tier_slice(
    ranked_drivers: list[tuple[int, str, sqlite3.Row]],
    tier: int,
    count: int,
) -> list[tuple[int, str, sqlite3.Row]]:
    if count <= 0 or not ranked_drivers:
        return []
    return ranked_drivers[:count]


def _tier_band_slice(
    ranked_drivers: list[tuple[int, str, sqlite3.Row]],
    tier: int,
    count: int,
) -> list[tuple[int, str, sqlite3.Row]]:
    if count <= 0 or not ranked_drivers:
        return []

    normalized_tier = max(1, min(5, tier))
    total = len(ranked_drivers)
    band_size = max(count, total // 5, 1)
    band_start = round((5 - normalized_tier) * total / 5)
    band_end = min(total, band_start + band_size)
    selected = ranked_drivers[band_start:band_end]

    above = list(reversed(ranked_drivers[:band_start]))
    below = ranked_drivers[band_end:]
    while len(selected) < count and (above or below):
        if below:
            selected.append(below.pop(0))
        if len(selected) >= count:
            break
        if above:
            selected.append(above.pop(0))

    return selected[:count]


def _series_family_id(series_id: str) -> str:
    cleaned = str(series_id).strip()
    if not cleaned:
        return ""
    if "-AI-" in cleaned:
        return cleaned.split("-AI-", 1)[0]
    return cleaned


def _movement_bonus(row: sqlite3.Row, target_style: str, target_tier: int, target_series_id: str) -> int:
    bonus = 0
    last_tier = _safe_int(row["last_tier"], 0) if "last_tier" in row.keys() else 0
    last_style = _normalize_style(str(row["last_style"])) if str(row["last_style"] or "").strip() else ""
    last_series_id = str(row["last_series_id"] or "").strip()
    target_family = _series_family_id(target_series_id)
    last_family = _series_family_id(last_series_id)

    if last_tier > 0:
        tier_gap = abs(target_tier - last_tier)
        if tier_gap == 0:
            bonus += 90
        elif tier_gap == 1:
            bonus += 35
        else:
            bonus -= 60 * (tier_gap - 1) + 25

        if target_tier < last_tier:
            bonus -= 10

    if last_style:
        if last_style == target_style:
            bonus += 80
        else:
            bonus -= 55

    if last_family and target_family:
        if last_family == target_family:
            bonus += 85
            if last_series_id == target_series_id:
                bonus += 25
        elif last_tier == target_tier and last_style == target_style:
            bonus += random.randint(-10, 20)

    primary_style = str(row["primary_style"] or "").strip()
    if primary_style == target_style:
        bonus += 40
    elif primary_style not in {"", "Unassigned"}:
        bonus -= 10

    return bonus


def _crossover_candidate_score(
    candidate: tuple[int, str, sqlite3.Row],
    target_style: str,
    target_tier: int,
    target_series_id: str,
) -> int:
    effective_mmr, _name, row = candidate
    score = effective_mmr + _movement_bonus(row, target_style, target_tier, target_series_id)
    last_tier = _safe_int(row["last_tier"], 0) if "last_tier" in row.keys() else 0
    if last_tier and abs(last_tier - target_tier) <= 1:
        score += 40
    if str(row["primary_style"] or "").strip() not in {"", "Unassigned", target_style}:
        score += STORYLINE_CROSSOVER_BONUS
    return score


def _select_mixed_style_rows(
    preferred_rows: list[tuple[int, str, sqlite3.Row]],
    unassigned_rows: list[tuple[int, str, sqlite3.Row]],
    overflow_rows: list[tuple[int, str, sqlite3.Row]],
    tier: int,
    count: int,
    target_style: str,
    target_series_id: str,
    draft_mode: str = "world",
) -> list[tuple[int, str, sqlite3.Row]]:
    slice_picker = _tier_slice if draft_mode == "world" else _tier_band_slice

    def prepare(bucket: list[tuple[int, str, sqlite3.Row]]) -> list[tuple[int, str, sqlite3.Row]]:
        random.shuffle(bucket)
        bucket.sort(
            key=lambda item: (
                -item[0],
                item[1],
            )
        )
        return bucket

    preferred_rows = prepare(preferred_rows)
    unassigned_rows = prepare(unassigned_rows)
    overflow_rows = prepare(overflow_rows)

    selected: list[tuple[int, str, sqlite3.Row]] = []
    selected.extend(slice_picker(preferred_rows, tier, count))
    if len(selected) < count:
        selected.extend(slice_picker(unassigned_rows, tier, count - len(selected)))

    if len(selected) >= count and overflow_rows and count >= STORYLINE_CROSSOVER_MIN_FIELD:
        crossover_chance = 0.30 if tier == 1 else 0.24 if tier in {2, 3} else 0.15
        if random.random() < crossover_chance:
            selected_ids = {str(row["id"]) for _score, _name, row in selected if "id" in row.keys()}
            remaining_overflow = [item for item in overflow_rows if str(item[2]["id"]) not in selected_ids]
            remaining_overflow.sort(
                key=lambda item: -_crossover_candidate_score(item, target_style, tier, target_series_id)
            )
            crossover_pick = remaining_overflow[:1]
            if crossover_pick:
                selected = selected[: max(0, count - 1)] + crossover_pick

    return selected[:count]


def _normalize_style(style: str) -> str:
    normalized = style.strip().casefold()
    if normalized == "oval":
        return "Oval"
    if normalized == "20r/80o":
        return "Oval"
    if normalized in {"open wheel", "open-wheel", "openwheel"}:
        return "Open Wheel"
    if normalized == "80r/20o":
        return "Open Wheel"
    if normalized in {"rallycross", "rally cross"}:
        return "Rallycross"
    return "Sports Car"


def _load_team_rows() -> list[dict[str, str]]:
    global _TEAMS_CACHE
    if not TEAMS_CSV.exists():
        return []
    if _TEAMS_CACHE is None:
        with TEAMS_CSV.open(newline="", encoding="utf-8") as file_obj:
            _TEAMS_CACHE = [dict(row) for row in csv.DictReader(file_obj)]
    return [dict(row) for row in _TEAMS_CACHE]


def _team_row_id(row: dict[str, Any]) -> str:
    return (
        str(row.get("Team_ID", "")).strip()
        or str(row.get("ID", "")).strip()
        or str(row.get("team_id", "")).strip()
        or str(row.get("Team", "")).strip()
        or str(row.get("team_name", "")).strip()
        or "Independent"
    )


def _team_row_name(row: dict[str, Any]) -> str:
    return str(row.get("Team", "") or row.get("team_name", "") or row.get("team_id", "") or "Independent").strip()


def _team_game(row: dict[str, Any], fallback: str = "") -> str:
    return str(row.get("Game", "") or row.get("game", "") or fallback or "Any").strip() or "Any"


def _team_key(team_id: str, game: str) -> str:
    normalized_game = str(game or "Any").strip().casefold() or "any"
    normalized_id = str(team_id or "Independent").strip().casefold() or "independent"
    return f"{normalized_game}|{normalized_id}"


def _team_row_colors(row: dict[str, Any]) -> str:
    colors = []
    for key in ("Color 1", "Color 2", "Color 3", "color1", "color2", "color3"):
        value = str(row.get(key, "")).strip().upper().lstrip("#")
        if re.fullmatch(r"[0-9A-F]{6}", value):
            colors.append(value)
    return ",".join(colors[:3])


TEAM_PERSONALITIES = (
    "Professional",
    "Aggressive",
    "Development",
    "Data-Driven",
    "Underdog",
    "Prestige",
    "Family",
)


def _team_row_personality_value(row: dict[str, Any]) -> str:
    for key in ("Personality", "Team Personality", "team_personality", "personality"):
        value = str(row.get(key, "")).strip()
        if value:
            return value
    return ""


def _team_row_personality(row: dict[str, Any]) -> str:
    value = _team_row_personality_value(row)
    if value:
        return value
    return _team_personality_for_identity(_team_row_id(row), _team_row_name(row), _team_game(row))


def _team_personality_for_identity(team_id: str, team_name: str, game: str = "") -> str:
    target_id = str(team_id).strip()
    target_name = str(team_name).strip().casefold()
    target_game = str(game).strip().casefold()
    for row in _load_team_rows():
        row_id = _team_row_id(row)
        row_name = _team_row_name(row)
        row_game = _team_game(row).strip().casefold()
        if target_game and row_game not in {target_game, "any"}:
            continue
        if (target_id and row_id == target_id) or (target_name and row_name.casefold() == target_name):
            value = _team_row_personality_value(row)
            if value:
                return value
            break

    seed_value = _stable_seed(target_id, target_name, target_game, "team-personality")
    return TEAM_PERSONALITIES[seed_value % len(TEAM_PERSONALITIES)]


def team_personality_for_identity(team_id: str, team_name: str, game: str = "") -> str:
    return _team_personality_for_identity(team_id, team_name, game)


def _team_colors_for_identity(team_id: str, team_name: str, game: str = "") -> str:
    target_id = str(team_id).strip()
    target_name = str(team_name).strip().casefold()
    target_game = str(game).strip().casefold()
    for row in _load_team_rows():
        row_id = _team_row_id(row)
        row_name = _team_row_name(row)
        row_game = _team_game(row).strip().casefold()
        if target_game and row_game not in {target_game, "any"}:
            continue
        if (target_id and row_id == target_id) or (target_name and row_name.casefold() == target_name):
            colors = _team_row_colors(row)
            if colors:
                return colors
    return ""


def team_colors_for_identity(team_id: str, team_name: str, game: str = "") -> str:
    return _team_colors_for_identity(team_id, team_name, game)


def _sync_team_reputations_from_csv(connection: sqlite3.Connection) -> None:
    now = _now()
    for row in _load_team_rows():
        team_id = _team_row_id(row)
        team_name = _team_row_name(row)
        game = _team_game(row)
        base_prestige = _safe_int(row.get("Prestige"), 50)
        key = _team_key(team_id, game)
        connection.execute(
            """
            INSERT INTO team_reputations (
                team_key,
                team_id,
                team_name,
                game,
                base_prestige,
                reputation,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(team_key) DO UPDATE SET
                team_name = excluded.team_name,
                base_prestige = excluded.base_prestige
            """,
            (key, team_id, team_name, game, base_prestige, base_prestige, now),
        )


def _sync_team_totals_from_history(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        """
        SELECT
            team_key,
            team_id,
            team_name,
            game,
            COUNT(*) AS seasons_completed,
            SUM(championships) AS championships,
            SUM(wins) AS wins,
            SUM(podiums) AS podiums
        FROM team_season_results
        GROUP BY team_key, team_id, team_name, game
        """
    ).fetchall()
    now = _now()
    for row in rows:
        latest = connection.execute(
            """
            SELECT championship_name, style
            FROM team_season_results
            WHERE team_key = ?
            ORDER BY season_year DESC, created_at DESC
            LIMIT 1
            """,
            (row["team_key"],),
        ).fetchone()
        existing = connection.execute(
            """
            SELECT base_prestige, reputation, seasons_completed, championships, wins, podiums
            FROM team_reputations
            WHERE team_key = ?
            """,
            (row["team_key"],),
        ).fetchone()
        base_prestige = _safe_int(existing["base_prestige"] if existing else None, 50)
        aggregate_seasons = _safe_int(row["seasons_completed"], 0)
        aggregate_titles = _safe_int(row["championships"], 0)
        aggregate_wins = _safe_int(row["wins"], 0)
        aggregate_podiums = _safe_int(row["podiums"], 0)
        current_reputation = _safe_int(existing["reputation"] if existing else None, base_prestige)
        rebuilt_reputation = max(
            1,
            min(
                100,
                base_prestige
                + min(24, aggregate_titles * 3)
                + min(18, aggregate_wins // 3)
                + min(10, aggregate_podiums // 8)
                - min(8, max(0, aggregate_seasons - aggregate_podiums) // 20),
            ),
        )
        connection.execute(
            """
            INSERT INTO team_reputations (
                team_key,
                team_id,
                team_name,
                game,
                base_prestige,
                reputation,
                seasons_completed,
                championships,
                wins,
                podiums,
                last_championship,
                last_style,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(team_key) DO UPDATE SET
                team_name = excluded.team_name,
                reputation = CASE
                    WHEN seasons_completed = 0 THEN excluded.reputation
                    ELSE MAX(reputation, excluded.reputation)
                END,
                seasons_completed = MAX(seasons_completed, excluded.seasons_completed),
                championships = MAX(championships, excluded.championships),
                wins = MAX(wins, excluded.wins),
                podiums = MAX(podiums, excluded.podiums),
                last_championship = COALESCE(excluded.last_championship, last_championship),
                last_style = COALESCE(excluded.last_style, last_style),
                updated_at = excluded.updated_at
            """,
            (
                row["team_key"],
                row["team_id"],
                row["team_name"],
                row["game"],
                base_prestige,
                max(current_reputation, rebuilt_reputation),
                aggregate_seasons,
                aggregate_titles,
                aggregate_wins,
                aggregate_podiums,
                latest["championship_name"] if latest else None,
                latest["style"] if latest else None,
                now,
            ),
        )


def _team_reputation_value(save_name: str, team: dict[str, Any], fallback_game: str = "") -> int:
    initialize_driver_pool(save_name)
    team_id = _team_row_id(team)
    game = _team_game(team, fallback_game)
    team_name = _team_row_name(team)
    with _connect(save_name) as connection:
        row = connection.execute(
            """
            SELECT reputation
            FROM team_reputations
            WHERE team_key = ?
               OR (team_id = ? AND (game = ? OR game = 'Any'))
               OR team_name = ?
            ORDER BY
                CASE WHEN team_key = ? THEN 0 ELSE 1 END,
                game DESC
            LIMIT 1
            """,
            (_team_key(team_id, game), team_id, game, team_name, _team_key(team_id, game)),
        ).fetchone()
    if row:
        return _safe_int(row["reputation"], _safe_int(team.get("Prestige"), 50))
    return _safe_int(team.get("Prestige"), 50)


def active_driver_rows_for_selection(save_name: str) -> list[sqlite3.Row]:
    initialize_driver_pool(save_name)
    with _connect(save_name) as connection:
        return connection.execute(
            """
            SELECT name, is_human, primary_style, mmr, career_starts, current_championship
            FROM drivers
            WHERE status = 'active'
            """
        ).fetchall()


def existing_team_seats_by_championship(save_name: str) -> dict[tuple[str, str], list[dict[str, Any]]]:
    initialize_driver_pool(save_name)
    with _connect(save_name) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM team_championship_seats
            WHERE status = 'active'
            ORDER BY team_prestige DESC, team_name ASC, team_seat ASC, seat_number ASC
            """
        ).fetchall()
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["championship_id"]), str(row["game"]))].append(_team_seat_row_to_plan(row))
    return grouped


def _team_reputation_from_map(
    reputations: dict[str, int] | None,
    team: dict[str, Any],
    fallback_game: str,
    fallback: int = 50,
) -> int:
    if not reputations:
        return int(fallback)
    team_id = _team_row_id(team)
    team_key = _team_key(team_id, _team_game(team, fallback_game))
    team_name = _team_row_name(team)
    return (
        reputations.get(team_key)
        or reputations.get(team_id)
        or reputations.get(team_name)
        or int(fallback)
    )


def _eligible_teams_for_championship(championship: dict[str, Any]) -> list[dict[str, str]]:
    championship_style = _normalize_style(str(championship.get("Style", "Sports Car")))
    championship_tier = _safe_int(championship.get("_field_tier", championship.get("Tier")), 1)
    championship_game = str(championship.get("Game", "")).strip().casefold()

    eligible: list[dict[str, str]] = []
    fallback: list[dict[str, str]] = []
    for row in _load_team_rows():
        row_game = str(row.get("Game", "")).strip().casefold()
        if row_game and championship_game and row_game != championship_game:
            continue
        low_tier = _safe_int(row.get("Low_Tier", row.get("Min_Tier")), 1)
        max_tier = _safe_int(row.get("Max_Tier", row.get("High_Tier")), 5)
        if championship_tier < low_tier or championship_tier > max_tier:
            continue
        base_style = str(row.get("Base_Style", "ANY")).strip()
        if not base_style or base_style.casefold() == "any":
            fallback.append(row)
            continue
        if _normalize_style(base_style) == championship_style:
            eligible.append(row)
    return eligible or fallback


def _build_team_seat_plan(field_size: int, championship: dict[str, Any]) -> list[dict[str, Any]]:
    eligible = _eligible_teams_for_championship(championship)
    if not eligible or field_size <= 0:
        return []

    seat_plan: list[dict[str, Any]] = []
    team_occurrences: dict[str, int] = defaultdict(int)
    available = list(eligible)
    championship_game = str(championship.get("Game", "") or "Any").strip() or "Any"
    while len(seat_plan) < field_size:
        if not available:
            available = list(eligible)
        weights = [max(1, _safe_int(team.get("Prestige"), 50)) for team in available]
        chosen_index = random.choices(range(len(available)), weights=weights, k=1)[0]
        team = dict(available.pop(chosen_index))
        seats_for_team = 2 if (len(seat_plan) + 1 < field_size and random.random() < 0.35) else 1
        for _ in range(seats_for_team):
            if len(seat_plan) >= field_size:
                break
            team_id = str(team.get("Team_ID", "")).strip() or str(team.get("ID", "")).strip() or str(team.get("Team", "")).strip()
            team_occurrences[team_id] += 1
            seat_plan.append(
                {
                    "team_id": team_id,
                    "team_key": _team_key(team_id, _team_game(team, championship_game)),
                    "team_name": str(team.get("Team", "")).strip() or "Independent",
                    "team_seat": 1 if team_occurrences[team_id] % 2 == 1 else 2,
                    "team_prestige": _safe_int(team.get("Prestige"), 50),
                    "team_colors": _team_row_colors(team),
                    "team_personality": _team_row_personality(team),
                }
            )
    return seat_plan


def _championship_team_seat_identity(championship: dict[str, Any]) -> tuple[str, str, str, str]:
    championship_name = _championship_pool_display_name(championship)
    championship_id = (
        str(championship.get("Championship_ID", "")).strip()
        or str(championship.get("id", "")).strip()
        or championship_name
    )
    game = str(championship.get("Game", "") or "Any").strip() or "Any"
    style = _normalize_style(str(championship.get("Style", "Sports Car")))
    return championship_id, championship_name, game, style


def _team_seat_row_to_plan(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "team_id": str(row["team_id"]),
        "team_key": str(row["team_key"]),
        "team_name": str(row["team_name"]),
        "seat_number": _safe_int(row["seat_number"], 1),
        "team_seat": _safe_int(row["team_seat"], 1),
        "team_prestige": _safe_int(row["team_prestige"], 50),
        "driver_id": str(row["driver_id"] or "").strip(),
        "driver_name": str(row["driver_name"] or "").strip(),
        "class_name": str(row["class_name"] or "").strip() or "Overall",
    }


def _record_team_seat_history(
    connection: sqlite3.Connection,
    *,
    team_key: str,
    team_id: str,
    team_name: str,
    championship_id: str,
    championship_name: str,
    game: str,
    style: str,
    seat_number: int,
    team_seat: int,
    event_type: str,
    season_year: int | None,
    reason: str,
    now: str,
) -> None:
    connection.execute(
        """
        INSERT INTO team_seat_history (
            id,
            team_key,
            team_id,
            team_name,
            championship_id,
            championship_name,
            game,
            style,
            seat_number,
            team_seat,
            event_type,
            season_year,
            reason,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            team_key,
            team_id,
            team_name,
            championship_id,
            championship_name,
            game,
            style,
            int(seat_number),
            int(team_seat),
            event_type,
            season_year,
            reason,
            now,
        ),
    )


def _team_seat_history_exists(
    connection: sqlite3.Connection,
    championship_id: str,
    game: str,
    seat_number: int,
    event_type: str,
    season_year: int | None = None,
) -> bool:
    if season_year is None:
        row = connection.execute(
            """
            SELECT 1
            FROM team_seat_history
            WHERE championship_id = ?
              AND game = ?
              AND seat_number = ?
              AND event_type = ?
            LIMIT 1
            """,
            (championship_id, game, int(seat_number), event_type),
        ).fetchone()
    else:
        row = connection.execute(
            """
            SELECT 1
            FROM team_seat_history
            WHERE championship_id = ?
              AND game = ?
              AND seat_number = ?
              AND event_type = ?
              AND season_year = ?
            LIMIT 1
            """,
            (championship_id, game, int(seat_number), event_type, int(season_year)),
        ).fetchone()
    return row is not None


def _team_championship_counts(connection: sqlite3.Connection) -> dict[str, int]:
    rows = connection.execute(
        """
        SELECT team_key, COUNT(DISTINCT championship_id) AS championship_count
        FROM team_championship_seats
        WHERE status = 'active'
        GROUP BY team_key
        """
    ).fetchall()
    return {str(row["team_key"]): _safe_int(row["championship_count"], 0) for row in rows}


def _recent_team_seat_score(
    connection: sqlite3.Connection,
    seat: sqlite3.Row,
    championship: dict[str, Any],
) -> int:
    team_key = str(seat["team_key"])
    championship_id = str(seat["championship_id"])
    prestige = _safe_int(championship.get("Prestige"), 1)
    reputation_row = connection.execute(
        "SELECT reputation FROM team_reputations WHERE team_key = ?",
        (team_key,),
    ).fetchone()
    reputation = _safe_int(reputation_row["reputation"], _safe_int(seat["team_prestige"], 50)) if reputation_row else _safe_int(seat["team_prestige"], 50)
    recent = connection.execute(
        """
        SELECT points, wins, championships
        FROM team_season_results
        WHERE team_key = ?
          AND championship_id = ?
        ORDER BY season_year DESC
        LIMIT 2
        """,
        (team_key, championship_id),
    ).fetchall()
    points = sum(_safe_int(row["points"], 0) for row in recent)
    wins = sum(_safe_int(row["wins"], 0) for row in recent)
    titles = sum(_safe_int(row["championships"], 0) for row in recent)
    prestige_pressure = max(0, (prestige * 10) - reputation)
    performance_bonus = min(20, points // 25) + min(8, wins * 2) + min(12, titles * 6)
    return reputation + performance_bonus - prestige_pressure


def _candidate_team_for_open_seat(
    connection: sqlite3.Connection,
    save_name: str,
    championship: dict[str, Any],
    current_team_key: str,
    protected_team_keys: set[str],
    championship_counts: dict[str, int],
    max_championships: int = 6,
) -> dict[str, Any] | None:
    championship_game = str(championship.get("Game", "") or "Any").strip() or "Any"
    championship_id = str(championship.get("id", "")).strip() or str(championship.get("Championship", "")).strip()
    championship_prestige = _safe_int(championship.get("Prestige"), 1)
    candidates: list[tuple[int, dict[str, Any]]] = []
    for team in _eligible_teams_for_championship(championship):
        team_id = _team_row_id(team)
        team_key = _team_key(team_id, _team_game(team, championship_game))
        if not team_key or team_key == current_team_key or team_key in protected_team_keys:
            continue
        if championship_counts.get(team_key, 0) >= max_championships:
            continue
        already_in_championship = connection.execute(
            """
            SELECT 1
            FROM team_championship_seats
            WHERE team_key = ?
              AND championship_id = ?
              AND status = 'active'
            LIMIT 1
            """,
            (team_key, championship_id),
        ).fetchone()
        if already_in_championship:
            continue
        team_reputation = _team_reputation_value(save_name, team, championship_game)
        team_prestige = _safe_int(team.get("Prestige"), 50)
        prestige_fit = max(0, 100 - abs((championship_prestige * 10) - team_reputation))
        score = team_reputation + prestige_fit + random.randint(0, 12) - max(0, championship_counts.get(team_key, 0) - 2) * 8
        candidates.append(
            (
                score,
                {
                    "team_id": team_id,
                    "team_key": team_key,
                    "team_name": _team_row_name(team),
                    "team_prestige": team_prestige,
                    "team_reputation": team_reputation,
                },
            )
        )

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def run_offseason_team_seat_market(
    save_name: str,
    championships: list[dict[str, Any]],
    protected_team_keys: set[str] | None = None,
) -> dict[str, int]:
    initialize_driver_pool(save_name)
    protected = {str(value).strip() for value in (protected_team_keys or set()) if str(value).strip()}
    championship_by_id = {
        str(championship.get("id", "")).strip() or str(championship.get("Championship", "")).strip(): dict(championship)
        for championship in championships
    }
    now = _now()
    season_year = _world_year(save_name)
    summary = {"evaluated": 0, "lost": 0, "sold": 0, "acquired": 0, "new_teams": 0}

    with _connect(save_name) as connection:
        seats = connection.execute(
            """
            SELECT *
            FROM team_championship_seats
            WHERE status = 'active'
            ORDER BY last_active_year ASC, championship_name ASC, seat_number ASC
            """
        ).fetchall()
        if not seats:
            return summary

        vulnerable: list[tuple[int, sqlite3.Row, dict[str, Any]]] = []
        for seat in seats:
            team_key = str(seat["team_key"])
            championship_id = str(seat["championship_id"])
            championship = championship_by_id.get(championship_id)
            if not championship or team_key in protected:
                continue
            summary["evaluated"] += 1
            score = _recent_team_seat_score(connection, seat, championship)
            championship_prestige = _safe_int(championship.get("Prestige"), 1)
            threshold = 46 + (championship_prestige * 4)
            if score < threshold:
                vulnerable.append((score, seat, championship))

        if not vulnerable:
            connection.commit()
            return summary

        random.shuffle(vulnerable)
        vulnerable.sort(key=lambda item: item[0])
        churn_limit = max(1, min(12, round(len(seats) * 0.12)))
        championship_counts = _team_championship_counts(connection)

        for _score, seat, championship in vulnerable[:churn_limit]:
            old_team_key = str(seat["team_key"])
            old_team_id = str(seat["team_id"])
            old_team_name = str(seat["team_name"])
            championship_id = str(seat["championship_id"])
            championship_name = str(seat["championship_name"])
            game = str(seat["game"])
            style = str(seat["style"])
            seat_number = _safe_int(seat["seat_number"], 1)
            team_seat = _safe_int(seat["team_seat"], 1)

            buyer = _candidate_team_for_open_seat(
                connection,
                save_name,
                championship,
                old_team_key,
                protected,
                championship_counts,
            )
            if not buyer:
                continue

            event_type = "sold" if _safe_int(buyer.get("team_reputation"), 50) >= _safe_int(seat["team_prestige"], 50) else "lost"
            old_reason = "Seat sold after weak recent performance" if event_type == "sold" else "Seat lost after weak recent performance"
            _record_team_seat_history(
                connection,
                team_key=old_team_key,
                team_id=old_team_id,
                team_name=old_team_name,
                championship_id=championship_id,
                championship_name=championship_name,
                game=game,
                style=style,
                seat_number=seat_number,
                team_seat=team_seat,
                event_type=event_type,
                season_year=season_year,
                reason=old_reason,
                now=now,
            )
            _record_team_seat_history(
                connection,
                team_key=str(buyer["team_key"]),
                team_id=str(buyer["team_id"]),
                team_name=str(buyer["team_name"]),
                championship_id=championship_id,
                championship_name=championship_name,
                game=game,
                style=style,
                seat_number=seat_number,
                team_seat=team_seat,
                event_type="acquired",
                season_year=season_year,
                reason=f"Acquired seat from {old_team_name}",
                now=now,
            )
            connection.execute(
                """
                UPDATE team_championship_seats
                SET team_key = ?,
                    team_id = ?,
                    team_name = ?,
                    team_prestige = ?,
                    driver_id = NULL,
                    driver_name = NULL,
                    class_name = NULL,
                    acquired_year = ?,
                    last_active_year = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    str(buyer["team_key"]),
                    str(buyer["team_id"]),
                    str(buyer["team_name"]),
                    _safe_int(buyer.get("team_prestige"), 50),
                    season_year,
                    season_year,
                    now,
                    str(seat["id"]),
                ),
            )
            championship_counts[old_team_key] = max(0, championship_counts.get(old_team_key, 1) - 1)
            championship_counts[str(buyer["team_key"])] = championship_counts.get(str(buyer["team_key"]), 0) + 1
            summary[event_type] += 1
            summary["acquired"] += 1
            if championship_counts[str(buyer["team_key"])] == 1:
                summary["new_teams"] += 1

        connection.commit()
    return summary


def _build_persistent_team_seat_plan(
    save_name: str,
    field_size: int,
    championship: dict[str, Any],
) -> list[dict[str, Any]]:
    if field_size <= 0:
        return []

    initialize_driver_pool(save_name)
    championship_id, championship_name, game, style = _championship_team_seat_identity(championship)
    now = _now()
    year = _world_year(save_name)

    with _connect(save_name) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM team_championship_seats
            WHERE championship_id = ?
              AND game = ?
              AND status = 'active'
            ORDER BY seat_number
            """,
            (championship_id, game),
        ).fetchall()
        seat_plan = [_team_seat_row_to_plan(row) for row in rows[:field_size]]

        if len(rows) < field_size:
            existing_team_counts: dict[str, int] = defaultdict(int)
            for row in rows:
                existing_team_counts[str(row["team_id"])] += 1

            next_seat_number = len(rows) + 1
            additions = _build_team_seat_plan(field_size - len(rows), championship)
            for seat in additions:
                team_id = str(seat.get("team_id", "")).strip()
                existing_team_counts[team_id] += 1
                team_seat = 1 if existing_team_counts[team_id] % 2 == 1 else 2
                seat["team_seat"] = team_seat
                team_key = str(seat.get("team_key", "")).strip()
                team_name = str(seat.get("team_name", "")).strip() or "Independent"
                connection.execute(
                    """
                    INSERT INTO team_championship_seats (
                        id,
                        championship_id,
                        championship_name,
                        game,
                        style,
                        seat_number,
                        team_key,
                        team_id,
                        team_name,
                        team_seat,
                        team_prestige,
                        driver_id,
                        driver_name,
                        class_name,
                        acquired_year,
                        last_active_year,
                        status,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?, 'active', ?, ?)
                    ON CONFLICT(championship_id, game, seat_number) DO UPDATE SET
                        team_key = excluded.team_key,
                        team_id = excluded.team_id,
                        team_name = excluded.team_name,
                        team_seat = excluded.team_seat,
                        team_prestige = excluded.team_prestige,
                        last_active_year = excluded.last_active_year,
                        status = 'active',
                        updated_at = excluded.updated_at
                    """,
                    (
                        str(uuid.uuid4()),
                        championship_id,
                        championship_name,
                        game,
                        style,
                        next_seat_number,
                        team_key,
                        team_id,
                        team_name,
                        team_seat,
                        _safe_int(seat.get("team_prestige"), 50),
                        year,
                        year,
                        now,
                        now,
                    ),
                )
                if not _team_seat_history_exists(connection, championship_id, game, next_seat_number, "acquired"):
                    _record_team_seat_history(
                        connection,
                        team_key=team_key,
                        team_id=team_id,
                        team_name=team_name,
                        championship_id=championship_id,
                        championship_name=championship_name,
                        game=game,
                        style=style,
                        seat_number=next_seat_number,
                        team_seat=team_seat,
                        event_type="acquired",
                        season_year=year,
                        reason="Initial championship seat assignment",
                        now=now,
                    )
                if len(seat_plan) < field_size:
                    seat_plan.append(dict(seat))
                next_seat_number += 1

        existing_acquired_seats = {
            _safe_int(history_row["seat_number"], 0)
            for history_row in connection.execute(
                """
                SELECT seat_number
                FROM team_seat_history
                WHERE championship_id = ?
                  AND game = ?
                  AND event_type = 'acquired'
                """,
                (championship_id, game),
            ).fetchall()
        }
        for row in rows[:field_size]:
            seat_number = _safe_int(row["seat_number"], 0)
            if seat_number and seat_number not in existing_acquired_seats:
                _record_team_seat_history(
                    connection,
                    team_key=str(row["team_key"]),
                    team_id=str(row["team_id"]),
                    team_name=str(row["team_name"]),
                    championship_id=championship_id,
                    championship_name=championship_name,
                    game=game,
                    style=style,
                    seat_number=seat_number,
                    team_seat=_safe_int(row["team_seat"], 1),
                    event_type="acquired",
                    season_year=_safe_int(row["acquired_year"], year),
                    reason="Existing championship seat backfilled into ownership history",
                    now=now,
                )

        connection.execute(
            """
            UPDATE team_championship_seats
            SET last_active_year = ?,
                updated_at = ?
            WHERE championship_id = ?
              AND game = ?
              AND status = 'active'
              AND seat_number <= ?
            """,
            (year, now, championship_id, game, field_size),
        )
        connection.commit()

    return seat_plan[:field_size]


def _sync_team_seat_occupants_for_season(
    connection: sqlite3.Connection,
    championship: dict[str, Any],
    standings: list[dict[str, Any]],
    released_driver_ids: set[str],
    season_year: int,
    now: str,
) -> None:
    championship_id, championship_name, game, style = _championship_team_seat_identity(championship)
    seat_rows = connection.execute(
        """
        SELECT id, seat_number, team_key, team_id, team_name, team_seat
        FROM team_championship_seats
        WHERE championship_id = ?
          AND game = ?
          AND status = 'active'
        ORDER BY seat_number
        """,
        (championship_id, game),
    ).fetchall()
    if not seat_rows:
        return

    seats_by_team: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in seat_rows:
        seats_by_team[str(row["team_key"])].append(row)

    drivers_by_team: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for driver in standings:
        team_key = str(driver.get("team_key", "")).strip()
        if team_key:
            drivers_by_team[team_key].append(driver)

    for team_key, team_seats in seats_by_team.items():
        assigned_drivers = sorted(
            drivers_by_team.get(team_key, []),
            key=lambda driver: (
                _safe_int(driver.get("team_seat"), 99),
                -int(driver.get("points", 0) or 0),
                -int(driver.get("wins", 0) or 0),
                str(driver.get("name", "")),
            ),
        )
        for seat_row in team_seats:
            seat_number = _safe_int(seat_row["seat_number"], 0)
            if seat_number and not _team_seat_history_exists(
                connection,
                championship_id,
                game,
                seat_number,
                "active_season",
                season_year,
            ):
                _record_team_seat_history(
                    connection,
                    team_key=team_key,
                    team_id=str(seat_row["team_id"]),
                    team_name=str(seat_row["team_name"]),
                    championship_id=championship_id,
                    championship_name=championship_name,
                    game=game,
                    style=style,
                    seat_number=seat_number,
                    team_seat=_safe_int(seat_row["team_seat"], 1),
                    event_type="active_season",
                    season_year=season_year,
                    reason="Competed in this championship seat",
                    now=now,
                )
        for seat_row, driver in zip(team_seats, assigned_drivers):
            connection.execute(
                """
                UPDATE team_championship_seats
                SET championship_name = ?,
                    style = ?,
                    driver_id = ?,
                    driver_name = ?,
                    class_name = ?,
                    last_active_year = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    championship_name,
                    style,
                    str(driver.get("driver_id", "")).strip() or None,
                    str(driver.get("name", "")).strip() or None,
                    str(driver.get("class_name", "Overall")).strip() or "Overall",
                    int(season_year),
                    now,
                    str(seat_row["id"]),
                ),
            )
        if len(assigned_drivers) < len(team_seats):
            for seat_row in team_seats[len(assigned_drivers):]:
                connection.execute(
                    """
                    UPDATE team_championship_seats
                    SET championship_name = ?,
                        style = ?,
                        driver_id = NULL,
                        driver_name = NULL,
                        class_name = COALESCE(class_name, 'Overall'),
                        last_active_year = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (championship_name, style, int(season_year), now, str(seat_row["id"])),
                )

    if released_driver_ids:
        placeholders = ",".join("?" for _ in released_driver_ids)
        connection.execute(
            f"""
            UPDATE team_championship_seats
            SET driver_id = NULL,
                driver_name = NULL,
                updated_at = ?
            WHERE championship_id = ?
              AND game = ?
              AND driver_id IN ({placeholders})
            """,
            [now, championship_id, game, *sorted(released_driver_ids)],
        )


def _team_seat_offers_for_championship(
    save_name: str,
    championship: dict[str, Any],
    reputation_map: dict[str, int] | None = None,
    max_offers: int = 5,
) -> list[dict[str, Any]]:
    championship_rows = championship.get("_player_entry_rows")
    if not isinstance(championship_rows, list) or not championship_rows:
        championship_rows = [championship]
    field_size = _estimated_championship_seat_count(championship, championship_rows)
    championship_id, _championship_name, game, _style = _championship_team_seat_identity(championship)
    initialize_driver_pool(save_name)
    with _connect(save_name) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM team_championship_seats
            WHERE championship_id = ?
              AND game = ?
              AND status = 'active'
            ORDER BY seat_number ASC
            LIMIT ?
            """,
            (championship_id, game, field_size),
        ).fetchall()
    seat_plan = [_team_seat_row_to_plan(row) for row in rows]
    if len(seat_plan) < field_size:
        existing_counts: dict[str, int] = defaultdict(int)
        for seat in seat_plan:
            existing_counts[str(seat.get("team_id", "")).strip()] += 1
        for seat in _build_team_seat_plan(field_size - len(seat_plan), championship):
            team_id = str(seat.get("team_id", "")).strip()
            existing_counts[team_id] += 1
            seat["team_seat"] = existing_counts[team_id]
            seat["seat_number"] = len(seat_plan) + 1
            seat_plan.append(dict(seat))
    reputations = reputation_map or {}
    offers: list[dict[str, Any]] = []
    seen_team_keys: set[str] = set()
    for seat in seat_plan:
        team_key = str(seat.get("team_key", "")).strip()
        team_id = str(seat.get("team_id", "")).strip()
        team_name = str(seat.get("team_name", "")).strip() or "Independent"
        dedupe_key = team_key or team_id or team_name
        if dedupe_key in seen_team_keys:
            continue
        seen_team_keys.add(dedupe_key)
        team_prestige = _safe_int(seat.get("team_prestige"), 50)
        team_reputation = (
            reputations.get(team_key)
            or reputations.get(team_id)
            or reputations.get(team_name)
            or team_prestige
        )
        offers.append(
            {
                "team_id": team_id,
                "team_key": team_key,
                "team_name": team_name,
                "team_prestige": team_prestige,
                "team_reputation": team_reputation,
                "seat_number": _safe_int(seat.get("seat_number"), len(offers) + 1),
                "offer_note": "Offer",
                "team_colors": str(seat.get("team_colors", "")).strip()
                or _team_colors_for_identity(team_id, team_name, game),
                "team_personality": str(seat.get("team_personality", "")).strip()
                or _team_personality_for_identity(team_id, team_name, game),
            }
        )
    if not offers:
        return []

    offer_rng = random.Random(
        _stable_seed(
            save_name,
            championship_id,
            game,
            str(_world_year(save_name)),
            "team-seat-offers",
        )
    )
    offer_limit = max(1, min(int(max_offers), len(offers)))
    offer_count = offer_rng.randint(1, offer_limit)
    selected_offers = offer_rng.sample(offers, offer_count)
    selected_offers.sort(
        key=lambda offer: (
            -_safe_int(offer.get("team_reputation"), 50),
            -_safe_int(offer.get("team_prestige"), 50),
            str(offer.get("team_name", "")),
        )
    )
    return selected_offers


def assign_teams_to_standings(
    standings: list[dict[str, Any]],
    championship: dict[str, Any],
    save_name: str | None = None,
) -> list[dict[str, Any]]:
    if not standings:
        return standings
    missing_indices = [
        index
        for index, driver in enumerate(standings)
        if not str(driver.get("team_name", "")).strip()
    ]
    if not missing_indices:
        return standings

    if save_name:
        seat_plan = _build_persistent_team_seat_plan(save_name, len(missing_indices), championship)
    else:
        seat_plan = _build_team_seat_plan(len(missing_indices), championship)
    if not seat_plan:
        return standings

    remaining_indices = list(missing_indices)
    remaining_seats = [dict(seat) for seat in seat_plan]
    ordered_remaining_indices = sorted(
        remaining_indices,
        key=lambda index: (
            -_safe_int(standings[index].get("mmr"), BASELINE_MMR),
            str(standings[index].get("name", "")),
        ),
    )
    ordered_remaining_seats = sorted(
        remaining_seats,
        key=lambda seat: (
            -_safe_int(seat.get("team_prestige"), 50),
            str(seat.get("team_name", "")),
            _safe_int(seat.get("team_seat"), 1),
        ),
    )

    for index, seat in zip(ordered_remaining_indices, ordered_remaining_seats):
        standings[index]["team_id"] = seat["team_id"]
        standings[index]["team_key"] = seat["team_key"]
        standings[index]["team_name"] = seat["team_name"]
        standings[index]["team_seat"] = seat["team_seat"]
        standings[index]["team_prestige"] = seat["team_prestige"]
    return standings


def _stable_seed(*parts: str) -> int:
    seed = 0
    for part in parts:
        for char in str(part):
            seed = ((seed * 131) + ord(char)) % (2**32)
    return seed


def _player_group_effective_mmr_for_style(save_name: str, player_names: list[str], style: str) -> int:
    initialize_driver_pool(save_name)
    player_set = {str(name).strip() for name in player_names if str(name).strip()}
    if not player_set:
        return BASELINE_MMR

    with _connect(save_name) as connection:
        rows = connection.execute(
            """
            SELECT name, primary_style, mmr
            FROM drivers
            WHERE status = 'active'
              AND is_human = 1
            """
        ).fetchall()

    ratings = [
        _effective_style_mmr(int(row["mmr"]), str(row["primary_style"]), style)
        for row in rows
        if str(row["name"]).strip() in player_set
    ]
    if not ratings:
        return BASELINE_MMR
    return round(sum(ratings) / len(ratings))


def player_effective_mmr_for_style(save_name: str, player_names: list[str], style: str) -> int:
    return _player_group_effective_mmr_for_style(save_name, player_names, style)


def players_are_fresh_rookies(save_name: str, player_names: list[str]) -> bool:
    initialize_driver_pool(save_name)
    player_set = {str(name).strip() for name in player_names if str(name).strip()}
    if not player_set:
        return False
    with _connect(save_name) as connection:
        rows = connection.execute(
            """
            SELECT name, career_starts, current_championship
            FROM drivers
            WHERE status = 'active'
              AND is_human = 1
            """
        ).fetchall()
    matched_rows = [row for row in rows if str(row["name"]).strip() in player_set]
    if len(matched_rows) < len(player_set):
        return False
    return all(
        int(row["career_starts"] or 0) == 0
        and not str(row["current_championship"] or "").strip()
        for row in matched_rows
    )


def team_offers_for_player(
    save_name: str,
    player_names: list[str],
    championship: dict[str, Any],
    max_offers: int = 5,
    player_effective_mmr: int | None = None,
    reputation_map: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    seat_offers = _team_seat_offers_for_championship(
        save_name,
        championship,
        reputation_map=reputation_map,
        max_offers=max_offers,
    )
    if seat_offers:
        return seat_offers

    eligible = _eligible_teams_for_championship(championship)
    if not eligible:
        return []

    style = _normalize_style(str(championship.get("Style", "Sports Car")))
    if player_effective_mmr is None:
        player_effective_mmr = _player_group_effective_mmr_for_style(save_name, player_names, style)
    championship_prestige = _safe_int(championship.get("Prestige"), 1)
    reputations = reputation_map or {}

    rng = random.Random(
        _stable_seed(
            save_name,
            ",".join(sorted(str(name).strip() for name in player_names)),
            str(_world_year(save_name)),
            str(championship.get("id", "")),
            str(championship.get("Championship", "")),
            str(championship.get("Sub_Champ", "")),
            "team-offers",
        )
    )
    offer_count = rng.randint(1, max(1, min(int(max_offers), len(eligible))))

    remaining = [dict(team) for team in eligible]
    offers: list[dict[str, Any]] = []
    while remaining and len(offers) < offer_count:
        weights = []
        for team in remaining:
            team_prestige = _safe_int(team.get("Prestige"), 50)
            team_key = _team_key(_team_row_id(team), _team_game(team, str(championship.get("Game", ""))))
            team_reputation = reputations.get(team_key) or reputations.get(_team_row_id(team)) or reputations.get(_team_row_name(team))
            if team_reputation is None:
                team_reputation = _team_reputation_value(save_name, team, str(championship.get("Game", "")))
            prestige_fit = max(1, 120 - abs(team_prestige - championship_prestige))
            weights.append(max(1, team_reputation + prestige_fit))
        chosen_index = rng.choices(range(len(remaining)), weights=weights, k=1)[0]
        team = remaining.pop(chosen_index)
        team_key = _team_key(_team_row_id(team), _team_game(team, str(championship.get("Game", ""))))
        team_reputation = reputations.get(team_key) or reputations.get(_team_row_id(team)) or reputations.get(_team_row_name(team))
        if team_reputation is None:
            team_reputation = _team_reputation_value(save_name, team, str(championship.get("Game", "")))
        offers.append(
            {
                "team_id": str(team.get("Team_ID", "")).strip() or str(team.get("ID", "")).strip(),
                "team_key": team_key,
                "team_name": str(team.get("Team", "")).strip() or "Independent",
                "team_prestige": _safe_int(team.get("Prestige"), 50),
                "team_reputation": team_reputation,
                "team_colors": _team_row_colors(team),
                "team_personality": _team_row_personality(team),
            }
        )

    return offers


def current_team_offer_for_championship(
    save_name: str,
    current_team_offer: dict[str, Any] | None,
    championship: dict[str, Any],
    reputation_map: dict[str, int] | None = None,
) -> dict[str, Any] | None:
    if not isinstance(current_team_offer, dict):
        return None
    current_team_id = str(current_team_offer.get("team_id", "")).strip()
    current_team_key = str(current_team_offer.get("team_key", "")).strip()
    current_team_name = str(current_team_offer.get("team_name", "")).strip()
    if not current_team_id and not current_team_key and not current_team_name:
        return None

    reputations = reputation_map or {}
    championship_game = str(championship.get("Game", "")).strip()
    for team in _eligible_teams_for_championship(championship):
        team_id = _team_row_id(team)
        team_key = _team_key(team_id, _team_game(team, championship_game))
        team_name = _team_row_name(team)
        key_matches = bool(current_team_key and current_team_key == team_key)
        id_matches = bool(current_team_id and current_team_id == team_id)
        name_matches = bool(current_team_name and current_team_name.casefold() == team_name.casefold())
        if not (key_matches or id_matches or name_matches):
            continue
        team_reputation = reputations.get(team_key) or reputations.get(team_id) or reputations.get(team_name)
        if team_reputation is None:
            team_reputation = _team_reputation_value(save_name, team, championship_game)
        return {
            "team_id": team_id,
            "team_key": team_key,
            "team_name": team_name,
            "team_prestige": _safe_int(team.get("Prestige"), 50),
            "team_reputation": team_reputation,
            "offer_note": "Current",
            "team_colors": _team_row_colors(team),
            "team_personality": _team_row_personality(team),
        }
    return None


def _championship_pool_display_name(championship: dict[str, Any]) -> str:
    return str(
        championship.get("Pool_Championship")
        or championship.get("Championship")
        or ""
    ).strip()


def _championship_group_display_name(
    championship: dict[str, Any],
    group_index: int,
    group_count: int,
) -> str:
    base_name = str(championship.get("Championship", "Championship")).strip() or "Championship"
    return base_name


def championship_pool_display_name(
    championship: dict[str, Any],
    group_index: int = 0,
    group_count: int | None = None,
) -> str:
    if group_count is None:
        group_count = 1
    return _championship_group_display_name(championship, group_index, group_count)


def _skill_from_rating(rating: int) -> int:
    return max(40, min(95, round(rating / 12.5)))


def _driver_ids_by_name(save_name: str) -> dict[str, str]:
    with _connect(save_name) as connection:
        rows = connection.execute(
            """
            SELECT id, name FROM drivers
            WHERE status = 'active'
            """
        ).fetchall()
    return {str(row["name"]): str(row["id"]) for row in rows}


def driver_profile_map(save_name: str) -> dict[str, dict[str, Any]]:
    initialize_driver_pool(save_name)
    with _connect(save_name) as connection:
        rows = connection.execute(
            """
            SELECT
                name,
                country_code,
                iracing_relative_skill,
                iracing_aggression,
                iracing_optimism,
                iracing_smoothness,
                iracing_pit_crew_skill,
                iracing_strategy_riskiness,
                iracing_sponsor1,
                iracing_sponsor2,
                driver_age,
                ams2_aggression,
                ams2_avoidance_of_forced_mistakes,
                ams2_avoidance_of_mistakes,
                ams2_blue_flag_conceding,
                ams2_consistency,
                ams2_defending,
                ams2_fuel_management,
                ams2_general_skill,
                ams2_qualifying_skill,
                ams2_race_skill,
                ams2_stamina,
                ams2_start_reactions,
                ams2_tyre_management,
                ams2_vehicle_reliability,
                ams2_weather_tyre_changes,
                ams2_wet_skill
            FROM drivers
            """
        ).fetchall()
    return {str(row["name"]): dict(row) for row in rows}


def _sim_rating_from_profile(profile: dict[str, Any], game: str, fallback_rating: int) -> int:
    normalized_game = str(game).strip().casefold()
    if normalized_game == "ams2":
        general_skill = _safe_int(profile.get("ams2_general_skill"), -1)
        if general_skill >= 0:
            return max(0, int(round(max(0, min(100, general_skill)) * 12.5)))
        try:
            race_skill = float(profile.get("ams2_race_skill", 0) or 0)
        except (TypeError, ValueError):
            race_skill = 0.0
        if race_skill <= 0:
            race_skill = max(0.01, min(1.0, _skill_from_rating(fallback_rating) / 100.0))
        return max(0, int(round(race_skill * 1250)))

    relative_skill = _safe_int(profile.get("iracing_relative_skill"), -1)
    if relative_skill < 0:
        relative_skill = _skill_from_rating(fallback_rating)
    relative_skill = max(0, min(100, relative_skill))
    return max(0, int(round(relative_skill * 12.5)))


def _sim_rating_lookup(save_name: str, names: set[str], game: str) -> dict[str, int]:
    if not names:
        return {}

    placeholders = ",".join("?" for _ in names)
    with _connect(save_name) as connection:
        rows = connection.execute(
            f"""
            SELECT name, mmr, iracing_relative_skill, ams2_general_skill, ams2_race_skill
            FROM drivers
            WHERE name IN ({placeholders})
              AND status = 'active'
            """,
            list(names),
        ).fetchall()
    return {
        str(row["name"]): _sim_rating_from_profile(dict(row), game, _safe_int(row["mmr"], BASELINE_MMR))
        for row in rows
    }


def _ratings_for_driver_ids(save_name: str, driver_ids: list[str]) -> dict[str, int]:
    if not driver_ids:
        return {}

    placeholders = ",".join("?" for _ in driver_ids)
    with _connect(save_name) as connection:
        rows = connection.execute(
            f"""
            SELECT id, mmr AS rating FROM drivers
            WHERE id IN ({placeholders})
            """,
            driver_ids,
        ).fetchall()
    return {str(row["id"]): int(row["rating"]) for row in rows}


def _elo_changes_for_finish_order(
    finish_order_names: list[str],
    driver_ids_by_name: dict[str, str],
    current_ratings: dict[str, int],
) -> dict[str, int]:
    driver_count = len(finish_order_names)
    if driver_count < 2:
        return {driver_ids_by_name[name]: 0 for name in finish_order_names if name in driver_ids_by_name}

    changes: dict[str, int] = {}
    for position, driver_name in enumerate(finish_order_names):
        driver_id = driver_ids_by_name.get(driver_name)
        if not driver_id or driver_id not in current_ratings:
            continue

        rating = current_ratings[driver_id]
        score_delta = 0.0
        for opponent_position, opponent_name in enumerate(finish_order_names):
            if opponent_name == driver_name:
                continue
            opponent_id = driver_ids_by_name.get(opponent_name)
            if not opponent_id or opponent_id not in current_ratings:
                continue
            opponent_rating = current_ratings[opponent_id]
            actual = 1.0 if position < opponent_position else 0.0
            expected = 1.0 / (1.0 + 10 ** ((opponent_rating - rating) / 400))
            score_delta += actual - expected

        # Soften field-size normalization so large races move ratings more than they do now.
        normalized_delta = score_delta / max(1.0, math.sqrt(driver_count - 1))
        change = round(RACE_K_FACTOR * normalized_delta)
        changes[driver_id] = max(-RACE_RATING_CHANGE_CAP, min(RACE_RATING_CHANGE_CAP, change))
    return changes


def list_drivers(save_name: str, include_retired: bool = False) -> list[dict[str, Any]]:
    initialize_driver_pool(save_name)
    where_clause = "" if include_retired else "WHERE status = 'active'"
    with _connect(save_name) as connection:
        rows = connection.execute(
            f"""
            SELECT
                id,
                name,
                is_human,
                status,
                primary_style,
                mmr,
                sports_car_rating,
                oval_rating,
                open_wheel_rating,
                seasons_completed,
                career_starts,
                wins,
                podiums,
                championships,
                current_tier,
                current_style,
                current_championship,
                retirement_after_seasons
            FROM drivers
            {where_clause}
            ORDER BY status ASC, is_human DESC, mmr DESC, name ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def best_driver_in_world(save_name: str) -> dict[str, Any] | None:
    initialize_driver_pool(save_name)
    with _connect(save_name) as connection:
        row = connection.execute(
            """
            SELECT
                id,
                name,
                is_human,
                status,
                primary_style,
                mmr,
                championships,
                wins,
                podiums,
                seasons_completed,
                current_tier,
                current_style,
                current_championship
            FROM drivers
            WHERE status = 'active'
            ORDER BY mmr DESC, championships DESC, wins DESC, name ASC
            LIMIT 1
            """
        ).fetchone()
    return dict(row) if row else None


def notable_retirements(save_name: str, season_year: int, limit: int = 5) -> list[dict[str, Any]]:
    initialize_driver_pool(save_name)
    with _connect(save_name) as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                name,
                primary_style,
                mmr,
                championships,
                wins,
                podiums,
                seasons_completed
            FROM drivers
            WHERE status = 'retired'
              AND retired_year = ?
            ORDER BY championships DESC, wins DESC, podiums DESC, mmr DESC, name ASC
            LIMIT ?
            """,
            (int(season_year), max(1, int(limit))),
        ).fetchall()
    return [dict(row) for row in rows]


def top_rookies_for_year(save_name: str, season_year: int, limit: int = 5) -> list[dict[str, Any]]:
    initialize_driver_pool(save_name)
    with _connect(save_name) as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                name,
                primary_style,
                mmr,
                iracing_relative_skill,
                current_tier,
                current_style,
                current_championship
            FROM drivers
            WHERE status = 'active'
              AND is_human = 0
              AND debut_year = ?
            ORDER BY iracing_relative_skill DESC, mmr DESC, name ASC
            LIMIT ?
            """,
            (int(season_year), max(1, int(limit))),
        ).fetchall()
    return [dict(row) for row in rows]


def team_reputation_map(save_name: str) -> dict[str, int]:
    initialize_driver_pool(save_name)
    save_data = save_manager.load_save(save_name) or {}
    target_game = str(save_data.get("game", "iRacing")).strip()
    target_game_key = target_game.casefold()
    selected_rows: dict[str, dict[str, Any]] = {}
    with _connect(save_name) as connection:
        _sync_team_totals_from_history(connection)
        connection.commit()
        rows = connection.execute(
            """
            SELECT team_key, team_id, team_name, reputation
                 , game
            FROM team_reputations
            """
        ).fetchall()
    for row in rows:
        team_id = str(row["team_id"] or "").strip()
        team_name = str(row["team_name"] or "").strip()
        group_key = team_id or team_name
        if not group_key:
            continue
        existing = selected_rows.get(group_key)
        row_game = str(row["game"] or "").strip().casefold()
        existing_game = str((existing or {}).get("game", "")).strip().casefold()
        if existing is None or (row_game == target_game_key and existing_game != target_game_key):
            selected_rows[group_key] = dict(row)

    reputations: dict[str, int] = {}
    for row in selected_rows.values():
        reputation = _safe_int(row["reputation"], 50)
        for key in (row["team_key"], row["team_id"], row["team_name"]):
            normalized = str(key or "").strip()
            if normalized:
                reputations[normalized] = reputation
    return reputations


def list_teams_page(
    save_name: str,
    search: str = "",
    sort_by: str = "Reputation",
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    initialize_driver_pool(save_name)
    save_data = save_manager.load_save(save_name) or {}
    target_game = str(save_data.get("game", "iRacing")).strip()
    target_game_key = target_game.casefold()
    cleaned_search = str(search).strip()
    with _connect(save_name) as connection:
        _sync_team_totals_from_history(connection)
        connection.commit()
        rows = connection.execute(
            """
            SELECT
                team_key,
                team_id,
                team_name,
                game,
                base_prestige,
                reputation,
                seasons_completed,
                championships,
                wins,
                podiums,
                last_championship,
                last_style
            FROM team_reputations
            """,
        ).fetchall()

    row_items = [dict(row) for row in rows]
    has_game_specific_rows = any(str(row.get("game", "")).strip().casefold() == target_game_key for row in row_items)
    selected_rows: dict[str, dict[str, Any]] = {}
    for item in row_items:
        row_game = str(item.get("game", "")).strip().casefold()
        if has_game_specific_rows and row_game != target_game_key:
            continue
        team_id = str(item.get("team_id", "")).strip()
        team_name = str(item.get("team_name", "")).strip()
        group_key = team_id or team_name
        if not group_key:
            continue
        existing = selected_rows.get(group_key)
        existing_game = str((existing or {}).get("game", "")).strip().casefold()
        if existing is None:
            selected_rows[group_key] = item
        elif row_game == target_game_key and existing_game != target_game_key:
            selected_rows[group_key] = item
        elif row_game == existing_game:
            if _safe_int(item.get("seasons_completed"), 0) > _safe_int(existing.get("seasons_completed"), 0):
                selected_rows[group_key] = item

    teams = list(selected_rows.values())
    if cleaned_search:
        search_value = cleaned_search.casefold()
        teams = [
            team
            for team in teams
            if search_value in str(team.get("team_name", "")).casefold()
            or search_value in str(team.get("game", "")).casefold()
            or search_value in str(team.get("last_style", "")).casefold()
        ]

    sort_options = {
        "Name": lambda row: (str(row.get("team_name", "")),),
        "Reputation": lambda row: (-_safe_int(row.get("reputation"), 50), -_safe_int(row.get("championships"), 0), -_safe_int(row.get("wins"), 0), str(row.get("team_name", ""))),
        "Titles": lambda row: (-_safe_int(row.get("championships"), 0), -_safe_int(row.get("reputation"), 50), -_safe_int(row.get("wins"), 0), str(row.get("team_name", ""))),
        "Wins": lambda row: (-_safe_int(row.get("wins"), 0), -_safe_int(row.get("reputation"), 50), -_safe_int(row.get("championships"), 0), str(row.get("team_name", ""))),
        "Seasons": lambda row: (-_safe_int(row.get("seasons_completed"), 0), -_safe_int(row.get("reputation"), 50), str(row.get("team_name", ""))),
    }
    teams.sort(key=sort_options.get(sort_by, sort_options["Reputation"]))
    total = len(teams)
    start = max(0, int(offset))
    end = start + max(1, int(limit))
    return teams[start:end], total


def get_team_profile(save_name: str, team_key: str) -> dict[str, Any] | None:
    initialize_driver_pool(save_name)
    cleaned_key = str(team_key).strip()
    if not cleaned_key:
        return None
    with _connect(save_name) as connection:
        _sync_team_totals_from_history(connection)
        connection.commit()
        team_row = connection.execute(
            """
            SELECT
                team_key,
                team_id,
                team_name,
                game,
                base_prestige,
                reputation,
                seasons_completed,
                championships,
                wins,
                podiums,
                last_championship,
                last_style
            FROM team_reputations
            WHERE team_key = ?
            """,
            (cleaned_key,),
        ).fetchone()
        if not team_row:
            return None

        season_rows = connection.execute(
            """
            SELECT
                championship_name,
                season_year,
                game,
                style,
                class_name,
                drivers,
                driver_count,
                points,
                wins,
                podiums,
                championships
            FROM team_season_results
            WHERE team_key = ?
            ORDER BY season_year DESC, championship_name ASC, class_name ASC
            """,
            (cleaned_key,),
        ).fetchall()
        decision_rows = connection.execute(
            """
            SELECT
                driver_name,
                championship_name,
                season_year,
                decision,
                reason
            FROM team_driver_decisions
            WHERE team_key = ?
            ORDER BY season_year DESC, created_at DESC
            LIMIT 30
            """,
            (cleaned_key,),
        ).fetchall()
        ownership_rows = connection.execute(
            """
            SELECT
                championship_name,
                game,
                style,
                seat_number,
                team_seat,
                event_type,
                season_year,
                reason,
                created_at
            FROM team_seat_history
            WHERE team_key = ?
            ORDER BY
                COALESCE(season_year, 0) DESC,
                created_at DESC,
                championship_name ASC,
                seat_number ASC
            LIMIT 80
            """,
            (cleaned_key,),
        ).fetchall()

    team = dict(team_row)
    team["team_colors"] = _team_colors_for_identity(
        str(team.get("team_id", "")),
        str(team.get("team_name", "")),
        str(team.get("game", "")),
    )
    return {
        "team": team,
        "season_history": [dict(row) for row in season_rows],
        "driver_decisions": [dict(row) for row in decision_rows],
        "ownership_history": [dict(row) for row in ownership_rows],
    }


def rename_team(save_name: str, team_key: str, new_name: str) -> tuple[bool, str]:
    initialize_driver_pool(save_name)
    cleaned_team_key = str(team_key).strip()
    cleaned_new_name = str(new_name).strip()
    if not cleaned_team_key:
        return False, "No team selected."
    if not cleaned_new_name:
        return False, "Team name cannot be blank."

    now = _now()
    with _connect(save_name) as connection:
        row = connection.execute(
            "SELECT team_name FROM team_reputations WHERE team_key = ?",
            (cleaned_team_key,),
        ).fetchone()
        if not row:
            return False, "Team not found."
        old_name = str(row["team_name"]).strip()
        if old_name == cleaned_new_name:
            return True, "Team name is already set."

        connection.execute(
            "UPDATE team_reputations SET team_name = ?, updated_at = ? WHERE team_key = ?",
            (cleaned_new_name, now, cleaned_team_key),
        )
        connection.execute(
            "UPDATE team_driver_decisions SET team_name = ? WHERE team_key = ?",
            (cleaned_new_name, cleaned_team_key),
        )
        connection.execute(
            "UPDATE team_season_results SET team_name = ? WHERE team_key = ?",
            (cleaned_new_name, cleaned_team_key),
        )
        connection.execute(
            "UPDATE team_championship_seats SET team_name = ?, updated_at = ? WHERE team_key = ?",
            (cleaned_new_name, now, cleaned_team_key),
        )
        connection.execute(
            "UPDATE team_seat_history SET team_name = ? WHERE team_key = ?",
            (cleaned_new_name, cleaned_team_key),
        )
        connection.execute(
            "UPDATE driver_race_results SET team_name = ? WHERE team_name = ?",
            (cleaned_new_name, old_name),
        )
        connection.commit()

    save_data = save_manager.load_save(save_name)
    if save_data is not None:
        updated_save = _replace_team_name_in_save_payload(save_data, cleaned_team_key, old_name, cleaned_new_name)
        save_manager.update_save(save_name, updated_save)
    return True, f"Team renamed to {cleaned_new_name}."


def recent_team_storylines(save_name: str, season_year: int, limit: int = 8) -> list[dict[str, Any]]:
    initialize_driver_pool(save_name)
    with _connect(save_name) as connection:
        rows = connection.execute(
            """
            SELECT
                tdd.team_name,
                tdd.driver_name,
                tdd.championship_name,
                tdd.decision,
                tdd.reason,
                tr.reputation
            FROM team_driver_decisions tdd
            LEFT JOIN team_reputations tr
              ON tr.team_key = tdd.team_key
            WHERE tdd.season_year = ?
            ORDER BY
                CASE tdd.decision WHEN 'released' THEN 0 ELSE 1 END,
                COALESCE(tr.reputation, 50) DESC,
                tdd.team_name ASC,
                tdd.driver_name ASC
            LIMIT ?
            """,
            (int(season_year), max(1, int(limit))),
        ).fetchall()
    return [dict(row) for row in rows]


def recent_team_seat_storylines(save_name: str, season_year: int, limit: int = 8) -> list[dict[str, Any]]:
    initialize_driver_pool(save_name)
    with _connect(save_name) as connection:
        rows = connection.execute(
            """
            SELECT
                team_name,
                championship_name,
                event_type,
                reason
            FROM team_seat_history
            WHERE season_year = ?
              AND event_type IN ('sold', 'lost', 'acquired', 'moved')
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (int(season_year), max(1, int(limit))),
        ).fetchall()
    return [dict(row) for row in rows]


def championship_storyline_drivers(
    save_name: str,
    standings: list[dict[str, Any]],
    game: str,
    tier: int,
    player_names: list[str] | None = None,
) -> dict[str, Any]:
    initialize_driver_pool(save_name)
    player_set = {str(name).strip() for name in (player_names or []) if str(name).strip()}
    ai_driver_ids = [
        str(driver.get("driver_id", "")).strip()
        for driver in standings
        if str(driver.get("name", "")).strip() not in player_set and str(driver.get("driver_id", "")).strip()
    ]
    if not ai_driver_ids:
        return {"watch_drivers": [], "rising_driver": None}

    placeholders = ",".join("?" for _ in ai_driver_ids)
    normalized_game = str(game).strip().casefold()
    skill_column = "ams2_general_skill" if normalized_game == "ams2" else "iracing_relative_skill"
    with _connect(save_name) as connection:
        rows = connection.execute(
            f"""
            SELECT
                id,
                name,
                last_tier,
                {skill_column} AS skill_value
            FROM drivers
            WHERE id IN ({placeholders})
            """,
            ai_driver_ids,
        ).fetchall()

    ranked = sorted(
        [dict(row) for row in rows],
        key=lambda row: (
            -(float(row.get("skill_value", 0) or 0)),
            str(row.get("name", "")).strip(),
        ),
    )
    watch_drivers = [str(row.get("name", "")).strip() for row in ranked[:2] if str(row.get("name", "")).strip()]
    rising_pool = [
        row
        for row in ranked
        if _safe_int(row.get("last_tier"), 0) == max(1, int(tier) - 1)
    ]
    rising_driver = next(
        (
            str(row.get("name", "")).strip()
            for row in rising_pool
            if str(row.get("name", "")).strip() and str(row.get("name", "")).strip() not in watch_drivers
        ),
        None,
    )
    if not rising_driver and rising_pool:
        rising_driver = str(rising_pool[0].get("name", "")).strip() or None

    return {
        "watch_drivers": watch_drivers,
        "rising_driver": rising_driver,
    }


def get_driver_profile(save_name: str, driver_id: str) -> dict[str, Any] | None:
    initialize_driver_pool(save_name)
    with _connect(save_name) as connection:
        driver_row = connection.execute(
            """
            SELECT
                id,
                name,
                is_human,
                status,
                primary_style,
                mmr,
                seasons_completed,
                career_starts,
                wins,
                podiums,
                championships,
                current_tier,
                current_style,
                current_championship,
                retirement_after_seasons,
                created_at,
                updated_at
            FROM drivers
            WHERE id = ?
            """,
            (driver_id,),
        ).fetchone()
        if not driver_row:
            return None

        season_rows = connection.execute(
            """
            SELECT
                championship_id,
                championship_name,
                season_year,
                style,
                tier,
                class_name,
                finishing_place
            FROM driver_season_results
            WHERE driver_id = ?
            ORDER BY season_year DESC, tier DESC, championship_name ASC
            """,
            (driver_id,),
        ).fetchall()

        title_rows = connection.execute(
            """
            SELECT
                championship_id,
                championship_name,
                season_year,
                style,
                tier,
                class_name
            FROM driver_championship_wins
            WHERE driver_id = ?
            ORDER BY season_year DESC, tier DESC, championship_name ASC
            """,
            (driver_id,),
        ).fetchall()

    season_history = [dict(row) for row in season_rows]
    championship_history = [dict(row) for row in title_rows]
    styles_by_year: dict[int, str] = {}
    for item in sorted(season_history, key=lambda row: int(row.get("season_year", 0) or 0)):
        season_year = int(item.get("season_year", 0) or 0)
        style = str(item.get("style", "")).strip()
        if season_year and style and season_year not in styles_by_year:
            styles_by_year[season_year] = style

    discipline_changes: list[dict[str, Any]] = []
    previous_style = ""
    for season_year in sorted(styles_by_year):
        style = styles_by_year[season_year]
        if previous_style and style != previous_style:
            discipline_changes.append(
                {
                    "season_year": season_year,
                    "from_style": previous_style,
                    "to_style": style,
                }
            )
        previous_style = style

    return {
        "driver": dict(driver_row),
        "season_history": season_history,
        "championship_history": championship_history,
        "discipline_changes": discipline_changes,
    }


def _replace_exact_value(value: Any, old_value: str, new_value: str) -> Any:
    if isinstance(value, str):
        return new_value if value == old_value else value
    if isinstance(value, list):
        return [_replace_exact_value(item, old_value, new_value) for item in value]
    if isinstance(value, dict):
        updated: dict[Any, Any] = {}
        for key, item in value.items():
            updated_key = new_value if isinstance(key, str) and key == old_value else key
            updated[updated_key] = _replace_exact_value(item, old_value, new_value)
        return updated
    return value


def _replace_driver_name_in_save_payload(value: Any, driver_id: str, old_name: str, new_name: str) -> Any:
    updated = _replace_exact_value(value, old_name, new_name)
    if isinstance(updated, dict) and str(updated.get("driver_id", "")).strip() == driver_id:
        if "name" in updated:
            updated["name"] = new_name
        if "driver_name" in updated:
            updated["driver_name"] = new_name
    return updated


def _replace_team_name_in_save_payload(value: Any, team_key: str, old_name: str, new_name: str) -> Any:
    updated = _replace_exact_value(value, old_name, new_name)
    if isinstance(updated, dict) and str(updated.get("team_key", "")).strip() == team_key and "team_name" in updated:
        updated["team_name"] = new_name
    return updated


def _replace_name_in_pipe_list(raw_value: str, old_name: str, new_name: str) -> str:
    parts = [part.strip() for part in str(raw_value).split("|")]
    return " | ".join(new_name if part == old_name else part for part in parts if part)


def rename_driver(save_name: str, driver_id: str, new_name: str) -> tuple[bool, str]:
    initialize_driver_pool(save_name)
    cleaned_driver_id = str(driver_id).strip()
    cleaned_new_name = str(new_name).strip()
    if not cleaned_driver_id:
        return False, "No driver selected."
    if not cleaned_new_name:
        return False, "Driver name cannot be blank."

    now = _now()
    with _connect(save_name) as connection:
        row = connection.execute(
            "SELECT name, is_human, status FROM drivers WHERE id = ?",
            (cleaned_driver_id,),
        ).fetchone()
        if not row:
            return False, "Driver not found."
        old_name = str(row["name"]).strip()
        if old_name == cleaned_new_name:
            return True, "Driver name is already set."

        duplicate = connection.execute(
            """
            SELECT id
            FROM drivers
            WHERE name = ?
              AND is_human = ?
              AND status = ?
              AND id <> ?
            LIMIT 1
            """,
            (cleaned_new_name, int(row["is_human"]), str(row["status"]), cleaned_driver_id),
        ).fetchone()
        if duplicate:
            return False, "Another active driver already has that name."

        connection.execute(
            "UPDATE drivers SET name = ?, updated_at = ? WHERE id = ?",
            (cleaned_new_name, now, cleaned_driver_id),
        )
        connection.execute(
            "UPDATE driver_race_results SET driver_name = ? WHERE driver_id = ?",
            (cleaned_new_name, cleaned_driver_id),
        )
        connection.execute(
            "UPDATE team_driver_decisions SET driver_name = ? WHERE driver_id = ?",
            (cleaned_new_name, cleaned_driver_id),
        )
        connection.execute(
            "UPDATE team_championship_seats SET driver_name = ?, updated_at = ? WHERE driver_id = ?",
            (cleaned_new_name, now, cleaned_driver_id),
        )

        team_season_rows = connection.execute(
            "SELECT id, drivers FROM team_season_results WHERE drivers LIKE ?",
            (f"%{old_name}%",),
        ).fetchall()
        for item in team_season_rows:
            updated_drivers = _replace_name_in_pipe_list(str(item["drivers"]), old_name, cleaned_new_name)
            if updated_drivers != str(item["drivers"]):
                connection.execute(
                    "UPDATE team_season_results SET drivers = ? WHERE id = ?",
                    (updated_drivers, str(item["id"])),
                )
        connection.commit()

    save_data = save_manager.load_save(save_name)
    if save_data is not None:
        updated_save = _replace_driver_name_in_save_payload(save_data, cleaned_driver_id, old_name, cleaned_new_name)
        save_manager.update_save(save_name, updated_save)
    return True, f"Driver renamed to {cleaned_new_name}."


def get_driver_race_history(
    save_name: str,
    driver_id: str,
    championship_id: str,
    season_year: int,
) -> list[dict[str, Any]]:
    initialize_driver_pool(save_name)
    with _connect(save_name) as connection:
        rows = connection.execute(
            """
            SELECT
                race_num,
                track,
                layout,
                championship_name,
                season_year,
                style,
                tier,
                class_name,
                overall_pos,
                class_pos,
                class_size,
                team_name,
                points_awarded,
                mmr_change
            FROM driver_race_results
            WHERE driver_id = ?
              AND championship_id = ?
              AND season_year = ?
            ORDER BY race_num ASC
            """,
            (driver_id, championship_id, int(season_year)),
        ).fetchall()
    return [dict(row) for row in rows]


def latest_tier_champions(save_name: str, season_year: int, tier: int = 5) -> list[dict[str, Any]]:
    initialize_driver_pool(save_name)
    with _connect(save_name) as connection:
        rows = connection.execute(
            """
            SELECT
                cw.championship_id,
                cw.championship_name,
                cw.season_year,
                cw.style,
                cw.tier,
                COALESCE(
                    NULLIF(cw.class_name, 'Overall'),
                    dsr.class_name,
                    cw.class_name,
                    'Overall'
                ) AS class_name,
                d.name AS driver_name,
                d.mmr,
                d.primary_style
            FROM driver_championship_wins cw
            JOIN drivers d
              ON d.id = cw.driver_id
            LEFT JOIN driver_season_results dsr
              ON dsr.driver_id = cw.driver_id
             AND dsr.championship_id = cw.championship_id
             AND dsr.season_year = cw.season_year
             AND dsr.finishing_place = 1
            WHERE cw.season_year = ?
              AND cw.tier = ?
            ORDER BY cw.style ASC, cw.championship_name ASC, d.name ASC
            """,
            (int(season_year), int(tier)),
        ).fetchall()
    return [dict(row) for row in rows]


def latest_close_title_battles(save_name: str, season_year: int, max_gap: int = 10, limit: int = 5) -> list[dict[str, Any]]:
    initialize_driver_pool(save_name)
    with _connect(save_name) as connection:
        rows = connection.execute(
            """
            SELECT
                dsr.championship_id,
                dsr.championship_name,
                dsr.season_year,
                dsr.style,
                dsr.tier,
                COALESCE(NULLIF(dsr.class_name, ''), 'Overall') AS class_label,
                dsr.finishing_place,
                dsr.driver_id,
                d.name AS driver_name,
                COALESCE(SUM(drr.points_awarded), 0) AS points
            FROM driver_season_results dsr
            JOIN drivers d
              ON d.id = dsr.driver_id
            LEFT JOIN driver_race_results drr
              ON drr.driver_id = dsr.driver_id
             AND drr.championship_id = dsr.championship_id
             AND drr.season_year = dsr.season_year
             AND COALESCE(NULLIF(drr.class_name, ''), 'Overall') = COALESCE(NULLIF(dsr.class_name, ''), 'Overall')
            WHERE dsr.season_year = ?
            GROUP BY
                dsr.championship_id,
                dsr.championship_name,
                dsr.season_year,
                dsr.style,
                dsr.tier,
                COALESCE(NULLIF(dsr.class_name, ''), 'Overall'),
                dsr.finishing_place,
                dsr.driver_id,
                d.name
            ORDER BY dsr.championship_name ASC, class_label ASC, dsr.finishing_place ASC
            """,
            (int(season_year),),
        ).fetchall()

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        item = dict(row)
        grouped[(str(item.get("championship_id", "")), str(item.get("class_label", "Overall")))].append(item)

    battles: list[dict[str, Any]] = []
    for group_rows in grouped.values():
        sorted_rows = sorted(group_rows, key=lambda item: _safe_int(item.get("finishing_place"), 9999))
        if len(sorted_rows) < 2:
            continue
        champion = sorted_rows[0]
        runner_up = sorted_rows[1]
        champion_points = _safe_int(champion.get("points"), 0)
        runner_up_points = _safe_int(runner_up.get("points"), 0)
        if champion_points <= 0 or runner_up_points <= 0:
            continue
        gap = champion_points - runner_up_points
        if gap < 0 or gap > int(max_gap):
            continue
        battles.append(
            {
                "championship_id": champion.get("championship_id", ""),
                "championship_name": champion.get("championship_name", ""),
                "season_year": champion.get("season_year", season_year),
                "style": champion.get("style", ""),
                "tier": champion.get("tier", 0),
                "class_name": champion.get("class_label", "Overall"),
                "champion_name": champion.get("driver_name", "Unknown"),
                "runner_up_name": runner_up.get("driver_name", "Unknown"),
                "champion_points": champion_points,
                "runner_up_points": runner_up_points,
                "gap": gap,
            }
        )

    battles.sort(key=lambda item: (_safe_int(item.get("gap"), 9999), -_safe_int(item.get("tier"), 0)))
    return battles[: max(0, int(limit))]


def _effective_style_mmr(mmr: int, primary_style: str, target_style: str) -> int:
    effective_mmr = int(mmr)
    if str(primary_style) not in {"", "Unassigned", target_style}:
        effective_mmr -= NON_PRIMARY_STYLE_PENALTY
    return effective_mmr


def _style_draft_bucket(primary_style: str, target_style: str) -> int:
    normalized_primary = str(primary_style).strip()
    if normalized_primary == target_style:
        return 0
    if normalized_primary in {"", "Unassigned"}:
        return 1
    return 2


def _estimated_championship_seat_count(
    row: dict[str, Any],
    championship_rows: list[dict[str, Any]],
) -> int:
    max_opp = _safe_int(row.get("Max_Opp"), 0)
    field_size = max(1, max_opp)
    championship_group_id = str(row.get("Championship_ID", "")).strip() or str(row.get("id", "")).strip()
    group_rows = [
        candidate
        for candidate in championship_rows
        if (str(candidate.get("Championship_ID", "")).strip() or str(candidate.get("id", "")).strip()) == championship_group_id
    ]
    class_count = max(1, len(group_rows))
    return max(1, round(field_size / class_count))


def _draft_seat_entries_for_championship(
    save_name: str,
    championship: dict[str, Any],
    championship_rows: list[dict[str, Any]],
    game: str,
    reputation_map: dict[str, int] | None = None,
    existing_seats_by_championship: dict[tuple[str, str], list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    seat_count = _estimated_championship_seat_count(championship, championship_rows)
    if seat_count <= 0:
        return []

    championship_id, _championship_name, championship_game, _style = _championship_team_seat_identity(championship)
    if existing_seats_by_championship is not None:
        existing_seats = list(existing_seats_by_championship.get((championship_id, championship_game), []))[:seat_count]
    else:
        existing_seats: list[dict[str, Any]] = []
        try:
            with _connect(save_name) as connection:
                rows = connection.execute(
                    """
                    SELECT *
                    FROM team_championship_seats
                    WHERE championship_id = ?
                      AND game = ?
                      AND status = 'active'
                    ORDER BY team_prestige DESC, team_name ASC, team_seat ASC, seat_number ASC
                    LIMIT ?
                    """,
                    (championship_id, championship_game, seat_count),
                ).fetchall()
            existing_seats = [_team_seat_row_to_plan(row) for row in rows]
        except Exception:
            existing_seats = []

    if len(existing_seats) >= seat_count:
        seat_plan = existing_seats[:seat_count]
    else:
        eligible_teams = sorted(
            _eligible_teams_for_championship(championship),
            key=lambda team: (
                -_team_reputation_from_map(reputation_map, team, championship_game, _safe_int(team.get("Prestige"), 50)),
                -_safe_int(team.get("Prestige"), 50),
                _team_row_name(team),
            ),
        )
        seat_plan = list(existing_seats)
        team_counts: dict[str, int] = defaultdict(int)
        for seat in seat_plan:
            team_counts[str(seat.get("team_id", "")).strip()] += 1
        team_index = 0
        while len(seat_plan) < seat_count:
            if not eligible_teams:
                seat_plan.append(
                    {
                        "team_id": "",
                        "team_key": "",
                        "team_name": "Independent",
                        "team_seat": len(seat_plan) + 1,
                        "team_prestige": 0,
                    }
                )
                continue
            team = eligible_teams[team_index % len(eligible_teams)]
            team_index += 1
            team_id = _team_row_id(team)
            team_counts[team_id] += 1
            seat_plan.append(
                {
                    "team_id": team_id,
                    "team_key": _team_key(team_id, _team_game(team, championship_game)),
                    "team_name": _team_row_name(team),
                    "team_seat": team_counts[team_id],
                    "team_prestige": _safe_int(team.get("Prestige"), 50),
                }
            )

    championship_prestige = _safe_int(championship.get("Prestige"), 0)
    championship_tier = _safe_int(championship.get("Tier"), 1)
    entries: list[dict[str, Any]] = []
    for seat_index, seat in enumerate(seat_plan[:seat_count], start=1):
        team_reputation = _safe_int(seat.get("team_prestige"), 50)
        team_key = str(seat.get("team_key", "")).strip()
        if reputation_map is not None:
            team_reputation = reputation_map.get(team_key) or reputation_map.get(str(seat.get("team_id", "")).strip()) or reputation_map.get(str(seat.get("team_name", "")).strip()) or team_reputation
        elif team_key:
            try:
                with _connect(save_name) as connection:
                    reputation_row = connection.execute(
                        "SELECT reputation FROM team_reputations WHERE team_key = ?",
                        (team_key,),
                    ).fetchone()
                if reputation_row:
                    team_reputation = _safe_int(reputation_row["reputation"], team_reputation)
            except Exception:
                pass
        entries.append(
            {
                "championship_id": str(championship.get("id", "")).strip(),
                "championship_name": str(championship.get("Championship", "")).strip(),
                "prestige": championship_prestige,
                "tier": championship_tier,
                "game": game,
                "team_id": str(seat.get("team_id", "")).strip(),
                "team_key": team_key,
                "team_name": str(seat.get("team_name", "")).strip() or "Independent",
                "team_prestige": _safe_int(seat.get("team_prestige"), 50),
                "team_reputation": team_reputation,
                "seat_index": seat_index,
            }
        )
    return entries


def _draft_ordered_seat_entries(
    save_name: str,
    style: str,
    championship_rows: list[dict[str, Any]],
    game: str,
    reputation_map: dict[str, int] | None = None,
    existing_seats_by_championship: dict[tuple[str, str], list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    normalized_style = _normalize_style(style)
    normalized_game = str(game).strip().casefold()
    style_rows = [
        dict(row)
        for row in championship_rows
        if _normalize_style(str(row.get("Style", ""))) == normalized_style
        and str(row.get("Game", "")).strip().casefold() in {"", normalized_game}
    ]
    seats: list[dict[str, Any]] = []
    for row in style_rows:
        seats.extend(
            _draft_seat_entries_for_championship(
                save_name,
                row,
                style_rows,
                game,
                reputation_map=reputation_map,
                existing_seats_by_championship=existing_seats_by_championship,
            )
        )
    return sorted(
        seats,
        key=lambda seat: (
            -_safe_int(seat.get("prestige"), 0),
            -_safe_int(seat.get("team_reputation"), 50),
            -_safe_int(seat.get("team_prestige"), 50),
            str(seat.get("championship_name", "")),
            str(seat.get("team_name", "")),
            _safe_int(seat.get("seat_index"), 1),
        ),
    )


def player_entry_prestige_for_style(
    save_name: str,
    player_names: list[str],
    style: str,
    championship_rows: list[dict[str, Any]] | None = None,
    game: str = "iRacing",
    driver_rows: list[sqlite3.Row] | None = None,
    reputation_map: dict[str, int] | None = None,
    existing_seats_by_championship: dict[tuple[str, str], list[dict[str, Any]]] | None = None,
) -> int:
    initialize_driver_pool(save_name)
    normalized_style = _normalize_style(style)
    player_set = {str(name).strip() for name in player_names if str(name).strip()}
    if not player_set:
        return 0

    if driver_rows is None:
        with _connect(save_name) as connection:
            rows = connection.execute(
                """
                SELECT name, is_human, primary_style, mmr, career_starts, current_championship
                FROM drivers
                WHERE status = 'active'
                """
            ).fetchall()
    else:
        rows = driver_rows

    ai_draft_rows: list[tuple[int, int, str]] = []
    player_ratings: list[int] = []
    player_buckets: list[int] = []
    player_row_count = 0
    fresh_player_row_count = 0
    for row in rows:
        name = str(row["name"])
        primary_style = str(row["primary_style"])
        effective_mmr = _effective_style_mmr(
            int(row["mmr"]),
            primary_style,
            normalized_style,
        )
        if bool(row["is_human"]) and name in player_set:
            player_row_count += 1
            player_ratings.append(effective_mmr)
            player_buckets.append(_style_draft_bucket(primary_style, normalized_style))
            if (
                int(row["career_starts"] or 0) == 0
                and not str(row["current_championship"] or "").strip()
            ):
                fresh_player_row_count += 1
        else:
            ai_draft_rows.append(
                (
                    _style_draft_bucket(primary_style, normalized_style),
                    effective_mmr,
                    name,
                )
            )

    if not player_ratings:
        return 0

    if championship_rows is None:
        championship_rows = load_championship_rows(game)

    style_rows = [
        row
        for row in championship_rows
        if _normalize_style(str(row.get("Style", ""))) == normalized_style
    ]
    if not style_rows:
        return 0
    minimum_prestige = min((_safe_int(row.get("Prestige"), 0) for row in style_rows), default=0)

    if player_row_count > 0 and fresh_player_row_count == player_row_count:
        return minimum_prestige
    if not ai_draft_rows:
        return minimum_prestige

    group_effective_mmr = round(sum(player_ratings) / len(player_ratings))
    group_style_bucket = min(player_buckets) if player_buckets else 1
    draft_pool = sorted(
        [("player", "__player__", group_style_bucket, group_effective_mmr)]
        + [("ai", driver_name, bucket, rating) for bucket, rating, driver_name in ai_draft_rows],
        key=lambda item: (item[2], -item[3], item[0], item[1]),
    )
    player_pick_index = next(
        (index for index, row in enumerate(draft_pool) if row[0] == "player"),
        len(draft_pool),
    )
    seat_entries = _draft_ordered_seat_entries(
        save_name,
        normalized_style,
        style_rows,
        game,
        reputation_map=reputation_map,
        existing_seats_by_championship=existing_seats_by_championship,
    )
    if player_pick_index < len(seat_entries):
        return _safe_int(seat_entries[player_pick_index].get("prestige"), 0)
    return minimum_prestige


def list_drivers_page(
    save_name: str,
    include_retired: bool = False,
    discipline: str = "All",
    tier: str = "All",
    search: str = "",
    sort_by: str = "MMR",
    driver_names: set[str] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    initialize_driver_pool(save_name)
    clauses = []
    params: list[Any] = []
    if not include_retired:
        clauses.append("status = 'active'")
    if discipline != "All":
        clauses.append("current_style = ?")
        params.append(discipline)
    if tier != "All":
        clauses.append("current_tier = ?")
        params.append(int(tier))
    cleaned_search = str(search).strip()
    if cleaned_search:
        clauses.append("LOWER(name) LIKE ?")
        params.append(f"%{cleaned_search.casefold()}%")
    cleaned_driver_names = sorted(str(name).strip() for name in (driver_names or set()) if str(name).strip())
    if driver_names is not None:
        if cleaned_driver_names:
            placeholders = ", ".join("?" for _name in cleaned_driver_names)
            clauses.append(f"name IN ({placeholders})")
            params.extend(cleaned_driver_names)
        else:
            clauses.append("1 = 0")
    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    order_options = {
        "Name": "name ASC",
        "Wins": "wins DESC, podiums DESC, championships DESC, mmr DESC, name ASC",
        "Podiums": "podiums DESC, wins DESC, championships DESC, mmr DESC, name ASC",
        "Titles": "championships DESC, wins DESC, podiums DESC, mmr DESC, name ASC",
        "Seasons": "seasons_completed DESC, championships DESC, wins DESC, mmr DESC, name ASC",
        "MMR": "mmr DESC, championships DESC, wins DESC, name ASC",
    }
    order_clause = order_options.get(sort_by, order_options["MMR"])

    with _connect(save_name) as connection:
        total_row = connection.execute(
            f"SELECT COUNT(*) AS total FROM drivers {where_clause}",
            params,
        ).fetchone()
        rows = connection.execute(
            f"""
            SELECT
                id,
                name,
                is_human,
                status,
                primary_style,
                mmr,
                seasons_completed,
                career_starts,
                wins,
                podiums,
                championships,
                current_tier,
                current_style,
                current_championship,
                retirement_after_seasons
            FROM drivers
            {where_clause}
            ORDER BY
                CASE WHEN status = 'active' THEN 0 ELSE 1 END,
                is_human DESC,
                {order_clause}
            LIMIT ? OFFSET ?
            """,
            [*params, max(1, int(limit)), max(0, int(offset))],
        ).fetchall()
    return [dict(row) for row in rows], int(total_row["total"] if total_row else 0)


def _retirement_target() -> int:
    import random

    return random.randint(12, 20)
