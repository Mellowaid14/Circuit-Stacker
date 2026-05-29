from __future__ import annotations

import customtkinter as ctk

from ..custom_championships import (
    append_custom_championship,
    custom_championship_rows,
    infer_tier_for_car,
    new_custom_championship_id,
)
from ..settings_manager import list_all_cars


STYLE_OPTIONS = ["Sports Car", "Open Wheel", "Oval", "Rallycross", "80R/20O", "20R/80O"]
START_TYPE_OPTIONS = ["Standing", "Rolling"]
GAME_OPTIONS = ["iRacing", "AMS2"]
CLASS_OPTIONS = ["1", "2", "3", "4", "5"]


class CustomChampionshipScreen(ctk.CTkFrame):
    def __init__(self, parent, show_screen) -> None:
        super().__init__(parent, fg_color="transparent")
        self.parent = parent
        self.show_screen = show_screen
        self.selected_cars: list[dict[str, str]] = []
        self.car_options: list[tuple[str, dict[str, str]]] = []
        self.car_by_label: dict[str, dict[str, str]] = {}
        self._tier_autofill_enabled = True
        self._setting_tier_programmatically = False

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
        self.game_menu = self._option(basics, "Game", self.game_var, GAME_OPTIONS, self._refresh_car_options)
        self.style_var = ctk.StringVar(value=STYLE_OPTIONS[0])
        self._option(basics, "Style", self.style_var, STYLE_OPTIONS)
        self.start_type_var = ctk.StringVar(value=START_TYPE_OPTIONS[0])
        self._option(basics, "Start Type", self.start_type_var, START_TYPE_OPTIONS)

        race_box = self._section(scroll, "Race Format")
        race_box.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=6)
        self.tier_var = ctk.StringVar(value="1")
        self._option(race_box, "Tier (track selection)", self.tier_var, CLASS_OPTIONS, self._mark_tier_manual)
        ctk.CTkLabel(
            race_box,
            text="Auto-filled from the selected car when possible. This controls which track pool the schedule uses.",
            font=ctk.CTkFont(size=10),
            text_color="gray",
            anchor="w",
            wraplength=420,
        ).pack(fill="x", padx=14, pady=(0, 12))
        self.race_count_entry = self._entry(race_box, "Num of Races", "4")
        self.race_time_entry = self._entry(race_box, "Race Time", "15")
        self.max_opponents_entry = self._entry(race_box, "Max number of Opponents", "20")
        self.prestige_entry = self._entry(race_box, "Prestige", "1")
        ctk.CTkLabel(
            race_box,
            text="Prestige hint: 1 is local races. 100 is F1/world elite level.",
            font=ctk.CTkFont(size=10),
            text_color="gray",
            anchor="w",
        ).pack(fill="x", padx=14, pady=(0, 12))

        cars_box = self._section(scroll, "Cars and Classes")
        cars_box.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=6)
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
            row=1, column=2, pady=(8, 0)
        )
        ctk.CTkButton(
            car_controls,
            text="Add Car",
            command=self.add_selected_car,
            width=110,
            height=34,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=1, column=3, padx=(8, 0), pady=(8, 0))

        self.selected_cars_frame = ctk.CTkFrame(cars_box, fg_color=("gray84", "gray18"), corner_radius=12)
        self.selected_cars_frame.pack(fill="x", padx=14, pady=(0, 12))
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
            text="<- Settings",
            command=lambda: self.show_screen("SettingsScreen"),
            width=130,
            height=38,
            fg_color="gray30",
            hover_color="gray40",
        ).pack(side="left", padx=(10, 0))

    def on_show(self) -> None:
        self._refresh_car_options()
        self._refresh_selected_cars()
        self.status_label.configure(text=f"{len(custom_championship_rows())} custom championship row(s) saved.")

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
        for widget in self.selected_cars_frame.winfo_children():
            widget.destroy()
        if not self.selected_cars:
            ctk.CTkLabel(
                self.selected_cars_frame,
                text="No cars added yet. Add at least one car to create the championship.",
                text_color="gray",
                anchor="w",
            ).pack(fill="x", padx=12, pady=10)
            return
        for index, car in enumerate(self.selected_cars, start=1):
            text = f"{index}. Class {car.get('_custom_class', '1')} | {car.get('Car', '')} | {car.get('Car class', '')}"
            ctk.CTkLabel(self.selected_cars_frame, text=text, anchor="w").pack(fill="x", padx=12, pady=4)

    def save_custom_championship(self) -> None:
        name = self.name_entry.get().strip()
        if not name:
            self.status_label.configure(text="Championship name is required.", text_color="#ff7777")
            return
        if not self.selected_cars:
            self.status_label.configure(text="Add at least one car.", text_color="#ff7777")
            return
        try:
            race_count = self._parse_int(self.race_count_entry.get(), "Num of Races", 1, 50)
            race_time = self._parse_int(self.race_time_entry.get(), "Race Time", 1, 240)
            max_opponents = self._parse_int(self.max_opponents_entry.get(), "Max number of Opponents", 1, 80)
            prestige = self._parse_int(self.prestige_entry.get(), "Prestige", 1, 100)
            tier = self._parse_int(self.tier_var.get(), "Tier", 1, 5)
        except ValueError as error:
            self.status_label.configure(text=str(error), text_color="#ff7777")
            return

        championship_id = new_custom_championship_id(name)
        game = self.game_var.get()
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
                    "Prestige": str(prestige),
                }
            )

        path = append_custom_championship(rows)
        self.status_label.configure(text=f"Saved {name} to {path.name}.", text_color="#4da6ff")
        self.name_entry.delete(0, "end")
        self.selected_cars = []
        self._tier_autofill_enabled = True
        self._set_tier_value("1")
        self._refresh_selected_cars()

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
