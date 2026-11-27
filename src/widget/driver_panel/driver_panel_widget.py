from __future__ import annotations

from collections import deque
from bisect import bisect_right
from statistics import median
import time
from typing import Any

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPaintEvent, QPainter, QResizeEvent
from PySide6.QtWidgets import QWidget
from src.laps.archive import LapArchiveStore, local_owner_key

from .driver_panel_renderer import DriverPanelRenderer, DriverPanelViewData


class DriverPanelWidget(QWidget):
    MINIMUM_WIDTH = 180
    MINIMUM_HEIGHT = 70

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
        self.lap_archive: LapArchiveStore | None = None
        self._personal_best_key: tuple[str, ...] | None = None
        self._personal_best_trace: list[dict[str, float]] = []
        self._next_personal_best_check = 0.0
        self._current_lap_marker: int | None = None
        self._current_lap_samples: list[tuple[float, float, float]] = []
        self._current_lap_graph: list[tuple[float, float, float]] = []
        self._current_lap_capture_started = False

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
        self._graph_throttle_samples: deque[float] = deque(maxlen=5)
        self._graph_brake_samples: deque[float] = deque(maxlen=5)
        self._graph_clutch_samples: deque[float] = deque(maxlen=5)
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

        # O desenho interno é responsivo; este limite mantém o puxador e os
        # principais dados utilizáveis sem obrigar o painel a 360 x 130 px.
        self.setMinimumSize(self.MINIMUM_WIDTH, self.MINIMUM_HEIGHT)

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

        interval = "Volta" if bool(self.config.get("compare_personal_best", False)) else str(self.config.get("graph_interval", "10 s"))
        seconds = {"5 s": 5, "10 s": 10, "15 s": 15, "20 s": 20, "30 s": 30, "45 s": 45, "60 s": 60, "90 s": 90, "120 s": 120, "180 s": 180, "300 s": 300, "600 s": 600, "Volta": 180, "Sessão": 3600}.get(interval, 10)
        history_rate = min(
            120,
            max(1, int(self.config.get("sample_rate_hz", 60))),
        )
        self._history_interval_s = 1.0 / history_rate
        history_size = max(30, min(432000, history_rate * seconds))

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
        self._graph_throttle_samples.append(throttle)
        self._graph_brake_samples.append(brake)
        self._graph_clutch_samples.append(clutch)
        steering = max(-1.0, min(1.0, float(getattr(player_data, "steering", 0.0))))
        smoothing = max(0.0, min(0.95, float(self.config.get("steering_smoothing", 0.32))))
        self._smoothed_steering += (steering - self._smoothed_steering) * (1.0 - smoothing)
        rpm = max(0.0, float(getattr(player_data, "rpm", 0.0)))
        max_rpm = max(1.0, float(getattr(player_data, "max_rpm", 9000.0) or 9000.0))
        speed_kmh = max(0.0, float(getattr(player_data, "speed_kmh", 0.0)))
        gear = int(getattr(player_data, "gear", 0))
        now = time.monotonic()
        rpm_flash_phase = self.view_data.rpm_flash_phase
        if gear != self._previous_gear:
            self._gear_flash_until = now + 0.22
            self._previous_gear = gear
        self._max_rpm_seen = max(self._max_rpm_seen, rpm)
        self._max_throttle_seen = max(self._max_throttle_seen, throttle)
        self._max_brake_seen = max(self._max_brake_seen, brake)
        self._max_clutch_seen = max(self._max_clutch_seen, clutch)

        if now >= self._next_history_sample_at:
            if self._next_history_sample_at == 0.0:
                self._next_history_sample_at = now
            self._next_history_sample_at += self._history_interval_s
            while self._next_history_sample_at <= now:
                self._next_history_sample_at += self._history_interval_s
            self.throttle_history.append(median(self._graph_throttle_samples))
            self.brake_history.append(median(self._graph_brake_samples))
            self.clutch_history.append(median(self._graph_clutch_samples))
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
            rpm_flash_phase=rpm_flash_phase,
        )
        self._previous_throttle = throttle
        self._previous_brake = brake
        self._update_personal_best_trace(player_data, throttle, brake, now)

        self.update()

    @staticmethod
    def _rpm_flash_phase_at(now: float, frequency_hz: float) -> bool:
        """Alterna a cor na frequência pedida; não cria timers adicionais."""
        frequency = max(10.0, min(100.0, float(frequency_hz)))
        return (int(max(0.0, now) * frequency) % 2) == 0

    def update_rpm_flash(self, now: float | None = None) -> None:
        """Atualiza apenas a fase visual enquanto o motor está no limitador."""
        current_time = time.monotonic() if now is None else float(now)
        layout = self.config.get("layout", {})
        light_3_at = max(0.0, min(1.1, float(layout.get("shift_light_3", 0.96))))
        flash_at = max(light_3_at, min(1.2, float(layout.get("rpm_flash_start", 0.99))))
        ratio = self.view_data.rpm / max(1.0, self.view_data.max_rpm)
        active = ratio >= flash_at
        phase = (
            self._rpm_flash_phase_at(
                current_time,
                float(self.config.get("rpm_flash_frequency_hz", 20.0)),
            )
            if active else False
        )
        if phase != self.view_data.rpm_flash_phase:
            self.view_data.rpm_flash_phase = phase
            self.update()

    def _update_personal_best_trace(
        self,
        frame: Any,
        throttle: float,
        brake: float,
        now: float,
    ) -> None:
        if (
            not bool(self.config.get("compare_personal_best", False))
        ):
            return
        track = str(getattr(frame, "track_name", "") or "")
        category = str(getattr(frame, "vehicle_class", "") or "")
        model = str(getattr(frame, "vehicle_model", "") or "")
        filename = str(getattr(frame, "vehicle_filename", "") or "")
        owner = local_owner_key()
        scope = str(self.config.get("personal_best_scope", "category") or "category")
        context_key = (owner, track.casefold(), category.casefold(), model.casefold(), filename.casefold(), scope)
        if context_key != self._personal_best_key or now >= self._next_personal_best_check:
            if self.lap_archive is None:
                self.lap_archive = LapArchiveStore()
            record = self.lap_archive.best(track, category, model, filename, scope, owner)
            self._personal_best_trace = record.trace if record is not None else []
            self._personal_best_key = context_key
            self._next_personal_best_check = now + 2.0

        length = float(getattr(frame, "track_length_m", 0.0) or 0.0)
        distance = float(getattr(frame, "lap_distance_m", 0.0) or 0.0)
        marker = int(getattr(frame, "lap_number", 0) or 0)
        fraction = distance / length if length > 0.0 else -1.0
        if marker != self._current_lap_marker:
            self._current_lap_samples.clear()
            self._current_lap_marker = marker
            self._current_lap_capture_started = 0.0 <= fraction <= 0.035
        if bool(getattr(frame, "current_lap_invalidated", False)):
            self._current_lap_samples.clear()
            self._current_lap_capture_started = False
            return
        if not self._current_lap_capture_started or not 0.0 <= fraction <= 1.02:
            return
        ratio = max(0.0, min(1.0, fraction))
        if self._current_lap_samples and ratio + 0.025 < self._current_lap_samples[-1][0]:
            self._current_lap_samples.clear()
            self._current_lap_capture_started = False
            return
        self._current_lap_samples.append((ratio, throttle, brake))

    def _comparison_graph(self) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
        if len(self._current_lap_samples) > 600:
            count = len(self._current_lap_samples)
            indexes = [round(index * (count - 1) / 599) for index in range(600)]
            self._current_lap_graph = [self._current_lap_samples[index] for index in indexes]
        else:
            self._current_lap_graph = self._current_lap_samples
        if not self._personal_best_trace:
            return [], []
        best_throttle = [
            (float(sample.get("distance", 0.0)), float(sample.get("throttle", 0.0)))
            for sample in self._personal_best_trace
        ]
        best_brake = [
            (float(sample.get("distance", 0.0)), float(sample.get("brake", 0.0)))
            for sample in self._personal_best_trace
        ]
        return best_throttle, best_brake

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
        self._graph_throttle_samples.clear()
        self._graph_brake_samples.clear()
        self._graph_clutch_samples.clear()
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
        reference_throttle: list[tuple[float, float]] = []
        reference_brake: list[tuple[float, float]] = []
        compare_best = bool(self.config.get("compare_personal_best", False))
        if compare_best:
            reference_throttle, reference_brake = self._comparison_graph()
            if self._current_lap_capture_started:
                current = getattr(self, "_current_lap_graph", self._current_lap_samples)
                throttle = [(sample[0], sample[1]) for sample in current]
                brake = [(sample[0], sample[2]) for sample in current]
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
            reference_throttle,
            reference_brake,
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

        interval = "Volta" if bool(self.config.get("compare_personal_best", False)) else str(self.config.get("graph_interval", "10 s"))
        seconds = {"5 s": 5.0, "10 s": 10.0, "15 s": 15.0, "20 s": 20.0, "30 s": 30.0, "45 s": 45.0, "60 s": 60.0, "90 s": 90.0, "120 s": 120.0, "180 s": 180.0, "300 s": 300.0, "600 s": 600.0}.get(interval)
        points = max(2, min(6000, int(self.config.get("graph_history_points", 240))))
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
