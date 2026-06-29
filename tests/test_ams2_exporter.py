from __future__ import annotations

from pathlib import Path

from circuit_stackers import ams2_exporter
from circuit_stackers.ams2_exporter import _build_driver_stats


def test_build_driver_stats_defaults_new_scalars_to_one() -> None:
    stats = _build_driver_stats({}, 80, normalized_race_skill=0.8)

    assert stats["weight_scalar"] == "1.000"
    assert stats["power_scalar"] == "1.000"
    assert stats["drag_scalar"] == "1.000"
    assert stats["setup_downforce"] == "0.500"
    assert stats["setup_downforce_randomness"] == "0.350"


def test_build_driver_stats_preserves_explicit_scalars() -> None:
    stats = _build_driver_stats(
        {
            "ams2_weight_scalar": 0.9,
            "ams2_power_scalar": 1.1,
            "ams2_drag_scalar": 0.9,
        },
        80,
        normalized_race_skill=0.8,
    )

    assert stats["weight_scalar"] == "0.900"
    assert stats["power_scalar"] == "1.100"
    assert stats["drag_scalar"] == "0.900"


def test_build_driver_stats_preserves_setup_downforce_values() -> None:
    stats = _build_driver_stats(
        {
            "ams2_setup_downforce": 0.35,
            "ams2_setup_downforce_randomness": 0.35,
        },
        80,
        normalized_race_skill=0.8,
    )

    assert stats["setup_downforce"] == "0.350"
    assert stats["setup_downforce_randomness"] == "0.350"


def test_validate_ams2_roster_files_accepts_player_exported_in_xml(tmp_path: Path, monkeypatch) -> None:
    custom_ai_dir = tmp_path / "UserData" / "CustomAIDrivers"
    custom_ai_dir.mkdir(parents=True)
    ams2_exporter._write_roster_xml(
        custom_ai_dir / "F-Vee.xml",
        [
            {"livery_name": "Daniel Rienda #5", "country": "USA", "name": "Alex Sumner", **_build_driver_stats({}, 80, normalized_race_skill=0.8)},
            {"livery_name": "Elisio Netto #12", "country": "USA", "name": "Theodore Clarke", **_build_driver_stats({}, 66, normalized_race_skill=0.66)},
        ],
    )
    monkeypatch.setattr(ams2_exporter, "game_directory", lambda _game: str(tmp_path))
    monkeypatch.setattr(
        ams2_exporter,
        "_livery_rows_for_class",
        lambda _class_name: [{"Roster_Name": "F-Vee.xml"}],
    )

    result = ams2_exporter.validate_ams2_roster_files(
        {"Championship": "Formula Vee Gen1"},
        [
            {"name": "Alex Sumner", "class_name": "Formula Vee Brazil Gen 1", "skill": 80},
            {"name": "Theodore Clarke", "class_name": "Formula Vee Brazil Gen 1", "skill": 66},
        ],
        ["Alex Sumner"],
    )

    assert result.ok is True
