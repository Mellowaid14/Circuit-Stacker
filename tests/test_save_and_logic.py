from __future__ import annotations

import json
from pathlib import Path

from circuit_stackers import game_logic, save_manager


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
