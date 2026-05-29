from __future__ import annotations

import customtkinter as ctk
from datetime import datetime
from uuid import uuid4

from ..driver_pool import add_human_drivers
from ..game_logic import prepare_offseason_championship_select, save_needs_world_setup, simulate_world_history_year, start_championship
from ..save_manager import load_save, update_save


class WorldSetupScreen(ctk.CTkFrame):
    def __init__(self, parent, show_screen) -> None:
        super().__init__(parent, fg_color="transparent")
        self.parent = parent
        self.show_screen = show_screen
        self._running = False
        self._save_name = ""
        self._championship: dict | None = None
        self._player_names: list[str] = []
        self._player_car: dict | None = None
        self._starting_difficulty = 75
        self._years_remaining = 0
        self._total_years = 5
        self._status_lines: list[str] = []

        wrapper = ctk.CTkFrame(self, fg_color="transparent")
        wrapper.pack(expand=True)

        ctk.CTkLabel(
            wrapper,
            text="Setting up the world championships...",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(pady=(0, 8))
        self.detail_label = ctk.CTkLabel(
            wrapper,
            text="Building the world before your journey begins.",
            font=ctk.CTkFont(size=13),
            text_color="gray",
        )
        self.detail_label.pack(pady=(0, 16))
        self.status_label = ctk.CTkLabel(wrapper, text="", font=ctk.CTkFont(size=12), text_color="#4da6ff")
        self.status_label.pack()

    def set_request(
        self,
        save_name: str,
        championship: dict | None,
        player_names: list[str],
        player_car: dict | None,
        starting_difficulty: int,
    ) -> None:
        self._save_name = save_name
        self._championship = championship
        self._player_names = list(player_names)
        self._player_car = player_car
        self._starting_difficulty = starting_difficulty
        save_data = load_save(save_name) or {}
        self._total_years = max(5, min(20, int(save_data.get("world_history_years", 5) or 5)))
        self._years_remaining = self._total_years if save_needs_world_setup(save_data) else 0
        self._status_lines = []

    def on_show(self) -> None:
        if self._running:
            return
        if self._championship:
            self.detail_label.configure(text="Finalizing the world and placing you into your selected championship.")
        else:
            self.detail_label.configure(text="Simulating the world before you choose where your rookie career begins.")
        self._running = True
        self.status_label.configure(text="Preparing world data...")
        self.after(100, self._run_next_step)

    def _run_next_step(self) -> None:
        try:
            if not self._save_name:
                self._running = False
                self.show_screen("MenuScreen")
                return

            if self._years_remaining > 0:
                current_year = self._total_years - self._years_remaining + 1
                self.status_label.configure(
                    text=f"Simulating world history year {current_year} of {self._total_years}..."
                )
                self.update_idletasks()
                summary = simulate_world_history_year(self._save_name)
                self._status_lines.append(
                    f"Year {current_year}: {summary.get('championships', 0)} championships, "
                    f"{summary.get('races', 0)} races, {summary.get('teams', 0)} teams, "
                    f"{summary.get('rookies_added', 0)} rookies."
                )
                self._years_remaining -= 1
                if self._years_remaining == 0:
                    save_data = load_save(self._save_name) or {"save_name": self._save_name}
                    save_data["world_year"] = datetime.now().year
                    save_data["world_setup_complete"] = True
                    update_save(self._save_name, save_data)
                self.status_label.configure(text=self._status_lines[-1])
                self.after(75, self._run_next_step)
                return

            if not self._championship:
                self.status_label.configure(text="World setup complete. Choose your starting championship.")
                self.update_idletasks()
                add_human_drivers(self._save_name, self._player_names)
                prepare_offseason_championship_select(self._save_name, self._player_names)
                championship_screen = self.parent.screens["ChampionshipScreen"]
                championship_screen.save_name = self._save_name
                championship_screen.player_names = list(self._player_names)
                championship_screen.current_tier = 1
                championship_screen.starting_difficulty = self._starting_difficulty
                self._running = False
                self.show_screen("ChampionshipScreen")
                return

            self.status_label.configure(text="Finalizing your selected championship...")
            self.update_idletasks()
            state = start_championship(
                self._save_name,
                self._championship,
                player_names=self._player_names,
                player_car=self._player_car,
                starting_difficulty=self._starting_difficulty,
            )
            self._add_championship_start_messages(state)
            gameplay = self.parent.screens["GameplayScreen"]
            gameplay.load_state(state)
            self._running = False
            self.show_screen("GameplayScreen")
        except Exception as error:
            self._running = False
            championship_screen = self.parent.screens["ChampionshipScreen"]
            championship_screen.season_summary_message = f"Could not start championship: {error}"
            championship_screen.season_summary_color = "#ff5555"
            self.show_screen("ChampionshipScreen")

    def _add_championship_start_messages(self, state: dict) -> None:
        messages = self._championship_start_messages(state)
        if not messages:
            return
        existing_messages = list(state.get("messages") or [])
        state["messages"] = existing_messages + messages
        if self._save_name:
            update_save(self._save_name, {"messages": state["messages"]})

    def _championship_start_messages(self, state: dict) -> list[dict]:
        messages: list[dict] = []
        championship = state.get("championship") or {}
        championship_name = str(championship.get("Championship", "")).strip() or "your new championship"
        team_name = str((state.get("player_team_offer") or {}).get("team_name", "")).strip()
        player_car = str((state.get("player_car") or {}).get("Car", "")).strip()
        player_label = ", ".join(str(name).strip() for name in state.get("players", []) if str(name).strip()) or "Driver"
        sender = team_name or "Team Management"
        intro_lines = [
            f"{player_label},",
            "",
            f"Welcome to {team_name or 'the team'}. We are pleased to confirm your seat for the upcoming {championship_name} season.",
            "",
            "This is a serious opportunity and the expectations are clear: prepare well, keep the car clean, and build momentum every weekend. The team believes your current form has earned this chance, and now the focus shifts to turning that potential into results.",
        ]
        if player_car:
            intro_lines.append("")
            intro_lines.append(f"You will be assigned to the {player_car}.")
        intro_lines.extend(
            [
                "",
                "The first objective is consistency. If we can leave each round with strong points and steady progress, the bigger results will come.",
                "",
                "Welcome aboard. Let's get to work.",
                "",
                f"{sender}",
            ]
        )
        messages.append(self._message(f"Welcome to {team_name or championship_name}", "\n".join(intro_lines), sender=sender))

        team_colors = self._team_color_codes(state.get("player_team_offer") or {})
        if str(state.get("game", "iRacing")).strip().casefold() == "iracing" and team_colors:
            color_lines = [
                f"{player_label},",
                "",
                "If you would like to run the team's colors on your personal iRacing paint, use the following hex codes:",
                "",
            ]
            color_lines.extend(
                f"Color {index}: #{color}"
                for index, color in enumerate(team_colors, start=1)
            )
            color_lines.extend(
                [
                    "",
                    "These match the colors shown on your championship offer card and are pulled from the same color set used for generated iRacing AI paints.",
                    "",
                    f"{sender}",
                ]
            )
            message = self._message("Team Paint Colors", "\n".join(color_lines), sender=sender)
            message["team_colors"] = ",".join(team_colors)
            message["colors"] = team_colors
            messages.append(message)

        watch_drivers = [str(name).strip() for name in (state.get("watch_drivers") or []) if str(name).strip()]
        rising_driver = str(state.get("rising_driver", "")).strip()
        if watch_drivers or rising_driver:
            lines = [f"Driver to watch: {name}" for name in watch_drivers[:2]]
            if rising_driver:
                lines.append(f"On their way up: {rising_driver}")
            messages.append(self._message("Drivers To Watch", "\n".join(lines), sender="Race Control"))

        if str(state.get("game", "iRacing")).strip().casefold() == "ams2":
            restart_lines = [
                f"{player_label},",
                "",
                "Your AMS2 roster files have been exported for this championship.",
                "",
                "Before starting the season in-game, fully close and restart Automobilista 2 so the Custom AI roster reloads correctly. AMS2 can keep old roster data in memory if the game is already open.",
                "",
                "After restarting, set up the championship/race using the assigned roster and livery details from your messages.",
                "",
                "Race Control",
            ]
            messages.append(self._message("Restart AMS2 Before Racing", "\n".join(restart_lines), sender="Race Control"))

            player_liveries = state.get("player_liveries") or []
            if player_liveries:
                lines = ["Use this assigned livery when setting up the championship in AMS2."]
                for item in player_liveries:
                    driver_name = str(item.get("driver_name", "")).strip() or "Player"
                    livery_name = str(item.get("livery_name", "")).strip() or "-"
                    roster_name = str(item.get("roster_name", "")).strip()
                    detail = f"{driver_name}: {livery_name}"
                    if roster_name:
                        detail = f"{detail} ({roster_name})"
                    lines.append(detail)
                messages.append(self._message("Assigned AMS2 Livery", "\n".join(lines), sender="Race Control"))
        return messages

    @staticmethod
    def _message(title: str, body: str, sender: str = "Race Control") -> dict:
        return {
            "id": uuid4().hex,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "category": "Race Control",
            "sender": sender,
            "title": title,
            "body": body,
            "read": False,
        }

    @staticmethod
    def _team_color_codes(player_team_offer: dict) -> list[str]:
        raw_colors = str(player_team_offer.get("team_colors", "")).strip()
        colors = [color.strip().upper().lstrip("#") for color in raw_colors.split(",") if color.strip()]
        return [color for color in colors if len(color) == 6]
