from __future__ import annotations

import customtkinter as ctk

from ..driver_pool import list_teams_page, world_db_path


class TeamPoolScreen(ctk.CTkFrame):
    def __init__(self, parent, show_screen) -> None:
        super().__init__(parent, fg_color="transparent")
        self.parent = parent
        self.show_screen = show_screen
        self.gameplay_screen = None
        self.back_screen = "GameplayScreen"
        self.context_save_name: str | None = None
        self.search_filter = ctk.StringVar(value="")
        self.sort_filter = ctk.StringVar(value="Reputation")
        self.applied_search = ""
        self.applied_sort = "Reputation"
        self.page_size = 100
        self.current_offset = 0
        self.total_teams = 0

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(18, 8))
        self.title_label = ctk.CTkLabel(top, text="Team Pool", font=ctk.CTkFont(size=22, weight="bold"))
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

        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.pack(fill="x", padx=24, pady=(0, 8))
        ctk.CTkLabel(controls, text="Search:", font=ctk.CTkFont(size=11), text_color="gray").pack(side="left", padx=(0, 6))
        search_entry = ctk.CTkEntry(
            controls,
            textvariable=self.search_filter,
            width=180,
            height=30,
            font=ctk.CTkFont(size=11),
            placeholder_text="Team, game, style",
        )
        search_entry.pack(side="left")
        search_entry.bind("<Return>", lambda _event: self.apply_filters())

        ctk.CTkLabel(controls, text="Sort:", font=ctk.CTkFont(size=11), text_color="gray").pack(side="left", padx=(14, 6))
        ctk.CTkOptionMenu(
            controls,
            values=["Reputation", "Name", "Titles", "Wins", "Seasons"],
            variable=self.sort_filter,
            width=125,
            height=30,
            font=ctk.CTkFont(size=11),
        ).pack(side="left")
        ctk.CTkButton(
            controls,
            text="Apply",
            command=self.apply_filters,
            width=65,
            height=30,
            fg_color="gray30",
            hover_color="gray40",
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=(10, 0))

        self.status_label = ctk.CTkLabel(controls, text="", font=ctk.CTkFont(size=11), text_color="gray")
        self.status_label.pack(side="left", padx=(14, 0))
        self.prev_btn = ctk.CTkButton(
            controls,
            text="< Prev",
            command=self.previous_page,
            width=75,
            height=30,
            fg_color="gray30",
            hover_color="gray40",
            font=ctk.CTkFont(size=11),
        )
        self.prev_btn.pack(side="right", padx=(8, 0))
        self.next_btn = ctk.CTkButton(
            controls,
            text="Next >",
            command=self.next_page,
            width=75,
            height=30,
            fg_color="gray30",
            hover_color="gray40",
            font=ctk.CTkFont(size=11),
        )
        self.next_btn.pack(side="right")

        table_box = ctk.CTkFrame(self, fg_color=("gray90", "gray15"), corner_radius=12)
        table_box.pack(fill="both", expand=True, padx=24, pady=(0, 14))
        self.table_frame = ctk.CTkScrollableFrame(table_box, fg_color="transparent")
        self.table_frame.pack(fill="both", expand=True, padx=10, pady=10)

    def set_gameplay_screen(self, gameplay_screen) -> None:
        self.gameplay_screen = gameplay_screen

    def set_back_screen(self, screen_name: str) -> None:
        self.back_screen = screen_name or "GameplayScreen"

    def set_context(self, save_name: str | None) -> None:
        self.context_save_name = save_name

    def on_show(self) -> None:
        self.applied_search = ""
        self.applied_sort = "Reputation"
        self.search_filter.set("")
        self.sort_filter.set("Reputation")
        self.refresh(reset_page=True)

    def apply_filters(self) -> None:
        self.applied_search = self.search_filter.get()
        self.applied_sort = self.sort_filter.get()
        self.refresh(reset_page=True)

    def refresh(self, reset_page: bool = False) -> None:
        for widget in self.table_frame.winfo_children():
            widget.destroy()
        if reset_page:
            self.current_offset = 0

        save_name = self.context_save_name or getattr(self.gameplay_screen, "save_name", None)
        if not save_name:
            self.subtitle_label.configure(text="No save loaded.")
            self.status_label.configure(text="")
            return

        teams, self.total_teams = list_teams_page(
            save_name,
            search=self.applied_search,
            sort_by=self.applied_sort,
            limit=self.page_size,
            offset=self.current_offset,
        )
        self.subtitle_label.configure(text=f"Save: {save_name} | DB: {world_db_path(save_name).name}")
        shown_start = 0 if self.total_teams == 0 else self.current_offset + 1
        shown_end = min(self.current_offset + len(teams), self.total_teams)
        self.status_label.configure(text=f"Showing {shown_start}-{shown_end} of {self.total_teams}")
        self.prev_btn.configure(state="normal" if self.current_offset > 0 else "disabled")
        self.next_btn.configure(state="normal" if self.current_offset + self.page_size < self.total_teams else "disabled")

        header = ctk.CTkFrame(self.table_frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, 4))
        for text, width in [
            ("Team", 220),
            ("Game", 80),
            ("Str", 55),
            ("Move", 60),
            ("Amb", 55),
            ("Funds", 55),
            ("Base", 55),
            ("Trend", 80),
            ("Seasons", 70),
            ("Titles", 55),
            ("Wins", 55),
            ("Podiums", 70),
            ("Last Style", 100),
            ("Last Championship", 210),
        ]:
            ctk.CTkLabel(
                header,
                text=text,
                width=width,
                anchor="w",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color="gray",
            ).pack(side="left", padx=3)

        if not teams:
            ctk.CTkLabel(self.table_frame, text="No teams found for this save.", text_color="gray").pack(pady=20)
            return

        for team in teams:
            row = ctk.CTkFrame(self.table_frame, fg_color=("gray80", "gray22"), corner_radius=6)
            row.pack(fill="x", pady=2)
            values = [
                (team.get("team_name", ""), 220),
                (team.get("game", ""), 80),
                (str(team.get("current_strength", team.get("reputation", ""))), 55),
                (self._movement_text(team), 60),
                (str(team.get("team_ambition", "")), 55),
                (str(team.get("team_financial_strength", "")), 55),
                (str(team.get("base_prestige", "")), 55),
                (str(team.get("trajectory", "stable")).title(), 80),
                (str(team.get("seasons_completed", "")), 70),
                (str(team.get("championships", "")), 55),
                (str(team.get("wins", "")), 55),
                (str(team.get("podiums", "")), 70),
                (team.get("last_style") or "-", 100),
                (team.get("last_championship") or "-", 210),
            ]
            for value, width in values:
                ctk.CTkLabel(row, text=str(value), width=width, anchor="w", font=ctk.CTkFont(size=11)).pack(
                    side="left", padx=3, pady=5
                )
            ctk.CTkButton(
                row,
                text="View",
                width=55,
                height=26,
                font=ctk.CTkFont(size=10),
                command=lambda current_team=team: self.open_team_detail(current_team),
            ).pack(side="right", padx=6, pady=4)

    @staticmethod
    def _movement_text(team: dict) -> str:
        delta = int(team.get("latest_strength_delta", 0) or 0)
        if delta > 0:
            return f"+{delta}"
        if delta < 0:
            return str(delta)
        return "-"

    def next_page(self) -> None:
        if self.current_offset + self.page_size >= self.total_teams:
            return
        self.current_offset += self.page_size
        self.refresh()

    def previous_page(self) -> None:
        if self.current_offset <= 0:
            return
        self.current_offset = max(0, self.current_offset - self.page_size)
        self.refresh()

    def open_team_detail(self, team: dict) -> None:
        save_name = self.context_save_name or getattr(self.gameplay_screen, "save_name", None)
        team_key = str(team.get("team_key", "")).strip()
        if not save_name or not team_key:
            return
        detail_screen = self.parent.screens["TeamDetailScreen"]
        if hasattr(detail_screen, "set_context"):
            detail_screen.set_context(save_name, team_key, "TeamPoolScreen")
        self.show_screen("TeamDetailScreen")
