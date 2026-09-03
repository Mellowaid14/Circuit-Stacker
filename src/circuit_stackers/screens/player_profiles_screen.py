from __future__ import annotations

import re
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from ..player_profiles import (
    create_player_profile,
    default_profile_id,
    delete_player_profile,
    export_player_profile,
    get_player_profile,
    import_player_profile,
    list_player_profiles,
    profile_owned_assets,
    rename_player_profile,
    set_default_profile,
)


class PlayerProfilesScreen(ctk.CTkFrame):
    def __init__(self, parent, show_screen) -> None:
        super().__init__(parent, fg_color="transparent")
        self.parent = parent
        self.show_screen = show_screen
        self.selected_profile_id = ""

        ctk.CTkLabel(self, text="Player Profiles", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(30, 4))
        ctk.CTkLabel(
            self,
            text="Each profile keeps its own owned cars and tracks. Co-op careers use only content shared by every selected profile.",
            font=ctk.CTkFont(size=12),
            text_color="gray",
            wraplength=760,
        ).pack(pady=(0, 16))

        shell = ctk.CTkFrame(self, fg_color="transparent")
        shell.pack(fill="both", expand=True, padx=80, pady=(0, 16))
        shell.grid_columnconfigure(0, weight=2)
        shell.grid_columnconfigure(1, weight=3)
        shell.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(shell, fg_color=("gray90", "gray15"), corner_radius=12)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ctk.CTkLabel(left, text="Profiles", font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=16, pady=(16, 8))
        self.profile_list = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self.profile_list.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        left_actions = ctk.CTkFrame(left, fg_color="transparent")
        left_actions.pack(fill="x", padx=16, pady=(0, 16))
        ctk.CTkButton(left_actions, text="Create Profile", command=self._create_profile, height=36).pack(fill="x")
        ctk.CTkButton(
            left_actions,
            text="Import Profile",
            command=self._import_profile,
            height=34,
            fg_color="gray30",
            hover_color="gray40",
        ).pack(fill="x", pady=(8, 0))

        right = ctk.CTkFrame(shell, fg_color=("gray90", "gray15"), corner_radius=12)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        self.name_label = ctk.CTkLabel(right, text="Select a profile", font=ctk.CTkFont(size=20, weight="bold"))
        self.name_label.pack(anchor="w", padx=20, pady=(20, 8))
        self.content_label = ctk.CTkLabel(right, text="", justify="left", text_color="gray", font=ctk.CTkFont(size=12))
        self.content_label.pack(anchor="w", padx=20, pady=(0, 18))
        actions = ctk.CTkFrame(right, fg_color="transparent")
        actions.pack(anchor="w", padx=20)
        self.iracing_btn = ctk.CTkButton(actions, text="Edit iRacing Content", command=lambda: self._open_ownership("iRacing"), width=170)
        self.iracing_btn.pack(side="left")
        self.ams2_btn = ctk.CTkButton(actions, text="Edit AMS2 Content", command=lambda: self._open_ownership("AMS2"), width=170)
        self.ams2_btn.pack(side="left", padx=(10, 0))
        profile_actions = ctk.CTkFrame(right, fg_color="transparent")
        profile_actions.pack(anchor="w", padx=20, pady=(14, 0))
        self.rename_btn = ctk.CTkButton(profile_actions, text="Rename", command=self._rename_profile, width=110, fg_color="gray30", hover_color="gray40")
        self.rename_btn.pack(side="left")
        self.default_btn = ctk.CTkButton(
            profile_actions,
            text="Make Default",
            command=self._make_default,
            width=125,
            fg_color="gray30",
            hover_color="gray40",
        )
        self.default_btn.pack(side="left", padx=(10, 0))
        self.delete_btn = ctk.CTkButton(profile_actions, text="Delete", command=self._delete_profile, width=110, fg_color="#9f2f2f", hover_color="#7d2525")
        self.delete_btn.pack(side="left", padx=(10, 0))
        self.export_btn = ctk.CTkButton(
            profile_actions,
            text="Export Profile",
            command=self._export_profile,
            width=130,
            fg_color="gray30",
            hover_color="gray40",
        )
        self.export_btn.pack(side="left", padx=(10, 0))
        self.status_label = ctk.CTkLabel(right, text="", text_color="gray", font=ctk.CTkFont(size=11))
        self.status_label.pack(anchor="w", padx=20, pady=(16, 0))

        ctk.CTkButton(
            self,
            text="<- Back to Settings",
            command=lambda: self.show_screen("SettingsScreen"),
            width=160,
            height=36,
            fg_color="gray30",
            hover_color="gray40",
        ).pack(pady=(0, 18))

    def on_show(self) -> None:
        self._refresh()

    def _refresh(self, preferred_id: str = "") -> None:
        profiles = list_player_profiles()
        valid_ids = {profile["id"] for profile in profiles}
        if preferred_id in valid_ids:
            self.selected_profile_id = preferred_id
        elif self.selected_profile_id not in valid_ids:
            self.selected_profile_id = default_profile_id()
        for widget in self.profile_list.winfo_children():
            widget.destroy()
        for profile in profiles:
            is_selected = profile["id"] == self.selected_profile_id
            label = profile["name"] + ("  (Default)" if profile["id"] == default_profile_id() else "")
            ctk.CTkButton(
                self.profile_list,
                text=label,
                command=lambda profile_id=profile["id"]: self._select_profile(profile_id),
                anchor="w",
                height=38,
                fg_color=("#cfe7ff", "#17456e") if is_selected else ("gray82", "gray22"),
                hover_color=("gray75", "gray28"),
            ).pack(fill="x", pady=3)
        self._show_selected()

    def _select_profile(self, profile_id: str) -> None:
        self.selected_profile_id = profile_id
        self._refresh(profile_id)

    def _show_selected(self) -> None:
        profile = next((item for item in list_player_profiles() if item["id"] == self.selected_profile_id), None)
        enabled = "normal" if profile else "disabled"
        for button in (self.iracing_btn, self.ams2_btn, self.rename_btn, self.default_btn, self.delete_btn, self.export_btn):
            button.configure(state=enabled)
        if not profile:
            self.name_label.configure(text="Select a profile")
            self.content_label.configure(text="")
            return
        ir_cars, ir_tracks = profile_owned_assets(profile["id"], "iRacing")
        ams_cars, ams_tracks = profile_owned_assets(profile["id"], "AMS2")
        self.name_label.configure(text=profile["name"])
        self.content_label.configure(
            text=(
                f"iRacing: {len(ir_cars)} cars | {len(ir_tracks)} tracks\n"
                f"AMS2: {len(ams_cars)} DLC car entries | {len(ams_tracks)} DLC tracks"
            )
        )
        self.delete_btn.configure(state="disabled" if profile["id"] == default_profile_id() else "normal")
        self.default_btn.configure(
            state="disabled" if profile["id"] == default_profile_id() else "normal",
            text="Default Profile" if profile["id"] == default_profile_id() else "Make Default",
        )

    def _prompt_name(self, title: str, text: str) -> str:
        dialog = ctk.CTkInputDialog(title=title, text=text)
        return str(dialog.get_input() or "").strip()

    def _create_profile(self) -> None:
        name = self._prompt_name("Create Player Profile", "Profile / driver name:")
        if not name:
            return
        success, message, profile = create_player_profile(name)
        self.status_label.configure(text=message, text_color="#43b86b" if success else "#ff5c5c")
        self._refresh(profile["id"] if profile else "")

    def _rename_profile(self) -> None:
        if not self.selected_profile_id:
            return
        name = self._prompt_name("Rename Player Profile", "New profile / driver name:")
        if not name:
            return
        success, message = rename_player_profile(self.selected_profile_id, name)
        self.status_label.configure(text=message, text_color="#43b86b" if success else "#ff5c5c")
        self._refresh(self.selected_profile_id)

    def _delete_profile(self) -> None:
        success, message = delete_player_profile(self.selected_profile_id)
        self.status_label.configure(text=message, text_color="#43b86b" if success else "#ff5c5c")
        if success:
            self.selected_profile_id = default_profile_id()
        self._refresh(self.selected_profile_id)

    def _make_default(self) -> None:
        if not self.selected_profile_id:
            return
        success, message = set_default_profile(self.selected_profile_id)
        self.status_label.configure(text=message, text_color="#43b86b" if success else "#ff5c5c")
        self._refresh(self.selected_profile_id)

    def _export_profile(self) -> None:
        profile = get_player_profile(self.selected_profile_id)
        if profile is None:
            return
        safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", profile["name"]).strip("._") or "player_profile"
        selected = filedialog.asksaveasfilename(
            title="Export Player Profile",
            initialfile=f"{safe_name}.csprofile",
            defaultextension=".csprofile",
            filetypes=[("Circuit Stacker Profile", "*.csprofile"), ("JSON files", "*.json")],
        )
        if not selected:
            return
        success, message = export_player_profile(self.selected_profile_id, Path(selected))
        self.status_label.configure(text=message, text_color="#43b86b" if success else "#ff5c5c")

    def _import_profile(self) -> None:
        selected = filedialog.askopenfilename(
            title="Import Player Profile",
            filetypes=[
                ("Circuit Stacker Profile", "*.csprofile"),
                ("JSON files", "*.json"),
                ("All files", "*.*"),
            ],
        )
        if not selected:
            return
        success, message, profile = import_player_profile(Path(selected))
        self.status_label.configure(text=message, text_color="#43b86b" if success else "#ff5c5c")
        self._refresh(profile["id"] if profile else self.selected_profile_id)

    def _open_ownership(self, game: str) -> None:
        if not self.selected_profile_id:
            return
        screen = self.parent.screens["OwnershipScreen"]
        screen.set_game(game)
        screen.set_profile(self.selected_profile_id, "PlayerProfilesScreen")
        self.show_screen("OwnershipScreen")
