from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import customtkinter as ctk

from ..ams2_exporter import validate_ams2_roster_files
from ..save_manager import update_save
from .manual_setup_screen import build_manual_setup_content


ACCENT = "#2f8cff"
ACCENT_DARK = "#15507d"
SUCCESS = "#218c4a"
SUCCESS_DARK = "#176b38"
CARD = ("gray88", "gray17")
CARD_ALT = ("gray84", "gray20")
MUTED = ("gray45", "gray62")


class RaceWeekendScreen(ctk.CTkFrame):
    def __init__(self, parent, show_screen) -> None:
        super().__init__(parent, fg_color="transparent")
        self.parent = parent
        self.show_screen = show_screen
        self.gameplay_screen = None

        top = ctk.CTkFrame(self, fg_color=("gray86", "gray13"), corner_radius=18)
        top.pack(fill="x", padx=18, pady=(18, 10))
        title_stack = ctk.CTkFrame(top, fg_color="transparent")
        title_stack.pack(side="left", fill="x", expand=True, padx=18, pady=14)
        self.eyebrow_label = ctk.CTkLabel(
            title_stack,
            text="RACE WEEKEND",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=ACCENT,
            anchor="w",
        )
        self.eyebrow_label.pack(anchor="w")
        self.title_label = ctk.CTkLabel(
            title_stack,
            text="Race Weekend",
            font=ctk.CTkFont(size=27, weight="bold"),
            anchor="w",
        )
        self.title_label.pack(anchor="w", fill="x", pady=(2, 0))
        self.subtitle_label = ctk.CTkLabel(
            title_stack,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=MUTED,
            anchor="w",
        )
        self.subtitle_label.pack(anchor="w", fill="x", pady=(4, 0))
        ctk.CTkButton(
            top,
            text="<- Gameplay",
            command=lambda: self.show_screen("GameplayScreen"),
            width=118,
            height=34,
            fg_color="gray30",
            hover_color="gray40",
            font=ctk.CTkFont(size=11),
        ).pack(side="right", padx=18, pady=18)

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=18, pady=(0, 10))
        content.grid_columnconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=2)
        content.grid_rowconfigure(0, weight=1)

        self.summary_box = ctk.CTkFrame(content, fg_color=("gray90", "gray15"), corner_radius=16)
        self.summary_box.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.summary_frame = ctk.CTkScrollableFrame(self.summary_box, fg_color="transparent")
        self.summary_frame.pack(fill="both", expand=True, padx=12, pady=12)

        setup_box = ctk.CTkFrame(content, fg_color=("gray90", "gray15"), corner_radius=16)
        setup_box.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        setup_header = ctk.CTkFrame(setup_box, fg_color="transparent")
        setup_header.pack(fill="x", padx=14, pady=(12, 4))
        self.setup_title_label = ctk.CTkLabel(
            setup_header,
            text="Manual Setup",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=ACCENT,
        )
        self.setup_title_label.pack(side="left")
        self.setup_subtitle_label = ctk.CTkLabel(setup_box, text="", text_color="gray", font=ctk.CTkFont(size=11))
        self.setup_subtitle_label.pack(anchor="w", padx=16, pady=(0, 4))
        self.setup_frame = ctk.CTkScrollableFrame(setup_box, fg_color="transparent")
        self.setup_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=18, pady=(0, 12))
        self.status_label = ctk.CTkLabel(bottom, text="", text_color="gray", font=ctk.CTkFont(size=11))
        self.status_label.pack(side="left")
        ctk.CTkButton(
            bottom,
            text="Re-export Roster",
            command=self.reexport_roster,
            width=145,
            height=34,
            fg_color=ACCENT_DARK,
            hover_color="#103d62",
            font=ctk.CTkFont(size=11, weight="bold"),
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            bottom,
            text="Enter Race",
            command=self.enter_results_screen,
            width=180,
            height=38,
            corner_radius=12,
            fg_color=SUCCESS,
            hover_color=SUCCESS_DARK,
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(side="right")

    def set_gameplay_screen(self, gameplay_screen) -> None:
        self.gameplay_screen = gameplay_screen

    def on_show(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        gameplay = self.gameplay_screen
        for widget in self.summary_frame.winfo_children():
            widget.destroy()
        for widget in self.setup_frame.winfo_children():
            widget.destroy()
        self.status_label.configure(text="")

        if gameplay is None or not getattr(gameplay, "championship", None):
            self.title_label.configure(text="Race Weekend")
            self.subtitle_label.configure(text="No active championship loaded.")
            ctk.CTkLabel(self.summary_frame, text="Load a save to see race weekend details.", text_color="gray").pack(pady=24)
            return
        if gameplay.current_race >= len(gameplay.schedule):
            self.title_label.configure(text="Race Weekend Complete")
            self.subtitle_label.configure(text="This championship has no remaining races.")
            ctk.CTkLabel(self.summary_frame, text="The current season is complete.", text_color="gray").pack(pady=24)
            return

        race = gameplay.schedule[gameplay.current_race]
        championship = gameplay.championship or {}
        self.eyebrow_label.configure(text=f"{getattr(gameplay, 'game', '')} RACE WEEKEND")
        self.title_label.configure(text=str(championship.get("Championship", "Race Weekend")))
        self.subtitle_label.configure(
            text=f"Round {race.get('race_num', gameplay.current_race + 1)} of {len(gameplay.schedule)} | {race.get('track', '')}"
        )

        date_text = gameplay._display_date(race) if hasattr(gameplay, "_display_date") else str(race.get("date", ""))
        time_text = gameplay._display_time(str(race.get("time_of_day", ""))) if hasattr(gameplay, "_display_time") else str(race.get("time_of_day", ""))
        weather_text = gameplay._display_weather(race) if hasattr(gameplay, "_display_weather") else str(race.get("weather", ""))
        difficulty_text = gameplay._difficulty_display() if hasattr(gameplay, "_difficulty_display") else str(getattr(gameplay, "starting_difficulty", ""))
        opponent_count, opponent_classes = gameplay._opponent_summary() if hasattr(gameplay, "_opponent_summary") else (0, "-")
        if hasattr(gameplay, "ensure_current_race_briefing"):
            gameplay.ensure_current_race_briefing()

        self._hero_card(str(race.get("track", "")), str(race.get("layout", "")), date_text, time_text)
        self._section("Weekend Snapshot")
        stats = ctk.CTkFrame(self.summary_frame, fg_color="transparent")
        stats.pack(fill="x", pady=(0, 6))
        self._stat_card(stats, "Weather", weather_text)
        self._stat_card(stats, "Difficulty", difficulty_text)

        self._stat_card(stats, "Opponents", str(opponent_count))
        self._section("Race Details")
        self._info("Championship", str(championship.get("Championship", "")))
        self._info("Layout", str(race.get("layout", "")))
        self._info("Opponents", str(opponent_count))
        self._info("Opponent Class", opponent_classes)
        self._info("Race Length", f"{championship.get('Race_Time', '-')} min")
        self._info("Start Type", str(championship.get("Start_Type", "")))

        self._section("Player")
        player_car = gameplay.player_car or {}
        self._info("Car", str(player_car.get("Car", "Unassigned")))
        team_name = str((gameplay.player_team_offer or {}).get("team_name", "")).strip()
        if team_name:
            self._info("Team", team_name)
        liveries = list(getattr(gameplay, "player_liveries", []) or [])
        if str(getattr(gameplay, "game", "")).strip().casefold() == "ams2":
            if liveries:
                for entry in liveries:
                    driver_name = str(entry.get("driver_name", "")).strip() or "Player"
                    self._info(f"{driver_name} Livery", str(entry.get("livery_name", "")).strip() or "-")
            else:
                self._info("Livery", "Re-export roster to refresh")

        self._section("Weekend Flow")
        self._flow_step("1", "Review setup", "Confirm weather, time, roster, livery, and difficulty.")
        self._flow_step("2", "Launch in game", "Use the setup panel as your checklist before entering the session.")
        self._flow_step("3", "Save results", "Enter Race opens live sync, manual sorting, imports, and result saving.")

        build_manual_setup_content(
            self.setup_frame,
            gameplay,
            title_label=self.setup_title_label,
            subtitle_label=self.setup_subtitle_label,
        )

    def _section(self, text: str) -> None:
        ctk.CTkLabel(
            self.summary_frame,
            text=text,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=ACCENT,
            anchor="w",
        ).pack(fill="x", pady=(8, 4))

    def _hero_card(self, track: str, layout: str, date_text: str, time_text: str) -> None:
        card = ctk.CTkFrame(self.summary_frame, fg_color=("#dce9f8", "#10263a"), corner_radius=16)
        card.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(
            card,
            text=track or "Next Race",
            font=ctk.CTkFont(size=21, weight="bold"),
            anchor="w",
            wraplength=330,
        ).pack(fill="x", padx=14, pady=(14, 2))
        ctk.CTkLabel(
            card,
            text=layout or "Layout TBD",
            font=ctk.CTkFont(size=12),
            text_color=MUTED,
            anchor="w",
            wraplength=330,
        ).pack(fill="x", padx=14)
        pill_row = ctk.CTkFrame(card, fg_color="transparent")
        pill_row.pack(fill="x", padx=14, pady=(10, 14))
        self._pill(pill_row, date_text or "-")
        self._pill(pill_row, time_text or "-")

    def _pill(self, parent, text: str) -> None:
        ctk.CTkLabel(
            parent,
            text=text,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=("#c6dcf5", "#173a59"),
            corner_radius=12,
            width=92,
            height=24,
        ).pack(side="left", padx=(0, 8))

    def _stat_card(self, parent, label: str, value: str) -> None:
        card = ctk.CTkFrame(parent, fg_color=CARD_ALT, corner_radius=12)
        card.pack(fill="x", pady=3)
        ctk.CTkLabel(card, text=label.upper(), font=ctk.CTkFont(size=9, weight="bold"), text_color=MUTED).pack(
            anchor="w", padx=12, pady=(8, 0)
        )
        ctk.CTkLabel(card, text=value, font=ctk.CTkFont(size=12, weight="bold"), anchor="w", wraplength=310).pack(
            fill="x", padx=12, pady=(0, 8)
        )

    def _info(self, label: str, value: str) -> None:
        row = ctk.CTkFrame(self.summary_frame, fg_color="transparent")
        row.pack(fill="x", pady=1)
        ctk.CTkLabel(row, text=f"{label}:", width=112, anchor="w", text_color="gray", font=ctk.CTkFont(size=11)).pack(
            side="left"
        )
        ctk.CTkLabel(row, text=value, anchor="w", justify="left", font=ctk.CTkFont(size=11), wraplength=260).pack(
            side="left", fill="x", expand=True
        )

    def _note(self, text: str) -> None:
        ctk.CTkLabel(
            self.summary_frame,
            text=text,
            anchor="w",
            justify="left",
            text_color="gray",
            font=ctk.CTkFont(size=11),
            wraplength=340,
        ).pack(fill="x", pady=2)

    def _flow_step(self, number: str, title: str, body: str) -> None:
        row = ctk.CTkFrame(self.summary_frame, fg_color=CARD_ALT, corner_radius=12)
        row.pack(fill="x", pady=4)
        ctk.CTkLabel(
            row,
            text=number,
            width=30,
            height=30,
            fg_color=ACCENT_DARK,
            corner_radius=15,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left", padx=10, pady=10)
        text_stack = ctk.CTkFrame(row, fg_color="transparent")
        text_stack.pack(side="left", fill="x", expand=True, padx=(0, 10), pady=8)
        ctk.CTkLabel(text_stack, text=title, font=ctk.CTkFont(size=12, weight="bold"), anchor="w").pack(fill="x")
        ctk.CTkLabel(
            text_stack,
            text=body,
            font=ctk.CTkFont(size=10),
            text_color=MUTED,
            anchor="w",
            justify="left",
            wraplength=280,
        ).pack(fill="x")

    def _send_pre_race_briefing(
        self,
        *,
        race: dict,
        championship: dict,
        weather_text: str,
        opponent_count: int,
        opponent_classes: str,
    ) -> None:
        gameplay = self.gameplay_screen
        if gameplay is None:
            return
        race_index = int(getattr(gameplay, "current_race", 0) or 0)
        round_number = race.get("race_num", race_index + 1)
        total_rounds = len(getattr(gameplay, "schedule", []) or [])
        track = str(race.get("track", "")).strip() or "the next venue"
        layout = str(race.get("layout", "")).strip()
        championship_name = str(championship.get("Championship", "")).strip() or "the championship"
        race_time = str(championship.get("Race_Time", "-")).strip()
        start_type = str(championship.get("Start_Type", "")).strip() or "standard"

        lines = [
            f"Round {round_number} of {total_rounds} is next: {track}{f' ({layout})' if layout else ''}.",
            f"You are racing in {championship_name}.",
            f"Race control expects {opponent_count} opponents across {opponent_classes}.",
            f"Scheduled race length is {race_time} minutes with a {start_type} start.",
            f"Forecast: {weather_text or 'Clear'}."
        ]

        focus_lines = self._pre_race_focus_lines()
        if focus_lines:
            lines.append("")
            lines.extend(focus_lines)

        lines.append("")
        lines.append("Review the setup panel, confirm the roster, and make sure the session settings match before going green.")

        self._add_race_control_message(
            f"Pre-Race Briefing: Round {round_number}",
            "\n".join(lines),
            dedupe_suffix=f"pre-race-briefing:{race_index}",
        )

    def _pre_race_focus_lines(self) -> list[str]:
        gameplay = self.gameplay_screen
        if gameplay is None:
            return []

        lines: list[str] = []
        heat = {
            str(name).strip(): int(stage or 0)
            for name, stage in dict(getattr(gameplay, "rivalry_heat", {}) or {}).items()
            if str(name).strip() and int(stage or 0) > 0
        }
        if heat:
            hottest_name, hottest_stage = max(heat.items(), key=lambda item: item[1])
            stage_text = "red-hot" if hottest_stage >= 3 else ("heated" if hottest_stage == 2 else "building")
            lines.append(f"Rivalry watch: {hottest_name} is a {stage_text} matchup. Keep it clean, but do not give away easy track position.")

        watch_drivers = [
            str(name).strip()
            for name in list(getattr(gameplay, "watch_drivers", []) or [])
            if str(name).strip()
        ]
        if watch_drivers:
            lines.append(f"Drivers to watch: {', '.join(watch_drivers[:3])}.")

        rising_driver = str(getattr(gameplay, "rising_driver", "") or "").strip()
        if rising_driver:
            lines.append(f"Form guide: {rising_driver} has been marked as a rising driver by the paddock.")

        return lines

    def reexport_roster(self) -> None:
        gameplay = self.gameplay_screen
        if gameplay is None:
            return
        gameplay.reexport_roster()
        self._refresh()
        self.status_label.configure(text="Roster re-export requested.", text_color="#6bbd6b")
        if str(getattr(gameplay, "game", "")).strip().casefold() == "ams2":
            self._add_race_control_message(
                "AMS2 Driver Roster Refreshed",
                "Race Control has re-exported your AMS2 Custom AI roster for the current championship.\n\n"
                "Before entering the session, restart Automobilista 2 if it was already open so the game reloads the updated driver list.",
            )

    def enter_results_screen(self) -> None:
        gameplay = self.gameplay_screen
        if gameplay is not None and str(getattr(gameplay, "game", "")).strip().casefold() == "ams2":
            roster_validation = validate_ams2_roster_files(
                getattr(gameplay, "championship", {}) or {},
                list(getattr(gameplay, "standings", []) or []),
                list(getattr(gameplay, "player_names", []) or []),
            )
            if not roster_validation.ok:
                self.status_label.configure(text=roster_validation.message, text_color="#ff7777")
                self._refresh()
                self.status_label.configure(text=roster_validation.message, text_color="#ff7777")
                self._add_race_control_message(
                    "AMS2 Roster Check Failed",
                    f"{roster_validation.message}\n\n"
                    "Use Re-export Roster, then restart Automobilista 2 before entering the race. "
                    "This helps prevent old AI names from staying loaded in-game.",
                )
                return
            self.status_label.configure(text=roster_validation.message, text_color="#6bbd6b")
        if gameplay is not None and getattr(gameplay, "race_status_label", None) is not None:
            gameplay.race_status_label.configure(text="")
        self.show_screen("ManualResultsScreen")

    def _add_race_control_message(self, title: str, body: str, *, dedupe_suffix: str | None = None) -> None:
        gameplay = self.gameplay_screen
        if gameplay is None:
            return
        messages = [dict(message) for message in list(getattr(gameplay, "messages", []) or []) if isinstance(message, dict)]
        dedupe_key = f"race-weekend:{getattr(gameplay, 'current_race', 0)}:{dedupe_suffix or title}"
        if any(str(message.get("dedupe_key", "")) == dedupe_key for message in messages):
            return
        messages.append(
            {
                "id": f"msg-{uuid4().hex}",
                "title": title,
                "body": body,
                "category": "Race Control",
                "sender": "Race Control",
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "read": False,
                "dedupe_key": dedupe_key,
            }
        )
        gameplay.messages = messages
        save_name = str(getattr(gameplay, "save_name", "") or "").strip()
        if save_name:
            update_save(save_name, {"messages": messages})
        if hasattr(gameplay, "_refresh_message_button"):
            gameplay._refresh_message_button()
