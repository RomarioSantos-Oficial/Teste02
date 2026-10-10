from __future__ import annotations

import math
from typing import Any

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget


class DamageWidget(QWidget):
    geometry_changed = Signal(str, float, float, float, float)
    selected = Signal(str)

    # Ordem visual usada pelo TinyPedal: FL, FC, FR, CL, CR, RL, RC, RR.
    LMU_TO_VISUAL = (1, 0, 7, 2, 6, 3, 4, 5)

    def __init__(self, widget_id: str, config: dict[str, Any], parent=None) -> None:
        super().__init__(parent)
        self.widget_id = widget_id
        self.config = config
        self.player: Any = None
        self.edit_mode = False
        self._dragging = False
        self._resizing = False
        self._drag_offset = QPoint()
        self._resize_start_global = QPoint()
        self._resize_start_size = self.size()
        self.setWindowTitle("Sector Flow Drive - Damage")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setMinimumSize(80, 110)
        self.update_config(config)

    def update_telemetry(self, player: Any) -> None:
        self.player = player
        self.update()

    def update_config(self, config: dict[str, Any]) -> None:
        self.config = config
        self.setWindowOpacity(max(0.1, min(1.0, float(config.get("opacity", 1.0)))))
        self.update()

    def apply_normalized_geometry(self, screen) -> None:
        pos, size = self.config.get("position", {}), self.config.get("size", {})
        w = max(self.minimumWidth(), int(screen.width() * float(size.get("width", .07))))
        h = max(self.minimumHeight(), int(screen.height() * float(size.get("height", .18))))
        self.setGeometry(
            screen.x() + int(screen.width() * float(pos.get("x", .88))),
            screen.y() + int(screen.height() * float(pos.get("y", .58))), w, h,
        )

    def set_edit_mode(self, enabled: bool) -> None:
        self.edit_mode = enabled
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, not enabled)
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        c = self.config.get("colors", {})
        p.setPen(QPen(QColor(c.get("border", "#384553")), 1.2))
        p.setBrush(QColor(c.get("background", "#0B1018")))
        p.drawRect(QRectF(1, 1, self.width()-2, self.height()-2))

        margin = max(6.0, min(self.width(), self.height()) * .07)
        area = QRectF(margin, margin, self.width()-2*margin, self.height()-2*margin)
        # O TinyPedal mostra o carro como uma grade 3x3: frente e traseira
        # completas, laterais no meio e o centro vazado. Reserva-se o rodapé
        # para a leitura de integridade.
        body_w = area.width() * .88
        body_h = area.height() * .78
        body = QRectF(area.center().x()-body_w/2, area.top(), body_w, body_h)

        raw = list(getattr(self.player, "body_damage", []) or [])
        visual = [raw[i] if i < len(raw) else 0 for i in self.LMU_TO_VISUAL]
        if bool(getattr(self.player, "body_detached", False)):
            visual[6] = 3
        gap = max(1.0, min(body.width(), body.height()) * .025)
        row_h = (body.height()-2*gap)/3
        side_w = (body.width()-2*gap)*.28
        center_w = body.width()-2*side_w-2*gap
        parts = (
            QRectF(body.left(), body.top(), side_w, row_h),
            QRectF(body.left()+side_w+gap, body.top(), center_w, row_h),
            QRectF(body.right()-side_w, body.top(), side_w, row_h),
            QRectF(body.left(), body.top()+row_h+gap, side_w, row_h),
            QRectF(body.right()-side_w, body.top()+row_h+gap, side_w, row_h),
            QRectF(body.left(), body.bottom()-row_h, side_w, row_h),
            QRectF(body.left()+side_w+gap, body.bottom()-row_h, center_w, row_h),
            QRectF(body.right()-side_w, body.bottom()-row_h, side_w, row_h),
        )
        for rect, severity in zip(parts, visual):
            p.fillRect(rect.adjusted(1, 1, -1, -1), self._damage_color(severity))

        wheels = list(getattr(self.player, "wheels", []) or [])
        susp = list(getattr(self.player, "suspension_damage", []) or [])
        wheel_w, wheel_h = side_w*.48, row_h*.68
        # Rodas nos quatro cantos internos, como no TinyPedal; os elos de
        # suspensão terminam junto ao centro das laterais, sem cruzar o carro.
        x_left = body.left()+side_w-wheel_w*.35
        x_right = body.right()-side_w-wheel_w*.65
        y_front = body.top()+row_h-wheel_h*.45
        y_rear = body.bottom()-row_h-wheel_h*.55
        for i, (x, y) in enumerate(((x_left,y_front),(x_right,y_front),(x_left,y_rear),(x_right,y_rear))):
            detached = i < len(wheels) and bool(getattr(wheels[i], "detached", False))
            damage = float(susp[i]) if i < len(susp) else 0.0
            color = self._suspension_color(damage, detached)
            wheel_center = QRectF(x,y,wheel_w,wheel_h).center()
            # Quatro pontos separados no chassi impedem que os braços
            # esquerda/direita pareçam apenas duas linhas contínuas.
            is_left = i % 2 == 0
            is_front = i < 2
            chassis_x = body.left()+side_w+gap*.5 if is_left else body.right()-side_w-gap*.5
            chassis_y = body.top()+row_h+gap*.5 if is_front else body.bottom()-row_h-gap*.5
            if bool(self.config.get("show_suspension_links", True)):
                p.setPen(QPen(color.lighter(135), max(1.0, area.width()*.012)))
                p.drawLine(wheel_center, QPointF(chassis_x, chassis_y))
            p.fillRect(QRectF(x, y, wheel_w, wheel_h), color)

        impact = tuple(getattr(self.player, "last_impact_position", (0.0, 0.0)) or (0.0,0.0))
        impact_age = (
            float(getattr(self.player, "vehicle_elapsed_time_s", 0.0) or 0.0)
            - float(getattr(self.player, "last_impact_time_s", 0.0) or 0.0)
        )
        if (
            bool(self.config.get("show_last_impact", True))
            and 0.0 <= impact_age <= float(self.config.get("impact_duration_s", 5.0))
            and any(abs(float(v)) > .001 for v in impact)
        ):
            angle = math.atan2(float(impact[1]), float(impact[0]))
            radius = min(area.width(), area.height())*.43
            center = area.center()
            point = center + QPoint(int(math.cos(angle)*radius), int(-math.sin(angle)*radius))
            p.setPen(QPen(QColor(c.get("impact", "#FF8A00")), 3))
            p.drawLine(center, point)

        if bool(self.config.get("show_integrity", True)):
            damage = float(getattr(self.player, "vehicle_damage", 0.0) or 0.0)
            damage = damage * 100.0 if damage <= 1.0 else damage
            if damage <= 0 and raw:
                damage = sum(max(0,min(2,int(v))) for v in raw[:8]) / 16 * 100
            p.setPen(QColor(c.get("text", "#FFFFFF")))
            font = p.font(); font.setBold(True); font.setPixelSize(max(9, int(area.height()*.09))); p.setFont(font)
            p.drawText(QRectF(area.left(), area.bottom()-area.height()*.1, area.width(), area.height()*.1), Qt.AlignmentFlag.AlignCenter, f"{max(0,100-damage):.0f}%")

        if self.edit_mode:
            p.setPen(QPen(QColor(c.get("edit_border", "#8B5CF6")), 2, Qt.PenStyle.DashLine))
            p.drawRect(self.rect().adjusted(1,1,-2,-2))
            handle = max(10, int(min(self.width(), self.height())*.09))
            p.fillRect(QRectF(self.width()-handle, self.height()-handle, handle, handle), QColor(c.get("edit_border", "#8B5CF6")))

    def _damage_color(self, severity: int) -> QColor:
        c = self.config.get("colors", {})
        return QColor(c.get(("body_ok","body_light","body_heavy","detached")[max(0,min(3,int(severity)))], "#38D996"))

    def _suspension_color(self, damage: float, detached: bool) -> QColor:
        c = self.config.get("colors", {})
        if detached: return QColor(c.get("detached", "#000000"))
        if damage >= float(self.config.get("susp_totaled_threshold", .8)):
            return QColor(c.get("susp_totaled", "#0000FF"))
        if damage >= float(self.config.get("susp_heavy_threshold", .4)):
            return QColor(c.get("susp_heavy", "#FF00FF"))
        if damage >= .15:
            return QColor(c.get("susp_medium", "#FF6600"))
        if damage >= float(self.config.get("susp_light_threshold", .005)):
            return QColor(c.get("susp_light", "#FFFF00"))
        return QColor(c.get("susp_ok", "#44CC00"))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.edit_mode and event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self.widget_id)
            handle = max(12, int(min(self.width(), self.height())*.12))
            if event.position().x() >= self.width()-handle and event.position().y() >= self.height()-handle:
                self._resizing = True
                self._resize_start_global = event.globalPosition().toPoint()
                self._resize_start_size = self.size()
            else:
                self._dragging = True
                self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._resizing:
            delta = event.globalPosition().toPoint() - self._resize_start_global
            self.resize(max(self.minimumWidth(), self._resize_start_size.width()+delta.x()), max(self.minimumHeight(), self._resize_start_size.height()+delta.y()))
            self.update()
        elif self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        elif self.edit_mode:
            handle = max(12, int(min(self.width(), self.height())*.12))
            over_handle = event.position().x() >= self.width()-handle and event.position().y() >= self.height()-handle
            self.setCursor(Qt.CursorShape.SizeFDiagCursor if over_handle else Qt.CursorShape.SizeAllCursor)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if (self._dragging or self._resizing) and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False; self._resizing = False
            self.unsetCursor()
            screen = self.screen().geometry()
            self.geometry_changed.emit(self.widget_id, (self.x()-screen.x())/screen.width(), (self.y()-screen.y())/screen.height(), self.width()/screen.width(), self.height()/screen.height())
