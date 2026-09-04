from __future__ import annotations

import random
import re
from pathlib import Path

import customtkinter as ctk
from PIL import Image, ImageOps

from ..ams2_exporter import preview_player_livery_for_car
from ..custom_championships import championship_rows
from ..driver_pool import (
    current_team_promotion_is_earned,
    championship_pool_display_name,
    current_team_offer_for_championship,
    get_world_year,
    player_effective_mmr_for_style,
    players_are_fresh_rookies,
    team_reputation_map,
    team_offers_for_player,
)
from ..game_logic import get_eligible_player_cars, hydrate_active_rivals_state
from ..paths import resource_path
from ..roster_exporter import team_color_set
from ..save_manager import load_save, update_save


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
            # A multiclass/custom championship has one row per car. Show each
            # distinct class once instead of repeating the class for every car.
            class_labels: list[str] = []
            seen_class_labels: set[str] = set()
            for candidate in player_entry_rows:
                class_label = str(candidate.get("Sub_Champ", "")).strip()
                normalized_label = class_label.casefold()
                if class_label and normalized_label not in seen_class_labels:
                    seen_class_labels.add(normalized_label)
                    class_labels.append(class_label)
            if class_labels:
                display_row["Sub_Champ"] = " / ".join(class_labels)
        display_row["_entry_rows"] = full_group_rows
        display_row["_player_entry_rows"] = player_entry_rows
        merged_rows.append(display_row)
    return merged_rows


