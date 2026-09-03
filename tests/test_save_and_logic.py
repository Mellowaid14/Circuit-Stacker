from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from circuit_stackers import driver_pool, game_logic, save_manager


def test_create_and_list_save(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(save_manager, "SAVES_DIR", tmp_path)

    success, message = save_manager.create_save("RookieRun", {"tier": 1, "championship": None})
    saved = json.loads((tmp_path / "RookieRun.json").read_text(encoding="utf-8"))

    assert success is True
    assert message == "Save created!"
    assert save_manager.list_saves() == ["RookieRun"]
    assert saved["world_db_name"].startswith("RookieRun_")


def test_new_saves_get_distinct_world_databases_when_names_sanitize_the_same(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(save_manager, "SAVES_DIR", tmp_path)

    save_manager.create_save("Heat check", {"tier": 1})
    save_manager.create_save("Heat_check", {"tier": 1})

    first_path = save_manager.world_db_path("Heat check")
    second_path = save_manager.world_db_path("Heat_check")

    assert first_path != second_path
    assert first_path.name.startswith("Heat_check_")
    assert second_path.name.startswith("Heat_check_")


def test_create_save_rejects_path_like_and_reserved_names(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(save_manager, "SAVES_DIR", tmp_path)

    for invalid_name in ("../OtherFolder", "bad/name", "CON", "career?.json"):
        success, message = save_manager.create_save(invalid_name, {"tier": 1})
        assert success is False
        assert message

    assert list(tmp_path.glob("*.json")) == []


def test_corrupt_save_is_not_overwritten_by_update(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(save_manager, "SAVES_DIR", tmp_path)
    corrupt_path = tmp_path / "Damaged.json"
    corrupt_path.write_text("{not valid json", encoding="utf-8")

    assert save_manager.load_save("Damaged") is None
    assert save_manager.update_save("Damaged", {"score": 10}) is False
    assert corrupt_path.read_text(encoding="utf-8") == "{not valid json"


def test_player_team_offer_builds_fallback_key_without_crashing() -> None:
    standings = [{"name": "Player One"}, {"name": "AI One"}]
    offer = {
        "team_id": "team-7",
        "team_name": "Test Racing",
        "team_prestige": 20,
        "team_reputation": 55,
    }

    updated = game_logic._apply_player_team_offer(standings, ["Player One"], offer, "iRacing")

    assert updated[0]["team_key"] == "iracing|team-7"
    assert updated[0]["team_name"] == "Test Racing"
    assert "team_name" not in updated[1]


def test_start_championship_persists_schedule_and_standings(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(save_manager, "SAVES_DIR", tmp_path)
    monkeypatch.setattr(game_logic, "update_save", save_manager.update_save)

    save_manager.create_save("TestDriver", {"tier": 1, "championship": None})
    championship = {
        "id": "mx5-test",
        "Championship_ID": "mx5-test",
        "Championship": "Mazda MX-5 Cup",
        "Tier": "1",
        "Car": "MX-5",
        "Style": "Sports Car",
        "Num of Races": "4",
        "Game": "Iracing",
        "Max_Opp": "8",
    }
    player_car = {"id": "mx5", "Car": "MX-5", "Car class": "MX-5", "Car_Class_ID": "1"}
    standings = [
        {
            "name": "TestDriver" if index == 0 else f"AI {index}",
            "class_name": "MX-5",
            "points": 0,
            "wins": 0,
        }
        for index in range(8)
    ]

    class FakeAdapter:
        @staticmethod
        def export_championship_assets(*_args, **_kwargs):
            return Path("roster.json"), Path("season.json"), []

    monkeypatch.setattr(game_logic, "_championship_group_rows", lambda *_args: [championship])
    monkeypatch.setattr(game_logic, "_class_names_for_rows", lambda *_args: ["MX-5"])
    monkeypatch.setattr(game_logic, "load_tracks", lambda *_args: [{}])
    monkeypatch.setattr(
        game_logic,
        "build_schedule",
        lambda *_args, **_kwargs: [
            {"race_num": number, "track": f"Track {number}", "completed": False, "result": None}
            for number in range(1, 5)
        ],
    )
    monkeypatch.setattr(game_logic, "set_human_primary_style_if_unassigned", lambda *_args: None)
    monkeypatch.setattr(game_logic, "build_standings_from_pool", lambda *_args: list(standings))
    monkeypatch.setattr(game_logic, "assign_driver_classes", lambda rows, *_args: rows)
    monkeypatch.setattr(
        game_logic,
        "_populate_world_with_player_championship",
        lambda _save, _champ, _schedule, rows, _size: (rows, {}),
    )
    monkeypatch.setattr(game_logic, "assign_teams_to_standings", lambda rows, *_args: rows)
    monkeypatch.setattr(game_logic, "add_ai_drivers_from_standings", lambda *_args: None)
    monkeypatch.setattr(game_logic, "set_ai_primary_style_on_first_championship", lambda *_args: None)
    monkeypatch.setattr(game_logic, "set_current_championship_for_standings", lambda *_args: None)
    monkeypatch.setattr(game_logic, "championship_cars", lambda *_args: [player_car])
    monkeypatch.setattr(game_logic, "get_game_adapter", lambda *_args: FakeAdapter())
    monkeypatch.setattr(
        game_logic,
        "championship_storyline_drivers",
        lambda *_args: {"watch_drivers": [], "rising_driver": None},
    )

    state = game_logic.start_championship("TestDriver", championship, player_car=player_car)
    saved = json.loads((tmp_path / "TestDriver.json").read_text(encoding="utf-8"))

    assert state["championship"]["Championship"] == "Mazda MX-5 Cup"
    assert len(state["schedule"]) == 4
    assert len(state["standings"]) == 8
    assert saved["current_race"] == 0
    assert saved["championship"]["Championship"] == "Mazda MX-5 Cup"


def test_simulate_race_marks_event_complete_and_awards_points(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(save_manager, "SAVES_DIR", tmp_path)
    monkeypatch.setattr(game_logic, "update_save", save_manager.update_save)

    save_manager.create_save("DriverOne", {"tier": 1, "championship": None})
    state = {
        "save_name": "DriverOne",
        "tier": 1,
        "score": 0,
        "championship": {"Championship": "Mini Season"},
        "schedule": [
            {
                "race_num": 1,
                "track": "Okayama",
                "layout": "Full",
                "country": "",
                "time_of_day": "Morning",
                "weather": "Sunny",
                "date": "1 Jan",
                "completed": False,
                "result": None,
            }
        ],
        "standings": [
            {"name": "DriverOne", "nationality": "Player", "skill": 80, "points": 0, "wins": 0},
            {"name": "AI One", "nationality": "American", "skill": 60, "points": 0, "wins": 0},
        ],
        "current_race": 0,
    }
    monkeypatch.setattr(game_logic, "world_simulated_finish_order", lambda *_args: ["DriverOne", "AI One"])
    monkeypatch.setattr(game_logic, "update_ratings_after_race", lambda *_args: None)
    monkeypatch.setattr(game_logic, "record_driver_race_results", lambda *_args: None)
    monkeypatch.setattr(game_logic, "_persist_active_state", lambda *_args: None)
    monkeypatch.setattr(game_logic, "_sync_iracing_season_difficulty", lambda *_args: None)

    updated = game_logic.simulate_race(state)

    assert updated["current_race"] == 1
    assert updated["schedule"][0]["completed"] is True
    assert updated["schedule"][0]["result"] == {"DriverOne": 1}
    assert sum(driver["points"] for driver in updated["standings"]) == 43


def test_rivals_mode_hydrates_and_persists_active_career_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(save_manager, "SAVES_DIR", tmp_path)
    monkeypatch.setattr(game_logic, "update_save", save_manager.update_save)

    save_manager.create_save(
        "RivalSave",
        {
            "game": "iRacing",
            "career_mode": "Rivals",
            "players": ["Alex", "Blake"],
            "all_players": ["Alex", "Blake"],
            "active_player_name": "Alex",
            "player_perspectives": {"Alex": {"rivalry_heat": {}, "messages": []}, "Blake": {"rivalry_heat": {}, "messages": []}},
            "player_careers": {
                "Alex": {
                    "players": ["Alex"],
                    "tier": 2,
                    "unlocked_tier": 2,
                    "championship": {"Championship": "Alex Cup", "Tier": "2"},
                    "schedule": [{"race_num": 1, "completed": False}],
                    "standings": [{"name": "Alex", "points": 0, "wins": 0}],
                    "current_race": 0,
                },
                "Blake": {
                    "players": ["Blake"],
                    "tier": 4,
                    "unlocked_tier": 4,
                    "championship": {"Championship": "Blake Trophy", "Tier": "4"},
                    "schedule": [{"race_num": 1, "completed": True}],
                    "standings": [{"name": "Blake", "points": 25, "wins": 1}],
                    "current_race": 1,
                },
            },
        },
    )

    alex_state = game_logic.hydrate_active_rivals_state(save_manager.load_save("RivalSave"))
    alex_state["current_race"] = 1
    game_logic._persist_active_state(alex_state)

    saved = save_manager.load_save("RivalSave")
    assert saved["players"] == ["Alex", "Blake"]
    assert saved["player_careers"]["Alex"]["current_race"] == 1
    assert saved["player_careers"]["Blake"]["current_race"] == 1

    save_manager.update_save("RivalSave", {"active_player_name": "Blake"})
    blake_state = game_logic.hydrate_active_rivals_state(save_manager.load_save("RivalSave"))

    assert blake_state["players"] == ["Blake"]
    assert blake_state["all_players"] == ["Alex", "Blake"]
    assert blake_state["championship"]["Championship"] == "Blake Trophy"


def test_rivals_empty_active_career_does_not_inherit_stale_top_level_championship() -> None:
    state = game_logic.hydrate_active_rivals_state(
        {
            "save_name": "Rivals",
            "game": "iRacing",
            "career_mode": "Rivals",
            "players": ["Alex", "Blake"],
            "all_players": ["Alex", "Blake"],
            "active_player_name": "Blake",
            "championship": {"Championship": "Alex Cup", "Tier": "1"},
            "schedule": [{"race_num": 1, "completed": False}],
            "standings": [{"name": "Alex", "points": 0, "wins": 0}],
            "current_race": 0,
            "player_careers": {
                "Alex": {
                    "players": ["Alex"],
                    "championship": {"Championship": "Alex Cup", "Tier": "1"},
                    "schedule": [{"race_num": 1, "completed": False}],
                    "standings": [{"name": "Alex", "points": 0, "wins": 0}],
                    "current_race": 0,
                },
                "Blake": {},
            },
        }
    )

    assert state["players"] == ["Blake"]
    assert state["championship"] is None
    assert state["schedule"] == []
    assert state["standings"] == []


def test_rivals_waits_for_every_driver_before_offseason(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(save_manager, "SAVES_DIR", tmp_path)

    save_manager.create_save(
        "RivalWait",
        {
            "game": "iRacing",
            "career_mode": "Rivals",
            "players": ["Alex", "Blake"],
            "all_players": ["Alex", "Blake"],
            "active_player_name": "Alex",
            "player_careers": {
                "Alex": {
                    "players": ["Alex"],
                    "championship": {"Championship": "Alex Cup"},
                    "schedule": [{"race_num": 1, "completed": True}],
                    "standings": [{"name": "Alex", "points": 20, "wins": 1}],
                    "current_race": 1,
                },
                "Blake": {
                    "players": ["Blake"],
                    "championship": {"Championship": "Blake Trophy"},
                    "schedule": [{"race_num": 1, "completed": False}, {"race_num": 2, "completed": False}],
                    "standings": [{"name": "Blake", "points": 0, "wins": 0}],
                    "current_race": 1,
                },
            },
        },
    )

    assert game_logic.rivals_waiting_for_drivers("RivalWait") == ["Blake"]
    assert game_logic.rivals_all_active_seasons_complete("RivalWait") is False

    saved = save_manager.load_save("RivalWait")
    saved["player_careers"]["Blake"]["current_race"] = 2
    saved["player_careers"]["Blake"]["schedule"][1]["completed"] = True
    save_manager.update_save("RivalWait", saved)

    assert game_logic.rivals_waiting_for_drivers("RivalWait") == []
    assert game_logic.rivals_all_active_seasons_complete("RivalWait") is True


def test_rivals_finalize_batches_all_completed_careers_once(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(save_manager, "SAVES_DIR", tmp_path)
    monkeypatch.setattr(game_logic, "update_save", save_manager.update_save)
    finalized: list[tuple[str, bool]] = []
    advanced: list[int] = []

    def fake_finalize_driver_season(_save_name, championship, _standings, advance_world_year=True):
        finalized.append((championship.get("Championship", ""), advance_world_year))
        return {
            "champions": [],
            "retired": 0,
            "forced_retired": 0,
            "rookies_added": 0,
            "next_world_year": 2026,
        }

    def fake_advance_world_year(_save_name, years=1):
        advanced.append(years)
        return 2027

    monkeypatch.setattr(game_logic, "finalize_driver_season", fake_finalize_driver_season)
    monkeypatch.setattr(game_logic, "advance_world_year", fake_advance_world_year)

    save_manager.create_save(
        "RivalBatch",
        {
            "game": "iRacing",
            "career_mode": "Rivals",
            "players": ["Alex", "Blake"],
            "all_players": ["Alex", "Blake"],
            "active_player_name": "Blake",
            "player_perspectives": {"Alex": {"rivalry_heat": {}, "messages": []}, "Blake": {"rivalry_heat": {}, "messages": []}},
            "player_careers": {
                "Alex": {
                    "players": ["Alex"],
                    "tier": 1,
                    "unlocked_tier": 1,
                    "championship": {"Championship": "Alex Cup", "Tier": "1"},
                    "schedule": [{"race_num": 1, "completed": True}],
                    "standings": [{"name": "Alex", "points": 25, "wins": 1}],
                    "current_race": 1,
                    "world_sim_progress": {"instances": [], "complete": True, "summary": {}},
                },
                "Blake": {
                    "players": ["Blake"],
                    "tier": 2,
                    "unlocked_tier": 2,
                    "championship": {"Championship": "Blake Trophy", "Tier": "2"},
                    "schedule": [{"race_num": 1, "completed": True}],
                    "standings": [{"name": "Blake", "points": 25, "wins": 1}],
                    "current_race": 1,
                    "world_sim_progress": {"instances": [], "complete": True, "summary": {}},
                },
            },
        },
    )

    state = game_logic.hydrate_active_rivals_state(save_manager.load_save("RivalBatch"))
    new_state, summary = game_logic.finalize_season(state)
    saved = save_manager.load_save("RivalBatch")

    assert sorted(finalized) == [("Alex Cup", False), ("Blake Trophy", False)]
    assert advanced == [1]
    assert saved["player_careers"]["Alex"]["championship"] is None
    assert saved["player_careers"]["Blake"]["championship"] is None
    assert new_state["players"] == ["Blake"]
    assert summary["driver_pool"]["next_world_year"] == 2027


def test_team_reputation_moves_surface_in_queries(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(save_manager, "SAVES_DIR", tmp_path)

    save_manager.create_save("TeamWorld", {"game": "AMS2", "tier": 2})
    driver_pool.initialize_driver_pool("TeamWorld")
    world_db = save_manager.world_db_path("TeamWorld")

    with sqlite3.connect(world_db) as connection:
        now = "2026-06-29T12:00:00"
        connection.row_factory = sqlite3.Row
        connection.execute(
            """
            INSERT INTO team_reputations (
                team_key, team_id, team_name, game, base_prestige, reputation, current_strength,
                team_form, team_ambition, team_stability, team_development, team_financial_strength,
                team_capital, sponsor_backing, team_pressure, team_philosophy, trajectory, last_season_points, last_season_wins,
                last_season_titles, seasons_completed, championships, wins, podiums, last_championship,
                last_style, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ams2|unit-test-team-a",
                "unit-test-team-a",
                "Unit Test Apex",
                "AMS2",
                60,
                67,
                67,
                4,
                58,
                54,
                59,
                56,
                72,
                67,
                48,
                "Balanced",
                "rising",
                120,
                3,
                0,
                1,
                0,
                3,
                6,
                "Formula Test",
                "Open Wheel",
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO team_reputations (
                team_key, team_id, team_name, game, base_prestige, reputation, current_strength,
                team_form, team_ambition, team_stability, team_development, team_financial_strength,
                team_capital, sponsor_backing, team_pressure, team_philosophy, trajectory, last_season_points, last_season_wins,
                last_season_titles, seasons_completed, championships, wins, podiums, last_championship,
                last_style, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ams2|unit-test-team-b",
                "unit-test-team-b",
                "Unit Test Beacon",
                "AMS2",
                62,
                55,
                55,
                -5,
                51,
                47,
                49,
                50,
                34,
                39,
                61,
                "Win Now",
                "falling",
                72,
                0,
                0,
                1,
                0,
                0,
                1,
                "Formula Test",
                "Open Wheel",
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO team_reputation_history (
                id, team_key, team_id, team_name, championship_id, championship_name, season_year, game,
                previous_strength, new_strength, delta, previous_team_capital, new_team_capital, capital_delta,
                previous_sponsor_backing, new_sponsor_backing, sponsor_backing_delta, trajectory, points, wins, titles, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "hist-a",
                "ams2|unit-test-team-a",
                "unit-test-team-a",
                "Unit Test Apex",
                "formula-test",
                "Formula Test",
                2026,
                "AMS2",
                61,
                67,
                6,
                61,
                72,
                11,
                58,
                67,
                9,
                "rising",
                120,
                3,
                0,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO team_reputation_history (
                id, team_key, team_id, team_name, championship_id, championship_name, season_year, game,
                previous_strength, new_strength, delta, previous_team_capital, new_team_capital, capital_delta,
                previous_sponsor_backing, new_sponsor_backing, sponsor_backing_delta, trajectory, points, wins, titles, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "hist-b",
                "ams2|unit-test-team-b",
                "unit-test-team-b",
                "Unit Test Beacon",
                "formula-test",
                "Formula Test",
                2026,
                "AMS2",
                60,
                55,
                -5,
                43,
                34,
                -9,
                47,
                39,
                -8,
                "falling",
                72,
                0,
                0,
                now,
            ),
        )
        connection.commit()

    risers = driver_pool.recent_team_reputation_moves("TeamWorld", 2026, direction="rise", limit=3)
    fallers = driver_pool.recent_team_reputation_moves("TeamWorld", 2026, direction="fall", limit=3)
    teams, total = driver_pool.list_teams_page("TeamWorld")
    profile = driver_pool.get_team_profile("TeamWorld", "ams2|unit-test-team-a")
    latest_move = driver_pool.latest_team_reputation_move_for_year("TeamWorld", "ams2|unit-test-team-a", 2026)

    assert risers[0]["team_name"] == "Unit Test Apex"
    assert risers[0]["delta"] == 6
    assert risers[0]["capital_delta"] == 11
    assert risers[0]["sponsor_backing_delta"] == 9
    assert fallers[0]["team_name"] == "Unit Test Beacon"
    assert fallers[0]["delta"] == -5
    assert fallers[0]["capital_delta"] == -9
    assert total == 2
    apex_row = next(team for team in teams if team["team_name"] == "Unit Test Apex")
    assert apex_row["latest_strength_delta"] == 6
    assert apex_row["team_capital_band"] == "strong"
    assert apex_row["sponsor_backing_band"] == "national"
    assert profile is not None
    assert profile["reputation_history"][0]["delta"] == 6
    assert profile["reputation_history"][0]["capital_delta"] == 11
    assert profile["team"]["team_capital"] == 72
    assert profile["team"]["sponsor_backing"] == 67
    assert latest_move is not None
    assert latest_move["new_team_capital"] == 72
