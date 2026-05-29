from __future__ import annotations

import customtkinter as ctk

from ..game_logic import prepare_offseason_championship_select, run_world_simulation_step


class SimProgressScreen(ctk.CTkFrame):
    def __init__(self, parent, show_screen) -> None:
        super().__init__(parent, fg_color="transparent")
        self.parent = parent
        self.show_screen = show_screen
        self.gameplay_screen = None
        self._running = False
        self._mode = "season"
        self._offseason_request: dict | None = None

        wrapper = ctk.CTkFrame(self, fg_color="transparent")
        wrapper.pack(expand=True)

        self.title_label = ctk.CTkLabel(
            wrapper,
            text="Simming to next event...",
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        self.title_label.pack(pady=(0, 8))
        self.detail_label = ctk.CTkLabel(
            wrapper,
            text="The world calendar is running its races for this part of the season.",
            font=ctk.CTkFont(size=13),
            text_color="gray",
        )
        self.detail_label.pack(pady=(0, 16))
        self.status_label = ctk.CTkLabel(wrapper, text="", font=ctk.CTkFont(size=12), text_color="#4da6ff")
        self.status_label.pack()

    def set_gameplay_screen(self, gameplay_screen) -> None:
        self.gameplay_screen = gameplay_screen

    def set_offseason_request(
        self,
        save_name: str,
        player_names: list[str],
        next_tier: int,
        starting_difficulty: int,
    ) -> None:
        self._mode = "offseason"
        self._offseason_request = {
            "save_name": save_name,
            "player_names": list(player_names),
            "next_tier": int(next_tier),
            "starting_difficulty": int(starting_difficulty),
        }

    def on_show(self) -> None:
        if self._running:
            return
        self._running = True
        if self._mode == "offseason":
            self.title_label.configure(text="Teams picking drivers...")
            self.detail_label.configure(
                text="Teams are reviewing seats, making offers, and building the next season's grid."
            )
            self.status_label.configure(text="Opening the offseason team market...")
            self.after(100, self._run_offseason)
        else:
            self.title_label.configure(text="Simming to next event...")
            self.detail_label.configure(text="The world calendar is running its races for this part of the season.")
            self.status_label.configure(text="Preparing world races...")
            self.after(100, self._run_chunk)

    def _run_offseason(self) -> None:
        try:
            request = self._offseason_request or {}
            save_name = str(request.get("save_name", "")).strip()
            player_names = list(request.get("player_names") or [])
            if not save_name:
                self.show_screen("ChampionshipScreen")
                return

            self.status_label.configure(text="Teams are picking drivers and reserving open seats...")
            self.update_idletasks()
            reserved_instances = prepare_offseason_championship_select(save_name, player_names)
            self.status_label.configure(
                text=f"Team picks complete. {len(reserved_instances)} world championships reserved."
            )
            self.update_idletasks()

            championship_screen = self.parent.screens["ChampionshipScreen"]
            championship_screen.save_name = save_name
            championship_screen.player_names = player_names
            championship_screen.current_tier = int(request.get("next_tier", 1) or 1)
            championship_screen.starting_difficulty = int(request.get("starting_difficulty", 75) or 75)
            championship_screen.season_summary_message = ""
            championship_screen.season_summary_color = "gray"
            self._mode = "season"
            self._offseason_request = None
            self.after(250, lambda: self.show_screen("ChampionshipScreen"))
        except Exception as error:
            championship_screen = self.parent.screens["ChampionshipScreen"]
            championship_screen.season_summary_message = f"Could not prepare championship select: {error}"
            championship_screen.season_summary_color = "#ff5555"
            self._mode = "season"
            self._offseason_request = None
            self.show_screen("ChampionshipScreen")
        finally:
            self._running = False

    def _run_chunk(self) -> None:
        try:
            if self.gameplay_screen is None or not self.gameplay_screen.save_name:
                self.show_screen("GameplayScreen")
                return

            state = {
                "save_name": self.gameplay_screen.save_name,
                "game": getattr(self.gameplay_screen, "game", "iRacing"),
                "players": self.gameplay_screen.player_names,
                "starting_difficulty": self.gameplay_screen.starting_difficulty,
                "tier": self.gameplay_screen.tier,
                "unlocked_tier": self.gameplay_screen.unlocked_tier,
                "score": self.gameplay_screen.score,
                "championship": self.gameplay_screen.championship,
                "player_car": self.gameplay_screen.player_car,
                "player_liveries": getattr(self.gameplay_screen, "player_liveries", []),
                "watch_drivers": getattr(self.gameplay_screen, "watch_drivers", []),
                "rising_driver": getattr(self.gameplay_screen, "rising_driver", None),
                "rivalry_heat": getattr(self.gameplay_screen, "rivalry_heat", {}),
                "messages": getattr(self.gameplay_screen, "messages", []),
                "schedule": self.gameplay_screen.schedule,
                "standings": self.gameplay_screen.standings,
                "current_race": self.gameplay_screen.current_race,
                "world_sim_progress": self.gameplay_screen.world_sim_progress,
            }
            state = run_world_simulation_step(state)
            self.gameplay_screen.load_state(state)

            progress = state.get("world_sim_progress") or {}
            last_summary = progress.get("last_summary") or {}
            self.status_label.configure(
                text=(
                    f"Simmed {last_summary.get('championships', 0)} world championships, "
                    f"{last_summary.get('races', 0)} races."
                )
            )

            if self.gameplay_screen.current_race >= len(self.gameplay_screen.schedule):
                self.after(250, self.gameplay_screen._handle_season_completion)
            else:
                self.after(250, lambda: self.show_screen("GameplayScreen"))
        finally:
            self._running = False
