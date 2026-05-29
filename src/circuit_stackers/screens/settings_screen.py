from __future__ import annotations

from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from ..settings_manager import (
    load_settings,
    update_ams2_directory,
    update_ams2_leaderboard_overlay_geometry,
    update_check_for_updates_on_launch,
    update_custom_overlay_enabled,
    update_iracing_directory,
)
from ..update_checker import update_check_configured
from ..version import APP_VERSION


class OverlayLayoutEditor(ctk.CTkToplevel):
    def __init__(self, parent, on_saved) -> None:
        super().__init__(parent)
        self.title("Overlay Layout Editor")
        self.attributes("-topmost", True)
        self.on_saved = on_saved
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.resize_start_x = 0
        self.resize_start_y = 0
        self.resize_start_width = 0
        self.resize_start_height = 0
        settings = load_settings()
        self.geometry(str(settings.get("ams2_leaderboard_overlay_geometry", "520x520+80+80")))
        self.overrideredirect(True)
        try:
            self.attributes("-alpha", 0.72)
        except Exception:
            pass
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        shell = ctk.CTkFrame(self, fg_color="#101010", corner_radius=0, border_width=2, border_color="#4da6ff")
        shell.pack(fill="both", expand=True)
        shell.bind("<ButtonPress-1>", self._start_drag)
        shell.bind("<B1-Motion>", self._drag)

        title = ctk.CTkLabel(
            shell,
            text="AMS2 Leaderboard Overlay Box",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        title.pack(anchor="w", padx=16, pady=(16, 4))
        title.bind("<ButtonPress-1>", self._start_drag)
        title.bind("<B1-Motion>", self._drag)
        hint = ctk.CTkLabel(
            shell,
            text="Drag this box to position it. Drag the Resize handle to size it. Save when it is where you want it.",
            text_color="gray",
            wraplength=440,
            justify="left",
        )
        hint.pack(anchor="w", padx=16, pady=(0, 12))
        hint.bind("<ButtonPress-1>", self._start_drag)
        hint.bind("<B1-Motion>", self._drag)

        preview = ctk.CTkFrame(shell, fg_color="#202020", corner_radius=0)
        preview.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        for label, width in [("POS", 42), ("Name", 130), ("Car", 100), ("Gap", 60)]:
            ctk.CTkLabel(preview, text=label, width=width, anchor="w", text_color="gray").pack(
                side="left", padx=6, pady=14
            )

        actions = ctk.CTkFrame(shell, fg_color="transparent")
        actions.pack(fill="x", padx=16, pady=(0, 16))
        ctk.CTkButton(actions, text="Save Position", command=self._save, width=130, height=32).pack(side="left")
        ctk.CTkButton(
            actions,
            text="Close",
            command=self.destroy,
            width=90,
            height=32,
            fg_color="gray30",
            hover_color="gray40",
        ).pack(side="left", padx=(10, 0))
        resize_handle = ctk.CTkLabel(actions, text="Resize", width=70, anchor="e", text_color="#4da6ff")
        resize_handle.pack(side="right")
        resize_handle.bind("<ButtonPress-1>", self._start_resize)
        resize_handle.bind("<B1-Motion>", self._resize)

    def _start_drag(self, event) -> None:
        self.drag_start_x = int(event.x_root) - self.winfo_x()
        self.drag_start_y = int(event.y_root) - self.winfo_y()

    def _drag(self, event) -> None:
        self.geometry(f"+{int(event.x_root) - self.drag_start_x}+{int(event.y_root) - self.drag_start_y}")

    def _start_resize(self, event) -> None:
        self.resize_start_x = int(event.x_root)
        self.resize_start_y = int(event.y_root)
        self.resize_start_width = self.winfo_width()
        self.resize_start_height = self.winfo_height()

    def _resize(self, event) -> None:
        width = max(300, self.resize_start_width + int(event.x_root) - self.resize_start_x)
        height = max(240, self.resize_start_height + int(event.y_root) - self.resize_start_y)
        self.geometry(f"{width}x{height}+{self.winfo_x()}+{self.winfo_y()}")

    def _save(self) -> None:
        self.update_idletasks()
        geometry = f"{self.winfo_width()}x{self.winfo_height()}+{self.winfo_x()}+{self.winfo_y()}"
        update_ams2_leaderboard_overlay_geometry(geometry)
        self.on_saved(geometry)
        self.destroy()


class SettingsScreen(ctk.CTkFrame):
    def __init__(self, parent, show_screen) -> None:
        super().__init__(parent, fg_color="transparent")
        self.parent = parent
        self.show_screen = show_screen
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(28, 10))
        ctk.CTkLabel(header, text="Settings", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(0, 8))
        ctk.CTkLabel(
            header,
            text="Set your game folders and manage owned content for both iRacing and AMS2.",
            font=ctk.CTkFont(size=13),
            text_color="gray",
        ).pack()

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 10))
        body.grid_columnconfigure(0, weight=1)

        content = ctk.CTkFrame(body, fg_color="transparent")
        content.pack(fill="x", padx=120, pady=(0, 16))
        content.grid_columnconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=1)

        iracing_box = self._build_game_box(content, "iRacing")
        iracing_box.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.iracing_path_entry = self._build_path_entry(iracing_box)
        self._build_path_buttons(
            iracing_box,
            browse_command=lambda: self.browse_for_path(self.iracing_path_entry, "iRacing"),
            save_command=lambda: self.save_path(self.iracing_path_entry, "iRacing"),
            ownership_command=lambda: self.open_ownership("iRacing"),
        )
        self.iracing_warning_label = self._build_path_warning(iracing_box)
        self.iracing_path_entry.bind("<KeyRelease>", lambda _event: self.validate_path_entry("iRacing"))

        ams2_box = self._build_game_box(content, "AMS2")
        ams2_box.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        self.ams2_path_entry = self._build_path_entry(ams2_box)
        self._build_path_buttons(
            ams2_box,
            browse_command=lambda: self.browse_for_path(self.ams2_path_entry, "AMS2"),
            save_command=lambda: self.save_path(self.ams2_path_entry, "AMS2"),
            ownership_command=lambda: self.open_ownership("AMS2"),
        )
        self.ams2_warning_label = self._build_path_warning(ams2_box)
        self.ams2_path_entry.bind("<KeyRelease>", lambda _event: self.validate_path_entry("AMS2"))

        custom_box = ctk.CTkFrame(body, fg_color=("gray90", "gray15"), corner_radius=12)
        custom_box.pack(fill="x", padx=120, pady=(0, 16))
        ctk.CTkLabel(
            custom_box,
            text="Custom Championships",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=18, pady=(16, 6))
        ctk.CTkLabel(
            custom_box,
            text="Create user championships that are included in new careers and future season offers.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        ).pack(anchor="w", padx=18, pady=(0, 10))
        custom_actions = ctk.CTkFrame(custom_box, fg_color="transparent")
        custom_actions.pack(anchor="w", padx=18, pady=(0, 16))
        ctk.CTkButton(
            custom_actions,
            text="Custom Championship Builder",
            command=lambda: self.show_screen("CustomChampionshipScreen"),
            height=34,
            width=210,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left")
        ctk.CTkButton(
            custom_actions,
            text="Manage Championships",
            command=lambda: self.show_screen("CustomChampionshipManageScreen"),
            height=34,
            width=190,
            fg_color="gray30",
            hover_color="gray40",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left", padx=(10, 0))

        updates_box = ctk.CTkFrame(body, fg_color=("gray90", "gray15"), corner_radius=12)
        updates_box.pack(fill="x", padx=120, pady=(0, 16))
        ctk.CTkLabel(
            updates_box,
            text="App Updates",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=18, pady=(16, 6))
        ctk.CTkLabel(
            updates_box,
            text=f"Current version: {APP_VERSION}. Updates use the latest GitHub release when the repo is configured.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        ).pack(anchor="w", padx=18, pady=(0, 10))
        self.update_check_var = ctk.BooleanVar(value=True)
        self.update_check_switch = ctk.CTkSwitch(
            updates_box,
            text="Check for updates when Circuit Stacker launches",
            variable=self.update_check_var,
            command=self.save_update_check_enabled,
            font=ctk.CTkFont(size=12),
        )
        self.update_check_switch.pack(anchor="w", padx=18, pady=(0, 10))
        update_actions = ctk.CTkFrame(updates_box, fg_color="transparent")
        update_actions.pack(anchor="w", padx=18, pady=(0, 16))
        self.check_now_btn = ctk.CTkButton(
            update_actions,
            text="Check Now",
            command=self.check_for_updates_now,
            height=34,
            width=130,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.check_now_btn.pack(side="left")
        self.update_config_label = ctk.CTkLabel(update_actions, text="", text_color="gray", font=ctk.CTkFont(size=11))
        self.update_config_label.pack(side="left", padx=(12, 0))

        overlay_box = ctk.CTkFrame(body, fg_color=("gray90", "gray15"), corner_radius=12)
        overlay_box.pack(fill="x", padx=120, pady=(0, 16))
        ctk.CTkLabel(
            overlay_box,
            text="Custom Overlays (Experimental)",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w", padx=18, pady=(16, 6))
        self.overlay_enabled_var = ctk.BooleanVar(value=False)
        self.overlay_switch = ctk.CTkSwitch(
            overlay_box,
            text="Enable AMS2 leaderboard overlay (experimental)",
            variable=self.overlay_enabled_var,
            command=self.save_overlay_enabled,
            font=ctk.CTkFont(size=12),
        )
        self.overlay_switch.pack(anchor="w", padx=18, pady=(0, 10))
        overlay_actions = ctk.CTkFrame(overlay_box, fg_color="transparent")
        overlay_actions.pack(anchor="w", padx=18, pady=(0, 16))
        ctk.CTkButton(
            overlay_actions,
            text="Overlay Layout Editor",
            command=self.open_overlay_editor,
            height=34,
            width=180,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left")
        self.overlay_geometry_label = ctk.CTkLabel(overlay_actions, text="", text_color="gray", font=ctk.CTkFont(size=11))
        self.overlay_geometry_label.pack(side="left", padx=(12, 0))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 18))
        footer.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(footer, text="", font=ctk.CTkFont(size=11), text_color="gray")
        self.status_label.grid(row=0, column=0, pady=(0, 8))

        ctk.CTkButton(
            footer,
            text="<- Back",
            command=self.go_back,
            height=36,
            width=140,
            fg_color="gray30",
            hover_color="gray40",
            font=ctk.CTkFont(size=12),
        ).grid(row=1, column=0)

    def _build_game_box(self, parent, game_name: str) -> ctk.CTkFrame:
        box = ctk.CTkFrame(parent, fg_color=("gray90", "gray15"), corner_radius=12)
        ctk.CTkLabel(box, text=f"{game_name} Folder", font=ctk.CTkFont(size=14, weight="bold")).pack(
            anchor="w", padx=18, pady=(18, 6)
        )
        return box

    @staticmethod
    def _build_path_entry(parent) -> ctk.CTkEntry:
        entry = ctk.CTkEntry(parent, width=420, height=38, font=ctk.CTkFont(size=12))
        entry.pack(padx=18, pady=(0, 12))
        return entry

    @staticmethod
    def _build_path_warning(parent) -> ctk.CTkLabel:
        label = ctk.CTkLabel(
            parent,
            text="",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#ff5c5c",
            wraplength=390,
            justify="left",
        )
        label.pack(anchor="w", padx=18, pady=(0, 16))
        return label

    def _build_path_buttons(self, parent, browse_command, save_command, ownership_command) -> None:
        path_buttons = ctk.CTkFrame(parent, fg_color="transparent")
        path_buttons.pack(pady=(0, 18))

        ctk.CTkButton(
            path_buttons,
            text="Browse for Folder",
            command=browse_command,
            height=34,
            width=150,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left")

        ctk.CTkButton(
            path_buttons,
            text="Save Folder Path",
            command=save_command,
            height=34,
            width=150,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#1f8f45",
            hover_color="#176f35",
        ).pack(side="left", padx=(10, 0))

        ctk.CTkButton(
            parent,
            text="Owned Cars and Tracks",
            command=ownership_command,
            height=36,
            width=190,
            font=ctk.CTkFont(size=12),
            fg_color="gray30",
            hover_color="gray40",
        ).pack(pady=(0, 18))

    def on_show(self) -> None:
        settings = load_settings()
        self.iracing_path_entry.delete(0, "end")
        self.iracing_path_entry.insert(0, settings["iracing_directory"])
        self.ams2_path_entry.delete(0, "end")
        self.ams2_path_entry.insert(0, settings["ams2_directory"])
        self.overlay_enabled_var.set(bool(settings.get("custom_overlay_enabled", False)))
        self.update_check_var.set(bool(settings.get("check_for_updates_on_launch", True)))
        configured = update_check_configured()
        self.check_now_btn.configure(state="normal" if configured else "disabled")
        self.update_config_label.configure(
            text="GitHub repo configured." if configured else "GitHub repo not configured yet."
        )
        self.overlay_geometry_label.configure(
            text=f"AMS2 leaderboard: {settings.get('ams2_leaderboard_overlay_geometry', '520x520+80+80')}"
        )
        self.validate_path_entry("iRacing")
        self.validate_path_entry("AMS2")
        self.status_label.configure(text="")

    def save_path(self, entry: ctk.CTkEntry, game: str) -> None:
        warning = self.validate_path_entry(game)
        if game == "AMS2":
            update_ams2_directory(entry.get())
        else:
            update_iracing_directory(entry.get())
        self.status_label.configure(text=f"{game} folder saved." if not warning else f"{game} folder saved with warning.")

    def browse_for_path(self, entry: ctk.CTkEntry, game: str) -> None:
        selected_path = filedialog.askdirectory(initialdir=entry.get() or None)
        if not selected_path:
            return
        entry.delete(0, "end")
        entry.insert(0, selected_path)
        self.save_path(entry, game)

    def validate_path_entry(self, game: str) -> str:
        entry = self.ams2_path_entry if game == "AMS2" else self.iracing_path_entry
        label = self.ams2_warning_label if game == "AMS2" else self.iracing_warning_label
        warning = self._directory_warning(game, entry.get())
        label.configure(text=warning)
        return warning

    @staticmethod
    def _directory_warning(game: str, path_value: str) -> str:
        path_text = str(path_value or "").strip()
        if not path_text:
            return f"Select your {game} folder."

        root = Path(path_text)
        if not root.exists() or not root.is_dir():
            return "Folder does not exist."

        if game == "iRacing":
            if any(not (root / name).is_dir() for name in ("airosters", "aiseasons")):
                return "Folder does not seem to be correct. Please verify before moving forward."
            return ""

        if not (root / "UserData").is_dir():
            return "Folder does not seem to be correct. Please verify before moving forward."
        return ""

    def open_ownership(self, game: str) -> None:
        ownership_screen = self.parent.screens["OwnershipScreen"]
        if hasattr(ownership_screen, "set_game"):
            ownership_screen.set_game(game)
        self.show_screen("OwnershipScreen")

    def go_back(self) -> None:
        if hasattr(self.parent, "return_from_settings"):
            self.parent.return_from_settings()
            return
        self.show_screen("MenuScreen")

    def save_overlay_enabled(self) -> None:
        update_custom_overlay_enabled(bool(self.overlay_enabled_var.get()))
        state = "enabled" if self.overlay_enabled_var.get() else "disabled"
        self.status_label.configure(text=f"Experimental custom overlays {state}.")

    def save_update_check_enabled(self) -> None:
        update_check_for_updates_on_launch(bool(self.update_check_var.get()))
        state = "enabled" if self.update_check_var.get() else "disabled"
        self.status_label.configure(text=f"Launch update checks {state}.")

    def check_for_updates_now(self) -> None:
        if hasattr(self.parent, "run_update_check"):
            self.status_label.configure(text="Checking GitHub for updates...")
            self.parent.run_update_check(manual=True)
        else:
            self.status_label.configure(text="Update checker is not available.")

    def open_overlay_editor(self) -> None:
        OverlayLayoutEditor(self, self._overlay_geometry_saved)

    def _overlay_geometry_saved(self, geometry: str) -> None:
        self.overlay_geometry_label.configure(text=f"AMS2 leaderboard: {geometry}")
        manual_results = self.parent.screens.get("ManualResultsScreen") if hasattr(self.parent, "screens") else None
        overlay = getattr(manual_results, "ams2_leaderboard_overlay", None)
        if overlay is not None and hasattr(overlay, "apply_geometry"):
            overlay.apply_geometry(geometry)
        self.status_label.configure(text="Overlay position saved.")
