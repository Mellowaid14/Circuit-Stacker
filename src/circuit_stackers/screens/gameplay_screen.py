from __future__ import annotations

import customtkinter as ctk
import re
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

from ..driver_pool import get_world_year, list_drivers, team_reputation_map
from ..game_logic import build_world_news_items, continue_or_initialize_season, finalize_season, reexport_championship_assets
from ..paths import resource_path
from ..season_exporter import iracing_skill_spread_for_prestige
from ..weather import display_weather
from .manual_setup_screen import RaceSetupPopup


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
ACCENT = "#2f8cff"
ACCENT_DARK = "#15507d"
SUCCESS = "#218c4a"
SUCCESS_DARK = "#176b38"
CARD = ("gray88", "gray17")
CARD_DEEP = ("gray84", "gray14")
ROW = ("gray84", "gray20")
MUTED = ("gray45", "gray62")
NEWS_KIND_STYLES = {
    "race": ("RACE REPORT", "#1d7f52", "#143d2d"),
    "title": ("TITLE FIGHT", "#d49b28", "#4d3711"),
    "interview": ("INTERVIEW", "#b861d9", "#42234f"),
    "team": ("TEAM PADDOCK", "#e17732", "#4e2813"),
    "driver": ("DRIVER WATCH", "#2f8cff", "#17385d"),
    "weather": ("WEATHER WATCH", "#5aa6bb", "#173842"),
    "world": ("WORLD NEWS", "#7587a8", "#252d3c"),
}


