from __future__ import annotations

import customtkinter as ctk
from PIL import Image, ImageOps

from ..paths import resource_path


BACKGROUND_PATH = resource_path("assets", "Main Menu.png")


class MenuScreen(ctk.CTkFrame):
    def __init__(self, parent, show_screen) -> None:
        super().__init__(parent, fg_color="transparent")
        self.show_screen = show_screen
        self._source_image = None
        self.background_image = None
        self.background_label: ctk.CTkLabel | None = None
        self._last_background_size: tuple[int, int] | None = None
        self._pending_background_size: tuple[int, int] | None = None
        self._resize_after_id: str | None = None

        if BACKGROUND_PATH.exists():
            self._source_image = Image.open(BACKGROUND_PATH)
            self.background_label = ctk.CTkLabel(self, text="")
            self.background_label.place(relx=0.5, rely=0.5, anchor="center", relwidth=1, relheight=1)
            self.bind("<Configure>", self._resize_background)

        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.place(relx=0.5, rely=0.92, anchor="s")

        ctk.CTkButton(
            button_frame,
            text="New Career",
            command=lambda: show_screen("NewGame"),
            height=38,
            width=160,
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(pady=8)

        ctk.CTkButton(
            button_frame,
            text="Load Career",
            command=lambda: show_screen("LoadScreen"),
            height=38,
            width=160,
            font=ctk.CTkFont(size=13),
            fg_color="gray30",
            hover_color="gray40",
        ).pack(pady=8)

    def on_show(self) -> None:
        if hasattr(self.master, "set_menu_music_active"):
            self.master.set_menu_music_active(True)

    def on_hide(self) -> None:
        if hasattr(self.master, "set_menu_music_active"):
            self.master.set_menu_music_active(False)

    def _resize_background(self, _event=None) -> None:
        if self._source_image is None or self.background_label is None:
            return
        width = max(1, int(getattr(_event, "width", self.winfo_width())))
        height = max(1, int(getattr(_event, "height", self.winfo_height())))
        target_size = (width, height)
        if self._last_background_size == target_size or self._pending_background_size == target_size:
            return
        self._pending_background_size = target_size
        if self._resize_after_id is not None:
            try:
                self.after_cancel(self._resize_after_id)
            except Exception:
                pass
        self._resize_after_id = self.after(120, self._apply_background_resize)

    def _apply_background_resize(self) -> None:
        self._resize_after_id = None
        if self._source_image is None or self.background_label is None or self._pending_background_size is None:
            return
        target_size = self._pending_background_size
        if self._last_background_size == target_size:
            return
        self._last_background_size = target_size
        fitted_image = ImageOps.fit(
            self._source_image,
            target_size,
            method=Image.Resampling.BILINEAR,
        )
        self.background_image = ctk.CTkImage(
            light_image=fitted_image,
            dark_image=fitted_image,
            size=target_size,
        )
        self.background_label.configure(image=self.background_image)
