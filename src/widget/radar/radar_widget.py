from __future__ import annotations

import math
from typing import Any

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QMouseEvent, QPainter, QPainterPath, QPen, QPolygonF
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
        self._radar_samples: dict[int, tuple[float, float, float]] = {}
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
                reference_time = float(getattr(player, "radar_elapsed_time_s", 0.0) or 0.0)
                x, y, source = self._relative_position(player, driver, track_length, reference_time)
                if source == "INVALID":
                    continue
                if abs(x) <= self._side_range and -self._ahead_range <= y <= self._behind_range:
                    targets.append((driver, x, y, source))
        self.targets = targets
        if bool(self.config.get("auto_hide_when_clear", True)) and not self.edit_mode:
            self.setVisible(bool(targets))
        elif not self.isVisible():
            self.show()
        self.update()

    def _relative_position(
        self, player: Any, driver: Any, track_length: float, reference_time: float = 0.0
    ) -> tuple[float, float, str]:
        if (
            bool(getattr(player, "radar_position_valid", False))
            and bool(getattr(driver, "radar_position_valid", False))
        ):
            player_x = float(getattr(player, "radar_longitudinal_m", 0.0) or 0.0)
            player_y = float(getattr(player, "radar_lateral_m", 0.0) or 0.0)
            other_x, other_y = self._interpolated_radar_position(driver, reference_time)
            delta_x, delta_y = other_x-player_x, other_y-player_y
            yaw = float(getattr(player, "radar_orientation_yaw_rad", 0.0) or 0.0) - math.pi
            cos_yaw, sin_yaw = math.cos(yaw), math.sin(yaw)
            rotated_x = cos_yaw*delta_x - sin_yaw*delta_y
            rotated_y = cos_yaw*delta_y + sin_yaw*delta_x
            return rotated_x, rotated_y, "MEM"
        # O radar precisa da posição relativa no referencial do jogador, como
        # no TinyPedal. A projeção lapDistance/pathLateral é fallback pois
        # achata a pista e não acompanha a geometria das curvas.
        if (
            bool(getattr(player, "api_spatial_position", False))
            and bool(getattr(driver, "api_spatial_position", False))
            and bool(getattr(player, "api_lateral_position", False))
            and bool(getattr(driver, "api_lateral_position", False))
            and track_length > 100.0
        ):
            delta = float(getattr(driver, "lap_distance_m", 0.0)) - float(getattr(player, "lap_distance_m", 0.0))
            delta = (delta + track_length * .5) % track_length - track_length * .5
            x = float(getattr(driver, "path_lateral_m", 0.0)) - float(getattr(player, "path_lateral_m", 0.0))
            return x, -delta, "API"
        return 0.0, 0.0, "INVALID"

    def _interpolated_radar_position(self, driver: Any, reference_time: float) -> tuple[float, float]:
        """Interpola o último ponto dos carros como o módulo do TinyPedal."""
        x = float(getattr(driver, "radar_longitudinal_m", 0.0) or 0.0)
        y = float(getattr(driver, "radar_lateral_m", 0.0) or 0.0)
        sample_time = float(getattr(driver, "radar_elapsed_time_s", 0.0) or 0.0)
        slot_value = getattr(driver, "slot_id", None)
        slot_id = int(slot_value) if slot_value is not None else id(driver)
        previous = self._radar_samples.get(slot_id)
        if previous is not None:
            previous_time, previous_x, previous_y = previous
            sample_delta = sample_time-previous_time
            reference_delta = reference_time-sample_time
            if sample_delta > 0 and reference_delta > 0:
                factor = reference_delta/sample_delta
                x += (x-previous_x)*factor
                y += (y-previous_y)*factor
        self._radar_samples[slot_id] = (
            sample_time,
            float(getattr(driver, "radar_longitudinal_m", 0.0) or 0.0),
            float(getattr(driver, "radar_lateral_m", 0.0) or 0.0),
        )
        return x, y

    @property
    def _radius_m(self) -> float:
        return max(5.0, float(self.config.get("radar_radius_m", 15.0)))

    @property
    def _side_range(self) -> float:
        return self._radius_m

    @property
    def _ahead_range(self) -> float:
        return self._radius_m

    @property
    def _behind_range(self) -> float:
        return self._radius_m

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
        meters = max(self._side_range, self._ahead_range, self._behind_range)
        scale = min(area.width(), area.height()) * .46 / meters

        if bool(self.config.get("show_marks", True)):
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(colors.get("marks", "#58677A")), 1, Qt.PenStyle.DashLine))
            for ratio in (.33, .66, 1.0):
                radius = min(area.width(), area.height()) * .46 * ratio
                p.drawEllipse(QRectF(cx-radius, cy-radius, radius*2, radius*2))

        # O TinyPedal limita o radar à área circular; evita carros surgindo
        # nos cantos do widget fora do alcance visual.
        clip_radius = min(area.width(), area.height()) * .46
        clip = QPainterPath()
        clip.addEllipse(QRectF(cx-clip_radius, cy-clip_radius, clip_radius*2, clip_radius*2))
        p.setClipPath(clip)

        car_w = max(7.0, float(self.config.get("vehicle_width_m", 2.0))*scale)
        car_h = max(13.0, float(self.config.get("vehicle_length_m", 5.0))*scale)
        p.setPen(QPen(QColor(colors.get("vehicle_outline", "#050505")), max(1.0, min(area.width(), area.height())*.008)))
        p.setBrush(QColor(colors.get("player", "#FFFFFF")))
        p.drawRoundedRect(QRectF(cx-car_w/2, cy-car_h/2, car_w, car_h), 3, 3)

        vehicle_width = float(self.config.get("vehicle_width_m", 2.0))
        vehicle_length = float(self.config.get("vehicle_length_m", 5.0))
        overlap_min_x = vehicle_width * .9
        overlap_max_x = vehicle_width * (float(self.config.get("overlap_nearby_range_multiplier", 5.0)) + .9)
        overlap_critical_x = vehicle_width * (float(self.config.get("overlap_critical_range_multiplier", 1.0)) + .9)
        nearest_left, nearest_right = -overlap_max_x, overlap_max_x
        for driver, x, y, _source in self.targets:
            px, py = cx + x*scale, cy + y*scale
            if abs(y) < vehicle_length * 1.2 and abs(x) < overlap_max_x:
                if -overlap_min_x > x > nearest_left:
                    nearest_left = x
                if overlap_min_x < x < nearest_right:
                    nearest_right = x
            color = self._target_color(driver, colors)
            p.setBrush(color)
            p.save()
            p.translate(px, py)
            p.rotate(-float(getattr(driver, "relative_orientation_rad", 0.0) or 0.0) * 180.0 / math.pi)
            p.drawRoundedRect(QRectF(-car_w/2, -car_h/2, car_w, car_h), 3, 3)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 230))
            p.drawPolygon(QPolygonF((
                QPointF(-car_w*.28, -car_h*.22),
                QPointF(0, -car_h*.48),
                QPointF(car_w*.28, -car_h*.22),
            )))
            p.restore()

        self._draw_overlap_indicator(
            p, area, nearest_left, nearest_right, overlap_min_x,
            overlap_max_x, overlap_critical_x, scale, vehicle_width, colors,
        )

        if self.edit_mode:
            p.setClipping(False)
            p.setPen(QPen(QColor(colors.get("edit_border", "#8B5CF6")), 2, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush); p.drawRect(self.rect().adjusted(1,1,-2,-2))
            handle = max(10, int(min(self.width(), self.height())*.08))
            p.fillRect(QRectF(self.width()-handle, self.height()-handle, handle, handle), QColor(colors.get("edit_border", "#8B5CF6")))

    def _draw_overlap_indicator(
        self, p: QPainter, area: QRectF, nearest_left: float, nearest_right: float,
        min_range_x: float, max_range_x: float, critical_range_x: float,
        scale: float, vehicle_width: float, colors: dict,
    ) -> None:
        """Indicador de sobreposição alinhado à posição do carro, como no TinyPedal."""
        width = max(1.0, vehicle_width * float(self.config.get("indicator_size_multiplier", 8.0)) * scale)
        edge = max((width-3.0)/width, .001)
        offset = vehicle_width * scale * .5
        center_x = area.center().x()
        for x, left in ((nearest_left, True), (nearest_right, False)):
            distance = abs(x)
            if distance >= max_range_x or distance <= min_range_x:
                continue
            intensity = max(0.0, min(1.0, 1.0-(distance-min_range_x)/(max_range_x-min_range_x)))
            critical = distance <= critical_range_x
            color = QColor(colors.get("critical" if critical else "nearby", "#FF2638" if critical else "#FFC400"))
            color.setAlphaF(color.alphaF()*intensity)
            gradient = QLinearGradient(0, 0, width, 0)
            if left:
                gradient.setColorAt(0.0, QColor(0, 0, 0, 0))
                gradient.setColorAt(edge, color)
                gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
                x_pos = center_x + x*scale - width + offset
            else:
                gradient.setColorAt(0.0, QColor(0, 0, 0, 0))
                gradient.setColorAt(1.0-edge, color)
                gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
                x_pos = center_x + x*scale - offset
            p.fillRect(QRectF(x_pos, area.top(), width, area.height()), gradient)

    @staticmethod
    def _target_color(driver: Any, colors: dict) -> QColor:
        if int(getattr(driver, "position", 0) or 0) == 1:
            key = "leader"
        elif bool(getattr(driver, "in_pits", False)) or bool(getattr(driver, "pitting", False)):
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
