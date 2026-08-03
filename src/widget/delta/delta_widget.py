from __future__ import annotations

import time
from collections import deque
from pathlib import Path
from typing import Any

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QMouseEvent, QPaintEvent, QPainter
from PySide6.QtWidgets import QWidget

from .delta_animation import SmoothValue, TimedFade
from .delta_logo_manager import DeltaLogoManager
from .delta_models import DeltaSectorData, DeltaViewData, FastestLapData
from .delta_renderer import DeltaRenderer
from .delta_session_tracker import DeltaSessionTracker


class DeltaWidget(QWidget):
    geometry_changed = Signal(str, float, float, float, float)
    selected = Signal(str)

    def __init__(
        self,
        widget_id: str,
        config: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.widget_id = widget_id
        self.config = config
        self.project_root = Path(__file__).resolve().parents[3]

        self.logo_manager = DeltaLogoManager(
            self.project_root,
            str(config.get("logo_directory", "images/logos")),
        )
        self.session_tracker = DeltaSessionTracker(self.logo_manager)
        self.renderer = DeltaRenderer(self.logo_manager)

        self.view_data = DeltaViewData()
        self._target_delta = 0.0
        self._smooth_delta = SmoothValue(response=float(config.get("delta_smoothing", 12.0)))
        self._fastest_fade = TimedFade()
        self._fastest_data: FastestLapData | None = None
        self._last_fastest_visible = False
        self._delta_history: deque[float] = deque(
            maxlen=max(20, int(config.get("history_points", 240)))
        )

        self.edit_mode = False
        self._dragging = False
        self._resizing = False
        self._drag_offset = QPoint()
        self._resize_start_global = QPoint()
        self._resize_start_size = None
        self._fitting_content = False
        self._last_tick = time.monotonic()

        self.setMinimumSize(420, 130)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle("Sector Flow Drive - Delta V2")

        self._animation_timer = QTimer(self)
        self._animation_timer.timeout.connect(self._animate)
        self._animation_timer.start(33)

        self.apply_config()

    def apply_config(self) -> None:
        self.setWindowOpacity(float(self.config.get("opacity", 0.96)))
        self._smooth_delta.response = max(1.0, float(self.config.get("delta_smoothing", 12.0)))

        history_points = max(20, int(self.config.get("history_points", 240)))
        if self._delta_history.maxlen != history_points:
            self._delta_history = deque(self._delta_history, maxlen=history_points)

        self.logo_manager.set_directory(str(self.config.get("logo_directory", "images/logos")))
        self._fit_content_if_enabled()
        self.update()

    def apply_normalized_geometry(self, screen_geometry) -> None:
        position = self.config.get("position", {})
        size = self.config.get("size", {})
        scale = float(self.config.get("scale", 1.0))

        width = max(
            self.minimumWidth(),
            int(screen_geometry.width() * float(size.get("width", 0.56)) * scale),
        )
        configured_height = max(
            self.minimumHeight(),
            int(screen_geometry.height() * float(size.get("height", 0.36)) * scale),
        )
        height = (
            self.renderer.preferred_height(width, self.config, self._fastest_is_visible())
            if bool(self.config.get("auto_fit_content", True))
            else configured_height
        )

        x = int(
            screen_geometry.left()
            + screen_geometry.width() * float(position.get("x", 0.22))
        )
        y = int(
            screen_geometry.top()
            + screen_geometry.height() * float(position.get("y", 0.18))
        )
        self.setGeometry(x, y, width, max(self.minimumHeight(), height))

    def update_from_session(self, session: Any) -> None:
        if session is None:
            return

        player = getattr(session, "player", None)
        raw_delta = float(getattr(player, "delta_best_s", 0.0) or 0.0) if player else 0.0
        self._target_delta = raw_delta
        self._smooth_delta.set_target(raw_delta)
        self._delta_history.append(raw_delta)

        result = self.session_tracker.update(
            session,
            announce_initial_fastest=bool(
                self.config.get("announce_initial_fastest", False)
            ),
        )

        if result.session_changed:
            self._fastest_fade.reset()
            self._fastest_data = None
            self._delta_history.clear()
            self._smooth_delta.reset(raw_delta)

        always_visible = bool(self.config.get("fastest_lap_always_visible", False))

        if result.new_announcement is not None:
            self._fastest_data = result.new_announcement
            self._fastest_fade.start(
                visible_seconds=float(self.config.get("fastest_lap_show_seconds", 5.0)),
                fade_seconds=float(self.config.get("fastest_lap_fade_seconds", 0.30)),
                always_visible=always_visible,
            )
        elif always_visible and result.current_fastest is not None:
            self._fastest_data = result.current_fastest
            if not self._fastest_fade.active:
                self._fastest_fade.start(
                    visible_seconds=float(self.config.get("fastest_lap_show_seconds", 5.0)),
                    fade_seconds=float(self.config.get("fastest_lap_fade_seconds", 0.30)),
                    always_visible=True,
                )

        self.view_data.session_key = result.session_key
        self.view_data.session_time_text = self._format_duration(
            float(getattr(session, "remaining_time_s", 0.0) or 0.0)
        )
        self.view_data.session_name = self._session_name(
            int(getattr(session, "session", 0) or 0)
        )
        self.view_data.track_state = self._track_state(session)
        self.view_data.penalties = self._player_penalties(session)
        self.view_data.sectors = self._sector_data(player)
        self.update()

    def update_config(self, config: dict[str, Any]) -> None:
        self.config = config
        self.apply_config()

    def set_edit_mode(self, enabled: bool) -> None:
        self.edit_mode = bool(enabled)
        self.setCursor(
            Qt.CursorShape.SizeAllCursor if enabled else Qt.CursorShape.ArrowCursor
        )
        self.update()

    def clear_history(self) -> None:
        self._delta_history.clear()
        self.update()

    def reset_session_state(self) -> None:
        self.session_tracker.reset()
        self._fastest_fade.reset()
        self._fastest_data = None
        self._delta_history.clear()
        self._smooth_delta.reset(0.0)
        self.view_data = DeltaViewData()
        self._fit_content_if_enabled()
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        self.renderer.draw(
            painter,
            QRectF(self.rect()),
            self.view_data,
            list(self._delta_history),
            self.config,
            self.edit_mode,
        )
        if self.edit_mode:
            self._draw_resize_handle(painter)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self.edit_mode or event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return

        self.selected.emit(self.widget_id)
        if self._resize_handle_rect().contains(event.position()):
            self._resizing = True
            self._resize_start_global = event.globalPosition().toPoint()
            self._resize_start_size = self.size()
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        else:
            self._dragging = True
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self.edit_mode:
            event.ignore()
            return

        if self._resizing and self._resize_start_size is not None:
            delta = event.globalPosition().toPoint() - self._resize_start_global
            width = max(self.minimumWidth(), self._resize_start_size.width() + delta.x())

            if bool(self.config.get("auto_fit_content", True)):
                height = self.renderer.preferred_height(
                    width,
                    self.config,
                    self._fastest_is_visible(),
                )
            else:
                height = max(
                    self.minimumHeight(),
                    self._resize_start_size.height() + delta.y(),
                )

            self.resize(width, height)
            event.accept()
            return

        if self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return

        self.setCursor(
            Qt.CursorShape.SizeFDiagCursor
            if self._resize_handle_rect().contains(event.position())
            else Qt.CursorShape.SizeAllCursor
        )

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return

        changed = self._dragging or self._resizing
        self._dragging = False
        self._resizing = False
        self.setCursor(
            Qt.CursorShape.SizeAllCursor
            if self.edit_mode
            else Qt.CursorShape.ArrowCursor
        )

        if changed:
            self._emit_normalized_geometry()
            event.accept()
            return
        event.ignore()

    def _animate(self) -> None:
        now = time.monotonic()
        dt = now - self._last_tick
        self._last_tick = now

        self.view_data.delta_s = self._smooth_delta.step(dt)
        alpha = self._fastest_fade.alpha()

        if alpha <= 0 and not bool(self.config.get("fastest_lap_always_visible", False)):
            self._fastest_data = None

        self.view_data.fastest_lap = self._fastest_data
        self.view_data.fastest_alpha = alpha

        visible = self._fastest_is_visible()
        if visible != self._last_fastest_visible:
            self._last_fastest_visible = visible
            self._fit_content_if_enabled()

        self.update()

    def _fastest_is_visible(self) -> bool:
        return self._fastest_data is not None and self.view_data.fastest_alpha > 0.001

    def _fit_content_if_enabled(self) -> None:
        if self._fitting_content or not bool(self.config.get("auto_fit_content", True)):
            return
        if self.width() <= 0:
            return

        preferred = self.renderer.preferred_height(
            self.width(),
            self.config,
            self._fastest_is_visible(),
        )
        preferred = max(self.minimumHeight(), preferred)

        if abs(self.height() - preferred) <= 2:
            return

        self._fitting_content = True
        self.resize(self.width(), preferred)
        self._fitting_content = False

    def _draw_resize_handle(self, painter: QPainter) -> None:
        rect = self._resize_handle_rect()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(Qt.GlobalColor.white)
        painter.drawRect(rect)

    def _resize_handle_rect(self) -> QRectF:
        size = max(10, int(min(self.width(), self.height()) * 0.045))
        return QRectF(
            self.width() - size - 3,
            self.height() - size - 3,
            size,
            size,
        )

    def _emit_normalized_geometry(self) -> None:
        screen = self.screen()
        if screen is None:
            return

        rect = screen.geometry()
        self.geometry_changed.emit(
            self.widget_id,
            (self.x() - rect.left()) / rect.width(),
            (self.y() - rect.top()) / rect.height(),
            self.width() / rect.width(),
            self.height() / rect.height(),
        )

    @staticmethod
    def _player_penalties(session: Any) -> int:
        for row in getattr(session, "drivers", []) or []:
            if bool(getattr(row, "is_player", False)):
                return int(getattr(row, "penalties", 0) or 0)
        return 0

    @staticmethod
    def _sector_data(player: Any) -> list[DeltaSectorData]:
        result = [
            DeltaSectorData("S1"),
            DeltaSectorData("S2"),
            DeltaSectorData("S3"),
        ]
        if player is None:
            return result

        values = getattr(player, "sector_deltas", None)
        if isinstance(values, (list, tuple)):
            for index in range(min(3, len(values))):
                try:
                    result[index].delta_s = float(values[index])
                except (TypeError, ValueError):
                    pass
            return result

        for index, name in enumerate(
            ["sector1_delta_s", "sector2_delta_s", "sector3_delta_s"]
        ):
            value = getattr(player, name, None)
            if value is not None:
                try:
                    result[index].delta_s = float(value)
                except (TypeError, ValueError):
                    pass
        return result

    @staticmethod
    def _format_duration(seconds: float) -> str:
        if seconds <= 0:
            return "--:--:--"
        total = int(seconds)
        hours, remainder = divmod(total, 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    @staticmethod
    def _session_name(code: int) -> str:
        names = {
            0: "Test Day",
            1: "Practice 1",
            2: "Practice 2",
            3: "Practice 3",
            4: "Practice 4",
            5: "Qualifying 1",
            6: "Qualifying 2",
            7: "Qualifying 3",
            8: "Qualifying 4",
            9: "Warmup",
            10: "Race",
            11: "Race 2",
            12: "Race 3",
            13: "Race 4",
        }
        return names.get(code, f"Session {code}")

    @staticmethod
    def _track_state(session: Any) -> str:
        raining = float(getattr(session, "raining", 0.0) or 0.0)
        grip = int(getattr(session, "track_grip_level", 0) or 0)

        if raining >= 0.50:
            return "Wet"
        if raining > 0.05:
            return "Damp"

        labels = {
            0: "Dry",
            1: "Green",
            2: "Light Rubber",
            3: "Medium Rubber",
            4: "Heavy Rubber",
            5: "Saturated",
        }
        return labels.get(grip, "Dry")
