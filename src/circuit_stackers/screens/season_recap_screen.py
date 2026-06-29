from __future__ import annotations

import customtkinter as ctk

from ..driver_pool import best_driver_in_world, latest_tier_champions, notable_retirements, top_rookies_for_year
from ..game_logic import load_world_championships


class SeasonRecapScreen(ctk.CTkFrame):
    def __init__(self, parent, show_screen) -> None:
        super().__init__(parent, fg_color="transparent")
        self.show_screen = show_screen
        self.parent = parent
        self.save_name: str | None = None
        self.player_names: list[str] = []
        self.championship_name = ""
        self.summary: dict = {}
        self.final_standings: list[dict] = []
        self.player_team_offer: dict = {}
        self.career_mode = "Solo"
        self.player_perspectives: dict[str, dict] = {}
        self.next_tier = 1
        self.starting_difficulty = 75

        ctk.CTkLabel(self, text="Season Recap", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(28, 4))
        self.subtitle_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=12), text_color="gray")
        self.subtitle_label.pack(pady=(0, 12))

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=18, pady=(0, 10))
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        left_box = self._make_box(content, "Season Summary")
        left_box.grid(row=0, column=0, padx=6, pady=6, sticky="nsew")
        self.summary_frame = ctk.CTkScrollableFrame(left_box, fg_color="transparent")
        self.summary_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        right_box = self._make_box(content, "Final Standings")
        right_box.grid(row=0, column=1, padx=6, pady=6, sticky="nsew")
        self.standings_frame = ctk.CTkScrollableFrame(right_box, fg_color="transparent")
        self.standings_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        button_row = ctk.CTkFrame(self, fg_color="transparent")
        button_row.pack(pady=(0, 8))
        ctk.CTkButton(
            button_row,
            text="Open Driver Pool",
            command=self.open_driver_pool,
            width=140,
            height=34,
            fg_color="gray30",
            hover_color="gray40",
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=(0, 8))
        self.continue_btn = ctk.CTkButton(
            button_row,
            text="Continue to Championship Select",
            command=self.continue_to_championship_select,
            width=240,
            height=36,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.continue_btn.pack(side="left")

    def _make_box(self, parent, title: str) -> ctk.CTkFrame:
        box = ctk.CTkFrame(parent, fg_color=("gray88", "gray17"), corner_radius=10)
        ctk.CTkLabel(
            box,
            text=title,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("#1a6fc4", "#4da6ff"),
        ).pack(anchor="w", padx=10, pady=(8, 4))
        return box

    def _info_row(self, parent, label: str, value: str) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=1)
        ctk.CTkLabel(
            row,
            text=label,
            font=ctk.CTkFont(size=11),
            text_color="gray",
            width=128,
            anchor="w",
        ).pack(side="left")
        ctk.CTkLabel(
            row,
            text=value,
            font=ctk.CTkFont(size=11),
            anchor="w",
            justify="left",
        ).pack(side="left", fill="x", expand=True)

    def _section_label(self, parent, text: str) -> None:
        ctk.CTkLabel(
            parent,
            text=text,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=("#1a6fc4", "#4da6ff"),
            anchor="w",
        ).pack(fill="x", pady=(8, 2))

    def set_recap(
        self,
        save_name: str,
        player_names: list[str],
        championship_name: str,
        summary: dict,
        final_standings: list[dict],
        next_tier: int,
        starting_difficulty: int,
    ) -> None:
        self.save_name = save_name
        self.player_names = list(player_names)
        self.championship_name = championship_name
        self.summary = dict(summary)
        self.final_standings = [dict(row) for row in final_standings]
        self.player_team_offer = dict(self.summary.get("player_team_offer") or {}) if isinstance(self.summary.get("player_team_offer"), dict) else {}
        self.career_mode = str(self.summary.get("career_mode") or ("Co-op" if len(self.player_names) > 1 else "Solo"))
        self.player_perspectives = {
            str(name): dict(value)
            for name, value in dict(self.summary.get("player_perspectives") or {}).items()
            if isinstance(value, dict)
        }
        self.next_tier = int(next_tier)
        self.starting_difficulty = int(starting_difficulty)

    def on_show(self) -> None:
        subtitle = self.championship_name or "Season complete"
        if self.save_name:
            subtitle = f"{subtitle} | Save: {self.save_name}"
        self.subtitle_label.configure(text=subtitle)
        self._refresh_summary()
        self._refresh_standings()

    def _refresh_summary(self) -> None:
        for widget in self.summary_frame.winfo_children():
            widget.destroy()

        summary = self.summary or {}
        driver_pool = summary.get("driver_pool") or {}
        world_sim = driver_pool.get("world_simulation") or {}
        world_retirements = int(driver_pool.get("retired", 0) or 0) + int(world_sim.get("retired", 0) or 0)
        world_forced_out = int(driver_pool.get("forced_retired", 0) or 0) + int(world_sim.get("forced_retired", 0) or 0)
        world_rookies = int(driver_pool.get("rookies_added", 0) or 0) + int(world_sim.get("rookies_added", 0) or 0)
        color = "#6bbd6b" if summary.get("new_tier", 1) >= summary.get("old_tier", 1) else "#ffb347"
        outcome = str(summary.get("outcome", "stayed")).capitalize()
        outcome_text = outcome

        headline = ctk.CTkLabel(
            self.summary_frame,
            text=outcome_text,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=color,
        )
        headline.pack(anchor="w", pady=(2, 8))

        self._section_label(self.summary_frame, "Co-op Driver Results" if len(self.player_names) > 1 else "Player Result")
        average_position = summary.get("average_position")
        average_text = f"{average_position:.1f}" if isinstance(average_position, (int, float)) else "-"
        self._info_row(self.summary_frame, "Average Finish:", average_text)
        positions = summary.get("player_positions") or []
        for index, player_name in enumerate(self.player_names):
            fallback_position = positions[index] if index < len(positions) else None
            self._info_row(self.summary_frame, f"{player_name}:", self._player_result_text(player_name, fallback_position))
            if len(self.player_names) > 1:
                self._info_row(self.summary_frame, "Rivalries:", self._player_rivalry_text(player_name))

        team_name = str(self.player_team_offer.get("team_name", "")).strip()
        if team_name:
            self._section_label(self.summary_frame, "Garage View")
            self._info_row(self.summary_frame, "Team:", team_name)
            self._info_row(self.summary_frame, "Season Read:", self._team_season_recap_text())

        self._section_label(self.summary_frame, "World Update")
        self._info_row(self.summary_frame, "World Year:", str(driver_pool.get("next_world_year", "-")))
        best_driver = best_driver_in_world(self.save_name) if self.save_name else None
        if best_driver:
            best_driver_text = (
                f"{best_driver.get('name', '-')}"
                f" | MMR {best_driver.get('mmr', '-')}"
                f" | {best_driver.get('primary_style', 'Unassigned')}"
            )
            self._info_row(self.summary_frame, "Best Driver:", best_driver_text)
        self._info_row(self.summary_frame, "Retirements:", str(world_retirements))
        self._info_row(self.summary_frame, "Forced Out:", str(world_forced_out))
        self._info_row(self.summary_frame, "World Championships:", str(world_sim.get("championships", 0)))
        self._info_row(self.summary_frame, "World Races This Year:", str(world_sim.get("races", 0)))
        self._info_row(self.summary_frame, "Rookies Entering:", str(world_rookies))

        completed_year = int(driver_pool.get("next_world_year", 0) or 0) - 1
        tier_five_champions = latest_tier_champions(self.save_name, completed_year, tier=5) if self.save_name and completed_year > 0 else []
        if tier_five_champions:
            tier_five_champions = self._headline_tier_champions(tier_five_champions)
            self._section_label(self.summary_frame, f"Tier 5 Champions ({completed_year})")
            for champion in tier_five_champions:
                label = f"{champion.get('championship_name', '-')}:"
                value = (
                    f"{champion.get('driver_name', '-')}"
                    f" | {champion.get('style', '-')}"
                    f" | MMR {champion.get('mmr', '-')}"
                )
                self._info_row(self.summary_frame, label, value)

        tier_four_champions = latest_tier_champions(self.save_name, completed_year, tier=4) if self.save_name and completed_year > 0 else []
        if tier_four_champions:
            tier_four_champions = self._headline_tier_champions(tier_four_champions)
            self._section_label(self.summary_frame, f"Tier 4 Champions ({completed_year})")
            for champion in tier_four_champions[:6]:
                label = f"{champion.get('championship_name', '-')}:"
                value = (
                    f"{champion.get('driver_name', '-')}"
                    f" | {champion.get('style', '-')}"
                    f" | MMR {champion.get('mmr', '-')}"
                )
                self._info_row(self.summary_frame, label, value)

        retiring_drivers = notable_retirements(self.save_name, completed_year, limit=5) if self.save_name and completed_year > 0 else []
        if retiring_drivers:
            self._section_label(self.summary_frame, "Notable Retirements")
            for driver in retiring_drivers:
                label = f"{driver.get('name', '-')}:"
                value = (
                    f"{driver.get('primary_style', 'Unassigned')}"
                    f" | Titles {driver.get('championships', 0)}"
                    f" | Wins {driver.get('wins', 0)}"
                    f" | Seasons {driver.get('seasons_completed', 0)}"
                )
                self._info_row(self.summary_frame, label, value)

        rookie_year = int(driver_pool.get("next_world_year", 0) or 0)
        rookies = top_rookies_for_year(self.save_name, rookie_year, limit=5) if self.save_name and rookie_year > 0 else []
        if rookies:
            self._section_label(self.summary_frame, f"Top Rookies Entering ({rookie_year})")
            for driver in rookies:
                self._info_row(self.summary_frame, "", str(driver.get("name", "-")))

    def _headline_tier_champions(self, champions: list[dict]) -> list[dict]:
        championships_by_id = {
            str(championship.get("id", "")).strip(): championship
            for championship in load_world_championships()
            if str(championship.get("Tier", "")).strip() == "5"
        }
        grouped: dict[str, list[dict]] = {}
        for champion in champions:
            championship_id = str(champion.get("championship_id", "")).strip()
            grouped.setdefault(championship_id, []).append(champion)

        headline_champions: list[dict] = []
        for championship_id, grouped_champions in grouped.items():
            championship = championships_by_id.get(championship_id, {})
            preferred_class = str(championship.get("_headline_class_name", "")).strip()
            if not preferred_class:
                class_names = championship.get("_class_names", []) or []
                if isinstance(class_names, list) and class_names:
                    preferred_class = str(class_names[0]).strip()

            selected = None
            if preferred_class:
                selected = next(
                    (
                        champion
                        for champion in grouped_champions
                        if str(champion.get("class_name", "")).strip().casefold() == preferred_class.casefold()
                    ),
                    None,
                )
            if not selected:
                selected = next(
                    (
                        champion
                        for champion in grouped_champions
                        if str(champion.get("class_name", "")).strip().casefold() == "overall"
                    ),
                    None,
                )
            if not selected:
                selected = max(grouped_champions, key=lambda champion: int(champion.get("mmr", 0) or 0))
            headline_champions.append(selected)

        headline_champions.sort(key=lambda champion: str(champion.get("championship_name", "")))
        return headline_champions

    def _player_result_text(self, player_name: str, fallback_position) -> str:
        row, overall_position, class_position = self._player_final_position(player_name)
        if not row:
            return f"P{fallback_position}" if fallback_position else "-"

        class_name = str(row.get("class_name", "")).strip()
        position_text = f"P{overall_position}" if overall_position else (f"P{fallback_position}" if fallback_position else "-")
        if class_name and class_name.casefold() != "overall" and class_position:
            position_text = f"{class_name} P{class_position}"

        return (
            f"{position_text} | Points {row.get('points', 0)} | Wins {row.get('wins', 0)} | "
            f"Podiums {row.get('podiums', 0)}"
        )

    def _player_final_position(self, player_name: str) -> tuple[dict | None, int | None, int | None]:
        sorted_overall = sorted(self.final_standings, key=lambda driver: (driver.get("points", 0), driver.get("wins", 0)), reverse=True)
        target = None
        overall_position = None
        for position, driver in enumerate(sorted_overall, 1):
            if str(driver.get("name", "")) == player_name:
                target = driver
                overall_position = position
                break
        if not target:
            return None, None, None

        class_name = str(target.get("class_name", "")).strip() or "Overall"
        class_rows = [
            driver
            for driver in self.final_standings
            if (str(driver.get("class_name", "")).strip() or "Overall").casefold() == class_name.casefold()
        ]
        sorted_class = sorted(class_rows, key=lambda driver: (driver.get("points", 0), driver.get("wins", 0)), reverse=True)
        class_position = None
        for position, driver in enumerate(sorted_class, 1):
            if str(driver.get("name", "")) == player_name:
                class_position = position
                break
        return target, overall_position, class_position

    def _player_rivalry_text(self, player_name: str) -> str:
        perspective = self.player_perspectives.get(player_name, {}) if isinstance(self.player_perspectives, dict) else {}
        heat = {
            str(name).strip(): int(stage)
            for name, stage in dict(perspective.get("rivalry_heat") or {}).items()
            if str(name).strip() and str(stage).strip() in {"1", "2", "3"}
        }
        if not heat:
            return "No active rivalries"

        full_rivals = [name for name, stage in heat.items() if int(stage) >= 3]
        hot_name, hot_stage = max(heat.items(), key=lambda item: int(item[1]))
        if full_rivals:
            return f"{len(full_rivals)} full rival{'s' if len(full_rivals) != 1 else ''} | Hottest: {hot_name}"
        stage_text = "orange" if int(hot_stage) == 2 else "yellow"
        return f"{len(heat)} active | Hottest: {hot_name} ({stage_text})"

    def _team_season_recap_text(self) -> str:
        team_name = str(self.player_team_offer.get("team_name", "")).strip() or "The team"
        philosophy = str(self.player_team_offer.get("team_philosophy", "")).strip().casefold()
        trajectory = str(self.player_team_offer.get("team_trajectory", "")).strip().casefold()
        outcome = str((self.summary or {}).get("outcome", "stayed")).strip().casefold()
        average_position = self.summary.get("average_position")
        average_text = f"{average_position:.1f}" if isinstance(average_position, (int, float)) else "-"

        outcome_line = {
            "promoted": f"The season ended in a step forward, and {team_name} will see that as proof the program is moving.",
            "stayed": f"The season held position overall, which leaves {team_name} looking closely at how to sharpen the next campaign.",
            "demoted": f"The season slipped backward, and {team_name} will treat that as a reset point rather than something to hide from.",
        }.get(outcome, f"{team_name} is reviewing the season and setting the next target.")

        philosophy_line = {
            "win now": "A win-now team will judge this year mostly through whether the results were big enough often enough.",
            "driver continuity": "A continuity-focused team will care about whether the group kept building together over the full season.",
            "technical excellence": "A technical program will look at execution, clean weekends, and whether the details improved round to round.",
            "underdog grit": "An underdog team will value how many points were stolen from weekends that could have gone nowhere.",
            "rookie pipeline": "A development-focused team will care about whether the season showed real growth, not just isolated flashes.",
            "balanced": "A balanced team will weigh both the headline results and the steadiness of the campaign as a whole.",
        }.get(philosophy, "The garage will judge the season through its own standards and what it thinks comes next.")

        trajectory_line = {
            "rising": "The feeling in the garage should still be upward-looking heading into the offseason.",
            "falling": "The garage mood is likely to be sharper and more demanding after the trend this year.",
            "rebuilding": "The team is likely to frame the next phase as part of a larger rebuild.",
            "stable": "The team should see the offseason as a chance to refine rather than reinvent.",
        }.get(trajectory, "")

        return " ".join(
            part
            for part in (
                outcome_line,
                philosophy_line,
                trajectory_line,
                f"Average finishing position for your side of the garage: {average_text}.",
            )
            if part
        )

    def _refresh_standings(self) -> None:
        for widget in self.standings_frame.winfo_children():
            widget.destroy()

        if not self.final_standings:
            ctk.CTkLabel(self.standings_frame, text="No final standings available.", text_color="gray").pack(pady=16)
            return

        groups: dict[str, list[dict]] = {}
        for driver in self.final_standings:
            class_name = str(driver.get("class_name", "")).strip() or "Overall"
            groups.setdefault(class_name, []).append(driver)

        multiclass = len(groups) > 1
        player_set = set(self.player_names)
        for class_name, drivers in groups.items():
            if multiclass:
                ctk.CTkLabel(
                    self.standings_frame,
                    text=class_name,
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color=("#1a6fc4", "#4da6ff"),
                ).pack(anchor="w", padx=4, pady=(6, 2))

            header = ctk.CTkFrame(self.standings_frame, fg_color="transparent")
            header.pack(fill="x")
            for column, width in [("Pos", 35), ("Driver", 150), ("Team", 140), ("Points", 60), ("Wins", 50), ("Podiums", 65)]:
                ctk.CTkLabel(
                    header,
                    text=column,
                    font=ctk.CTkFont(size=10, weight="bold"),
                    text_color="gray",
                    width=width,
                    anchor="w",
                ).pack(side="left", padx=4)

            sorted_standings = sorted(drivers, key=lambda driver: (driver["points"], driver["wins"]), reverse=True)
            for position, driver in enumerate(sorted_standings, 1):
                is_player = str(driver.get("name", "")) in player_set
                row = ctk.CTkFrame(
                    self.standings_frame,
                    fg_color=("#ddeeff", "#1a3a55") if is_player else ("gray80", "gray22"),
                    corner_radius=6,
                )
                row.pack(fill="x", pady=1)
                for value, width in [
                    (f"P{position}", 35),
                    (str(driver.get("name", "")), 150),
                    (str(driver.get("team_name", "-")), 140),
                    (str(driver.get("points", 0)), 60),
                    (str(driver.get("wins", 0)), 50),
                    (str(driver.get("podiums", 0)), 65),
                ]:
                    ctk.CTkLabel(row, text=value, font=ctk.CTkFont(size=11), width=width, anchor="w").pack(
                        side="left", padx=4, pady=4
                    )

    def continue_to_championship_select(self) -> None:
        if not self.save_name:
            self.show_screen("ChampionshipScreen")
            return

        sim_progress = self.parent.screens["SimProgressScreen"]
        if hasattr(sim_progress, "set_offseason_request"):
            sim_progress.set_offseason_request(
                save_name=self.save_name,
                player_names=self.player_names,
                next_tier=self.next_tier,
                starting_difficulty=self.starting_difficulty,
            )
            self.show_screen("SimProgressScreen")
            return

        championship_screen = self.parent.screens["ChampionshipScreen"]
        championship_screen.save_name = self.save_name
        championship_screen.player_names = self.player_names
        championship_screen.current_tier = self.next_tier
        championship_screen.starting_difficulty = self.starting_difficulty
        championship_screen.season_summary_message = ""
        championship_screen.season_summary_color = "gray"
        self.show_screen("ChampionshipScreen")

    def open_driver_pool(self) -> None:
        driver_pool_screen = self.parent.screens["DriverPoolScreen"]
        if hasattr(driver_pool_screen, "set_back_screen"):
            driver_pool_screen.set_back_screen("SeasonRecapScreen")
        if hasattr(driver_pool_screen, "set_context"):
            driver_pool_screen.set_context(self.save_name, "All", "All")
        self.show_screen("DriverPoolScreen")
