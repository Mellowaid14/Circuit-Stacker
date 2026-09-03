from __future__ import annotations

import customtkinter as ctk


class ScheduleScreen(ctk.CTkFrame):
    def __init__(self, parent, show_screen) -> None:
        super().__init__(parent, fg_color="transparent")
        self.parent = parent
        self.show_screen = show_screen
        self.gameplay_screen = None

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(18, 8))

        self.title_label = ctk.CTkLabel(top, text="Championship Schedule", font=ctk.CTkFont(size=22, weight="bold"))
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

        self.subtitle_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=11), text_color="gray")
        self.subtitle_label.pack(pady=(0, 8))

        table_box = ctk.CTkFrame(self, fg_color=("gray90", "gray15"), corner_radius=12)
        table_box.pack(fill="both", expand=True, padx=24, pady=(0, 14))
        self.table_frame = ctk.CTkScrollableFrame(table_box, fg_color="transparent")
        self.table_frame.pack(fill="both", expand=True, padx=10, pady=10)

    def set_gameplay_screen(self, gameplay_screen) -> None:
        self.gameplay_screen = gameplay_screen

    def on_show(self) -> None:
        if self.gameplay_screen is not None and hasattr(self.gameplay_screen, "reload_active_rivals_state"):
            self.gameplay_screen.reload_active_rivals_state()
        for widget in self.table_frame.winfo_children():
            widget.destroy()

        if self.gameplay_screen is None or not getattr(self.gameplay_screen, "schedule", None):
            self.subtitle_label.configure(text="No schedule available.")
            ctk.CTkLabel(self.table_frame, text="No schedule available.", text_color="gray").pack(pady=20)
            return

        championship = self.gameplay_screen.championship or {}
        self.subtitle_label.configure(text=f"{championship.get('Championship', 'Championship')} | Save: {self.gameplay_screen.save_name or '-'}")

        header = ctk.CTkFrame(self.table_frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, 2))
        for column, width in [
            ("#", 32),
            ("Track", 180),
            ("Layout", 220),
            ("Date", 100),
            ("Time", 75),
            ("Weather", 250),
            ("Results", 70),
        ]:
            ctk.CTkLabel(
                header,
                text=column,
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color="gray",
                width=width,
                anchor="w",
            ).pack(side="left", padx=3)

        for index, race in enumerate(self.gameplay_screen.schedule):
            is_current = index == self.gameplay_screen.current_race
            row = ctk.CTkFrame(
                self.table_frame,
                fg_color=("#ddeeff", "#1a3a55") if is_current else ("gray80", "gray22"),
                corner_radius=6,
            )
            row.pack(fill="x", pady=2)
            values = [
                (str(race.get("race_num", "")), 32),
                (self.gameplay_screen._fit_cell_text(race.get("track", ""), 28), 180),
                (self.gameplay_screen._fit_cell_text(race.get("layout", ""), 36), 220),
                (self.gameplay_screen._display_date(race), 100),
                (self.gameplay_screen._display_time(str(race.get("time_of_day", ""))), 75),
                (self.gameplay_screen._fit_cell_text(self.gameplay_screen._display_weather(race), 42), 250),
            ]
            for value, width in values:
                ctk.CTkLabel(row, text=value, font=ctk.CTkFont(size=11), width=width, anchor="w").pack(
                    side="left", padx=3, pady=5
                )
            ctk.CTkButton(
                row,
                text="View",
                width=60,
                height=24,
                font=ctk.CTkFont(size=10),
                command=lambda value=index: self.open_race_results(value),
            ).pack(side="left", padx=4, pady=4)

    def open_race_results(self, race_index: int) -> None:
        race_results_screen = self.parent.screens["RaceResultsScreen"]
        if hasattr(race_results_screen, "set_race_index"):
            race_results_screen.set_race_index(race_index)
        self.show_screen("RaceResultsScreen")