def _multiclass_offer_variants(championship: dict[str, str]) -> list[dict[str, str]]:
    """Create one offer-evaluation row per eligible class in a multiclass series."""
    entry_rows = championship.get("_player_entry_rows")
    if not isinstance(entry_rows, list) or len(entry_rows) < 2:
        return [championship]

    class_groups: dict[str, list[dict[str, str]]] = {}
    for row in entry_rows:
        class_name = str(row.get("Class_Name", "")).strip()
        if not class_name:
            sub_champ = str(row.get("Sub_Champ", "")).strip()
            class_name = sub_champ.split(":", 1)[-1].strip() if ":" in sub_champ else sub_champ
        class_name = class_name or "Overall"
        class_groups.setdefault(class_name.casefold(), []).append(dict(row))

    if len(class_groups) <= 1:
        return [championship]

    variants: list[dict[str, str]] = []
    for class_rows in class_groups.values():
        variant = dict(championship)
        class_name = str(class_rows[0].get("Class_Name", "")).strip()
        if not class_name:
            sub_champ = str(class_rows[0].get("Sub_Champ", "")).strip()
            class_name = sub_champ.split(":", 1)[-1].strip() if ":" in sub_champ else sub_champ
        variant["_player_entry_rows"] = class_rows
        variant["Sub_Champ"] = str(class_rows[0].get("Sub_Champ", "")).strip() or class_name
        variant["Class_Name"] = class_name
        variant["Prestige"] = str(class_rows[0].get("Prestige", variant.get("Prestige", "0")))
        variant["_offer_class_key"] = class_name
        variants.append(variant)
    return variants


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
    fresh_rookies = False
    if save_name and player_names:
        save_data = load_save(save_name) or {}
        fresh_rookies = players_are_fresh_rookies(save_name, player_names)
    career_path_id = str((save_data if "save_data" in locals() else {}).get("career_path_id", "default"))
    rows = championship_rows(game, career_path_id)
    # A fresh rookie should begin at the lowest prestige championship in each
    # discipline. Group-level checks allow every single-class series through
    # because each series is its own group, which makes the default path feel
    # almost completely unlocked at the start.
    minimum_prestige_by_style: dict[str, int] = {}
    for row in rows:
        style_name = _display_style(str(row.get("Style", "")).strip())
        row_prestige = int(row.get("Prestige", 0) or 0)
        minimum_prestige_by_style[style_name] = min(
            minimum_prestige_by_style.get(style_name, row_prestige),
            row_prestige,
        )
    candidate_rows: list[dict[str, str]] = []
    for row in rows:
        row["_player_entry_rows"] = _player_entry_rows_from_loaded_rows(row, rows)
        row_prestige = int(row.get("Prestige", 0) or 0)
        style_name = _display_style(str(row.get("Style", "")).strip())
        if (
            fresh_rookies
            and row_prestige > minimum_prestige_by_style.get(style_name, row_prestige)
            and row_prestige != 1
        ):
            continue
        row_id = str(row.get("id", "")).strip()
        eligible_cars = None
        if eligible_cars_by_id is not None and row_id:
            eligible_cars = eligible_cars_by_id.get(row_id)
        if eligible_cars is None:
            eligible_cars = get_eligible_player_cars(row, game, save_name)
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
        self.rivals_driver_var = ctk.StringVar(value="")
        self.rivals_driver_selector: ctk.CTkOptionMenu | None = None
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
        self.rivals_driver_selector = ctk.CTkOptionMenu(
            summary_stack,
            values=[],
            variable=self.rivals_driver_var,
            command=self._select_rivals_driver,
            width=180,
            height=30,
            font=ctk.CTkFont(size=11, weight="bold"),
        )

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
            save_data = hydrate_active_rivals_state(load_save(self.save_name) or {})
            all_players = save_data.get("all_players") or save_data.get("players", self.player_names)
            career_mode = str(save_data.get("career_mode", "")).strip()
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
            if career_mode == "Rivals" and len(all_players) > 1 and self.rivals_driver_selector is not None:
                self.rivals_driver_selector.configure(values=all_players)
                self.rivals_driver_var.set(str(save_data.get("active_player_name", self.player_names[0] if self.player_names else "")))
                if not self.rivals_driver_selector.winfo_ismapped():
                    self.rivals_driver_selector.pack(anchor="e", pady=(8, 0))
            elif self.rivals_driver_selector is not None and self.rivals_driver_selector.winfo_ismapped():
                self.rivals_driver_selector.pack_forget()
        if self.save_name:
            self.subtitle.configure(
                text=f"Save: {self.save_name} | Game: {self.save_game} | Drivers: {', '.join(self.player_names) or self.save_name}"
            )
        self.tier_label.configure(text=self._unlock_summary_text())
        self.effective_mmr_cache = {}
        self.mmr_label.configure(text=self._effective_mmr_summary_text())
        cache_key = self._current_offer_cache_key()
        rebuild = cache_key != self.offer_rows_cache_key
        if self.save_name and players_are_fresh_rookies(self.save_name, self.player_names):
            rebuild = True
        if str(self.save_game).strip().casefold() == "iracing" and self.offer_rows:
            rebuild = rebuild or any(not str(offer.get("_offer_team_colors", "")).strip() for offer in self.offer_rows)
        self.refresh_list(rebuild=rebuild)

    def _select_rivals_driver(self, player_name: str) -> None:
        if not self.save_name:
            return
        cleaned = str(player_name).strip()
        if not cleaned:
            return
        update_save(self.save_name, {"active_player_name": cleaned})
        save_data = hydrate_active_rivals_state(load_save(self.save_name) or {})
        if save_data.get("championship"):
            gameplay = self.parent.screens["GameplayScreen"]
            gameplay.load_state(save_data)
            self.show_screen("GameplayScreen")
            return
        self.offer_rows = []
        self.offer_rows_cache_key = None
        self.on_show()

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
        used_ams2_liveries_by_group: dict[str, set[str]] = {}
        offer_championships = [
            variant
            for championship in championships
            for variant in _multiclass_offer_variants(championship)
        ]
        for championship in offer_championships:
            eligible_cars = get_eligible_player_cars(championship, self.save_game, self.save_name)
            if not eligible_cars:
                continue
            championship_group_key = str(championship.get("Championship_ID", "") or championship.get("id", "")).strip()
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
                is_promotion = championship_prestige > self.current_championship_prestige
                if is_promotion and not current_team_promotion_is_earned(
                    self.save_name or "",
                    self.player_names,
                    self.current_team_offer,
                ):
                    current_offer = None
            if current_offer:
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
                class_key = str(championship.get("_offer_class_key", "")).strip()
                offer_id = f"{str(championship['id']).strip()}|{class_key}|{str(offer.get('team_id', '')).strip()}|{offer_index}"
                if offer_id in seen_offer_ids:
                    continue
                seen_offer_ids.add(offer_id)
                preview_car = self._preview_car_for_offer(
                    championship,
                    offer,
                    eligible_cars,
                    used_ams2_liveries_by_group.setdefault(championship_group_key, set()),
                )
                entry_label = (
                    str(championship.get("Class_Name", "")).strip()
                    or class_key
                    or str(preview_car.get("Car class", "")).strip()
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
                offer_row["_offer_seat_number"] = str(offer.get("seat_number", offer_index))
                offer_row["_offer_team_seat"] = str(offer.get("team_seat", "1"))
                offer_row["_offer_team_size"] = str(offer.get("team_size", "1"))
                offer_row["_offer_seat_quality"] = str(offer.get("seat_quality", offer.get("team_reputation", 50)))
                offer_row["_offer_team_personality"] = str(offer.get("team_personality", "")).strip()
                offer_row["_offer_team_ambition"] = str(offer.get("team_ambition", 50))
                offer_row["_offer_team_stability"] = str(offer.get("team_stability", 50))
                offer_row["_offer_team_development"] = str(offer.get("team_development", 50))
                offer_row["_offer_team_financial_strength"] = str(offer.get("team_financial_strength", 50))
                offer_row["_offer_team_pressure"] = str(offer.get("team_pressure", 50))
                offer_row["_offer_team_philosophy"] = str(offer.get("team_philosophy", "Balanced")).strip() or "Balanced"
                offer_row["_offer_team_trajectory"] = str(offer.get("trajectory", "stable")).strip() or "stable"
                offer_row["_offer_note"] = str(offer.get("offer_note", "Offer")).strip() or "Offer"
                offer_row["_offer_expectation"] = self._team_expectation_text(offer_row)
                offer_row["_offer_expectation_level"] = self._team_expectation_level(offer_row)
                offer_row["_offer_reason"] = self._team_offer_reason_text(offer_row)
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

    def _preview_car_for_offer(
        self,
        championship: dict[str, str],
        offer: dict[str, str],
        eligible_cars: list[dict[str, str]],
        used_ams2_liveries: set[str],
    ) -> dict[str, str]:
        if not eligible_cars:
            return {}
        assignment_key = "|".join(
            [
                str(self.save_name or "").strip(),
                str(championship.get("Championship_ID", "") or championship.get("id", "")).strip(),
                str(offer.get("team_key", "")).strip() or str(offer.get("team_id", "")).strip() or str(offer.get("team_name", "")).strip(),
                str(offer.get("seat_number", "")).strip(),
                str(offer.get("team_seat", "")).strip(),
            ]
        )
        ordered_cars = sorted(
            (dict(car) for car in eligible_cars),
            key=lambda car: (
                str(car.get("id", "")).strip(),
                str(car.get("Car", "")).strip().casefold(),
                str(car.get("Car class", "")).strip().casefold(),
            ),
        )
        seed = sum(ord(char) for char in assignment_key)
        preview_car = ordered_cars[seed % len(ordered_cars)] if assignment_key else dict(random.choice(ordered_cars))
        if str(self.save_game).strip().casefold() != "ams2":
            return preview_car
        preview_livery = preview_player_livery_for_car(
            preview_car,
            assignment_key=assignment_key,
            reserved_livery_names=used_ams2_liveries,
        )
        if preview_livery:
            preview_car["_preview_livery_name"] = str(preview_livery.get("livery_name", "")).strip()
            preview_car["_preview_roster_name"] = str(preview_livery.get("Roster_Name", "")).strip()
            preview_car["_preview_livery_class"] = str(preview_livery.get("Class", "")).strip()
            preview_car["_preview_livery_car_name"] = str(preview_livery.get("Car_Name", "")).strip()
            livery_name = str(preview_livery.get("livery_name", "")).strip()
            if livery_name:
                used_ams2_liveries.add(livery_name)
        return preview_car

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
                justify="left",
                wraplength=760,
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
        info.pack(side="left", fill="x", expand=True, padx=(0, 8), pady=12, anchor="n")

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
        ctk.CTkLabel(
            info,
            text=championship.get("_offer_reason", "Team interest is based on current fit."),
            font=ctk.CTkFont(size=11),
            text_color=MUTED,
            anchor="w",
            justify="left",
            wraplength=520,
        ).pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(
            info,
            text=championship.get("_offer_expectation", "Expectation: score points when possible."),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self._team_expectation_color(championship),
            anchor="w",
            justify="left",
            wraplength=520,
        ).pack(fill="x", pady=(0, 8))

        details = ctk.CTkFrame(info, fg_color="transparent")
        details.pack(fill="x")
        self._detail_chip(details, "Car", preview_car.get("Car", "-")).pack(side="left", padx=(0, 6))
        self._detail_chip(details, "Races", championship["Num of Races"]).pack(side="left", padx=(0, 6))
        self._detail_chip(details, "Time", f"{championship['Race_Time']} min").pack(side="left", padx=(0, 6))

        visual = ctk.CTkFrame(row, fg_color="transparent")
        visual.pack(side="right", padx=(4, 12), pady=10, anchor="n")
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
        frame = ctk.CTkFrame(parent, fg_color=("gray86", "gray18"), corner_radius=12, width=300, height=104)
        frame.pack_propagate(False)
        self._car_image_label(frame, car).pack(side="left", padx=(10, 0), pady=6)
        if str(self.save_game).strip().casefold() == "iracing":
            colors = self._offer_colors(championship)
            if colors:
                swatches = ctk.CTkFrame(frame, fg_color="transparent")
                swatches.pack(side="left", padx=(8, 6), pady=6)
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
        image = self._load_car_image(car, (196, 92))
        if image is None:
            return ctk.CTkLabel(parent, text="", width=196)
        return ctk.CTkLabel(parent, text="", image=image, width=196)

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
        iracing_assets = self._asset_game_folder().casefold() == "iracing"
        best_path: Path | None = None
        best_score = 0
        for path in self._car_asset_files():
            if iracing_assets and path.stem.casefold().endswith("_cutout"):
                continue
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
                f"{championship.get('_offer_reason', 'Team interest set')} | "
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
            "team_size": int(self.selected.get("_offer_team_size", 1) or 1),
            "seat_quality": int(self.selected.get("_offer_seat_quality", self.selected.get("_offer_team_reputation", 50)) or 50),
            "team_colors": ",".join(self._offer_colors(self.selected)),
            "team_personality": str(self.selected.get("_offer_team_personality", "")).strip(),
            "team_ambition": int(self.selected.get("_offer_team_ambition", 50) or 50),
            "team_stability": int(self.selected.get("_offer_team_stability", 50) or 50),
            "team_development": int(self.selected.get("_offer_team_development", 50) or 50),
            "team_financial_strength": int(self.selected.get("_offer_team_financial_strength", 50) or 50),
            "team_pressure": int(self.selected.get("_offer_team_pressure", 50) or 50),
            "team_philosophy": str(self.selected.get("_offer_team_philosophy", "Balanced")).strip() or "Balanced",
            "team_trajectory": str(self.selected.get("_offer_team_trajectory", "stable")).strip() or "stable",
            "offer_note": str(self.selected.get("_offer_note", "Offer")).strip() or "Offer",
            "team_offer_reason": str(self.selected.get("_offer_reason", "")).strip(),
            "team_expectation": str(self.selected.get("_offer_expectation", "")).strip(),
            "team_expectation_level": str(self.selected.get("_offer_expectation_level", "")).strip(),
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
        style_order = self._active_style_order()
        parts = [
            f"{style}: {self._effective_mmr_for_style(style)}"
            for style in style_order
        ]
        return "Effective MMR: " + " | ".join(parts)

    @classmethod
    def _team_expectation_text(cls, championship: dict[str, str]) -> str:
        level = cls._team_expectation_level(championship)
        races = cls._race_count(championship)
        if level == "wins":
            win_target = max(1, min(races, round(races * 0.30)))
            return f"Expectation: fight for wins, target {win_target}+ win{'s' if win_target != 1 else ''}."
        if level == "podiums":
            top_five_target = max(2, min(races, round(races * 0.60)))
            return f"Expectation: challenge up front, target {top_five_target}+ top 5s."
        if level == "top5":
            top_five_target = max(1, min(races, round(races * 0.40)))
            return f"Expectation: regular top 5s, target {top_five_target}+ strong finishes."
        if level == "top10":
            top_ten_target = max(2, min(races, round(races * 0.50)))
            return f"Expectation: bring home points, target {top_ten_target}+ top 10s."
        top_ten_target = max(1, min(races, round(races * 0.30)))
        return f"Expectation: build momentum, target {top_ten_target}+ top 10 finish{'es' if top_ten_target != 1 else ''}."

    @classmethod
    def _team_expectation_level(cls, championship: dict[str, str]) -> str:
        seat_quality = cls._offer_stat_value(
            championship,
            "_offer_seat_quality",
            cls._team_reputation_value(championship),
        )
        if seat_quality >= 90:
            return "wins"
        if seat_quality >= 78:
            return "podiums"
        if seat_quality >= 62:
            return "top5"
        if seat_quality >= 44:
            return "top10"
        return "development"

    @staticmethod
    def _team_expectation_color(championship: dict[str, str]) -> str:
        level = str(championship.get("_offer_expectation_level", "")).strip()
        return {
            "wins": "#ff7777",
            "podiums": "#ffb347",
            "top5": "#7dbdff",
            "top10": "#6bbd6b",
            "development": "gray",
        }.get(level, "gray")

    @staticmethod
    def _race_count(championship: dict[str, str]) -> int:
        try:
            return max(1, int(championship.get("Num of Races", 4) or 4))
        except (TypeError, ValueError):
            return 4

    @staticmethod
    def _team_reputation_value(championship: dict[str, str]) -> int:
        try:
            return int(championship.get("_offer_team_reputation", championship.get("_offer_team_prestige", 50)) or 50)
        except (TypeError, ValueError):
            return 50

    @staticmethod
    def _offer_stat_value(championship: dict[str, str], key: str, fallback: int = 50) -> int:
        try:
            return int(championship.get(key, fallback) or fallback)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _pressure_band(value: int) -> str:
        if value <= 40:
            return "low"
        if value >= 67:
            return "high"
        return "medium"

    @classmethod
    def _team_offer_reason_text(cls, championship: dict[str, str]) -> str:
        note = str(championship.get("_offer_note", "Offer")).strip() or "Offer"
        philosophy = str(championship.get("_offer_team_philosophy", "Balanced")).strip() or "Balanced"
        trajectory = str(championship.get("_offer_team_trajectory", "stable")).strip().title() or "Stable"
        ambition = cls._offer_stat_value(championship, "_offer_team_ambition")
        funds = cls._offer_stat_value(championship, "_offer_team_financial_strength")
        stability = cls._offer_stat_value(championship, "_offer_team_stability")
        pressure = cls._offer_stat_value(championship, "_offer_team_pressure")
        pressure_band = cls._pressure_band(pressure)

        if note == "Current":
            return f"Your current team is offering continuity. {trajectory} trajectory, {philosophy} philosophy."
        if note == "Promotion":
            return f"Your current team can move up with you. {trajectory} trajectory, {philosophy} philosophy."
        if note == "Aggressive Move":
            return f"This team is pushing hard in the market with ambition {ambition} and funding {funds}."
        if note == "Priority Target":
            return f"You are one of this team's top offseason targets. {philosophy} mindset, {trajectory} program."
        if note == "Safe Fit":
            return f"This is a steady seat with stability {stability} and lower market pressure at {pressure}."
        if ambition >= 70 and funds >= 70:
            return f"A fast-moving program with ambition {ambition}, funding {funds}, and a {trajectory.lower()} trend."
        if stability >= 65 and pressure <= 45:
            return f"A calmer long-term fit built on stability {stability} and manageable pressure."
        return f"{philosophy} philosophy, {trajectory.lower()} trajectory, and {pressure_band} team pressure shape this offer."

    def _current_offer_cache_key(self) -> tuple:
        mmr_values = tuple((style, self._effective_mmr_for_style(style)) for style in self._active_style_order())
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

    def _active_style_order(self) -> list[str]:
        if self.offer_rows:
            styles = {str(row.get("_offer_style", "")).strip() for row in self.offer_rows if str(row.get("_offer_style", "")).strip()}
            if styles:
                return self._sorted_styles(styles)
        save_data = load_save(self.save_name) if self.save_name else {}
        career_path_id = str((save_data or {}).get("career_path_id", "default"))
        styles = {
            _display_style(str(row.get("Style", "")).strip())
            for row in championship_rows(self.save_game, career_path_id)
            if str(row.get("Style", "")).strip()
        }
        if styles:
            return self._sorted_styles(styles)
        return list(STYLE_ORDER)

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
