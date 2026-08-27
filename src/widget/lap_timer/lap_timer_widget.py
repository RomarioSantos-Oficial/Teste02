from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .lap_timer_tracker import LapTimerData, LapTimerTracker


def format_lap(seconds: float, decimals: int = 3) -> str:
    if seconds <= 0.0:
        return "--:--.---" if decimals == 3 else "--:--.--"
    minutes = int(seconds // 60.0)
    rest = seconds - minutes * 60.0
    width = 3 + decimals
    return f"{minutes}:{rest:0{width}.{decimals}f}"


class LapTimerWidget(QWidget):
    geometry_changed = Signal(str, float, float, float, float)
    selected = Signal(str)

    def __init__(self, widget_id: str, config: dict[str, Any], parent=None) -> None:
        super().__init__(parent)
        self.widget_id = widget_id
        self.config = config
        self.tracker = LapTimerTracker()
        self.data = LapTimerData()
        self.edit_mode = False
        self._dragging = self._resizing = False
        self._drag_offset = QPoint()
        self._start_global = QPoint()
        self._start_size = self.size()
        self.setWindowTitle("Sector Flow Overlay - Lap Timer")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setMinimumSize(245, 150)
        # Timer exclusivamente visual. Dados e estimativas continuam no loop
        # central; aqui apenas interpolamos os milissegundos do cronometro.
        self._paint_timer = QTimer(self)
        self._paint_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._paint_timer.setInterval(16)
        self._paint_timer.timeout.connect(self._smooth_repaint)
        self._paint_timer.start()
        self.update_config(config)

    def _smooth_repaint(self) -> None:
        if self.isVisible() and self.tracker._running:
            self.update()

    def update_from_session(self, session: Any) -> None:
        self.data = self.tracker.update(session)
        self.update()

    def update_config(self, config: dict[str, Any]) -> None:
        self.config = config
        # A configuracao inicial usava #RRGGBBAA, mas QColor interpreta oito
        # digitos como #AARRGGBB. Isso fazia E8 virar azul e 0A/15 virarem um
        # alfa quase invisivel. Migra somente os dois valores antigos exatos.
        colors = self.config.setdefault("colors", {})
        if str(colors.get("background", "")).upper() == "#0A0F17E8":
            colors["background"] = "#080C12"
        if str(colors.get("panel", "")).upper() == "#151B26E8":
            colors["panel"] = "#10151D"
        if float(self.config.get("opacity", 0.98)) == 0.98:
            self.config["opacity"] = 1.0
        self.setWindowOpacity(max(0.10, min(1.0, float(config.get("opacity", 0.98)))))
        self.update()

    def apply_normalized_geometry(self, screen) -> None:
        pos, size = self.config.get("position", {}), self.config.get("size", {})
        self.setGeometry(
            screen.x() + int(screen.width() * float(pos.get("x", 0.70))),
            screen.y() + int(screen.height() * float(pos.get("y", 0.48))),
            max(self.minimumWidth(), int(screen.width() * float(size.get("width", 0.18)))),
            max(self.minimumHeight(), int(screen.height() * float(size.get("height", 0.27)))),
        )

    def set_edit_mode(self, enabled: bool) -> None:
        self.edit_mode = enabled
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, not enabled)
        self.update()

    def closeEvent(self, event) -> None:
        self._paint_timer.stop()
        event.accept()

    def _rows(self) -> list[tuple[str, str, str]]:
        c = self.config
        d = self.data
        decimals = int(c.get("decimals", 3))
        rows: list[tuple[str, str, str]] = []
        current = self.tracker.current_lap_time()
        if c.get("show_current", True):
            rows.append(("VOLTA ATUAL", format_lap(current, decimals), "invalid" if d.current_invalid else "current"))
        if c.get("show_last", True):
            label = "ULTIMA  INV" if d.last_invalid and d.last_lap_s > 0 else "ULTIMA"
            rows.append((label, format_lap(d.last_lap_s, decimals), "invalid" if d.last_invalid else "text"))
        if c.get("show_best", True):
            rows.append(("MELHOR", format_lap(d.best_lap_s, decimals), "best"))
        if c.get("show_predicted", True):
            rows.append(("PREVISTA", format_lap(d.predicted_lap_s, decimals), "predicted"))
        if c.get("show_theoretical", False):
            rows.append(("TEORICA", format_lap(d.theoretical_lap_s, decimals), "theoretical"))
        if c.get("show_laps", True):
            total = "--" if d.estimated_total_laps is None else f"~{int(math.ceil(d.estimated_total_laps))}"
            if d.estimated_total_laps is not None and abs(d.estimated_total_laps - round(d.estimated_total_laps)) < 0.001:
                total = str(int(round(d.estimated_total_laps)))
            rows.append(("VOLTAS", f"{d.completed_laps} / {total}", "text"))
        if c.get("show_remaining", False):
            value = "--" if d.remaining_laps is None else f"~{d.remaining_laps:.1f}"
            rows.append(("RESTANTES", value, "text"))
        return rows

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        colors = self.config.get("colors", {})
        outer = QRectF(1, 1, self.width() - 2, self.height() - 2)
        if self.config.get("background_enabled", True):
            p.setPen(QPen(QColor(colors.get("border", "#344155")), 1.2))
            p.setBrush(QColor(colors.get("background", "#080C12")))
            p.drawRoundedRect(outer, float(self.config.get("border_radius", 10)), float(self.config.get("border_radius", 10)))

        margin = max(7, int(min(self.width(), self.height()) * 0.05))
        area = self.rect().adjusted(margin, margin, -margin, -margin)
        font = p.font()
        font.setFamily(str(self.config.get("font_name", "Arial")))
        title_h = max(20, int(area.height() * 0.13))
        font.setPixelSize(max(10, int(title_h * float(self.config.get("title_font_scale", 0.52)))))
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor(colors.get("title", "#67E8F9")))
        p.drawText(QRectF(area.left(), area.top(), area.width() * 0.58, title_h), Qt.AlignmentFlag.AlignVCenter, "LAP TIMER")

        position_parts = []
        d = self.data
        if self.config.get("show_position", True) and d.position:
            position_parts.append(f"P {d.position}/{d.field_count}")
        if self.config.get("show_class_position", True) and d.class_position:
            position_parts.append(f"C {d.class_position}/{d.class_count}")
        font.setPixelSize(max(8, int(title_h * 0.40)))
        p.setFont(font)
        p.setPen(QColor(colors.get("muted", "#9BA8BA")))
        p.drawText(QRectF(area.left() + area.width() * 0.42, area.top(), area.width() * 0.58, title_h), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, "   ".join(position_parts))
        p.setPen(QPen(QColor(colors.get("accent", "#2563EB")), max(1.0, title_h * 0.07)))
        p.drawLine(area.left(), area.top() + title_h, area.right(), area.top() + title_h)

        rows = self._rows()
        gap = max(2.0, area.height() * 0.009)
        y = area.top() + title_h + gap
        row_h = max(16.0, (area.bottom() - y - gap * max(0, len(rows) - 1)) / max(1, len(rows)))
        color_map = {
            "text": colors.get("text", "#F4F7FB"), "current": colors.get("current", "#FFFFFF"),
            "best": colors.get("best", "#C084FC"), "predicted": colors.get("predicted", "#67E8F9"),
            "theoretical": colors.get("theoretical", "#FACC15"), "invalid": colors.get("invalid", "#EF4444"),
        }
        for label, value, role in rows:
            box = QRectF(area.left(), y, area.width(), row_h)
            if self.config.get("row_backgrounds", True):
                p.setPen(QPen(QColor(colors.get("panel_border", "#27313E")), 1))
                p.setBrush(QColor(colors.get("panel", "#10151D")))
                p.drawRoundedRect(box, 4, 4)
            font.setBold(False)
            font.setPixelSize(max(7, int(row_h * float(self.config.get("label_font_scale", 0.28)))))
            p.setFont(font)
            p.setPen(QColor(colors.get("muted", "#9BA8BA")))
            p.drawText(box.adjusted(max(6, row_h * .18), 0, -box.width() * .52, 0), Qt.AlignmentFlag.AlignVCenter, label)
            font.setBold(True)
            font.setPixelSize(max(10, int(row_h * float(self.config.get("value_font_scale", 0.46)))))
            p.setFont(font)
            p.setPen(QColor(color_map.get(role, color_map["text"])))
            p.drawText(box.adjusted(box.width() * .43, 0, -max(6, row_h * .18), 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, value)
            y += row_h + gap

        if self.edit_mode:
            p.setPen(QPen(QColor(colors.get("edit_border", "#8B5CF6")), 2, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(self.rect().adjusted(1, 1, -2, -2))
            p.fillRect(self.width() - 14, self.height() - 14, 14, 14, QColor(colors.get("edit_border", "#8B5CF6")))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.edit_mode and event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self.widget_id)
            self._resizing = event.position().x() >= self.width() - 18 and event.position().y() >= self.height() - 18
            self._dragging = not self._resizing
            self._start_global = event.globalPosition().toPoint()
            self._start_size = self.size()
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._resizing:
            delta = event.globalPosition().toPoint() - self._start_global
            self.resize(max(self.minimumWidth(), self._start_size.width() + delta.x()), max(self.minimumHeight(), self._start_size.height() + delta.y()))
            self.update()
        elif self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if (self._dragging or self._resizing) and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = self._resizing = False
            screen = self.screen().geometry()
            self.geometry_changed.emit(self.widget_id, (self.x() - screen.x()) / screen.width(), (self.y() - screen.y()) / screen.height(), self.width() / screen.width(), self.height() / screen.height())


import math
