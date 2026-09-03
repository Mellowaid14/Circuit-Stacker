from __future__ import annotations

import re
import threading
import time
from datetime import datetime
from tkinter import filedialog

import customtkinter as ctk

from ..ams2_name_mappings import (
    load_ams2_player_name_mappings,
    load_iracing_player_name_mappings,
    save_ams2_player_name_mappings,
    save_iracing_player_name_mappings,
)
from ..ams2_shared_memory import ams2_timing_by_name, ams2_timing_by_position, read_ams2_live_snapshot
from ..driver_pool import driver_profile_map
from ..game_adapters import get_game_adapter
from ..game_logic import ResultsImportMappingRequired, apply_finish_order, simulate_race
from ..iracing_telemetry import read_iracing_live_snapshot
from ..qt_leaderboard_overlay import QtAms2LeaderboardOverlay, pyside6_available
from ..settings_manager import game_directory, load_settings
from .manual_setup_screen import build_manual_setup_content


AMS2_LIVE_ORDER_REFRESH_MS = 3000
AMS2_SESSION_QUALIFY = 3
AMS2_SESSION_RACE = 5
IRACING_SESSION_QUALIFY_TEXT = "qual"
IRACING_SESSION_RACE_TEXT = "race"
_AMS2_LOGO_PATH_CACHE: dict[str, str] | None = None
_AMS2_LOGO_ALIASES = {
    "caterhamacademy": "caterhamacademy",
    "ginettag40cup": "ginettag40cup",
    "ginettag40": "ginettag40cup",
    "gt5": "gt5",
    "ginettagt5": "ginettagt5",
    "p4": "prototype1",
    "mcrs2000": "prototype1",
    "metalmoromrxduratecp4": "prototype1",
}


class ResultsMappingDialog(ctk.CTkToplevel):
    def __init__(self, parent, app_names: list[str], imported_names: list[str], on_confirm) -> None:
        super().__init__(parent)
        self.title("Map Imported Drivers")
        self.geometry("540x420")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._on_confirm = on_confirm
        self._app_names = app_names
        self._imported_names = imported_names
        self._variables: dict[str, ctk.StringVar] = {}

        ctk.CTkLabel(self, text="Match Imported Driver Names", font=ctk.CTkFont(size=20, weight="bold")).pack(
            pady=(20, 8)
        )
        ctk.CTkLabel(
            self,
            text="Pick which imported name belongs to each championship driver before applying the results.",
            text_color="gray",
            wraplength=460,
            justify="center",
        ).pack(pady=(0, 14))

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=(0, 14))

        for app_name in app_names:
            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", pady=6)
            ctk.CTkLabel(row, text=app_name, width=190, anchor="w", font=ctk.CTkFont(size=12, weight="bold")).pack(
                side="left", padx=(0, 10)
            )
            variable = ctk.StringVar(value=imported_names[0] if imported_names else "")
            self._variables[app_name] = variable
            ctk.CTkOptionMenu(row, values=imported_names, variable=variable, width=250).pack(side="left")

        self.status_label = ctk.CTkLabel(self, text="", text_color="#ff7777", font=ctk.CTkFont(size=11))
        self.status_label.pack(pady=(0, 10))

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(pady=(0, 16))
        ctk.CTkButton(actions, text="Apply Mapping", command=self._submit, width=140, height=34).pack(side="left")
        ctk.CTkButton(
            actions,
            text="Cancel",
            command=self.destroy,
            width=100,
            height=34,
            fg_color="gray30",
            hover_color="gray40",
        ).pack(side="left", padx=(10, 0))

    def _submit(self) -> None:
        selected = {app_name: variable.get().strip() for app_name, variable in self._variables.items()}
        chosen_values = [value for value in selected.values() if value]
        if len(chosen_values) != len(self._app_names):
            self.status_label.configure(text="Choose an imported driver for each championship driver.")
            return
        if len(set(chosen_values)) != len(chosen_values):
            self.status_label.configure(text="Each imported driver can only be used once.")
            return

        self.destroy()
        self._on_confirm({imported_name: app_name for app_name, imported_name in selected.items()})


class RaceSetupPopup(ctk.CTkToplevel):
    def __init__(self, parent, gameplay_screen) -> None:
        super().__init__(parent)
        self.title("Race Setup")
        self.geometry("820x720")
        self.minsize(720, 560)
        self.transient(parent)
        self.gameplay_screen = gameplay_screen

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(16, 8))
        self.title_label = ctk.CTkLabel(top, text="Race Setup", font=ctk.CTkFont(size=22, weight="bold"))
        self.title_label.pack(side="left")
        ctk.CTkButton(
            top,
            text="Close",
            command=self.destroy,
            width=90,
            height=30,
            fg_color="gray30",
            hover_color="gray40",
        ).pack(side="right")

        self.subtitle_label = ctk.CTkLabel(self, text="", text_color="gray", font=ctk.CTkFont(size=12))
        self.subtitle_label.pack(anchor="w", padx=18, pady=(0, 8))

        content = ctk.CTkScrollableFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        build_manual_setup_content(content, gameplay_screen, title_label=self.title_label, subtitle_label=self.subtitle_label)
        self.focus()


