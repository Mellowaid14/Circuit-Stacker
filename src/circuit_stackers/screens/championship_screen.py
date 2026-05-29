from __future__ import annotations

import random
import re
from pathlib import Path

import customtkinter as ctk
from PIL import Image, ImageOps

from ..ams2_exporter import preview_player_livery_for_car
from ..custom_championships import championship_rows
from ..driver_pool import (
    championship_pool_display_name,
    current_team_offer_for_championship,
    get_world_year,
    player_effective_mmr_for_style,
    player_entry_prestige_for_style,
    players_are_fresh_rookies,
    team_reputation_map,
    team_offers_for_player,
)
from ..game_logic import get_eligible_player_cars
from ..paths import resource_path
from ..roster_exporter import team_color_set
from ..save_manager import load_save


STYLE_ORDER = ["Sports Car", "Open Wheel", "Oval", "Rallycross"]
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
ACCENT = "#2f8cff"
ACCENT_DARK = "#15507d"
CARD = ("gray88", "gray16")
CARD_DEEP = ("gray84", "gray13")
ROW = ("gray83", "gray20")
SELECTED_ROW = ("#d8ecff", "#173a59")
MUTED = ("gray42", "gray64")
SUCCESS = "#218c4a"
SUCCESS_DARK = "#176b38"


def _display_style(style: str) -> str:
    normalized = str(style).strip().casefold()
    if normalized == "80r/20o":
        return "Open Wheel"
    if normalized == "20r/80o":
        return "Oval"
    return str(style).strip()


def _public_championship_row(row: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in row.items() if not str(key).startswith("_")}


def _player_entry_rows_from_loaded_rows(row: dict[str, str], rows: list[dict[str, str]]) -> list[dict[str, str]]:
    selected_row_id = str(row.get("id", "")).strip()
    if selected_row_id:
        exact_rows = [_public_championship_row(candidate) for candidate in rows if str(candidate.get("id", "")).strip() == selected_row_id]
        if exact_rows:
            return exact_rows

    group_id = str(row.get("Championship_ID", "") or row.get("id", "")).strip()
    group_rows = [
        _public_championship_row(candidate)
        for candidate in rows
        if str(candidate.get("Championship_ID", "") or candidate.get("id", "")).strip() == group_id
    ] or [_public_championship_row(row)]
    return group_rows


def _championship_group_key(row: dict[str, str]) -> str:
    return str(row.get("Championship_ID", "") or row.get("id", "")).strip()


