from __future__ import annotations

import json

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


def test_start_championship_persists_schedule_and_standings(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(save_manager, "SAVES_DIR", tmp_path)
    monkeypatch.setattr(game_logic, "update_save", save_manager.update_save)

    save_manager.create_save("TestDriver", {"tier": 1, "championship": None})
    championship = {
        "Championship": "Mazda MX-5 Cup",
        "Tier": "1",
        "Car": "MX-5",
        "Style": "Sports Car",
        "Num of Races": "4",
        "Game": "Iracing",
        "Max_Opp": "8",
    }

    state = game_logic.start_championship("TestDriver", championship)
    saved = json.loads((tmp_path / "TestDriver.json").read_text(encoding="utf-8"))

    assert state["championship"]["Championship"] == "Mazda MX-5 Cup"
    assert len(state["schedule"]) == 4
    assert len(state["standings"]) == 9
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

    updated = game_logic.simulate_race(state)

    assert updated["current_race"] == 1
    assert updated["schedule"][0]["completed"] is True
    assert updated["schedule"][0]["result"] in {1, 2}
    assert sum(driver["points"] for driver in updated["standings"]) == 43
