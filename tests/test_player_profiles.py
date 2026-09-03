from __future__ import annotations

from circuit_stackers import game_logic, player_profiles, settings_manager


def test_profiles_intersect_owned_content(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(player_profiles, "PROFILES_PATH", tmp_path / "player_profiles.json")
    first = player_profiles.list_player_profiles()[0]
    success, _message, second = player_profiles.create_player_profile("Co-op Partner")
    assert success is True
    assert second is not None

    iracing_cars = list(dict.fromkeys(
        str(row.get("id", "")).strip()
        for row in player_profiles.list_all_cars()
        if str(row.get("Game", "")).strip().casefold() in {"", "iracing"}
        and str(row.get("id", "")).strip()
    ))[:3]
    iracing_tracks = list(dict.fromkeys(
        str(row.get("Track", "")).strip()
        for row in player_profiles.list_all_tracks()
        if str(row.get("Game", "")).strip().casefold() in {"", "iracing"}
        and str(row.get("Track", "")).strip()
    ))[:3]
    assert len(iracing_cars) == 3
    assert len(iracing_tracks) == 3

    player_profiles.update_profile_owned_assets(first["id"], "iRacing", iracing_cars[:2], iracing_tracks[:2])
    player_profiles.update_profile_owned_assets(second["id"], "iRacing", iracing_cars[1:], iracing_tracks[1:])

    assert player_profiles.shared_owned_assets([first["id"], second["id"]], "iRacing") == (
        [iracing_cars[1]],
        [iracing_tracks[1]],
    )


def test_save_content_snapshot_overrides_global_ownership(monkeypatch) -> None:
    snapshot = {
        "game": "iRacing",
        "car_ids": ["shared-car"],
        "track_names": ["Shared Track"],
    }
    monkeypatch.setattr(
        game_logic,
        "load_save",
        lambda _save_name: {"player_profile_ids": ["one", "two"], "owned_content_snapshot": snapshot},
    )

    cars, tracks = game_logic._owned_assets_for_save("iRacing", "Co-op Career")

    assert cars == {"shared-car"}
    assert tracks == {"Shared Track"}


def test_profile_export_import_creates_portable_copy(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(player_profiles, "PROFILES_PATH", tmp_path / "player_profiles.json")
    original = player_profiles.list_player_profiles()[0]
    player_profiles.update_profile_owned_assets(original["id"], "iRacing", ["3", "7"], ["Adelaide"])
    export_path = tmp_path / "driver.csprofile"

    success, _message = player_profiles.export_player_profile(original["id"], export_path)
    imported_success, _import_message, imported = player_profiles.import_player_profile(export_path)

    assert success is True
    assert imported_success is True
    assert imported is not None
    assert imported["id"] != original["id"]
    assert imported["name"].endswith("(Imported)")
    assert player_profiles.profile_owned_assets(imported["id"], "iRacing") == (["3", "7"], ["Adelaide"])


def test_profile_can_be_renamed_and_promoted(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(player_profiles, "PROFILES_PATH", tmp_path / "player_profiles.json")
    original = player_profiles.list_player_profiles()[0]
    success, _message, second = player_profiles.create_player_profile("Second Driver")
    assert success is True
    assert second is not None

    renamed, _message = player_profiles.rename_player_profile(second["id"], "Team Mate")
    promoted, _message = player_profiles.set_default_profile(second["id"])

    assert renamed is True
    assert promoted is True
    assert player_profiles.default_profile_id() == second["id"]
    assert player_profiles.get_player_profile(second["id"])["name"] == "Team Mate"
    assert player_profiles.delete_player_profile(original["id"])[0] is True


def test_invalid_settings_json_falls_back_to_defaults(tmp_path, monkeypatch) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(settings_manager, "SETTINGS_PATH", settings_path)

    loaded = settings_manager.load_settings()

    assert loaded["settings_schema_version"] == settings_manager.SETTINGS_SCHEMA_VERSION
    assert loaded["iracing_directory"] == ""
    assert settings_path.read_text(encoding="utf-8") == "{broken"
