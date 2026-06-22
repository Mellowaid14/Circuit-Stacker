from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from ..settings_manager import (
    list_all_cars,
    list_all_tracks,
    owned_asset_lists,
    refresh_asset_caches,
    reset_owned_assets_to_default_for_game,
    update_owned_assets_for_game,
)
from ..player_profiles import (
    default_profile_id,
    get_player_profile,
    profile_owned_assets,
    reset_profile_owned_assets,
    update_profile_owned_assets,
)


class OwnershipScreen(ctk.CTkFrame):
    def __init__(self, parent, show_screen) -> None:
        super().__init__(parent, fg_color="transparent")
        self.show_screen = show_screen
        self.current_game = "iRacing"
        self.profile_id = default_profile_id()
        self.return_screen = "SettingsScreen"
        self.car_vars: dict[str, tk.BooleanVar] = {}
        self.track_vars: dict[str, tk.BooleanVar] = {}
        self.car_select_all_var: tk.BooleanVar | None = None
        self.track_select_all_var: tk.BooleanVar | None = None
        self.title_label = ctk.CTkLabel(self, text="Owned Cars and Tracks", font=ctk.CTkFont(size=24, weight="bold"))
        self.title_label.pack(
            pady=(28, 8)
        )
        self.subtitle_label = ctk.CTkLabel(
            self,
            text="Choose the content you own. These selections drive championships and schedule generation.",
            font=ctk.CTkFont(size=13),
            text_color="gray",
        )
        self.subtitle_label.pack(pady=(0, 16))
        self.profile_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("#15507d", "#7dbdff"),
        )
        self.profile_label.pack(pady=(0, 10))

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(pady=(0, 12))

        ctk.CTkButton(
            buttons,
            text="Save Ownership",
            command=self.save_ownership,
            height=36,
            width=150,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left")

        ctk.CTkButton(
            buttons,
            text="Reset to Default",
            command=self.reset_defaults,
            height=36,
            width=150,
            font=ctk.CTkFont(size=12),
            fg_color="gray30",
            hover_color="gray40",
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            buttons,
            text="<- Back",
            command=lambda: self.show_screen(self.return_screen),
            height=36,
            width=120,
            font=ctk.CTkFont(size=12),
            fg_color="gray30",
            hover_color="gray40",
        ).pack(side="left")

        columns = ctk.CTkFrame(self, fg_color="transparent")
        columns.pack(fill="both", expand=True, padx=24, pady=(0, 16))
        columns.grid_columnconfigure(0, weight=1)
        columns.grid_columnconfigure(1, weight=1)

        car_box = ctk.CTkFrame(columns, fg_color=("gray90", "gray15"), corner_radius=12)
        car_box.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.cars_box_label = ctk.CTkLabel(car_box, text="Cars", font=ctk.CTkFont(size=14, weight="bold"))
        self.cars_box_label.pack(
            anchor="w", padx=14, pady=(12, 6)
        )
        self.cars_frame = ctk.CTkScrollableFrame(car_box, height=500, fg_color="transparent")
        self.cars_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        track_box = ctk.CTkFrame(columns, fg_color=("gray90", "gray15"), corner_radius=12)
        track_box.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        self.tracks_box_label = ctk.CTkLabel(track_box, text="Tracks", font=ctk.CTkFont(size=14, weight="bold"))
        self.tracks_box_label.pack(
            anchor="w", padx=14, pady=(12, 6)
        )
        self.tracks_frame = ctk.CTkScrollableFrame(track_box, height=500, fg_color="transparent")
        self.tracks_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.status_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=11), text_color="gray")
        self.status_label.pack(pady=(0, 8))

    def on_show(self) -> None:
        profile = get_player_profile(self.profile_id)
        if profile is None:
            self.profile_id = default_profile_id()
            profile = get_player_profile(self.profile_id)
        self.profile_label.configure(text=f"Profile: {(profile or {}).get('name', 'Default Player')}")
        self.title_label.configure(text=f"{self.current_game} Owned Cars and Tracks")
        if self.current_game == "AMS2":
            self.subtitle_label.configure(
                text="Choose your AMS2 car and track DLC packs. These selections drive championships and schedule generation."
            )
            self.cars_box_label.configure(text="Car DLCs")
            self.tracks_box_label.configure(text="Track DLCs")
        else:
            self.subtitle_label.configure(
                text=f"Choose the {self.current_game} content you own. These selections drive championships and schedule generation."
            )
            self.cars_box_label.configure(text="Cars")
            self.tracks_box_label.configure(text="Tracks")
        self.populate_lists()
        self.status_label.configure(text="")

    def set_game(self, game: str) -> None:
        self.current_game = "AMS2" if str(game).strip().casefold() == "ams2" else "iRacing"

    def set_profile(self, profile_id: str, return_screen: str = "PlayerProfilesScreen") -> None:
        self.profile_id = str(profile_id).strip() or default_profile_id()
        self.return_screen = return_screen

    def populate_lists(self) -> None:
        refresh_asset_caches()
        if self.profile_id:
            owned_car_ids, owned_track_names = profile_owned_assets(self.profile_id, self.current_game)
        else:
            owned_car_ids, owned_track_names = owned_asset_lists(self.current_game)
        owned_car_ids = set(owned_car_ids)
        owned_track_names = set(owned_track_names)

        for widget in self.cars_frame.winfo_children():
            widget.destroy()
        for widget in self.tracks_frame.winfo_children():
            widget.destroy()

        self.car_vars = {}
        self.track_vars = {}
        self.car_select_all_var = None
        self.track_select_all_var = None

        if self.current_game == "AMS2":
            self._populate_ams2_car_dlcs(owned_car_ids)
            self._populate_ams2_track_dlcs(owned_track_names)
            self._sync_select_all_vars()
        else:
            for car in sorted(list_all_cars(), key=lambda row: row.get("Car", "").casefold()):
                if str(car.get("Game", "")).strip().casefold() not in {"", "iracing"}:
                    continue
                car_id = str(car["id"]).strip()
                label = car.get("Car", "Unknown Car")
                variable = tk.BooleanVar(value=car_id in owned_car_ids)
                self.car_vars[car_id] = variable
                ctk.CTkCheckBox(self.cars_frame, text=label, variable=variable).pack(anchor="w", padx=6, pady=4)

        if self.current_game != "AMS2":
            seen_tracks: set[str] = set()
            for track in sorted(list_all_tracks(), key=lambda row: row.get("Track", "").casefold()):
                game_name = str(track.get("Game", "")).strip().casefold()
                if game_name not in {"", "iracing"}:
                    continue
                track_name = str(track.get("Track", "")).strip()
                if not track_name or track_name.casefold() in seen_tracks:
                    continue
                seen_tracks.add(track_name.casefold())
                variable = tk.BooleanVar(value=track_name in owned_track_names)
                self.track_vars[track_name] = variable
                ctk.CTkCheckBox(self.tracks_frame, text=track_name, variable=variable).pack(anchor="w", padx=6, pady=4)

    def save_ownership(self) -> None:
        if self.current_game == "AMS2":
            selected_dlcs = {asset_id for asset_id, var in self.car_vars.items() if var.get()}
            car_ids = []
            for car in list_all_cars():
                if str(car.get("Game", "")).strip().casefold() not in {"", "ams2"}:
                    continue
                car_dlc = str(car.get("DLC", "")).strip() or "Base Game"
                if car_dlc in selected_dlcs:
                    car_ids.append(str(car.get("id", "")).strip())
            selected_track_dlcs = {asset_id for asset_id, var in self.track_vars.items() if var.get()}
            track_names = []
            for track in list_all_tracks():
                if str(track.get("Game", "")).strip().casefold() not in {"", "ams2"}:
                    continue
                track_name = str(track.get("Track", "")).strip()
                track_dlc = str(track.get("DLC", "")).strip()
                if not track_name or not track_dlc or track_dlc.casefold() == "base game":
                    continue
                if track_dlc in selected_track_dlcs:
                    track_names.append(track_name)
        else:
            car_ids = [asset_id for asset_id, var in self.car_vars.items() if var.get()]
            track_names = [asset_id for asset_id, var in self.track_vars.items() if var.get()]
        update_profile_owned_assets(self.profile_id, self.current_game, car_ids, track_names)
        if self.profile_id == default_profile_id():
            update_owned_assets_for_game(self.current_game, car_ids, track_names)
        self.status_label.configure(text=f"{self.current_game} owned content saved for this profile.")

    def reset_defaults(self) -> None:
        reset_profile_owned_assets(self.profile_id, self.current_game)
        if self.profile_id == default_profile_id():
            reset_owned_assets_to_default_for_game(self.current_game)
        self.populate_lists()
        self.status_label.configure(text=f"{self.current_game} ownership reset for this profile.")

    def _populate_ams2_car_dlcs(self, owned_car_ids: set[str]) -> None:
        dlc_to_car_ids: dict[str, set[str]] = {}
        for car in list_all_cars():
            if str(car.get("Game", "")).strip().casefold() not in {"", "ams2"}:
                continue
            car_id = str(car.get("id", "")).strip()
            if not car_id:
                continue
            dlc_name = str(car.get("DLC", "")).strip()
            if not dlc_name or dlc_name.casefold() == "base game":
                continue
            dlc_to_car_ids.setdefault(dlc_name, set()).add(car_id)

        for dlc_name in sorted(dlc_to_car_ids, key=str.casefold):
            if self.car_select_all_var is None:
                self.car_select_all_var = tk.BooleanVar(value=False)
                ctk.CTkCheckBox(
                    self.cars_frame,
                    text="Select All Car DLCs",
                    variable=self.car_select_all_var,
                    command=lambda: self._set_all_asset_vars("cars", self.car_select_all_var),
                    font=ctk.CTkFont(size=12, weight="bold"),
                ).pack(anchor="w", padx=6, pady=(4, 10))

            dlc_car_ids = dlc_to_car_ids[dlc_name]
            variable = tk.BooleanVar(value=bool(dlc_car_ids & owned_car_ids))
            self.car_vars[dlc_name] = variable
            ctk.CTkCheckBox(
                self.cars_frame,
                text=dlc_name,
                variable=variable,
                command=self._sync_select_all_vars,
            ).pack(anchor="w", padx=6, pady=4)

    def _populate_ams2_track_dlcs(self, owned_track_names: set[str]) -> None:
        dlc_to_track_names: dict[str, set[str]] = {}
        for track in list_all_tracks():
            if str(track.get("Game", "")).strip().casefold() not in {"", "ams2"}:
                continue
            track_name = str(track.get("Track", "")).strip()
            if not track_name:
                continue
            dlc_name = str(track.get("DLC", "")).strip()
            if not dlc_name or dlc_name.casefold() == "base game":
                continue
            dlc_to_track_names.setdefault(dlc_name, set()).add(track_name)

        for dlc_name in sorted(dlc_to_track_names, key=str.casefold):
            if self.track_select_all_var is None:
                self.track_select_all_var = tk.BooleanVar(value=False)
                ctk.CTkCheckBox(
                    self.tracks_frame,
                    text="Select All Track DLCs",
                    variable=self.track_select_all_var,
                    command=lambda: self._set_all_asset_vars("tracks", self.track_select_all_var),
                    font=ctk.CTkFont(size=12, weight="bold"),
                ).pack(anchor="w", padx=6, pady=(4, 10))

            dlc_track_names = dlc_to_track_names[dlc_name]
            variable = tk.BooleanVar(value=bool(dlc_track_names & owned_track_names))
            self.track_vars[dlc_name] = variable
            ctk.CTkCheckBox(
                self.tracks_frame,
                text=dlc_name,
                variable=variable,
                command=self._sync_select_all_vars,
            ).pack(anchor="w", padx=6, pady=4)

    def _set_all_asset_vars(self, asset_type: str, source_var: tk.BooleanVar | None) -> None:
        if source_var is None:
            return
        selected = bool(source_var.get())
        target_vars = self.car_vars if asset_type == "cars" else self.track_vars
        for variable in target_vars.values():
            variable.set(selected)
        self._sync_select_all_vars()

    def _sync_select_all_vars(self) -> None:
        if self.car_select_all_var is not None:
            self.car_select_all_var.set(bool(self.car_vars) and all(var.get() for var in self.car_vars.values()))
        if self.track_select_all_var is not None:
            self.track_select_all_var.set(bool(self.track_vars) and all(var.get() for var in self.track_vars.values()))
