from __future__ import annotations

import customtkinter as ctk

from ..driver_pool import get_driver_race_history


class DriverRaceHistoryScreen(ctk.CTkFrame):
    def __init__(self, parent, show_screen) -> None:
        super().__init__(parent, fg_color="transparent")
        self.parent = parent
        self.show_screen = show_screen
        self.save_name: str | None = None
        self.driver_id: str | None = None
        self.championship_id = ""
        self.season_year = 0
        self.back_screen = "DriverDetailScreen"

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(18, 8))
        self.title_label = ctk.CTkLabel(top, text="Race History", font=ctk.CTkFont(size=22, weight="bold"))
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

        box = ctk.CTkFrame(self, fg_color=("gray88", "gray17"), corner_radius=10)
        box.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        self.results_frame = ctk.CTkScrollableFrame(box, fg_color="transparent")
        self.results_frame.pack(fill="both", expand=True, padx=8, pady=8)

    def set_context(
        self,
        save_name: str,
        driver_id: str,
        championship_id: str,
        season_year: int,
        back_screen: str = "DriverDetailScreen",
    ) -> None:
        self.save_name = save_name
        self.driver_id = driver_id
        self.championship_id = championship_id
        self.season_year = int(season_year)
        self.back_screen = back_screen or "DriverDetailScreen"

    def on_show(self) -> None:
        for widget in self.results_frame.winfo_children():
            widget.destroy()

        if not self.save_name or not self.driver_id or not self.championship_id:
            self.subtitle_label.configure(text="No race history selected.")
            return

        rows = get_driver_race_history(self.save_name, self.driver_id, self.championship_id, self.season_year)
        if not rows:
            self.title_label.configure(text="Race History")
            self.subtitle_label.configure(text=f"{self.season_year} | No archived race results found.")
            ctk.CTkLabel(
                self.results_frame,
                text="Race-level results are only available for seasons completed after this archive feature was added.",
                text_color="gray",
            ).pack(pady=18)
            return

        championship_name = str(rows[0].get("championship_name", "Championship"))
        self.title_label.configure(text=championship_name)
        self.subtitle_label.configure(text=f"Season {self.season_year} | {str(rows[0].get('style', '-'))}")

        header = ctk.CTkFrame(self.results_frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, 4))
        for text, width in [
            ("Race", 50),
            ("Track", 150),
            ("Layout", 150),
            ("Class", 115),
            ("Overall", 65),
            ("Class Pos", 70),
            ("Points", 55),
            ("MMR", 55),
        ]:
            ctk.CTkLabel(
                header,
                text=text,
                width=width,
                anchor="w",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color="gray",
            ).pack(side="left", padx=3)

        for row_data in rows:
            row = ctk.CTkFrame(self.results_frame, fg_color=("gray80", "gray22"), corner_radius=6)
            row.pack(fill="x", pady=2)
            class_pos = f"P{row_data.get('class_pos', '-')}"
            class_size = int(row_data.get("class_size", 0) or 0)
            if class_size:
                class_pos = f"{class_pos}/{class_size}"
            values = [
                (str(row_data.get("race_num", "")), 50),
                (str(row_data.get("track", "")), 150),
                (str(row_data.get("layout", "")), 150),
                (str(row_data.get("class_name", "Overall")), 115),
                (f"P{row_data.get('overall_pos', '-')}", 65),
                (class_pos, 70),
                (str(row_data.get("points_awarded", 0)), 55),
                (self._format_mmr_change(row_data.get("mmr_change")), 55),
            ]
            for value, width in values:
                ctk.CTkLabel(row, text=value, width=width, anchor="w", font=ctk.CTkFont(size=11)).pack(
                    side="left", padx=3, pady=6
                )

    @staticmethod
    def _format_mmr_change(value) -> str:
        if value is None:
            return "-"
        try:
            change = int(value)
        except (TypeError, ValueError):
            return "-"
        return f"+{change}" if change > 0 else str(change)
