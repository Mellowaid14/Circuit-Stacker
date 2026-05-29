from __future__ import annotations

import customtkinter as ctk

from ..game_logic import migrate_loaded_rivalry_state
from ..save_manager import delete_save, list_saves, load_save


class LoadScreen(ctk.CTkFrame):
    def __init__(self, parent, show_screen) -> None:
        super().__init__(parent, fg_color="transparent")
        self.show_screen = show_screen
        self.parent = parent
        self.selected_save: str | None = None

        ctk.CTkLabel(self, text="Load Career", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(50, 4))
        ctk.CTkLabel(
            self,
            text="Select a save file to continue.",
            font=ctk.CTkFont(size=13),
            text_color="gray",
        ).pack(pady=(0, 20))

        self.list_frame = ctk.CTkScrollableFrame(self, width=400, height=300, fg_color=("gray90", "gray15"))
        self.list_frame.pack(padx=40, pady=(0, 10))

        self.status_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="#ff5555",
        )
        self.status_label.pack(pady=(0, 10))

        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.pack()

        self.load_btn = ctk.CTkButton(
            button_frame,
            text="Load Save",
            command=self.load_selected,
            height=38,
            width=160,
            font=ctk.CTkFont(size=13, weight="bold"),
            state="disabled",
        )
        self.load_btn.pack(pady=(0, 8))

        self.delete_btn = ctk.CTkButton(
            button_frame,
            text="Delete Save",
            command=self.delete_selected,
            height=36,
            width=160,
            fg_color="#8b0000",
            hover_color="#a00000",
            font=ctk.CTkFont(size=12),
            state="disabled",
        )
        self.delete_btn.pack(pady=(0, 8))

        ctk.CTkButton(
            button_frame,
            text="<- Back to Menu",
            command=lambda: show_screen("MenuScreen"),
            height=36,
            width=160,
            fg_color="gray30",
            hover_color="gray40",
            font=ctk.CTkFont(size=12),
        ).pack()

    def on_show(self) -> None:
        self.refresh_saves()

    def refresh_saves(self) -> None:
        for widget in self.list_frame.winfo_children():
            widget.destroy()

        saves = list_saves()
        self.selected_save = None
        self.load_btn.configure(state="disabled")
        self.delete_btn.configure(state="disabled")
        self.status_label.configure(text="")

        if not saves:
            ctk.CTkLabel(
                self.list_frame,
                text="No saves found.",
                font=ctk.CTkFont(size=12),
                text_color="gray",
            ).pack(pady=20)
            return

        for save_name in saves:
            self.add_save_row(save_name)

    def add_save_row(self, save_name: str) -> None:
        save_data = load_save(save_name) or {}
        game = str(save_data.get("game", "iRacing"))
        row = ctk.CTkFrame(self.list_frame, fg_color=("gray80", "gray20"), corner_radius=8)
        row.pack(fill="x", padx=8, pady=4)

        ctk.CTkLabel(row, text=f"Save: {save_name} | {game}", font=ctk.CTkFont(size=13), anchor="w").pack(
            side="left", padx=12, pady=10
        )

        ctk.CTkButton(
            row,
            text="Select",
            command=lambda value=save_name: self.select_save(value),
            height=28,
            width=80,
            font=ctk.CTkFont(size=11),
        ).pack(side="right", padx=8, pady=8)

    def select_save(self, save_name: str) -> None:
        self.selected_save = save_name
        self.load_btn.configure(state="normal")
        self.delete_btn.configure(state="normal")
        self.status_label.configure(text=f"Selected: {save_name}", text_color="gray")

    def load_selected(self) -> None:
        if not self.selected_save:
            return

        data = load_save(self.selected_save)
        if data is None:
            self.status_label.configure(text="Failed to load save.", text_color="#ff5555")
            return
        data = migrate_loaded_rivalry_state(data)

        championship = data.get("championship")
        if championship:
            gameplay = self.parent.screens["GameplayScreen"]
            gameplay.load_state(data)
            self.show_screen("GameplayScreen")
            return

        championship_screen = self.parent.screens["ChampionshipScreen"]
        championship_screen.save_name = self.selected_save
        championship_screen.player_names = data.get("players", [self.selected_save])
        championship_screen.current_tier = self._normalize_unlocked_tier(
            data.get("unlocked_tier", data.get("unlocked_tiers")),
            data.get("tier", data.get("Tier", 1)),
        )
        championship_screen.starting_difficulty = int(data.get("starting_difficulty", 75))
        self.show_screen("ChampionshipScreen")

    def delete_selected(self) -> None:
        if not self.selected_save:
            return

        delete_save(self.selected_save)
        self.status_label.configure(text=f"Deleted '{self.selected_save}'.", text_color="gray")
        self.refresh_saves()

    @staticmethod
    def _normalize_unlocked_tier(value, fallback: int = 1) -> int:
        if isinstance(value, dict):
            parsed_values = []
            for raw_value in value.values():
                try:
                    parsed_values.append(int(raw_value))
                except (TypeError, ValueError):
                    continue
            value = max(parsed_values) if parsed_values else fallback
        try:
            tier = int(value)
        except (TypeError, ValueError):
            tier = int(fallback)
        return max(1, min(5, tier))
