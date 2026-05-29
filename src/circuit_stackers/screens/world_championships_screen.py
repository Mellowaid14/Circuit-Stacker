from __future__ import annotations

import customtkinter as ctk

from ..game_logic import list_active_world_championships


class WorldChampionshipsScreen(ctk.CTkFrame):
    def __init__(self, parent, show_screen) -> None:
        super().__init__(parent, fg_color="transparent")
        self.parent = parent
        self.show_screen = show_screen
        self.gameplay_screen = None

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(18, 8))

        self.title_label = ctk.CTkLabel(top, text="World Championships", font=ctk.CTkFont(size=22, weight="bold"))
        self.title_label.pack(side="left")
        ctk.CTkButton(
            top,
            text="<- Back",
            command=lambda: self.show_screen("GameplayScreen"),
            width=90,
            height=30,
            fg_color="gray30",
            hover_color="gray40",
            font=ctk.CTkFont(size=11),
        ).pack(side="right")

        self.subtitle_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=11), text_color="gray")
        self.subtitle_label.pack(pady=(0, 8))

        table_box = ctk.CTkFrame(self, fg_color=("gray90", "gray15"), corner_radius=12)
        table_box.pack(fill="both", expand=True, padx=24, pady=(0, 14))
        self.table_frame = ctk.CTkScrollableFrame(table_box, fg_color="transparent")
        self.table_frame.pack(fill="both", expand=True, padx=10, pady=10)

    def set_gameplay_screen(self, gameplay_screen) -> None:
        self.gameplay_screen = gameplay_screen

    def on_show(self) -> None:
        for widget in self.table_frame.winfo_children():
            widget.destroy()

        save_name = getattr(self.gameplay_screen, "save_name", None)
        if not save_name:
            self.subtitle_label.configure(text="No active save loaded.")
            ctk.CTkLabel(self.table_frame, text="No championships available.", text_color="gray").pack(pady=20)
            return

        championships = list_active_world_championships(save_name)
        self.subtitle_label.configure(text=f"Save: {save_name} | {len(championships)} active championships")

        if not championships:
            ctk.CTkLabel(self.table_frame, text="No active championships available.", text_color="gray").pack(pady=20)
            return

        grouped: dict[str, list[dict]] = {}
        for item in championships:
            style = str(item.get("style", "")).strip() or "Other"
            grouped.setdefault(style, []).append(item)

        style_order = ["Sports Car", "Open Wheel", "Oval", "Rallycross", "Other"]
        sorted_styles = sorted(
            grouped.keys(),
            key=lambda style: (
                style_order.index(style) if style in style_order else len(style_order),
                style,
            ),
        )

        for style in sorted_styles:
            ctk.CTkLabel(
                self.table_frame,
                text=style,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=("#1a6fc4", "#4da6ff"),
            ).pack(anchor="w", padx=4, pady=(8, 2))

            header = ctk.CTkFrame(self.table_frame, fg_color="transparent")
            header.pack(fill="x", pady=(0, 4))
            for text, width in [
                ("Championship", 280),
                ("Drivers", 60),
                ("Round", 60),
                ("Type", 70),
            ]:
                ctk.CTkLabel(
                    header,
                    text=text,
                    width=width,
                    anchor="w",
                    font=ctk.CTkFont(size=10, weight="bold"),
                    text_color="gray",
                ).pack(side="left", padx=3)

            style_items = sorted(
                grouped[style],
                key=lambda item: (
                    -int(item.get("prestige", 0) or 0),
                    0 if item.get("is_player") else 1,
                    str(item.get("name", "")).strip(),
                ),
            )
            for item in style_items:
                row = ctk.CTkFrame(
                    self.table_frame,
                    fg_color=("#ddeeff", "#1a3a55") if item.get("is_player") else ("gray80", "gray22"),
                    corner_radius=6,
                )
                row.pack(fill="x", pady=2)
                values = [
                    (item.get("name", ""), 280),
                    (str(item.get("drivers", "")), 60),
                    (str(item.get("round_label", "")), 60),
                    ("Player" if item.get("is_player") else "World", 70),
                ]
                for value, width in values:
                    ctk.CTkLabel(row, text=str(value), width=width, anchor="w", font=ctk.CTkFont(size=11)).pack(
                        side="left", padx=3, pady=5
                    )
                ctk.CTkButton(
                    row,
                    text="View",
                    width=60,
                    height=26,
                    font=ctk.CTkFont(size=10),
                    command=lambda current_item=item: self.open_detail(current_item),
                ).pack(side="right", padx=6, pady=4)

    def open_detail(self, item: dict) -> None:
        save_name = getattr(self.gameplay_screen, "save_name", None)
        championship_key = str(item.get("key", "")).strip()
        if not save_name or not championship_key:
            return
        detail_screen = self.parent.screens["WorldChampionshipDetailScreen"]
        if hasattr(detail_screen, "set_context"):
            detail_screen.set_context(save_name, championship_key, "WorldChampionshipsScreen")
        self.show_screen("WorldChampionshipDetailScreen")
