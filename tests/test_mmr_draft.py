from __future__ import annotations

from circuit_stackers import driver_pool as pool, save_manager


def test_race_mmr_sums_each_class_opponent_as_a_head_to_head_result(monkeypatch):
    monkeypatch.setattr(pool, "RACE_RATING_CHANGE_CAP", 100)
    changes = pool._elo_changes_for_finish_order(
        ["First", "Second", "Third", "Fourth"],
        {name: name for name in ("First", "Second", "Third", "Fourth")},
        {name: 1000 for name in ("First", "Second", "Third", "Fourth")},
    )

    # First beats three equally rated opponents: 3 * (1 - 0.5) * K(4) = +6.
    assert changes == {"First": 6, "Second": 2, "Third": -2, "Fourth": -6}


def test_initial_mmr_seed_uses_ten_prestige_point_bands():
    assert pool._initial_mmr_for_prestige(1) == 1000
    assert pool._initial_mmr_for_prestige(9) == 1000
    assert pool._initial_mmr_for_prestige(10) == 1050
    assert pool._initial_mmr_for_prestige(19) == 1050
    assert pool._initial_mmr_for_prestige(20) == 1100


def series(id_, prestige, style="Sports Car", size=4):
    return {"id": id_, "Championship_ID": "group-" + id_, "Championship": id_,
            "Prestige": str(prestige), "Tier": "1", "Style": style, "Game": "iRacing", "Max_Opp": str(size)}


def driver(name, mmr, human=False, starts=8):
    return {"id": name, "name": name, "mmr": mmr, "is_human": human,
            "primary_style": "Oval", "career_starts": starts, "seasons_completed": 1,
            "last_tier": 1, "last_style": "Oval", "last_series_id": "old", "current_championship": None}


def mock_seats(monkeypatch):
    monkeypatch.setattr(pool, "initialize_driver_pool", lambda *a: None)
    def seats(save, row, rows, game, **kwargs):
        return [dict(championship_id=row["id"], championship_name=row["Championship"],
                     prestige=int(row["Prestige"]), team_prestige=90-i, team_reputation=90-i,
                     team_name=f"Team {i}", team_key=f"t{i}", team_id=f"t{i}", seat_index=i,
                     seat_number=i+1, team_seat=1) for i in range(int(row["Max_Opp"]))]
    monkeypatch.setattr(pool, "_draft_seat_entries_for_championship", seats)


def test_global_rank_uses_all_disciplines_and_returns_row_ids(monkeypatch):
    mock_seats(monkeypatch)
    rows = [series("elite", 5, "Oval"), series("middle", 3), series("rookie", 1)]
    drivers = [driver(str(i), 1600-i) for i in range(5)] + [driver("Player", 1200, True)]
    result = pool.player_accessible_championship_ids_for_style("save", ["Player"], "Sports Car", rows, driver_rows=drivers)
    assert result == {"middle", "rookie"}


def test_fresh_human_only_gets_rookie_championships(monkeypatch):
    mock_seats(monkeypatch)
    rows = [series("elite", 20, "Sports Car"), series("rookie", 1, "Sports Car")]
    drivers = [driver("Veteran", 1400)] + [driver("Player", 1000, True, starts=0)]

    assert pool.player_accessible_championship_ids_for_style(
        "save", ["Player"], "Sports Car", rows, driver_rows=drivers
    ) == {"rookie"}


def test_equal_prestige_alternates_every_pick(monkeypatch):
    mock_seats(monkeypatch)
    rows = [series("B", 5), series("A", 5), series("C", 1)]
    seats = pool._draft_ordered_seat_entries("save", "Oval", rows, "iRacing")
    assert [s["championship_id"] for s in seats] == ["A", "B"] * 4 + ["C"] * 4


def test_low_rank_human_only_gets_global_lowest_prestige(monkeypatch):
    mock_seats(monkeypatch)
    rows = [series("elite", 5, "Oval"), series("rookie", 1)]
    drivers = [driver(str(i), 1600) for i in range(20)] + [driver("Player", 800, True)]
    assert pool.player_accessible_championship_ids_for_style("save", ["Player"], "Oval", rows, driver_rows=drivers) == set()
    assert pool.player_accessible_championship_ids_for_style("save", ["Player"], "Sports Car", rows, driver_rows=drivers) == {"rookie"}


