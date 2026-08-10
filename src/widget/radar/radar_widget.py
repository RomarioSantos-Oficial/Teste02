from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget


class RadarWidget(QWidget):
    """Radar de proximidade. REST do LMU primeiro, Shared Memory como fallback."""

    geometry_changed = Signal(str, float, float, float, float)
    selected = Signal(str)

    def __init__(self, widget_id: str, config: dict[str, Any], parent=None) -> None:
        super().__init__(parent)
        self.widget_id = widget_id
        self.config = config
        self.session: Any = None
        self.targets: list[tuple[Any, float, float, str]] = []
        self.edit_mode = False
        self._dragging = self._resizing = False
        self._drag_offset = QPoint()
        self._resize_start_global = QPoint()
        self._resize_start_size = self.size()
        self.setWindowTitle("Sector Flow Drive - Radar")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setMinimumSize(110, 110)
        self.update_config(config)

    def update_config(self, config: dict[str, Any]) -> None:
        self.config = config
        self.setWindowOpacity(max(.1, min(1.0, float(config.get("opacity", 1.0)))))
        self.update()

    def update_from_session(self, session: Any) -> None:
        self.session = session
        drivers = list(getattr(session, "drivers", []) or [])
        player = next((d for d in drivers if bool(getattr(d, "is_player", False))), None)
        targets: list[tuple[Any, float, float, str]] = []
        if player is not None:
            track_length = float(getattr(session, "track_length_m", 0.0) or 0.0)
            for driver in drivers:
                if driver is player or bool(getattr(driver, "in_garage", False)):
                    continue
                x, y, source = self._relative_position(player, driver, track_length)
                if abs(x) <= self._side_range and -self._ahead_range <= y <= self._behind_range:
                    targets.append((driver, x, y, source))
        self.targets = targets
        if bool(self.config.get("auto_hide_when_clear", True)) and not self.edit_mode:
            self.setVisible(bool(targets))
        elif not self.isVisible():
            self.show()
        self.update()

    def _relative_position(self, player: Any, driver: Any, track_length: float) -> tuple[float, float, str]:
        # A API fornece lapDistance e, em algumas versões, pathLateral. Ela é
        # a fonte principal. O módulo compartilhado só completa quando esses
        # campos não chegaram ou quando o comprimento da pista é inválido.
        if (
            bool(getattr(player, "api_spatial_position", False))
            and bool(getattr(driver, "api_spatial_position", False))
            and track_length > 100.0
        ):
            delta = float(getattr(driver, "lap_distance_m", 0.0)) - float(getattr(player, "lap_distance_m", 0.0))
            delta = (delta + track_length * .5) % track_length - track_length * .5
            x = float(getattr(driver, "path_lateral_m", 0.0)) - float(getattr(player, "path_lateral_m", 0.0))
            return x, -delta, "API"
        return (
            float(getattr(driver, "relative_rotated_x_m", 0.0) or 0.0),
            float(getattr(driver, "relative_rotated_y_m", 0.0) or 0.0),
            "MEM",
        )

    @property
    def _radius_m(self) -> float:
        return max(5.0, float(self.config.get("radar_radius_m", 15.0)))

    @property
    def _side_range(self) -> float:
        return self._radius_m

    @property
    def _ahead_range(self) -> float:
        return self._radius_m * float(self.config.get("ahead_multiplier", 1.5))

    @property
    def _behind_range(self) -> float:
        return self._radius_m * float(self.config.get("behind_multiplier", 1.25))

    def apply_normalized_geometry(self, screen) -> None:
        pos, size = self.config.get("position", {}), self.config.get("size", {})
        w = max(self.minimumWidth(), int(screen.width() * float(size.get("width", .12))))
        h = max(self.minimumHeight(), int(screen.height() * float(size.get("height", .21))))
        self.setGeometry(screen.x()+int(screen.width()*float(pos.get("x", .72))), screen.y()+int(screen.height()*float(pos.get("y", .39))), w, h)

    def set_edit_mode(self, enabled: bool) -> None:
        self.edit_mode = bool(enabled)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, not enabled)
        if enabled:
            self.show()
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        colors = self.config.get("colors", {})
        area = QRectF(2, 2, self.width()-4, self.height()-4)
        if bool(self.config.get("show_background", False)):
            p.setPen(QPen(QColor(colors.get("border", "#344155")), 1))
            p.setBrush(QColor(colors.get("background", "#080D15")))
            p.drawRoundedRect(area, 10, 10)
        cx, cy = area.center().x(), area.center().y()
        scale_x = area.width() * .46 / self._side_range
        scale_y = area.height() * .46 / max(self._ahead_range, self._behind_range)

        if bool(self.config.get("show_marks", True)):
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(colors.get("marks", "#58677A")), 1, Qt.PenStyle.DashLine))
            for ratio in (.33, .66, 1.0):
                p.drawEllipse(QRectF(cx-area.width()*.46*ratio, cy-area.height()*.46*ratio, area.width()*.92*ratio, area.height()*.92*ratio))

        car_w = max(7.0, float(self.config.get("vehicle_width_m", 2.0))*scale_x)
        car_h = max(13.0, float(self.config.get("vehicle_length_m", 5.0))*scale_y)
        p.setPen(QPen(QColor(colors.get("vehicle_outline", "#050505")), max(1.0, min(area.width(), area.height())*.008)))
        p.setBrush(QColor(colors.get("player", "#FFFFFF")))
        p.drawRoundedRect(QRectF(cx-car_w/2, cy-car_h/2, car_w, car_h), 3, 3)

        nearest_left = nearest_right = 999.0
        for driver, x, y, _source in self.targets:
            px, py = cx + x*scale_x, cy + y*scale_y
            if x < 0: nearest_left = min(nearest_left, abs(x))
            else: nearest_right = min(nearest_right, abs(x))
            color = self._target_color(driver, colors)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(px-car_w/2, py-car_h/2, car_w, car_h), 3, 3)

        critical = float(self.config.get("critical_side_distance_m", 2.2))
        nearby = float(self.config.get("nearby_side_distance_m", 4.0))
        self._draw_side_warning(p, area, nearest_left, True, critical, nearby, colors)
        self._draw_side_warning(p, area, nearest_right, False, critical, nearby, colors)

        if self.edit_mode:
            p.setPen(QPen(QColor(colors.get("edit_border", "#8B5CF6")), 2, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush); p.drawRect(self.rect().adjusted(1,1,-2,-2))
            handle = max(10, int(min(self.width(), self.height())*.08))
            p.fillRect(QRectF(self.width()-handle, self.height()-handle, handle, handle), QColor(colors.get("edit_border", "#8B5CF6")))

    def _draw_side_warning(self, p: QPainter, area: QRectF, distance: float, left: bool, critical: float, nearby: float, colors: dict) -> None:
        if distance > nearby:
            return
        color = QColor(colors.get("critical" if distance <= critical else "nearby", "#FF2638" if distance <= critical else "#FFC400"))
        color.setAlpha(205)
        width = area.width()*.24
        grad = QLinearGradient(area.left(), 0, area.left()+width, 0) if left else QLinearGradient(area.right(), 0, area.right()-width, 0)
        grad.setColorAt(0, color); faded = QColor(color); faded.setAlpha(0); grad.setColorAt(1, faded)
        rect = QRectF(area.left(), area.top(), width, area.height()) if left else QRectF(area.right()-width, area.top(), width, area.height())
        p.fillRect(rect, grad)

    @staticmethod
    def _target_color(driver: Any, colors: dict) -> QColor:
        if bool(getattr(driver, "in_pits", False)) or bool(getattr(driver, "pitting", False)):
            key = "in_pit"
        elif bool(getattr(driver, "under_yellow", False)):
            key = "yellow"
        elif int(getattr(driver, "laps_behind_leader", 0) or 0) < 0:
            key = "laps_ahead"
        elif int(getattr(driver, "laps_behind_leader", 0) or 0) > 0:
            key = "laps_behind"
        else:
            key = "same_lap"
        return QColor(colors.get(key, "#23A8FF"))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.edit_mode and event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self.widget_id)
            handle = max(12, int(min(self.width(), self.height())*.12))
            if event.position().x() >= self.width()-handle and event.position().y() >= self.height()-handle:
                self._resizing = True; self._resize_start_global = event.globalPosition().toPoint(); self._resize_start_size = self.size()
            else:
                self._dragging = True; self._drag_offset = event.globalPosition().toPoint()-self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._resizing:
            delta = event.globalPosition().toPoint()-self._resize_start_global
            self.resize(max(self.minimumWidth(), self._resize_start_size.width()+delta.x()), max(self.minimumHeight(), self._resize_start_size.height()+delta.y())); self.update()
        elif self._dragging:
            self.move(event.globalPosition().toPoint()-self._drag_offset)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if (self._dragging or self._resizing) and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = self._resizing = False
            screen = self.screen().geometry()
            self.geometry_changed.emit(self.widget_id, (self.x()-screen.x())/screen.width(), (self.y()-screen.y())/screen.height(), self.width()/screen.width(), self.height()/screen.height())
