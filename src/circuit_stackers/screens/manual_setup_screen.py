from __future__ import annotations

import tkinter as tk
from datetime import datetime, timedelta

import customtkinter as ctk

from ..game_logic import difficulty_range_for_game, set_manual_difficulty
from ..season_exporter import iracing_skill_spread_for_prestige
from ..weather import parse_weather_slots, weather_timeline_text


TIME_TO_HOUR = {
    "Morning": 9,
    "Afternoon": 14,
    "Evening": 18,
    "Night": 21,
}


def build_manual_setup_content(content, gameplay, title_label=None, subtitle_label=None, race_index: int | None = None) -> None:
    builder = ManualSetupBuilder(content)
    builder.refresh(gameplay, title_label=title_label, subtitle_label=subtitle_label, race_index=race_index)


class ManualSetupBuilder:
    def __init__(self, content) -> None:
        self.content = content

    def refresh(self, gameplay, title_label=None, subtitle_label=None, race_index: int | None = None) -> None:
        for widget in self.content.winfo_children():
            widget.destroy()

        if gameplay is None or not getattr(gameplay, "schedule", None):
            if subtitle_label is not None:
                subtitle_label.configure(text="No current race is available.")
            ctk.CTkLabel(self.content, text="No race setup data available.", text_color="gray").pack(pady=24)
            return

        selected_race_index = gameplay.current_race if race_index is None else int(race_index)
        if selected_race_index >= len(gameplay.schedule):
            if subtitle_label is not None:
                subtitle_label.configure(text="The current championship is complete.")
            ctk.CTkLabel(self.content, text="No active race to set up.", text_color="gray").pack(pady=24)
            return

        race = gameplay.schedule[selected_race_index]
        championship = gameplay.championship or {}
        game = str(getattr(gameplay, "game", "iRacing")).strip()
        if title_label is not None:
            title_label.configure(text=f"Manual Setup: {game}")
        if subtitle_label is not None:
            subtitle_label.configure(
                text=f"Round {race.get('race_num', gameplay.current_race + 1)} - {race.get('track', '')}"
            )

        self._difficulty_editor(gameplay)
        if game.casefold() == "ams2":
            self._build_ams2_setup(gameplay, championship, race)
        else:
            self._build_iracing_setup(gameplay, championship, race)

    def _difficulty_editor(self, gameplay) -> None:
        game = str(getattr(gameplay, "game", "iRacing")).strip()
        min_difficulty, max_difficulty = difficulty_range_for_game(game)
        current_difficulty = max(
            min_difficulty,
            min(max_difficulty, int(getattr(gameplay, "starting_difficulty", max_difficulty) or max_difficulty)),
        )

        box = ctk.CTkFrame(self.content, fg_color=("gray88", "gray17"), corner_radius=10)
        box.pack(fill="x", padx=4, pady=6)
        header = ctk.CTkFrame(box, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(10, 6))
        ctk.CTkLabel(
            header,
            text="Difficulty",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=("#1a6fc4", "#4da6ff"),
            anchor="w",
        ).pack(side="left")
        status_label = ctk.CTkLabel(header, text="", font=ctk.CTkFont(size=11), text_color="gray")
        status_label.pack(side="left", padx=(12, 0))

        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 10))
        ctk.CTkLabel(row, text="AI Difficulty:", width=150, anchor="w", text_color="gray").pack(side="left")
        value_var = tk.StringVar(value=str(current_difficulty))
        value_entry = ctk.CTkEntry(row, width=70, textvariable=value_var, justify="center")
        value_entry.pack(side="left", padx=(0, 8))

        def hint_text(value: int) -> str:
            if game.casefold() == "ams2":
                return f"Allowed range: {min_difficulty}-{max_difficulty}"
            prestige = (getattr(gameplay, "championship", {}) or {}).get("Prestige", 1)
            low = max(min_difficulty, value - iracing_skill_spread_for_prestige(prestige))
            return f"iRacing export range: {low}-{value}"

        hint_label = ctk.CTkLabel(row, text=hint_text(current_difficulty), anchor="w", text_color="gray")

        def parse_value() -> int:
            try:
                raw_value = int(value_var.get().strip())
            except ValueError:
                raw_value = current_difficulty
            return max(min_difficulty, min(max_difficulty, raw_value))

        def step(delta: int) -> None:
            new_value = max(min_difficulty, min(max_difficulty, parse_value() + delta))
            value_var.set(str(new_value))
            hint_label.configure(text=hint_text(new_value))
            status_label.configure(text="")

        def save() -> None:
            save_name = str(getattr(gameplay, "save_name", "") or "").strip()
            if not save_name:
                status_label.configure(text="No save loaded.", text_color="#ff7777")
                return
            try:
                saved_difficulty, season_synced = set_manual_difficulty(save_name, parse_value())
            except Exception as error:
                status_label.configure(text=f"Could not save: {error}", text_color="#ff7777")
                return
            value_var.set(str(saved_difficulty))
            gameplay.starting_difficulty = saved_difficulty
            if hasattr(gameplay, "_refresh_current_race"):
                gameplay._refresh_current_race()
            hint_label.configure(text=hint_text(saved_difficulty))
            sync_note = " Season file updated." if game.casefold() == "iracing" and season_synced else ""
            status_label.configure(text=f"Saved.{sync_note}", text_color="#6bbd6b")

        ctk.CTkButton(row, text="-", width=34, height=28, command=lambda: step(-1)).pack(side="left", padx=(0, 6))
        ctk.CTkButton(row, text="+", width=34, height=28, command=lambda: step(1)).pack(side="left", padx=(0, 10))
        ctk.CTkButton(row, text="Save Difficulty", width=130, height=28, command=save).pack(side="left", padx=(0, 10))
        hint_label.pack(side="left", fill="x", expand=True)

    def _build_iracing_setup(self, gameplay, championship: dict, race: dict) -> None:
        race_time = self._race_datetime(race)
        practice_time = race_time - timedelta(hours=2)
        qualify_time = race_time - timedelta(hours=1)
        roster_name = f"CS-{championship.get('Championship', 'Championship')}-{gameplay.save_name}"
        player_car = gameplay.player_car or {}
        opponent_count, _opponent_classes = gameplay._opponent_summary()

        self._section(
            "Race Sessions",
            [
                ("Practice", f"{championship.get('Practice_Time', 20) or 20} min at {self._time_text(practice_time)}"),
                ("Qualifier", f"{championship.get('Qualifying_Laps', 2) or 2} laps at {self._time_text(qualify_time)}"),
                ("Race", f"{championship.get('Race_Time', '-')} min at {self._time_text(race_time)}"),
            ],
        )
        self._section("Set Car", [("Player Car", str(player_car.get("Car", "Unassigned")))])
        self._section(
            "Set Track",
            [
                ("Track", str(race.get("track", ""))),
                ("Track Layout", str(race.get("layout", ""))),
            ],
        )
        self._section("Track Options", [("Start Type", str(championship.get("Start_Type", "")))])
        self._section(
            "Time of Day",
            [
                ("Practice Time", self._time_text(practice_time)),
                ("Qualifier Time", self._time_text(qualify_time)),
                ("Race Time", self._time_text(race_time)),
            ],
        )
        self._section(
            "Weather",
            [
                ("Weather Mode", "Timeline editor"),
                ("Timeline", self._weather_timeline_text(race)),
            ],
        )
        self._section(
            "Race Options",
            [("Racing Discipline", self._iracing_discipline(championship))],
        )
        self._section("Track Conditions", [("Leave debris on track", "ON")])
        self._section(
            "AI Opponents",
            [
                ("Generated Roster", roster_name),
                ("AI Count", f"Max AI for roster ({opponent_count})"),
                ("AI Type", "Fixed Skill Range"),
                ("Skill Spread", "Use Difficulty section above"),
            ],
        )

    def _build_ams2_setup(self, gameplay, championship: dict, race: dict) -> None:
        race_time = self._race_datetime(race)
        practice_time = race_time - timedelta(hours=2)
        qualify_time = race_time - timedelta(hours=1)
        player_car = gameplay.player_car or {}
        opponent_count, opponent_classes = gameplay._opponent_summary()
        player_livery = self._player_livery_text(gameplay)
        practice_weather_slots = self._weather_slots(race, "practice_weather")
        qualifying_weather_slots = self._weather_slots(race, "qualifying_weather")
        race_weather_slots = self._weather_slots(race, "weather")

        self._section(
            "Player Car",
            [
                ("Car", str(player_car.get("Car", "Unassigned"))),
                ("Livery", player_livery),
            ],
        )
        self._section(
            "Session Settings",
            [
                ("Practice Time", self._time_text(practice_time)),
                ("Practice Weather", " | ".join(practice_weather_slots)),
                ("Qualifying Time", self._time_text(qualify_time)),
                ("Qualifying Weather", " | ".join(qualifying_weather_slots)),
            ],
        )
        self._section(
            "Race Settings",
            [
                ("Duration Type", "Time"),
                ("Time", f"{championship.get('Race_Time', '-')} min"),
                ("Time +1 Lap", "No"),
                ("Date Type", "Custom"),
                ("Date", self._date_text(gameplay, race)),
                ("Start Time", self._time_text(race_time)),
                ("Race Weather", " | ".join(race_weather_slots)),
                ("Race Weather Progression", self._weather_timeline_text(race, "weather", expand_ams2_legacy=True)),
                ("Start Type", str(championship.get("Start_Type", ""))),
            ],
        )
        self._section(
            "Opponents Settings",
            [
                ("Opponent Field Type", "Same Class" if opponent_classes == "Same class" else "Multi-Class"),
                ("Edit Class", opponent_classes),
                ("Opponent Number Type", "Custom" if opponent_classes == "Same class" else "Manual Grid"),
                ("Opponent Number", str(opponent_count)),
                ("AI Skill", "Use Difficulty section above"),
                ("AI Aggression", "Medium"),
            ],
        )

    def _section(self, title: str, rows: list[tuple[str, str]]) -> None:
        box = ctk.CTkFrame(self.content, fg_color=("gray88", "gray17"), corner_radius=10)
        box.pack(fill="x", padx=4, pady=6)
        ctk.CTkLabel(
            box,
            text=title,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=("#1a6fc4", "#4da6ff"),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 6))
        for label, value in rows:
            row = ctk.CTkFrame(box, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=2)
            ctk.CTkLabel(row, text=f"{label}:", width=150, anchor="w", text_color="gray").pack(side="left")
            ctk.CTkLabel(row, text=str(value), anchor="w", justify="left", wraplength=720).pack(
                side="left", fill="x", expand=True
            )
        ctk.CTkLabel(box, text="", height=4).pack()

    @staticmethod
    def _weather_slots(race: dict, key: str = "weather") -> list[str]:
        weather = str(race.get(key, "") or race.get("weather", "")).strip() or "Clear"
        return parse_weather_slots(weather, expand_ams2_legacy=True)[:4]

    def _weather_timeline_text(self, race: dict, key: str = "weather", *, expand_ams2_legacy: bool = False) -> str:
        weather = str(race.get(key, "") or race.get("weather", "")).strip() or "Clear"
        return weather_timeline_text(
            weather,
            expand_ams2_legacy=expand_ams2_legacy,
        )

    @staticmethod
    def _iracing_discipline(championship: dict) -> str:
        style = str(championship.get("Style", "Sports Car")).strip().casefold()
        if "oval" in style:
            return "Oval"
        if "open" in style or "formula" in style:
            return "Formula car"
        return "Sports Car"

    @staticmethod
    def _difficulty_range_text(gameplay) -> str:
        top = max(0, min(125, int(getattr(gameplay, "starting_difficulty", 75) or 75)))
        prestige = (getattr(gameplay, "championship", {}) or {}).get("Prestige", 1)
        low = max(0, top - iracing_skill_spread_for_prestige(prestige))
        if str(getattr(gameplay, "game", "")).strip().casefold() == "iracing":
            return f"{low}-{top}"
        return str(top)

    @staticmethod
    def _race_datetime(race: dict) -> datetime:
        raw_date = str(race.get("date", "15 May")).strip()
        try:
            day_str, month_str = raw_date.split(maxsplit=1)
            month = datetime.strptime(month_str.strip(), "%b").month
            day = int(day_str)
        except Exception:
            month = 5
            day = 15
        hour = TIME_TO_HOUR.get(str(race.get("time_of_day", "Afternoon")), 14)
        return datetime(2026, month, day, hour, 0)

    @staticmethod
    def _time_text(value: datetime) -> str:
        return value.strftime("%H:%M")

    @staticmethod
    def _date_text(gameplay, race: dict) -> str:
        if hasattr(gameplay, "_display_date"):
            return gameplay._display_date(race)
        return str(race.get("date", ""))

    @staticmethod
    def _player_livery_text(gameplay) -> str:
        liveries = getattr(gameplay, "player_liveries", []) or []
        if not liveries:
            return "Re-export roster to refresh"
        return " | ".join(
            str(item.get("livery_name", "")).strip()
            for item in liveries
            if str(item.get("livery_name", "")).strip()
        ) or "Re-export roster to refresh"


