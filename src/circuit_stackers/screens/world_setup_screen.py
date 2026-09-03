from __future__ import annotations

import threading

import customtkinter as ctk
from datetime import datetime
from uuid import uuid4

from ..driver_pool import add_human_drivers, team_personality_for_identity
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
                save_name = self._save_name

                def worker() -> None:
                    try:
                        summary = simulate_world_history_year(save_name)
                    except Exception as error:
                        self.after(0, lambda err=error: self._finish_error(err))
                        return
                    self.after(0, lambda result=summary: self._finish_history_year(result))

                threading.Thread(target=worker, daemon=True).start()
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
            self._finish_error(error)

    def _finish_history_year(self, summary: dict) -> None:
        current_year = self._total_years - self._years_remaining + 1
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

    def _finish_error(self, error: Exception) -> None:
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
        player_team_offer = state.get("player_team_offer") or {}
        team_name = str(player_team_offer.get("team_name", "")).strip()
        player_car = str((state.get("player_car") or {}).get("Car", "")).strip()
        player_label = ", ".join(str(name).strip() for name in state.get("players", []) if str(name).strip()) or "Driver"
        sender = team_name or "Team Management"
        personality = self._team_personality(player_team_offer, str(state.get("game", "")).strip())
        intro_lines = self._team_welcome_lines(
            player_label=player_label,
            team_name=team_name,
            championship_name=championship_name,
            personality=personality,
            philosophy=str(player_team_offer.get("team_philosophy", "")).strip(),
            trajectory=str(player_team_offer.get("team_trajectory", "")).strip(),
        )
        if player_car:
            intro_lines.append("")
            intro_lines.append(f"You will be assigned to the {player_car}.")

        expectation = str(player_team_offer.get("team_expectation", "")).strip()
        if expectation:
            intro_lines.extend(
                [
                    "",
                    "Season expectation:",
                    expectation,
                ]
            )
        offer_reason = str(player_team_offer.get("team_offer_reason", "")).strip()
        trajectory = str(player_team_offer.get("team_trajectory", "")).strip()
        philosophy = str(player_team_offer.get("team_philosophy", "")).strip()
        if offer_reason or trajectory or philosophy:
            intro_lines.append("")
            if offer_reason:
                intro_lines.extend(
                    [
                        "Why this seat came your way:",
                        offer_reason,
                    ]
                )
            if trajectory or philosophy:
                identity_bits = []
                if trajectory:
                    identity_bits.append(f"{trajectory.title()} trajectory")
                if philosophy:
                    identity_bits.append(f"{philosophy} philosophy")
                intro_lines.append("Team identity: " + " | ".join(identity_bits))

        team_colors = self._team_color_codes(state.get("player_team_offer") or {})
        if str(state.get("game", "iRacing")).strip().casefold() == "iracing" and team_colors:
            intro_lines.extend(
                [
                    "",
                    "Team colors for your iRacing paint:",
                    "",
                ]
            )
            intro_lines.extend(f"Color {index}: #{color}" for index, color in enumerate(team_colors, start=1))
        intro_lines.extend(self._team_welcome_closing(personality, sender))
        welcome_message = self._message(
            f"Welcome to {team_name or championship_name}",
            "\n".join(intro_lines),
            sender=sender,
            category="Team Message",
        )
        if team_colors:
            welcome_message["team_colors"] = ",".join(team_colors)
            welcome_message["colors"] = team_colors
        messages.append(welcome_message)

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
    def _message(title: str, body: str, sender: str = "Race Control", category: str = "Race Control") -> dict:
        return {
            "id": uuid4().hex,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "category": category,
            "sender": sender,
            "title": title,
            "body": body,
            "read": False,
        }

    @staticmethod
    def _team_personality(player_team_offer: dict, game: str) -> str:
        personality = str(player_team_offer.get("team_personality", "")).strip()
        if personality:
            return personality
        return team_personality_for_identity(
            str(player_team_offer.get("team_id", "")).strip(),
            str(player_team_offer.get("team_name", "")).strip(),
            game,
        )

    @staticmethod
    def _team_welcome_lines(
        *,
        player_label: str,
        team_name: str,
        championship_name: str,
        personality: str,
        philosophy: str = "",
        trajectory: str = "",
    ) -> list[str]:
        team_label = team_name or "the team"
        normalized = personality.strip().casefold()
        openings = {
            "aggressive": (
                f"Welcome to {team_label}. We did not offer this seat to cruise around and collect polite finishes.",
                f"The target in {championship_name} is simple: attack the weekends, take the space that is there, and make the paddock notice us early.",
            ),
            "development": (
                f"Welcome to {team_label}. We see this {championship_name} seat as the start of a proper build.",
                "The focus is clean feedback, steady progression, and turning every session into something useful for the next round.",
            ),
            "data-driven": (
                f"Welcome to {team_label}. Your seat for {championship_name} is confirmed, and the work now moves into execution.",
                "We will be watching consistency, race pace, avoidable mistakes, and how well each weekend plan turns into points.",
            ),
            "underdog": (
                f"Welcome to {team_label}. Not everyone outside this garage will expect much from us in {championship_name}.",
                "That is fine. We like it that way. Keep the car pointed forward, steal every point available, and we can make this season uncomfortable for bigger teams.",
            ),
            "prestige": (
                f"Welcome to {team_label}. This seat in {championship_name} carries standards, and we expect you to meet them.",
                "Preparation, discipline, and composure matter here. Results are important, but so is how you represent the badge every weekend.",
            ),
            "family": (
                f"Welcome to {team_label}. This is a close group, and we are glad to have you with us for {championship_name}.",
                "Trust the people around you, keep communication honest, and we will give you everything we can from the pit wall.",
            ),
        }
        opening, focus = openings.get(
            normalized,
            (
                f"Welcome to {team_label}. We are pleased to confirm your seat for the upcoming {championship_name} season.",
                "This is a serious opportunity: prepare well, keep the car clean, and build momentum every weekend.",
            ),
        )
        philosophy_line = WorldSetupScreen._team_philosophy_welcome_line(philosophy, trajectory, championship_name)
        return [
            f"{player_label},",
            "",
            opening,
            "",
            focus,
            *([ "", philosophy_line ] if philosophy_line else []),
        ]

    @staticmethod
    def _team_philosophy_welcome_line(philosophy: str, trajectory: str, championship_name: str) -> str:
        normalized = str(philosophy).strip().casefold()
        trend = str(trajectory).strip().casefold()
        trend_text = ""
        if trend == "rising":
            trend_text = " The garage feels like it is climbing."
        elif trend == "falling":
            trend_text = " There is real urgency around this campaign."
        elif trend == "rebuilding":
            trend_text = " This season is being treated like a reset."
        lines = {
            "win now": f"This team is in win-now mode for {championship_name}: results will be judged quickly.{trend_text}",
            "driver continuity": f"This group values continuity, trust, and building a season together over abrupt changes.{trend_text}",
            "technical excellence": f"The emphasis here is technical sharpness, clean execution, and making every session count.{trend_text}",
            "underdog grit": f"The plan is to scrap for everything available and make bigger programs work for every point.{trend_text}",
            "rookie pipeline": f"This program is built around development, upside, and turning raw pace into real racecraft.{trend_text}",
            "balanced": f"The team is looking for steady weekends, solid progress, and a season that builds properly.{trend_text}",
        }
        return lines.get(normalized, "").strip()

    @staticmethod
    def _team_welcome_closing(personality: str, sender: str) -> list[str]:
        normalized = personality.strip().casefold()
        closing = {
            "aggressive": "Bring the fight from round one.",
            "development": "Progress first, results next, and the bigger picture will take care of itself.",
            "data-driven": "Hit the marks, trust the process, and the results should follow.",
            "underdog": "Let them underestimate us. We will do the work.",
            "prestige": "Welcome aboard. Carry the standard.",
            "family": "Welcome aboard. We look after our own, and now that includes you.",
        }.get(normalized, "Welcome aboard. Let's get to work.")
        return [
            "",
            closing,
            "",
            f"{sender}",
        ]

    @staticmethod
    def _team_color_codes(player_team_offer: dict) -> list[str]:
        raw_colors = str(player_team_offer.get("team_colors", "")).strip()
        colors = [color.strip().upper().lstrip("#") for color in raw_colors.split(",") if color.strip()]
        return [color for color in colors if len(color) == 6]
