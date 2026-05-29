from __future__ import annotations

import ctypes
from pathlib import Path


class MenuMusicPlayer:
    def __init__(self, audio_path: Path) -> None:
        self.audio_path = audio_path
        self._alias = "circuit_stacker_menu_music"
        self._is_open = False
        self._is_playing = False
        self._volume = 0.45

    def play_loop(self) -> None:
        if not self.audio_path.exists():
            return
        if not self._is_open and not self._send(f'open "{self.audio_path}" type mpegvideo alias {self._alias}'):
            return
        self.set_volume(self._volume)
        if self._send(f"play {self._alias} repeat"):
            self._is_playing = True

    def stop(self) -> None:
        if not self._is_open:
            return
        self._send(f"stop {self._alias}")
        self._send(f"close {self._alias}")
        self._is_open = False
        self._is_playing = False

    def set_volume(self, volume: float) -> None:
        self._volume = max(0.0, min(1.0, float(volume)))
        if self._is_open:
            self._send(f"setaudio {self._alias} volume to {int(self._volume * 1000)}")

    def _send(self, command: str) -> bool:
        buffer = ctypes.create_unicode_buffer(255)
        result = ctypes.windll.winmm.mciSendStringW(command, buffer, len(buffer), None)
        if result == 0:
            if command.startswith("open "):
                self._is_open = True
            return True
        if command.startswith("open "):
            self._is_open = False
        return False