def test_driver_team_selection_is_only_mmr():
    assert pool._driver_team_market_score(driver("rookie", 1200, starts=0), {"team_philosophy": "Win Now"}, 99) == 1200
    assert pool._driver_team_market_score(dict(driver("veteran", 1199), wins=100), {}, 99) == 1199


def test_world_draft_rookie_quota_rotation_and_unique_drivers(monkeypatch):
    candidates = [driver(f"Veteran {i:02}", 1500-i) for i in range(16)]
    candidates += [driver(f"Rookie {i}", 1000, starts=0) for i in range(4)]
    monkeypatch.setattr(pool, "_active_world_ai_rows", lambda *a: candidates)
    instances = [{"championship": series(id_, prestige), "field_size": 4, "standings": []}
                 for id_, prestige in [("A", 5), ("B", 5), ("C", 1), ("D", 1)]]
    filled, _ = pool.populate_world_sim_instances("save", instances)
    assert [d["mmr"] for d in filled[0]["standings"]] == [1500, 1498, 1496, 1494]
    assert [d["mmr"] for d in filled[1]["standings"]] == [1499, 1497, 1495, 1493]
    for instance in filled[2:]:
        assert sum(d["career_starts"] == 0 and d["mmr"] == 1000 for d in instance["standings"]) == 2
    ids = [d["driver_id"] for i in filled for d in i["standings"]]
    assert len(ids) == len(set(ids)) == 16


def test_human_fallback_replaces_rookie_seat(monkeypatch):
    candidates = [driver(f"Veteran {i}", 1500-i) for i in range(4)] + [driver("Rookie", 1000, starts=0)]
    monkeypatch.setattr(pool, "_active_world_ai_rows", lambda *a: candidates)
    human = {"driver_id": "human", "name": "Player", "mmr": 800, "nationality": "Player", "class_name": "Overall"}
    filled, _ = pool.populate_world_sim_instances("save", [{"championship": series("A", 1), "field_size": 4, "standings": [human]}])
    assert [d["mmr"] for d in filled[0]["standings"]] == [800, 1000, 1500, 1499]


def test_offers_are_capped_at_three_per_class(monkeypatch):
    mock_seats(monkeypatch)
    rows = [series("A", 5, size=8), series("B", 1)]
    monkeypatch.setattr(save_manager, "load_save", lambda *a: {})
    monkeypatch.setattr(pool, "load_championship_rows", lambda *a: rows)
    monkeypatch.setattr(pool, "player_draft_position_for_style", lambda *a: 2)
    monkeypatch.setattr(pool, "_team_colors_for_identity", lambda *a: "")
    monkeypatch.setattr(pool, "_team_personality_for_identity", lambda *a: "")
    offers = pool.team_offers_for_player("save", ["Player"], rows[0], max_offers=99)
    assert [offer["team_id"] for offer in offers] == ["t2", "t3", "t4"]


def test_fresh_human_cannot_receive_non_rookie_team_offers(monkeypatch):
    mock_seats(monkeypatch)
    rows = [series("elite", 20, size=8), series("rookie", 1, size=8)]
    monkeypatch.setattr(save_manager, "load_save", lambda *a: {})
    monkeypatch.setattr(pool, "load_championship_rows", lambda *a: rows)
    monkeypatch.setattr(pool, "players_are_fresh_rookies", lambda *a: True)

    assert pool.team_offers_for_player("save", ["Player"], rows[0]) == []


def test_unseated_ai_retires_but_human_is_protected(tmp_path, monkeypatch):
    monkeypatch.setattr(save_manager, "SAVES_DIR", tmp_path)
    save_manager.create_save("draft", {})
    pool.initialize_driver_pool("draft")
    for name, human in [("Player", True), ("Missed", False), ("Seated", False)]:
        pool.add_driver("draft", name, human, "Sports Car", None)
    with pool._connect("draft") as connection:
        connection.execute("UPDATE drivers SET current_championship='A' WHERE name='Seated'")
    pool.retire_unseated_ai("draft")
    with pool._connect("draft") as connection:
        states = dict(connection.execute("SELECT name,status FROM drivers WHERE name IN ('Player','Missed','Seated')"))
    assert states == {"Player": "active", "Missed": "retired", "Seated": "active"}