class GameplayScreen(ctk.CTkFrame):
    def __init__(self, parent, show_screen) -> None:
        super().__init__(parent, fg_color="transparent")
        self.show_screen = show_screen
        self.parent = parent

        self.save_name: str | None = None
        self.game = "iRacing"
        self.player_names: list[str] = []
        self.championship: dict | None = None
        self.player_car: dict | None = None
        self.player_team_offer: dict | None = None
        self.player_liveries: list[dict] = []
        self.watch_drivers: list[str] = []
        self.rising_driver: str | None = None
        self.rivalry_heat: dict[str, int] = {}
        self.messages: list[dict] = []
        self.standings: list[dict] = []
        self.schedule: list[dict] = []
        self.current_race = 0
        self.tier = 1
        self.unlocked_tier = 1
        self.score = 0
        self.starting_difficulty = 75
        self.world_sim_progress: dict | None = None
        self.world_news_items: list[dict[str, str]] = []
        self.world_news_index = 0
        self._news_after_id: str | None = None
        self._news_transition_after_id: str | None = None
        self.news_dot_buttons: list[ctk.CTkButton] = []
        self.standings_view = "drivers"
        self.driver_standings_btn: ctk.CTkButton | None = None
        self.team_standings_btn: ctk.CTkButton | None = None
        self.race_status_label: ctk.CTkLabel | None = None
        self.messages_btn: ctk.CTkButton | None = None
        self._message_blink_after_id: str | None = None
        self._message_blink_on = False
        self.season_complete_handled = False
        self._asset_file_cache: dict[tuple[str, str], list[Path]] = {}
        self._ctk_image_cache: dict[tuple[str, int, int], ctk.CTkImage] = {}

        self._build_ui()

    def load_state(self, state: dict) -> None:
        self.save_name = state.get("save_name")
        self.game = str(state.get("game", "iRacing"))
        self.player_names = state.get("players", [self.save_name] if self.save_name else [])
        self.championship = state.get("championship")
        self.player_car = state.get("player_car")
        self.player_team_offer = state.get("player_team_offer")
        self.player_liveries = state.get("player_liveries", [])
        self.watch_drivers = [str(name).strip() for name in (state.get("watch_drivers") or []) if str(name).strip()]
        rising_driver = str(state.get("rising_driver", "")).strip()
        self.rising_driver = rising_driver or None
        self.rivalry_heat = {
            str(name).strip(): int(stage)
            for name, stage in dict(state.get("rivalry_heat") or {}).items()
            if str(name).strip() and str(stage).strip() in {"1", "2", "3"}
        }
        self.messages = list(state.get("messages") or [])
        self.standings = state.get("standings", [])
        self.schedule = state.get("schedule", [])
        self.current_race = state.get("current_race", 0)
        self.tier = state.get("tier", state.get("Tier", 1))
        self.unlocked_tier = self._normalize_unlocked_tier(
            state.get("unlocked_tier", state.get("unlocked_tiers")),
            self.tier,
        )
        self.score = state.get("score", 0)
        self.starting_difficulty = int(state.get("starting_difficulty", 75))
        self.world_sim_progress = state.get("world_sim_progress")
        self.season_complete_handled = False

    def _build_ui(self) -> None:
        top = ctk.CTkFrame(self, fg_color=("gray86", "gray13"), corner_radius=18)
        top.pack(fill="x", padx=16, pady=(12, 6))

        title_stack = ctk.CTkFrame(top, fg_color="transparent")
        title_stack.pack(side="left", fill="x", expand=True, padx=16, pady=8)
        self.header_label = ctk.CTkLabel(
            title_stack,
            text="CAREER DASHBOARD",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=ACCENT,
            anchor="w",
        )
        self.header_label.pack(anchor="w")
        self.header_meta_label = ctk.CTkLabel(
            title_stack,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=MUTED,
            anchor="w",
        )
        self.header_meta_label.pack(anchor="w", fill="x", pady=(1, 0))

        ctk.CTkButton(
            top,
            text="<- Menu",
            command=lambda: self.show_screen("MenuScreen"),
            width=96,
            height=32,
            fg_color="gray30",
            hover_color="gray40",
            font=ctk.CTkFont(size=11),
        ).pack(side="right", padx=16, pady=10)

        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=12, pady=6)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=2)
        grid.rowconfigure(0, weight=1)
        grid.rowconfigure(1, weight=1)

        box1 = self._make_box(grid, "Career Overview")
        box1.grid(row=0, column=0, padx=6, pady=6, sticky="nsew")
        self.champ_info_frame = ctk.CTkScrollableFrame(box1, fg_color="transparent")
        self.champ_info_frame.pack(fill="both", expand=True, padx=6, pady=(0, 8))

        box2 = self._make_world_news_box(grid)
        box2.grid(row=0, column=1, padx=6, pady=6, sticky="nsew")
        box2.grid_propagate(False)
        self.news_frame = ctk.CTkFrame(box2, fg_color="transparent")
        self.news_frame.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        self.news_frame.pack_propagate(False)
        self.news_accent_strip = ctk.CTkFrame(self.news_frame, width=8, corner_radius=8, fg_color=ACCENT)
        self.news_accent_strip.pack(side="left", fill="y", padx=(8, 0), pady=10)
        self.news_story_frame = ctk.CTkFrame(self.news_frame, fg_color="transparent")
        self.news_story_frame.pack(side="left", fill="both", expand=True, padx=(12, 16), pady=(12, 0))

        news_topline = ctk.CTkFrame(self.news_story_frame, fg_color="transparent")
        news_topline.pack(fill="x")
        self.news_kind_label = ctk.CTkLabel(
            news_topline,
            text="WORLD NEWS",
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=ACCENT_DARK,
            corner_radius=10,
            text_color="#f4f7fb",
            height=22,
        )
        self.news_kind_label.pack(side="left", ipadx=8)
        self.news_index_label = ctk.CTkLabel(
            news_topline,
            text="01 / 03",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=MUTED,
        )
        self.news_index_label.pack(side="right")
        self.news_meta_label = ctk.CTkLabel(
            self.news_story_frame,
            text="",
            font=ctk.CTkFont(size=10),
            justify="left",
            anchor="w",
            text_color=MUTED,
        )
        self.news_meta_label.pack(anchor="w", fill="x", pady=(6, 0))
        self.news_title_label = ctk.CTkLabel(
            self.news_story_frame,
            text="",
            font=ctk.CTkFont(size=21, weight="bold"),
            justify="left",
            anchor="w",
            wraplength=560,
        )
        self.news_title_label.pack(anchor="w", fill="x", pady=(6, 6))
        self.news_body_label = ctk.CTkLabel(
            self.news_story_frame,
            text="",
            font=ctk.CTkFont(size=13),
            justify="left",
            anchor="nw",
            wraplength=560,
            text_color=("gray20", "gray86"),
        )
        self.news_body_label.pack(anchor="w", fill="both", expand=True)
        self.news_chips_frame = ctk.CTkFrame(self.news_story_frame, fg_color="transparent", height=28)
        self.news_chips_frame.pack(fill="x", pady=(5, 4))
        self.news_chips_frame.pack_propagate(False)
        self.news_dots_frame = ctk.CTkFrame(self.news_story_frame, fg_color="transparent")
        self.news_dots_frame.pack(pady=(8, 0))

        box3 = self._make_current_race_box(grid)
        box3.grid(row=1, column=0, padx=6, pady=6, sticky="nsew")
        self.race_info_frame = ctk.CTkScrollableFrame(box3, fg_color="transparent")
        self.race_info_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.race_status_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=11), text_color="#ff7777")
        self.race_status_label.pack(pady=(0, 6))

        self.action_row = ctk.CTkFrame(self, fg_color="transparent")
        self.action_row.pack(fill="x", padx=18, pady=(0, 10))
        left_actions = ctk.CTkFrame(self.action_row, fg_color="transparent")
        left_actions.pack(side="left")
        right_actions = ctk.CTkFrame(self.action_row, fg_color="transparent")
        right_actions.pack(side="right")

        ctk.CTkButton(
            left_actions,
            text="Enter Race",
            command=self.open_manual_results_editor,
            height=38,
            width=190,
            corner_radius=12,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=SUCCESS,
            hover_color=SUCCESS_DARK,
        ).pack(side="left")
        ctk.CTkButton(
            left_actions,
            text="View Schedule",
            command=lambda: self.show_screen("ScheduleScreen"),
            height=34,
            width=160,
            font=ctk.CTkFont(size=11),
            fg_color="gray30",
            hover_color="gray40",
        ).pack(side="left", padx=(8, 0))
        ctk.CTkButton(
            left_actions,
            text="World Championships",
            command=lambda: self.show_screen("WorldChampionshipsScreen"),
            height=34,
            width=170,
            font=ctk.CTkFont(size=11),
            fg_color="gray30",
            hover_color="gray40",
        ).pack(side="left", padx=(8, 0))
        self.messages_btn = ctk.CTkButton(
            right_actions,
            text="Messages",
            command=self.open_messages,
            width=105,
            height=34,
            fg_color="gray30",
            hover_color="gray40",
            font=ctk.CTkFont(size=11),
        )
        self.messages_btn.pack(side="left")
        ctk.CTkButton(
            right_actions,
            text="Re-export Roster",
            command=self.reexport_roster,
            width=130,
            height=34,
            fg_color=ACCENT_DARK,
            hover_color="#103d62",
            font=ctk.CTkFont(size=11, weight="bold"),
        ).pack(side="left", padx=(8, 0))
        ctk.CTkButton(
            right_actions,
            text="Driver Pool",
            command=self.open_driver_pool,
            width=105,
            height=34,
            fg_color="gray30",
            hover_color="gray40",
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=(8, 0))
        ctk.CTkButton(
            right_actions,
            text="Team Pool",
            command=self.open_team_pool,
            width=100,
            height=34,
            fg_color="gray30",
            hover_color="gray40",
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=(8, 0))

        box4 = self._make_standings_box(grid)
        box4.grid(row=1, column=1, padx=6, pady=6, sticky="nsew")
        self.standings_scroll = ctk.CTkScrollableFrame(box4, fg_color="transparent")
        self.standings_scroll.pack(fill="both", expand=True, padx=6, pady=(0, 6))

    def _make_box(self, parent, title: str) -> ctk.CTkFrame:
        box = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=16)
        ctk.CTkLabel(
            box,
            text=title.upper(),
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=ACCENT,
        ).pack(anchor="w", padx=10, pady=(8, 4))
        return box

    def _make_world_news_box(self, parent) -> ctk.CTkFrame:
        box = ctk.CTkFrame(
            parent,
            fg_color=("gray86", "#101923"),
            corner_radius=16,
            border_width=1,
            border_color=("gray78", "#203449"),
        )
        ctk.CTkLabel(
            box,
            text="WORLD NEWS",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=ACCENT,
        ).pack(anchor="w", padx=10, pady=(8, 2))
        return box

    def _make_current_race_box(self, parent) -> ctk.CTkFrame:
        box = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=16)
        header = ctk.CTkFrame(box, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(8, 4))
        ctk.CTkLabel(
            header,
            text="NEXT RACE",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=ACCENT,
        ).pack(side="left")
        ctk.CTkButton(
            header,
            text="Manual Setup",
            command=self.open_manual_setup,
            width=105,
            height=24,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color=ACCENT_DARK,
            hover_color="#103d62",
        ).pack(side="right")
        return box

    def _make_standings_box(self, parent) -> ctk.CTkFrame:
        box = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=16)
        header = ctk.CTkFrame(box, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(8, 4))
        ctk.CTkLabel(
            header,
            text="STANDINGS",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=ACCENT,
        ).pack(side="left")
        self.team_standings_btn = ctk.CTkButton(
            header,
            text="Teams",
            width=70,
            height=24,
            font=ctk.CTkFont(size=10),
            command=lambda: self._set_standings_view("teams"),
        )
        self.team_standings_btn.pack(side="right")
        self.driver_standings_btn = ctk.CTkButton(
            header,
            text="Drivers",
            width=70,
            height=24,
            font=ctk.CTkFont(size=10),
            command=lambda: self._set_standings_view("drivers"),
        )
        self.driver_standings_btn.pack(side="right", padx=(0, 6))
        return box

    def _info_row(self, parent, label: str, value: str) -> None:
        row = ctk.CTkFrame(parent, fg_color=("gray86", "gray18"), corner_radius=8)
        row.pack(fill="x", pady=2)
        ctk.CTkLabel(
            row, text=label, font=ctk.CTkFont(size=10), text_color=MUTED, width=96, anchor="w"
        ).pack(side="left", padx=(8, 0), pady=5)
        ctk.CTkLabel(row, text=value, font=ctk.CTkFont(size=11), anchor="w", justify="left").pack(
            side="left", fill="x", expand=True, padx=(0, 8), pady=5
        )

    def _section_label(self, parent, text: str) -> None:
        ctk.CTkLabel(
            parent,
            text=text,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=ACCENT,
            anchor="w",
        ).pack(fill="x", pady=(6, 2))

    def _group_mmr(self) -> int | None:
        player_rows = self._player_driver_rows()
        if player_rows:
            ratings = []
            for driver in player_rows:
                try:
                    ratings.append(int(driver.get("mmr", 0)))
                except (TypeError, ValueError):
                    continue
            if ratings:
                return round(sum(ratings) / len(ratings))

        player_set = set(self.player_names)
        ratings = []
        for driver in self.standings:
            if driver.get("name") not in player_set:
                continue
            try:
                ratings.append(int(driver.get("mmr", 0)))
            except (TypeError, ValueError):
                continue
        if not ratings:
            return None
        return round(sum(ratings) / len(ratings))

    def _player_driver_rows(self) -> list[dict]:
        if not self.save_name:
            return []
        player_set = {name.strip() for name in self.player_names if name and name.strip()}
        try:
            drivers = list_drivers(self.save_name, include_retired=False)
        except Exception:
            return []
        return [driver for driver in drivers if driver.get("name") in player_set and bool(driver.get("is_human"))]

    def _player_career_text(self, player_name: str, driver: dict | None) -> str:
        if not driver:
            standing = next((row for row in self.standings if row.get("name") == player_name), {})
            mmr = standing.get("mmr", "-")
            return f"MMR {mmr}"

        primary = driver.get("primary_style") or "Unassigned"
        parts = [
            f"MMR {driver.get('mmr', '-')}",
            f"Primary {primary}",
            f"Seasons {driver.get('seasons_completed', 0)}",
            f"Starts {driver.get('career_starts', 0)}",
            f"Wins {driver.get('wins', 0)}",
            f"Podiums {driver.get('podiums', 0)}",
            f"Titles {driver.get('championships', 0)}",
        ]
        return " | ".join(str(part) for part in parts)

    def _pool_counts(self) -> tuple[int, int]:
        if not self.save_name:
            return 0, 0
        try:
            active_count = len(list_drivers(self.save_name, include_retired=False))
            all_count = len(list_drivers(self.save_name, include_retired=True))
        except Exception:
            return 0, 0
        return active_count, max(0, all_count - active_count)

    def on_show(self) -> None:
        if not self.championship or not self.save_name:
            return

        state = continue_or_initialize_season(
            save_name=self.save_name,
            championship=self.championship,
            player_names=self.player_names,
            player_car=self.player_car,
            starting_difficulty=self.starting_difficulty,
            schedule=self.schedule,
            standings=self.standings,
            current_race=self.current_race,
            unlocked_tier=self.unlocked_tier,
            world_sim_progress=self.world_sim_progress,
        )
        self.load_state(state)

        self.header_label.configure(text=f"{self.game.upper()} CAREER DASHBOARD")
        self.header_meta_label.configure(
            text=f"Save: {self.save_name} | World Year: {get_world_year(self.save_name) if self.save_name else '-'} | Race {min(self.current_race + 1, len(self.schedule)) if self.schedule else '-'} of {len(self.schedule)}"
        )
        if self.race_status_label is not None:
            self.race_status_label.configure(text="")

        self._refresh_champ_info()
        self._refresh_message_button()
        self._refresh_world_news()
        self._refresh_current_race()
        self._refresh_standings()
        self._handle_season_completion()

    def on_hide(self) -> None:
        self._cancel_news_rotation()
        self._cancel_news_transition()
        self._cancel_message_blink()

    def _refresh_champ_info(self) -> None:
        for widget in self.champ_info_frame.winfo_children():
            widget.destroy()

        championship = self.championship or {}
        actual_opponents = max(0, len(self.standings) - len(self.player_names))
        player_rows = {str(driver.get("name", "")): driver for driver in self._player_driver_rows()}
        active_count, retired_count = self._pool_counts()
        try:
            world_year = get_world_year(self.save_name) if self.save_name else "-"
        except Exception:
            world_year = "-"

        self._refresh_player_car_images()
        self._section_label(self.champ_info_frame, "Current Season")
        self._info_row(self.champ_info_frame, "Championship:", championship.get("Championship", ""))
        self._info_row(self.champ_info_frame, "Current Tier:", str(championship.get("Tier", "")))
        self._info_row(self.champ_info_frame, "Player Car:", (self.player_car or {}).get("Car", "Unassigned"))
        team_name = str((self.player_team_offer or {}).get("team_name", "")).strip()
        if team_name:
            self._info_row(self.champ_info_frame, "Player Team:", team_name)
        if self.game.strip().casefold() == "ams2":
            if self.player_liveries:
                for entry in self.player_liveries:
                    driver_name = str(entry.get("driver_name", "")).strip() or "Player"
                    livery_name = str(entry.get("livery_name", "")).strip() or "-"
                    self._info_row(self.champ_info_frame, f"{driver_name} Livery:", livery_name)
            else:
                self._info_row(self.champ_info_frame, "Player Livery:", "Re-export roster to refresh")

        self._section_label(self.champ_info_frame, "Drivers")
        for player_name in self.player_names:
            self._info_row(
                self.champ_info_frame,
                f"{player_name}:",
                self._player_career_text(player_name, player_rows.get(player_name)),
            )
        if len(self.player_names) > 1:
            group_mmr = self._group_mmr()
            self._info_row(self.champ_info_frame, "Group MMR:", str(group_mmr) if group_mmr is not None else "-")

        self._section_label(self.champ_info_frame, "Career")
        self._info_row(self.champ_info_frame, "Save:", self.save_name or "")
        self._info_row(self.champ_info_frame, "World Year:", str(world_year))
        self._info_row(self.champ_info_frame, "Unlocked Tier:", str(self.unlocked_tier))
        if active_count or retired_count:
            self._info_row(self.champ_info_frame, "Driver Pool:", f"{active_count} active | {retired_count} retired")

    def _fit_cell_text(self, value: str, max_chars: int) -> str:
        text = str(value)
        if len(text) <= max_chars:
            return text
        return f"{text[: max_chars - 3]}..."

    def _display_date(self, race: dict) -> str:
        raw_date = str(race.get("date", "")).strip()
        if not raw_date:
            return "-"
        try:
            day_str, month_str = raw_date.split(maxsplit=1)
            month_number = datetime.strptime(month_str.strip(), "%b").month
            world_year = get_world_year(self.save_name) if self.save_name else datetime.now().year
            return f"{month_number:02d}/{int(day_str):02d}/{int(world_year)}"
        except Exception:
            return raw_date

    @staticmethod
    def _display_time(time_of_day: str) -> str:
        mapping = {
            "Morning": "09:00",
            "Afternoon": "14:00",
            "Evening": "18:00",
            "Night": "21:00",
        }
        return mapping.get(str(time_of_day).strip(), str(time_of_day))

    def _display_weather(self, race: dict) -> str:
        return display_weather(
            str(race.get("weather", "")).strip(),
            expand_ams2_legacy=str(self.game).strip().casefold() == "ams2",
        )

    def _difficulty_display(self) -> str:
        try:
            top = int(self.starting_difficulty)
        except (TypeError, ValueError):
            top = 75
        if str(self.game).strip().casefold() != "iracing":
            return str(top)
        top = max(0, min(125, top))
        prestige = (self.championship or {}).get("Prestige", 1)
        low = max(0, top - iracing_skill_spread_for_prestige(prestige))
        return f"{low}-{top}"

    def _opponent_summary(self) -> tuple[int, str]:
        player_set = {str(name).strip() for name in self.player_names if str(name).strip()}
        opponents = [driver for driver in self.standings if str(driver.get("name", "")).strip() not in player_set]
        opponent_count = len(opponents)
        if not opponents:
            return 0, "Same class"

        class_counts: dict[str, int] = {}
        for driver in opponents:
            class_name = str(driver.get("class_name", "")).strip() or str((self.championship or {}).get("Car", "")).strip() or "Same class"
            class_counts[class_name] = class_counts.get(class_name, 0) + 1

        if len(class_counts) <= 1:
            return opponent_count, "Same class"

        parts = [f"{class_name} {count}" for class_name, count in sorted(class_counts.items(), key=lambda item: item[0])]
        return opponent_count, " | ".join(parts)

    def _refresh_world_news(self) -> None:
        self._cancel_news_rotation()
        self.world_news_items = build_world_news_items(
            self.save_name or "",
            player_championship=self.championship or {},
            watch_drivers=self.watch_drivers,
            rising_driver=self.rising_driver,
        )
        self.world_news_index = 0
        self._show_news_story()

    def _show_news_story(self) -> None:
        if not self.world_news_items:
            self.news_kind_label.configure(text="WORLD NEWS", fg_color=ACCENT_DARK)
            self.news_index_label.configure(text="-- / --")
            self.news_meta_label.configure(text="Paddock wire | Stories update with the world")
            self.news_title_label.configure(text="World News")
            self.news_body_label.configure(text="No stories available right now.")
            self._refresh_news_chips([])
            for widget in self.news_dots_frame.winfo_children():
                widget.destroy()
            self.news_dot_buttons = []
            self._cancel_news_rotation()
            return

        self.world_news_index = max(0, min(self.world_news_index, len(self.world_news_items) - 1))
        story = self.world_news_items[self.world_news_index]
        presentation = self._news_story_presentation(story)
        self._cancel_news_transition()
        self._apply_news_story(presentation, fade_in=False)
        self._news_transition_after_id = self.after(45, lambda value=presentation: self._apply_news_story(value))
        self._refresh_news_dots()
        self._schedule_news_rotation()
        return

        for widget in self.news_dots_frame.winfo_children():
            widget.destroy()
        for index in range(len(self.world_news_items)):
            color = "#ffffff" if index == self.world_news_index else "#8b8b8b"
            ctk.CTkButton(
                self.news_dots_frame,
                text="●",
                command=lambda value=index: self._select_news_story(value),
                width=18,
                height=18,
                corner_radius=9,
                fg_color="transparent",
                hover_color=("gray80", "gray25"),
                text_color=color,
                font=ctk.CTkFont(size=12),
            ).pack(side="left", padx=4)
        self._schedule_news_rotation()

    def _apply_news_story(self, story: dict[str, object], fade_in: bool = True) -> None:
        self._news_transition_after_id = None
        label, accent, badge_color = NEWS_KIND_STYLES[str(story["kind"])]
        self.news_accent_strip.configure(fg_color=accent)
        self.news_kind_label.configure(text=label, fg_color=badge_color)
        self.news_index_label.configure(text=f"{self.world_news_index + 1:02d} / {len(self.world_news_items):02d}")
        self.news_meta_label.configure(text=str(story["meta"]))
        self.news_title_label.configure(
            text=str(story["title"]),
            text_color=("#16283a", "#f4f7fb") if fade_in else MUTED,
        )
        self.news_body_label.configure(
            text=str(story["body"]),
            text_color=("gray20", "gray86") if fade_in else MUTED,
        )
        self._refresh_news_chips(list(story["chips"]))

    def _news_story_presentation(self, story: dict[str, str]) -> dict[str, object]:
        title = str(story.get("title", "World News")).strip() or "World News"
        raw_body = str(story.get("body", "")).strip()
        body = raw_body.replace("**", "")
        lowered = f"{title} {body}".casefold()
        kind = "world"
        if any(term in lowered for term in ("title", "champion", "clinched", "pressure round")):
            kind = "title"
        elif any(term in lowered for term in ("interview", "reaction", "\"")):
            kind = "interview"
        elif any(term in lowered for term in ("team", "retention", "market", "teammate")):
            kind = "team"
        elif any(term in lowered for term in ("weather", "rain", "storm", "fog")):
            kind = "weather"
        elif any(term in lowered for term in ("win", "podium", "round", "race", "contact", "points finish", "at ")):
            kind = "race"
        elif any(term in lowered for term in ("rookie", "driver", "retirement", "promotion", "rivalry")):
            kind = "driver"

        chips = []
        for highlighted in re.findall(r"\*\*(.+?)\*\*", raw_body):
            clean_value = re.sub(r"\s+", " ", highlighted).strip(" .,:;\"'")
            if clean_value and clean_value not in chips:
                chips.append(clean_value)
        if not chips and title != "World News":
            chips.append(title.replace(" Title Fight", "").replace(" Champion", "").strip())

        world_year = get_world_year(self.save_name) if self.save_name else "-"
        metadata = {
            "race": "Race wire",
            "title": "Championship desk",
            "interview": "Paddock interview",
            "team": "Team market",
            "driver": "Driver watch",
            "weather": "Forecast desk",
            "world": "World bulletin",
        }[kind]
        style = str((self.championship or {}).get("Style", "")).strip()
        meta_parts = [metadata, f"World Year {world_year}"]
        if style and kind in {"driver", "world"}:
            meta_parts.append(style)
        return {
            "kind": kind,
            "title": title,
            "body": body,
            "meta": " | ".join(meta_parts),
            "chips": chips[:3],
        }

    def _refresh_news_chips(self, chips: list[object]) -> None:
        for widget in self.news_chips_frame.winfo_children():
            widget.destroy()
        for chip in chips:
            ctk.CTkLabel(
                self.news_chips_frame,
                text=str(chip),
                height=22,
                corner_radius=11,
                fg_color=("gray76", "#203449"),
                text_color=("#17385d", "#d7e9ff"),
                font=ctk.CTkFont(size=10, weight="bold"),
            ).pack(side="left", padx=(0, 5), ipadx=8)

    def _refresh_news_dots(self) -> None:
        if len(self.news_dot_buttons) != len(self.world_news_items):
            for widget in self.news_dots_frame.winfo_children():
                widget.destroy()
            self.news_dot_buttons = []
            for index in range(len(self.world_news_items)):
                button = ctk.CTkButton(
                    self.news_dots_frame,
                    text="●",
                    command=lambda value=index: self._select_news_story(value),
                    width=18,
                    height=18,
                    corner_radius=9,
                    fg_color="transparent",
                    hover_color=("gray80", "gray25"),
                    text_color="#8b8b8b",
                    font=ctk.CTkFont(size=12),
                )
                button.pack(side="left", padx=4)
                self.news_dot_buttons.append(button)
        for index, button in enumerate(self.news_dot_buttons):
            button.configure(text_color="#ffffff" if index == self.world_news_index else "#8b8b8b")

    def _select_news_story(self, index: int) -> None:
        if not self.world_news_items:
            return
        self._cancel_news_rotation()
        self.world_news_index = max(0, min(int(index), len(self.world_news_items) - 1))
        self._show_news_story()

    def _cancel_news_rotation(self) -> None:
        if self._news_after_id is None:
            return
        try:
            self.after_cancel(self._news_after_id)
        except Exception:
            pass
        self._news_after_id = None

    def _cancel_news_transition(self) -> None:
        if self._news_transition_after_id is None:
            return
        try:
            self.after_cancel(self._news_transition_after_id)
        except Exception:
            pass
        self._news_transition_after_id = None

    def _schedule_news_rotation(self) -> None:
        self._cancel_news_rotation()
        if len(self.world_news_items) <= 1:
            return
        self._news_after_id = self.after(30000, self._advance_news_story)

    def _advance_news_story(self) -> None:
        self._news_after_id = None
        if len(self.world_news_items) <= 1:
            return
        if not self.winfo_ismapped():
            return
        if hasattr(self.parent, "window_is_changing") and self.parent.window_is_changing():
            self._news_after_id = self.after(1000, self._advance_news_story)
            return
        self.world_news_index = (self.world_news_index + 1) % len(self.world_news_items)
        self._show_news_story()

    def _refresh_current_race(self) -> None:
        for widget in self.race_info_frame.winfo_children():
            widget.destroy()

        if self.current_race >= len(self.schedule):
            ctk.CTkLabel(
                self.race_info_frame,
                text="Championship Complete!",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color="#4da6ff",
            ).pack(pady=20)
            ctk.CTkButton(
                self.race_info_frame,
                text="Continue Career",
                command=self._handle_season_completion,
                height=30,
                width=180,
                font=ctk.CTkFont(size=11, weight="bold"),
            ).pack(pady=(0, 10))
            return

        race = self.schedule[self.current_race]
        self._asset_image_label(
            self.race_info_frame,
            self._track_image_path(race),
            size=(540, 180),
            pady=(0, 10),
        )
        self._info_row(self.race_info_frame, "Race:", f"{race['race_num']} of {len(self.schedule)}")
        self._info_row(self.race_info_frame, "Track:", race["track"])
        self._info_row(self.race_info_frame, "Layout:", race["layout"])
        self._info_row(self.race_info_frame, "Date:", self._display_date(race))
        self._info_row(self.race_info_frame, "Time:", self._display_time(str(race.get("time_of_day", ""))))
        self._info_row(self.race_info_frame, "Weather:", self._display_weather(race))
        self._info_row(self.race_info_frame, "Difficulty:", self._difficulty_display())
        opponent_count, opponent_classes = self._opponent_summary()
        self._info_row(self.race_info_frame, "Opponents:", str(opponent_count))
        self._info_row(self.race_info_frame, "Opponent Class:", opponent_classes)
        self._info_row(
            self.race_info_frame,
            "Race Length:",
            f"{(self.championship or {}).get('Race_Time', '-') } min".replace("  ", " "),
        )
        self._info_row(self.race_info_frame, "Start Type:", (self.championship or {}).get("Start_Type", ""))

    def _refresh_player_car_images(self) -> None:
        if (
            self.game.strip().casefold() == "ams2"
            and len(self.player_names) > 1
            and self.player_liveries
        ):
            livery_by_driver = {
                str(livery.get("driver_name", "")).strip(): livery
                for livery in self.player_liveries
                if str(livery.get("driver_name", "")).strip()
            }
            row = ctk.CTkFrame(self.champ_info_frame, fg_color="transparent")
            row.pack(fill="x", pady=(0, 8))
            shown = 0
            for player_name in self.player_names:
                livery = livery_by_driver.get(player_name)
                path = self._player_car_image_path(livery)
                image = self._load_asset_image(path, (175, 72))
                if image is None:
                    continue
                card = ctk.CTkFrame(row, fg_color=("gray86", "gray18"), corner_radius=10)
                card.pack(side="left", fill="both", expand=True, padx=(0 if shown == 0 else 4, 4))
                ctk.CTkLabel(card, text="", image=image).pack(fill="x", padx=6, pady=(6, 2))
                ctk.CTkLabel(
                    card,
                    text=player_name,
                    font=ctk.CTkFont(size=10, weight="bold"),
                    anchor="center",
                ).pack(fill="x", padx=6, pady=(0, 6))
                shown += 1
            if shown:
                return
            row.destroy()

        self._asset_image_label(
            self.champ_info_frame,
            self._player_car_image_path(),
            size=(360, 118),
            pady=(0, 8),
        )

    def _player_car_image_path(self, livery: dict | None = None) -> Path | None:
        candidates: list[str] = []
        livery_rows = [livery] if livery else list(self.player_liveries or [])
        for livery_row in livery_rows:
            candidates.extend(
                [
                    str(livery_row.get("livery_name", "")).strip(),
                    str(livery_row.get("car_name", "")).strip(),
                    str(livery_row.get("car_id", "")).strip(),
                    str(livery_row.get("roster_name", "")).strip(),
                    str(livery_row.get("class_name", "")).strip(),
                ]
            )
        player_car = self.player_car or {}
        candidates.extend(
            [
                str(player_car.get("image file", "")).strip(),
                str(player_car.get("Car", "")).strip(),
                str(player_car.get("FILEPATH", "")).strip(),
                str(player_car.get("ams2_livery_folder", "")).strip(),
                str((self.championship or {}).get("Car", "")).strip(),
            ]
        )
        return self._best_asset_image("Cars", candidates)

    def _track_image_path(self, race: dict) -> Path | None:
        return self._best_asset_image(
            "Tracks",
            [
                str(race.get("layout", "")).strip(),
                str(race.get("track", "")).strip(),
            ],
        )

    def _best_asset_image(self, asset_type: str, candidates: list[str]) -> Path | None:
        normalized_candidates = [self._asset_key(candidate) for candidate in candidates if self._asset_key(candidate)]
        if not normalized_candidates:
            return None

        root = resource_path("assets", asset_type, self._asset_game_folder())
        best_path: Path | None = None
        best_score = 0
        for path in self._asset_files(asset_type):
            stem_key = self._asset_key(path.stem)
            cutout_stem_key = self._asset_key(path.stem.removesuffix("_cutout"))
            parent_key = self._asset_key(path.parent.name)
            try:
                relative_key = self._asset_key(" ".join(path.relative_to(root).parts))
            except ValueError:
                relative_key = self._asset_key(str(path))
            score = 0
            for candidate_key in normalized_candidates:
                if path.stem.endswith("_cutout") and candidate_key == cutout_stem_key:
                    score = max(score, 110)
                if candidate_key == stem_key:
                    score = max(score, 100)
                if candidate_key == parent_key:
                    score = max(score, 90)
                if candidate_key in stem_key or stem_key in candidate_key:
                    score = max(score, 75)
                if candidate_key in parent_key or parent_key in candidate_key:
                    score = max(score, 65)
                if candidate_key in relative_key:
                    score = max(score, 50)
            if score > best_score:
                best_score = score
                best_path = path
        return best_path if best_score >= 50 else None

    def _asset_files(self, asset_type: str) -> list[Path]:
        game_folder = self._asset_game_folder()
        cache_key = (asset_type, game_folder)
        if cache_key in self._asset_file_cache:
            return self._asset_file_cache[cache_key]
        root = resource_path("assets", asset_type, game_folder)
        if not root.exists():
            self._asset_file_cache[cache_key] = []
            return []
        files = [path for path in root.rglob("*") if path.is_file() and path.suffix.casefold() in IMAGE_EXTENSIONS]
        self._asset_file_cache[cache_key] = files
        return files

    def _asset_game_folder(self) -> str:
        return "AMS2" if str(self.game).strip().casefold() == "ams2" else "Iracing"

    @staticmethod
    def _asset_key(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(value).casefold())

    def _asset_image_label(
        self,
        parent,
        path: Path | None,
        *,
        size: tuple[int, int],
        pady: tuple[int, int],
    ) -> None:
        image = self._load_asset_image(path, size)
        if image is None:
            return
        label = ctk.CTkLabel(parent, text="", image=image)
        label.pack(fill="x", padx=4, pady=pady)

    def _load_asset_image(self, path: Path | None, size: tuple[int, int]) -> ctk.CTkImage | None:
        if path is None:
            return None
        cache_key = (str(path), int(size[0]), int(size[1]))
        if cache_key in self._ctk_image_cache:
            return self._ctk_image_cache[cache_key]
        try:
            source = Image.open(path).convert("RGBA")
            fitted = ImageOps.contain(source, size, method=Image.Resampling.BILINEAR)
            image = ctk.CTkImage(light_image=fitted, dark_image=fitted, size=fitted.size)
        except Exception:
            return None
        self._ctk_image_cache[cache_key] = image
        return image

    def _refresh_standings(self) -> None:
        for widget in self.standings_scroll.winfo_children():
            widget.destroy()
        self._refresh_standings_toggle_buttons()
        if self.standings_view == "teams":
            self._refresh_team_standings()
        else:
            self._refresh_driver_standings()

    def _refresh_driver_standings(self) -> None:
        player_set = set(self.player_names)
        season_stats = self._season_result_counts()
        groups: dict[str, list[dict]] = {}
        for driver in self.standings:
            class_name = str(driver.get("class_name", "")).strip() or "Overall"
            groups.setdefault(class_name, []).append(driver)

        multiclass = len(groups) > 1
        for class_name, drivers in groups.items():
            if multiclass:
                ctk.CTkLabel(
                    self.standings_scroll,
                    text=class_name,
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color=ACCENT,
                ).pack(anchor="w", padx=4, pady=(6, 2))

            header = ctk.CTkFrame(self.standings_scroll, fg_color="transparent")
            header.pack(fill="x")
            for column, width in [
                ("Pos", 35),
                ("Driver", 135),
                ("Team", 120),
                ("Points", 55),
                ("Wins", 45),
                ("Podiums", 60),
                ("Top 5", 50),
                ("MMR", 55),
                ("", 60),
            ]:
                ctk.CTkLabel(
                    header,
                    text=column,
                    font=ctk.CTkFont(size=10, weight="bold"),
                    text_color="gray",
                    width=width,
                    anchor="w",
                ).pack(side="left", padx=4)

            sorted_standings = sorted(drivers, key=lambda driver: (driver["points"], driver["wins"]), reverse=True)
            for position, driver in enumerate(sorted_standings, 1):
                is_player = driver["name"] in player_set
                driver_name = str(driver["name"])
                driver_stats = season_stats.get(driver_name, {"podiums": 0, "top5": 0})
                markers = ""
                if driver_name in self.watch_drivers:
                    markers += "★"
                if self.rising_driver and driver_name == self.rising_driver:
                    markers += "↑"
                display_name = f"{markers} {driver_name}".strip()
                row = ctk.CTkFrame(
                    self.standings_scroll,
                    fg_color=("#d8ecff", "#173a59") if is_player else ROW,
                    corner_radius=9,
                )
                row.pack(fill="x", pady=2)
                stripe_color = self._rivalry_stripe_color(driver_name)
                if stripe_color:
                    ctk.CTkFrame(
                        row,
                        fg_color=stripe_color,
                        width=5,
                        height=24,
                        corner_radius=4,
                    ).pack(side="left", padx=(0, 3), pady=3)

                for value, width in [
                    (str(position), 35),
                    (display_name, 135),
                    (str(driver.get("team_name", "-")), 120),
                    (str(driver["points"]), 55),
                    (str(driver["wins"]), 45),
                    (str(driver_stats.get("podiums", 0)), 60),
                    (str(driver_stats.get("top5", 0)), 50),
                    (str(driver.get("mmr", "-")), 55),
                ]:
                    ctk.CTkLabel(row, text=value, font=ctk.CTkFont(size=11), width=width, anchor="w").pack(
                        side="left", padx=4, pady=4
                    )
                ctk.CTkButton(
                    row,
                    text="View",
                    width=55,
                    height=24,
                    font=ctk.CTkFont(size=10),
                    fg_color="gray30",
                    hover_color="gray40",
                    command=lambda driver_id=str(driver.get("driver_id", "")).strip(): self._open_driver_detail(driver_id),
                ).pack(side="left", padx=(2, 0), pady=4)

    def _rivalry_stripe_color(self, driver_name: str) -> str:
        stage = int(self.rivalry_heat.get(str(driver_name).strip(), 0) or 0)
        if stage >= 3:
            return "#e04747"
        if stage == 2:
            return "#f08a24"
        if stage == 1:
            return "#e8c632"
        return ""

    def _refresh_team_standings(self) -> None:
        groups: dict[str, list[dict]] = {}
        for driver in self.standings:
            class_name = str(driver.get("class_name", "")).strip() or "Overall"
            groups.setdefault(class_name, []).append(driver)

        multiclass = len(groups) > 1
        for class_name, drivers in groups.items():
            if multiclass:
                ctk.CTkLabel(
                    self.standings_scroll,
                    text=class_name,
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color=ACCENT,
                ).pack(anchor="w", padx=4, pady=(6, 2))

            team_rows = self._team_standings_for_drivers(drivers)
            header = ctk.CTkFrame(self.standings_scroll, fg_color="transparent")
            header.pack(fill="x")
            for column, width in [
                ("Pos", 35),
                ("Team", 175),
                ("Rep", 45),
                ("Drivers", 60),
                ("Points", 60),
                ("Wins", 45),
                ("Podiums", 60),
                ("Top 5", 50),
                ("", 55),
            ]:
                ctk.CTkLabel(
                    header,
                    text=column,
                    font=ctk.CTkFont(size=10, weight="bold"),
                    text_color="gray",
                    width=width,
                    anchor="w",
                ).pack(side="left", padx=4)

            for position, team in enumerate(team_rows, 1):
                row = ctk.CTkFrame(self.standings_scroll, fg_color=ROW, corner_radius=9)
                row.pack(fill="x", pady=2)
                for value, width in [
                    (str(position), 35),
                    (team["team_name"], 175),
                    (str(team["reputation"]), 45),
                    (str(team["drivers"]), 60),
                    (str(team["points"]), 60),
                    (str(team["wins"]), 45),
                    (str(team["podiums"]), 60),
                    (str(team["top5"]), 50),
                ]:
                    ctk.CTkLabel(row, text=value, font=ctk.CTkFont(size=11), width=width, anchor="w").pack(
                        side="left", padx=4, pady=4
                    )
                ctk.CTkButton(
                    row,
                    text="View",
                    width=55,
                    height=24,
                    font=ctk.CTkFont(size=10),
                    fg_color="gray30",
                    hover_color="gray40",
                    command=lambda team_key=str(team.get("team_key", "")).strip(): self._open_team_detail(team_key),
                ).pack(side="left", padx=(2, 0), pady=4)

    def _team_standings_for_drivers(self, drivers: list[dict]) -> list[dict]:
        season_stats = self._season_result_counts()
        reputations = team_reputation_map(self.save_name) if self.save_name else {}
        teams: dict[str, dict] = {}
        for driver in drivers:
            team_name = str(driver.get("team_name", "")).strip() or "Independent"
            team_key = str(driver.get("team_key", "")).strip()
            team_id = str(driver.get("team_id", "")).strip()
            reputation = reputations.get(team_key) or reputations.get(team_id) or reputations.get(team_name) or 50
            row = teams.setdefault(
                team_name,
                {
                    "team_key": team_key,
                    "team_id": team_id,
                    "team_name": team_name,
                    "reputation": reputation,
                    "drivers": 0,
                    "points": 0,
                    "wins": 0,
                    "podiums": 0,
                    "top5": 0,
                },
            )
            driver_name = str(driver.get("name", "")).strip()
            driver_stats = season_stats.get(driver_name, {"podiums": 0, "top5": 0})
            row["drivers"] += 1
            row["points"] += int(driver.get("points", 0) or 0)
            row["wins"] += int(driver.get("wins", 0) or 0)
            row["podiums"] += int(driver_stats.get("podiums", 0) or 0)
            row["top5"] += int(driver_stats.get("top5", 0) or 0)
        return sorted(
            teams.values(),
            key=lambda row: (-row["points"], -row["wins"], -row["podiums"], -row["top5"], row["team_name"]),
        )

    def _set_standings_view(self, view: str) -> None:
        self.standings_view = "teams" if view == "teams" else "drivers"
        self._refresh_standings()

    def _refresh_standings_toggle_buttons(self) -> None:
        if self.driver_standings_btn is not None:
            self.driver_standings_btn.configure(
                fg_color="#1f6aa5" if self.standings_view == "drivers" else "gray30",
                hover_color="#15507d" if self.standings_view == "drivers" else "gray40",
            )
        if self.team_standings_btn is not None:
            self.team_standings_btn.configure(
                fg_color="#1f6aa5" if self.standings_view == "teams" else "gray30",
                hover_color="#15507d" if self.standings_view == "teams" else "gray40",
            )

    def _season_result_counts(self) -> dict[str, dict[str, int]]:
        counts: dict[str, dict[str, int]] = {}
        for race in self.schedule:
            full_results = race.get("full_results") or []
            if not isinstance(full_results, list):
                continue
            for row in full_results:
                if not isinstance(row, dict):
                    continue
                driver_name = str(row.get("driver_name", "")).strip()
                if not driver_name:
                    continue
                class_pos = int(row.get("class_pos", 0) or 0)
                driver_counts = counts.setdefault(driver_name, {"podiums": 0, "top5": 0})
                if 1 <= class_pos <= 3:
                    driver_counts["podiums"] += 1
                if 1 <= class_pos <= 5:
                    driver_counts["top5"] += 1
        return counts

    def open_manual_results_editor(self) -> None:
        if not self.championship or not self.save_name:
            return
        if self.race_status_label is not None:
            self.race_status_label.configure(text="")
        self.show_screen("RaceWeekendScreen")

    def open_manual_setup(self) -> None:
        if not self.championship or not self.save_name:
            return
        if self.race_status_label is not None:
            self.race_status_label.configure(text="")
        RaceSetupPopup(self, self)

    def reexport_roster(self) -> None:
        if not self.championship or not self.save_name:
            return
        try:
            updated_state = reexport_championship_assets(
                {
                    "save_name": self.save_name,
                    "players": self.player_names,
                    "game": self.game,
                    "starting_difficulty": self.starting_difficulty,
                    "tier": self.tier,
                    "unlocked_tier": self.unlocked_tier,
                    "score": self.score,
                    "championship": self.championship,
                    "player_car": self.player_car,
                    "player_team_offer": self.player_team_offer,
                    "player_liveries": self.player_liveries,
                    "rivalry_heat": self.rivalry_heat,
                    "messages": self.messages,
                    "schedule": self.schedule,
                    "standings": self.standings,
                    "current_race": self.current_race,
                    "world_sim_progress": self.world_sim_progress,
                }
            )
        except Exception as error:
            if self.race_status_label is not None:
                self.race_status_label.configure(text=f"Could not re-export roster: {error}", text_color="#ff7777")
            return

        self.load_state(updated_state)
        self._refresh_champ_info()
        self._refresh_message_button()
        if self.race_status_label is not None:
            game_label = "AMS2 roster" if self.game.strip().casefold() == "ams2" else "roster"
            self.race_status_label.configure(text=f"Re-exported {game_label}.", text_color="#6bbd6b")

    def open_driver_pool(self) -> None:
        driver_pool_screen = self.parent.screens["DriverPoolScreen"]
        if hasattr(driver_pool_screen, "set_back_screen"):
            driver_pool_screen.set_back_screen("GameplayScreen")
        if hasattr(driver_pool_screen, "set_context"):
            driver_pool_screen.set_context(self.save_name, self.tier, (self.championship or {}).get("Style"))
        self.show_screen("DriverPoolScreen")

    def open_team_pool(self) -> None:
        team_pool_screen = self.parent.screens["TeamPoolScreen"]
        if hasattr(team_pool_screen, "set_back_screen"):
            team_pool_screen.set_back_screen("GameplayScreen")
        if hasattr(team_pool_screen, "set_context"):
            team_pool_screen.set_context(self.save_name)
        self.show_screen("TeamPoolScreen")

    def open_messages(self) -> None:
        self.show_screen("MessagesScreen")

    def _refresh_message_button(self) -> None:
        if self.messages_btn is None:
            return
        unread = sum(1 for message in self.messages if not bool(message.get("read")))
        self.messages_btn.configure(text=f"Messages ({unread})" if unread else "Messages")
        if unread:
            self._start_message_blink()
        else:
            self._cancel_message_blink()
            self.messages_btn.configure(fg_color="gray30", hover_color="gray40")

    def _start_message_blink(self) -> None:
        if self.messages_btn is None or self._message_blink_after_id is not None:
            return
        self._message_blink_on = False
        self._pulse_message_button()

    def _pulse_message_button(self) -> None:
        if self.messages_btn is None:
            self._message_blink_after_id = None
            return
        unread = any(not bool(message.get("read")) for message in self.messages)
        if not unread:
            self._cancel_message_blink()
            self.messages_btn.configure(fg_color="gray30", hover_color="gray40")
            return
        self._message_blink_on = not self._message_blink_on
        self.messages_btn.configure(
            fg_color=ACCENT if self._message_blink_on else "gray30",
            hover_color=ACCENT_DARK if self._message_blink_on else "gray40",
        )
        self._message_blink_after_id = self.after(750, self._pulse_message_button)

    def _cancel_message_blink(self) -> None:
        if self._message_blink_after_id is not None:
            try:
                self.after_cancel(self._message_blink_after_id)
            except Exception:
                pass
        self._message_blink_after_id = None
        self._message_blink_on = False

    def _open_driver_detail(self, driver_id: str) -> None:
        if not self.save_name or not driver_id:
            return
        detail_screen = self.parent.screens["DriverDetailScreen"]
        if hasattr(detail_screen, "set_context"):
            detail_screen.set_context(self.save_name, driver_id, "GameplayScreen")
        self.show_screen("DriverDetailScreen")

    def _open_team_detail(self, team_key: str) -> None:
        if not self.save_name or not team_key:
            return
        detail_screen = self.parent.screens["TeamDetailScreen"]
        if hasattr(detail_screen, "set_context"):
            detail_screen.set_context(self.save_name, team_key, "GameplayScreen")
        self.show_screen("TeamDetailScreen")

    def open_race_results(self, race_index: int) -> None:
        race_results_screen = self.parent.screens["RaceResultsScreen"]
        if hasattr(race_results_screen, "set_race_index"):
            race_results_screen.set_race_index(race_index)
        self.show_screen("RaceResultsScreen")

    def _handle_season_completion(self) -> None:
        if self.season_complete_handled:
            return
        if not self.schedule or self.current_race < len(self.schedule):
            return
        if not self.save_name:
            return
        if not self._world_sim_complete():
            self.show_screen("SimProgressScreen")
            return

        new_state, summary = finalize_season(
            {
                "save_name": self.save_name,
                "players": self.player_names,
                "game": self.game,
                "starting_difficulty": self.starting_difficulty,
                "tier": self.tier,
                "unlocked_tier": self.unlocked_tier,
                "score": self.score,
                "championship": self.championship,
                "player_car": self.player_car,
                "player_team_offer": self.player_team_offer,
                "schedule": self.schedule,
                "standings": self.standings,
                "current_race": self.current_race,
                "world_sim_progress": self.world_sim_progress,
            }
        )
        self.season_complete_handled = True

        recap_screen = self.parent.screens["SeasonRecapScreen"]
        if hasattr(recap_screen, "set_recap"):
            recap_screen.set_recap(
                save_name=self.save_name,
                player_names=self.player_names,
                championship_name=str((self.championship or {}).get("Championship", "Season Recap")),
                summary=summary,
                final_standings=self.standings,
                next_tier=int(new_state.get("unlocked_tier", new_state["tier"])),
                starting_difficulty=int(new_state.get("starting_difficulty", self.starting_difficulty)),
            )
        self.show_screen("SeasonRecapScreen")

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

    def _world_sim_complete(self) -> bool:
        progress = self.world_sim_progress or {}
        if not progress:
            return False
        return bool(progress.get("complete", False))