def _merge_player_championship_rows(rows: list[dict[str, str]], all_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault((_championship_group_key(row), _display_style(str(row.get("Style", "")))), []).append(row)

    merged_rows: list[dict[str, str]] = []
    for (_group_id, _style), group_rows in grouped.items():
        group_rows = sorted(
            group_rows,
            key=lambda candidate: (
                -int(candidate.get("Prestige", 0) or 0),
                candidate.get("Championship", ""),
                candidate.get("Sub_Champ", ""),
            ),
        )
        display_row = dict(group_rows[0])
        full_group_rows = [
            _public_championship_row(candidate)
            for candidate in all_rows
            if _championship_group_key(candidate) == _championship_group_key(display_row)
        ] or [_public_championship_row(display_row)]
        player_entry_rows = [_public_championship_row(candidate) for candidate in group_rows]
        if len(player_entry_rows) > 1:
            display_row["Sub_Champ"] = " / ".join(
                str(candidate.get("Sub_Champ", "")).strip()
                for candidate in player_entry_rows
                if str(candidate.get("Sub_Champ", "")).strip()
            )
        display_row["_entry_rows"] = full_group_rows
        display_row["_player_entry_rows"] = player_entry_rows
        merged_rows.append(display_row)
    return merged_rows


def _style_limits_from_reserved_world(
    rows: list[dict[str, str]],
    reserved_instances: list[dict],
) -> dict[str, int]:
    row_id_to_group = {
        str(row.get("id", "")).strip(): _championship_group_key(row)
        for row in rows
        if str(row.get("id", "")).strip()
    }
    reserved_keys = {
        (
            str((instance.get("championship") or {}).get("Championship_ID", "")).strip()
            or row_id_to_group.get(str((instance.get("championship") or {}).get("id", "")).strip(), "")
            or str((instance.get("championship") or {}).get("id", "")).strip(),
            _display_style(str((instance.get("championship") or {}).get("Style", "")).strip()),
        )
        for instance in reserved_instances
        if isinstance(instance, dict)
    }
    limits: dict[str, int] = {}
    for row in rows:
        style_name = _display_style(str(row.get("Style", "")).strip())
        championship_key = str(row.get("Championship_ID", "") or row.get("id", "")).strip()
        if (championship_key, style_name) in reserved_keys:
            continue
        limits[style_name] = max(limits.get(style_name, 0), int(row.get("Prestige", 0) or 0))
    return limits


def load_championships(
    save_name: str | None = None,
    player_names: list[str] | None = None,
    game: str = "iRacing",
    eligible_cars_by_id: dict[str, list[dict[str, str]]] | None = None,
) -> list[dict[str, str]]:
    championships = []
    style_prestige_limits: dict[str, int] = {}
    saved_style_limits: dict[str, int] = {}
    if save_name and player_names:
        save_data = load_save(save_name) or {}
        ignore_saved_limits = players_are_fresh_rookies(save_name, player_names)
        raw_limits = {} if ignore_saved_limits else save_data.get("offseason_player_style_limits")
        if isinstance(raw_limits, dict):
            for raw_style, raw_limit in raw_limits.items():
                try:
                    saved_style_limits[_display_style(str(raw_style))] = int(raw_limit)
                except (TypeError, ValueError):
                    continue
    rows = championship_rows(game)
    if save_name and player_names and not saved_style_limits:
        saved_style_limits = _style_limits_from_reserved_world(
            rows,
            list((save_data if "save_data" in locals() else {}).get("offseason_world_instances") or []),
        )
    candidate_rows: list[dict[str, str]] = []
    for row in rows:
        row["_player_entry_rows"] = _player_entry_rows_from_loaded_rows(row, rows)
        row_prestige = int(row.get("Prestige", 0) or 0)
        style_name = _display_style(str(row.get("Style", "")).strip())
        if save_name and player_names:
            if style_name not in style_prestige_limits:
                calculated_limit = player_entry_prestige_for_style(
                    save_name,
                    player_names,
                    style_name,
                    championship_rows=rows,
                    game=game,
                )
                if style_name in saved_style_limits:
                    style_prestige_limits[style_name] = max(saved_style_limits[style_name], calculated_limit)
                else:
                    style_prestige_limits[style_name] = calculated_limit
            if row_prestige > style_prestige_limits[style_name] and row_prestige != 1:
                continue
        row_id = str(row.get("id", "")).strip()
        eligible_cars = None
        if eligible_cars_by_id is not None and row_id:
            eligible_cars = eligible_cars_by_id.get(row_id)
        if eligible_cars is None:
            eligible_cars = get_eligible_player_cars(row, game)
            if eligible_cars_by_id is not None and row_id:
                eligible_cars_by_id[row_id] = eligible_cars
        if not eligible_cars:
            continue
        candidate_rows.append(row)
    championships = _merge_player_championship_rows(candidate_rows, rows)
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in championships:
        grouped.setdefault(_display_style(row.get("Style", "")), []).append(row)

    ordered: list[dict[str, str]] = []
    for style_name in sorted(grouped):
        ordered.extend(
            sorted(
                grouped[style_name],
                key=lambda row: (
                    -int(row.get("Prestige", 0) or 0),
                    row.get("Championship", ""),
                    row.get("Sub_Champ", ""),
                ),
            )
        )
    return ordered


class ChampionshipScreen(ctk.CTkFrame):
    def __init__(self, parent, show_screen) -> None:
        super().__init__(parent, fg_color="transparent")
        self.show_screen = show_screen
        self.parent = parent
        self.selected: dict[str, str] | None = None
        self.preview_cars: dict[str, dict[str, str]] = {}
        self.offer_rows: list[dict[str, str]] = []
        self.offer_rows_cache_key: tuple | None = None
        self.effective_mmr_cache: dict[str, int] = {}
        self.row_frames: dict[str, ctk.CTkFrame] = {}
        self.selected_style: str | None = None
        self.selected_series_key: str | None = None
        self.save_name: str | None = None
        self.player_names: list[str] = []
        self.current_tier = 1
        self.starting_difficulty = 75
        self.save_game = "iRacing"
        self.current_team_offer: dict | None = None
        self.current_championship_prestige = 0
        self.season_summary_message = ""
        self.season_summary_color = "gray"
        self._asset_file_cache: dict[str, list[Path]] = {}
        self._ctk_image_cache: dict[tuple[str, int, int], ctk.CTkImage] = {}

        hero = ctk.CTkFrame(self, fg_color=CARD_DEEP, corner_radius=18)
        hero.pack(fill="x", padx=18, pady=(16, 10))
        title_stack = ctk.CTkFrame(hero, fg_color="transparent")
        title_stack.pack(side="left", fill="x", expand=True, padx=18, pady=12)
        ctk.CTkLabel(
            title_stack,
            text="CHAMPIONSHIP OFFERS",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=ACCENT,
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_stack,
            text="Select Championship",
            font=ctk.CTkFont(size=26, weight="bold"),
            anchor="w",
        ).pack(anchor="w")
        self.subtitle = ctk.CTkLabel(title_stack, text="", font=ctk.CTkFont(size=12), text_color=MUTED, anchor="w")
        self.subtitle.pack(anchor="w", fill="x", pady=(2, 0))

        summary_stack = ctk.CTkFrame(hero, fg_color="transparent")
        summary_stack.pack(side="right", padx=18, pady=12)
        self.tier_label = ctk.CTkLabel(
            summary_stack,
            text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=ACCENT,
            anchor="e",
        )
        self.tier_label.pack(anchor="e")
        self.mmr_label = ctk.CTkLabel(summary_stack, text="", font=ctk.CTkFont(size=11), text_color=MUTED, anchor="e")
        self.mmr_label.pack(anchor="e", pady=(4, 0))

        self.list_frame = ctk.CTkScrollableFrame(self, width=1120, height=550, fg_color=("gray90", "gray14"))
        self.list_frame.pack(fill="both", expand=True, padx=18, pady=(0, 8))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=18, pady=(0, 10))
        self.status_label = ctk.CTkLabel(footer, text="", font=ctk.CTkFont(size=11), text_color="#ff5555", anchor="w")
        self.status_label.pack(side="left", fill="x", expand=True)

        button_frame = ctk.CTkFrame(footer, fg_color="transparent")
        button_frame.pack(side="right")

        self.start_btn = ctk.CTkButton(
            button_frame,
            text="Start Championship",
            command=self.start_selected_championship,
            height=38,
            width=200,
            font=ctk.CTkFont(size=13, weight="bold"),
            state="disabled",
            fg_color=SUCCESS,
            hover_color=SUCCESS_DARK,
        )
        self.start_btn.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            button_frame,
            text="Main Menu",
            command=lambda: show_screen("MenuScreen"),
            height=38,
            width=120,
            fg_color="gray30",
            hover_color="gray40",
            font=ctk.CTkFont(size=12),
        ).pack(side="left")

    def on_show(self) -> None:
        self.selected_style = None
        self.selected_series_key = None
        self.selected = None
        self.start_btn.configure(state="disabled", text="Start Championship")
        if self.save_name:
            save_data = load_save(self.save_name) or {}
            self.player_names = save_data.get("players", self.player_names)
            self.current_tier = self._normalize_unlocked_tier(
                save_data.get("unlocked_tier", save_data.get("unlocked_tiers")),
                save_data.get("tier", self.current_tier),
            )
            self.starting_difficulty = int(save_data.get("starting_difficulty", self.starting_difficulty))
            self.save_game = str(save_data.get("game", "iRacing"))
            self.current_team_offer = save_data.get("player_team_offer") if isinstance(save_data.get("player_team_offer"), dict) else None
            current_championship = save_data.get("championship") if isinstance(save_data.get("championship"), dict) else {}
            self.current_championship_prestige = int(current_championship.get("Prestige", 0) or 0)
        if self.save_name:
            self.subtitle.configure(
                text=f"Save: {self.save_name} | Game: {self.save_game} | Drivers: {', '.join(self.player_names) or self.save_name}"
            )
        self.tier_label.configure(text=self._unlock_summary_text())
        self.effective_mmr_cache = {}
        self.mmr_label.configure(text=self._effective_mmr_summary_text())
        cache_key = self._current_offer_cache_key()
        rebuild = cache_key != self.offer_rows_cache_key
        if str(self.save_game).strip().casefold() == "iracing" and self.offer_rows:
            rebuild = rebuild or any(not str(offer.get("_offer_team_colors", "")).strip() for offer in self.offer_rows)
        self.refresh_list(rebuild=rebuild)

    def _fit_cell_text(self, value: str, max_chars: int) -> str:
        text = str(value)
        if len(text) <= max_chars:
            return text
        return f"{text[: max_chars - 3]}..."

    def refresh_list(self, rebuild: bool = False) -> None:
        for widget in self.list_frame.winfo_children():
            widget.destroy()

        if rebuild:
            self.selected = None
            self.start_btn.configure(state="disabled", text="Start Championship")
        self.row_frames = {}
        self.status_label.configure(text=self.season_summary_message, text_color=self.season_summary_color)

        if rebuild or not self.offer_rows:
            self.offer_rows = self._build_offer_rows()
            self.offer_rows_cache_key = self._current_offer_cache_key()
        if not self.offer_rows:
            ctk.CTkLabel(
                self.list_frame,
                text="No owned championships found for your current prestige range.",
                font=ctk.CTkFont(size=12),
                text_color="gray",
            ).pack(pady=20)
            return

        if self.selected_style and self.selected_series_key:
            self._render_style_offers(self.selected_style)
        elif self.selected_style:
            self._render_series_summary(self.selected_style)
        else:
            self._render_style_summary()

    def _build_offer_rows(self) -> list[dict[str, str]]:
        offer_rows: list[dict[str, str]] = []
        self.preview_cars = {}
        eligible_cars_by_id: dict[str, list[dict[str, str]]] = {}
        championships = load_championships(
            save_name=self.save_name,
            player_names=self.player_names,
            game=self.save_game,
            eligible_cars_by_id=eligible_cars_by_id,
        )
        reputations = team_reputation_map(self.save_name or "") if self.save_name else {}
        seen_offer_ids: set[str] = set()
        for championship in championships:
            eligible_cars = get_eligible_player_cars(championship, self.save_game)
            if not eligible_cars:
                continue
            style_name = _display_style(str(championship.get("Style", "")).strip())
            offers = team_offers_for_player(
                self.save_name or "",
                self.player_names,
                championship,
                player_effective_mmr=self._effective_mmr_for_style(style_name),
                reputation_map=reputations,
            ) or [{"team_id": "", "team_key": "", "team_name": "Independent", "team_prestige": 0, "team_reputation": 50}]
            current_offer = current_team_offer_for_championship(
                self.save_name or "",
                self.current_team_offer,
                championship,
                reputation_map=reputations,
            )
            if current_offer:
                current_offer = dict(current_offer)
                championship_prestige = int(championship.get("Prestige", 0) or 0)
                current_offer["offer_note"] = "Promotion" if championship_prestige > self.current_championship_prestige else "Current"
                current_key = str(current_offer.get("team_key", "")).strip()
                current_id = str(current_offer.get("team_id", "")).strip()
                offers = [
                    offer
                    for offer in offers
                    if str(offer.get("team_key", "")).strip() != current_key
                    and str(offer.get("team_id", "")).strip() != current_id
                ]
                offers.insert(0, current_offer)
                offers = offers[:5]
            for offer_index, offer in enumerate(offers, start=1):
                offer_row = dict(championship)
                offer_id = f"{str(championship['id']).strip()}|{str(offer.get('team_id', '')).strip()}|{offer_index}"
                if offer_id in seen_offer_ids:
                    continue
                seen_offer_ids.add(offer_id)
                preview_car = dict(random.choice(eligible_cars))
                if str(self.save_game).strip().casefold() == "ams2":
                    preview_livery = preview_player_livery_for_car(preview_car)
                    if preview_livery:
                        preview_car["_preview_livery_name"] = str(preview_livery.get("livery_name", "")).strip()
                        preview_car["_preview_roster_name"] = str(preview_livery.get("Roster_Name", "")).strip()
                        preview_car["_preview_livery_class"] = str(preview_livery.get("Class", "")).strip()
                        preview_car["_preview_livery_car_name"] = str(preview_livery.get("Car_Name", "")).strip()
                entry_label = (
                    str(preview_car.get("Car class", "")).strip()
                    or str(preview_car.get("Car", "")).strip()
                    or str(championship.get("Sub_Champ", "")).strip()
                    or "-"
                )
                offer_row["_offer_id"] = offer_id
                offer_row["_offer_style"] = style_name
                offer_row["_entry_label"] = entry_label
                offer_row["_offer_team_id"] = str(offer.get("team_id", "")).strip()
                offer_row["_offer_team_key"] = str(offer.get("team_key", "")).strip()
                offer_row["_offer_team_name"] = str(offer.get("team_name", "")).strip() or "Independent"
                offer_row["_offer_team_prestige"] = str(offer.get("team_prestige", 0))
                offer_row["_offer_team_reputation"] = str(offer.get("team_reputation", offer.get("team_prestige", 50)))
                offer_row["_offer_note"] = str(offer.get("offer_note", "Offer")).strip() or "Offer"
                if str(self.save_game).strip().casefold() == "iracing":
                    csv_colors = str(offer.get("team_colors", "")).strip()
                    color_seed = (
                        str(offer_row.get("_offer_team_key", "")).strip()
                        or str(offer_row.get("_offer_team_id", "")).strip()
                        or str(offer_row.get("_offer_team_name", "")).strip()
                    )
                    offer_row["_offer_team_colors"] = csv_colors or team_color_set(color_seed)
                offer_rows.append(offer_row)
                self.preview_cars[offer_id] = preview_car
        return offer_rows

    def _render_style_summary(self) -> None:
        grouped: dict[str, list[dict[str, str]]] = {}
        for offer in self.offer_rows:
            grouped.setdefault(str(offer.get("_offer_style", "Other")), []).append(offer)

        ctk.CTkLabel(
            self.list_frame,
            text="Choose a racing discipline to view your available team offers.",
            font=ctk.CTkFont(size=11),
            text_color=MUTED,
            anchor="w",
        ).pack(fill="x", padx=12, pady=(4, 6))

        for style_name in self._sorted_styles(grouped.keys()):
            offers = grouped[style_name]
            card = ctk.CTkFrame(self.list_frame, fg_color=ROW, corner_radius=14)
            card.pack(fill="x", padx=10, pady=3)
            stripe = ctk.CTkFrame(card, fg_color=ACCENT, width=5, corner_radius=4)
            stripe.pack(side="left", fill="y", padx=(0, 10), pady=5)
            text_stack = ctk.CTkFrame(card, fg_color="transparent")
            text_stack.pack(side="left", fill="both", expand=True, pady=6)
            ctk.CTkLabel(
                text_stack,
                text=style_name,
                font=ctk.CTkFont(size=15, weight="bold"),
                anchor="w",
            ).pack(anchor="w")
            ctk.CTkLabel(
                text_stack,
                text=f"Active MMR fit: {self._effective_mmr_for_style(style_name)}",
                font=ctk.CTkFont(size=10),
                text_color=MUTED,
                anchor="w",
            ).pack(anchor="w", pady=(0, 0))
            count_stack = ctk.CTkFrame(card, fg_color="transparent")
            count_stack.pack(side="left", padx=12)
            ctk.CTkLabel(
                count_stack,
                text=str(len(offers)),
                font=ctk.CTkFont(size=21, weight="bold"),
                text_color=("#15507d", "#7dbdff"),
            ).pack()
            ctk.CTkLabel(
                count_stack,
                text="offers",
                font=ctk.CTkFont(size=9, weight="bold"),
                text_color=MUTED,
            ).pack()
            ctk.CTkButton(
                card,
                text="View",
                command=lambda value=style_name: self.view_style(value),
                height=26,
                width=86,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color=ACCENT_DARK,
                hover_color="#103d62",
            ).pack(side="right", padx=10, pady=6)

    def _render_series_summary(self, style_filter: str) -> None:
        style_offers = [
            offer
            for offer in self.offer_rows
            if str(offer.get("_offer_style", "")).strip() == style_filter
        ]
        grouped: dict[str, list[dict[str, str]]] = {}
        for offer in style_offers:
            grouped.setdefault(self._offer_series_key(offer), []).append(offer)

        top_row = ctk.CTkFrame(self.list_frame, fg_color=CARD_DEEP, corner_radius=14)
        top_row.pack(fill="x", padx=10, pady=(6, 10))
        title_stack = ctk.CTkFrame(top_row, fg_color="transparent")
        title_stack.pack(side="left", fill="x", expand=True, padx=14, pady=12)
        ctk.CTkLabel(
            title_stack,
            text=f"{style_filter} Series",
            font=ctk.CTkFont(size=20, weight="bold"),
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_stack,
            text="Pick a series first, then choose which team offer to accept.",
            font=ctk.CTkFont(size=11),
            text_color=MUTED,
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))
        ctk.CTkButton(
            top_row,
            text="<- Styles",
            command=self.show_style_summary,
            height=34,
            width=100,
            fg_color="gray30",
            hover_color="gray40",
            font=ctk.CTkFont(size=12),
        ).pack(side="right", padx=14)

        ordered_groups = sorted(
            grouped.values(),
            key=lambda offers: (
                -max(int(offer.get("Prestige", 0) or 0) for offer in offers),
                offers[0].get("Championship", ""),
                offers[0].get("Sub_Champ", ""),
            ),
        )
        for offers in ordered_groups:
            representative = offers[0]
            preview_car = self.preview_cars.get(str(representative.get("_offer_id", "")).strip(), {})
            card = ctk.CTkFrame(self.list_frame, fg_color=ROW, corner_radius=14)
            card.pack(fill="x", padx=10, pady=5)
            ctk.CTkFrame(card, fg_color=ACCENT, width=5, corner_radius=4).pack(
                side="left", fill="y", padx=(0, 12), pady=8
            )
            text_stack = ctk.CTkFrame(card, fg_color="transparent")
            text_stack.pack(side="left", fill="x", expand=True, pady=10)
            ctk.CTkLabel(
                text_stack,
                text=representative.get("Championship", "Championship"),
                font=ctk.CTkFont(size=16, weight="bold"),
                anchor="w",
            ).pack(anchor="w")
            details = [
                str(representative.get("Sub_Champ", "")).strip(),
                str(preview_car.get("Car", "")).strip(),
                f"{representative.get('Num of Races', '-')} races",
                f"{representative.get('Race_Time', '-')} min",
            ]
            ctk.CTkLabel(
                text_stack,
                text=" | ".join(value for value in details if value),
                font=ctk.CTkFont(size=11),
                text_color=MUTED,
                anchor="w",
            ).pack(anchor="w", pady=(2, 0))

            count_stack = ctk.CTkFrame(card, fg_color="transparent")
            count_stack.pack(side="left", padx=14)
            ctk.CTkLabel(
                count_stack,
                text=str(len(offers)),
                font=ctk.CTkFont(size=23, weight="bold"),
                text_color=("#15507d", "#7dbdff"),
            ).pack()
            ctk.CTkLabel(
                count_stack,
                text="team offers",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=MUTED,
            ).pack()
            ctk.CTkButton(
                card,
                text="View Teams",
                command=lambda key=self._offer_series_key(representative): self.view_offer_series(key),
                height=32,
                width=112,
                font=ctk.CTkFont(size=12, weight="bold"),
                fg_color=ACCENT_DARK,
                hover_color="#103d62",
            ).pack(side="right", padx=12, pady=10)

    def _render_style_offers(self, style_filter: str) -> None:
        style_offers = [
            offer
            for offer in self.offer_rows
            if str(offer.get("_offer_style", "")).strip() == style_filter
            and self._offer_series_key(offer) == self.selected_series_key
        ]
        style_offers.sort(
            key=lambda row: (
                -int(row.get("Prestige", 0) or 0),
                row.get("Championship", ""),
                row.get("Sub_Champ", ""),
                0 if row.get("_offer_note") in {"Current", "Promotion"} else 1,
                -int(row.get("_offer_team_reputation", row.get("_offer_team_prestige", 0)) or 0),
                row.get("_offer_team_name", ""),
            )
        )

        top_row = ctk.CTkFrame(self.list_frame, fg_color=CARD_DEEP, corner_radius=14)
        top_row.pack(fill="x", padx=10, pady=(6, 10))
        title_stack = ctk.CTkFrame(top_row, fg_color="transparent")
        title_stack.pack(side="left", fill="x", expand=True, padx=14, pady=12)
        ctk.CTkLabel(
            title_stack,
            text=style_offers[0].get("Championship", f"{style_filter} Offers") if style_offers else f"{style_filter} Offers",
            font=ctk.CTkFont(size=20, weight="bold"),
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_stack,
            text=f"{style_filter} | {len(style_offers)} team offers, sorted by best current fit.",
            font=ctk.CTkFont(size=11),
            text_color=MUTED,
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))
        ctk.CTkButton(
            top_row,
            text="<- Series",
            command=self.show_style_series,
            height=34,
            width=100,
            fg_color="gray30",
            hover_color="gray40",
            font=ctk.CTkFont(size=12),
        ).pack(side="right", padx=14)

        for offer_row in style_offers:
            self.add_row(offer_row)

    def view_style(self, style_name: str) -> None:
        self.selected_style = style_name
        self.selected_series_key = None
        self.selected = None
        self.start_btn.configure(state="disabled", text="Start Championship")
        self.refresh_list(rebuild=False)

    def view_offer_series(self, series_key: str) -> None:
        self.selected_series_key = series_key
        self.selected = None
        self.start_btn.configure(state="disabled", text="Start Championship")
        self.refresh_list(rebuild=False)

    def show_style_series(self) -> None:
        self.selected_series_key = None
        self.selected = None
        self.start_btn.configure(state="disabled", text="Start Championship")
        self.refresh_list(rebuild=False)

    def show_style_summary(self) -> None:
        self.selected_style = None
        self.selected_series_key = None
        self.selected = None
        self.start_btn.configure(state="disabled", text="Start Championship")
        self.refresh_list(rebuild=False)

    def add_row(self, championship: dict[str, str]) -> None:
        championship_id = str(championship.get("_offer_id") or championship["id"]).strip()
        preview_car = self.preview_cars.get(championship_id, {})
        row = ctk.CTkFrame(self.list_frame, fg_color=ROW, corner_radius=16)
        row.pack(fill="x", padx=10, pady=7)
        self.row_frames[championship_id] = row

        stripe_color = ACCENT
        if championship.get("_offer_note") == "Current":
            stripe_color = SUCCESS
        elif championship.get("_offer_note") == "Promotion":
            stripe_color = "#d7982d"
        ctk.CTkFrame(row, fg_color=stripe_color, width=5, corner_radius=4).pack(
            side="left", fill="y", padx=(0, 12), pady=10
        )

        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True, padx=(0, 8), pady=12)

        title_line = ctk.CTkFrame(info, fg_color="transparent")
        title_line.pack(fill="x")
        self._pill(title_line, championship.get("_offer_note", "Offer"), stripe_color).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            title_line,
            text=championship["Championship"],
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        team_name = str(championship.get("_offer_team_name", "Independent")).strip() or "Independent"
        ctk.CTkLabel(
            info,
            text=team_name,
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=("#111111", "#ffffff"),
            anchor="w",
        ).pack(fill="x", pady=(6, 1))
        ctk.CTkLabel(
            info,
            text=f"Team reputation: {championship.get('_offer_team_reputation', '50')}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("#15507d", "#7dbdff"),
            anchor="w",
        ).pack(fill="x", pady=(0, 8))

        details = ctk.CTkFrame(info, fg_color="transparent")
        details.pack(fill="x")
        self._detail_chip(details, "Car", preview_car.get("Car", "-")).pack(side="left", padx=(0, 6))
        self._detail_chip(details, "Races", championship["Num of Races"]).pack(side="left", padx=(0, 6))
        self._detail_chip(details, "Time", f"{championship['Race_Time']} min").pack(side="left", padx=(0, 6))

        visual = ctk.CTkFrame(row, fg_color="transparent")
        visual.pack(side="right", padx=(4, 12), pady=6)
        self._car_preview_frame(visual, preview_car, championship).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            visual,
            text="Select",
            command=lambda value=championship: self.select_championship(value),
            height=34,
            width=86,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=ACCENT_DARK,
            hover_color="#103d62",
        ).pack(side="left")

        for widget in (row, info, title_line, details):
            widget.bind("<Button-1>", lambda _event, value=championship: self.select_championship(value))

    def _pill(self, parent, text: str, color: str) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color=color, corner_radius=10)
        ctk.CTkLabel(
            frame,
            text=str(text),
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="white",
        ).pack(padx=8, pady=2)
        return frame

    def _offer_series_key(self, offer: dict[str, str]) -> str:
        return (
            str(offer.get("Championship_ID", "")).strip()
            or str(offer.get("id", "")).strip()
            or str(offer.get("Championship", "")).strip()
        )

    def _detail_chip(self, parent, label: str, value: str) -> ctk.CTkFrame:
        chip = ctk.CTkFrame(parent, fg_color=("gray87", "gray17"), corner_radius=10)
        ctk.CTkLabel(
            chip,
            text=str(label).upper(),
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color=MUTED,
        ).pack(side="left", padx=(8, 5), pady=5)
        ctk.CTkLabel(
            chip,
            text=self._fit_cell_text(str(value), 30),
            font=ctk.CTkFont(size=11, weight="bold"),
        ).pack(side="left", padx=(0, 8), pady=5)
        return chip

    def _car_preview_frame(self, parent, car: dict[str, str], championship: dict[str, str]) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color=("gray86", "gray18"), corner_radius=12, width=315, height=128)
        frame.pack_propagate(False)
        self._car_image_label(frame, car).pack(side="left", padx=(10, 0), pady=8)
        if str(self.save_game).strip().casefold() == "iracing":
            colors = self._offer_colors(championship)
            if colors:
                swatches = ctk.CTkFrame(frame, fg_color="transparent")
                swatches.pack(side="left", padx=(8, 6), pady=8)
                ctk.CTkLabel(swatches, text="Team", font=ctk.CTkFont(size=9, weight="bold"), text_color="gray").pack()
                for color in colors:
                    ctk.CTkFrame(
                        swatches,
                        fg_color=f"#{color}",
                        width=30,
                        height=28,
                        corner_radius=4,
                        border_width=1,
                        border_color=("gray70", "gray25"),
                    ).pack(pady=2)
        return frame

    def _car_image_label(self, parent, car: dict[str, str]) -> ctk.CTkLabel:
        image = self._load_car_image(car, (212, 116))
        if image is None:
            return ctk.CTkLabel(parent, text="", width=212)
        return ctk.CTkLabel(parent, text="", image=image, width=212)

    def _offer_colors(self, championship: dict[str, str]) -> list[str]:
        raw_colors = str(championship.get("_offer_team_colors", "")).strip()
        if not raw_colors and str(self.save_game).strip().casefold() == "iracing":
            color_seed = (
                str(championship.get("_offer_team_key", "")).strip()
                or str(championship.get("_offer_team_id", "")).strip()
                or str(championship.get("_offer_team_name", "")).strip()
                or "Independent"
            )
            raw_colors = team_color_set(color_seed)
        colors = [color.strip().upper().lstrip("#") for color in raw_colors.split(",") if color.strip()]
        return [color for color in colors if re.fullmatch(r"[0-9A-Fa-f]{6}", color)]

    def _load_car_image(self, car: dict[str, str], size: tuple[int, int]) -> ctk.CTkImage | None:
        path = self._best_car_image(car)
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

    def _best_car_image(self, car: dict[str, str]) -> Path | None:
        candidates = [
            str(car.get("_preview_livery_name", "")).strip(),
            str(car.get("_preview_livery_car_name", "")).strip(),
            str(car.get("image file", "")).strip(),
            str(car.get("Car", "")).strip(),
            str(car.get("FILEPATH", "")).strip(),
            str(car.get("ams2_livery_folder", "")).strip(),
            str(car.get("Car class", "")).strip(),
        ]
        normalized_candidates = [self._asset_key(candidate) for candidate in candidates if self._asset_key(candidate)]
        if not normalized_candidates:
            return None

        root = resource_path("assets", "Cars", self._asset_game_folder())
        best_path: Path | None = None
        best_score = 0
        for path in self._car_asset_files():
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

    def _car_asset_files(self) -> list[Path]:
        game_folder = self._asset_game_folder()
        if game_folder in self._asset_file_cache:
            return self._asset_file_cache[game_folder]
        root = resource_path("assets", "Cars", game_folder)
        if not root.exists():
            self._asset_file_cache[game_folder] = []
            return []
        files = [path for path in root.rglob("*") if path.is_file() and path.suffix.casefold() in IMAGE_EXTENSIONS]
        self._asset_file_cache[game_folder] = files
        return files

    def _asset_game_folder(self) -> str:
        return "AMS2" if str(self.save_game).strip().casefold() == "ams2" else "Iracing"

    @staticmethod
    def _asset_key(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(value).casefold())

    def select_championship(self, championship: dict[str, str]) -> None:
        self.selected = championship
        selected_id = str(championship.get("_offer_id") or championship["id"]).strip()
        self.start_btn.configure(
            state="normal",
            text=f"Start {self._fit_cell_text(championship['Championship'], 18)}",
        )
        for championship_id, row in self.row_frames.items():
            row.configure(fg_color=SELECTED_ROW if championship_id == selected_id else ROW)
        preview_car = self.preview_cars.get(selected_id, {})
        self.status_label.configure(
            text=(
                f"Selected: {championship['Championship']} | "
                f"{championship.get('_offer_note', 'Offer')} | "
                f"{championship.get('_offer_team_name', 'Independent')} | "
                f"{preview_car.get('Car', 'No eligible car')} | {championship['Style']}"
            ),
            text_color="gray",
        )
        self.season_summary_message = ""

    def start_selected_championship(self) -> None:
        if not self.selected or not self.save_name:
            self.status_label.configure(text="Please select a championship.", text_color="#ff5555")
            return

        selected_id = str(self.selected.get("_offer_id") or self.selected["id"]).strip()
        championship_to_start = dict(self.selected)
        championship_to_start["Pool_Championship"] = championship_pool_display_name(championship_to_start)
        championship_to_start["unlocked_tier"] = str(self.current_tier)
        championship_to_start["player_team_offer"] = {
            "team_id": str(self.selected.get("_offer_team_id", "")).strip(),
            "team_key": str(self.selected.get("_offer_team_key", "")).strip(),
            "team_name": str(self.selected.get("_offer_team_name", "")).strip() or "Independent",
            "team_prestige": int(self.selected.get("_offer_team_prestige", 0) or 0),
            "team_reputation": int(self.selected.get("_offer_team_reputation", 50) or 50),
            "team_colors": ",".join(self._offer_colors(self.selected)),
        }
        self.season_summary_message = ""
        setup_screen = self.parent.screens["WorldSetupScreen"]
        if hasattr(setup_screen, "set_request"):
            setup_screen.set_request(
                self.save_name,
                championship_to_start,
                self.player_names,
                self.preview_cars.get(selected_id),
                self.starting_difficulty,
            )
        self.show_screen("WorldSetupScreen")

    def _unlock_summary_text(self) -> str:
        return "Championship access is based on current MMR fit."

    def _effective_mmr_for_style(self, style_name: str) -> int:
        if not self.save_name or not self.player_names:
            return 1000
        if style_name not in self.effective_mmr_cache:
            self.effective_mmr_cache[style_name] = player_effective_mmr_for_style(self.save_name, self.player_names, style_name)
        return self.effective_mmr_cache[style_name]

    def _effective_mmr_summary_text(self) -> str:
        if not self.save_name or not self.player_names:
            return "Effective MMR: -"
        parts = [
            f"{style}: {self._effective_mmr_for_style(style)}"
            for style in STYLE_ORDER
        ]
        return "Effective MMR: " + " | ".join(parts)

    def _current_offer_cache_key(self) -> tuple:
        mmr_values = tuple((style, self._effective_mmr_for_style(style)) for style in STYLE_ORDER)
        world_year = get_world_year(self.save_name) if self.save_name else 0
        current_team_key = ""
        if isinstance(self.current_team_offer, dict):
            current_team_key = (
                str(self.current_team_offer.get("team_key", "")).strip()
                or str(self.current_team_offer.get("team_id", "")).strip()
                or str(self.current_team_offer.get("team_name", "")).strip()
            )
        return (
            self.save_name,
            self.save_game,
            world_year,
            tuple(self.player_names),
            self.starting_difficulty,
            mmr_values,
            current_team_key,
            self.current_championship_prestige,
        )

    @staticmethod
    def _sorted_styles(styles) -> list[str]:
        return sorted(
            [str(style).strip() or "Other" for style in styles],
            key=lambda style: (
                STYLE_ORDER.index(style) if style in STYLE_ORDER else len(STYLE_ORDER),
                style,
            ),
        )

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
