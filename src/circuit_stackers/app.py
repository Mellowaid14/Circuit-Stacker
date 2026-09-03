from __future__ import annotations

import threading
import webbrowser

import customtkinter as ctk

from .screens.championship_screen import ChampionshipScreen
from .screens.custom_championship_manage_screen import CustomChampionshipManageScreen
from .screens.career_path_editor_screen import CareerPathEditorScreen
from .screens.custom_championship_screen import CustomChampionshipScreen
from .screens.driver_pool_screen import DriverPoolScreen
from .screens.driver_detail_screen import DriverDetailScreen
from .screens.driver_race_history_screen import DriverRaceHistoryScreen
from .screens.team_pool_screen import TeamPoolScreen
from .screens.team_detail_screen import TeamDetailScreen
from .screens.gameplay_screen import GameplayScreen
from .screens.load_screen import LoadScreen
from .screens.messages_screen import MessagesScreen
from .screens.race_results_screen import RaceResultsScreen
from .screens.race_weekend_screen import RaceWeekendScreen
from .screens.manual_results_screen import ManualResultsScreen
from .screens.manual_setup_screen import ManualSetupScreen
from .screens.menu_screen import MenuScreen
from .screens.new_game import NewGame
from .screens.ownership_screen import OwnershipScreen
from .screens.player_profiles_screen import PlayerProfilesScreen
from .screens.settings_screen import SettingsScreen
from .screens.season_recap_screen import SeasonRecapScreen
from .screens.sim_progress_screen import SimProgressScreen
from .screens.world_setup_screen import WorldSetupScreen
from .screens.world_championships_screen import WorldChampionshipsScreen
from .screens.world_championship_detail_screen import WorldChampionshipDetailScreen
from .screens.schedule_screen import ScheduleScreen
from .menu_music import MenuMusicPlayer
from .paths import resource_path
from .settings_manager import load_settings, update_menu_music_volume
from .update_checker import UpdateInfo, check_for_update, update_check_configured
from .version import APP_VERSION


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

ICON_CANDIDATES = [
    resource_path("assets", "circuit_stacker_icon.ico"),
]
MENU_MUSIC_PATH = resource_path("assets", "Circuit Stacker Splash Screen Loop.mp3")
SETTINGS_CHILD_SCREENS = {
    "CustomChampionshipScreen",
    "CustomChampionshipManageScreen",
    "CareerPathEditorScreen",
    "OwnershipScreen",
    "PlayerProfilesScreen",
}


