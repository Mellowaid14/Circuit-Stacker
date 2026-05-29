from __future__ import annotations

from datetime import datetime
import re

import customtkinter as ctk

from ..save_manager import update_save


class MessagesScreen(ctk.CTkFrame):
    def __init__(self, parent, show_screen) -> None:
        super().__init__(parent, fg_color="transparent")
        self.parent = parent
        self.show_screen = show_screen
        self.gameplay_screen = None
        self._selected_message_id: str | None = None

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=18, pady=(18, 8))
        ctk.CTkLabel(
            header,
            text="Messages",
            font=ctk.CTkFont(size=26, weight="bold"),
        ).pack(side="left")
        ctk.CTkButton(
            header,
            text="<- Back",
            command=lambda: self.show_screen("GameplayScreen"),
            width=100,
            height=32,
            fg_color="gray30",
            hover_color="gray40",
        ).pack(side="right")

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
        messages = self._messages()
        if messages and not self._selected_message_id:
            self._selected_message_id = self._message_id(messages[-1])
        self._render_messages()

    def _render_messages(self) -> None:
        for widget in self.message_list.winfo_children():
            widget.destroy()
        for widget in self.message_detail.winfo_children():
            widget.destroy()

        messages = self._messages()
        if not messages:
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
            message_id = self._message_id(message)
            selected = message_id == self._selected_message_id
            unread = not bool(message.get("read"))
            card = ctk.CTkFrame(
                self.message_list,
                fg_color=("#d8ecff", "#173a59") if selected else (("#e8f3ff", "#1f3f5f") if unread else ("gray84", "gray20")),
                corner_radius=10,
            )
            card.pack(fill="x", pady=4, padx=6)
            card.bind("<Button-1>", lambda _event, value=message_id: self._select_message(value))

            title = str(message.get("title", "Message")).strip() or "Message"
            sender = str(message.get("sender") or message.get("category") or "Race Control").strip()
            preview = self._preview(str(message.get("body", "")).strip(), 82)
            subject_row = ctk.CTkFrame(card, fg_color="transparent")
            subject_row.pack(fill="x", padx=10, pady=(10, 1))
            subject_row.bind("<Button-1>", lambda _event, value=message_id: self._select_message(value))
            if unread:
                dot = ctk.CTkLabel(
                    subject_row,
                    text="●",
                    font=ctk.CTkFont(size=14, weight="bold"),
                    text_color="#2f8cff",
                    width=16,
                )
                dot.pack(side="left", padx=(0, 4))
                dot.bind("<Button-1>", lambda _event, value=message_id: self._select_message(value))
            title_label = ctk.CTkLabel(
                subject_row,
                text=title,
                font=ctk.CTkFont(size=13, weight="bold" if unread else "normal"),
                anchor="w",
            )
            title_label.pack(side="left", fill="x", expand=True)
            title_label.bind("<Button-1>", lambda _event, value=message_id: self._select_message(value))
            sender_label = ctk.CTkLabel(
                card,
                text=sender,
                font=ctk.CTkFont(size=11),
                text_color=("gray35", "gray72"),
                anchor="w",
            )
            sender_label.pack(fill="x", padx=10)
            sender_label.bind("<Button-1>", lambda _event, value=message_id: self._select_message(value))
            if preview:
                preview_label = ctk.CTkLabel(
                    card,
                    text=preview,
                    font=ctk.CTkFont(size=11),
                    text_color=("gray40", "gray68"),
                    anchor="w",
                    justify="left",
                    wraplength=290,
                )
                preview_label.pack(fill="x", padx=10, pady=(2, 8))
                preview_label.bind("<Button-1>", lambda _event, value=message_id: self._select_message(value))

        selected_message = next(
            (message for message in messages if self._message_id(message) == self._selected_message_id),
            messages[-1],
        )
        self._selected_message_id = self._message_id(selected_message)
        self._render_detail(selected_message)

    def _render_detail(self, message: dict) -> None:
        sender = str(message.get("sender") or message.get("category") or "Race Control").strip()
        title = str(message.get("title", "Message")).strip() or "Message"
        body = str(message.get("body", "")).strip()
        timestamp = self._display_timestamp(str(message.get("created_at", "")))

        ctk.CTkLabel(
            self.message_detail,
            text=title,
            font=ctk.CTkFont(size=24, weight="bold"),
            anchor="w",
            justify="left",
            wraplength=760,
        ).pack(fill="x", padx=24, pady=(24, 6))
        ctk.CTkLabel(
            self.message_detail,
            text=f"From: {sender}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=("gray25", "gray82"),
            anchor="w",
        ).pack(fill="x", padx=24)
        if timestamp:
            ctk.CTkLabel(
                self.message_detail,
                text=timestamp,
                font=ctk.CTkFont(size=11),
                text_color=("gray45", "gray62"),
                anchor="w",
            ).pack(fill="x", padx=24, pady=(2, 18))

        colors = self._message_colors(message, body)
        if colors:
            self._render_color_samples(colors)

        ctk.CTkLabel(
            self.message_detail,
            text=body or "No message body.",
            font=ctk.CTkFont(size=14),
            justify="left",
            anchor="nw",
            wraplength=780,
        ).pack(fill="both", expand=True, padx=24, pady=(0, 24))
        self._mark_message_read(self._message_id(message))

    def _render_color_samples(self, colors: list[str]) -> None:
        row = ctk.CTkFrame(self.message_detail, fg_color=("gray84", "gray20"), corner_radius=12)
        row.pack(fill="x", padx=24, pady=(0, 18))
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

    def _mark_message_read(self, message_id: str) -> None:
        if self.gameplay_screen is None:
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
