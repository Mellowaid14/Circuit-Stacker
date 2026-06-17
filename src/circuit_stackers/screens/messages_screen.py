from __future__ import annotations

from datetime import datetime
import re

import customtkinter as ctk

from ..save_manager import update_save


MESSAGE_KIND_STYLES = {
    "rivalry": ("RIVAL MESSAGE", "#e04747", ("#f4dddd", "#2d1515"), ("#ffe3e3", "#491d1d")),
    "race": ("RACE REPORT", "#1d7f52", ("#ddf0e5", "#14291f"), ("#e6f7ed", "#183d2a")),
    "race control": ("RACE CONTROL", "#2f8cff", ("#dcecff", "#142235"), ("#e7f2ff", "#173a59")),
    "team": ("TEAM MESSAGE", "#e17732", ("#f2e3d8", "#2d1d12"), ("#ffe9db", "#4b2817")),
    "championship": ("CHAMPIONSHIP", "#d49b28", ("#f3ead7", "#2d2512"), ("#fff1d0", "#4a3914")),
    "weather": ("WEATHER", "#5aa6bb", ("#dcecef", "#13272d"), ("#e6f6f8", "#183941")),
    "world": ("WORLD NEWS", "#7587a8", ("#e4e8f0", "#1d2430"), ("#eff3fb", "#283245")),
    "default": ("MESSAGE", "#2f8cff", ("gray84", "gray20"), ("#e8f3ff", "#1f3f5f")),
}