class Ams2EventsLogPopup(ctk.CTkToplevel):
    def __init__(self, parent, events: list[str], game_label: str = "Live") -> None:
        super().__init__(parent)
        self.title(f"{game_label} Events Log")
        self.geometry("900x620")
        self.minsize(720, 460)
        self.transient(parent)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(16, 8))
        ctk.CTkLabel(top, text=f"{game_label} Events Log", font=ctk.CTkFont(size=22, weight="bold")).pack(side="left")
        ctk.CTkButton(
            top,
            text="Close",
            command=self.destroy,
            width=90,
            height=30,
            fg_color="gray30",
            hover_color="gray40",
        ).pack(side="right")

        ctk.CTkLabel(
            self,
            text="Live order changes from the current Enter Race session.",
            text_color="gray",
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w", padx=18, pady=(0, 8))

        box = ctk.CTkFrame(self, fg_color=("gray90", "gray15"), corner_radius=12)
        box.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        events_frame = ctk.CTkScrollableFrame(box, fg_color="transparent")
        events_frame.pack(fill="both", expand=True, padx=12, pady=12)

        if not events:
            ctk.CTkLabel(events_frame, text="No live order changes logged yet.", text_color="gray").pack(pady=24)
        else:
            for event in reversed(events):
                row = ctk.CTkFrame(events_frame, fg_color=("gray82", "gray20"), corner_radius=8)
                row.pack(fill="x", pady=4)
                ctk.CTkLabel(row, text=event, anchor="w", justify="left", wraplength=820).pack(
                    fill="x", padx=12, pady=8
                )
        self.focus()


def _normalize_logo_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


def _ams2_logo_paths() -> dict[str, str]:
    global _AMS2_LOGO_PATH_CACHE
    if _AMS2_LOGO_PATH_CACHE is not None:
        return dict(_AMS2_LOGO_PATH_CACHE)

    root = game_directory("AMS2")
    logo_dir = f"{root}\\GUI\\MotorsportLogos" if root else ""
    paths: dict[str, str] = {}
    if logo_dir:
        try:
            from pathlib import Path

            for path in Path(logo_dir).glob("*.dds"):
                paths[_normalize_logo_key(path.stem)] = str(path)
        except OSError:
            paths = {}
    _AMS2_LOGO_PATH_CACHE = paths
    return dict(paths)


def _ams2_logo_path_for_label(label: str) -> str:
    key = _normalize_logo_key(label)
    if not key:
        return ""
    paths = _ams2_logo_paths()
    candidate_keys = [key]
    if key in _AMS2_LOGO_ALIASES:
        candidate_keys.insert(0, _AMS2_LOGO_ALIASES[key])
    for candidate_key in candidate_keys:
        if candidate_key in paths:
            return paths[candidate_key]
    for candidate_key in candidate_keys:
        for logo_key, logo_path in paths.items():
            if candidate_key and (candidate_key in logo_key or logo_key in candidate_key):
                return logo_path
    return ""


def _format_lap_time(seconds: float) -> str:
    if seconds <= 0:
        return "--"
    minutes = int(seconds // 60)
    remaining = seconds - (minutes * 60)
    return f"{minutes}:{remaining:06.3f}"


class ManualResultsScreen(ctk.CTkFrame):
    def __init__(self, parent, show_screen) -> None:
        super().__init__(parent, fg_color="transparent")
        self.parent = parent
        self.show_screen = show_screen
        self.gameplay_screen = None
        self.finish_order: list[str] = []
        self.class_finish_orders: dict[str, list[str]] = {}
        self.selected_class = ""
        self.selected_index = 0
        self.pending_import_path: str | None = None
        self.ams2_sync_request_id = 0
        self.ams2_live_order_after_id: str | None = None
        self.ams2_events_log: list[str] = []
        self.ams2_last_order_snapshot: dict[str, list[str]] = {}
        self.ams2_player_name_mappings = load_ams2_player_name_mappings()
        self.iracing_player_name_mappings = load_iracing_player_name_mappings()
        self.live_session_timer_key: tuple[int, int, int] | None = None
        self.live_session_timer_started_at: float | None = None
        self.live_session_timer_expired_key: tuple[int, int, int] | None = None
        self.ams2_player_dropdown_vars: dict[str, ctk.StringVar] = {}
        self.ams2_live_participant_names: list[str] = []
        self.ams2_ai_name_mappings: dict[str, str] = {}
        self.ams2_qualifying_order: list[str] = []
        self.ams2_qualifying_order_locked = False
        self.ams2_last_session_state: int | None = None
        self.ams2_leaderboard_overlay = None
        self.order_class_headers: dict[str, ctk.CTkFrame] = {}
        self.order_row_widgets: dict[tuple[str, str], dict[str, object]] = {}
        self.order_drag_source: tuple[str, str] | None = None
        self.order_drag_target_index: int | None = None
        self.ams2_assignment_skill_cache: dict[str, float] = {}

        ctk.CTkLabel(self, text="Current Race", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(24, 6))
        self.subtitle_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=13), text_color="gray")
        self.subtitle_label.pack(pady=(0, 16))

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        content.grid_columnconfigure(0, weight=2)
        content.grid_columnconfigure(1, weight=1)
        content.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(content, fg_color=("gray90", "gray15"), corner_radius=12)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        ctk.CTkLabel(
            left,
            text="Finish Order",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=("#1a6fc4", "#4da6ff"),
        ).pack(anchor="w", padx=14, pady=(12, 8))
        self.order_frame = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self.order_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        right = ctk.CTkFrame(content, fg_color=("gray90", "gray15"), corner_radius=12)
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        right.grid_rowconfigure(3, weight=1)
        ctk.CTkButton(
            right,
            text="Race Setup",
            command=self.open_race_setup_popup,
            width=170,
            height=34,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(anchor="w", padx=14, pady=(12, 10))
        ctk.CTkLabel(
            right,
            text="Controls",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=("#1a6fc4", "#4da6ff"),
        ).pack(anchor="w", padx=14, pady=(0, 8))
        self.selection_label = ctk.CTkLabel(right, text="Selected: none", font=ctk.CTkFont(size=12))
        self.selection_label.pack(anchor="w", padx=14, pady=(0, 12))

        ctk.CTkButton(right, text="Move Up", command=self.move_up, width=150, height=34).pack(
            anchor="w", padx=14, pady=4
        )
        ctk.CTkButton(right, text="Move Down", command=self.move_down, width=150, height=34).pack(
            anchor="w", padx=14, pady=4
        )
        ctk.CTkLabel(
            right,
            text="Tip: sort each class in finishing order. Multiclass rating and points are class-based.",
            justify="left",
            wraplength=240,
            text_color="gray",
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w", padx=14, pady=(14, 0))

        self.ams2_sync_frame = ctk.CTkFrame(right, fg_color=("gray85", "gray20"), corner_radius=8)
        self.ams2_sync_header = ctk.CTkFrame(self.ams2_sync_frame, fg_color="transparent")
        self.ams2_sync_header.pack(fill="x", padx=10, pady=(10, 4))
        self.ams2_sync_light = ctk.CTkFrame(self.ams2_sync_header, width=14, height=14, corner_radius=7, fg_color="gray45")
        self.ams2_sync_light.pack(side="left", padx=(0, 8))
        self.ams2_sync_light.pack_propagate(False)
        ctk.CTkLabel(
            self.ams2_sync_header,
            text="Live Sync",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        ).pack(side="left")
        ctk.CTkButton(
            self.ams2_sync_header,
            text="Refresh",
            command=self.refresh_ams2_sync,
            width=70,
            height=24,
            font=ctk.CTkFont(size=10),
            fg_color="gray30",
            hover_color="gray40",
        ).pack(side="right")
        self.ams2_sync_label = ctk.CTkLabel(
            self.ams2_sync_frame,
            text="Checking live session...",
            height=24,
            anchor="w",
            font=ctk.CTkFont(size=11),
        )
        self.ams2_sync_label.pack(fill="x", padx=10, pady=(0, 10))
        self.ams2_events_button = ctk.CTkButton(
            self.ams2_sync_frame,
            text="View Events Log",
            command=self.open_ams2_events_log,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color="gray30",
            hover_color="gray40",
        )
        self.ams2_events_button.pack(fill="x", padx=10, pady=(0, 10))
        self.ams2_leaderboard_button = ctk.CTkButton(
            self.ams2_sync_frame,
            text="Leaderboard Overlay",
            command=self.open_ams2_leaderboard_overlay,
            height=28,
            font=ctk.CTkFont(size=11),
        )
        self.ams2_leaderboard_button.pack(fill="x", padx=10, pady=(0, 10))
        self.ams2_player_mapping_frame = ctk.CTkFrame(self.ams2_sync_frame, fg_color="transparent")
        self.ams2_player_mapping_frame.pack(fill="x", padx=10, pady=(0, 10))

        bottom_controls = ctk.CTkFrame(right, fg_color="transparent")
        bottom_controls.pack(side="bottom", fill="x", padx=14, pady=14)
        self.simulate_button = ctk.CTkButton(
            bottom_controls,
            text="Simulate Results",
            command=self.simulate_results,
            width=170,
            height=34,
        )
        self.simulate_button.pack(anchor="w", pady=(0, 8))
        self.import_button = ctk.CTkButton(
            bottom_controls,
            text="Import iRacing Results JSON",
            command=self.import_results_json,
            width=220,
            height=34,
        )
        self.import_button.pack(anchor="w")

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(pady=(0, 12))
        ctk.CTkButton(
            bottom,
            text="Save Race Result",
            command=self.save_results,
            height=36,
            width=160,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left")
        ctk.CTkButton(
            bottom,
            text="<- Back",
            command=self.go_back,
            height=36,
            width=120,
            font=ctk.CTkFont(size=12),
            fg_color="gray30",
            hover_color="gray40",
        ).pack(side="left", padx=(10, 0))

        self.status_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=11), text_color="#ff7777")
        self.status_label.pack(pady=(0, 6))

    def set_gameplay_screen(self, gameplay_screen) -> None:
        self.gameplay_screen = gameplay_screen

    def on_show(self) -> None:
        if self.gameplay_screen is None:
            self.stop_ams2_live_order_updates()
            self._hide_ams2_sync()
            return
        if hasattr(self.gameplay_screen, "reload_active_rivals_state"):
            self.gameplay_screen.reload_active_rivals_state()
        if self.gameplay_screen.current_race >= len(self.gameplay_screen.schedule):
            self.stop_ams2_live_order_updates()
            self.finish_order = []
            self.class_finish_orders = {}
            self.selected_class = ""
            self.subtitle_label.configure(text="Season finished")
            self.render_order()
            self._hide_ams2_sync()
            return

        race = self.gameplay_screen.schedule[self.gameplay_screen.current_race]
        adapter = get_game_adapter(getattr(self.gameplay_screen, "game", "iRacing"))
        self.subtitle_label.configure(text=f"Round {race['race_num']} - {race['track']} - {race['layout']}")
        self.import_button.configure(
            text=adapter.import_button_text,
            state="normal" if adapter.supports_results_import else "disabled",
        )
        self.class_finish_orders = self._build_class_finish_orders()
        self.selected_class = next(iter(self.class_finish_orders), "")
        self.finish_order = self._combined_finish_order()
        self.selected_index = 0
        self.status_label.configure(text="")
        self.ams2_events_log = []
        self.ams2_last_order_snapshot = {class_name: order[:] for class_name, order in self.class_finish_orders.items()}
        self.ams2_ai_name_mappings = {}
        self.ams2_qualifying_order = []
        self.ams2_qualifying_order_locked = False
        self.ams2_last_session_state = None
        self.ams2_assignment_skill_cache = {}
        self._refresh_ams2_player_mapping_ui()
        self.render_order()
        self.refresh_ams2_sync()
        self.start_ams2_live_order_updates()

    def on_hide(self) -> None:
        if self._leaderboard_overlay_exists():
            self.ams2_leaderboard_overlay.close()

    def _build_class_finish_orders(self) -> dict[str, list[str]]:
        if self.gameplay_screen is None:
            return {}

        grouped: dict[str, list[str]] = {}
        for driver in sorted(
            self.gameplay_screen.standings,
            key=lambda row: (str(row.get("class_name", "Overall")), str(row.get("name", ""))),
        ):
            class_name = str(driver.get("class_name", "")).strip() or "Overall"
            grouped.setdefault(class_name, []).append(str(driver.get("name", "")))
        return grouped

    def _combined_finish_order(self) -> list[str]:
        combined: list[str] = []
        for class_order in self.class_finish_orders.values():
            combined.extend(class_order)
        return combined

    def render_order(self) -> None:
        for widget in self.order_frame.winfo_children():
            widget.destroy()
        self.order_class_headers = {}
        self.order_row_widgets = {}
        self._clear_order_drag_visual()

        if not self.class_finish_orders:
            ctk.CTkLabel(self.order_frame, text="No race to edit.", text_color="gray").pack(pady=20)
            self.selection_label.configure(text="Selected: none")
            return

        if self.selected_class not in self.class_finish_orders:
            self.selected_class = next(iter(self.class_finish_orders), "")
        current_order = self.class_finish_orders.get(self.selected_class, [])
        self.selected_index = max(0, min(self.selected_index, len(current_order) - 1))
        selected_name = current_order[self.selected_index] if current_order else "none"
        self.selection_label.configure(
            text=f"Selected: {selected_name} ({self.selected_class})"
            if self.selected_class
            else f"Selected: {selected_name}"
        )

        player_set = set(self.gameplay_screen.player_names if self.gameplay_screen else [])
        for class_name, class_order in self.class_finish_orders.items():
            class_header = ctk.CTkFrame(self.order_frame, fg_color="transparent")
            class_header.pack(fill="x", pady=(8, 2))
            ctk.CTkLabel(
                class_header,
                text=f"{class_name} Class",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=("#1a6fc4", "#4da6ff"),
                anchor="w",
            ).pack(side="left", padx=4)
            self.order_class_headers[class_name] = class_header

            for index, driver_name in enumerate(class_order):
                is_selected = class_name == self.selected_class and index == self.selected_index
                is_player = driver_name in player_set
                row = ctk.CTkFrame(
                    self.order_frame,
                    fg_color="transparent",
                    corner_radius=6,
                )
                self._configure_order_row_style(row, is_selected=is_selected, is_player=is_player)
                row.pack(fill="x", pady=2)
                position_button = ctk.CTkButton(
                    row,
                    text=f"P{index + 1}",
                    width=50,
                    height=30,
                    command=lambda group=class_name, value=index: self.select_index(value, group),
                    font=ctk.CTkFont(size=11, weight="bold"),
                )
                position_button.pack(side="left", padx=(6, 8), pady=6)
                name_label = ctk.CTkLabel(row, text=driver_name, font=ctk.CTkFont(size=11), anchor="w")
                name_label.pack(
                    side="left", padx=4, pady=6
                )
                self._bind_order_row_drag(row, name_label, class_name, driver_name)
                up_button = ctk.CTkButton(
                    row,
                    text="^",
                    width=28,
                    height=28,
                    command=lambda group=class_name, value=index: self.move_index_up(value, group),
                    font=ctk.CTkFont(size=10, weight="bold"),
                )
                up_button.pack(side="right", padx=(2, 6), pady=4)
                down_button = ctk.CTkButton(
                    row,
                    text="v",
                    width=28,
                    height=28,
                    command=lambda group=class_name, value=index: self.move_index_down(value, group),
                    font=ctk.CTkFont(size=10, weight="bold"),
                )
                down_button.pack(side="right", padx=2, pady=4)
                self.order_row_widgets[(class_name, driver_name)] = {
                    "row": row,
                    "position_button": position_button,
                    "name_label": name_label,
                    "up_button": up_button,
                    "down_button": down_button,
                }

    def refresh_order_rows(self) -> None:
        if not self.class_finish_orders or not self.order_row_widgets:
            self.render_order()
            return

        if self.selected_class not in self.class_finish_orders:
            self.selected_class = next(iter(self.class_finish_orders), "")
        current_order = self.class_finish_orders.get(self.selected_class, [])
        self.selected_index = max(0, min(self.selected_index, len(current_order) - 1))
        selected_name = current_order[self.selected_index] if current_order else "none"
        self.selection_label.configure(
            text=f"Selected: {selected_name} ({self.selected_class})"
            if self.selected_class
            else f"Selected: {selected_name}"
        )

        player_set = set(self.gameplay_screen.player_names if self.gameplay_screen else [])
        for widget in self.order_frame.winfo_children():
            widget.pack_forget()

        for class_name, class_order in self.class_finish_orders.items():
            header = self.order_class_headers.get(class_name)
            if header is None:
                self.render_order()
                return
            header.pack(fill="x", pady=(8, 2))
            for index, driver_name in enumerate(class_order):
                widgets = self.order_row_widgets.get((class_name, driver_name))
                if widgets is None:
                    self.render_order()
                    return
                row = widgets["row"]
                position_button = widgets["position_button"]
                up_button = widgets["up_button"]
                down_button = widgets["down_button"]
                is_selected = class_name == self.selected_class and index == self.selected_index
                is_player = driver_name in player_set
                self._configure_order_row_style(
                    row,
                    is_selected=is_selected,
                    is_player=is_player,
                    is_drag_source=self.order_drag_source == (class_name, driver_name),
                    is_drop_target=(
                        self.order_drag_source is not None
                        and self.order_drag_source[0] == class_name
                        and self.order_drag_target_index == index
                    ),
                )
                position_button.configure(
                    text=f"P{index + 1}",
                    command=lambda group=class_name, value=index: self.select_index(value, group),
                )
                up_button.configure(command=lambda group=class_name, value=index: self.move_index_up(value, group))
                down_button.configure(command=lambda group=class_name, value=index: self.move_index_down(value, group))
                row.pack(fill="x", pady=2)

    def _bind_order_row_drag(self, row, name_label, class_name: str, driver_name: str) -> None:
        self._set_widget_cursor(row, "hand2")
        self._set_widget_cursor(name_label, "hand2")
        for widget in (row, name_label):
            widget.bind("<ButtonPress-1>", lambda _event, group=class_name, name=driver_name: self._start_order_drag(group, name))
            widget.bind("<B1-Motion>", self._update_order_drag_visual)
            widget.bind("<ButtonRelease-1>", self._finish_order_drag)

    def _start_order_drag(self, class_name: str, driver_name: str) -> None:
        self.order_drag_source = (class_name, driver_name)
        self.order_drag_target_index = None
        self._set_drag_row_cursor(class_name, driver_name, "fleur")
        self._apply_order_drag_visual()

    def _update_order_drag_visual(self, event) -> None:
        if self.order_drag_source is None:
            return
        class_name, _driver_name = self.order_drag_source
        next_target = self._drag_target_index(class_name, int(getattr(event, "y_root", 0) or 0))
        if next_target == self.order_drag_target_index:
            return
        previous_target = self.order_drag_target_index
        self.order_drag_target_index = next_target
        self._restore_order_target_style(class_name, previous_target)
        self._apply_order_drag_visual()

    def _finish_order_drag(self, event) -> None:
        if self.order_drag_source is None:
            return
        class_name, driver_name = self.order_drag_source
        class_order = self.class_finish_orders.get(class_name, [])
        if driver_name not in class_order:
            self._clear_order_drag_visual()
            return

        target_index = self._drag_target_index(class_name, int(getattr(event, "y_root", 0) or 0))
        current_index = class_order.index(driver_name)
        if target_index == current_index:
            self._clear_order_drag_visual()
            self.select_index(current_index, class_name)
            return

        class_order.pop(current_index)
        if target_index > current_index:
            target_index -= 1
        target_index = max(0, min(target_index, len(class_order)))
        class_order.insert(target_index, driver_name)
        self.selected_class = class_name
        self.selected_index = target_index
        self.finish_order = self._combined_finish_order()
        self._clear_order_drag_visual()
        self.refresh_order_rows()

    def _drag_target_index(self, class_name: str, y_root: int) -> int:
        class_order = self.class_finish_orders.get(class_name, [])
        for index, driver_name in enumerate(class_order):
            widgets = self.order_row_widgets.get((class_name, driver_name))
            if not widgets:
                continue
            row = widgets["row"]
            row_top = row.winfo_rooty()
            row_midpoint = row_top + (row.winfo_height() / 2)
            if y_root < row_midpoint:
                return index
        return len(class_order)

    def _clear_order_drag_visual(self) -> None:
        source = self.order_drag_source
        target_class = source[0] if source else ""
        target_index = self.order_drag_target_index
        self.order_drag_source = None
        self.order_drag_target_index = None
        if source is not None:
            self._set_drag_row_cursor(source[0], source[1], "hand2")
            self._restore_order_row_style(source[0], source[1])
        self._restore_order_target_style(target_class, target_index)

    def _apply_order_drag_visual(self) -> None:
        if self.order_drag_source is None:
            return
        class_name, driver_name = self.order_drag_source
        source_widgets = self.order_row_widgets.get((class_name, driver_name))
        if source_widgets:
            self._configure_order_row_style(
                source_widgets["row"],
                is_selected=False,
                is_player=False,
                is_drag_source=True,
            )
        self._restore_order_target_style(class_name, self.order_drag_target_index, as_drop_target=True)

    def _restore_order_target_style(self, class_name: str, index: int | None, *, as_drop_target: bool = False) -> None:
        if index is None or not class_name:
            return
        class_order = self.class_finish_orders.get(class_name, [])
        if index < 0 or index >= len(class_order):
            return
        driver_name = class_order[index]
        if self.order_drag_source == (class_name, driver_name):
            return
        widgets = self.order_row_widgets.get((class_name, driver_name))
        if not widgets:
            return
        if as_drop_target:
            self._configure_order_row_style(
                widgets["row"],
                is_selected=False,
                is_player=False,
                is_drop_target=True,
            )
            return
        self._restore_order_row_style(class_name, driver_name)

    def _restore_order_row_style(self, class_name: str, driver_name: str) -> None:
        widgets = self.order_row_widgets.get((class_name, driver_name))
        if not widgets:
            return
        class_order = self.class_finish_orders.get(class_name, [])
        try:
            index = class_order.index(driver_name)
        except ValueError:
            index = -1
        player_set = set(self.gameplay_screen.player_names if self.gameplay_screen else [])
        self._configure_order_row_style(
            widgets["row"],
            is_selected=class_name == self.selected_class and index == self.selected_index,
            is_player=driver_name in player_set,
        )

    def _configure_order_row_style(
        self,
        row,
        *,
        is_selected: bool,
        is_player: bool,
        is_drag_source: bool = False,
        is_drop_target: bool = False,
    ) -> None:
        if is_drag_source:
            row.configure(fg_color=("#b7d7f2", "#24435a"), border_width=2, border_color="#4da6ff")
            return
        if is_drop_target:
            row.configure(fg_color=("#fff2ba", "#5c4a18"), border_width=2, border_color="#ffcf4a")
            return
        row.configure(
            fg_color=("#ddeeff", "#1a3a55")
            if is_selected
            else (("#d7f0df", "#183324") if is_player else ("gray80", "gray22")),
            border_width=0,
        )

    def _set_drag_row_cursor(self, class_name: str, driver_name: str, cursor: str) -> None:
        widgets = self.order_row_widgets.get((class_name, driver_name))
        if not widgets:
            return
        for widget_key in ("row", "name_label"):
            self._set_widget_cursor(widgets.get(widget_key), cursor)

    @staticmethod
    def _set_widget_cursor(widget, cursor: str) -> None:
        try:
            widget.configure(cursor=cursor)
        except Exception:
            try:
                widget._canvas.configure(cursor=cursor)
            except Exception:
                pass

    def refresh_ams2_sync(self) -> None:
        if self.gameplay_screen is None:
            self._hide_ams2_sync()
            return
        game = self._current_game_key()
        if game not in {"ams2", "iracing"}:
            self._hide_ams2_sync()
            self.stop_ams2_live_order_updates()
            return

        self._show_ams2_sync()
        expected_names = [
            str(driver.get("name", "")).strip()
            for driver in getattr(self.gameplay_screen, "standings", [])
            if str(driver.get("name", "")).strip()
        ]
        self.ams2_sync_request_id += 1
        request_id = self.ams2_sync_request_id
        self.ams2_sync_light.configure(fg_color="gray45")
        self.ams2_sync_label.configure(
            text=f"{self._current_game_label()} Sync: checking...",
            text_color="gray",
        )
        threading.Thread(
            target=self._check_live_sync_in_background,
            args=(expected_names, request_id, game),
            daemon=True,
        ).start()

    def _check_live_sync_in_background(self, expected_names: list[str], request_id: int, game: str) -> None:
        if game == "ams2":
            snapshot, error = read_ams2_live_snapshot()
            status = self._live_sync_status_from_participants("AMS2", expected_names, snapshot.participants, error, snapshot.session_name)
        else:
            snapshot, error = read_iracing_live_snapshot()
            standby = self._is_iracing_standby_state(snapshot, error)
            if standby and not snapshot.participants:
                status = type(
                    "LiveSyncStatus",
                    (),
                    {
                        "available": True,
                        "all_found": False,
                        "summary": "iRacing Sync: waiting for live drivers",
                        "message": (
                            "iRacing telemetry detected: Yes\n"
                            f"Session: {snapshot.session_name}\n"
                            "Live positions are temporarily unavailable while iRacing changes sessions."
                        ),
                    },
                )()
            else:
                status = self._live_sync_status_from_participants("iRacing", expected_names, snapshot.participants, error, snapshot.session_name)
        self.after(0, lambda: self._apply_ams2_sync_status(status, request_id))

    def _live_sync_status_from_participants(self, game_label: str, expected_names: list[str], participants, error: str, session_name: str = ""):
        expected = [name for name in expected_names if str(name).strip()]
        mapped_names, unexpected_live_names = self._mapped_app_names_for_sync(participants)
        found = [name for name in expected if self._normalize_driver_name(name) in mapped_names]
        missing = [name for name in expected if self._normalize_driver_name(name) not in mapped_names]
        has_participants = bool(participants)
        all_found = has_participants and bool(expected) and not missing and not unexpected_live_names
        if all_found:
            summary = f"{game_label} Sync: ready"
        elif has_participants and missing:
            summary = f"{game_label} Sync: missing drivers"
        elif has_participants and unexpected_live_names:
            summary = f"{game_label} Sync: roster mismatch"
        elif has_participants:
            summary = f"{game_label} Sync: no expected drivers"
        else:
            summary = f"{game_label} Sync: no live drivers"
        detected_label = "shared memory" if game_label == "AMS2" else "telemetry"
        message = (
            f"{game_label} {detected_label} detected: {'Yes' if has_participants else 'No'}\n"
            f"Session: {session_name or '-'}\n"
            f"Drivers found: {len(found)} / {len(expected)}\n"
            f"Missing: {self._format_missing_names(missing)}\n"
            f"Unexpected live drivers: {self._format_missing_names(unexpected_live_names)}"
        )
        if error and not has_participants:
            message = f"{message}\nLast error: {error}"
        return type(
            "LiveSyncStatus",
            (),
            {
                "available": has_participants,
                "all_found": all_found,
                "summary": summary,
                "message": message,
            },
        )()

    def _mapped_app_names_for_sync(self, participants) -> tuple[set[str], list[str]]:
        live_name_map: dict[str, str] = {}
        for participant in participants:
            live_name = str(getattr(participant, "name", "")).strip()
            normalized_live_name = self._normalize_driver_name(live_name)
            if normalized_live_name:
                live_name_map.setdefault(normalized_live_name, live_name)
        live_names = set(live_name_map)
        mapped_app_names: set[str] = set()
        accounted_live_names: set[str] = set()
        for app_player, screen_name in self._current_player_name_mappings().items():
            normalized_screen_name = self._normalize_driver_name(screen_name)
            if normalized_screen_name in live_names:
                mapped_app_names.add(self._normalize_driver_name(app_player))
                accounted_live_names.add(normalized_screen_name)
        for driver in getattr(self.gameplay_screen, "standings", []) if self.gameplay_screen is not None else []:
            app_name = str(driver.get("name", "")).strip()
            normalized_app_name = self._normalize_driver_name(app_name)
            if normalized_app_name and normalized_app_name in live_names:
                mapped_app_names.add(normalized_app_name)
                accounted_live_names.add(normalized_app_name)
        for live_key, app_name in self.ams2_ai_name_mappings.items():
            normalized_live_key = self._normalize_driver_name(live_key)
            if normalized_live_key in live_names:
                mapped_app_names.add(self._normalize_driver_name(app_name))
                accounted_live_names.add(normalized_live_key)
        unexpected_live_names = [
            live_name_map[key]
            for key in sorted(live_names - accounted_live_names)
        ]
        return mapped_app_names, unexpected_live_names

    def _apply_ams2_sync_status(self, status, request_id: int) -> None:
        if request_id != self.ams2_sync_request_id:
            return
        color = "#36b66b" if status.available and status.all_found else "#d85a5a"
        self.ams2_sync_light.configure(fg_color=color)
        summary = getattr(status, "summary", "") or (
            f"{self._current_game_label()} Sync: ready"
            if status.available and status.all_found
            else f"{self._current_game_label()} Sync: missing drivers"
        )
        self.ams2_sync_label.configure(text=summary, text_color=color)
        self._log_ams2_event(status.message)

    def _show_ams2_sync(self) -> None:
        if not self.ams2_sync_frame.winfo_ismapped():
            self.ams2_sync_frame.pack(fill="x", padx=14, pady=(14, 0))
        if hasattr(self, "ams2_leaderboard_button"):
            overlays_enabled = self._custom_overlays_enabled()
            if self._current_game_key() == "ams2" and overlays_enabled:
                self.ams2_leaderboard_button.configure(state="normal", text="Leaderboard Overlay")
            elif self._current_game_key() == "ams2":
                self.ams2_leaderboard_button.configure(state="disabled", text="Overlay Disabled")
            else:
                self.ams2_leaderboard_button.configure(state="disabled", text="AMS2 Overlay")

    def _hide_ams2_sync(self) -> None:
        if self.ams2_sync_frame.winfo_ismapped():
            self.ams2_sync_frame.pack_forget()

    def start_ams2_live_order_updates(self) -> None:
        self.stop_ams2_live_order_updates()
        if self._should_use_ams2_live_order():
            self._poll_ams2_live_order()

    def stop_ams2_live_order_updates(self) -> None:
        if self.ams2_live_order_after_id is not None:
            try:
                self.after_cancel(self.ams2_live_order_after_id)
            except Exception:
                pass
            self.ams2_live_order_after_id = None

    def _should_use_ams2_live_order(self) -> bool:
        if self.gameplay_screen is None or not self.class_finish_orders:
            return False
        return self._current_game_key() in {"ams2", "iracing"}

    def _poll_ams2_live_order(self) -> None:
        if not self._should_use_ams2_live_order():
            self.stop_ams2_live_order_updates()
            return

        if self._current_game_key() == "ams2":
            snapshot, error = read_ams2_live_snapshot()
        else:
            snapshot, error = read_iracing_live_snapshot()
        if snapshot.participants:
            self._maybe_auto_open_ams2_leaderboard_overlay()
            if self._should_use_qualifying_ai_mapping():
                self._update_live_session_tracking(snapshot)
            participant_names = [participant.name for participant in snapshot.participants if participant.name]
            if participant_names != self.ams2_live_participant_names:
                self.ams2_live_participant_names = participant_names
                self._refresh_ams2_player_mapping_ui()
            updated = self._apply_ams2_live_order(snapshot.participants)
            self._update_qt_leaderboard_overlay(snapshot)
            self.ams2_sync_light.configure(fg_color="#36b66b")
            self.ams2_sync_label.configure(
                text=f"{snapshot.session_name}: {'updated' if updated else 'synced'}",
                text_color="#36b66b",
            )
        elif error:
            self._update_qt_leaderboard_overlay(snapshot, error)
            if self._is_iracing_standby_state(snapshot, error):
                self.ams2_sync_light.configure(fg_color="#36b66b")
                self.ams2_sync_label.configure(
                    text="iRacing Sync: connected, waiting for session",
                    text_color="#36b66b",
                )
            else:
                self.ams2_sync_light.configure(fg_color="#d85a5a")
                self.ams2_sync_label.configure(text=f"{self._current_game_label()} Sync: check events log", text_color="#d85a5a")
            self._log_ams2_event(error)

        self.ams2_live_order_after_id = self.after(AMS2_LIVE_ORDER_REFRESH_MS, self._poll_ams2_live_order)

    def _update_live_session_tracking(self, snapshot) -> None:
        session_state = int(getattr(snapshot, "session_state", 0) or 0)
        session_name = str(getattr(snapshot, "session_name", "")).strip().casefold()
        is_qualifying = (
            session_state == AMS2_SESSION_QUALIFY
            if self._current_game_key() == "ams2"
            else IRACING_SESSION_QUALIFY_TEXT in session_name
        )
        is_race = (
            session_state == AMS2_SESSION_RACE
            if self._current_game_key() == "ams2"
            else IRACING_SESSION_RACE_TEXT in session_name
        )
        if is_qualifying:
            self.ams2_qualifying_order = [
                self._normalize_driver_name(participant.name)
                for participant in snapshot.participants
                if participant.name and participant.position > 0
            ]
            self.ams2_qualifying_order_locked = False
        elif is_race and self.ams2_qualifying_order and not self.ams2_qualifying_order_locked:
            self.ams2_qualifying_order_locked = True
            self._log_ams2_event(f"Qualifying order locked for {self._current_game_label()} AI mapping.")
        self.ams2_last_session_state = AMS2_SESSION_RACE if is_race else (AMS2_SESSION_QUALIFY if is_qualifying else session_state)

    def _apply_ams2_live_order(self, participants) -> bool:
        position_by_name = self._mapped_ams2_positions(participants)
        updated_orders: dict[str, list[str]] = {}
        changed = False
        for class_name, class_order in self.class_finish_orders.items():
            matched = [
                driver_name
                for driver_name in class_order
                if self._normalize_driver_name(driver_name) in position_by_name
            ]
            unmatched = [
                driver_name
                for driver_name in class_order
                if self._normalize_driver_name(driver_name) not in position_by_name
            ]
            sorted_order = sorted(
                matched,
                key=lambda driver_name: position_by_name.get(self._normalize_driver_name(driver_name), 9999),
            ) + unmatched
            updated_orders[class_name] = sorted_order
            changed = changed or sorted_order != class_order

        if not changed:
            return False
        changes = self._summarize_order_changes(updated_orders)
        self.class_finish_orders = updated_orders
        self.finish_order = self._combined_finish_order()
        self.ams2_last_order_snapshot = {class_name: order[:] for class_name, order in updated_orders.items()}
        if self.selected_class not in self.class_finish_orders:
            self.selected_class = next(iter(self.class_finish_orders), "")
        self.selected_index = 0
        self.refresh_order_rows()
        self._log_ams2_event(changes or "Live order changed.")
        return True

    def _summarize_order_changes(self, updated_orders: dict[str, list[str]]) -> str:
        changes: list[str] = []
        previous_orders = self.ams2_last_order_snapshot or self.class_finish_orders
        for class_name, new_order in updated_orders.items():
            previous_order = previous_orders.get(class_name, [])
            previous_positions = {driver_name: index + 1 for index, driver_name in enumerate(previous_order)}
            for new_index, driver_name in enumerate(new_order, start=1):
                old_index = previous_positions.get(driver_name)
                if old_index is not None and old_index != new_index:
                    changes.append(f"{driver_name} P{old_index}->P{new_index} ({class_name})")
                if len(changes) >= 5:
                    break
            if len(changes) >= 5:
                break
        if not changes:
            return "Live order changed."
        extra = " ..." if len(changes) >= 5 else ""
        return "Live order update: " + "; ".join(changes) + extra

    def _mapped_ams2_positions(self, participants) -> dict[str, int]:
        participant_positions = {}
        participant_display_names = {}
        for participant in participants:
            if not participant.name or participant.position <= 0:
                continue
            normalized_name = self._normalize_driver_name(participant.name)
            participant_positions[normalized_name] = participant.position
            participant_display_names[normalized_name] = participant.name
        position_by_app_name: dict[str, int] = {}
        mapped_game_names: set[str] = set()

        for app_player, screen_name in self._current_player_name_mappings().items():
            normalized_screen_name = self._normalize_driver_name(screen_name)
            normalized_app_player = self._normalize_driver_name(app_player)
            if normalized_screen_name in participant_positions:
                position_by_app_name[normalized_app_player] = participant_positions[normalized_screen_name]
                mapped_game_names.add(normalized_screen_name)

        all_app_names = [
            str(driver.get("name", "")).strip()
            for driver in getattr(self.gameplay_screen, "standings", [])
            if str(driver.get("name", "")).strip()
        ]
        for app_name in all_app_names:
            normalized_app_name = self._normalize_driver_name(app_name)
            if normalized_app_name in position_by_app_name:
                continue
            if normalized_app_name in participant_positions:
                position_by_app_name[normalized_app_name] = participant_positions[normalized_app_name]
                mapped_game_names.add(normalized_app_name)

        app_player_set = {
            self._normalize_driver_name(name)
            for name in getattr(self.gameplay_screen, "player_names", [])
            if str(name).strip()
        }
        mapped_app_names = set(position_by_app_name)
        if not self._should_use_qualifying_ai_mapping():
            return position_by_app_name

        remaining_ai_names = [
            str(driver.get("name", "")).strip()
            for driver in getattr(self.gameplay_screen, "standings", [])
            if str(driver.get("name", "")).strip()
            and self._normalize_driver_name(str(driver.get("name", ""))) not in app_player_set
            and self._normalize_driver_name(str(driver.get("name", ""))) not in mapped_app_names
        ]
        remaining_game_positions = [
            (screen_name, position)
            for screen_name, position in participant_positions.items()
            if screen_name not in mapped_game_names
        ]
        remaining_ai_names.sort(key=self._ai_assignment_skill_key)

        available_ai_by_normalized_name = {
            self._normalize_driver_name(app_name): app_name
            for app_name in remaining_ai_names
        }
        used_ai_names: set[str] = set()
        for screen_name, position in remaining_game_positions:
            mapped_app_name = self.ams2_ai_name_mappings.get(screen_name)
            normalized_mapped_app = self._normalize_driver_name(mapped_app_name or "")
            if normalized_mapped_app not in available_ai_by_normalized_name:
                continue
            position_by_app_name[normalized_mapped_app] = position
            mapped_game_names.add(screen_name)
            used_ai_names.add(normalized_mapped_app)

        if not self.ams2_ai_name_mappings and self.ams2_last_session_state != AMS2_SESSION_RACE:
            return position_by_app_name

        remaining_game_positions = self._ordered_game_positions_for_ai_mapping(
            [
                (screen_name, position)
                for screen_name, position in remaining_game_positions
                if screen_name not in mapped_game_names
            ]
        )
        assignable_ai_names = [
            app_name
            for app_name in remaining_ai_names
            if self._normalize_driver_name(app_name) not in used_ai_names
        ]
        for app_name, (screen_name, position) in zip(assignable_ai_names, remaining_game_positions):
            self.ams2_ai_name_mappings[screen_name] = app_name
            position_by_app_name[self._normalize_driver_name(app_name)] = position
            display_name = participant_display_names.get(screen_name, screen_name)
            self._log_ams2_event(f"Mapped AMS2 AI '{display_name}' to '{app_name}'.")

        return position_by_app_name

    def _ordered_game_positions_for_ai_mapping(self, game_positions: list[tuple[str, int]]) -> list[tuple[str, int]]:
        if not game_positions:
            return []
        position_by_game_name = dict(game_positions)
        if self.ams2_qualifying_order:
            ordered = [
                (game_name, position_by_game_name[game_name])
                for game_name in self.ams2_qualifying_order
                if game_name in position_by_game_name
            ]
            remaining = [
                (game_name, position)
                for game_name, position in game_positions
                if game_name not in {name for name, _position in ordered}
            ]
            remaining.sort(key=lambda item: item[1])
            return ordered + remaining
        if not self.ams2_ai_name_mappings:
            self._log_ams2_event(
                f"No qualifying order captured; using current {self._current_game_label()} order for AI mapping fallback."
            )
        return sorted(game_positions, key=lambda item: item[1])

    def _should_use_qualifying_ai_mapping(self) -> bool:
        if self.gameplay_screen is None:
            return False
        player_count = len(
            [str(name).strip() for name in getattr(self.gameplay_screen, "player_names", []) if str(name).strip()]
        )
        return self._current_game_key() == "ams2" and player_count > 1

    def _ai_assignment_skill_key(self, driver_name: str) -> tuple[float, str]:
        driver = next(
            (
                row
                for row in getattr(self.gameplay_screen, "standings", [])
                if self._normalize_driver_name(row.get("name", "")) == self._normalize_driver_name(driver_name)
            ),
            {},
        )
        rating = self._driver_skill_value(driver, driver_name)
        variance = ((sum(ord(character) for character in driver_name) % 51) - 25)
        return (-(rating + variance), driver_name)

    def _driver_skill_value(self, driver: dict, driver_name: str = "") -> float:
        if self._current_game_key() == "ams2":
            try:
                sim_rating = float(driver.get("sim_rating", 0) or 0)
            except (TypeError, ValueError):
                sim_rating = 0
            if sim_rating:
                return sim_rating

            if not self.ams2_assignment_skill_cache and self.gameplay_screen is not None:
                profiles = driver_profile_map(str(getattr(self.gameplay_screen, "save_name", "") or ""))
                self.ams2_assignment_skill_cache = {
                    self._normalize_driver_name(name): float(
                        profile.get("ams2_general_skill", profile.get("ams2_race_skill", 0) * 100) or 0
                    ) * 12.5
                    for name, profile in profiles.items()
                }
            race_skill_rating = self.ams2_assignment_skill_cache.get(self._normalize_driver_name(driver_name))
            if race_skill_rating:
                return race_skill_rating

        for key in ("sim_rating", "skill", "mmr"):
            try:
                value = float(driver.get(key, 0) or 0)
            except (TypeError, ValueError):
                value = 0
            if value:
                return value
        return 0.0

    def _refresh_ams2_player_mapping_ui(self) -> None:
        if not hasattr(self, "ams2_player_mapping_frame"):
            return
        for widget in self.ams2_player_mapping_frame.winfo_children():
            widget.destroy()
        self.ams2_player_dropdown_vars = {}

        if self.gameplay_screen is None or not self._supports_live_order_game():
            return
        player_names = [str(name).strip() for name in getattr(self.gameplay_screen, "player_names", []) if str(name).strip()]
        if not player_names:
            return

        ctk.CTkLabel(
            self.ams2_player_mapping_frame,
            text="Player screen names",
            anchor="w",
            font=ctk.CTkFont(size=11, weight="bold"),
        ).pack(fill="x", pady=(0, 4))
        dropdown_values = [""] + self.ams2_live_participant_names
        for player_name in player_names:
            saved_value = self._current_player_name_mappings().get(player_name, "")
            if saved_value and saved_value not in dropdown_values:
                dropdown_values.append(saved_value)
            row = ctk.CTkFrame(self.ams2_player_mapping_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=player_name, width=95, anchor="w", font=ctk.CTkFont(size=10)).pack(side="left")
            variable = ctk.StringVar(value=saved_value if saved_value in dropdown_values else "")
            self.ams2_player_dropdown_vars[player_name] = variable
            ctk.CTkOptionMenu(
                row,
                values=dropdown_values,
                variable=variable,
                width=150,
                height=26,
                command=lambda _value=None: self.save_ams2_player_mappings(),
            ).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            self.ams2_player_mapping_frame,
            text="Save Player Names",
            command=self.save_ams2_player_mappings,
            height=26,
            font=ctk.CTkFont(size=10),
            fg_color="gray30",
            hover_color="gray40",
        ).pack(fill="x", pady=(6, 0))

    def save_ams2_player_mappings(self) -> None:
        mappings = self._current_player_name_mappings()
        for player_name, variable in self.ams2_player_dropdown_vars.items():
            value = variable.get().strip()
            if value:
                mappings[player_name] = value
            else:
                mappings.pop(player_name, None)
        if self._current_game_key() == "ams2":
            self.ams2_player_name_mappings = mappings
            save_ams2_player_name_mappings(mappings)
        else:
            self.iracing_player_name_mappings = mappings
            save_iracing_player_name_mappings(mappings)
        self._log_ams2_event(f"Saved {self._current_game_label()} player screen-name mappings.")

    def _log_ams2_event(self, message: str) -> None:
        clean_message = " | ".join(str(message).strip().splitlines())
        if not clean_message:
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        event = f"{timestamp} - {clean_message}"
        if self.ams2_events_log and self.ams2_events_log[-1].split(" - ", 1)[-1] == clean_message:
            return
        self.ams2_events_log.append(event)
        if len(self.ams2_events_log) > 250:
            self.ams2_events_log = self.ams2_events_log[-250:]

    def open_ams2_events_log(self) -> None:
        Ams2EventsLogPopup(self, self.ams2_events_log, self._current_game_label())

    def _current_game_key(self) -> str:
        game = str(getattr(self.gameplay_screen, "game", "") if self.gameplay_screen is not None else "").strip().casefold()
        return "ams2" if game == "ams2" else "iracing"

    def _current_game_label(self) -> str:
        return "AMS2" if self._current_game_key() == "ams2" else "iRacing"

    def _supports_live_order_game(self) -> bool:
        return self._current_game_key() in {"ams2", "iracing"}

    def _is_iracing_standby_state(self, snapshot, error: str) -> bool:
        if self._current_game_key() != "iracing":
            return False
        session_name = str(getattr(snapshot, "session_name", "") or "").strip().casefold()
        if session_name == "disconnected":
            return False
        standby_messages = (
            "did not expose driver info yet",
            "no active live buffer yet",
            "has no live positions yet",
        )
        return any(message in str(error).casefold() for message in standby_messages)

    def _current_player_name_mappings(self) -> dict[str, str]:
        return dict(self.ams2_player_name_mappings if self._current_game_key() == "ams2" else self.iracing_player_name_mappings)

    def _custom_overlays_enabled(self) -> bool:
        return bool(load_settings().get("custom_overlay_enabled", False))

    def _maybe_auto_open_ams2_leaderboard_overlay(self) -> None:
        if self._current_game_key() != "ams2" or not self._custom_overlays_enabled():
            return
        if self._leaderboard_overlay_exists():
            return
        self._create_leaderboard_overlay()

    def open_ams2_leaderboard_overlay(self) -> None:
        if self._current_game_key() != "ams2":
            self.status_label.configure(text="The leaderboard overlay is available for AMS2 races.", text_color="#ff7777")
            return
        if not self._custom_overlays_enabled():
            self.status_label.configure(text="Custom overlays are disabled in Settings.", text_color="#ff7777")
            return
        if self._leaderboard_overlay_exists():
            self._raise_leaderboard_overlay()
            return
        self._create_leaderboard_overlay()

    def _create_leaderboard_overlay(self) -> None:
        if not pyside6_available():
            self.ams2_leaderboard_overlay = None
            self.status_label.configure(
                text="Leaderboard overlay requires PySide6/Qt and no fallback overlay is available.",
                text_color="#ff7777",
            )
            return
        self.ams2_leaderboard_overlay = QtAms2LeaderboardOverlay(
            str(load_settings().get("ams2_leaderboard_overlay_geometry", "520x520+80+80")),
            on_closed=lambda: setattr(self, "ams2_leaderboard_overlay", None),
        )

    def _leaderboard_overlay_exists(self) -> bool:
        overlay = self.ams2_leaderboard_overlay
        if overlay is None:
            return False
        if hasattr(overlay, "exists"):
            return bool(overlay.exists())
        if hasattr(overlay, "winfo_exists"):
            return bool(overlay.winfo_exists())
        return False

    def _raise_leaderboard_overlay(self) -> None:
        overlay = self.ams2_leaderboard_overlay
        if overlay is None:
            return
        if hasattr(overlay, "lift"):
            overlay.lift()
        elif hasattr(overlay, "raise_"):
            overlay.raise_()

    def _update_qt_leaderboard_overlay(self, snapshot, error: str = "") -> None:
        overlay = self.ams2_leaderboard_overlay
        if overlay is None or not hasattr(overlay, "render"):
            return
        if error or not getattr(snapshot, "participants", []):
            rows: list[dict[str, str]] = []
            all_synced = False
            status = "App not synced"
        else:
            rows, all_synced, missing_count = self.ams2_overlay_rows(snapshot)
            status = "App synced" if all_synced else "App not synced"
        overlay.render(rows, all_synced, status, self._leaderboard_header_data(snapshot))

    def _leaderboard_header_data(self, snapshot) -> dict[str, object]:
        session_state = int(getattr(snapshot, "session_state", 0) or 0)
        session = {1: "P", 2: "P", 3: "Q", 4: "R", 5: "R", 6: "P"}.get(session_state, "-")
        leader_lap = 0
        estimated_lap_time = 0.0
        if getattr(snapshot, "participants", None):
            leader = min(snapshot.participants, key=lambda participant: int(getattr(participant, "position", 9999) or 9999))
            leader_lap = max(
                int(getattr(leader, "current_lap", 0) or 0),
                int(getattr(leader, "laps_completed", 0) or 0) + 1,
            )
            estimated_lap_time = self._estimated_top_driver_lap_time_seconds(snapshot, leader)
        uses_lap_count = self._is_lap_count_race() and int(getattr(snapshot, "laps_in_event", 0) or 0) > 0
        if uses_lap_count:
            progress = f"{max(1, leader_lap)}/{int(getattr(snapshot, 'laps_in_event', 0) or 0)}"
            remaining_seconds = 0.0
            estimated_total_laps = float(int(getattr(snapshot, "laps_in_event", 0) or 0))
        else:
            remaining_seconds = self._race_seconds_remaining(snapshot)
            progress = self._format_time_left(remaining_seconds)
            estimated_total_laps = self._estimated_total_laps(snapshot, max(1, leader_lap), estimated_lap_time, remaining_seconds)
        return {
            "session": session,
            "progress": progress,
            "uses_lap_count": uses_lap_count,
            "remaining_seconds": remaining_seconds,
            "current_lap": max(1, leader_lap),
            "estimated_lap_time_seconds": estimated_lap_time,
            "estimated_total_laps": estimated_total_laps,
        }

    @staticmethod
    def _estimated_top_driver_lap_time_seconds(snapshot, leader) -> float:
        top_drivers = sorted(
            list(getattr(snapshot, "participants", []) or []),
            key=lambda participant: int(getattr(participant, "position", 9999) or 9999),
        )[:5]
        last_lap_times = [
            float(getattr(participant, "last_lap_time", 0.0) or 0.0)
            for participant in top_drivers
            if 20.0 <= float(getattr(participant, "last_lap_time", 0.0) or 0.0) <= 600.0
        ]
        if last_lap_times:
            return sum(last_lap_times) / len(last_lap_times)
        track_length = float(getattr(snapshot, "track_length", 0.0) or 0.0)
        if track_length <= 0:
            return 0.0
        leader_speed = float(getattr(leader, "speed", 0.0) or 0.0)
        if leader_speed > 5:
            return track_length / leader_speed
        speeds = [
            float(getattr(participant, "speed", 0.0) or 0.0)
            for participant in getattr(snapshot, "participants", [])
        ]
        usable_speeds = [speed for speed in speeds if speed > 5]
        if not usable_speeds:
            return 0.0
        return track_length / (sum(usable_speeds) / len(usable_speeds))

    @staticmethod
    def _estimated_total_laps(snapshot, current_lap: int, estimated_lap_time: float, remaining_seconds: float) -> float:
        if estimated_lap_time <= 1:
            return 0.0
        current_lap_progress = 0.0
        track_length = float(getattr(snapshot, "track_length", 0.0) or 0.0)
        if track_length > 0 and getattr(snapshot, "participants", None):
            leader = min(snapshot.participants, key=lambda participant: int(getattr(participant, "position", 9999) or 9999))
            current_lap_progress = max(
                0.0,
                min(0.99, float(getattr(leader, "lap_distance", 0.0) or 0.0) / track_length),
            )
        return max(float(current_lap), (float(current_lap) + current_lap_progress + (remaining_seconds / estimated_lap_time)))

    def _is_lap_count_race(self) -> bool:
        championship = getattr(self.gameplay_screen, "championship", {}) if self.gameplay_screen else {}
        race_length_type = str(championship.get("race_length_type", championship.get("Race_Length_Type", ""))).strip().casefold()
        return race_length_type in {"laps", "lap", "3"}

    def _race_seconds_remaining(self, snapshot) -> float:
        duration_seconds = self._session_duration_seconds(snapshot)
        if duration_seconds > 0:
            timer_key = self._session_timer_key(snapshot, duration_seconds)
            if self.live_session_timer_expired_key == timer_key:
                return 0.0

        shared_remaining = float(getattr(snapshot, "event_time_remaining", 0.0) or 0.0)
        if 2 < shared_remaining < 24 * 60 * 60:
            return shared_remaining

        if duration_seconds > 0:
            return self._wall_clock_session_remaining(snapshot, duration_seconds)

        return 0.0

    def _session_duration_seconds(self, snapshot) -> float:
        session_duration_minutes = float(getattr(snapshot, "session_duration_minutes", 0.0) or 0.0)
        if session_duration_minutes > 0:
            return session_duration_minutes * 60.0

        championship = getattr(self.gameplay_screen, "championship", {}) if self.gameplay_screen else {}
        try:
            race_minutes = float(championship.get("Race_Time", 0) or 0)
        except (TypeError, ValueError):
            race_minutes = 0.0
        if race_minutes <= 0:
            return 0.0
        return race_minutes * 60.0

    def _session_timer_key(self, snapshot, duration_seconds: float) -> tuple[int, int, int]:
        session_state = int(getattr(snapshot, "session_state", 0) or 0)
        race_index = int(getattr(self.gameplay_screen, "current_race", 0) or 0) if self.gameplay_screen else 0
        return (race_index, session_state, int(round(duration_seconds)))

    def _wall_clock_session_remaining(self, snapshot, duration_seconds: float) -> float:
        if duration_seconds <= 0:
            return 0.0
        timer_key = self._session_timer_key(snapshot, duration_seconds)
        if self.live_session_timer_key != timer_key or self.live_session_timer_started_at is None:
            self.live_session_timer_key = timer_key
            self.live_session_timer_started_at = time.monotonic()
            if self.live_session_timer_expired_key != timer_key:
                self.live_session_timer_expired_key = None
        if self.live_session_timer_expired_key == timer_key:
            return 0.0
        elapsed = time.monotonic() - self.live_session_timer_started_at
        if elapsed >= duration_seconds:
            self.live_session_timer_expired_key = timer_key
            return 0.0
        return max(0.0, duration_seconds - elapsed)

    @staticmethod
    def _session_elapsed_seconds(snapshot) -> float:
        elapsed_candidates = [
            float(getattr(participant, "current_time", 0.0) or 0.0)
            for participant in getattr(snapshot, "participants", [])
        ]
        return max([value for value in elapsed_candidates if value > 0], default=0.0)

    @staticmethod
    def _format_time_left(seconds: float) -> str:
        if seconds <= 0:
            return "-"
        total_seconds = int(round(seconds))
        minutes, secs = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"

    def ams2_overlay_rows(self, participants_or_snapshot) -> tuple[list[dict[str, str]], bool, int]:
        participants = list(getattr(participants_or_snapshot, "participants", participants_or_snapshot) or [])
        track_length = float(getattr(participants_or_snapshot, "track_length", 0.0) or 0.0)
        standings = list(getattr(self.gameplay_screen, "standings", []) if self.gameplay_screen is not None else [])
        app_names = [
            str(driver.get("name", "")).strip()
            for driver in standings
            if str(driver.get("name", "")).strip()
        ]
        driver_by_name = {
            self._normalize_driver_name(str(driver.get("name", ""))): driver
            for driver in standings
            if str(driver.get("name", "")).strip()
        }
        app_name_by_live_name = self._ams2_app_name_by_live_name(participants)
        mapped_app_names = set(self._mapped_ams2_positions(participants))

        leader = next((participant for participant in participants if int(getattr(participant, "position", 0) or 0) == 1), None)
        if leader is None and participants:
            leader = sorted(participants, key=lambda participant: int(getattr(participant, "position", 9999) or 9999))[0]
        session_state = int(getattr(participants_or_snapshot, "session_state", 0) or 0)
        timing_by_name = ams2_timing_by_name()
        timing_by_position = ams2_timing_by_position()

        all_rows: list[dict[str, str]] = []
        player_positions: list[int] = []
        player_class_name = ""
        player_set = {
            self._normalize_driver_name(name)
            for name in getattr(self.gameplay_screen, "player_names", [])
            if str(name).strip()
        }
        player_class_name = next(
            (
                str(driver.get("class_name", "")).strip()
                for driver in standings
                if self._normalize_driver_name(str(driver.get("name", ""))) in player_set
                and str(driver.get("class_name", "")).strip()
            ),
            "",
        )
        race_classes = [class_name for class_name in self.class_finish_orders if str(class_name).strip()]
        race_class_keys = {str(class_name).casefold() for class_name in race_classes}
        for participant in sorted(participants, key=lambda item: int(getattr(item, "position", 9999) or 9999)):
            live_key = self._normalize_driver_name(getattr(participant, "name", ""))
            app_name = app_name_by_live_name.get(live_key, str(getattr(participant, "name", "")).strip())
            normalized_app_name = self._normalize_driver_name(app_name)
            driver = driver_by_name.get(normalized_app_name, {})
            position = int(getattr(participant, "position", 0) or 0)
            class_name = str(driver.get("class_name", "")).strip()
            if not class_name and len(race_classes) == 1:
                class_name = race_classes[0]
            if race_class_keys and class_name.casefold() not in race_class_keys:
                continue
            if normalized_app_name in player_set:
                player_positions.append(position)
                player_class_name = class_name
            car_label = self._overlay_car_label(driver)
            all_rows.append(
                {
                    "pos": f"P{position}" if position > 0 else "-",
                    "name": self._fit_overlay_text(app_name or str(getattr(participant, "name", "")).strip(), 24),
                    "car": self._fit_overlay_text(car_label, 12),
                    "_logo_path": _ams2_logo_path_for_label(car_label),
                    "gap": self._leader_gap_text(
                        participant,
                        leader,
                        timing_by_name,
                        timing_by_position,
                        track_length,
                        session_state,
                    ),
                    "_position": position,
                    "_class_name": class_name,
                    "_is_player": normalized_app_name in player_set,
                }
            )

        rows = self._select_overlay_rows(all_rows, player_positions, player_class_name)
        missing_count = len([name for name in app_names if self._normalize_driver_name(name) not in mapped_app_names])
        return rows, missing_count == 0 and bool(app_names) and bool(rows), missing_count

    def _select_overlay_rows(self, rows: list[dict[str, str]], player_positions: list[int], player_class_name: str = "") -> list[dict[str, str]]:
        class_order = self._overlay_class_order(rows, player_class_name)
        class_counts = {
            class_name: len([row for row in rows if str(row.get("_class_name", "Overall")) == class_name])
            for class_name in class_order
        }
        selected: list[dict[str, str]] = []
        for class_index, class_name in enumerate(class_order):
            class_rows = [
                row.copy()
                for row in rows
                if str(row.get("_class_name", "Overall")) == class_name
            ]
            for class_position, row in enumerate(class_rows, start=1):
                row["_class_position"] = class_position
                row["pos"] = f"P{class_position}"
                row["_class_color"] = self._overlay_class_color(class_index)
            if class_name.casefold() == player_class_name.casefold():
                class_player_positions = [
                    int(row.get("_class_position", 0) or 0)
                    for row in class_rows
                    if row.get("_is_player")
                ]
                display_rows = self._select_player_class_overlay_rows(class_rows, class_player_positions)
            else:
                display_rows = class_rows[:2]
            if not display_rows:
                continue
            selected.append(self._overlay_class_header(class_name, class_counts.get(class_name, len(class_rows)), class_index))
            selected.extend(display_rows)
        return selected

    @staticmethod
    def _overlay_class_order(rows: list[dict[str, str]], player_class_name: str = "") -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        if player_class_name:
            ordered.append(player_class_name)
            seen.add(player_class_name)
        for row in sorted(rows, key=lambda item: int(item.get("_position", 9999) or 9999)):
            class_name = str(row.get("_class_name", "Overall")) or "Overall"
            if class_name not in seen:
                ordered.append(class_name)
                seen.add(class_name)
        return ordered

    @staticmethod
    def _overlay_class_header(class_name: str, count: int, class_index: int) -> dict[str, str]:
        return {
            "_row_type": "class_header",
            "_class_name": class_name,
            "_class_count": str(count),
            "_class_color": ManualResultsScreen._overlay_class_color(class_index),
        }

    @staticmethod
    def _overlay_class_color(class_index: int) -> str:
        colors = ["green", "yellow", "red", "blue"]
        return colors[class_index % len(colors)]

    def _select_player_class_overlay_rows(self, rows: list[dict[str, str]], player_positions: list[int]) -> list[dict[str, str]]:
        if len(rows) <= 5:
            return rows
        rows_by_position = {
            int(row.get("_class_position", 0) or 0): row
            for row in rows
            if int(row.get("_class_position", 0) or 0) > 0
        }
        focused_player_position = min(player_positions) if player_positions else 0
        if focused_player_position <= 4:
            return rows[:5]

        max_position = max(rows_by_position) if rows_by_position else focused_player_position
        if focused_player_position >= max_position:
            focused_positions = [focused_player_position - 2, focused_player_position - 1, focused_player_position]
        elif focused_player_position == max_position - 1:
            focused_positions = [focused_player_position - 1, focused_player_position, focused_player_position + 1]
        else:
            focused_positions = [focused_player_position - 1, focused_player_position, focused_player_position + 1]
        selected_positions = [1, 2, *focused_positions]
        selected: list[dict[str, str]] = []
        seen_positions: set[int] = set()
        for position in selected_positions:
            row = rows_by_position.get(position)
            if row and position not in seen_positions:
                selected.append(row)
                seen_positions.add(position)

        for row in rows:
            if len(selected) >= 5:
                break
            position = int(row.get("_class_position", 0) or 0)
            if position not in seen_positions:
                selected.append(row)
                seen_positions.add(position)
        return selected[:5]

    def _ams2_app_name_by_live_name(self, participants) -> dict[str, str]:
        live_names = {
            self._normalize_driver_name(getattr(participant, "name", "")): str(getattr(participant, "name", "")).strip()
            for participant in participants
            if str(getattr(participant, "name", "")).strip()
        }
        mapped: dict[str, str] = {}

        for app_player, screen_name in self._current_player_name_mappings().items():
            live_key = self._normalize_driver_name(screen_name)
            if live_key in live_names:
                mapped[live_key] = str(app_player).strip()

        standings = list(getattr(self.gameplay_screen, "standings", []) if self.gameplay_screen is not None else [])
        for driver in standings:
            app_name = str(driver.get("name", "")).strip()
            live_key = self._normalize_driver_name(app_name)
            if app_name and live_key in live_names and live_key not in mapped:
                mapped[live_key] = app_name

        if self._should_use_qualifying_ai_mapping():
            for live_key, app_name in self.ams2_ai_name_mappings.items():
                normalized_live_key = self._normalize_driver_name(live_key)
                if normalized_live_key in live_names:
                    mapped[normalized_live_key] = str(app_name).strip()
        return mapped

    def _overlay_car_label(self, driver: dict) -> str:
        for key in ("car", "car_name", "player_car", "assigned_car", "class_name"):
            value = str(driver.get(key, "")).strip()
            if value:
                return value
        return "-"

    def _leader_gap_text(
        self,
        participant,
        leader,
        timing_by_name: dict,
        timing_by_position: dict[int, object],
        track_length: float = 0.0,
        session_state: int = 0,
    ) -> str:
        if leader is None:
            return "-"
        participant_position = int(getattr(participant, "position", 0) or 0)
        leader_position = int(getattr(leader, "position", 0) or 0)
        if session_state == AMS2_SESSION_QUALIFY:
            return self._qualifying_gap_text(participant, leader)
        if participant_position == leader_position:
            return "Leader"
        participant_timing = timing_by_name.get(self._normalize_driver_name(getattr(participant, "name", ""))) or timing_by_position.get(participant_position)
        leader_timing = timing_by_name.get(self._normalize_driver_name(getattr(leader, "name", ""))) or timing_by_position.get(leader_position)
        if participant_timing is not None and leader_timing is not None:
            lap_gap = int(getattr(leader_timing, "current_lap", 0) or 0) - int(
                getattr(participant_timing, "current_lap", 0) or 0
            )
            if lap_gap > 0:
                return f"+{lap_gap}L"
            seconds_gap = float(getattr(participant_timing, "current_time", 0.0) or 0.0) - float(
                getattr(leader_timing, "current_time", 0.0) or 0.0
            )
            if seconds_gap >= 0 and seconds_gap < 600:
                return f"+{seconds_gap:.1f}s"
        participant_time = float(getattr(participant, "current_time", 0.0) or 0.0)
        leader_time = float(getattr(leader, "current_time", 0.0) or 0.0)
        if participant_time > 0 and leader_time > 0:
            lap_gap = int(getattr(leader, "current_lap", 0) or 0) - int(getattr(participant, "current_lap", 0) or 0)
            if lap_gap > 0:
                return f"+{lap_gap}L"
            seconds_gap = participant_time - leader_time
            if seconds_gap >= 0 and seconds_gap < 600:
                return f"+{seconds_gap:.1f}s"
        estimated_gap = self._estimated_leader_gap_seconds(participant, leader, track_length)
        if estimated_gap is not None:
            return f"+{estimated_gap:.1f}s"
        return "--"

    @staticmethod
    def _qualifying_gap_text(participant, leader) -> str:
        participant_time = float(getattr(participant, "fastest_lap_time", 0.0) or 0.0)
        leader_time = float(getattr(leader, "fastest_lap_time", 0.0) or 0.0)
        if participant_time <= 0 or leader_time <= 0:
            return "--"
        if int(getattr(participant, "position", 0) or 0) == int(getattr(leader, "position", 0) or 0):
            return _format_lap_time(participant_time)
        seconds_gap = participant_time - leader_time
        if seconds_gap < 0 or seconds_gap >= 600:
            return "--"
        return f"+{seconds_gap:.3f}s"

    @staticmethod
    def _estimated_leader_gap_seconds(participant, leader, track_length: float) -> float | None:
        if track_length <= 0:
            return None
        leader_progress = (
            int(getattr(leader, "laps_completed", 0) or 0) * track_length
            + float(getattr(leader, "lap_distance", 0.0) or 0.0)
        )
        participant_progress = (
            int(getattr(participant, "laps_completed", 0) or 0) * track_length
            + float(getattr(participant, "lap_distance", 0.0) or 0.0)
        )
        distance_gap = leader_progress - participant_progress
        if distance_gap <= 0:
            return None
        if distance_gap >= track_length:
            return None
        speeds = [
            float(getattr(participant, "speed", 0.0) or 0.0),
            float(getattr(leader, "speed", 0.0) or 0.0),
        ]
        usable_speeds = [speed for speed in speeds if speed > 3.0]
        if not usable_speeds:
            return None
        average_speed = sum(usable_speeds) / len(usable_speeds)
        seconds_gap = distance_gap / average_speed
        if 0 <= seconds_gap < 600:
            return seconds_gap
        return None

    @staticmethod
    def _fit_overlay_text(value: str, max_chars: int) -> str:
        text = str(value).strip() or "-"
        return text if len(text) <= max_chars else f"{text[: max_chars - 3]}..."

    def open_race_setup_popup(self) -> None:
        if self.gameplay_screen is None:
            return
        RaceSetupPopup(self, self.gameplay_screen)

    @staticmethod
    def _normalize_driver_name(name: str) -> str:
        return " ".join(str(name).strip().casefold().split())

    @staticmethod
    def _format_missing_names(missing: list[str]) -> str:
        if not missing:
            return "None"
        preview = ", ".join(missing[:4])
        extra = f" +{len(missing) - 4} more" if len(missing) > 4 else ""
        return f"{preview}{extra}"

    def select_index(self, index: int, class_name: str | None = None) -> None:
        previous_class = self.selected_class
        previous_index = self.selected_index
        if class_name is not None:
            self.selected_class = class_name
        self.selected_index = index
        self._refresh_selection_visual(previous_class, previous_index)

    def _refresh_selection_visual(self, previous_class: str, previous_index: int) -> None:
        self._restore_order_index_style(previous_class, previous_index)
        self._restore_order_index_style(self.selected_class, self.selected_index)
        current_order = self.class_finish_orders.get(self.selected_class, [])
        selected_name = current_order[self.selected_index] if 0 <= self.selected_index < len(current_order) else "none"
        self.selection_label.configure(
            text=f"Selected: {selected_name} ({self.selected_class})"
            if self.selected_class
            else f"Selected: {selected_name}"
        )

    def _restore_order_index_style(self, class_name: str, index: int) -> None:
        class_order = self.class_finish_orders.get(class_name, [])
        if index < 0 or index >= len(class_order):
            return
        self._restore_order_row_style(class_name, class_order[index])

    def move_up(self) -> None:
        order = self.class_finish_orders.get(self.selected_class, [])
        if self.selected_index <= 0 or not order:
            return
        order[self.selected_index - 1], order[self.selected_index] = (
            order[self.selected_index],
            order[self.selected_index - 1],
        )
        self.selected_index -= 1
        self.finish_order = self._combined_finish_order()
        self.refresh_order_rows()

    def move_down(self) -> None:
        order = self.class_finish_orders.get(self.selected_class, [])
        if self.selected_index >= len(order) - 1 or not order:
            return
        order[self.selected_index + 1], order[self.selected_index] = (
            order[self.selected_index],
            order[self.selected_index + 1],
        )
        self.selected_index += 1
        self.finish_order = self._combined_finish_order()
        self.refresh_order_rows()

    def move_index_up(self, index: int, class_name: str | None = None) -> None:
        self.select_index(index, class_name)
        self.move_up()

    def move_index_down(self, index: int, class_name: str | None = None) -> None:
        self.select_index(index, class_name)
        self.move_down()

    def save_results(self) -> None:
        if self.gameplay_screen is None or not self.class_finish_orders:
            return

        self.stop_ams2_live_order_updates()
        self.finish_order = self._combined_finish_order()
        try:
            state = apply_finish_order(self._build_state_payload(), self.finish_order)
        except ValueError as error:
            self.status_label.configure(text=str(error), text_color="#ff7777")
            return

        self._apply_updated_state(state, "Race result saved.")

    def simulate_results(self) -> None:
        if self.gameplay_screen is None:
            return

        self.stop_ams2_live_order_updates()
        payload = self._build_state_payload()
        self.status_label.configure(text="Simulating race...", text_color="#4da6ff")
        self.simulate_button.configure(state="disabled")

        def worker() -> None:
            try:
                state = simulate_race(payload)
            except Exception as error:
                self.after(0, lambda err=error: self._finish_simulation_error(err))
                return
            self.after(0, lambda result=state: self._finish_simulation(result))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_simulation(self, state: dict) -> None:
        self.simulate_button.configure(state="normal")
        self._apply_updated_state(state, "Race simulated.")

    def _finish_simulation_error(self, error: Exception) -> None:
        self.simulate_button.configure(state="normal")
        self.status_label.configure(text=f"Could not simulate race: {error}", text_color="#ff7777")

    def import_results_json(self) -> None:
        if self.gameplay_screen is None:
            return

        adapter = get_game_adapter(getattr(self.gameplay_screen, "game", "iRacing"))
        if not adapter.supports_results_import:
            self.status_label.configure(text=f"{adapter.game_name} results import is not implemented yet.", text_color="#ffb347")
            return

        selected_file = filedialog.askopenfilename(
            title=adapter.import_dialog_title,
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
        )
        if not selected_file:
            return

        try:
            finish_order = adapter.import_results(self._build_state_payload(), selected_file)
        except ResultsImportMappingRequired as error:
            self.pending_import_path = selected_file
            self.open_mapping_dialog(error.app_names, error.imported_names)
            return
        except ValueError as error:
            self.status_label.configure(text=str(error), text_color="#ff7777")
            return

        self.pending_import_path = None
        self._apply_imported_finish_order(finish_order, f"{adapter.game_name} results loaded. Review and save to confirm.")

    def open_mapping_dialog(self, app_names: list[str], imported_names: list[str]) -> None:
        if not app_names or not imported_names:
            self.status_label.configure(
                text="Imported results could not be matched to this championship.",
                text_color="#ff7777",
            )
            return
        self.status_label.configure(text="Driver names need mapping before the import can be applied.", text_color="#ffb347")
        ResultsMappingDialog(self, app_names, imported_names, self.apply_import_mapping)

    def apply_import_mapping(self, name_map: dict[str, str]) -> None:
        if self.pending_import_path is None:
            return
        adapter = get_game_adapter(getattr(self.gameplay_screen, "game", "iRacing"))
        try:
            finish_order = adapter.import_results(self._build_state_payload(), self.pending_import_path, name_map=name_map)
        except ValueError as error:
            self.status_label.configure(text=str(error), text_color="#ff7777")
            return

        self.pending_import_path = None
        self._apply_imported_finish_order(finish_order, f"{adapter.game_name} results loaded. Review and save to confirm.")

    def _apply_imported_finish_order(self, finish_order: list[str], message: str) -> None:
        if self.gameplay_screen is None:
            return
        standings_by_name = {
            str(driver.get("name", "")).strip(): str(driver.get("class_name", "")).strip() or "Overall"
            for driver in self.gameplay_screen.standings
        }
        imported_by_class: dict[str, list[str]] = {}
        for driver_name in finish_order:
            class_name = standings_by_name.get(str(driver_name).strip(), "Overall")
            imported_by_class.setdefault(class_name, []).append(driver_name)

        if set(imported_by_class.keys()) != set(self.class_finish_orders.keys()):
            self.status_label.configure(
                text="Imported results could not be grouped against the current class layout.",
                text_color="#ff7777",
            )
            return

        for class_name, class_order in self.class_finish_orders.items():
            imported_class_order = imported_by_class.get(class_name, [])
            if set(imported_class_order) != set(class_order):
                self.status_label.configure(
                    text=f"Imported results for {class_name} do not match the current championship field.",
                    text_color="#ff7777",
                )
                return

        self.class_finish_orders = {class_name: imported_by_class[class_name][:] for class_name in self.class_finish_orders}
        self.finish_order = self._combined_finish_order()
        self.selected_class = next(iter(self.class_finish_orders), "")
        self.selected_index = 0
        self.status_label.configure(text=message, text_color="#6bbd6b")
        self.render_order()

    def _build_state_payload(self) -> dict:
        if self.gameplay_screen is None:
            return {}
        return {
            "save_name": self.gameplay_screen.save_name,
            "game": getattr(self.gameplay_screen, "game", "iRacing"),
            "career_mode": getattr(self.gameplay_screen, "career_mode", "Solo"),
            "players": self.gameplay_screen.player_names,
            "all_players": getattr(self.gameplay_screen, "all_player_names", self.gameplay_screen.player_names),
            "active_player_name": getattr(self.gameplay_screen, "active_player_name", ""),
            "player_perspectives": getattr(self.gameplay_screen, "player_perspectives", {}),
            "starting_difficulty": self.gameplay_screen.starting_difficulty,
            "tier": self.gameplay_screen.tier,
            "unlocked_tier": self.gameplay_screen.unlocked_tier,
            "score": self.gameplay_screen.score,
            "championship": self.gameplay_screen.championship,
            "player_car": self.gameplay_screen.player_car,
            "player_liveries": getattr(self.gameplay_screen, "player_liveries", []),
            "watch_drivers": getattr(self.gameplay_screen, "watch_drivers", []),
            "rising_driver": getattr(self.gameplay_screen, "rising_driver", None),
            "rivalry_heat": getattr(self.gameplay_screen, "rivalry_heat", {}),
            "messages": getattr(self.gameplay_screen, "messages", []),
            "schedule": self.gameplay_screen.schedule,
            "standings": self.gameplay_screen.standings,
            "current_race": self.gameplay_screen.current_race,
            "world_sim_progress": self.gameplay_screen.world_sim_progress,
        }

    def _apply_updated_state(self, state: dict, message: str) -> None:
        if self.gameplay_screen is None:
            return

        self.stop_ams2_live_order_updates()
        self.gameplay_screen.load_state(state)
        if self.gameplay_screen.race_status_label is not None:
            self.gameplay_screen.race_status_label.configure(text=message, text_color="#6bbd6b")
        sim_progress = self.parent.screens.get("SimProgressScreen") if hasattr(self.parent, "screens") else None
        if sim_progress is not None and hasattr(sim_progress, "set_season_intro_status"):
            sim_progress.set_season_intro_status(f"{message} Simming the world calendar...")
        self.show_screen("SimProgressScreen")

    def go_back(self) -> None:
        self.stop_ams2_live_order_updates()
        self.show_screen("GameplayScreen")
