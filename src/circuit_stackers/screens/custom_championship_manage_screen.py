from __future__ import annotations

import customtkinter as ctk

from ..custom_championships import delete_custom_championship, grouped_custom_championships, update_custom_championship
from .custom_championship_screen import CLASS_OPTIONS, GAME_OPTIONS, START_TYPE_OPTIONS, STYLE_OPTIONS


class CustomChampionshipManageScreen(ctk.CTkFrame):
    def __init__(self, parent, show_screen) -> None:
        super().__init__(parent, fg_color="transparent")
        self.parent = parent
        self.show_screen = show_screen
        self.groups: list[dict[str, object]] = []
        self.selected_group_id = ""
        self.pending_delete_group_id = ""
        self.row_editors: list[dict[str, object]] = []
        self.filter_game_var = ctk.StringVar(value="All Games")
        self.filter_style_var = ctk.StringVar(value="All Styles")
        self.filter_frame = None

        header = ctk.CTkFrame(self, fg_color=("gray88", "gray14"), corner_radius=18)
        header.pack(fill="x", padx=18, pady=(18, 10))
        ctk.CTkLabel(
            header,
            text="CUSTOM CHAMPIONSHIPS",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#2f8cff",
        ).pack(anchor="w", padx=18, pady=(14, 2))
        ctk.CTkLabel(header, text="Manage Championships", font=ctk.CTkFont(size=25, weight="bold")).pack(
            anchor="w", padx=18
        )
        ctk.CTkLabel(
            header,
            text="Edit or delete user-created championships. Built-in championships are not changed.",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        ).pack(anchor="w", padx=18, pady=(2, 14))

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=18, pady=(0, 8))
        content.grid_columnconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=0)
        content.grid_rowconfigure(0, weight=1)

        self.list_frame = ctk.CTkScrollableFrame(content, fg_color=("gray90", "gray15"), corner_radius=14)
        self.list_frame.grid(row=0, column=0, columnspan=2, sticky="nsew")
        filters = ctk.CTkFrame(self.list_frame, fg_color="transparent")
        filters.pack(fill="x", padx=12, pady=(12, 4))
        self.filter_frame = filters
        ctk.CTkLabel(filters, text="Game", text_color="gray").pack(side="left", padx=(0, 6))
        ctk.CTkOptionMenu(
            filters,
            variable=self.filter_game_var,
            values=["All Games", *GAME_OPTIONS],
            command=self._filters_changed,
            width=130,
            height=30,
        ).pack(side="left")
        ctk.CTkLabel(filters, text="Style", text_color="gray").pack(side="left", padx=(14, 6))
        ctk.CTkOptionMenu(
            filters,
            variable=self.filter_style_var,
            values=["All Styles", *STYLE_OPTIONS],
            command=self._filters_changed,
            width=145,
            height=30,
        ).pack(side="left")
        self.edit_frame = ctk.CTkScrollableFrame(content, fg_color=("gray90", "gray15"), corner_radius=14)
        self.edit_frame.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        self.edit_frame.grid_remove()

        self.status_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=11), text_color="gray")
        self.status_label.pack(pady=(0, 8))
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(pady=(0, 12))
        ctk.CTkButton(
            actions,
            text="<- Settings",
            command=lambda: self.show_screen("SettingsScreen"),
            width=130,
            height=36,
            fg_color="gray30",
            hover_color="gray40",
        ).pack(side="left")
        ctk.CTkButton(
            actions,
            text="Create New",
            command=self._create_new,
            width=130,
            height=36,
        ).pack(side="left", padx=(10, 0))

    def on_show(self) -> None:
        self._load_groups()

    def _load_groups(self) -> None:
        self.groups = grouped_custom_championships()
        if self.selected_group_id and not any(str(group.get("championship_id")) == self.selected_group_id for group in self.groups):
            self.selected_group_id = ""
        if not self.selected_group_id and self.groups:
            self.selected_group_id = str(self.groups[0].get("championship_id", ""))
        self._render_list()
        self._render_editor()

    def _render_list(self) -> None:
        for widget in self.list_frame.winfo_children():
            if widget is not self.filter_frame:
                widget.destroy()
        filtered_groups = self._filtered_groups()
        ctk.CTkLabel(
            self.list_frame,
            text=f"Custom Championships ({len(filtered_groups)} of {len(self.groups)})",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(12, 8))
        if not filtered_groups:
            ctk.CTkLabel(
                self.list_frame,
                text="No custom championships match the selected filters." if self.groups else "No custom championships yet.",
                text_color="gray",
            ).pack(anchor="w", padx=12, pady=8)
            return
        for group in filtered_groups:
            group_id = str(group.get("championship_id", ""))
            selected = group_id == self.selected_group_id
            row = ctk.CTkFrame(
                self.list_frame,
                fg_color=("#d8ecff", "#173a59") if selected else ("gray84", "gray20"),
                corner_radius=12,
            )
            row.pack(fill="x", padx=10, pady=4)
            label_stack = ctk.CTkFrame(row, fg_color="transparent")
            label_stack.pack(side="left", fill="x", expand=True, padx=10, pady=8)
            ctk.CTkLabel(
                label_stack,
                text=str(group.get("name", "")),
                font=ctk.CTkFont(size=12, weight="bold"),
                anchor="w",
            ).pack(anchor="w")
            ctk.CTkLabel(
                label_stack,
                text=f"{group.get('game', '-')} | {group.get('style', '-')} | Tier {group.get('tier', '-')} | Prestige {group.get('prestige', '-')}",
                font=ctk.CTkFont(size=10),
                text_color="gray",
                anchor="w",
            ).pack(anchor="w")
            ctk.CTkButton(
                row,
                text="Open Builder",
                command=lambda value=group_id: self._open_group(value),
                width=110,
                height=28,
            ).pack(side="right", padx=(4, 8))
            ctk.CTkButton(
                row,
                text="Delete",
                command=lambda value=group_id: self._delete_from_list(value),
                width=72,
                height=28,
                fg_color="#8c2f2f",
                hover_color="#6c2323",
            ).pack(side="right", padx=(4, 0))

    def _render_editor(self) -> None:
        for widget in self.edit_frame.winfo_children():
            widget.destroy()
        self.row_editors = []
        group = self._selected_group()
        if not group:
            ctk.CTkLabel(
                self.edit_frame,
                text="Select a custom championship to edit.",
                text_color="gray",
            ).pack(pady=24)
            return

        rows = [dict(row) for row in group.get("rows", []) if isinstance(row, dict)]
        first = rows[0]
        ctk.CTkLabel(
            self.edit_frame,
            text="Edit Championship",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(anchor="w", padx=14, pady=(14, 10))

        self.name_entry = self._entry("Championship Name", first.get("Championship", ""))
        self.game_var = ctk.StringVar(value=first.get("Game", "iRacing") if first.get("Game", "") in GAME_OPTIONS else "iRacing")
        self._option("Game", self.game_var, GAME_OPTIONS)
        self.style_var = ctk.StringVar(value=first.get("Style", "Sports Car") if first.get("Style", "") in STYLE_OPTIONS else "Sports Car")
        self._option("Style", self.style_var, STYLE_OPTIONS)
        self.start_type_var = ctk.StringVar(
            value=first.get("Start_Type", "Standing") if first.get("Start_Type", "") in START_TYPE_OPTIONS else "Standing"
        )
        self._option("Start Type", self.start_type_var, START_TYPE_OPTIONS)
        self.tier_var = ctk.StringVar(value=first.get("Tier", "1") if first.get("Tier", "") in CLASS_OPTIONS else "1")
        self._option("Tier (track selection)", self.tier_var, CLASS_OPTIONS)
        self.race_count_entry = self._entry("Num of Races", first.get("Num of Races", "4"))
        self.race_time_entry = self._entry("Race Time", first.get("Race_Time", "15"))
        self.max_opponents_entry = self._entry("Max Grid Size", first.get("Max_Opp", "20"))
        ctk.CTkLabel(
            self.edit_frame,
            text="Includes the player and any co-op players. Example: 20 means 20 total cars on the grid.",
            font=ctk.CTkFont(size=10),
            text_color="gray",
            anchor="w",
            wraplength=420,
        ).pack(fill="x", padx=14, pady=(0, 10))
        self.prestige_entry = self._entry("Prestige", first.get("Prestige", "1"))

        ctk.CTkLabel(
            self.edit_frame,
            text="Cars and Classes",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=14, pady=(10, 6))
        for index, row in enumerate(rows, start=1):
            self._row_editor(row, index)

        actions = ctk.CTkFrame(self.edit_frame, fg_color="transparent")
        actions.pack(fill="x", padx=14, pady=(14, 18))
        ctk.CTkButton(
            actions,
            text="Save Changes",
            command=self.save_changes,
            width=140,
            height=34,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left")
        ctk.CTkButton(
            actions,
            text="Delete Championship",
            command=self.delete_selected,
            width=170,
            height=34,
            fg_color="#8c2f2f",
            hover_color="#6c2323",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left", padx=(10, 0))

    def _entry(self, label: str, value: str) -> ctk.CTkEntry:
        ctk.CTkLabel(self.edit_frame, text=label, font=ctk.CTkFont(size=11), anchor="w").pack(
            fill="x", padx=14, pady=(0, 4)
        )
        entry = ctk.CTkEntry(self.edit_frame, height=32)
        entry.pack(fill="x", padx=14, pady=(0, 10))
        entry.insert(0, str(value))
        return entry

    def _option(self, label: str, variable: ctk.StringVar, values: list[str]) -> None:
        ctk.CTkLabel(self.edit_frame, text=label, font=ctk.CTkFont(size=11), anchor="w").pack(
            fill="x", padx=14, pady=(0, 4)
        )
        ctk.CTkOptionMenu(self.edit_frame, variable=variable, values=values, height=32).pack(
            fill="x", padx=14, pady=(0, 10)
        )

    def _row_editor(self, row: dict[str, str], index: int) -> None:
        frame = ctk.CTkFrame(self.edit_frame, fg_color=("gray84", "gray20"), corner_radius=10)
        frame.pack(fill="x", padx=14, pady=4)
        ctk.CTkLabel(
            frame,
            text=f"{index}. {row.get('Sub_Champ', '') or row.get('Car_ID', '')}",
            font=ctk.CTkFont(size=11, weight="bold"),
            anchor="w",
        ).pack(anchor="w", padx=10, pady=(8, 2))
        class_var = ctk.StringVar(value=self._class_number_from_row(row))
        ctk.CTkOptionMenu(frame, variable=class_var, values=["1", "2", "3", "4", "5"], width=90, height=28).pack(
            anchor="w", padx=10, pady=(0, 8)
        )
        self.row_editors.append({"row": dict(row), "class_var": class_var})

    def _filtered_groups(self) -> list[dict[str, object]]:
        selected_game = self.filter_game_var.get().casefold()
        selected_style = self.filter_style_var.get().casefold()
        return [
            group
            for group in self.groups
            if (selected_game == "all games" or str(group.get("game", "")).casefold() == selected_game)
            and (selected_style == "all styles" or str(group.get("style", "")).casefold() == selected_style)
        ]

    def _filters_changed(self, _value: str = "") -> None:
        if self.selected_group_id and not any(
            str(group.get("championship_id", "")) == self.selected_group_id for group in self._filtered_groups()
        ):
            self.selected_group_id = ""
        self._render_list()
        self._render_editor()

    def _select_group(self, group_id: str) -> None:
        self.selected_group_id = group_id
        self.pending_delete_group_id = ""
        self._render_list()
        self._render_editor()
        self.status_label.configure(text="")

    def _open_group(self, group_id: str) -> None:
        group = next((item for item in self.groups if str(item.get("championship_id", "")) == group_id), None)
        if not group:
            return
        builder = self.parent.screens["CustomChampionshipScreen"]
        builder.edit_group(group)
        self.show_screen("CustomChampionshipScreen")

    def _create_new(self) -> None:
        builder = self.parent.screens["CustomChampionshipScreen"]
        builder.start_new()
        self.show_screen("CustomChampionshipScreen")

    def _delete_from_list(self, group_id: str) -> None:
        self.selected_group_id = group_id
        self._render_list()
        self._render_editor()
        self.delete_selected()

    def _selected_group(self) -> dict[str, object] | None:
        return next((group for group in self.groups if str(group.get("championship_id", "")) == self.selected_group_id), None)

    def save_changes(self) -> None:
        group = self._selected_group()
        if not group:
            return
        name = self.name_entry.get().strip()
        if not name:
            self.status_label.configure(text="Championship name is required.", text_color="#ff7777")
            return
        try:
            race_count = self._parse_int(self.race_count_entry.get(), "Num of Races", 1, 50)
            race_time = self._parse_int(self.race_time_entry.get(), "Race Time", 1, 240)
            max_opponents = self._parse_int(self.max_opponents_entry.get(), "Max Grid Size", 1, 80)
            prestige = self._parse_int(self.prestige_entry.get(), "Prestige", 1, 100)
            tier = self._parse_int(self.tier_var.get(), "Tier", 1, 5)
        except ValueError as error:
            self.status_label.configure(text=str(error), text_color="#ff7777")
            return

        championship_id = str(group.get("championship_id", "")).strip()
        rows: list[dict[str, str]] = []
        for editor in self.row_editors:
            row = dict(editor["row"])
            class_number = str(editor["class_var"].get()).strip() or "1"
            row.update(
                {
                    "Tier": str(tier),
                    "Championship": name,
                    "Sub_Champ": self._class_label(row, class_number),
                    "Championship_ID": championship_id,
                    "Style": self.style_var.get(),
                    "Num of Races": str(race_count),
                    "Race_Time": str(race_time),
                    "Game": self.game_var.get(),
                    "Max_Opp": str(max_opponents),
                    "Start_Type": self.start_type_var.get(),
                    "Prestige": str(prestige),
                }
            )
            rows.append(row)
        update_custom_championship(championship_id, rows)
        self.status_label.configure(text=f"Saved changes to {name}.", text_color="#4da6ff")
        self._load_groups()

    def delete_selected(self) -> None:
        group = self._selected_group()
        if not group:
            return
        group_id = str(group.get("championship_id", ""))
        name = str(group.get("name", "custom championship"))
        if self.pending_delete_group_id != group_id:
            self.pending_delete_group_id = group_id
            self.status_label.configure(
                text=f"Click Delete Championship again to permanently delete {name}.",
                text_color="#ffbb55",
            )
            return
        delete_custom_championship(group_id)
        self.selected_group_id = ""
        self.pending_delete_group_id = ""
        self.status_label.configure(text=f"Deleted {name}.", text_color="#4da6ff")
        self._load_groups()

    @staticmethod
    def _class_label(row: dict[str, str], class_number: str) -> str:
        existing = str(row.get("Sub_Champ", "")).strip()
        if ":" in existing:
            return f"Class {class_number}:{existing.split(':', 1)[1]}"
        return f"Class {class_number}: {existing or row.get('Car_ID', '')}"

    @staticmethod
    def _class_number_from_row(row: dict[str, str]) -> str:
        sub_champ = str(row.get("Sub_Champ", "")).strip()
        lowered = sub_champ.casefold()
        if lowered.startswith("class "):
            number = sub_champ[6:].split(":", 1)[0].strip()
            if number in CLASS_OPTIONS:
                return number
        return "1"

    @staticmethod
    def _parse_int(value: str, label: str, low: int, high: int) -> int:
        try:
            parsed = int(str(value).strip())
        except ValueError as error:
            raise ValueError(f"{label} must be a number from {low} to {high}.") from error
        if parsed < low or parsed > high:
            raise ValueError(f"{label} must be between {low} and {high}.")
        return parsed
