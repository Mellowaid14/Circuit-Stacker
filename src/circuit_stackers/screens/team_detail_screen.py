from __future__ import annotations

import customtkinter as ctk
import re

from ..driver_pool import get_team_profile, rename_team
from ..game_logic import current_team_championships
from ..save_manager import load_save


class TeamDetailScreen(ctk.CTkFrame):
    def __init__(self, parent, show_screen) -> None:
        super().__init__(parent, fg_color="transparent")
        self.show_screen = show_screen
        self.save_name: str | None = None
        self.team_key: str | None = None
        self.back_screen = "TeamPoolScreen"

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(18, 8))
        self.title_label = ctk.CTkLabel(top, text="Team Details", font=ctk.CTkFont(size=22, weight="bold"))
        self.title_label.pack(side="left")
        ctk.CTkButton(
            top,
            text="<- Back",
            command=lambda: self.show_screen(self.back_screen),
            width=90,
            height=30,
            fg_color="gray30",
            hover_color="gray40",
            font=ctk.CTkFont(size=11),
        ).pack(side="right")
        ctk.CTkButton(
            top,
            text="Edit Name",
            command=self.edit_team_name,
            width=100,
            height=30,
            fg_color="gray30",
            hover_color="gray40",
            font=ctk.CTkFont(size=11),
        ).pack(side="right", padx=(0, 8))

        self.subtitle_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=11), text_color="gray")
        self.subtitle_label.pack(pady=(0, 8))

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        content.columnconfigure(0, weight=1)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        summary_box = self._make_box(content, "Team Summary")
        summary_box.grid(row=0, column=0, padx=(0, 8), sticky="nsew")
        self.summary_frame = ctk.CTkScrollableFrame(summary_box, fg_color="transparent")
        self.summary_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        history_box = self._make_box(content, "Championship History")
        history_box.grid(row=0, column=1, padx=(8, 0), sticky="nsew")
        self.history_frame = ctk.CTkScrollableFrame(history_box, fg_color="transparent")
        self.history_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def _make_box(self, parent, title: str) -> ctk.CTkFrame:
        box = ctk.CTkFrame(parent, fg_color=("gray88", "gray17"), corner_radius=10)
        ctk.CTkLabel(
            box,
            text=title,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("#1a6fc4", "#4da6ff"),
        ).pack(anchor="w", padx=10, pady=(8, 4))
        return box

    def _info_row(self, parent, label: str, value: str) -> None:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=1)
        ctk.CTkLabel(row, text=label, width=125, anchor="w", font=ctk.CTkFont(size=11), text_color="gray").pack(side="left")
        ctk.CTkLabel(row, text=value, anchor="w", font=ctk.CTkFont(size=11), justify="left").pack(side="left", fill="x", expand=True)

    def _section_label(self, parent, text: str) -> None:
        ctk.CTkLabel(
            parent,
            text=text,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=("#1a6fc4", "#4da6ff"),
            anchor="w",
        ).pack(fill="x", pady=(8, 2))

    def _color_swatches(self, parent, colors: list[str]) -> None:
        if not colors:
            return
        row = ctk.CTkFrame(parent, fg_color=("gray84", "gray20"), corner_radius=8)
        row.pack(fill="x", pady=(2, 8))
        ctk.CTkLabel(
            row,
            text="Team Colors:",
            width=125,
            anchor="w",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        ).pack(side="left", padx=(8, 0), pady=8)
        for color in colors:
            swatch = ctk.CTkFrame(
                row,
                fg_color=f"#{color}",
                width=34,
                height=22,
                corner_radius=5,
                border_width=1,
                border_color=("gray60", "gray30"),
            )
            swatch.pack(side="left", padx=4, pady=8)
            ctk.CTkLabel(row, text=f"#{color}", font=ctk.CTkFont(size=10), text_color=("gray25", "gray82")).pack(
                side="left", padx=(0, 8)
            )

    @staticmethod
    def _parse_colors(raw_colors: str) -> list[str]:
        colors = [color.strip().upper().lstrip("#") for color in str(raw_colors).split(",") if color.strip()]
        return [color for color in colors if re.fullmatch(r"[0-9A-F]{6}", color)]

    def set_context(self, save_name: str, team_key: str, back_screen: str = "TeamPoolScreen") -> None:
        self.save_name = save_name
        self.team_key = team_key
        self.back_screen = back_screen or "TeamPoolScreen"

    def edit_team_name(self) -> None:
        if not self.save_name or not self.team_key:
            self.subtitle_label.configure(text="No team selected.")
            return
        profile = get_team_profile(self.save_name, self.team_key)
        current_name = str(((profile or {}).get("team") or {}).get("team_name", "")).strip()
        prompt = f"Enter the new team name:\nCurrent: {current_name}" if current_name else "Enter the new team name:"
        dialog = ctk.CTkInputDialog(text=prompt, title="Edit Team Name")
        new_name = str(dialog.get_input() or "").strip()
        if not new_name:
            return
        ok, message = rename_team(self.save_name, self.team_key, new_name)
        self.subtitle_label.configure(text=message)
        if ok:
            self._refresh_gameplay_state()
            self.on_show()

    def _refresh_gameplay_state(self) -> None:
        if not self.save_name:
            return
        gameplay_screen = getattr(getattr(self, "master", None), "screens", {}).get("GameplayScreen")
        if gameplay_screen is None or not hasattr(gameplay_screen, "load_state"):
            return
        save_data = load_save(self.save_name)
        if save_data:
            gameplay_screen.load_state(save_data)

    def on_show(self) -> None:
        for widget in self.summary_frame.winfo_children():
            widget.destroy()
        for widget in self.history_frame.winfo_children():
            widget.destroy()

        if not self.save_name or not self.team_key:
            self.subtitle_label.configure(text="No team selected.")
            return

        profile = get_team_profile(self.save_name, self.team_key)
        if not profile:
            self.subtitle_label.configure(text="Team not found.")
            return

        team = profile.get("team") or {}
        season_history = profile.get("season_history") or []
        decisions = profile.get("driver_decisions") or []
        ownership_history = profile.get("ownership_history") or []
        current_championships = current_team_championships(self.save_name, self.team_key)
        team_name = str(team.get("team_name", "Team Details"))
        self.title_label.configure(text=team_name)
        self.subtitle_label.configure(text=f"Save: {self.save_name} | {team.get('game', '-')} | Rep {team.get('reputation', '-')}")

        self._section_label(self.summary_frame, "Current Snapshot")
        self._color_swatches(self.summary_frame, self._parse_colors(str(team.get("team_colors", ""))))
        self._info_row(self.summary_frame, "Reputation:", str(team.get("reputation", "-")))
        self._info_row(self.summary_frame, "Base Prestige:", str(team.get("base_prestige", "-")))
        self._info_row(self.summary_frame, "Game:", str(team.get("game", "-")))
        self._info_row(self.summary_frame, "Last Style:", str(team.get("last_style") or "-"))
        self._info_row(self.summary_frame, "Last Series:", str(team.get("last_championship") or "-"))

        self._section_label(self.summary_frame, "Career Totals")
        self._info_row(self.summary_frame, "Seasons:", str(team.get("seasons_completed", 0)))
        self._info_row(self.summary_frame, "Titles:", str(team.get("championships", 0)))
        self._info_row(self.summary_frame, "Wins:", str(team.get("wins", 0)))
        self._info_row(self.summary_frame, "Podiums:", str(team.get("podiums", 0)))
        championships_run = {
            str(item.get("championship_name", "")).strip()
            for item in season_history
            if str(item.get("championship_name", "")).strip()
        }
        if championships_run:
            self._info_row(self.summary_frame, "Series Run:", str(len(championships_run)))

        if decisions:
            self._section_label(self.summary_frame, "Recent Retain / Release")
            for item in decisions[:10]:
                decision = str(item.get("decision", "")).title()
                self._info_row(
                    self.summary_frame,
                    f"{item.get('season_year', '-')}:",
                    f"{decision} {item.get('driver_name', '-')} ({item.get('reason', '-')})",
                )

        if current_championships:
            self._section_label(self.history_frame, "Current Championships")
            current_header = ctk.CTkFrame(self.history_frame, fg_color="transparent")
            current_header.pack(fill="x", pady=(0, 4))
            for text, width in [("Championship", 170), ("Class", 95), ("Drivers", 220), ("Round", 55), ("Pts", 45), ("Wins", 45)]:
                ctk.CTkLabel(
                    current_header,
                    text=text,
                    width=width,
                    anchor="w",
                    font=ctk.CTkFont(size=10, weight="bold"),
                    text_color="gray",
                ).pack(side="left", padx=3)

            for item in current_championships:
                row = ctk.CTkFrame(
                    self.history_frame,
                    fg_color=("#ddeeff", "#1a3a55") if bool(item.get("is_player")) else ("gray80", "gray22"),
                    corner_radius=6,
                )
                row.pack(fill="x", pady=2)
                drivers = str(item.get("drivers", "")).replace(" | ", ", ")
                values = [
                    (str(item.get("championship_name", "")), 170),
                    (str(item.get("class_name", "")), 95),
                    (drivers or "-", 220),
                    (str(item.get("round_label", "-")), 55),
                    (str(item.get("points", "")), 45),
                    (str(item.get("wins", "")), 45),
                ]
                for value, width in values:
                    ctk.CTkLabel(row, text=str(value), width=width, anchor="w", font=ctk.CTkFont(size=11)).pack(
                        side="left", padx=3, pady=5
                    )

        if not season_history:
            ctk.CTkLabel(
                self.history_frame,
                text="No detailed team seasons recorded yet. New seasons will populate this history.",
                text_color="gray",
            ).pack(pady=(18 if not current_championships else 10))
            if not ownership_history:
                return

        if ownership_history:
            self._section_label(self.history_frame, "Seat Ownership")
            ownership_header = ctk.CTkFrame(self.history_frame, fg_color="transparent")
            ownership_header.pack(fill="x", pady=(0, 4))
            for text, width in [("Year", 55), ("Event", 95), ("Championship", 175), ("Seat", 55), ("Reason", 235)]:
                ctk.CTkLabel(
                    ownership_header,
                    text=text,
                    width=width,
                    anchor="w",
                    font=ctk.CTkFont(size=10, weight="bold"),
                    text_color="gray",
                ).pack(side="left", padx=3)

            for item in ownership_history[:18]:
                row = ctk.CTkFrame(self.history_frame, fg_color=("gray80", "gray22"), corner_radius=6)
                row.pack(fill="x", pady=2)
                values = [
                    (str(item.get("season_year") or "-"), 55),
                    (self._event_label(str(item.get("event_type", ""))), 95),
                    (str(item.get("championship_name", "")), 175),
                    (str(item.get("team_seat") or item.get("seat_number") or "-"), 55),
                    (str(item.get("reason", "")), 235),
                ]
                for value, width in values:
                    ctk.CTkLabel(row, text=str(value), width=width, anchor="w", font=ctk.CTkFont(size=11)).pack(
                        side="left", padx=3, pady=5
                    )

        if not season_history:
            return

        self._section_label(self.history_frame, "Championship History")
        header = ctk.CTkFrame(self.history_frame, fg_color="transparent")
        header.pack(fill="x", pady=(0, 4))
        for text, width in [("Year", 55), ("Championship", 170), ("Class", 95), ("Drivers", 220), ("Pts", 45), ("Wins", 45), ("Titles", 45)]:
            ctk.CTkLabel(
                header,
                text=text,
                width=width,
                anchor="w",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color="gray",
            ).pack(side="left", padx=3)

        for item in season_history:
            row = ctk.CTkFrame(self.history_frame, fg_color=("gray80", "gray22"), corner_radius=6)
            row.pack(fill="x", pady=2)
            drivers = str(item.get("drivers", "")).replace(" | ", ", ")
            values = [
                (str(item.get("season_year", "")), 55),
                (str(item.get("championship_name", "")), 170),
                (str(item.get("class_name", "")), 95),
                (drivers or "-", 220),
                (str(item.get("points", "")), 45),
                (str(item.get("wins", "")), 45),
                (str(item.get("championships", "")), 45),
            ]
            for value, width in values:
                ctk.CTkLabel(row, text=str(value), width=width, anchor="w", font=ctk.CTkFont(size=11)).pack(
                    side="left", padx=3, pady=5
                )

    @staticmethod
    def _event_label(event_type: str) -> str:
        labels = {
            "acquired": "Acquired",
            "active_season": "Active",
            "lost": "Lost",
            "sold": "Sold",
            "moved": "Moved",
        }
        return labels.get(event_type.strip().casefold(), event_type.replace("_", " ").title() or "-")