def test_mmr_survives_reopening_at_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr(save_manager, "SAVES_DIR", tmp_path)
    save_manager.create_save("reopen", {})
    pool.initialize_driver_pool("reopen")
    pool.add_driver("reopen", "Veteran", False, "Sports Car", None)
    with pool._connect("reopen") as connection:
        connection.execute("UPDATE drivers SET mmr=1000, sports_car_rating=1400, career_starts=10 WHERE name='Veteran'")
    pool._INITIALIZED_POOLS.clear()
    pool.initialize_driver_pool("reopen")
    with pool._connect("reopen") as connection:
        assert connection.execute("SELECT mmr FROM drivers WHERE name='Veteran'").fetchone()[0] == 1000


def test_team_prestige_picks_by_mmr_and_preserves_human_seat(monkeypatch):
    seats = [dict(team_id=str(i), team_key=str(i), team_name=str(i), team_seat=1, team_prestige=90-i*20) for i in range(3)]
    monkeypatch.setattr(pool, "_build_team_seat_plan", lambda *a: seats)
    human = dict(driver("Player", 1700, True), **seats[0])
    standings = [human, driver("Experienced", 1100), driver("Rookie", 1200, starts=0)]
    result = pool.assign_teams_to_standings(standings, series("A", 5))
    assert [(d["name"], d["team_id"]) for d in result] == [("Player", "0"), ("Experienced", "2"), ("Rookie", "1")]


def test_multiclass_lowest_prestige_has_rookie_intake(monkeypatch):
    candidates = [driver(f"Veteran {i}", 1500-i) for i in range(10)] + [driver(f"Rookie {i}", 1000, starts=0) for i in range(4)]
    monkeypatch.setattr(pool, "_active_world_ai_rows", lambda *a: candidates)
    championship = dict(series("Mixed", 1, size=8), _class_names=["A", "B"], _class_prestiges={"A": 1, "B": 1})
    filled, _ = pool.populate_world_sim_instances("save", [{"championship": championship, "field_size": 8, "standings": []}])
    for class_name in ("A", "B"):
        drivers = [d for d in filled[0]["standings"] if d["class_name"] == class_name]
        assert len(drivers) == 4
        assert sum(d["career_starts"] == 0 for d in drivers) == 2


def test_two_seasons_replace_rookies_and_force_unseated_retirement(tmp_path, monkeypatch):
    monkeypatch.setattr(save_manager, "SAVES_DIR", tmp_path)
    save_manager.create_save("seasons", {})
    pool.initialize_driver_pool("seasons")
    for i in range(12):
        pool.add_driver("seasons", f"Veteran {i}", False, "Sports Car", None)
    pool.add_driver("seasons", "Player", True, "Sports Car", None)
    with pool._connect("seasons") as connection:
        for i in range(12):
            connection.execute("UPDATE drivers SET mmr=?,career_starts=8 WHERE name=?", (1500-i, f"Veteran {i}"))
    previous_rookies = set()
    for season in range(2):
        instances = [{"championship": series(id_, prestige), "field_size": 4, "standings": []}
                     for id_, prestige in [("Advanced", 5), ("Entry", 1)]]
        filled, _ = pool.populate_world_sim_instances("seasons", instances)
        rookies = {d["driver_id"] for d in filled[1]["standings"] if d["career_starts"] == 0}
        assert len(rookies) == 2
        assert rookies.isdisjoint(previous_rookies)
        previous_rookies = rookies
        for instance in filled:
            pool.set_current_championship_for_standings("seasons", instance["standings"], instance["championship"])
        assert pool.retire_unseated_ai("seasons") == (6 if season == 0 else 2)
        with pool._connect("seasons") as connection:
            assert connection.execute("SELECT status FROM drivers WHERE name='Player'").fetchone()[0] == "active"
            connection.execute("UPDATE drivers SET career_starts=career_starts+4 WHERE current_championship IS NOT NULL")
            connection.execute("UPDATE drivers SET current_championship=NULL,current_style=NULL,current_tier=NULL")