class UpdateAvailablePopup(ctk.CTkToplevel):
    def __init__(self, parent, update_info: UpdateInfo) -> None:
        super().__init__(parent)
        self.update_info = update_info
        self.title("Circuit Stacker Update Available")
        self.geometry("560x460")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        shell = ctk.CTkFrame(self, fg_color=("gray90", "gray15"), corner_radius=14)
        shell.pack(fill="both", expand=True, padx=18, pady=18)
        ctk.CTkLabel(
            shell,
            text="Update Available",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=("#1a6fc4", "#4da6ff"),
        ).pack(anchor="w", padx=18, pady=(18, 4))
        ctk.CTkLabel(
            shell,
            text=f"Circuit Stacker {update_info.latest_version} is available. You are running {update_info.current_version}.",
            font=ctk.CTkFont(size=13),
            justify="left",
            wraplength=460,
        ).pack(anchor="w", padx=18, pady=(0, 12))

        ctk.CTkLabel(
            shell,
            text="Patch Notes",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=("#1a6fc4", "#4da6ff"),
        ).pack(anchor="w", padx=18, pady=(0, 6))

        notes = _format_release_notes(update_info.release_notes)
        notes_box = ctk.CTkTextbox(shell, height=190, wrap="word", font=ctk.CTkFont(size=11))
        notes_box.pack(fill="x", padx=18, pady=(0, 14))
        notes_box.insert("1.0", notes)
        notes_box.configure(state="disabled")

        actions = ctk.CTkFrame(shell, fg_color="transparent")
        actions.pack(fill="x", padx=18, pady=(0, 18))
        ctk.CTkButton(
            actions,
            text="Download Update",
            command=self._open_download,
            width=150,
            height=34,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left")
        ctk.CTkButton(
            actions,
            text="Later",
            command=self.destroy,
            width=100,
            height=34,
            fg_color="gray30",
            hover_color="gray40",
            font=ctk.CTkFont(size=12),
        ).pack(side="right")

    def _open_download(self) -> None:
        webbrowser.open(self.update_info.download_url)
        self.destroy()


def _format_release_notes(release_notes: str) -> str:
    notes = release_notes.strip() or "No patch notes were added for this update."
    notes = notes.replace("\r\n", "\n").replace("\r", "\n")
    if len(notes) > 2200:
        notes = notes[:2200].rstrip() + "\n\n...open the GitHub release page to read the full notes."
    return notes


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Circuit Stackers")
        self.geometry("1400x900")
        self.minsize(1200, 760)
        self.resizable(True, True)
        self._window_changing = False
        self._window_change_after_id: str | None = None
        self._menu_music_active = False
        self._menu_music_muted = False
        self._music_volume_hide_after_id: str | None = None
        self._music_volume_save_after_id: str | None = None
        self._update_check_running = False
        self._update_popup_shown = False
        self.current_screen_name = ""
        self.settings_return_screen = "MenuScreen"
        settings = load_settings()
        self._menu_music_volume = float(settings.get("menu_music_volume", 0.45))
        self.menu_music = MenuMusicPlayer(MENU_MUSIC_PATH)
        self.menu_music.set_volume(self._menu_music_volume)
        self._apply_window_icon()
        self.bind("<Configure>", self._track_window_change)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(side="bottom", pady=12)

        self.toggle_btn = ctk.CTkButton(
            footer,
            text="Dark Mode",
            command=self.toggle_mode,
            width=120,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color="transparent",
            border_width=1,
            text_color=("gray30", "gray70"),
        )
        self.toggle_btn.pack(side="left", padx=(0, 10))

        self.settings_btn = ctk.CTkButton(
            footer,
            text="Settings",
            command=self.open_settings,
            width=120,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color="transparent",
            border_width=1,
            text_color=("gray30", "gray70"),
        )
        self.settings_btn.pack(side="left")

        self.music_btn = ctk.CTkButton(
            footer,
            text="\U0001f50a",
            command=self.toggle_menu_music,
            width=44,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color="transparent",
            border_width=1,
            text_color=("gray30", "gray70"),
        )
        self.music_btn.pack(side="left", padx=(10, 0))
        self.music_btn.bind("<Enter>", self._show_music_volume_slider)
        self.music_btn.bind("<Leave>", self._schedule_hide_music_volume_slider)

        self.music_volume_popup = ctk.CTkFrame(
            self,
            width=178,
            height=64,
            fg_color=("gray88", "gray16"),
            corner_radius=10,
            border_width=1,
            border_color=("gray65", "gray35"),
        )
        self.music_volume_popup.bind("<Enter>", self._show_music_volume_slider)
        self.music_volume_popup.bind("<Leave>", self._schedule_hide_music_volume_slider)
        ctk.CTkLabel(
            self.music_volume_popup,
            text="Volume",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=("gray25", "gray75"),
        ).pack(anchor="w", padx=12, pady=(8, 2))
        self.music_volume_slider = ctk.CTkSlider(
            self.music_volume_popup,
            from_=0,
            to=1,
            number_of_steps=100,
            width=150,
            height=16,
            command=self.set_menu_music_volume,
        )
        self.music_volume_slider.set(self._menu_music_volume)
        self.music_volume_slider.pack(padx=12, pady=(0, 10))
        self.music_volume_slider.bind("<Enter>", self._show_music_volume_slider)
        self.music_volume_slider.bind("<Leave>", self._schedule_hide_music_volume_slider)

        self.screens: dict[str, ctk.CTkFrame] = {}
        for screen_class in [
            MenuScreen,
            NewGame,
            LoadScreen,
            ChampionshipScreen,
            CustomChampionshipScreen,
            CustomChampionshipManageScreen,
            CareerPathEditorScreen,
            GameplayScreen,
            DriverPoolScreen,
            DriverDetailScreen,
            DriverRaceHistoryScreen,
            TeamPoolScreen,
            TeamDetailScreen,
            MessagesScreen,
            RaceResultsScreen,
            RaceWeekendScreen,
            ManualResultsScreen,
            ManualSetupScreen,
            SeasonRecapScreen,
            SimProgressScreen,
            WorldSetupScreen,
            ScheduleScreen,
            WorldChampionshipsScreen,
            WorldChampionshipDetailScreen,
            SettingsScreen,
            PlayerProfilesScreen,
            OwnershipScreen,
        ]:
            screen = screen_class(self, self.show_screen)
            self.screens[screen_class.__name__] = screen

        manual_results = self.screens["ManualResultsScreen"]
        race_weekend = self.screens["RaceWeekendScreen"]
        manual_setup = self.screens["ManualSetupScreen"]
        gameplay = self.screens["GameplayScreen"]
        race_results = self.screens["RaceResultsScreen"]
        schedule_screen = self.screens["ScheduleScreen"]
        driver_pool = self.screens["DriverPoolScreen"]
        team_pool = self.screens["TeamPoolScreen"]
        messages_screen = self.screens["MessagesScreen"]
        sim_progress = self.screens["SimProgressScreen"]
        world_championships = self.screens["WorldChampionshipsScreen"]
        if hasattr(manual_results, "set_gameplay_screen"):
            manual_results.set_gameplay_screen(gameplay)
        if hasattr(race_weekend, "set_gameplay_screen"):
            race_weekend.set_gameplay_screen(gameplay)
        if hasattr(manual_setup, "set_gameplay_screen"):
            manual_setup.set_gameplay_screen(gameplay)
        if hasattr(race_results, "set_gameplay_screen"):
            race_results.set_gameplay_screen(gameplay)
        if hasattr(schedule_screen, "set_gameplay_screen"):
            schedule_screen.set_gameplay_screen(gameplay)
        if hasattr(driver_pool, "set_gameplay_screen"):
            driver_pool.set_gameplay_screen(gameplay)
        if hasattr(team_pool, "set_gameplay_screen"):
            team_pool.set_gameplay_screen(gameplay)
        if hasattr(messages_screen, "set_gameplay_screen"):
            messages_screen.set_gameplay_screen(gameplay)
        if hasattr(sim_progress, "set_gameplay_screen"):
            sim_progress.set_gameplay_screen(gameplay)
        if hasattr(world_championships, "set_gameplay_screen"):
            world_championships.set_gameplay_screen(gameplay)

        self.show_screen("MenuScreen")
        self.after(1200, self._run_launch_update_check)

    def show_screen(self, name: str) -> None:
        if (
            name == "SettingsScreen"
            and self.current_screen_name
            and self.current_screen_name != "SettingsScreen"
            and self.current_screen_name not in SETTINGS_CHILD_SCREENS
        ):
            self.settings_return_screen = self.current_screen_name

        for screen in self.screens.values():
            if screen.winfo_ismapped() and hasattr(screen, "on_hide"):
                screen.on_hide()
            screen.pack_forget()

        target = self.screens[name]
        target.pack(fill="both", expand=True)
        self.current_screen_name = name
        if hasattr(target, "on_show"):
            target.on_show()

    def open_settings(self) -> None:
        self.show_screen("SettingsScreen")

    def return_from_settings(self) -> None:
        target = self.settings_return_screen
        if target not in self.screens or target == "SettingsScreen":
            target = "MenuScreen"
        self.show_screen(target)

    def window_is_changing(self) -> bool:
        return self._window_changing

    def set_menu_music_active(self, active: bool) -> None:
        self._menu_music_active = active
        self._sync_menu_music()

    def toggle_menu_music(self) -> None:
        self._menu_music_muted = not self._menu_music_muted
        self.music_btn.configure(text="\U0001f507" if self._menu_music_muted else "\U0001f50a")
        self._sync_menu_music()

    def set_menu_music_volume(self, volume: float) -> None:
        self._menu_music_volume = max(0.0, min(1.0, float(volume)))
        self.menu_music.set_volume(self._menu_music_volume)
        if self._music_volume_save_after_id is not None:
            try:
                self.after_cancel(self._music_volume_save_after_id)
            except Exception:
                pass
        self._music_volume_save_after_id = self.after(350, self._save_menu_music_volume)

    def _save_menu_music_volume(self) -> None:
        self._music_volume_save_after_id = None
        update_menu_music_volume(self._menu_music_volume)

    def _show_music_volume_slider(self, _event=None) -> None:
        if self._music_volume_hide_after_id is not None:
            try:
                self.after_cancel(self._music_volume_hide_after_id)
            except Exception:
                pass
            self._music_volume_hide_after_id = None
        self._position_music_volume_popup()
        self.music_volume_popup.lift()

    def _schedule_hide_music_volume_slider(self, _event=None) -> None:
        if self._music_volume_hide_after_id is not None:
            try:
                self.after_cancel(self._music_volume_hide_after_id)
            except Exception:
                pass
        self._music_volume_hide_after_id = self.after(450, self._hide_music_volume_slider)

    def _hide_music_volume_slider(self) -> None:
        self._music_volume_hide_after_id = None
        if self.music_volume_popup.winfo_ismapped():
            self.music_volume_popup.place_forget()

    def _position_music_volume_popup(self) -> None:
        self.update_idletasks()
        popup_width = 178
        popup_height = 64
        button_x = self.music_btn.winfo_rootx() - self.winfo_rootx()
        button_y = self.music_btn.winfo_rooty() - self.winfo_rooty()
        button_center_x = button_x + self.music_btn.winfo_width() // 2
        x = max(8, min(self.winfo_width() - popup_width - 8, button_center_x - popup_width // 2))
        y = max(8, button_y - popup_height - 8)
        self.music_volume_popup.place(x=x, y=y)

    def _sync_menu_music(self) -> None:
        if self._menu_music_active and not self._menu_music_muted:
            self.menu_music.play_loop()
        else:
            self.menu_music.stop()

    def _track_window_change(self, event) -> None:
        if event.widget is not self:
            return
        self._window_changing = True
        if self._window_change_after_id is not None:
            try:
                self.after_cancel(self._window_change_after_id)
            except Exception:
                pass
        self._window_change_after_id = self.after(220, self._mark_window_change_complete)

    def _mark_window_change_complete(self) -> None:
        self._window_changing = False
        self._window_change_after_id = None
        # Windows/DWM can occasionally leave a Tk window visually translucent
        # after a move or resize. The main application window should always be
        # opaque; restore that state once the Configure-event burst settles.
        try:
            self.attributes("-alpha", 1.0)
        except Exception:
            pass

    def toggle_mode(self) -> None:
        mode = ctk.get_appearance_mode()
        new_mode = "light" if mode == "Dark" else "dark"
        ctk.set_appearance_mode(new_mode)
        self.toggle_btn.configure(text="Light Mode" if new_mode == "light" else "Dark Mode")

    def _apply_window_icon(self) -> None:
        for icon_path in ICON_CANDIDATES:
            if not icon_path.exists():
                continue
            try:
                self.iconbitmap(icon_path)
                return
            except Exception:
                continue

    def _run_launch_update_check(self) -> None:
        settings = load_settings()
        if not bool(settings.get("check_for_updates_on_launch", True)):
            return
        self.run_update_check(manual=False)

    def run_update_check(self, manual: bool = False) -> None:
        if self._update_check_running:
            return
        if not update_check_configured():
            if manual:
                self._show_update_status("GitHub update repo is not configured yet.")
            return
        self._update_check_running = True
        threading.Thread(target=self._check_for_updates_in_background, args=(manual,), daemon=True).start()

    def _check_for_updates_in_background(self, manual: bool) -> None:
        update_info = check_for_update()
        self.after(0, lambda: self._handle_update_check_result(update_info, manual))

    def _handle_update_check_result(self, update_info: UpdateInfo | None, manual: bool) -> None:
        self._update_check_running = False
        if update_info is None:
            if manual:
                self._show_update_status(f"Circuit Stacker {APP_VERSION} is up to date.")
            return
        if self._update_popup_shown and not manual:
            return
        self._update_popup_shown = True
        UpdateAvailablePopup(self, update_info)

    def _show_update_status(self, message: str) -> None:
        settings_screen = self.screens.get("SettingsScreen")
        status_label = getattr(settings_screen, "status_label", None)
        if status_label is not None:
            status_label.configure(text=message)


def launch_app() -> None:
    app = App()
    app.mainloop()
