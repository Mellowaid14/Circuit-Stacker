from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .ams2_exporter import export_ams2_roster
from .roster_exporter import export_roster
from .save_manager import load_save
from .season_exporter import export_season

@dataclass(frozen=True)
class GameAdapter:
    game_name: str
    import_button_text: str
    import_dialog_title: str
    supports_results_import: bool

    def export_championship_assets(
        self,
        save_name: str,
        championship: dict[str, Any],
        standings: list[dict[str, Any]],
        player_names: list[str],
        player_car: dict[str, str] | None,
        schedule: list[dict[str, Any]],
        starting_difficulty: int,
        existing_player_liveries: list[dict[str, str]] | None = None,
    ) -> tuple[str, str, list[dict[str, str]]]:
        if self.game_name == "iRacing":
            roster_path = export_roster(save_name, championship, standings, player_names, player_car)
            season_path = export_season(
                save_name,
                championship,
                standings,
                player_names,
                player_car,
                schedule,
                starting_difficulty=starting_difficulty,
            )
            return str(roster_path), str(season_path), []
        if self.game_name == "AMS2":
            roster_path, player_liveries = export_ams2_roster(
                save_name,
                championship,
                standings,
                player_names,
                player_car,
                existing_player_liveries=existing_player_liveries,
            )
            return str(roster_path), "", player_liveries
        return "", "", []

    def import_results(
        self,
        state: dict[str, Any],
        json_path: str,
        name_map: dict[str, str] | None = None,
    ) -> list[str]:
        if self.game_name == "iRacing":
            from .game_logic import import_iracing_results

            return import_iracing_results(state, json_path, name_map=name_map)
        if self.game_name == "AMS2":
            from .game_logic import import_ams2_results

            return import_ams2_results(state, json_path, name_map=name_map)
        raise ValueError(f"{self.game_name} results import is not implemented yet.")


IRACING_ADAPTER = GameAdapter(
    game_name="iRacing",
    import_button_text="Import iRacing Results JSON",
    import_dialog_title="Select iRacing Results JSON",
    supports_results_import=True,
)

AMS2_ADAPTER = GameAdapter(
    game_name="AMS2",
    import_button_text="Import AMS2 Results JSON",
    import_dialog_title="Select AMS2 Results JSON",
    supports_results_import=True,
)


def get_game_adapter(game: str) -> GameAdapter:
    return AMS2_ADAPTER if str(game).strip().casefold() == "ams2" else IRACING_ADAPTER


def adapter_for_save(save_name: str) -> GameAdapter:
    save_data = load_save(save_name) or {}
    return get_game_adapter(str(save_data.get("game", "iRacing")))