class ManualSetupScreen(ctk.CTkFrame):
    def __init__(self, parent, show_screen) -> None:
        super().__init__(parent, fg_color="transparent")
        self.parent = parent
        self.show_screen = show_screen
        self.gameplay_screen = None

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(16, 8))

        self.title_label = ctk.CTkLabel(top, text="Manual Race Setup", font=ctk.CTkFont(size=22, weight="bold"))
        self.title_label.pack(side="left")

        ctk.CTkButton(
            top,
            text="<- Back",
            command=lambda: self.show_screen("GameplayScreen"),
            width=90,
            height=30,
            fg_color="gray30",
            hover_color="gray40",
            font=ctk.CTkFont(size=11),
        ).pack(side="right")

        self.subtitle_label = ctk.CTkLabel(
            self,
            text="Use this checklist to manually set up the current race.",
            text_color="gray",
            font=ctk.CTkFont(size=12),
        )
        self.subtitle_label.pack(anchor="w", padx=18, pady=(0, 8))

        self.content = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.content.pack(fill="both", expand=True, padx=14, pady=(0, 12))

    def set_gameplay_screen(self, gameplay_screen) -> None:
        self.gameplay_screen = gameplay_screen

    def on_show(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        build_manual_setup_content(
            self.content,
            self.gameplay_screen,
            title_label=self.title_label,
            subtitle_label=self.subtitle_label,
        )

    def _build_iracing_setup(self, gameplay, championship: dict, race: dict) -> None:
        race_time = self._race_datetime(race)
        practice_time = race_time - timedelta(hours=2)
        qualify_time = race_time - timedelta(hours=1)
        roster_name = f"CS-{championship.get('Championship', 'Championship')}-{gameplay.save_name}"
        player_car = gameplay.player_car or {}
        opponent_count, _opponent_classes = gameplay._opponent_summary()

        self._section(
            "Race Sessions",
            [
                ("Practice", f"{championship.get('Practice_Time', 20) or 20} min at {self._time_text(practice_time)}"),
                ("Qualifier", f"{championship.get('Qualifying_Laps', 2) or 2} laps at {self._time_text(qualify_time)}"),
                ("Race", f"{championship.get('Race_Time', '-')} min at {self._time_text(race_time)}"),
            ],
        )
        self._section("Set Car", [("Player Car", str(player_car.get("Car", "Unassigned")))])
        self._section(
            "Set Track",
            [
                ("Track", str(race.get("track", ""))),
                ("Track Layout", str(race.get("layout", ""))),
            ],
        )
        self._section("Track Options", [("Start Type", str(championship.get("Start_Type", "")))])
        self._section(
            "Time of Day",
            [
                ("Practice Time", self._time_text(practice_time)),
                ("Qualifier Time", self._time_text(qualify_time)),
                ("Race Time", self._time_text(race_time)),
            ],
        )
        self._section(
            "Weather",
            [
                ("Weather Mode", "Timeline editor"),
                ("Timeline", self._weather_timeline_text(race)),
            ],
        )
        self._section(
            "Race Options",
            [("Racing Discipline", self._iracing_discipline(championship))],
        )
        self._section("Track Conditions", [("Leave debris on track", "ON")])
        self._section(
            "AI Opponents",
            [
                ("Generated Roster", roster_name),
                ("AI Count", f"Max AI for roster ({opponent_count})"),
                ("AI Type", "Fixed Skill Range"),
                ("Skill Spread", "Use Difficulty section above"),
            ],
        )

    def _build_ams2_setup(self, gameplay, championship: dict, race: dict) -> None:
        race_time = self._race_datetime(race)
        practice_time = race_time - timedelta(hours=2)
        qualify_time = race_time - timedelta(hours=1)
        player_car = gameplay.player_car or {}
        opponent_count, opponent_classes = gameplay._opponent_summary()
        player_livery = self._player_livery_text(gameplay)
        practice_weather_slots = self._weather_slots(race, "practice_weather")
        qualifying_weather_slots = self._weather_slots(race, "qualifying_weather")
        race_weather_slots = self._weather_slots(race, "weather")

        self._section(
            "Player Car",
            [
                ("Car", str(player_car.get("Car", "Unassigned"))),
                ("Livery", player_livery),
            ],
        )
        self._section(
            "Session Settings",
            [
                ("Practice Time", self._time_text(practice_time)),
                ("Practice Weather", " | ".join(practice_weather_slots)),
                ("Qualifying Time", self._time_text(qualify_time)),
                ("Qualifying Weather", " | ".join(qualifying_weather_slots)),
            ],
        )
        self._section(
            "Race Settings",
            [
                ("Duration Type", "Time"),
                ("Time", f"{championship.get('Race_Time', '-')} min"),
                ("Time +1 Lap", "No"),
                ("Date Type", "Custom"),
                ("Date", self._date_text(gameplay, race)),
                ("Start Time", self._time_text(race_time)),
                ("Race Weather", " | ".join(race_weather_slots)),
                ("Race Weather Progression", self._weather_timeline_text(race, "weather", expand_ams2_legacy=True)),
                ("Start Type", str(championship.get("Start_Type", ""))),
            ],
        )
        self._section(
            "Opponents Settings",
            [
                ("Opponent Field Type", "Same Class" if opponent_classes == "Same class" else "Multi-Class"),
                ("Edit Class", opponent_classes),
                ("Opponent Number Type", "Custom" if opponent_classes == "Same class" else "Manual Grid"),
                ("Opponent Number", str(opponent_count)),
                ("AI Skill", "Use Difficulty section above"),
                ("AI Aggression", "Medium"),
            ],
        )

    def _section(self, title: str, rows: list[tuple[str, str]]) -> None:
        box = ctk.CTkFrame(self.content, fg_color=("gray88", "gray17"), corner_radius=10)
        box.pack(fill="x", padx=4, pady=6)
        ctk.CTkLabel(
            box,
            text=title,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=("#1a6fc4", "#4da6ff"),
            anchor="w",
        ).pack(fill="x", padx=12, pady=(10, 6))
        for label, value in rows:
            row = ctk.CTkFrame(box, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=2)
            ctk.CTkLabel(row, text=f"{label}:", width=150, anchor="w", text_color="gray").pack(side="left")
            ctk.CTkLabel(row, text=str(value), anchor="w", justify="left", wraplength=860).pack(
                side="left", fill="x", expand=True
            )
        ctk.CTkLabel(box, text="", height=4).pack()

    @staticmethod
    def _weather_slots(race: dict, key: str = "weather") -> list[str]:
        weather = str(race.get(key, "") or race.get("weather", "")).strip() or "Clear"
        return parse_weather_slots(weather, expand_ams2_legacy=True)[:4]

    def _weather_timeline_text(self, race: dict, key: str = "weather", *, expand_ams2_legacy: bool = False) -> str:
        weather = str(race.get(key, "") or race.get("weather", "")).strip() or "Clear"
        return weather_timeline_text(
            weather,
            expand_ams2_legacy=expand_ams2_legacy,
        )

    @staticmethod
    def _iracing_discipline(championship: dict) -> str:
        style = str(championship.get("Style", "Sports Car")).strip().casefold()
        if "oval" in style:
            return "Oval"
        if "open" in style or "formula" in style:
            return "Formula car"
        return "Sports Car"

    @staticmethod
    def _difficulty_range_text(gameplay) -> str:
        top = max(0, min(125, int(getattr(gameplay, "starting_difficulty", 75) or 75)))
        prestige = (getattr(gameplay, "championship", {}) or {}).get("Prestige", 1)
        low = max(0, top - iracing_skill_spread_for_prestige(prestige))
        if str(getattr(gameplay, "game", "")).strip().casefold() == "iracing":
            return f"{low}-{top}"
        return str(top)

    @staticmethod
    def _race_datetime(race: dict) -> datetime:
        raw_date = str(race.get("date", "15 May")).strip()
        try:
            day_str, month_str = raw_date.split(maxsplit=1)
            month = datetime.strptime(month_str.strip(), "%b").month
            day = int(day_str)
        except Exception:
            month = 5
            day = 15
        hour = TIME_TO_HOUR.get(str(race.get("time_of_day", "Afternoon")), 14)
        return datetime(2026, month, day, hour, 0)

    @staticmethod
    def _time_text(value: datetime) -> str:
        return value.strftime("%H:%M")

    @staticmethod
    def _date_text(gameplay, race: dict) -> str:
        if hasattr(gameplay, "_display_date"):
            return gameplay._display_date(race)
        return str(race.get("date", ""))

    @staticmethod
    def _player_livery_text(gameplay) -> str:
        liveries = getattr(gameplay, "player_liveries", []) or []
        if not liveries:
            return "Re-export roster to refresh"
        return " | ".join(
            str(item.get("livery_name", "")).strip()
            for item in liveries
            if str(item.get("livery_name", "")).strip()
        ) or "Re-export roster to refresh"


class RaceSetupPopup(ctk.CTkToplevel):
    def __init__(self, parent, gameplay_screen, race_index: int | None = None) -> None:
        super().__init__(parent)
        self.title("Race Setup")
        self.geometry("820x720")
        self.minsize(720, 560)
        self.transient(parent)
        self.gameplay_screen = gameplay_screen
        self.race_index = race_index

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(16, 8))
        self.title_label = ctk.CTkLabel(top, text="Race Setup", font=ctk.CTkFont(size=22, weight="bold"))
        self.title_label.pack(side="left")
        ctk.CTkButton(
            top,
            text="Close",
            command=self.destroy,
            width=90,
            height=30,
            fg_color="gray30",
            hover_color="gray40",
        ).pack(side="right")

        self.subtitle_label = ctk.CTkLabel(self, text="", text_color="gray", font=ctk.CTkFont(size=12))
        self.subtitle_label.pack(anchor="w", padx=18, pady=(0, 8))

        content = ctk.CTkScrollableFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        build_manual_setup_content(
            content,
            gameplay_screen,
            title_label=self.title_label,
            subtitle_label=self.subtitle_label,
            race_index=race_index,
        )
        self.focus()
