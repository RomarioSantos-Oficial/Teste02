from __future__ import annotations

from collections import deque
from bisect import bisect_right
import time
from typing import Any

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPaintEvent, QPainter, QResizeEvent
from PySide6.QtWidgets import QWidget

from .driver_panel_renderer import DriverPanelRenderer, DriverPanelViewData


class DriverPanelWidget(QWidget):
    geometry_changed = Signal(str, float, float, float, float)
    selected = Signal(str)

    def __init__(
        self,
        widget_id: str,
        config: dict[str, Any],
        parent=None,
    ) -> None:
        super().__init__(parent)

        self.widget_id = widget_id
        self.config = config
        self.renderer = DriverPanelRenderer()
        self.view_data = DriverPanelViewData()

        history_size = max(
            30,
            int(config.get("graph_history_points", 240)),
        )
        self.throttle_history: deque[float] = deque(maxlen=history_size)
        self.brake_history: deque[float] = deque(maxlen=history_size)
        self.clutch_history: deque[float] = deque(maxlen=history_size)
        self.rpm_history: deque[float] = deque(maxlen=history_size)
        self.steering_history: deque[float] = deque(maxlen=history_size)
        self.speed_history: deque[float] = deque(maxlen=history_size)
        self.history_times: deque[float] = deque(maxlen=history_size)
        self._history_interval_s = 1.0 / 30.0
        self._next_history_sample_at = 0.0
        self._visible_history_cache: tuple[list[float], ...] = (
            [], [], [], [], [], []
        )
        self._active_graph_interval = str(
            config.get("graph_interval", "10 s")
        )
        self._smoothed_steering = 0.0
        self._max_rpm_seen = 0.0
        self._max_throttle_seen = 0.0
        self._max_brake_seen = 0.0
        self._max_clutch_seen = 0.0
        self._previous_throttle = 0.0
        self._previous_brake = 0.0
        self._previous_gear = 0
        self._gear_flash_until = 0.0

        self.edit_mode = False
        self._dragging = False
        self._resizing = False
        self._drag_offset = QPoint()
        self._resize_start_global = QPoint()
        self._resize_start_size = None

        # Permite painel realmente pequeno.
        self.setMinimumSize(360, 130)

        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
            True,
        )
        self.setWindowTitle("Sector Flow Drive - Telemetry")

        self.apply_config()

    def apply_config(self) -> None:
        self.setWindowOpacity(
            float(self.config.get("opacity", 0.96))
        )

        interval = str(self.config.get("graph_interval", "10 s"))
        seconds = {"5 s": 5, "10 s": 10, "30 s": 30, "Volta": 180, "Sessão": 3600}.get(interval, 10)
        history_rate = min(
            30,
            max(1, int(self.config.get("sample_rate_hz", 60))),
        )
        history_size = max(30, min(108000, history_rate * seconds))

        if self.throttle_history.maxlen != history_size:
            self.throttle_history = deque(
                self.throttle_history,
                maxlen=history_size,
            )
            self.brake_history = deque(
                self.brake_history,
                maxlen=history_size,
            )
            self.clutch_history = deque(self.clutch_history, maxlen=history_size)
            self.rpm_history = deque(self.rpm_history, maxlen=history_size)
            self.steering_history = deque(self.steering_history, maxlen=history_size)
            self.speed_history = deque(self.speed_history, maxlen=history_size)
            self.history_times = deque(self.history_times, maxlen=history_size)

        if interval != self._active_graph_interval:
            self.clear_graph()
            self._active_graph_interval = interval

        self.update()

    def apply_normalized_geometry(self, screen_geometry) -> None:
        position = self.config.get("position", {})
        size = self.config.get("size", {})
        scale = float(self.config.get("scale", 1.0))

        width_ratio = float(size.get("width", 0.72)) * scale
        height_ratio = float(size.get("height", 0.30)) * scale

        x = int(
            screen_geometry.left()
            + screen_geometry.width()
            * float(position.get("x", 0.14))
        )
        y = int(
            screen_geometry.top()
            + screen_geometry.height()
            * float(position.get("y", 0.66))
        )
        width = max(
            self.minimumWidth(),
            int(screen_geometry.width() * width_ratio),
        )
        height = max(
            self.minimumHeight(),
            int(screen_geometry.height() * height_ratio),
        )

        self.setGeometry(x, y, width, height)

    def update_telemetry(self, player_data: Any) -> None:
        if player_data is None:
            return

        throttle = max(
            0.0,
            min(
                1.0,
                float(getattr(player_data, "throttle", 0.0)),
            ),
        )
        brake = max(
            0.0,
            min(
                1.0,
                float(getattr(player_data, "brake", 0.0)),
            ),
        )
        clutch = max(0.0, min(1.0, float(getattr(player_data, "clutch", 0.0))))
        steering = max(-1.0, min(1.0, float(getattr(player_data, "steering", 0.0))))
        smoothing = max(0.0, min(0.95, float(self.config.get("steering_smoothing", 0.32))))
        self._smoothed_steering += (steering - self._smoothed_steering) * (1.0 - smoothing)
        rpm = max(0.0, float(getattr(player_data, "rpm", 0.0)))
        max_rpm = max(1.0, float(getattr(player_data, "max_rpm", 9000.0) or 9000.0))
        speed_kmh = max(0.0, float(getattr(player_data, "speed_kmh", 0.0)))
        gear = int(getattr(player_data, "gear", 0))
        now = time.monotonic()
        if gear != self._previous_gear:
            self._gear_flash_until = now + 0.22
            self._previous_gear = gear
        self._max_rpm_seen = max(self._max_rpm_seen, rpm)
        self._max_throttle_seen = max(self._max_throttle_seen, throttle)
        self._max_brake_seen = max(self._max_brake_seen, brake)
        self._max_clutch_seen = max(self._max_clutch_seen, clutch)

        if now >= self._next_history_sample_at:
            self._next_history_sample_at = now + self._history_interval_s
            self.throttle_history.append(throttle)
            self.brake_history.append(brake)
            self.clutch_history.append(clutch)
            self.rpm_history.append(min(1.0, rpm / max_rpm))
            self.steering_history.append((self._smoothed_steering + 1.0) * 0.5)
            self.speed_history.append(min(1.0, speed_kmh / 350.0))
            self.history_times.append(now)
            self._visible_history_cache = self._visible_history(now)

        self.view_data = DriverPanelViewData(
            speed_kmh=speed_kmh,
            rpm=rpm,
            max_rpm=max_rpm,
            gear=gear,
            throttle=throttle,
            brake=brake,
            clutch=clutch,
            steering=self._smoothed_steering,
            max_rpm_seen=self._max_rpm_seen,
            max_throttle_seen=self._max_throttle_seen,
            max_brake_seen=self._max_brake_seen,
            max_clutch_seen=self._max_clutch_seen,
            throttle_abrupt=throttle - self._previous_throttle > 0.20,
            brake_abrupt=brake - self._previous_brake > 0.20,
            gear_flash=now < self._gear_flash_until,
        )
        self._previous_throttle = throttle
        self._previous_brake = brake

        self.update()

    def clear_graph(self) -> None:
        self.throttle_history.clear()
        self.brake_history.clear()
        self.clutch_history.clear()
        self.rpm_history.clear()
        self.steering_history.clear()
        self.speed_history.clear()
        self.history_times.clear()
        self._max_rpm_seen = 0.0
        self._max_throttle_seen = 0.0
        self._max_brake_seen = 0.0
        self._max_clutch_seen = 0.0
        self._next_history_sample_at = 0.0
        self._visible_history_cache = ([], [], [], [], [], [])
        self.update()

    def set_edit_mode(self, enabled: bool) -> None:
        self.edit_mode = enabled
        self.setCursor(
            Qt.CursorShape.SizeAllCursor
            if enabled
            else Qt.CursorShape.ArrowCursor
        )
        self.update()

    def update_config(self, new_config: dict[str, Any]) -> None:
        self.config = new_config
        self.apply_config()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event

        painter = QPainter(self)
        throttle, brake, clutch, rpm, steering, speed = self._visible_history_cache
        self.renderer.draw(
            painter,
            QRectF(self.rect()),
            self.view_data,
            throttle,
            brake,
            clutch,
            rpm,
            steering,
            speed,
            self.config,
            self.edit_mode,
        )

        if self.edit_mode:
            self._draw_resize_handle(painter)

    def _visible_history(
        self, now: float | None = None
    ) -> tuple[list[float], ...]:
        """Mantém a curva original e posiciona cada amostra pelo tempo real."""
        times = list(self.history_times)
        # Apenas os três pedais são desenhados no gráfico. RPM, direção e
        # velocidade atuais já chegam pelo view_data.
        series = [
            list(self.throttle_history),
            list(self.brake_history),
            list(self.clutch_history),
        ]
        if not times:
            return tuple(series + [[], [], []])

        interval = str(self.config.get("graph_interval", "10 s"))
        seconds = {"5 s": 5.0, "10 s": 10.0, "30 s": 30.0}.get(interval)
        points = max(2, int(self.config.get("graph_history_points", 240)))
        if seconds is not None:
            checked_at = time.monotonic() if now is None else float(now)
            cutoff = checked_at - seconds
            # Inclui uma amostra anterior ao corte para a linha entrar pela
            # borda esquerda sem mudar seu formato.
            start = max(0, bisect_right(times, cutoff) - 1)
            indexes = list(range(start, len(times)))
            if len(indexes) > points:
                indexes = [
                    indexes[round(index * (len(indexes) - 1) / (points - 1))]
                    for index in range(points)
                ]
            timed: list[list[tuple[float, float]]] = []
            for values in series:
                timed.append([
                    ((times[index] - cutoff) / seconds, values[index])
                    for index in indexes
                ])
            return tuple(timed + [[], [], []])

        # Volta/sessão não possuem duração fixa antecipadamente; nesses modos
        # apenas reduzimos a resolução sem alterar a ordem das amostras.
        length = len(series[0])
        if length > points:
            indexes = [
                round(index * (length - 1) / (points - 1))
                for index in range(points)
            ]
            series = [[values[index] for index in indexes] for values in series]
        return tuple(series + [[], [], []])

    def _draw_resize_handle(self, painter: QPainter) -> None:
        size = max(10, int(min(self.width(), self.height()) * 0.055))

        handle = QRectF(
            self.width() - size - 3,
            self.height() - size - 3,
            size,
            size,
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(Qt.GlobalColor.white)
        painter.drawRect(handle)

    def _resize_handle_rect(self) -> QRectF:
        size = max(
            10,
            int(min(self.width(), self.height()) * 0.055),
        )

        return QRectF(
            self.width() - size - 3,
            self.height() - size - 3,
            size,
            size,
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if (
            not self.edit_mode
            or event.button() != Qt.MouseButton.LeftButton
        ):
            event.ignore()
            return

        self.selected.emit(self.widget_id)

        if self._resize_handle_rect().contains(
            event.position()
        ):
            self._resizing = True
            self._resize_start_global = (
                event.globalPosition().toPoint()
            )
            self._resize_start_size = self.size()
            self.setCursor(
                Qt.CursorShape.SizeFDiagCursor
            )
        else:
            self._dragging = True
            self._drag_offset = (
                event.globalPosition().toPoint()
                - self.frameGeometry().topLeft()
            )
            self.setCursor(
                Qt.CursorShape.ClosedHandCursor
            )

        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self.edit_mode:
            event.ignore()
            return

        if self._resizing and self._resize_start_size:
            delta = (
                event.globalPosition().toPoint()
                - self._resize_start_global
            )

            width = max(
                self.minimumWidth(),
                self._resize_start_size.width() + delta.x(),
            )
            height = max(
                self.minimumHeight(),
                self._resize_start_size.height() + delta.y(),
            )

            self.resize(width, height)
            event.accept()
            return

        if self._dragging:
            self.move(
                event.globalPosition().toPoint()
                - self._drag_offset
            )
            event.accept()
            return

        if self._resize_handle_rect().contains(
            event.position()
        ):
            self.setCursor(
                Qt.CursorShape.SizeFDiagCursor
            )
        else:
            self.setCursor(
                Qt.CursorShape.SizeAllCursor
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

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.update()

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
