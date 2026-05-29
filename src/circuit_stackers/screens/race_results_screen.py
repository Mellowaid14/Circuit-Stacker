from __future__ import annotations

import customtkinter as ctk

from ..weather import display_weather
from .manual_setup_screen import RaceSetupPopup


class RaceResultsScreen(ctk.CTkFrame):
    def __init__(self, parent, show_screen) -> None:
        super().__init__(parent, fg_color="transparent")
        self.show_screen = show_screen
        self.gameplay_screen = None
        self.race_index: int | None = None
        self.override_schedule: list[dict] | None = None
        self.override_championship: dict | None = None
        self.override_player_names: list[str] = []
        self.back_screen = "GameplayScreen"

        ctk.CTkLabel(self, text="Race Results", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(24, 6))
        self.subtitle_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=13), text_color="gray")
        self.subtitle_label.pack(pady=(0, 16))

        self.info_frame = ctk.CTkFrame(self, fg_color=("gray90", "gray15"), corner_radius=12)
        self.info_frame.pack(fill="x", padx=24, pady=(0, 12))

        results_box = ctk.CTkFrame(self, fg_color=("gray90", "gray15"), corner_radius=12)
        results_box.pack(fill="both", expand=True, padx=24, pady=(0, 12))
        self.results_frame = ctk.CTkScrollableFrame(results_box, fg_color="transparent")
        self.results_frame.pack(fill="both", expand=True, padx=10, pady=10)

        ctk.CTkButton(
            self,
            text="<- Back",
            command=lambda: self.show_screen(self.back_screen),
            height=36,
            width=120,
            font=ctk.CTkFont(size=12),
            fg_color="gray30",
            hover_color="gray40",
        ).pack(pady=(0, 12))

    def set_gameplay_screen(self, gameplay_screen) -> None:
        self.gameplay_screen = gameplay_screen

    def set_race_index(self, race_index: int) -> None:
        self.override_schedule = None
        self.override_championship = None
        self.override_player_names = []
        self.back_screen = "GameplayScreen"
        self.race_index = race_index

    def set_world_context(
        self,
        schedule: list[dict],
        championship: dict | None,
        race_index: int,
        back_screen: str = "WorldChampionshipDetailScreen",
    ) -> None:
        self.override_schedule = list(schedule or [])
        self.override_championship = dict(championship or {})
        self.override_player_names = []
        self.race_index = race_index
        self.back_screen = back_screen or "WorldChampionshipDetailScreen"

    def on_show(self) -> None:
        for widget in self.info_frame.winfo_children():
            widget.destroy()
        for widget in self.results_frame.winfo_children():
            widget.destroy()

        schedule = self.override_schedule if self.override_schedule is not None else getattr(self.gameplay_screen, "schedule", None)
        championship = self.override_championship if self.override_schedule is not None else getattr(self.gameplay_screen, "championship", None)
        player_names = self.override_player_names if self.override_schedule is not None else getattr(self.gameplay_screen, "player_names", [])

        if schedule is None or self.race_index is None:
            self.subtitle_label.configure(text="No race selected.")
            return

        if self.race_index >= len(schedule):
            self.subtitle_label.configure(text="Race not found.")
            return

        race = schedule[self.race_index]
        self.subtitle_label.configure(text=f"Round {race['race_num']} - {race['track']}")
        opponent_count, opponent_classes = self._opponent_summary(race, championship, player_names)

        if self.override_schedule is None and self.gameplay_screen is not None:
            actions = ctk.CTkFrame(self.info_frame, fg_color="transparent")
            actions.pack(fill="x", padx=14, pady=(10, 2))
            ctk.CTkButton(
                actions,
                text="Manual Setup",
                command=lambda value=self.race_index: self.open_manual_setup_popup(value),
                width=120,
                height=28,
                font=ctk.CTkFont(size=11, weight="bold"),
            ).pack(side="right")

        details = [
            ("Race", f"{race['race_num']} of {len(schedule)}"),
            ("Track", race["track"]),
            ("Layout", race["layout"]),
            ("Date", self._display_date(race)),
            ("Time", self._display_time(str(race.get("time_of_day", "")))),
            ("Weather", self._display_weather(race, championship)),
            ("Opponents", str(opponent_count)),
            ("Opponent Class", opponent_classes),
            ("Race Length", f"{(championship or {}).get('Race_Time', '-') } min".replace("  ", " ")),
            ("Start Type", (championship or {}).get("Start_Type", "")),
        ]
        for label, value in details:
            row = ctk.CTkFrame(self.info_frame, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=4)
            ctk.CTkLabel(row, text=f"{label}:", width=90, anchor="w", text_color="gray").pack(side="left")
            ctk.CTkLabel(row, text=str(value), anchor="w", justify="left", wraplength=980).pack(side="left", fill="x", expand=True)

        results = race.get("full_results", [])
        if not results:
            ctk.CTkLabel(self.results_frame, text="No saved results for this race yet.", text_color="gray").pack(pady=20)
            return

        player_set = set(player_names)
        for class_name, class_results in self._group_results_by_class(results).items():
            class_header = ctk.CTkFrame(self.results_frame, fg_color="transparent")
            class_header.pack(fill="x", pady=(8, 2))
            ctk.CTkLabel(
                class_header,
                text=f"{class_name} Class",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=("#1a6fc4", "#4da6ff"),
                anchor="w",
            ).pack(side="left", padx=4)

            header = ctk.CTkFrame(self.results_frame, fg_color="transparent")
            header.pack(fill="x", pady=(0, 4))
            for text, width in [("Overall", 55), ("Class Pos", 70), ("Driver", 190), ("Team", 150), ("Pts", 40), ("MMR", 55)]:
                ctk.CTkLabel(
                    header,
                    text=text,
                    width=width,
                    anchor="w",
                    font=ctk.CTkFont(size=10, weight="bold"),
                    text_color="gray",
                ).pack(side="left", padx=4)

            for result in class_results:
                is_player = result["driver_name"] in player_set
                row = ctk.CTkFrame(
                    self.results_frame,
                    fg_color=("#ddeeff", "#1a3a55") if is_player else ("gray80", "gray22"),
                    corner_radius=6,
                )
                row.pack(fill="x", pady=2)
                values = [
                    (str(result["overall_pos"]), 55),
                    (str(result["class_pos"]), 70),
                    (str(result["driver_name"]), 190),
                    (str(result.get("team_name", "-") or "-"), 150),
                    (str(result["points_awarded"]), 40),
                    (self._format_mmr_change(result.get("mmr_change")), 55),
                ]
                for value, width in values:
                    ctk.CTkLabel(row, text=value, width=width, anchor="w", font=ctk.CTkFont(size=11)).pack(
                        side="left", padx=4, pady=6
                    )

    @staticmethod
    def _display_date(race: dict) -> str:
        import datetime as _datetime

        raw_date = str(race.get("date", "")).strip()
        if not raw_date:
            return "-"
        try:
            day_str, month_str = raw_date.split(maxsplit=1)
            month_number = _datetime.datetime.strptime(month_str.strip(), "%b").month
            year = int(race.get("world_year", 0) or 0)
            if not year:
                year = _datetime.datetime.now().year
            return f"{month_number:02d}/{int(day_str):02d}/{int(year)}"
        except Exception:
            return raw_date

    @staticmethod
    def _display_time(time_of_day: str) -> str:
        mapping = {
            "Morning": "09:00",
            "Afternoon": "14:00",
            "Evening": "18:00",
            "Night": "21:00",
        }
        return mapping.get(str(time_of_day).strip(), str(time_of_day))

    def _display_weather(self, race: dict, championship: dict | None = None) -> str:
        game = str((championship or {}).get("Game", "")).strip().casefold()
        if not game and self.gameplay_screen is not None:
            game = str(getattr(self.gameplay_screen, "game", "")).strip().casefold()
        return display_weather(str(race.get("weather", "")).strip(), expand_ams2_legacy=game == "ams2")

    @staticmethod
    def _opponent_summary(race: dict, championship: dict | None, player_names: list[str]) -> tuple[int, str]:
        standings = []
        current_results = race.get("full_results")
        if isinstance(current_results, list):
            standings = current_results
        player_set = {str(name).strip() for name in player_names if str(name).strip()}
        opponents = [driver for driver in standings if str(driver.get("driver_name", "")).strip() not in player_set]
        opponent_count = len(opponents)
        if not opponents:
            return 0, "Same class"

        class_counts: dict[str, int] = {}
        for driver in opponents:
            class_name = str(driver.get("class_name", "")).strip() or str((championship or {}).get("Car", "")).strip() or "Same class"
            class_counts[class_name] = class_counts.get(class_name, 0) + 1

        if len(class_counts) <= 1:
            return opponent_count, "Same class"
        parts = [f"{class_name} {count}" for class_name, count in sorted(class_counts.items(), key=lambda item: item[0])]
        return opponent_count, " | ".join(parts)

    @staticmethod
    def _group_results_by_class(results: list[dict]) -> dict[str, list[dict]]:
        grouped: dict[str, list[dict]] = {}
        for result in sorted(
            results,
            key=lambda row: (
                str(row.get("class_name", "Overall")),
                int(row.get("class_pos", row.get("overall_pos", 0)) or 0),
            ),
        ):
            class_name = str(result.get("class_name", "Overall")).strip() or "Overall"
            grouped.setdefault(class_name, []).append(result)
        return grouped

    @staticmethod
    def _format_mmr_change(value) -> str:
        if value is None:
            return "-"
        try:
            change = int(value)
        except (TypeError, ValueError):
            return "-"
        if change > 0:
            return f"+{change}"
        return str(change)

    def open_manual_setup_popup(self, race_index: int | None = None) -> None:
        if self.gameplay_screen is None:
            return
        RaceSetupPopup(self, self.gameplay_screen, race_index=race_index)
