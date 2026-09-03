from __future__ import annotations

import json
from tkinter import filedialog, messagebox
from pathlib import Path

import customtkinter as ctk

from ..career_paths import delete_career_path, default_career_path, export_career_path, list_career_paths, save_career_path
from ..custom_championships import built_in_championship_rows, grouped_custom_championships


class CareerPathEditorScreen(ctk.CTkFrame):
    """Edit a portable, ordered career path without changing built-in CSVs."""

    def __init__(self, parent, show_screen) -> None:
        super().__init__(parent, fg_color="transparent")
        self.show_screen = show_screen
        self.paths: list[dict[str, object]] = []
        self.current: dict[str, object] = default_career_path()
        self.stage_ids: list[str] = []
        self.stage_labels: dict[str, str] = {}
        self.stage_styles: dict[str, str] = {}
        self.stage_prestiges: dict[str, int] = {}
        self.available_label_to_id: dict[str, str] = {}
        self.championship_search_var = ctk.StringVar(value="")
        self.game_var = ctk.StringVar(value="iRacing")
        self.save_button = None
        self.add_stage_button = None

        header = ctk.CTkFrame(self, fg_color=("gray88", "gray14"), corner_radius=18)
        header.pack(fill="x", padx=18, pady=(18, 10))
        ctk.CTkLabel(header, text="CAREER PATHS", text_color="#2f8cff", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=18, pady=(14, 2))
        ctk.CTkLabel(header, text="Career Path Editor", font=ctk.CTkFont(size=25, weight="bold")).pack(anchor="w", padx=18)
        ctk.CTkLabel(header, text="Build a progression from the championship data already in Circuit Stackers.", text_color="gray").pack(anchor="w", padx=18, pady=(2, 14))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=(0, 8))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        self.path_list = ctk.CTkScrollableFrame(body, fg_color=("gray90", "gray15"), corner_radius=14)
        self.path_list.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        editor = ctk.CTkScrollableFrame(body, fg_color=("gray90", "gray15"), corner_radius=14)
        editor.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        self.title_entry = self._entry(editor, "Path Name")
        self.author_entry = self._entry(editor, "Author")
        self.description_entry = self._entry(editor, "Description")
        ctk.CTkLabel(editor, text="Game", anchor="w").pack(fill="x", padx=14, pady=(0, 4))
        self.game_menu = ctk.CTkOptionMenu(editor, variable=self.game_var, values=["iRacing", "AMS2"], command=lambda _value: self._refresh_available())
        self.game_menu.pack(fill="x", padx=14, pady=(0, 12))

        ctk.CTkLabel(editor, text="Available Championships", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=14, pady=(4, 6))
        self.championship_search_entry = ctk.CTkEntry(
            editor,
            textvariable=self.championship_search_var,
            placeholder_text="Search championships, styles, or IDs...",
            height=32,
        )
        self.championship_search_entry.pack(fill="x", padx=14, pady=(0, 8))
        self.championship_search_var.trace_add("write", lambda *_args: self._championship_search_changed())
        self.available_menu = ctk.CTkComboBox(editor, values=[], width=420)
        self.available_menu.pack(fill="x", padx=14, pady=(0, 8))
        actions = ctk.CTkFrame(editor, fg_color="transparent")
        actions.pack(fill="x", padx=14, pady=(0, 14))
        self.add_stage_button = ctk.CTkButton(actions, text="Add Stage", command=self._add_stage, width=110)
        self.add_stage_button.pack(side="left")
        self.save_button = ctk.CTkButton(actions, text="Save Path", command=self._save, width=110)
        self.save_button.pack(side="left", padx=8)
        ctk.CTkButton(actions, text="Export", command=self._export, width=90, fg_color="gray30", hover_color="gray40").pack(side="left")
        ctk.CTkButton(actions, text="Import", command=self._import, width=90, fg_color="gray30", hover_color="gray40").pack(side="left", padx=8)
        ctk.CTkLabel(editor, text="Championships in This Path", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=14, pady=(8, 6))
        self.stage_frame = ctk.CTkFrame(editor, fg_color=("gray84", "gray20"), corner_radius=10)
        self.stage_frame.pack(fill="x", padx=14, pady=(0, 12))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(pady=(0, 12))
        self.status_label = ctk.CTkLabel(footer, text="", text_color="gray")
        self.status_label.pack(side="left", padx=10)
        ctk.CTkButton(footer, text="Back to Settings", command=lambda: self.show_screen("SettingsScreen"), width=140, fg_color="gray30", hover_color="gray40").pack(side="left")

    def _entry(self, parent, label: str) -> ctk.CTkEntry:
        ctk.CTkLabel(parent, text=label, anchor="w").pack(fill="x", padx=14, pady=(0, 4))
        entry = ctk.CTkEntry(parent, height=34)
        entry.pack(fill="x", padx=14, pady=(0, 10))
        return entry

    def on_show(self) -> None:
        self.paths = list_career_paths()
        self._render_paths()
        self._load_path(default_career_path(self.game_var.get()))

    def _render_paths(self) -> None:
        for widget in self.path_list.winfo_children():
            widget.destroy()
        ctk.CTkLabel(self.path_list, text="Saved Paths", font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=12, pady=(12, 8))
        for path in self.paths:
            title = str(path.get("title", "Career Path"))
            if str(path.get("path_id", "")).strip() == "default":
                ctk.CTkLabel(self.path_list, text=f"{title} (Built-in)", anchor="w", text_color="gray").pack(fill="x", padx=10, pady=7)
            else:
                row = ctk.CTkFrame(self.path_list, fg_color="transparent")
                row.pack(fill="x", padx=10, pady=3)
                row.bind("<ButtonRelease-1>", lambda _event, item=path: self._load_path(item))
                ctk.CTkButton(row, text=title, anchor="w", command=lambda item=path: self._load_path(item), fg_color="gray30", hover_color="gray40").pack(side="left", fill="x", expand=True)
                ctk.CTkButton(row, text="Delete", width=70, command=lambda item=path: self._delete_path(item), fg_color="#8c2f2f", hover_color="#6c2323").pack(side="right", padx=(6, 0))
        ctk.CTkButton(self.path_list, text="Start Fresh", command=lambda: self._load_path({"title": "", "author": "", "description": "", "game": self.game_var.get(), "championship_ids": []}), fg_color="#1f6f9f", hover_color="#185777").pack(fill="x", padx=10, pady=(14, 4))

    def _load_path(self, payload: dict[str, object]) -> None:
        self.current = dict(payload)
        self.title_entry.delete(0, "end")
        self.title_entry.insert(0, str(payload.get("title", "")))
        self.author_entry.delete(0, "end")
        self.author_entry.insert(0, str(payload.get("author", "")))
        self.description_entry.delete(0, "end")
        self.description_entry.insert(0, str(payload.get("description", "")))
        self.game_var.set(str(payload.get("game", "iRacing")) if str(payload.get("game", "")).casefold() in {"iracing", "ams2"} else "iRacing")
        self.stage_ids = [str(value) for value in payload.get("championship_ids", []) if str(value).strip()]
        self._refresh_available()
        self._render_stages()
        self._set_default_lock(str(payload.get("path_id", "")).strip() == "default")

    def _set_default_lock(self, locked: bool) -> None:
        state = "disabled" if locked else "normal"
        for widget in (
            self.title_entry,
            self.author_entry,
            self.description_entry,
            self.game_menu,
            self.available_menu,
            self.add_stage_button,
            self.save_button,
        ):
            if widget is not None:
                widget.configure(state=state)
        for row in self.stage_frame.winfo_children():
            for widget in row.winfo_children():
                if isinstance(widget, ctk.CTkButton):
                    widget.configure(state=state)

    def _refresh_available(self) -> None:
        game = self.game_var.get()
        search_terms = [term for term in self.championship_search_var.get().strip().casefold().split() if term]
        groups: dict[str, str] = {}
        for row in built_in_championship_rows(game) + [row for group in grouped_custom_championships() for row in group.get("rows", []) if isinstance(row, dict) and str(row.get("Game", "")).casefold() == game.casefold()]:
            group_id = str(row.get("Championship_ID", "") or row.get("id", "")).strip()
            if group_id:
                groups[group_id] = str(row.get("Championship", "")).strip() or group_id
        self.stage_labels = groups
        self.stage_styles = {}
        self.stage_prestiges = {}
        for row in built_in_championship_rows(game) + [
            row
            for group in grouped_custom_championships()
            for row in group.get("rows", [])
            if isinstance(row, dict) and str(row.get("Game", "")).casefold() == game.casefold()
        ]:
            group_id = str(row.get("Championship_ID", "") or row.get("id", "")).strip()
            if group_id:
                self.stage_styles[group_id] = str(row.get("Style", "")).strip() or "Unclassified"
                try:
                    self.stage_prestiges[group_id] = max(
                        self.stage_prestiges.get(group_id, 0),
                        int(str(row.get("Prestige", "0")).strip() or 0),
                    )
                except ValueError:
                    self.stage_prestiges[group_id] = 0
        self._sort_stage_ids()
        values = []
        self.available_label_to_id = {}
        for group_id, label in groups.items():
            if group_id in self.stage_ids:
                continue
            style = self.stage_styles.get(group_id, "")
            searchable = f"{label} {style} {group_id}".casefold()
            if search_terms and not all(term in searchable for term in search_terms):
                continue
            display = label
            if display in self.available_label_to_id:
                display = f"{label} ({group_id})"
            self.available_label_to_id[display] = group_id
            values.append(display)
        self.available_menu.configure(values=values)
        if values:
            self.available_menu.set(values[0])

    def _championship_search_changed(self) -> None:
        self._refresh_available()

    def _render_stages(self) -> None:
        for widget in self.stage_frame.winfo_children():
            widget.destroy()
        if not self.stage_ids:
            ctk.CTkLabel(self.stage_frame, text="No stages yet. Add championships from the list below.", text_color="gray").pack(anchor="w", padx=10, pady=10)
            return
        current_style = ""
        for index, stage_id in enumerate(self.stage_ids):
            style = self.stage_styles.get(stage_id, "Unclassified")
            if style != current_style:
                ctk.CTkLabel(
                    self.stage_frame,
                    text=style,
                    font=ctk.CTkFont(size=12, weight="bold"),
                    text_color="#4da6ff",
                    anchor="w",
                ).pack(fill="x", padx=10, pady=(8, 2))
                current_style = style
            row = ctk.CTkFrame(self.stage_frame, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=3)
            ctk.CTkLabel(row, text=f"{index + 1}. {self.stage_labels.get(stage_id, stage_id)}", anchor="w").pack(side="left", fill="x", expand=True)
            ctk.CTkButton(row, text="↑", width=28, command=lambda i=index: self._move_stage(i, -1)).pack(side="right", padx=2)
            ctk.CTkButton(row, text="↓", width=28, command=lambda i=index: self._move_stage(i, 1)).pack(side="right", padx=2)
            ctk.CTkButton(row, text="Remove", width=70, command=lambda i=index: self._remove_stage(i), fg_color="gray30", hover_color="gray40").pack(side="right", padx=2)

    def _add_stage(self) -> None:
        value = self.available_menu.get()
        stage_id = self.available_label_to_id.get(value, "")
        if stage_id and stage_id in self.stage_labels:
            self.stage_ids.append(stage_id)
            self._refresh_available()
            self._render_stages()

    def _remove_stage(self, index: int) -> None:
        self.stage_ids.pop(index)
        self._refresh_available()
        self._render_stages()

    def _move_stage(self, index: int, delta: int) -> None:
        target = index + delta
        if 0 <= target < len(self.stage_ids):
            self.stage_ids[index], self.stage_ids[target] = self.stage_ids[target], self.stage_ids[index]
            self._render_stages()

    def _sort_stage_ids(self) -> None:
        self.stage_ids.sort(
            key=lambda stage_id: (
                self.stage_styles.get(stage_id, "Unclassified").casefold(),
                -self.stage_prestiges.get(stage_id, 0),
                self.stage_labels.get(stage_id, stage_id).casefold(),
            )
        )

    def _delete_path(self, payload: dict[str, object]) -> None:
        path_id = str(payload.get("path_id", "")).strip()
        title = str(payload.get("title", "Career Path")).strip() or "Career Path"
        if not messagebox.askyesno("Delete Career Path", f"Delete '{title}'? This cannot be undone."):
            return
        success, message = delete_career_path(path_id)
        self.status_label.configure(text=message, text_color="#4da6ff" if success else "#ff7777")
        if success:
            self.paths = list_career_paths()
            self._render_paths()
            self._load_path(default_career_path(self.game_var.get()))

    def _payload(self) -> dict[str, object]:
        return {"schema_version": 1, "package_type": "career_path", "path_id": self.current.get("path_id", ""), "title": self.title_entry.get().strip() or "Career Path", "author": self.author_entry.get().strip(), "description": self.description_entry.get().strip(), "game": self.game_var.get(), "championship_ids": list(self.stage_ids)}

    def _save(self) -> None:
        if str(self.current.get("path_id", "")).strip() == "default":
            self.status_label.configure(text="The built-in Default Career Path cannot be changed.", text_color="#ffbb55")
            return
        path = save_career_path(self._payload())
        self.status_label.configure(text=f"Saved {path.name}.", text_color="#4da6ff")
        self.paths = list_career_paths()
        self._render_paths()

    def _export(self) -> None:
        destination = filedialog.asksaveasfilename(defaultextension=".circuitstacker.json", filetypes=[("Circuit Stackers Career Path", "*.circuitstacker.json")])
        if destination:
            export_career_path(self._payload(), Path(destination))
            self.status_label.configure(text="Career path exported.", text_color="#4da6ff")

    def _import(self) -> None:
        selected = filedialog.askopenfilename(filetypes=[("Circuit Stackers Career Path", "*.circuitstacker.json"), ("JSON", "*.json")])
        if not selected:
            return
        try:
            payload = json.loads(Path(selected).read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Invalid career path file.")
            saved = save_career_path(payload)
            self.paths = list_career_paths()
            self._render_paths()
            self._load_path(payload)
            self.status_label.configure(text=f"Imported {saved.name}.", text_color="#4da6ff")
        except (OSError, json.JSONDecodeError, ValueError) as error:
            self.status_label.configure(text=f"Import failed: {error}", text_color="#ff7777")
