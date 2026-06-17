from __future__ import annotations

import customtkinter as ctk

from ..driver_pool import get_world_year, list_drivers_page, top_rookies_for_year, world_db_path
from ..save_manager import load_save


class DriverPoolScreen(ctk.CTkFrame):
    def __init__(self, parent, show_screen) -> None:
        super().__init__(parent, fg_color="transparent")
        self.show_screen = show_screen
        self.gameplay_screen = None
        self.back_screen = "GameplayScreen"
        self.context_save_name: str | None = None
        self.context_tier: int | None = None
        self.context_style: str | None = None
        self.include_retired = False
        self.pending_include_retired = False
        self.discipline_filter = ctk.StringVar(value="All")
        self.tier_filter = ctk.StringVar(value="All")
        self.search_filter = ctk.StringVar(value="")
        self.sort_filter = ctk.StringVar(value="MMR")
        self.rival_filter = ctk.StringVar(value="All")
        self.applied_discipline = "All"
        self.applied_tier = "All"
        self.applied_search = ""
        self.applied_sort = "MMR"
        self.applied_rival = "All"
        self.page_size = 100
        self.current_offset = 0
        self.total_drivers = 0
        self.top_rookie_names: set[str] = set()
        self.rivalry_heat: dict[str, int] = {}

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(18, 8))

        self.title_label = ctk.CTkLabel(top, text="Driver Pool", font=ctk.CTkFont(size=22, weight="bold"))
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

        self.toggle_retired_btn = ctk.CTkButton(
            controls,
            text="Show Retired",
            command=self.toggle_retired,
            width=130,
            height=30,
            fg_color="gray30",
            hover_color="gray40",
            font=ctk.CTkFont(size=11),
        )
        self.toggle_retired_btn.pack(side="left")

        ctk.CTkLabel(controls, text="Search:", font=ctk.CTkFont(size=11), text_color="gray").pack(
            side="left", padx=(14, 6)
        )
        self.search_entry = ctk.CTkEntry(
            controls,
            textvariable=self.search_filter,
            width=150,
            height=30,
            font=ctk.CTkFont(size=11),
            placeholder_text="Driver name",
        )
        self.search_entry.pack(side="left")
        self.search_entry.bind("<Return>", lambda _event: self.apply_filters())

        ctk.CTkLabel(controls, text="Discipline:", font=ctk.CTkFont(size=11), text_color="gray").pack(
            side="left", padx=(14, 6)
        )
        self.discipline_menu = ctk.CTkOptionMenu(
            controls,
            values=["All", "Sports Car", "Oval", "Open Wheel", "Rallycross"],
            variable=self.discipline_filter,
            width=130,
            height=30,
            font=ctk.CTkFont(size=11),
        )
        self.discipline_menu.pack(side="left")

        ctk.CTkLabel(controls, text="Tier:", font=ctk.CTkFont(size=11), text_color="gray").pack(
            side="left", padx=(14, 6)
        )
        self.tier_menu = ctk.CTkOptionMenu(
            controls,
            values=["All", "1", "2", "3", "4", "5"],
            variable=self.tier_filter,
            width=90,
            height=30,
            font=ctk.CTkFont(size=11),
        )
        self.tier_menu.pack(side="left")

        ctk.CTkLabel(controls, text="Sort:", font=ctk.CTkFont(size=11), text_color="gray").pack(
            side="left", padx=(14, 6)
        )
        self.sort_menu = ctk.CTkOptionMenu(
            controls,
            values=["MMR", "Name", "Wins", "Podiums", "Titles", "Seasons"],
            variable=self.sort_filter,
            width=110,
            height=30,
            font=ctk.CTkFont(size=11),
        )
        self.sort_menu.pack(side="left")

        ctk.CTkLabel(controls, text="Rivals:", font=ctk.CTkFont(size=11), text_color="gray").pack(
            side="left", padx=(14, 6)
        )
        self.rival_menu = ctk.CTkOptionMenu(
            controls,
            values=["All", "Rivals"],
            variable=self.rival_filter,
            width=95,
            height=30,
            font=ctk.CTkFont(size=11),
        )
        self.rival_menu.pack(side="left")

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

    def set_context(self, save_name: str | None, tier: int | None = None, style: str | None = None) -> None:
        self.context_save_name = save_name
        self.context_tier = tier
        self.context_style = style

    def on_show(self) -> None:
        current_tier = self.context_tier if self.context_tier not in (None, "") else getattr(self.gameplay_screen, "tier", None)
        current_style = self.context_style if self.context_style not in (None, "") else getattr(self.gameplay_screen, "style", None)
        default_tier = str(current_tier) if current_tier not in (None, "") else "All"
        default_style = current_style if current_style in {"Sports Car", "Oval", "Open Wheel", "Rallycross"} else "All"
        self.pending_include_retired = False
        self.include_retired = False
        self.applied_tier = default_tier
        self.applied_discipline = default_style
        self.applied_search = ""
        self.applied_sort = "MMR"
        self.applied_rival = "All"
        self.tier_filter.set(default_tier)
        self.discipline_filter.set(default_style)
        self.search_filter.set("")
        self.sort_filter.set("MMR")
        self.rival_filter.set("All")
        self._update_retired_button()
        self.refresh(reset_page=True)

    def toggle_retired(self) -> None:
        self.pending_include_retired = not self.pending_include_retired
        self._update_retired_button()

    def _update_retired_button(self) -> None:
        self.toggle_retired_btn.configure(text="Hide Retired" if self.pending_include_retired else "Show Retired")

    def apply_filters(self) -> None:
        self.include_retired = self.pending_include_retired
        self.applied_discipline = self.discipline_filter.get()
        self.applied_tier = self.tier_filter.get()
        self.applied_search = self.search_filter.get()
        self.applied_sort = self.sort_filter.get()
        self.applied_rival = self.rival_filter.get()
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

        current_world_year = get_world_year(save_name)
        save_data = load_save(save_name) or {}
        active_player_name = str(getattr(self.gameplay_screen, "active_player_name", "") or save_data.get("active_player_name", "")).strip()
        saved_perspectives = save_data.get("player_perspectives") if isinstance(save_data.get("player_perspectives"), dict) else {}
        active_saved_perspective = (
            saved_perspectives.get(active_player_name)
            if active_player_name and isinstance(saved_perspectives.get(active_player_name), dict)
            else {}
        )
        saved_heat_source = active_saved_perspective.get("rivalry_heat") if active_saved_perspective else save_data.get("rivalry_heat")
        saved_heat = {
            str(name).strip(): int(stage)
            for name, stage in dict(saved_heat_source or {}).items()
            if str(name).strip() and str(stage).strip() in {"1", "2", "3"}
        }
        if hasattr(self.gameplay_screen, "_active_rivalry_heat"):
            active_heat_source = self.gameplay_screen._active_rivalry_heat()
        else:
            active_heat_source = getattr(self.gameplay_screen, "rivalry_heat", {})
        active_heat = {
            str(name).strip(): int(stage)
            for name, stage in dict(active_heat_source or {}).items()
            if str(name).strip() and str(stage).strip() in {"1", "2", "3"}
        }
        self.rivalry_heat = dict(saved_heat)
        self.rivalry_heat.update(active_heat)
        for name, stage in saved_heat.items():
            if int(stage) >= 3:
                self.rivalry_heat[name] = 3
        rival_names = {
            name
            for name, stage in self.rivalry_heat.items()
            if int(stage) >= 3
        }
        self.top_rookie_names = {
            str(driver.get("name", "")).strip()
            for driver in top_rookies_for_year(save_name, current_world_year, limit=5)
        }

        rival_filter_active = self.applied_rival == "Rivals"
        drivers, self.total_drivers = list_drivers_page(
            save_name,
            include_retired=self.include_retired,
            discipline="All" if rival_filter_active else self.applied_discipline,
            tier="All" if rival_filter_active else self.applied_tier,
            search=self.applied_search,
            sort_by=self.applied_sort,
            driver_names=rival_names if rival_filter_active else None,
            limit=self.page_size,
            offset=self.current_offset,
        )
        self.subtitle_label.configure(text=f"Save: {save_name} | DB: {world_db_path(save_name).name}")
        shown_start = 0 if self.total_drivers == 0 else self.current_offset + 1
        shown_end = min(self.current_offset + len(drivers), self.total_drivers)
        self.status_label.configure(text=f"Showing {shown_start}-{shown_end} of {self.total_drivers}")
        self.prev_btn.configure(state="normal" if self.current_offset > 0 else "disabled")
        self.next_btn.configure(
            state="normal" if self.current_offset + self.page_size < self.total_drivers else "disabled"
        )

        header = ctk.CTkFrame(self.table_frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, 4))
        for text, width in [
            ("Name", 180),
            ("Type", 70),
            ("Status", 80),
            ("Primary", 100),
            ("Tier", 45),
            ("Style", 90),
            ("Current Championship", 180),
            ("MMR", 70),
            ("Seasons", 70),
            ("Wins", 55),
            ("Podiums", 65),
            ("Titles", 55),
        ]:
            ctk.CTkLabel(
                header,
                text=text,
                width=width,
                anchor="w",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color="gray",
            ).pack(side="left", padx=3)

        if not drivers:
            ctk.CTkLabel(self.table_frame, text="No drivers found for this save.", text_color="gray").pack(pady=20)
            return

        for driver in drivers:
            is_human = bool(driver.get("is_human"))
            is_retired = str(driver.get("status", "")).casefold() == "retired"
            is_top_rookie = (
                not is_human
                and not is_retired
                and str(driver.get("name", "")).strip() in self.top_rookie_names
            )
            row = ctk.CTkFrame(
                self.table_frame,
                fg_color=("#ddeeff", "#1a3a55")
                if is_human
                else (
                    ("#e7d9ff", "#3b2854")
                    if is_top_rookie
                    else (("#dedede", "#2b2b2b") if is_retired else ("gray80", "gray22"))
                ),
                corner_radius=6,
            )
            row.pack(fill="x", pady=2)
            heat_color = self._rivalry_stripe_color(driver.get("name", ""))
            if heat_color:
                ctk.CTkFrame(
                    row,
                    fg_color=heat_color,
                    width=5,
                    height=26,
                    corner_radius=4,
                ).pack(side="left", padx=(0, 3), pady=3)
            values = [
                (driver.get("name", ""), 180),
                ("Human" if is_human else "AI", 70),
                (driver.get("status", ""), 80),
                (driver.get("primary_style", ""), 100),
                (self._display_empty(driver.get("current_tier")), 45),
                (driver.get("current_style") or "-", 90),
                (driver.get("current_championship") or "-", 180),
                (str(driver.get("mmr", "")), 70),
                (str(driver.get("seasons_completed", "")), 70),
                (str(driver.get("wins", "")), 55),
                (str(driver.get("podiums", "")), 65),
                (str(driver.get("championships", "")), 55),
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
                command=lambda current_driver=driver: self.open_driver_detail(current_driver),
            ).pack(side="right", padx=6, pady=4)

    def next_page(self) -> None:
        if self.current_offset + self.page_size >= self.total_drivers:
            return
        self.current_offset += self.page_size
        self.refresh()

    def previous_page(self) -> None:
        if self.current_offset <= 0:
            return
        self.current_offset = max(0, self.current_offset - self.page_size)
        self.refresh()

    @staticmethod
    def _display_empty(value) -> str:
        if value is None or value == "":
            return "-"
        return str(value)

    def _rivalry_stripe_color(self, driver_name: str) -> str:
        stage = int(self.rivalry_heat.get(str(driver_name).strip(), 0) or 0)
        if stage >= 3:
            return "#e04747"
        if stage == 2:
            return "#f08a24"
        if stage == 1:
            return "#e8c632"
        return ""

    def open_driver_detail(self, driver: dict) -> None:
        save_name = self.context_save_name or getattr(self.gameplay_screen, "save_name", None)
        driver_id = str(driver.get("id", "")).strip()
        if not save_name or not driver_id:
            return
        detail_screen = self.master.screens["DriverDetailScreen"]
        if hasattr(detail_screen, "set_context"):
            detail_screen.set_context(save_name, driver_id, "DriverPoolScreen")
        self.show_screen("DriverDetailScreen")
