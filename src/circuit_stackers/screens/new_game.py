from __future__ import annotations

import customtkinter as ctk

from ..game_logic import create_new_save
from ..settings_manager import game_directory


class NewGame(ctk.CTkFrame):
    def __init__(self, parent, show_screen) -> None:
        super().__init__(parent, fg_color="transparent")
        self.show_screen = show_screen
        self.parent = parent
        self.player_entries: list[ctk.CTkEntry] = []
        self.player_rows: list[ctk.CTkFrame] = []
        self.game_var = ctk.StringVar(value="iRacing")
        self.career_mode_var = ctk.StringVar(value="Solo")

        form_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        form_scroll.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        ctk.CTkLabel(form_scroll, text="New Career", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(36, 4))
        ctk.CTkLabel(
            form_scroll,
            text="Create a save file, then add one or more human drivers.",
            font=ctk.CTkFont(size=13),
            text_color="gray",
        ).pack(pady=(0, 18))

        entry_frame = ctk.CTkFrame(form_scroll, fg_color="transparent")
        entry_frame.pack()
        self.input_width = 280

        ctk.CTkLabel(entry_frame, text="Save Name", font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(0, 4))

        self.save_name_entry = ctk.CTkEntry(
            entry_frame,
            placeholder_text="e.g. Rookie Road Run",
            height=38,
            width=self.input_width,
            font=ctk.CTkFont(size=13),
        )
        self.save_name_entry.pack()

        ctk.CTkLabel(entry_frame, text="Game", font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(18, 4))
        self.game_selector = ctk.CTkSegmentedButton(
            entry_frame,
            values=["iRacing", "AMS2"],
            variable=self.game_var,
            command=self._on_game_changed,
            width=self.input_width,
            height=36,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.game_selector.pack()

        ctk.CTkLabel(entry_frame, text="Career Mode", font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(18, 4))
        self.career_mode_selector = ctk.CTkOptionMenu(
            entry_frame,
            values=["Solo", "Co-op", "Rivals (coming later)"],
            variable=self.career_mode_var,
            width=self.input_width,
            height=36,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.career_mode_selector.pack()
        ctk.CTkLabel(
            entry_frame,
            text="Co-op shares one career path. Rivals mode will split drivers into separate careers later.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            wraplength=self.input_width,
            justify="left",
        ).pack(pady=(6, 0))

        ctk.CTkLabel(entry_frame, text="Drivers", font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(18, 4))
        self.players_frame = ctk.CTkFrame(entry_frame, fg_color="transparent")
        self.players_frame.pack(anchor="w")
        self.add_player_entry()

        ctk.CTkButton(
            entry_frame,
            text="Add Driver",
            command=self.add_player_entry,
            height=30,
            width=120,
            font=ctk.CTkFont(size=11),
            fg_color="gray30",
            hover_color="gray40",
        ).pack(pady=(8, 0))

        ctk.CTkLabel(entry_frame, text="Starting Difficulty", font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(18, 4))
        difficulty_row = ctk.CTkFrame(entry_frame, fg_color="transparent")
        difficulty_row.pack()
        self.difficulty_entry = ctk.CTkEntry(
            difficulty_row,
            placeholder_text="0-125",
            width=120,
            height=34,
            font=ctk.CTkFont(size=13),
        )
        self.difficulty_entry.insert(0, "75")
        self.difficulty_entry.pack()
        self.difficulty_hint = ctk.CTkLabel(
            entry_frame,
            text="Set your top end AI difficulty.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        )
        self.difficulty_hint.pack(pady=(6, 0))

        ctk.CTkLabel(entry_frame, text="Starting World History", font=ctk.CTkFont(size=12)).pack(anchor="w", pady=(18, 4))
        history_row = ctk.CTkFrame(entry_frame, fg_color="transparent")
        history_row.pack()
        self.history_years_value = ctk.StringVar(value="5")
        self.history_years_slider = ctk.CTkSlider(
            history_row,
            from_=5,
            to=20,
            number_of_steps=15,
            width=220,
            command=self._update_history_years_label,
        )
        self.history_years_slider.set(5)
        self.history_years_slider.pack(side="left")
        self.history_years_label = ctk.CTkLabel(
            history_row,
            textvariable=self.history_years_value,
            width=40,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.history_years_label.pack(side="left", padx=(10, 0))
        ctk.CTkLabel(
            entry_frame,
            text="How many years of world history to simulate before your career begins.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        ).pack(pady=(6, 0))

        self.error_label = ctk.CTkLabel(
            entry_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="#ff5555",
        )
        self.error_label.pack(pady=(4, 0))

        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.pack(side="bottom", pady=(0, 10))

        ctk.CTkButton(
            button_frame,
            text="Next ->",
            command=self.start_game,
            height=38,
            width=160,
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(side="left", padx=(0, 10))

        self.settings_btn = ctk.CTkButton(
            button_frame,
            text="Open Settings",
            command=lambda: show_screen("SettingsScreen"),
            height=36,
            width=160,
            fg_color="gray30",
            hover_color="gray40",
            font=ctk.CTkFont(size=12),
        )

        self.back_btn = ctk.CTkButton(
            button_frame,
            text="<- Back to Menu",
            command=lambda: show_screen("MenuScreen"),
            height=36,
            width=160,
            fg_color="gray30",
            hover_color="gray40",
            font=ctk.CTkFont(size=12),
        )
        self.back_btn.pack(side="left")
        self._on_game_changed(self.game_var.get())

    def start_game(self) -> None:
        selected_game = self.game_var.get() or "iRacing"
        if not game_directory(selected_game):
            self.error_label.configure(text=f"Set your {selected_game} folder in Settings before creating a new career.")
            if not self.settings_btn.winfo_ismapped():
                self.settings_btn.pack(side="left", padx=(0, 10), before=self.back_btn)
            return

        save_name = self.save_name_entry.get().strip()
        if not save_name:
            self.error_label.configure(text="Please enter a save name.")
            return

        player_names = [entry.get().strip() for entry in self.player_entries if entry.get().strip()]
        if not player_names:
            self.error_label.configure(text="Add at least one driver name.")
            return
        career_mode = self.career_mode_var.get().strip()
        if career_mode.startswith("Rivals"):
            self.error_label.configure(text="Rivals mode is planned for a later 1.5 phase. Use Solo or Co-op for now.")
            return
        if career_mode == "Solo" and len(player_names) > 1:
            self.error_label.configure(text="Solo careers can only have one driver. Choose Co-op for multiple drivers.")
            return

        try:
            starting_difficulty = int(self.difficulty_entry.get().strip())
        except ValueError:
            min_difficulty, max_difficulty = self._difficulty_range_for_game(selected_game)
            self.error_label.configure(
                text=f"Starting difficulty must be a number from {min_difficulty} to {max_difficulty}."
            )
            return
        min_difficulty, max_difficulty = self._difficulty_range_for_game(selected_game)
        if starting_difficulty < min_difficulty or starting_difficulty > max_difficulty:
            self.error_label.configure(
                text=f"Starting difficulty must be between {min_difficulty} and {max_difficulty}."
            )
            return

        world_history_years = int(round(float(self.history_years_slider.get())))
        if world_history_years < 5 or world_history_years > 20:
            self.error_label.configure(text="Starting world history must be between 5 and 20 years.")
            return

        success, message = create_new_save(
            save_name,
            player_names,
            starting_difficulty=starting_difficulty,
            world_history_years=world_history_years,
            game=selected_game,
            career_mode=career_mode,
        )
        if not success:
            self.error_label.configure(text=message)
            return

        self.error_label.configure(text="")
        world_setup_screen = self.parent.screens["WorldSetupScreen"]
        if hasattr(world_setup_screen, "set_request"):
            world_setup_screen.set_request(
                save_name,
                None,
                player_names,
                None,
                starting_difficulty,
            )
        self.show_screen("WorldSetupScreen")

    @staticmethod
    def _difficulty_range_for_game(game: str) -> tuple[int, int]:
        if str(game).strip().casefold() == "ams2":
            return 70, 120
        return 0, 125

    def _on_game_changed(self, selected_game: str) -> None:
        min_difficulty, max_difficulty = self._difficulty_range_for_game(selected_game)
        default_value = "95" if str(selected_game).strip().casefold() == "ams2" else "75"
        self.difficulty_entry.delete(0, "end")
        self.difficulty_entry.insert(0, default_value)
        self.difficulty_entry.configure(placeholder_text=f"{min_difficulty}-{max_difficulty}")
        self.difficulty_hint.configure(text=f"Set your top end AI difficulty. ({min_difficulty}-{max_difficulty})")

    def _update_history_years_label(self, value: float) -> None:
        self.history_years_value.set(str(int(round(value))))

    def add_player_entry(self) -> None:
        row = ctk.CTkFrame(self.players_frame, fg_color="transparent")
        row.pack(fill="x", pady=4)
        entry = ctk.CTkEntry(
            row,
            placeholder_text=f"Driver {len(self.player_entries) + 1}",
            height=34,
            width=self.input_width,
            font=ctk.CTkFont(size=13),
        )
        entry.pack(side="left")
        remove_btn = ctk.CTkButton(
            row,
            text="Remove",
            command=lambda current_row=row, current_entry=entry: self.remove_player_entry(current_row, current_entry),
            height=30,
            width=90,
            font=ctk.CTkFont(size=11),
            fg_color="gray30",
            hover_color="gray40",
        )
        remove_btn.pack(side="left", padx=(8, 0))
        self.player_entries.append(entry)
        self.player_rows.append(row)
        if len(self.player_entries) > 1 and self.career_mode_var.get() == "Solo":
            self.career_mode_var.set("Co-op")
        self._refresh_remove_buttons()

    def remove_player_entry(self, row: ctk.CTkFrame, entry: ctk.CTkEntry) -> None:
        if len(self.player_entries) <= 1:
            self.error_label.configure(text="You need at least one driver.")
            return

        if entry in self.player_entries:
            self.player_entries.remove(entry)
        if row in self.player_rows:
            self.player_rows.remove(row)
        row.destroy()
        if len(self.player_entries) == 1 and self.career_mode_var.get() == "Co-op":
            self.career_mode_var.set("Solo")
        self._refresh_remove_buttons()

    def _refresh_remove_buttons(self) -> None:
        allow_remove = len(self.player_rows) > 1
        for row in self.player_rows:
            for widget in row.winfo_children():
                if isinstance(widget, ctk.CTkButton) and widget.cget("text") == "Remove":
                    widget.configure(state="normal" if allow_remove else "disabled")
