from __future__ import annotations

from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from .exporter import (
    ChampionshipOption,
    build_iracing_roster_payload,
    default_source_folder,
    export_roster_json,
    infer_iracing_car,
    list_championship_options,
    list_iracing_cars,
    list_slot_keys,
    load_export_bundle,
    resolve_roster_drivers,
    slot_label,
)


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class StandaloneExporterApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("AMS2 to iRacing Roster Exporter")
        self.geometry("920x760")
        self.minsize(860, 700)

        self.bundle: dict[str, dict[str, list[dict]]] = {}
        self.slot_options: list[str] = []
        self.championship_options: list[ChampionshipOption] = []
        self.car_options = list_iracing_cars()

        self.export_folder_var = ctk.StringVar(value=str(default_source_folder()))
        self.output_folder_var = ctk.StringVar(value=str((Path.cwd() / "output").resolve()))
        self.slot_var = ctk.StringVar(value="Select a slot")
        self.championship_var = ctk.StringVar(value="Select a championship")
        self.car_var = ctk.StringVar(value="Auto-detect")
        self.status_var = ctk.StringVar(
            value="Defaulting to the race-pace-career-app folder. If roster_exports exists there, the tool will load it automatically."
        )

        self._build_ui()
        self.after(50, self._auto_load_default_source)

    def _build_ui(self) -> None:
        ctk.CTkLabel(
            self,
            text="AMS2 to iRacing Roster Exporter",
            font=ctk.CTkFont(size=28, weight="bold"),
        ).pack(pady=(28, 8))

        ctk.CTkLabel(
            self,
            text="This tool defaults to the race-pace-career-app folder and will automatically look for exported RxDB JSON files in a roster_exports subfolder.",
            font=ctk.CTkFont(size=13),
            text_color="gray",
            wraplength=760,
            justify="center",
        ).pack(pady=(0, 18))

        panel = ctk.CTkFrame(self, corner_radius=16)
        panel.pack(fill="both", expand=True, padx=28, pady=(0, 28))

        self._folder_row(panel, "Export Folder", self.export_folder_var, self.choose_export_folder)
        self._folder_row(panel, "Output Folder", self.output_folder_var, self.choose_output_folder)

        self.slot_menu = ctk.CTkOptionMenu(
            panel,
            values=["Select a slot"],
            variable=self.slot_var,
            command=self.on_slot_change,
            width=520,
        )
        self._labeled_row(panel, "Save Slot", self.slot_menu)

        self.championship_menu = ctk.CTkOptionMenu(
            panel,
            values=["Select a championship"],
            variable=self.championship_var,
            command=self.on_championship_change,
            width=520,
        )
        self._labeled_row(panel, "Championship", self.championship_menu)

        car_values = ["Auto-detect"] + [self._car_label(car) for car in self.car_options]
        self.car_menu = ctk.CTkOptionMenu(
            panel,
            values=car_values,
            variable=self.car_var,
            width=520,
        )
        self._labeled_row(panel, "iRacing Car", self.car_menu)

        self.summary_box = ctk.CTkTextbox(panel, height=230, wrap="word")
        self.summary_box.pack(fill="both", expand=True, padx=22, pady=(10, 12))
        self.summary_box.insert("1.0", "No export loaded yet.")
        self.summary_box.configure(state="disabled")

        button_row = ctk.CTkFrame(panel, fg_color="transparent")
        button_row.pack(fill="x", padx=22, pady=(0, 14))

        ctk.CTkButton(
            button_row,
            text="Export Roster",
            command=self.export_roster,
            height=40,
            width=170,
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(side="left")

        ctk.CTkLabel(
            button_row,
            textvariable=self.status_var,
            font=ctk.CTkFont(size=12),
            text_color="gray",
            anchor="w",
            justify="left",
        ).pack(side="left", padx=(14, 0), fill="x", expand=True)

    def _folder_row(self, parent, label: str, variable: ctk.StringVar, command) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=22, pady=(18, 0))
        ctk.CTkLabel(row, text=label, width=130, anchor="w", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        ctk.CTkEntry(row, textvariable=variable, width=520).pack(side="left", padx=(0, 12), fill="x", expand=True)
        ctk.CTkButton(row, text="Browse", command=command, width=110).pack(side="left")

    def _labeled_row(self, parent, label: str, widget) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=22, pady=(18, 0))
        ctk.CTkLabel(row, text=label, width=130, anchor="w", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        widget.pack(side="left", fill="x", expand=True)

    def choose_export_folder(self) -> None:
        folder = filedialog.askdirectory(title="Choose race-pace-career-app or export folder")
        if not folder:
            return
        self.export_folder_var.set(folder)
        self.load_exports(folder)

    def choose_output_folder(self) -> None:
        folder = filedialog.askdirectory(title="Choose roster output folder")
        if folder:
            self.output_folder_var.set(folder)

    def load_exports(self, folder: str) -> None:
        try:
            self.bundle = load_export_bundle(folder)
        except Exception as error:
            self.status_var.set(str(error))
            self._set_summary(str(error))
            self.slot_options = []
            self.championship_options = []
            self.slot_var.set("Select a slot")
            self.slot_menu.configure(values=["Select a slot"])
            self.championship_var.set("Select a championship")
            self.championship_menu.configure(values=["Select a championship"])
            return

        self.slot_options = list_slot_keys(self.bundle)
        slot_labels = [slot_label(slot) for slot in self.slot_options]
        self.slot_var.set(slot_labels[0] if slot_labels else "Select a slot")
        self.slot_menu.configure(values=slot_labels or ["Select a slot"])
        self.status_var.set(f"Loaded {len(self.slot_options)} slot export set(s).")
        self.on_slot_change(self.slot_var.get())

    def on_slot_change(self, selected_label: str) -> None:
        slot_key = self._slot_key_from_label(selected_label)
        if not slot_key:
            return
        self.championship_options = list_championship_options(self.bundle, slot_key)
        labels = [option.label for option in self.championship_options] or ["Select a championship"]
        self.championship_var.set(labels[0])
        self.championship_menu.configure(values=labels)
        self.on_championship_change(self.championship_var.get())

    def on_championship_change(self, selected_label: str) -> None:
        option = self._selected_championship(selected_label)
        if option is None:
            return
        auto_car = infer_iracing_car(option)
        self.car_var.set(self._car_label(auto_car) if auto_car else "Auto-detect")

        summary_lines = [
            f"Slot: {slot_label(option.slot_key)}",
            f"Championship: {option.label}",
            f"Championship ID: {option.championship_id}",
            f"Season IDs: {', '.join(option.season_ids) if option.season_ids else 'Not found in export'}",
        ]
        try:
            drivers = resolve_roster_drivers(self.bundle, option)
            summary_lines.append(f"Resolved drivers: {len(drivers)}")
            summary_lines.append(f"First drivers: {', '.join(driver.get('name', driver.get('displayName', 'Unknown')) for driver in drivers[:6])}")
        except Exception as error:
            summary_lines.append(f"Driver resolution warning: {error}")
        if auto_car:
            summary_lines.append(f"Auto car match: {self._car_label(auto_car)}")
        else:
            summary_lines.append("Auto car match: none")
        self._set_summary("\n".join(summary_lines))

    def export_roster(self) -> None:
        option = self._selected_championship(self.championship_var.get())
        if option is None:
            self.status_var.set("Select a championship first.")
            return
        try:
            drivers = resolve_roster_drivers(self.bundle, option)
            chosen_car = self._selected_car(option)
            payload = build_iracing_roster_payload(drivers, option, chosen_car)
            roster_path = export_roster_json(self.output_folder_var.get(), option, payload)
        except Exception as error:
            self.status_var.set(str(error))
            return
        self.status_var.set(f"Exported {len(payload['drivers'])} drivers to {roster_path}")
        self._set_summary(
            "\n".join(
                [
                    f"Export complete: {roster_path}",
                    f"Slot: {slot_label(option.slot_key)}",
                    f"Championship: {option.label}",
                    f"Drivers: {len(payload['drivers'])}",
                    f"Car: {self._car_label(chosen_car) if chosen_car else 'No car assigned'}",
                ]
            )
        )

    def _auto_load_default_source(self) -> None:
        source = self.export_folder_var.get().strip()
        if source:
            self.load_exports(source)

    def _selected_championship(self, label: str) -> ChampionshipOption | None:
        for option in self.championship_options:
            if option.label == label:
                return option
        return self.championship_options[0] if self.championship_options else None

    def _slot_key_from_label(self, label: str) -> str | None:
        for slot_key in self.slot_options:
            if slot_label(slot_key) == label:
                return slot_key
        return self.slot_options[0] if self.slot_options else None

    def _selected_car(self, option: ChampionshipOption) -> dict[str, str] | None:
        selected = self.car_var.get()
        if selected == "Auto-detect":
            return infer_iracing_car(option)
        for car in self.car_options:
            if self._car_label(car) == selected:
                return car
        return infer_iracing_car(option)

    @staticmethod
    def _car_label(car: dict[str, str] | None) -> str:
        if not car:
            return "Auto-detect"
        return f"{car.get('Car class', 'Unknown')} | {car.get('Car', 'Unknown')}"

    def _set_summary(self, text: str) -> None:
        self.summary_box.configure(state="normal")
        self.summary_box.delete("1.0", "end")
        self.summary_box.insert("1.0", text)
        self.summary_box.configure(state="disabled")


def launch_app() -> None:
    app = StandaloneExporterApp()
    app.mainloop()