class MessagesScreen(ctk.CTkFrame):
    def __init__(self, parent, show_screen) -> None:
        super().__init__(parent, fg_color="transparent")
        self.parent = parent
        self.show_screen = show_screen
        self.gameplay_screen = None
        self._selected_message_id: str | None = None

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(18, 8))
        self.title_label = ctk.CTkLabel(
            header,
            text="Messages",
            font=ctk.CTkFont(size=26, weight="bold"),
        )
        self.title_label.pack(side="left")
        ctk.CTkButton(
            header,
            text="<- Back",
            command=lambda: self.show_screen("GameplayScreen"),
            width=100,
            height=32,
            fg_color="gray30",
            hover_color="gray40",
        ).pack(side="right")
        self.delete_read_btn = ctk.CTkButton(
            header,
            text="Delete Read",
            command=self._delete_read_messages,
            width=120,
            height=32,
            fg_color="#7a2c2c",
            hover_color="#943737",
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.delete_read_btn.pack(side="right", padx=(0, 8))

        self.subtitle = ctk.CTkLabel(
            self,
            text="Team notes, race-control reminders, and championship updates live here.",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        self.subtitle.pack(anchor="w", padx=22, pady=(0, 10))

        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        self.content.columnconfigure(0, weight=0)
        self.content.columnconfigure(1, weight=1)
        self.content.rowconfigure(0, weight=1)

        self.message_list = ctk.CTkScrollableFrame(self.content, fg_color=("gray88", "gray16"), width=330)
        self.message_list.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        self.message_detail = ctk.CTkFrame(self.content, fg_color=("gray90", "gray14"), corner_radius=16)
        self.message_detail.grid(row=0, column=1, sticky="nsew")

    def set_gameplay_screen(self, gameplay_screen) -> None:
        self.gameplay_screen = gameplay_screen

    def on_show(self) -> None:
        self._refresh_header()
        messages = self._messages()
        if messages and not self._selected_message_id:
            self._selected_message_id = self._message_id(messages[-1])
        self._render_messages()

    def _refresh_header(self) -> None:
        active_player = ""
        player_count = 0
        if self.gameplay_screen is not None:
            active_player = str(getattr(self.gameplay_screen, "active_player_name", "") or "").strip()
            player_count = len(list(getattr(self.gameplay_screen, "player_names", []) or []))

        if player_count > 1 and active_player:
            self.title_label.configure(text=f"Messages - {active_player}")
            self.subtitle.configure(
                text=(
                    f"Shared team notes plus {active_player}'s personal rival messages live here. "
                    f"Switch views on the dashboard to read another driver's inbox."
                )
            )
            return

        self.title_label.configure(text="Messages")
        self.subtitle.configure(text="Team notes, race-control reminders, and championship updates live here.")

    def _render_messages(self) -> None:
        for widget in self.message_list.winfo_children():
            widget.destroy()
        for widget in self.message_detail.winfo_children():
            widget.destroy()

        messages = self._messages()
        if not messages:
            self.message_detail.configure(fg_color=("gray90", "gray14"))
            self._refresh_delete_button()
            ctk.CTkLabel(
                self.message_list,
                text="No messages yet.",
                font=ctk.CTkFont(size=15, weight="bold"),
                text_color="gray",
            ).pack(pady=40)
            ctk.CTkLabel(
                self.message_detail,
                text="Select a message to read it.",
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color="gray",
            ).pack(expand=True)
            return

        for message in reversed(messages):
            self._render_message_card(message)

        selected_message = next(
            (message for message in messages if self._message_id(message) == self._selected_message_id),
            messages[-1],
        )
        self._selected_message_id = self._message_id(selected_message)
        self._render_detail(selected_message)
        self._refresh_delete_button()

    def _render_message_card(self, message: dict) -> None:
        message_id = self._message_id(message)
        selected = message_id == self._selected_message_id
        unread = not bool(message.get("read"))
        kind_label, accent_color, normal_color, unread_color = self._message_style(message)
        card = ctk.CTkFrame(
            self.message_list,
            fg_color=unread_color if unread or selected else normal_color,
            corner_radius=12,
            border_width=1 if selected else 0,
            border_color=accent_color,
        )
        card.pack(fill="x", pady=4, padx=6)
        self._bind_select(card, message_id)

        accent = ctk.CTkFrame(card, fg_color=accent_color, width=7, corner_radius=8)
        accent.pack(side="left", fill="y", padx=(7, 0), pady=8)
        self._bind_select(accent, message_id)

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(side="left", fill="both", expand=True, padx=(9, 10), pady=8)
        self._bind_select(body, message_id)

        meta_row = ctk.CTkFrame(body, fg_color="transparent")
        meta_row.pack(fill="x", pady=(0, 5))
        self._bind_select(meta_row, message_id)
        badge = ctk.CTkLabel(
            meta_row,
            text=kind_label,
            font=ctk.CTkFont(size=9, weight="bold"),
            text_color="#f4f7fb",
            fg_color=accent_color,
            corner_radius=9,
            height=20,
        )
        badge.pack(side="left", ipadx=7)
        self._bind_select(badge, message_id)
        if unread:
            new_label = ctk.CTkLabel(
                meta_row,
                text="NEW",
                font=ctk.CTkFont(size=9, weight="bold"),
                text_color=accent_color,
            )
            new_label.pack(side="right", padx=(6, 0))
            self._bind_select(new_label, message_id)
        delete_button = ctk.CTkButton(
            meta_row,
            text="X",
            command=lambda value=message_id: self._delete_single_message(value),
            width=24,
            height=20,
            corner_radius=8,
            fg_color="#7a2c2c",
            hover_color="#a33d3d",
            font=ctk.CTkFont(size=10, weight="bold"),
        )
        delete_button.pack(side="right")

        title = str(message.get("title", "Message")).strip() or "Message"
        sender = str(message.get("sender") or message.get("category") or "Race Control").strip()
        preview = self._preview(str(message.get("body", "")).strip(), 82)
        title_label = ctk.CTkLabel(
            body,
            text=title,
            font=ctk.CTkFont(size=13, weight="bold" if unread else "normal"),
            anchor="w",
            justify="left",
            wraplength=270,
        )
        title_label.pack(fill="x")
        self._bind_select(title_label, message_id)
        sender_label = ctk.CTkLabel(
            body,
            text=sender,
            font=ctk.CTkFont(size=11),
            text_color=("gray35", "gray72"),
            anchor="w",
        )
        sender_label.pack(fill="x")
        self._bind_select(sender_label, message_id)
        if preview:
            preview_label = ctk.CTkLabel(
                body,
                text=preview,
                font=ctk.CTkFont(size=11),
                text_color=("gray40", "gray68"),
                anchor="w",
                justify="left",
                wraplength=290,
            )
            preview_label.pack(fill="x", pady=(3, 0))
            self._bind_select(preview_label, message_id)

    def _render_detail(self, message: dict) -> None:
        sender = str(message.get("sender") or message.get("category") or "Race Control").strip()
        title = str(message.get("title", "Message")).strip() or "Message"
        body = str(message.get("body", "")).strip()
        timestamp = self._display_timestamp(str(message.get("created_at", "")))
        kind_label, accent_color, normal_color, _unread_color = self._message_style(message)

        self.message_detail.configure(fg_color=normal_color)
        shell = ctk.CTkFrame(self.message_detail, fg_color="transparent")
        shell.pack(fill="both", expand=True, padx=18, pady=18)
        accent = ctk.CTkFrame(shell, fg_color=accent_color, width=9, corner_radius=9)
        accent.pack(side="left", fill="y", padx=(0, 14))
        body_frame = ctk.CTkFrame(shell, fg_color="transparent")
        body_frame.pack(side="left", fill="both", expand=True)

        meta_row = ctk.CTkFrame(body_frame, fg_color="transparent")
        meta_row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(
            meta_row,
            text=kind_label,
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#f4f7fb",
            fg_color=accent_color,
            corner_radius=10,
            height=24,
        ).pack(side="left", ipadx=9)
        if timestamp:
            ctk.CTkLabel(
                meta_row,
                text=timestamp,
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=("gray45", "gray62"),
                anchor="e",
            ).pack(side="right")

        ctk.CTkLabel(
            body_frame,
            text=title,
            font=ctk.CTkFont(size=24, weight="bold"),
            anchor="w",
            justify="left",
            wraplength=760,
        ).pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(
            body_frame,
            text=f"From: {sender}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=("gray25", "gray82"),
            anchor="w",
        ).pack(fill="x", pady=(0, 18))

        colors = self._message_colors(message, body)
        if colors:
            self._render_color_samples(body_frame, colors)

        ctk.CTkLabel(
            body_frame,
            text=body or "No message body.",
            font=ctk.CTkFont(size=14),
            justify="left",
            anchor="nw",
            wraplength=780,
        ).pack(fill="both", expand=True, pady=(0, 6))
        self._mark_message_read(self._message_id(message))

    def _render_color_samples(self, parent, colors: list[str]) -> None:
        row = ctk.CTkFrame(parent, fg_color=("gray84", "gray20"), corner_radius=12)
        row.pack(fill="x", pady=(0, 18))
        ctk.CTkLabel(
            row,
            text="Sample colors",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("gray28", "gray82"),
        ).pack(anchor="w", padx=12, pady=(10, 6))
        swatch_row = ctk.CTkFrame(row, fg_color="transparent")
        swatch_row.pack(anchor="w", padx=12, pady=(0, 12))
        for index, color in enumerate(colors, start=1):
            group = ctk.CTkFrame(swatch_row, fg_color="transparent")
            group.pack(side="left", padx=(0, 14))
            ctk.CTkFrame(
                group,
                fg_color=f"#{color}",
                width=58,
                height=34,
                corner_radius=7,
                border_width=1,
                border_color=("gray55", "gray35"),
            ).pack()
            ctk.CTkLabel(group, text=f"{index}: #{color}", font=ctk.CTkFont(size=10), text_color=("gray35", "gray72")).pack(
                pady=(4, 0)
            )

    @staticmethod
    def _message_colors(message: dict, body: str) -> list[str]:
        raw_colors = message.get("colors") or message.get("team_colors") or []
        if isinstance(raw_colors, str):
            colors = [color.strip().upper().lstrip("#") for color in raw_colors.split(",") if color.strip()]
        else:
            colors = [str(color).strip().upper().lstrip("#") for color in raw_colors if str(color).strip()]
        if not colors:
            colors = re.findall(r"#([0-9A-Fa-f]{6})", body)
        return [color for color in colors[:3] if re.fullmatch(r"[0-9A-F]{6}", color)]

    def _select_message(self, message_id: str) -> None:
        self._selected_message_id = message_id
        self._render_messages()

    def _bind_select(self, widget, message_id: str) -> None:
        widget.bind("<Button-1>", lambda _event, value=message_id: self._select_message(value))

    def _refresh_delete_button(self) -> None:
        read_count = sum(1 for message in self._messages() if bool(message.get("read")))
        self.delete_read_btn.configure(
            text=f"Delete Read ({read_count})" if read_count else "Delete Read",
            state="normal" if read_count else "disabled",
        )

    def _delete_read_messages(self) -> None:
        if self.gameplay_screen is None:
            return

        shared_messages = [dict(message) for message in list(getattr(self.gameplay_screen, "messages", []) or [])]
        kept_shared = [message for message in shared_messages if not bool(message.get("read"))]
        removed_count = len(shared_messages) - len(kept_shared)
        self.gameplay_screen.messages = kept_shared

        perspectives = getattr(self.gameplay_screen, "player_perspectives", {})
        if isinstance(perspectives, dict):
            perspectives = {str(name): dict(value) for name, value in perspectives.items() if isinstance(value, dict)}
        else:
            perspectives = {}

        active_player = str(getattr(self.gameplay_screen, "active_player_name", "") or "").strip()
        if active_player and active_player in perspectives:
            perspective = dict(perspectives.get(active_player) or {})
            personal_messages = [dict(message) for message in list(perspective.get("messages") or []) if isinstance(message, dict)]
            kept_personal = [message for message in personal_messages if not bool(message.get("read"))]
            removed_count += len(personal_messages) - len(kept_personal)
            perspective["messages"] = kept_personal
            perspectives[active_player] = perspective
            self.gameplay_screen.player_perspectives = perspectives

        if removed_count <= 0:
            self._refresh_delete_button()
            return

        save_name = getattr(self.gameplay_screen, "save_name", None)
        if save_name:
            update_save(
                save_name,
                {
                    "messages": kept_shared,
                    "player_perspectives": perspectives,
                },
            )
        if hasattr(self.gameplay_screen, "_refresh_message_button"):
            self.gameplay_screen._refresh_message_button()

        self._selected_message_id = None
        self._render_messages()

    def _delete_single_message(self, message_id: str) -> None:
        if self.gameplay_screen is None:
            return

        target_id = str(message_id)
        removed = False
        shared_messages = [dict(message) for message in list(getattr(self.gameplay_screen, "messages", []) or [])]
        kept_shared = [message for message in shared_messages if self._message_id(message) != target_id]
        if len(kept_shared) != len(shared_messages):
            removed = True
            self.gameplay_screen.messages = kept_shared

        perspectives = getattr(self.gameplay_screen, "player_perspectives", {})
        if isinstance(perspectives, dict):
            perspectives = {str(name): dict(value) for name, value in perspectives.items() if isinstance(value, dict)}
        else:
            perspectives = {}

        active_player = str(getattr(self.gameplay_screen, "active_player_name", "") or "").strip()
        if active_player and active_player in perspectives:
            perspective = dict(perspectives.get(active_player) or {})
            personal_messages = [dict(message) for message in list(perspective.get("messages") or []) if isinstance(message, dict)]
            kept_personal = [message for message in personal_messages if self._message_id(message) != target_id]
            if len(kept_personal) != len(personal_messages):
                removed = True
                perspective["messages"] = kept_personal
                perspectives[active_player] = perspective
                self.gameplay_screen.player_perspectives = perspectives

        if not removed:
            self._render_messages()
            return

        save_name = getattr(self.gameplay_screen, "save_name", None)
        if save_name:
            update_save(
                save_name,
                {
                    "messages": getattr(self.gameplay_screen, "messages", []),
                    "player_perspectives": perspectives,
                },
            )
        if hasattr(self.gameplay_screen, "_refresh_message_button"):
            self.gameplay_screen._refresh_message_button()

        if self._selected_message_id == target_id:
            self._selected_message_id = None
        self._render_messages()

    @staticmethod
    def _message_style(message: dict) -> tuple[str, str, tuple[str, str], tuple[str, str]]:
        category = str(message.get("category") or message.get("type") or "").strip().casefold()
        title = str(message.get("title") or "").strip().casefold()
        sender = str(message.get("sender") or "").strip().casefold()
        combined = " ".join([category, title, sender])

        if "rival" in combined:
            key = "rivalry"
        elif "race report" in combined or ("race" in category and "control" not in category):
            key = "race"
        elif "race control" in combined or "control" in category:
            key = "race control"
        elif "team" in combined or "welcome" in title:
            key = "team"
        elif "championship" in combined or "season" in combined:
            key = "championship"
        elif "weather" in combined:
            key = "weather"
        elif "world" in combined or "news" in combined:
            key = "world"
        else:
            key = "default"
        return MESSAGE_KIND_STYLES[key]

    def _mark_message_read(self, message_id: str) -> None:
        if self.gameplay_screen is None:
            return
        if hasattr(self.gameplay_screen, "mark_active_message_read"):
            self.gameplay_screen.mark_active_message_read(message_id)
            return

        messages = self._messages()
        target = next((message for message in messages if self._message_id(message) == message_id), None)
        if not target or bool(target.get("read")):
            return
        updated = []
        for message in messages:
            row = dict(message)
            if self._message_id(row) == message_id:
                row["read"] = True
            updated.append(row)
        self.gameplay_screen.messages = updated
        save_name = getattr(self.gameplay_screen, "save_name", None)
        if save_name:
            update_save(save_name, {"messages": updated})
        if hasattr(self.gameplay_screen, "_refresh_message_button"):
            self.gameplay_screen._refresh_message_button()

    def _messages(self) -> list[dict]:
        if self.gameplay_screen is not None and hasattr(self.gameplay_screen, "active_messages"):
            return list(self.gameplay_screen.active_messages())
        return list(getattr(self.gameplay_screen, "messages", []) or [])

    @staticmethod
    def _message_id(message: dict) -> str:
        return str(message.get("id") or message.get("created_at") or id(message))

    @staticmethod
    def _preview(value: str, max_chars: int) -> str:
        text = " ".join(str(value).split())
        if len(text) <= max_chars:
            return text
        return f"{text[: max_chars - 3]}..."

    @staticmethod
    def _display_timestamp(raw_value: str) -> str:
        if not raw_value:
            return ""
        try:
            value = datetime.fromisoformat(raw_value)
        except ValueError:
            return raw_value
        return value.strftime("%m/%d/%Y %H:%M")
