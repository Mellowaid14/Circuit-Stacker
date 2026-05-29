from __future__ import annotations

import ctypes
import re
import time
from typing import Any


def pyside6_available() -> bool:
    return _HAS_QT


def parse_geometry(geometry: str, fallback: tuple[int, int, int, int] = (520, 520, 80, 80)) -> tuple[int, int, int, int]:
    match = re.match(r"^(\d+)x(\d+)([+-]\d+)([+-]\d+)$", str(geometry).strip())
    if not match:
        return fallback
    return tuple(int(value) for value in match.groups())  # type: ignore[return-value]


class QtAms2LeaderboardOverlay:
    def __init__(self, geometry: str, on_closed=None) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication

        self._app = QApplication.instance() or QApplication([])
        self._widget = _LeaderboardWidget(on_closed=on_closed)
        width, height, x, y = parse_geometry(geometry)
        self._widget.setGeometry(x, y, width, height)
        self._widget.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.Tool
        )
        self._widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._widget.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._widget.setStyleSheet("background: transparent; border: none;")
        window_transparent_for_input = getattr(Qt.WindowType, "WindowTransparentForInput", None)
        if window_transparent_for_input is not None:
            self._widget.setWindowFlag(window_transparent_for_input, True)
        self._widget.show()
        _make_window_click_through(int(self._widget.winId()))
        self._widget.raise_()
        self._app.processEvents()

    def render(self, rows: list[dict[str, Any]], all_synced: bool, status: str, header_text: Any) -> None:
        self._widget.set_data(rows, all_synced, status, header_text)
        self._app.processEvents()

    def apply_geometry(self, geometry: str) -> None:
        width, height, x, y = parse_geometry(geometry)
        self._widget.setGeometry(x, y, width, height)
        self._app.processEvents()

    def exists(self) -> bool:
        return not self._widget.isHidden()

    def lift(self) -> None:
        self._widget.raise_()
        self._widget.activateWindow()
        self._app.processEvents()

    def close(self) -> None:
        self._widget.close()
        self._app.processEvents()


def _make_window_click_through(hwnd: int) -> None:
    if not hwnd:
        return
    try:
        user32 = ctypes.windll.user32
        get_window_long = user32.GetWindowLongPtrW
        set_window_long = user32.SetWindowLongPtrW
        get_window_long.restype = ctypes.c_void_p
        get_window_long.argtypes = [ctypes.c_void_p, ctypes.c_int]
        set_window_long.restype = ctypes.c_void_p
        set_window_long.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        current_style = int(get_window_long(ctypes.c_void_p(hwnd), -20) or 0)
        click_through_style = current_style | 0x00080000 | 0x00000020 | 0x08000000
        set_window_long(ctypes.c_void_p(hwnd), -20, ctypes.c_void_p(click_through_style))
    except Exception:
        pass
    try:
        dwmapi = ctypes.windll.dwmapi
        # Windows can draw a 1px native border around transparent tool windows.
        # Ask DWM to remove that non-client trim so only our painted cards show.
        disabled_policy = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd),
            2,  # DWMWA_NCRENDERING_POLICY
            ctypes.byref(disabled_policy),
            ctypes.sizeof(disabled_policy),
        )
        no_border = ctypes.c_int(0xFFFFFFFE)
        dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd),
            34,  # DWMWA_BORDER_COLOR
            ctypes.byref(no_border),
            ctypes.sizeof(no_border),
        )
    except Exception:
        pass


def _load_qt_classes():
    from PySide6.QtCore import QRectF, Qt, QTimer
    from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
    from PySide6.QtWidgets import QWidget

    return QRectF, Qt, QTimer, QColor, QFont, QPainter, QPen, QPixmap, QWidget


try:
    QRectF, Qt, QTimer, QColor, QFont, QPainter, QPen, QPixmap, QWidget = _load_qt_classes()
    _HAS_QT = True
except Exception:
    QRectF = Qt = QTimer = QColor = QFont = QPainter = QPen = QPixmap = None
    QWidget = object
    _HAS_QT = False


