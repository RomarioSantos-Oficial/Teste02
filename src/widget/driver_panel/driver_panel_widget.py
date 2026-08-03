from __future__ import annotations

from collections import deque
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

        history_size = max(
            30,
            int(self.config.get("graph_history_points", 240)),
        )

        if self.throttle_history.maxlen != history_size:
            self.throttle_history = deque(
                self.throttle_history,
                maxlen=history_size,
            )
            self.brake_history = deque(
                self.brake_history,
                maxlen=history_size,
            )

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

        self.throttle_history.append(throttle)
        self.brake_history.append(brake)

        self.view_data = DriverPanelViewData(
            speed_kmh=float(
                getattr(player_data, "speed_kmh", 0.0)
            ),
            rpm=float(getattr(player_data, "rpm", 0.0)),
            max_rpm=float(
                getattr(player_data, "max_rpm", 9000.0)
                or 9000.0
            ),
            gear=int(getattr(player_data, "gear", 0)),
            throttle=throttle,
            brake=brake,
            steering=float(
                getattr(player_data, "steering", 0.0)
            ),
        )

        self.update()

    def clear_graph(self) -> None:
        self.throttle_history.clear()
        self.brake_history.clear()
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
        self.renderer.draw(
            painter,
            QRectF(self.rect()),
            self.view_data,
            list(self.throttle_history),
            list(self.brake_history),
            self.config,
            self.edit_mode,
        )

        if self.edit_mode:
            self._draw_resize_handle(painter)

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
