from __future__ import annotations

import customtkinter as ctk

from ..custom_championships import (
    append_custom_championship,
    custom_championship_rows,
    infer_tier_for_car,
    new_custom_championship_id,
    update_custom_championship,
)
from ..settings_manager import list_all_cars, list_all_tracks


STYLE_OPTIONS = ["Sports Car", "Open Wheel", "Oval", "Rallycross", "80R/20O", "20R/80O"]
START_TYPE_OPTIONS = ["Standing", "Rolling"]
GAME_OPTIONS = ["iRacing", "AMS2"]
CLASS_OPTIONS = ["1", "2", "3", "4", "5"]
TRACK_TIER_OPTIONS = ["All Tiers", "Tier 1", "Tier 2", "Tier 3", "Tier 4", "Tier 5"]


class CustomChampionshipScreen(ctk.CTkFrame):
    def __init__(self, parent, show_screen) -> None:
        super().__init__(parent, fg_color="transparent")
        self.parent = parent
        self.show_screen = show_screen
        self.selected_cars: list[dict[str, str]] = []
        self.class_header_vars: dict[str, tuple[ctk.StringVar, ctk.StringVar, ctk.StringVar]] = {}
        self.car_options: list[tuple[str, dict[str, str]]] = []
        self.car_by_label: dict[str, dict[str, str]] = {}
        self._tier_autofill_enabled = True
        self._setting_tier_programmatically = False
        self._editing_championship_id = ""
        self.class_name_entry = None
        self.track_vars: dict[str, ctk.BooleanVar] = {}
        self.track_rows: dict[str, dict[str, str]] = {}
        self.track_catalog: dict[str, dict[str, str]] = {}
        self.track_by_label: dict[str, dict[str, str]] = {}
        self._loaded_track_selection = ""
        self._selected_track_keys: set[str] = set()
        self._selected_track_order: list[str] = []
        self._visible_track_keys: set[str] = set()
        self._track_search_after_id = None

        header = ctk.CTkFrame(self, fg_color=("gray88", "gray14"), corner_radius=18)
        header.pack(fill="x", padx=18, pady=(18, 10))
        ctk.CTkLabel(
            header,
            text="CUSTOM CHAMPIONSHIPS",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#2f8cff",
        ).pack(anchor="w", padx=18, pady=(14, 2))
        ctk.CTkLabel(
            header,
            text="Create Championship",
            font=ctk.CTkFont(size=25, weight="bold"),
        ).pack(anchor="w", padx=18)
        ctk.CTkLabel(
            header,
            text="Custom championships are saved outside the shipped data and will be included in new saves and future season offers.",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        ).pack(anchor="w", padx=18, pady=(2, 14))

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=18, pady=(0, 8))
        scroll.grid_columnconfigure(0, weight=1)
        scroll.grid_columnconfigure(1, weight=1)

        basics = self._section(scroll, "Championship Details")
        basics.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=6)
        self.game_var = ctk.StringVar(value="iRacing")
        self.name_entry = self._entry(basics, "Championship Name")
        self.game_menu = self._option(basics, "Game", self.game_var, GAME_OPTIONS, self._game_changed)
        self.style_var = ctk.StringVar(value=STYLE_OPTIONS[0])
        self._option(basics, "Style", self.style_var, STYLE_OPTIONS, self._discipline_changed)
        self.start_type_var = ctk.StringVar(value=START_TYPE_OPTIONS[0])
        self._option(basics, "Start Type", self.start_type_var, START_TYPE_OPTIONS)

        race_box = self._section(scroll, "Race Format")
        race_box.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=6)
        self.tier_var = ctk.StringVar(value="1")
        ctk.CTkLabel(
            race_box,
            text="The track tier is selected in the Track Selection filter below.",
            font=ctk.CTkFont(size=10),
            text_color="gray",
            anchor="w",
            wraplength=420,
        ).pack(fill="x", padx=14, pady=(0, 12))
        self.race_count_entry = self._entry(race_box, "Num of Races", "4")
        self.race_time_entry = self._entry(race_box, "Race Time", "15")
        self.max_opponents_entry = self._entry(race_box, "Max Grid Size", "20")
        ctk.CTkLabel(
            race_box,
            text="Includes the player and any co-op players. Example: 20 means 20 total cars on the grid.",
            font=ctk.CTkFont(size=10),
            text_color="gray",
            anchor="w",
            wraplength=420,
        ).pack(fill="x", padx=14, pady=(0, 12))
        cars_box = self._section(scroll, "Cars and Classes")
        cars_box.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=6)
        ctk.CTkLabel(
            cars_box,
            text="Class is the race class assigned to each car. Choose the class before clicking Add Car.",
            font=ctk.CTkFont(size=11),
            text_color="#4da6ff",
            anchor="w",
        ).pack(fill="x", padx=14, pady=(0, 10))
        car_controls = ctk.CTkFrame(cars_box, fg_color="transparent")
        car_controls.pack(fill="x", padx=14, pady=(0, 10))
        car_controls.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(car_controls, text="Search", width=70, anchor="w").grid(row=0, column=0, sticky="w")
        self.car_search_var = ctk.StringVar(value="")
        self.car_search_entry = ctk.CTkEntry(car_controls, textvariable=self.car_search_var, height=34)
        self.car_search_entry.grid(row=0, column=1, sticky="ew", padx=(8, 12))
        self.car_search_var.trace_add("write", lambda *_args: self._refresh_car_dropdown())

        self.car_var = ctk.StringVar(value="")
        self.car_dropdown = ctk.CTkComboBox(car_controls, variable=self.car_var, values=[], height=34)
        self.car_dropdown.grid(row=1, column=1, sticky="ew", padx=(8, 12), pady=(8, 0))
        ctk.CTkLabel(car_controls, text="Car", width=70, anchor="w").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.class_var = ctk.StringVar(value="1")
        ctk.CTkOptionMenu(car_controls, variable=self.class_var, values=CLASS_OPTIONS, width=90, height=34).grid(
            row=0, column=4, padx=(8, 0), sticky="w"
        )
        ctk.CTkLabel(car_controls, text="Class name", width=90, anchor="w").grid(row=0, column=2, padx=(8, 0), sticky="w")
        self.class_name_entry = ctk.CTkEntry(car_controls, width=150, height=34)
        self.class_name_entry.grid(row=0, column=3, padx=(8, 0), sticky="ew")
        self.class_name_entry.insert(0, "Class 1")
        ctk.CTkLabel(car_controls, text="Class prestige", width=95, anchor="w").grid(row=0, column=5, padx=(8, 0), sticky="w")
        self.class_prestige_entry = ctk.CTkEntry(car_controls, width=70, height=34)
        self.class_prestige_entry.grid(row=0, column=6, padx=(8, 0), sticky="w")
        self.class_prestige_entry.insert(0, "1")
        ctk.CTkLabel(car_controls, text="Class cars", width=70, anchor="w").grid(row=1, column=2, padx=(8, 0), pady=(8, 0), sticky="w")
        self.class_cars_entry = ctk.CTkEntry(car_controls, width=70, height=34)
        self.class_cars_entry.grid(row=1, column=3, padx=(8, 0), pady=(8, 0), sticky="ew")
        self.class_cars_entry.insert(0, "8")
        ctk.CTkButton(
            car_controls,
            text="Add Car",
            command=self.add_selected_car,
            width=110,
            height=34,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=1, column=6, padx=(8, 0), pady=(8, 0))

        self.selected_cars_frame = ctk.CTkFrame(cars_box, fg_color=("gray84", "gray18"), corner_radius=12)
        self.selected_cars_frame.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkLabel(cars_box, text="Track Selection", font=ctk.CTkFont(size=14, weight="bold"), anchor="w").pack(
            fill="x", padx=14, pady=(8, 2)
        )
        ctk.CTkLabel(
            cars_box,
            text="Search for a track, choose it from the list, then click Add Track. Any track style may be selected.",
            font=ctk.CTkFont(size=10),
            text_color="gray",
            anchor="w",
        ).pack(fill="x", padx=14, pady=(0, 8))
        track_search_controls = ctk.CTkFrame(cars_box, fg_color="transparent")
        track_search_controls.pack(fill="x", padx=14, pady=(0, 8))
        track_search_controls.grid_columnconfigure(0, weight=1)
        self.track_search_var = ctk.StringVar(value="")
        self.track_search_entry = ctk.CTkEntry(
            track_search_controls,
            textvariable=self.track_search_var,
            placeholder_text="Search tracks or layouts...",
            height=32,
        )
        self.track_search_entry.grid(row=0, column=0, sticky="ew")
        self.track_search_var.trace_add("write", lambda *_args: self._track_search_changed())
        self.track_tier_filter_var = ctk.StringVar(value="All Tiers")
        ctk.CTkOptionMenu(
            track_search_controls,
            variable=self.track_tier_filter_var,
            values=TRACK_TIER_OPTIONS,
            command=self._track_tier_filter_changed,
            width=120,
            height=32,
        ).grid(row=0, column=1, padx=(8, 0))
        self.track_var = ctk.StringVar(value="")
        self.track_dropdown = ctk.CTkComboBox(track_search_controls, variable=self.track_var, values=[], height=32)
        self.track_dropdown.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ctk.CTkButton(
            track_search_controls,
            text="Add Track",
            command=self._add_selected_track,
            width=120,
            height=32,
        ).grid(row=1, column=1, padx=(8, 0), pady=(8, 0))
        ctk.CTkButton(
            cars_box,
            text="Add All From Tier",
            command=self._add_all_tracks_from_tier,
            width=160,
            height=30,
            fg_color="gray30",
            hover_color="gray40",
        ).pack(anchor="w", padx=14, pady=(0, 8))
        ctk.CTkLabel(
            cars_box,
            text="Tracks in Championship",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).pack(
            fill="x", padx=14, pady=(4, 2)
        )
        self.selected_tracks_frame = ctk.CTkFrame(cars_box, fg_color=("gray84", "gray18"), corner_radius=12)
        self.selected_tracks_frame.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkButton(
            cars_box,
            text="Clear Cars",
            command=self.clear_selected_cars,
            width=120,
            height=30,
            fg_color="gray30",
            hover_color="gray40",
        ).pack(anchor="w", padx=14, pady=(0, 14))

        self.status_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=11), text_color="gray")
        self.status_label.pack(pady=(0, 8))
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(pady=(0, 12))
        ctk.CTkButton(
            actions,
            text="Save Custom Championship",
            command=self.save_custom_championship,
            width=220,
            height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(side="left")
        ctk.CTkButton(
            actions,
            text="<- Manage Championships",
            command=lambda: self.show_screen("CustomChampionshipManageScreen"),
            width=130,
            height=38,
            fg_color="gray30",
            hover_color="gray40",
        ).pack(side="left", padx=(10, 0))

    def on_show(self) -> None:
        existing_cars = list(self.selected_cars) if self._editing_championship_id else []
        self._refresh_car_options()
        self.selected_cars = existing_cars
        self._refresh_selected_cars()
        self._refresh_track_options(self._loaded_track_selection if self._editing_championship_id else "")
        self._refresh_selected_tracks()
        if not self._editing_championship_id:
            self.status_label.configure(text=f"{len(custom_championship_rows())} custom championship row(s) saved.")

    def start_new(self) -> None:
        self._editing_championship_id = ""
        self._loaded_track_selection = ""
        self._selected_track_keys = set()
        self._selected_track_order = []
        self.track_tier_filter_var.set("All Tiers")
        self.track_search_var.set("")
        self.name_entry.delete(0, "end")
        self.game_var.set("iRacing")
        self.style_var.set(STYLE_OPTIONS[0])
        self.start_type_var.set(START_TYPE_OPTIONS[0])
        self._set_tier_value("1")
        for entry, value in ((self.race_count_entry, "4"), (self.race_time_entry, "15"), (self.max_opponents_entry, "20")):
            entry.delete(0, "end")
            entry.insert(0, value)
        for entry, value in ((self.class_prestige_entry, "1"), (self.class_cars_entry, "8")):
            entry.delete(0, "end")
            entry.insert(0, value)
        self._refresh_car_options()
        self._refresh_selected_cars()
        self._set_class_name_entry("Class 1")
        self._refresh_track_options("")
        self._refresh_selected_tracks()
        self.status_label.configure(text="Create a new custom championship.", text_color="gray")

    def edit_group(self, group: dict[str, object]) -> None:
        rows = [dict(row) for row in group.get("rows", []) if isinstance(row, dict)]
        if not rows:
            return
        first = rows[0]
        self._editing_championship_id = str(group.get("championship_id", "")).strip()
        self._loaded_track_selection = str(first.get("Track_Selection", "")).strip()
        self.track_tier_filter_var.set("All Tiers")
        self.name_entry.delete(0, "end")
        self.name_entry.insert(0, str(first.get("Championship", "")))
        game = str(first.get("Game", "iRacing"))
        self.game_var.set(game if game in GAME_OPTIONS else "iRacing")
        style = str(first.get("Style", STYLE_OPTIONS[0]))
        self.style_var.set(style if style in STYLE_OPTIONS else STYLE_OPTIONS[0])
        start_type = str(first.get("Start_Type", START_TYPE_OPTIONS[0]))
        self.start_type_var.set(start_type if start_type in START_TYPE_OPTIONS else START_TYPE_OPTIONS[0])
        tier = str(first.get("Tier", "1"))
        self._set_tier_value(tier if tier in CLASS_OPTIONS else "1")
        for entry, value in ((self.race_count_entry, first.get("Num of Races", "4")), (self.race_time_entry, first.get("Race_Time", "15")), (self.max_opponents_entry, first.get("Max_Opp", "20"))):
            entry.delete(0, "end")
            entry.insert(0, str(value))
        self._refresh_car_options()
        self._set_class_name_entry(str(first.get("Class_Name", "")).strip() or "Class 1")
        self.class_prestige_entry.delete(0, "end")
        self.class_prestige_entry.insert(0, str(first.get("Prestige", "1")))
        self.class_cars_entry.delete(0, "end")
        self.class_cars_entry.insert(0, str(first.get("Class_Cars", "8")))
        cars_by_id = {str(car.get("id", "")).strip(): car for _label, car in self.car_options}
        self.selected_cars = []
        class_numbers = {
            self._class_number_from_sub_champ(str(row.get("Sub_Champ", "")))
            for row in rows
        }
        default_class_cars = max(1, int(str(first.get("Max_Opp", "20")) or 20) // max(1, len(class_numbers)))
        for row in rows:
            car = dict(cars_by_id.get(str(row.get("Car_ID", "")).strip(), {}))
            if not car:
                car = {"id": row.get("Car_ID", ""), "Car": row.get("Car_ID", ""), "Car class": row.get("Sub_Champ", "")}
            car["_custom_class"] = self._class_number_from_sub_champ(str(row.get("Sub_Champ", "")))
            car["_custom_class_name"] = str(row.get("Class_Name", "")).strip() or f"Class {car['_custom_class']}"
            car["_custom_class_prestige"] = str(row.get("Prestige", "1")).strip() or "1"
            car["_custom_class_cars"] = str(row.get("Class_Cars", "")).strip() or str(default_class_cars)
            self.selected_cars.append(car)
        self._refresh_selected_cars()
        self._refresh_track_options(str(first.get("Track_Selection", "")))
        self.status_label.configure(text=f"Editing {first.get('Championship', 'championship')}.", text_color="gray")

    def _section(self, parent, title: str) -> ctk.CTkFrame:
        box = ctk.CTkFrame(parent, fg_color=("gray90", "gray15"), corner_radius=14)
        ctk.CTkLabel(box, text=title, font=ctk.CTkFont(size=15, weight="bold")).pack(
            anchor="w", padx=14, pady=(14, 10)
        )
        return box

    def _entry(self, parent, label: str, default: str = "") -> ctk.CTkEntry:
        ctk.CTkLabel(parent, text=label, font=ctk.CTkFont(size=11), anchor="w").pack(fill="x", padx=14, pady=(0, 4))
        entry = ctk.CTkEntry(parent, height=34)
        entry.pack(fill="x", padx=14, pady=(0, 12))
        if default:
            entry.insert(0, default)
        return entry

    def _option(self, parent, label: str, variable: ctk.StringVar, values: list[str], command=None) -> ctk.CTkOptionMenu:
        ctk.CTkLabel(parent, text=label, font=ctk.CTkFont(size=11), anchor="w").pack(fill="x", padx=14, pady=(0, 4))
        menu = ctk.CTkOptionMenu(parent, variable=variable, values=values, command=command, height=34)
        menu.pack(fill="x", padx=14, pady=(0, 12))
        return menu

    def _refresh_car_options(self, *_args) -> None:
        game = self.game_var.get()
        normalized_game = game.strip().casefold()
        self.car_options = []
        for car in list_all_cars():
            if str(car.get("Game", "")).strip().casefold() not in {"", normalized_game}:
                continue
            if normalized_game == "iracing" and not str(car.get("Car_Class_ID", "")).strip():
                continue
            car_name = str(car.get("Car", "")).strip()
            class_name = str(car.get("Car class", "")).strip()
            car_id = str(car.get("id", "")).strip()
            label = f"{car_name} | {class_name} | ID {car_id}"
            self.car_options.append((label, dict(car)))
        self.car_options.sort(key=lambda item: item[0].casefold())
        self.selected_cars = []
        self._tier_autofill_enabled = True
        self._set_tier_value("1")
        self._refresh_selected_cars()
        self._refresh_car_dropdown()

    def _game_changed(self, *_args) -> None:
        self._refresh_car_options()
        self._selected_track_keys = set()
        self._selected_track_order = []
        self._refresh_track_options("")

    def _set_class_name_entry(self, value: str) -> None:
        if self.class_name_entry is None:
            return
        self.class_name_entry.delete(0, "end")
        self.class_name_entry.insert(0, value)

    def _refresh_track_options(self, selected_value: str | None = None) -> None:
        if selected_value is not None:
            self._selected_track_order = [value.strip() for value in selected_value.split("||") if value.strip()]
            self._selected_track_keys = set(self._selected_track_order)
        self.track_rows = {}
        game = self.game_var.get().strip().casefold()
        search_terms = [term for term in self.track_search_var.get().strip().casefold().split() if term]
        try:
            tier = int(self.tier_var.get())
        except ValueError:
            tier = 1
        tier_filter = self.track_tier_filter_var.get().strip()
        filtered_tier = None
        if tier_filter != "All Tiers":
            try:
                filtered_tier = int(tier_filter.rsplit(" ", 1)[-1])
            except ValueError:
                filtered_tier = tier
        tracks: list[dict[str, str]] = []
        self.track_catalog = {}
        for track in list_all_tracks():
            if str(track.get("Game", "")).strip().casefold() not in {"", game}:
                continue
            key = f"{track.get('Track', '').strip()}::{track.get('Layout', '').strip()}"
            self.track_catalog[key] = dict(track)
            tiers = {value.strip() for value in str(track.get("My_Tiers", "")).split(".") if value.strip()}
            if filtered_tier is not None and str(filtered_tier) not in tiers:
                continue
            searchable = (
                f"{track.get('Track', '')} {track.get('Layout', '')} "
                f"{track.get('Country', '')}"
            ).casefold()
            if "united states" in searchable and "usa" not in searchable:
                searchable += " usa"
            if "usa" in searchable and "united states" not in searchable:
                searchable += " united states"
            if "united kingdom" in searchable and "england" not in searchable:
                searchable += " england uk"
            if "england" in searchable and "united kingdom" not in searchable:
                searchable += " united kingdom uk"
            if search_terms and not all(term in searchable for term in search_terms):
                continue
            tracks.append(dict(track))
        tracks.sort(key=lambda row: (str(row.get("Track", "")).casefold(), str(row.get("Layout", "")).casefold()))
        self.track_by_label = {}
        for track in tracks:
            key = f"{track.get('Track', '').strip()}::{track.get('Layout', '').strip()}"
            capacity = str(track.get("Garages", "")).strip() or "Unspecified"
            label = (
                f"{track.get('Track', '')} | {track.get('Layout', '')} | "
                f"Tier {track.get('My_Tiers', '-')} | {track.get('Country', '-')} | "
                f"Capacity {capacity}"
            )
            self.track_by_label[label] = {**track, "_key": key}
        values = list(self.track_by_label)
        self.track_dropdown.configure(values=values)
        if values and self.track_var.get() not in values:
            self.track_var.set(values[0])
        elif not values:
            self.track_var.set("")

    def _add_selected_track(self) -> None:
        track = self.track_by_label.get(self.track_var.get())
        if not track:
            self.status_label.configure(text="Pick a track before adding it.", text_color="#ff7777")
            return
        key = str(track.get("_key", "")).strip()
        if key and key not in self._selected_track_keys:
            self._selected_track_keys.add(key)
            self._selected_track_order.append(key)
        self._refresh_selected_tracks()
        self.status_label.configure(text=f"Added {track.get('Track', 'track')} to the championship.", text_color="gray")

    def _add_all_tracks_from_tier(self) -> None:
        tier_filter = self.track_tier_filter_var.get().strip()
        if tier_filter == "All Tiers":
            self.status_label.configure(text="Choose a specific Tier filter before adding all tracks.", text_color="#ff7777")
            return
        try:
            selected_tier = tier_filter.rsplit(" ", 1)[-1]
            int(selected_tier)
        except ValueError:
            self.status_label.configure(text="Choose a valid Tier filter before adding all tracks.", text_color="#ff7777")
            return

        added = 0
        for key, track in self.track_catalog.items():
            tiers = {value.strip() for value in str(track.get("My_Tiers", "")).split(".") if value.strip()}
            if selected_tier not in tiers or key in self._selected_track_keys:
                continue
            self._selected_track_keys.add(key)
            self._selected_track_order.append(key)
            added += 1
        self._refresh_selected_tracks()
        self.status_label.configure(
            text=f"Added {added} track(s) from Tier {selected_tier}." if added else f"All Tier {selected_tier} tracks are already added.",
            text_color="gray",
        )

    def _refresh_selected_tracks(self) -> None:
        for widget in self.selected_tracks_frame.winfo_children():
            widget.destroy()
        selected_keys = [key for key in self._selected_track_order if key in self._selected_track_keys]
        selected_keys.extend(key for key in self._selected_track_keys if key not in selected_keys)
        selected = [self.track_catalog[key] for key in selected_keys if key in self.track_catalog]
        if not selected:
            ctk.CTkLabel(self.selected_tracks_frame, text="No tracks added yet.", text_color="gray").pack(anchor="w", padx=12, pady=10)
            return
        for index, track in enumerate(selected, start=1):
            key = f"{track.get('Track', '').strip()}::{track.get('Layout', '').strip()}"
            capacity = str(track.get("Garages", "")).strip() or "Unspecified"
            row = ctk.CTkFrame(self.selected_tracks_frame, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=3)
            ctk.CTkLabel(
                row,
                text=f"{index}. {track.get('Track', '')} | {track.get('Layout', '')} | Capacity {capacity}",
                anchor="w",
            ).pack(
                side="left", fill="x", expand=True, padx=(4, 8)
            )
            ctk.CTkButton(
                row,
                text="Remove",
                command=lambda track_key=key: self._remove_selected_track(track_key),
                width=78,
                height=26,
                fg_color="#8c2f2f",
                hover_color="#6c2323",
            ).pack(side="right")

    def _remove_selected_track(self, key: str) -> None:
        self._selected_track_keys.discard(key)
        if key in self._selected_track_order:
            self._selected_track_order.remove(key)
        if key in self.track_vars:
            self.track_vars[key].set(False)
        self._refresh_selected_tracks()

    def _track_search_changed(self) -> None:
        if self._track_search_after_id is not None:
            try:
                self.after_cancel(self._track_search_after_id)
            except Exception:
                pass
        self._track_search_after_id = self.after(180, self._run_track_search)

    def _run_track_search(self) -> None:
        self._track_search_after_id = None
        self._refresh_track_options(self._current_track_selection())

    def _track_tier_filter_changed(self, *_args) -> None:
        selected = self.track_tier_filter_var.get().strip()
        if selected != "All Tiers":
            self._set_tier_value(selected.rsplit(" ", 1)[-1])
        self._refresh_track_options(self._current_track_selection())

    def _refresh_car_dropdown(self) -> None:
        search_terms = [term for term in self.car_search_var.get().strip().casefold().split() if term]
        matches = [
            (label, car)
            for label, car in self.car_options
            if all(term in label.casefold() for term in search_terms)
        ][:100]
        values = [label for label, _car in matches]
        self.car_by_label = {label: car for label, car in matches}
        self.car_dropdown.configure(values=values)
        if values and self.car_var.get() not in values:
            self.car_var.set(values[0])
        elif not values:
            self.car_var.set("")

    def add_selected_car(self) -> None:
        label = self.car_var.get()
        car = self.car_by_label.get(label)
        if not car:
            self.status_label.configure(text="Pick a car before adding it.", text_color="#ff7777")
            return
        entry = dict(car)
        entry["_custom_class"] = self.class_var.get()
        entry["_custom_class_name"] = self.class_name_entry.get().strip() or f"Class {entry['_custom_class']}"
        existing_class_car_counts = {
            str(existing.get("_custom_class", "1")): str(existing.get("_custom_class_cars", "")).strip()
            for existing in self.selected_cars
            if str(existing.get("_custom_class", "1")) == entry["_custom_class"]
        }
        try:
            class_prestige = self._parse_int(self.class_prestige_entry.get(), "Class prestige", 1, 100)
            class_cars = self._parse_int(
                existing_class_car_counts.get(entry["_custom_class"], self.class_cars_entry.get()),
                "Class cars",
                1,
                self._parse_int(self.max_opponents_entry.get(), "Max Grid Size", 1, 80),
            )
        except ValueError as error:
            self.status_label.configure(text=str(error), text_color="#ff7777")
            return
        entry["_custom_class_prestige"] = str(class_prestige)
        entry["_custom_class_cars"] = str(class_cars)
        self.selected_cars.append(entry)
        if self._tier_autofill_enabled:
            self._set_tier_value(infer_tier_for_car(entry, self.game_var.get()))
        self._refresh_selected_cars()
        self.status_label.configure(text=f"Added {entry.get('Car', 'car')} to Class {entry['_custom_class']}.", text_color="gray")

    def clear_selected_cars(self) -> None:
        self.selected_cars = []
        self._tier_autofill_enabled = True
        self._set_tier_value("1")
        self._refresh_selected_cars()
        self.status_label.configure(text="Car list cleared.", text_color="gray")

    def _refresh_selected_cars(self) -> None:
        self._sync_class_header_edits()
        for widget in self.selected_cars_frame.winfo_children():
            widget.destroy()
        self.class_header_vars = {}
        if not self.selected_cars:
            ctk.CTkLabel(
                self.selected_cars_frame,
                text="No cars added yet. Add at least one car to create the championship.",
                text_color="gray",
                anchor="w",
            ).pack(fill="x", padx=12, pady=10)
            return
        current_class = None
        for index, car in enumerate(self.selected_cars, start=1):
            class_number = str(car.get("_custom_class", "1"))
            class_name = str(car.get("_custom_class_name", "")).strip() or f"Class {class_number}"
            class_prestige = str(car.get("_custom_class_prestige", "1")).strip() or "1"
            class_cars = str(car.get("_custom_class_cars", "8")).strip() or "8"
            if class_number != current_class:
                header = ctk.CTkFrame(self.selected_cars_frame, fg_color="transparent")
                header.pack(fill="x", padx=12, pady=(8, 2))
                ctk.CTkLabel(
                    header,
                    text=f"Class {class_number}",
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color="#4da6ff",
                ).pack(side="left", padx=(0, 8))
                ctk.CTkLabel(header, text="Name", text_color="gray").pack(side="left", padx=(0, 4))
                name_var = ctk.StringVar(value=class_name)
                ctk.CTkEntry(header, textvariable=name_var, width=150, height=28).pack(side="left", padx=(0, 10))
                ctk.CTkLabel(header, text="Prestige", text_color="gray").pack(side="left", padx=(0, 4))
                prestige_var = ctk.StringVar(value=class_prestige)
                ctk.CTkEntry(header, textvariable=prestige_var, width=65, height=28).pack(side="left")
                ctk.CTkLabel(header, text="Cars", text_color="gray").pack(side="left", padx=(10, 4))
                cars_var = ctk.StringVar(value=class_cars)
                ctk.CTkEntry(header, textvariable=cars_var, width=65, height=28).pack(side="left")
                self.class_header_vars[class_number] = (name_var, prestige_var, cars_var)
                current_class = class_number
            row = ctk.CTkFrame(self.selected_cars_frame, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=3)
            text = f"{index}. {car.get('Car', '')}  |  {car.get('Car class', '')}"
            ctk.CTkLabel(row, text=text, anchor="w").pack(side="left", fill="x", expand=True, padx=(18, 8))
            ctk.CTkButton(
                row,
                text="Remove",
                command=lambda car_index=index - 1: self.remove_selected_car(car_index),
                width=78,
                height=26,
                fg_color="#8c2f2f",
                hover_color="#6c2323",
            ).pack(side="right")

    def remove_selected_car(self, index: int) -> None:
        if index < 0 or index >= len(self.selected_cars):
            return
        removed = self.selected_cars.pop(index)
        self._refresh_selected_cars()
        self.status_label.configure(
            text=f"Removed {removed.get('Car', 'car')} from the championship.",
            text_color="gray",
        )

    def _sync_class_header_edits(self) -> None:
        for class_number, (name_var, prestige_var, cars_var) in self.class_header_vars.items():
            class_name = name_var.get().strip() or f"Class {class_number}"
            class_prestige = prestige_var.get().strip() or "1"
            class_cars = cars_var.get().strip() or "1"
            for car in self.selected_cars:
                if str(car.get("_custom_class", "1")) == class_number:
                    car["_custom_class_name"] = class_name
                    car["_custom_class_prestige"] = class_prestige
                    car["_custom_class_cars"] = class_cars

    def _tier_changed(self, *_args) -> None:
        self._mark_tier_manual()
        self._refresh_track_options(self._current_track_selection())

    def _discipline_changed(self, *_args) -> None:
        self._refresh_track_options(self._current_track_selection())

    def _current_track_selection(self) -> str:
        for key in self._visible_track_keys:
            if self.track_vars.get(key) and self.track_vars[key].get():
                self._selected_track_keys.add(key)
                if key not in self._selected_track_order:
                    self._selected_track_order.append(key)
            else:
                self._selected_track_keys.discard(key)
                if key in self._selected_track_order:
                    self._selected_track_order.remove(key)
        self._selected_track_order = [key for key in self._selected_track_order if key in self._selected_track_keys]
        return "||".join(self._selected_track_order)

    def save_custom_championship(self) -> None:
        self._sync_class_header_edits()
        name = self.name_entry.get().strip()
        if not name:
            self.status_label.configure(text="Championship name is required.", text_color="#ff7777")
            return
        if not self.selected_cars:
            self.status_label.configure(text="Add at least one car.", text_color="#ff7777")
            return
        if not self._current_track_selection():
            self.status_label.configure(text="Select at least one track.", text_color="#ff7777")
            return
        try:
            race_count = self._parse_int(self.race_count_entry.get(), "Num of Races", 1, 50)
            race_time = self._parse_int(self.race_time_entry.get(), "Race Time", 1, 240)
            max_opponents = self._parse_int(self.max_opponents_entry.get(), "Max Grid Size", 1, 80)
            tier = self._parse_int(self.tier_var.get(), "Tier", 1, 5)
        except ValueError as error:
            self.status_label.configure(text=str(error), text_color="#ff7777")
            return

        championship_id = self._editing_championship_id or new_custom_championship_id(name)
        game = self.game_var.get()
        track_selection = self._current_track_selection()
        try:
            class_prestiges = {
                id(car): self._parse_int(car.get("_custom_class_prestige", "1"), "Class prestige", 1, 100)
                for car in self.selected_cars
            }
            class_cars = {
                id(car): self._parse_int(car.get("_custom_class_cars", "1"), "Class cars", 1, max_opponents)
                for car in self.selected_cars
            }
        except ValueError as error:
            self.status_label.configure(text=str(error), text_color="#ff7777")
            return
        class_car_totals = {
            str(car.get("_custom_class", "1")): class_cars[id(car)]
            for car in self.selected_cars
        }
        total_class_cars = sum(class_car_totals.values())
        if total_class_cars > max_opponents:
            self.status_label.configure(
                text=f"Class cars total {total_class_cars}, but Max Grid Size is only {max_opponents}.",
                text_color="#ff7777",
            )
            return
        rows: list[dict[str, str]] = []
        for index, car in enumerate(self.selected_cars, start=1):
            class_number = str(car.get("_custom_class", "1")).strip() or "1"
            car_name = str(car.get("Car", "")).strip()
            car_class = str(car.get("Car class", "")).strip() or car_name
            rows.append(
                {
                    "id": f"{championship_id}_{index}",
                    "Tier": str(tier),
                    "Championship": name,
                    "Sub_Champ": f"Class {class_number}: {car_class}",
                    "Class_Name": str(car.get("_custom_class_name", "")).strip() or f"Class {class_number}",
                    "Class_Cars": str(class_cars[id(car)]),
                    "Championship_ID": championship_id,
                    "Car_Class": "",
                    "Car_ID": str(car.get("id", "")).strip(),
                    "Style": self.style_var.get(),
                    "Num of Races": str(race_count),
                    "Race_Time": str(race_time),
                    "Game": game,
                    "Max_Opp": str(max_opponents),
                    "Min_Opp": "",
                    "Start_Type": self.start_type_var.get(),
                    "Prestige": str(class_prestiges[id(car)]),
                    "Track_Selection": track_selection,
                }
            )

        if self._editing_championship_id:
            update_custom_championship(championship_id, rows)
            self.status_label.configure(text=f"Saved changes to {name}.", text_color="#4da6ff")
        else:
            path = append_custom_championship(rows)
            self.status_label.configure(text=f"Saved {name} to {path.name}.", text_color="#4da6ff")
        self.start_new()

    @staticmethod
    def _class_number_from_sub_champ(sub_champ: str) -> str:
        lowered = sub_champ.strip().casefold()
        if lowered.startswith("class "):
            number = lowered[6:].split(":", 1)[0].strip()
            if number in CLASS_OPTIONS:
                return number
        return "1"

    def _mark_tier_manual(self, *_args) -> None:
        if self._setting_tier_programmatically:
            return
        self._tier_autofill_enabled = False

    def _set_tier_value(self, value: str) -> None:
        self._setting_tier_programmatically = True
        self.tier_var.set(str(value))
        self._setting_tier_programmatically = False

    @staticmethod
    def _parse_int(value: str, label: str, low: int, high: int) -> int:
        try:
            parsed = int(str(value).strip())
        except ValueError as error:
            raise ValueError(f"{label} must be a number from {low} to {high}.") from error
        if parsed < low or parsed > high:
            raise ValueError(f"{label} must be between {low} and {high}.")
        return parsed
