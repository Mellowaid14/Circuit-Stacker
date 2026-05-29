from __future__ import annotations

import customtkinter as ctk

from ..driver_pool import get_driver_profile, get_world_year, rename_driver, top_rookies_for_year
from ..save_manager import load_save


class DriverDetailScreen(ctk.CTkFrame):
    def __init__(self, parent, show_screen) -> None:
        super().__init__(parent, fg_color="transparent")
        self.parent = parent
        self.show_screen = show_screen
        self.save_name: str | None = None
        self.driver_id: str | None = None
        self.back_screen = "DriverPoolScreen"

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(18, 8))

        self.title_label = ctk.CTkLabel(top, text="Driver Details", font=ctk.CTkFont(size=22, weight="bold"))
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
        ctk.CTkButton(
            top,
            text="Edit Name",
            command=self.edit_driver_name,
            width=100,
            height=30,
            fg_color="gray30",
            hover_color="gray40",
            font=ctk.CTkFont(size=11),
        ).pack(side="right", padx=(0, 8))

        self.subtitle_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=11), text_color="gray")
        self.subtitle_label.pack(pady=(0, 8))

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        summary_box = self._make_box(content, "Career Summary")
        summary_box.grid(row=0, column=0, padx=(0, 8), sticky="nsew")
        self.summary_frame = ctk.CTkScrollableFrame(summary_box, fg_color="transparent")
        self.summary_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        history_box = self._make_box(content, "Career History")
        history_box.grid(row=0, column=1, padx=(8, 0), sticky="nsew")
        self.history_frame = ctk.CTkScrollableFrame(history_box, fg_color="transparent")
        self.history_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

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
        ctk.CTkLabel(row, text=label, width=120, anchor="w", font=ctk.CTkFont(size=11), text_color="gray").pack(side="left")
        ctk.CTkLabel(row, text=value, anchor="w", font=ctk.CTkFont(size=11), justify="left").pack(side="left", fill="x", expand=True)

    def _section_label(self, parent, text: str) -> None:
        ctk.CTkLabel(
            parent,
            text=text,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=("#1a6fc4", "#4da6ff"),
            anchor="w",
        ).pack(fill="x", pady=(8, 2))

    def set_context(self, save_name: str, driver_id: str, back_screen: str = "DriverPoolScreen") -> None:
        self.save_name = save_name
        self.driver_id = driver_id
        self.back_screen = back_screen or "DriverPoolScreen"

    def edit_driver_name(self) -> None:
        if not self.save_name or not self.driver_id:
            self.subtitle_label.configure(text="No driver selected.")
            return
        profile = get_driver_profile(self.save_name, self.driver_id)
        current_name = str(((profile or {}).get("driver") or {}).get("name", "")).strip()
        prompt = f"Enter the new driver name:\nCurrent: {current_name}" if current_name else "Enter the new driver name:"
        dialog = ctk.CTkInputDialog(text=prompt, title="Edit Driver Name")
        new_name = str(dialog.get_input() or "").strip()
        if not new_name:
            return
        ok, message = rename_driver(self.save_name, self.driver_id, new_name)
        self.subtitle_label.configure(text=message)
        if ok:
            self._refresh_gameplay_state()
            self.on_show()

    def _refresh_gameplay_state(self) -> None:
        if not self.save_name:
            return
        gameplay_screen = getattr(self.parent, "screens", {}).get("GameplayScreen")
        if gameplay_screen is None or not hasattr(gameplay_screen, "load_state"):
            return
        save_data = load_save(self.save_name)
        if save_data:
            gameplay_screen.load_state(save_data)

    def on_show(self) -> None:
        for widget in self.summary_frame.winfo_children():
            widget.destroy()
        for widget in self.history_frame.winfo_children():
            widget.destroy()

        if not self.save_name or not self.driver_id:
            self.subtitle_label.configure(text="No driver selected.")
            return

        profile = get_driver_profile(self.save_name, self.driver_id)
        if not profile:
            self.subtitle_label.configure(text="Driver not found.")
            return

        driver = profile.get("driver") or {}
        season_history = profile.get("season_history") or []
        championship_history = profile.get("championship_history") or []
        discipline_changes = profile.get("discipline_changes") or []
        driver_name = str(driver.get("name", "Driver Details"))
        current_world_year = get_world_year(self.save_name)
        top_rookie_names = {
            str(item.get("name", "")).strip()
            for item in top_rookies_for_year(self.save_name, current_world_year, limit=5)
        }
        debut_year = int(driver.get("debut_year") or 0)
        rookie_watch_years: set[int] = set()
        if debut_year > 0:
            debut_top_rookie_names = {
                str(item.get("name", "")).strip()
                for item in top_rookies_for_year(self.save_name, debut_year, limit=5)
            }
            if driver_name.strip() in debut_top_rookie_names:
                rookie_watch_years.add(debut_year)
        title_text = driver_name
        if driver_name.strip() in top_rookie_names:
            title_text = f"{driver_name} - Rookie to Watch *"
        self.title_label.configure(text=title_text)
        self.subtitle_label.configure(
            text=f"Save: {self.save_name} | {'Human' if bool(driver.get('is_human')) else 'AI'} | {driver.get('status', '-')}"
        )

        self._section_label(self.summary_frame, "Current Snapshot")
        self._info_row(self.summary_frame, "MMR:", str(driver.get("mmr", "-")))
        self._info_row(self.summary_frame, "Primary Style:", str(driver.get("primary_style", "Unassigned")))
        self._info_row(self.summary_frame, "Current Tier:", str(driver.get("current_tier") or "-"))
        self._info_row(self.summary_frame, "Current Style:", str(driver.get("current_style") or "-"))
        self._info_row(self.summary_frame, "Current Series:", str(driver.get("current_championship") or "-"))

        self._section_label(self.summary_frame, "Career Totals")
        self._info_row(self.summary_frame, "Seasons:", str(driver.get("seasons_completed", 0)))
        self._info_row(self.summary_frame, "Starts:", str(driver.get("career_starts", 0)))
        self._info_row(self.summary_frame, "Wins:", str(driver.get("wins", 0)))
        self._info_row(self.summary_frame, "Podiums:", str(driver.get("podiums", 0)))
        self._info_row(self.summary_frame, "Titles:", str(driver.get("championships", 0)))
        if season_history:
            best_finish = min(int(item.get("finishing_place", 999) or 999) for item in season_history)
            self._info_row(self.summary_frame, "Best Finish:", f"P{best_finish}")
            styles_seen = {str(item.get("style", "")).strip() for item in season_history if str(item.get("style", "")).strip()}
            self._info_row(self.summary_frame, "Disciplines Run:", str(len(styles_seen)))
        if not bool(driver.get("is_human")):
            self._section_label(self.summary_frame, "AI Profile")
            self._info_row(
                self.summary_frame,
                "Retires After:",
                str(driver.get("retirement_after_seasons") or "-"),
            )
            self._info_row(self.summary_frame, "Status:", str(driver.get("status") or "-"))

        if championship_history:
            self._section_label(self.summary_frame, "Championship Titles")
            for title in championship_history[:6]:
                label = f"{title.get('season_year', '-')}:"
                class_name = str(title.get("class_name", "")).strip()
                title_name = str(title.get("championship_name", "")).strip()
                value = title_name if not class_name or class_name == "Overall" else f"{title_name} ({class_name})"
                self._info_row(self.summary_frame, label, value)

        if discipline_changes:
            self._section_label(self.summary_frame, "Discipline Changes")
            for item in discipline_changes[-6:]:
                self._info_row(
                    self.summary_frame,
                    f"{item.get('season_year', '-')}:",
                    f"{item.get('from_style', '-')} -> {item.get('to_style', '-')}",
                )

        if not season_history:
            ctk.CTkLabel(self.history_frame, text="No completed seasons yet.", text_color="gray").pack(pady=18)
            return

        header = ctk.CTkFrame(self.history_frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, 4))
        for text, width in [("Year", 55), ("Championship", 180), ("Style", 80), ("Finish", 85), ("", 85)]:
            ctk.CTkLabel(
                header,
                text=text,
                width=width,
                anchor="w",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color="gray",
            ).pack(side="left", padx=3)

        for item in season_history:
            season_year = int(item.get("season_year") or 0)
            is_rookie_watch_year = season_year in rookie_watch_years
            row = ctk.CTkFrame(
                self.history_frame,
                fg_color=("#e7d9ff", "#3b2854") if is_rookie_watch_year else ("gray80", "gray22"),
                corner_radius=6,
            )
            row.pack(fill="x", pady=2)
            finish_text = f"P{item.get('finishing_place', '-')}"
            class_name = str(item.get("class_name", "")).strip()
            if class_name and class_name != "Overall":
                finish_text = f"{finish_text} ({class_name})"
            for value, width in [
                (str(item.get("season_year", "")), 55),
                (str(item.get("championship_name", "")), 180),
                (str(item.get("style", "")), 80),
                (finish_text, 85),
            ]:
                ctk.CTkLabel(row, text=value, width=width, anchor="w", font=ctk.CTkFont(size=11)).pack(
                    side="left", padx=3, pady=5
                )
            ctk.CTkButton(
                row,
                text="View Races",
                command=lambda history_item=dict(item): self.open_race_history(history_item),
                width=80,
                height=24,
                fg_color="gray30",
                hover_color="gray40",
                font=ctk.CTkFont(size=10),
            ).pack(side="left", padx=3, pady=4)

    def open_race_history(self, history_item: dict) -> None:
        if not self.save_name or not self.driver_id:
            return
        race_history_screen = self.parent.screens["DriverRaceHistoryScreen"]
        if hasattr(race_history_screen, "set_context"):
            race_history_screen.set_context(
                self.save_name,
                self.driver_id,
                str(history_item.get("championship_id", "")).strip(),
                int(history_item.get("season_year", 0) or 0),
                "DriverDetailScreen",
            )
        self.show_screen("DriverRaceHistoryScreen")
