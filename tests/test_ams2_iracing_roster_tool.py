from __future__ import annotations

import json

from ams2_iracing_roster_tool import exporter


def test_bundle_and_championship_detection(tmp_path) -> None:
    slot = "rxdb-dexie-career-sim-slot-2--"
    (tmp_path / f"{slot}3--championships.json").write_text(
        json.dumps([{"id": "champ-1", "name": "Formula USA"}]),
        encoding="utf-8",
    )
    (tmp_path / f"{slot}1--championshipSeasons.json").write_text(
        json.dumps([{"id": "season-1", "championship_id": "champ-1"}]),
        encoding="utf-8",
    )
    (tmp_path / f"{slot}1--championshipEntry.json").write_text(json.dumps([]), encoding="utf-8")
    (tmp_path / f"{slot}0--drivers.json").write_text(json.dumps([]), encoding="utf-8")

    bundle = exporter.load_export_bundle(tmp_path)
    options = exporter.list_championship_options(bundle, "career-sim-slot-2")

    assert exporter.list_slot_keys(bundle) == ["career-sim-slot-2"]
    assert len(options) == 1
    assert options[0].label == "Formula USA"
    assert options[0].season_ids == ("season-1",)


def test_roster_resolution_and_stat_conversion(tmp_path) -> None:
    slot = "rxdb-dexie-career-sim-slot-2--"
    (tmp_path / f"{slot}3--championships.json").write_text(
        json.dumps([{"id": "champ-1", "name": "Formula USA", "car_class": "Dallara IR18"}]),
        encoding="utf-8",
    )
    (tmp_path / f"{slot}1--championshipSeasons.json").write_text(
        json.dumps([{"id": "season-1", "championship_id": "champ-1"}]),
        encoding="utf-8",
    )
    (tmp_path / f"{slot}1--championshipEntry.json").write_text(
        json.dumps([{"id": "entry-1", "championship_season_id": "season-1", "team_seat_id": "seat-1"}]),
        encoding="utf-8",
    )
    (tmp_path / f"{slot}5--teamSeats.json").write_text(
        json.dumps([{"id": "seat-1", "championship_entry_id": "entry-1"}]),
        encoding="utf-8",
    )
    (tmp_path / f"{slot}0--driverContracts.json").write_text(
        json.dumps([{"id": "contract-1", "team_seat_id": "seat-1", "driver_id": "driver-1"}]),
        encoding="utf-8",
    )
    (tmp_path / f"{slot}0--drivers.json").write_text(
        json.dumps(
            [
                {
                    "id": "driver-1",
                    "name": "Alex Driver",
                    "age": 24,
                    "race_skill": 0.84,
                    "aggression": 0.55,
                    "consistency": 0.72,
                    "stamina": 0.64,
                    "fuel_management": 0.61,
                    "tyre_management": 0.79,
                    "avoidance_of_forced_mistakes": 0.46,
                }
            ]
        ),
        encoding="utf-8",
    )

    bundle = exporter.load_export_bundle(tmp_path)
    option = exporter.list_championship_options(bundle, "career-sim-slot-2")[0]
    drivers = exporter.resolve_roster_drivers(bundle, option)
    payload = exporter.build_iracing_roster_payload(drivers, option, iracing_car=None)

    assert len(drivers) == 1
    assert payload["drivers"][0]["driverName"] == "Alex Driver"
    assert payload["drivers"][0]["driverSkill"] == 84
    assert payload["drivers"][0]["driverAggression"] == 55
    assert payload["drivers"][0]["driverOptimism"] == 68
    assert payload["drivers"][0]["driverSmoothness"] == 72
    assert payload["drivers"][0]["pitCrewSkill"] == 70
    assert payload["drivers"][0]["strategyRiskiness"] == 46
    assert payload["drivers"][0]["driverAge"] == 24
