from __future__ import annotations

import customtkinter as ctk

from ..driver_pool import team_reputation_map
from ..game_logic import export_world_championship_roster, get_active_world_championship_detail
from ..weather import display_weather


class WorldChampionshipDetailScreen(ctk.CTkFrame):
    def __init__(self, parent, show_screen) -> None:
        super().__init__(parent, fg_color="transparent")
        self.parent = parent
        self.show_screen = show_screen
        self.save_name: str | None = None
        self.championship_key: str | None = None
        self.back_screen = "WorldChampionshipsScreen"
        self.standings_view = "drivers"
        self.driver_standings_btn: ctk.CTkButton | None = None
        self.team_standings_btn: ctk.CTkButton | None = None
        self.export_status_label: ctk.CTkLabel | None = None
        self.current_detail: dict | None = None

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(18, 8))

        self.title_label = ctk.CTkLabel(top, text="World Championship", font=ctk.CTkFont(size=22, weight="bold"))
        self.title_label.pack(side="left")
        ctk.CTkButton(
            top,
            text="<- Back",
            command=lambda: self.show_screen(self.back_screen),
            width=90,
            height=30,
            fg_color="gray30",
            hover_color="gray40",
            font=ctk.CTkFont(size=11),
        ).pack(side="right")

        self.subtitle_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=11), text_color="gray")
        self.subtitle_label.pack(pady=(0, 8))

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)
        content.rowconfigure(1, weight=2)

        info_box = self._make_box(content, "Championship Info")
        info_box.grid(row=0, column=0, padx=(0, 8), pady=(0, 8), sticky="nsew")
        self.info_frame = ctk.CTkScrollableFrame(info_box, fg_color="transparent")
        self.info_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        schedule_box = self._make_box(content, "Schedule")
        schedule_box.grid(row=0, column=1, padx=(8, 0), pady=(0, 8), sticky="nsew")
        self.schedule_frame = ctk.CTkScrollableFrame(schedule_box, fg_color="transparent")
        self.schedule_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        standings_box = self._make_standings_box(content)
        standings_box.grid(row=1, column=0, columnspan=2, sticky="nsew")
        self.standings_frame = ctk.CTkScrollableFrame(standings_box, fg_color="transparent")
        self.standings_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def _make_box(self, parent, title: str) -> ctk.CTkFrame:
        box = ctk.CTkFrame(parent, fg_color=("gray88", "gray17"), corner_radius=10)
        ctk.CTkLabel(
            box,
            text=title,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("#1a6fc4", "#4da6ff"),
        ).pack(anchor="w", padx=10, pady=(8, 4))
        return box

    def _make_standings_box(self, parent) -> ctk.CTkFrame:
        box = ctk.CTkFrame(parent, fg_color=("gray88", "gray17"), corner_radius=10)
        header = ctk.CTkFrame(box, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(8, 4))
        ctk.CTkLabel(
            header,
            text="Standings",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("#1a6fc4", "#4da6ff"),
        ).pack(side="left")
        self.export_status_label = ctk.CTkLabel(header, text="", font=ctk.CTkFont(size=10), text_color="gray")
        self.export_status_label.pack(side="left", padx=(12, 0))
        self.team_standings_btn = ctk.CTkButton(
            header,
            text="Teams",
            width=70,
            height=24,
            font=ctk.CTkFont(size=10),
            command=lambda: self._set_standings_view("teams"),
        )
        self.team_standings_btn.pack(side="right")
        self.driver_standings_btn = ctk.CTkButton(
            header,
            text="Drivers",
            width=70,
            height=24,
            font=ctk.CTkFont(size=10),
            command=lambda: self._set_standings_view("drivers"),
        )
        self.driver_standings_btn.pack(side="right", padx=(0, 6))
        ctk.CTkButton(
            header,
            text="Export Roster",
            width=105,
            height=24,
            font=ctk.CTkFont(size=10),
            fg_color="#1f6aa5",
            hover_color="#15507d",
            command=self.export_roster,
        ).pack(side="right", padx=(0, 6))
        return box

    def _info_row(self, parent, label: str, value: str) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=1)
        ctk.CTkLabel(row, text=label, width=120, anchor="w", font=ctk.CTkFont(size=11), text_color="gray").pack(
            side="left"
        )
        ctk.CTkLabel(row, text=value, anchor="w", font=ctk.CTkFont(size=11), justify="left").pack(
            side="left", fill="x", expand=True
        )

    def set_context(self, save_name: str, championship_key: str, back_screen: str = "WorldChampionshipsScreen") -> None:
        self.save_name = save_name
        self.championship_key = championship_key
        self.back_screen = back_screen or "WorldChampionshipsScreen"

    def on_show(self) -> None:
        for frame in (self.info_frame, self.schedule_frame, self.standings_frame):
            for widget in frame.winfo_children():
                widget.destroy()

        if not self.save_name or not self.championship_key:
            self.subtitle_label.configure(text="No championship selected.")
            if self.export_status_label is not None:
                self.export_status_label.configure(text="")
            return

        detail = get_active_world_championship_detail(self.save_name, self.championship_key)
        if not detail:
            self.subtitle_label.configure(text="Championship not found.")
            if self.export_status_label is not None:
                self.export_status_label.configure(text="")
            return
        self.current_detail = detail
        if self.export_status_label is not None:
            self.export_status_label.configure(text="")

        championship = detail.get("championship") or {}
        standings = detail.get("standings") or []
        schedule = detail.get("schedule") or []
        current_race = int(detail.get("current_race", 0) or 0)

        self.title_label.configure(text=str(detail.get("name", "World Championship")))
        self.subtitle_label.configure(text=f"Save: {self.save_name} | {'Player' if detail.get('is_player') else 'World'} Championship")

        self._info_row(self.info_frame, "Tier:", str(championship.get("Tier", "-")))
        self._info_row(self.info_frame, "Style:", str(championship.get("Style", "-")))
        self._info_row(self.info_frame, "Drivers:", str(len(standings)))
        self._info_row(
            self.info_frame,
            "Round:",
            f"{min(current_race + 1, len(schedule))}/{len(schedule)}" if schedule else "-",
        )
        self._info_row(self.info_frame, "Races:", str(len(schedule)))
        self._info_row(self.info_frame, "Player Series:", "Yes" if detail.get("is_player") else "No")

        if not schedule:
            ctk.CTkLabel(self.schedule_frame, text="No schedule available.", text_color="gray").pack(pady=18)
        else:
            header = ctk.CTkFrame(self.schedule_frame, fg_color="transparent")
            header.pack(fill="x", pady=(0, 4))
            for text, width in [("Rnd", 40), ("Track", 160), ("Layout", 130), ("Weather", 240), ("", 60)]:
                ctk.CTkLabel(
                    header,
                    text=text,
                    width=width,
                    anchor="w",
                    font=ctk.CTkFont(size=10, weight="bold"),
                    text_color="gray",
                ).pack(side="left", padx=3)

            for index, race in enumerate(schedule):
                is_current = index == current_race and index < len(schedule)
                row = ctk.CTkFrame(
                    self.schedule_frame,
                    fg_color=("#ddeeff", "#1a3a55") if is_current else ("gray80", "gray22"),
                    corner_radius=6,
                )
                row.pack(fill="x", pady=2)
                for value, width in [
                    (str(race.get("race_num", index + 1)), 40),
                    (str(race.get("track", "")), 160),
                    (str(race.get("layout", "")), 130),
                    (
                        self._fit_cell_text(
                            display_weather(
                                str(race.get("weather", "")),
                                expand_ams2_legacy=str(championship.get("Game", "")).strip().casefold() == "ams2",
                            ),
                            40,
                        ),
                        240,
                    ),
                ]:
                    ctk.CTkLabel(row, text=value, width=width, anchor="w", font=ctk.CTkFont(size=11)).pack(
                        side="left", padx=3, pady=5
                    )
                ctk.CTkButton(
                    row,
                    text="View",
                    width=55,
                    height=24,
                    font=ctk.CTkFont(size=10),
                    fg_color="gray30",
                    hover_color="gray40",
                    command=lambda race_idx=index, races=schedule, champ=championship: self._open_race_results(races, champ, race_idx),
                ).pack(side="left", padx=(3, 0), pady=4)

        self._refresh_standings_view(standings)

    @staticmethod
    def _fit_cell_text(value, max_chars: int) -> str:
        text = str(value)
        if len(text) <= max_chars:
            return text
        return f"{text[: max_chars - 3]}..."

    def _refresh_standings_view(self, standings: list[dict] | None = None) -> None:
        for widget in self.standings_frame.winfo_children():
            widget.destroy()
        self._refresh_standings_toggle_buttons()
        if standings is None:
            standings = list((self.current_detail or {}).get("standings") or [])
        if self.standings_view == "teams":
            self._render_team_standings(standings)
        else:
            self._render_driver_standings(standings)

    def _render_driver_standings(self, standings: list[dict]) -> None:
        grouped: dict[str, list[dict]] = {}
        for driver in standings:
            class_name = str(driver.get("class_name", "")).strip() or "Overall"
            grouped.setdefault(class_name, []).append(driver)

        multiclass = len(grouped) > 1
        for class_name, drivers in grouped.items():
            if multiclass:
                ctk.CTkLabel(
                    self.standings_frame,
                    text=class_name,
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color=("#1a6fc4", "#4da6ff"),
                ).pack(anchor="w", padx=4, pady=(6, 2))

            header = ctk.CTkFrame(self.standings_frame, fg_color="transparent")
            header.pack(fill="x", pady=(0, 2))
            for text, width in [("Pos", 40), ("Driver", 150), ("Team", 150), ("Points", 70), ("Wins", 55), ("MMR", 70), ("", 60)]:
                ctk.CTkLabel(
                    header,
                    text=text,
                    width=width,
                    anchor="w",
                    font=ctk.CTkFont(size=10, weight="bold"),
                    text_color="gray",
                ).pack(side="left", padx=3)

            sorted_drivers = sorted(drivers, key=lambda row: (row.get("points", 0), row.get("wins", 0)), reverse=True)
            for position, driver in enumerate(sorted_drivers, start=1):
                row = ctk.CTkFrame(self.standings_frame, fg_color=("gray80", "gray22"), corner_radius=6)
                row.pack(fill="x", pady=2)
                for value, width in [
                    (f"P{position}", 40),
                    (str(driver.get("name", "")), 150),
                    (str(driver.get("team_name", "-")), 150),
                    (str(driver.get("points", 0)), 70),
                    (str(driver.get("wins", 0)), 55),
                    (str(driver.get("mmr", "-")), 70),
                ]:
                    ctk.CTkLabel(row, text=value, width=width, anchor="w", font=ctk.CTkFont(size=11)).pack(
                        side="left", padx=3, pady=5
                    )
                ctk.CTkButton(
                    row,
                    text="View",
                    width=55,
                    height=24,
                    font=ctk.CTkFont(size=10),
                    fg_color="gray30",
                    hover_color="gray40",
                    command=lambda driver_id=str(driver.get("driver_id", "")).strip(): self._open_driver_detail(driver_id),
                ).pack(side="left", padx=(3, 0), pady=4)

    def _render_team_standings(self, standings: list[dict]) -> None:
        grouped: dict[str, list[dict]] = {}
        for driver in standings:
            class_name = str(driver.get("class_name", "")).strip() or "Overall"
            grouped.setdefault(class_name, []).append(driver)

        multiclass = len(grouped) > 1
        for class_name, drivers in grouped.items():
            if multiclass:
                ctk.CTkLabel(
                    self.standings_frame,
                    text=class_name,
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color=("#1a6fc4", "#4da6ff"),
                ).pack(anchor="w", padx=4, pady=(6, 2))

            header = ctk.CTkFrame(self.standings_frame, fg_color="transparent")
            header.pack(fill="x", pady=(0, 2))
            for text, width in [("Pos", 40), ("Team", 195), ("Rep", 45), ("Drivers", 70), ("Points", 70), ("Wins", 55)]:
                ctk.CTkLabel(
                    header,
                    text=text,
                    width=width,
                    anchor="w",
                    font=ctk.CTkFont(size=10, weight="bold"),
                    text_color="gray",
                ).pack(side="left", padx=3)

            for position, team in enumerate(self._team_standings_for_drivers(drivers), start=1):
                row = ctk.CTkFrame(self.standings_frame, fg_color=("gray80", "gray22"), corner_radius=6)
                row.pack(fill="x", pady=2)
                for value, width in [
                    (f"P{position}", 40),
                    (team["team_name"], 195),
                    (str(team["reputation"]), 45),
                    (str(team["drivers"]), 70),
                    (str(team["points"]), 70),
                    (str(team["wins"]), 55),
                ]:
                    ctk.CTkLabel(row, text=value, width=width, anchor="w", font=ctk.CTkFont(size=11)).pack(
                        side="left", padx=3, pady=5
                    )

    def _team_standings_for_drivers(self, drivers: list[dict]) -> list[dict]:
        reputations = team_reputation_map(self.save_name) if self.save_name else {}
        teams: dict[str, dict] = {}
        for driver in drivers:
            team_name = str(driver.get("team_name", "")).strip() or "Independent"
            team_key = str(driver.get("team_key", "")).strip()
            team_id = str(driver.get("team_id", "")).strip()
            reputation = reputations.get(team_key) or reputations.get(team_id) or reputations.get(team_name) or 50
            row = teams.setdefault(
                team_name,
                {"team_key": team_key, "team_id": team_id, "team_name": team_name, "reputation": reputation, "drivers": 0, "points": 0, "wins": 0},
            )
            row["drivers"] += 1
            row["points"] += int(driver.get("points", 0) or 0)
            row["wins"] += int(driver.get("wins", 0) or 0)
        return sorted(teams.values(), key=lambda row: (-row["points"], -row["wins"], row["team_name"]))

    def _set_standings_view(self, view: str) -> None:
        self.standings_view = "teams" if view == "teams" else "drivers"
        self._refresh_standings_view()

    def _refresh_standings_toggle_buttons(self) -> None:
        if self.driver_standings_btn is not None:
            self.driver_standings_btn.configure(
                fg_color="#1f6aa5" if self.standings_view == "drivers" else "gray30",
                hover_color="#15507d" if self.standings_view == "drivers" else "gray40",
            )
        if self.team_standings_btn is not None:
            self.team_standings_btn.configure(
                fg_color="#1f6aa5" if self.standings_view == "teams" else "gray30",
                hover_color="#15507d" if self.standings_view == "teams" else "gray40",
            )

    def export_roster(self) -> None:
        if not self.save_name or not self.championship_key:
            return
        if self.export_status_label is not None:
            self.export_status_label.configure(text="Exporting roster...", text_color="gray")
            self.export_status_label.update_idletasks()
        try:
            export_world_championship_roster(self.save_name, self.championship_key)
        except Exception as error:
            if self.export_status_label is not None:
                self.export_status_label.configure(text=f"Export failed: {error}", text_color="#ff7777")
            return
        if self.export_status_label is not None:
            self.export_status_label.configure(text="Roster exported.", text_color="#6bbd6b")

    def _open_driver_detail(self, driver_id: str) -> None:
        if not self.save_name or not driver_id:
            return
        detail_screen = self.parent.screens["DriverDetailScreen"]
        if hasattr(detail_screen, "set_context"):
            detail_screen.set_context(self.save_name, driver_id, "WorldChampionshipDetailScreen")
        self.show_screen("DriverDetailScreen")

    def _open_race_results(self, schedule: list[dict], championship: dict, race_index: int) -> None:
        race_results_screen = self.parent.screens["RaceResultsScreen"]
        if hasattr(race_results_screen, "set_world_context"):
            race_results_screen.set_world_context(schedule, championship, race_index, "WorldChampionshipDetailScreen")
        self.show_screen("RaceResultsScreen")
