from __future__ import annotations

import threading
import webbrowser

import customtkinter as ctk

from .screens.championship_screen import ChampionshipScreen
from .screens.custom_championship_manage_screen import CustomChampionshipManageScreen
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
from .screens.settings_screen import SettingsScreen
from .screens.season_recap_screen import SeasonRecapScreen
from .screens.sim_progress_screen import SimProgressScreen
from .screens.world_setup_screen import WorldSetupScreen
from .screens.world_championships_screen import WorldChampionshipsScreen
from .screens.world_championship_detail_screen import WorldChampionshipDetailScreen
from .screens.schedule_screen import ScheduleScreen
from .menu_music import MenuMusicPlayer
from .paths import resource_path
from .settings_manager import load_settings
from .update_checker import UpdateInfo, check_for_update, update_check_configured
from .version import APP_VERSION


ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

ICON_CANDIDATES = [
    resource_path("assets", "circuit_stacker_icon.ico"),
]
MENU_MUSIC_PATH = resource_path("assets", "Circuit Stacker Splash Screen Loop.mp3")


class UpdateAvailablePopup(ctk.CTkToplevel):
    def __init__(self, parent, update_info: UpdateInfo) -> None:
        super().__init__(parent)
        self.update_info = update_info
        self.title("Circuit Stacker Update Available")
        self.geometry("520x360")
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

        notes = update_info.release_notes.strip() or "No release notes were added for this update."
        if len(notes) > 700:
            notes = notes[:700].rstrip() + "..."
        notes_box = ctk.CTkTextbox(shell, height=120, wrap="word", font=ctk.CTkFont(size=11))
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
        self._update_check_running = False
        self._update_popup_shown = False
        self.menu_music = MenuMusicPlayer(MENU_MUSIC_PATH)
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
            command=lambda: self.show_screen("SettingsScreen"),
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

        self.screens: dict[str, ctk.CTkFrame] = {}
        for screen_class in [
            MenuScreen,
            NewGame,
            LoadScreen,
            ChampionshipScreen,
            CustomChampionshipScreen,
            CustomChampionshipManageScreen,
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
        for screen in self.screens.values():
            if screen.winfo_ismapped() and hasattr(screen, "on_hide"):
                screen.on_hide()
            screen.pack_forget()

        target = self.screens[name]
        target.pack(fill="both", expand=True)
        if hasattr(target, "on_show"):
            target.on_show()

    def window_is_changing(self) -> bool:
        return self._window_changing

    def set_menu_music_active(self, active: bool) -> None:
        self._menu_music_active = active
        self._sync_menu_music()

    def toggle_menu_music(self) -> None:
        self._menu_music_muted = not self._menu_music_muted
        self.music_btn.configure(text="\U0001f507" if self._menu_music_muted else "\U0001f50a")
        self._sync_menu_music()

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