class _LeaderboardWidget(QWidget):
    def __init__(self, on_closed=None) -> None:
        super().__init__()
        self._on_closed = on_closed
        self._rows: list[dict[str, Any]] = []
        self._all_synced = False
        self._status = "App synced to drivers: checking..."
        self._header_text: Any = "- / - / L0 / -"
        self._header_updated_at = time.monotonic()
        self._pixmaps: dict[str, QPixmap] = {}
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self.update)
        self._timer.start()

    def set_data(self, rows: list[dict[str, Any]], all_synced: bool, status: str, header_text: Any) -> None:
        self._rows = rows[:16]
        self._all_synced = bool(all_synced)
        self._status = status
        self._header_text = header_text
        self._header_updated_at = time.monotonic()
        self.update()

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._on_closed:
            self._on_closed()
        super().closeEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        width = self.width()
        x = 4
        top = 4
        card_width = max(250, width - 8)

        self._draw_card(painter, QRectF(x, top, card_width, 30), QColor(0, 0, 0, 190), 12)
        painter.setPen(QColor(245, 245, 245, 245))
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self._draw_header_parts(painter, x + 10, top + 7, card_width - 20)

        row_y = top + 34
        row_height = 38
        driver_index = 0
        for row in self._rows:
            if row_y > self.height() - 28:
                break
            if row.get("_row_type") == "class_header":
                self._draw_class_header(painter, row, x, row_y, card_width)
                row_y += 18
                continue
            row_rect = QRectF(x, row_y, card_width, row_height)
            row_color = QColor(46, 46, 46, 204) if driver_index % 2 else QColor(28, 28, 28, 204)
            self._draw_card(painter, row_rect, row_color, 8)
            if row.get("_is_player"):
                self._draw_player_glow(painter, row_rect)
            self._draw_class_strip(painter, row, row_rect)
            self._draw_row(painter, row, x, row_y, card_width, row_height)
            row_y += row_height
            driver_index += 1

        status_y = row_y + 4
        color = QColor(54, 182, 107, 245) if self._all_synced else QColor(216, 90, 90, 245)
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(x + 2, status_y + 4, 12, 12)
        painter.setPen(color)
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(QRectF(x + 22, status_y, card_width - 24, 20), Qt.AlignmentFlag.AlignLeft, self._status)

    def _draw_class_header(self, painter, row: dict[str, Any], x: int, y: int, width: int) -> None:
        class_name = str(row.get("_class_name", "Class") or "Class")
        count = str(row.get("_class_count", "") or "")
        color = self._class_color(str(row.get("_class_color", "green") or "green"))
        badge_width = min(width - 8, max(72, 10 + (len(class_name) + len(count) + 1) * 7))
        badge_rect = QRectF(x + 4, y + 2, badge_width, 14)
        self._draw_card(painter, badge_rect, color, 4)
        painter.setPen(QColor(12, 12, 12, 245))
        painter.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        painter.drawText(
            badge_rect.adjusted(5, -1, -5, 1),
            Qt.AlignmentFlag.AlignCenter,
            f"{class_name} {count}".strip(),
        )

    def _draw_header_parts(self, painter, x: int, y: int, width: int) -> None:
        parts = self._current_header_parts()
        while len(parts) < 3:
            parts.append("-")
        parts = parts[:3]
        segment_width = max(1, width / 3)
        alignments = [
            Qt.AlignmentFlag.AlignLeft,
            Qt.AlignmentFlag.AlignCenter,
            Qt.AlignmentFlag.AlignRight,
        ]
        for index, part in enumerate(parts):
            painter.drawText(
                QRectF(x + (segment_width * index), y, segment_width, 18),
                alignments[index],
                part,
            )

    def _current_header_parts(self) -> list[str]:
        if isinstance(self._header_text, dict):
            session = str(self._header_text.get("session", "-") or "-")
            remaining_seconds = float(self._header_text.get("remaining_seconds", 0.0) or 0.0)
            elapsed = max(0.0, time.monotonic() - self._header_updated_at)
            live_remaining = max(0.0, remaining_seconds - elapsed)
            if self._header_text.get("uses_lap_count"):
                progress = str(self._header_text.get("progress", "-") or "-")
            else:
                progress = self._format_time_left(live_remaining)
            lap_text = self._lap_estimate_text(live_remaining)
            return [session, progress, lap_text]
        return [part.strip() for part in str(self._header_text).split("/") if part.strip()]

    def _lap_estimate_text(self, remaining_seconds: float) -> str:
        current_lap = max(1, int(self._header_text.get("current_lap", 1) or 1))
        estimated_total_laps = float(self._header_text.get("estimated_total_laps", 0.0) or 0.0)
        if estimated_total_laps > 0:
            return f"L{current_lap}/~{estimated_total_laps:.1f}"
        return f"L{current_lap}/~-"

    @staticmethod
    def _format_time_left(seconds: float) -> str:
        if seconds <= 0:
            return "0:00"
        total_seconds = int(round(seconds))
        minutes, secs = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"

    def _draw_row(self, painter, row: dict[str, Any], x: int, y: int, width: int, height: int) -> None:
        painter.setPen(QColor(255, 255, 255, 245))
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        painter.drawText(QRectF(x + 12, y + 10, 34, 18), Qt.AlignmentFlag.AlignLeft, str(row.get("pos", "")))
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(QRectF(x + 50, y + 10, 145, 18), Qt.AlignmentFlag.AlignLeft, str(row.get("name", "")))

        logo_path = str(row.get("_logo_path", "") or "")
        if logo_path:
            pixmap = self._pixmaps.get(logo_path)
            if pixmap is None:
                pixmap = QPixmap(logo_path)
                self._pixmaps[logo_path] = pixmap
            if not pixmap.isNull():
                scaled = pixmap.scaled(62, 24, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                painter.drawPixmap(x + 205, y + 7, scaled)

        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        painter.drawText(QRectF(x + 285, y + 10, 70, 18), Qt.AlignmentFlag.AlignLeft, str(row.get("gap", "")))

    @staticmethod
    def _draw_card(painter, rect: QRectF, color: QColor, radius: int) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(rect, radius, radius)

    def _draw_class_strip(self, painter, row: dict[str, Any], rect: QRectF) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._class_color(str(row.get("_class_color", "green") or "green")))
        painter.drawRoundedRect(QRectF(rect.x(), rect.y(), 6, rect.height()), 4, 4)

    @staticmethod
    def _draw_player_glow(painter, rect: QRectF) -> None:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for inset, alpha, width in [(0, 120, 3), (2, 210, 2)]:
            glow_rect = rect.adjusted(inset, inset, -inset, -inset)
            painter.setPen(QPen(QColor(48, 154, 255, alpha), width))
            painter.drawRoundedRect(glow_rect, 8, 8)
        painter.setPen(Qt.PenStyle.NoPen)

    @staticmethod
    def _class_color(name: str) -> QColor:
        colors = {
            "green": QColor(92, 218, 125, 230),
            "yellow": QColor(238, 214, 84, 230),
            "red": QColor(234, 92, 92, 230),
            "blue": QColor(77, 166, 255, 230),
        }
        return colors.get(name, colors["green"])
