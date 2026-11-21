from __future__ import annotations
from decimal import Decimal, ROUND_CEILING
from typing import Any
from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget
from .fuel_time_tracker import FuelTimeData, FuelTimeTracker

class FuelTimeWidget(QWidget):
    geometry_changed=Signal(str,float,float,float,float); selected=Signal(str)
    def __init__(self, widget_id:str, config:dict[str,Any], parent=None)->None:
        super().__init__(parent); self.widget_id=widget_id; self.config=config; self.tracker=FuelTimeTracker(config); self.data=FuelTimeData(); self.edit_mode=False
        self._dragging=self._resizing=False; self._drag_offset=QPoint(); self._start_global=QPoint(); self._start_size=self.size()
        self.setWindowTitle("Sector Flow Drive - Fuel Time"); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground,True); self.setMouseTracking(True); self.setMinimumSize(300,145); self.update_config(config)
    def update_from_session(self,session:Any)->None: self.data=self.tracker.update(session); self.update()
    def update_config(self,config:dict[str,Any])->None: self.config=config; self.tracker.update_config(config); self.setWindowOpacity(max(.1,min(1.0,float(config.get("opacity",1.0))))); self.update()
    def apply_normalized_geometry(self,screen)->None:
        pos,size=self.config.get("position",{}),self.config.get("size",{})
        self.setGeometry(screen.x()+int(screen.width()*float(pos.get("x",.35))),screen.y()+int(screen.height()*float(pos.get("y",.72))),max(self.minimumWidth(),int(screen.width()*float(size.get("width",.30)))),max(self.minimumHeight(),int(screen.height()*float(size.get("height",.16)))))
    def set_edit_mode(self,enabled:bool)->None: self.edit_mode=enabled; self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,not enabled); self.update()
    @staticmethod
    def _v(value:float|None,suffix:str="",decimals:int=1)->str: return "--" if value is None else f"{value:.{decimals}f}{suffix}"
    @staticmethod
    def _fuel_ratio(value:float|None)->str:
        if value is None: return "--"
        rounded=Decimal(str(value)).quantize(Decimal("0.01"),rounding=ROUND_CEILING)
        return f"{rounded:.2f}"
    def paintEvent(self,_event)->None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        colors = self.config.get("colors", {})
        background = QColor(colors.get("background", "#090D12"))
        border = QColor(colors.get("border", "#35404A"))
        accent = QColor(colors.get("accent", "#43BDCA"))
        panel = QColor(colors.get("panel", "#151C24"))
        panel_border = QColor(colors.get("panel_border", "#26303A"))
        text = QColor(colors.get("text", "#F4F6F8"))
        muted = QColor(colors.get("muted", "#A7B0BA"))

        painter.setPen(QPen(border, 1.2))
        painter.setBrush(background)
        painter.drawRoundedRect(QRectF(1, 1, self.width() - 2, self.height() - 2), 10, 10)

        margin = max(6, int(min(self.width(), self.height()) * 0.045))
        area = self.rect().adjusted(margin, margin, -margin, -margin)
        title_height = max(22, int(area.height() * 0.16))
        font = painter.font()
        font.setFamily(str(self.config.get("font_name", "Bahnschrift Condensed")))
        font.setBold(True)
        font.setPixelSize(max(11, int(title_height * 0.52)))
        painter.setFont(font)
        painter.setPen(QColor(colors.get("title", "#F4F6F8")))
        painter.drawText(
            QRectF(area.left() + 4, area.top(), area.width() * 0.55, title_height),
            Qt.AlignmentFlag.AlignVCenter,
            "FUEL TIME",
        )

        status = f"{self.data.sample_count}/{int(self.config.get('average_laps', 5))} VOLTAS"
        font.setPixelSize(max(8, int(title_height * 0.38)))
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(muted)
        painter.drawText(
            QRectF(area.left() + area.width() * 0.55, area.top(), area.width() * 0.45 - 4, title_height),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
            status,
        )

        painter.setPen(QPen(accent, max(1.0, title_height * 0.07)))
        painter.drawLine(area.left(), area.top() + title_height, area.right(), area.top() + title_height)

        data = self.data
        rows = [
            ("COMBUSTIVEL", self._v(data.fuel_l, " L"), "MEDIA/VOLTA", self._v(data.fuel_per_lap_l, " L")),
            ("VOLTAS REST.", self._v(data.laps_remaining), "AUTONOMIA", self._v(data.fuel_laps, " v")),
            ("NECESSARIO", self._v(data.fuel_needed_l, " L"), "ADICIONAR", self._v(data.fuel_to_add_l, " L")),
            ("ALVO/VOLTA", self._v(data.target_fuel_per_lap_l, " L"), "FINAL", self._v(data.finish_fuel_l, " L")),
        ]
        if bool(self.config.get("show_energy", True)):
            rows.append(
                (
                    "ENERGIA/VOLTA",
                    self._v(data.energy_per_lap_pct, "%"),
                    "FUEL RATIO",
                    self._fuel_ratio(data.fuel_ratio),
                )
            )

        gap = max(3.0, area.width() * 0.008)
        y = area.top() + title_height + gap
        row_height = max(18, (area.bottom() - y - gap * (len(rows) - 1)) / max(1, len(rows)))
        half_width = (area.width() - gap) / 2

        for left_label, left_value, right_label, right_value in rows:
            for x, label, value in (
                (area.left(), left_label, left_value),
                (area.left() + half_width + gap, right_label, right_value),
            ):
                box = QRectF(x, y, half_width, row_height)
                painter.setPen(QPen(panel_border, 1))
                painter.setBrush(panel)
                painter.drawRoundedRect(box, 5, 5)

                marker = QRectF(box.left() + 1, box.top() + 4, 2, max(1, box.height() - 8))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(accent)
                painter.drawRoundedRect(marker, 1, 1)

                font.setPixelSize(max(7, int(row_height * 0.28)))
                font.setBold(False)
                painter.setFont(font)
                painter.setPen(muted)
                painter.drawText(
                    box.adjusted(max(7, row_height * 0.18), 0, -box.width() * 0.46, 0),
                    Qt.AlignmentFlag.AlignVCenter,
                    label,
                )

                font.setPixelSize(max(9, int(row_height * 0.43)))
                font.setBold(True)
                painter.setFont(font)
                value_color = text
                if label in {"ADICIONAR", "FINAL"} and value != "--":
                    numeric = data.fuel_to_add_l if label == "ADICIONAR" else data.finish_fuel_l
                    if numeric is not None and numeric < 0.05:
                        value_color = QColor(colors.get("good", "#55D98A"))
                    if numeric is not None and numeric < 0:
                        value_color = QColor(colors.get("warning", "#FF5E6B"))
                painter.setPen(value_color)
                painter.drawText(
                    box.adjusted(box.width() * 0.50, 0, -max(5, row_height * 0.18), 0),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                    value,
                )
            y += row_height + gap

        if self.edit_mode:
            edit_border = QColor(colors.get("edit_border", "#8B4DFF"))
            painter.setPen(QPen(edit_border, 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.rect().adjusted(1, 1, -2, -2))
            painter.fillRect(self.width() - 14, self.height() - 14, 14, 14, edit_border)
    def mousePressEvent(self,e:QMouseEvent)->None:
        if self.edit_mode and e.button()==Qt.MouseButton.LeftButton:
            self.selected.emit(self.widget_id); self._resizing=e.position().x()>=self.width()-18 and e.position().y()>=self.height()-18; self._dragging=not self._resizing; self._start_global=e.globalPosition().toPoint(); self._start_size=self.size(); self._drag_offset=e.globalPosition().toPoint()-self.frameGeometry().topLeft()
    def mouseMoveEvent(self,e:QMouseEvent)->None:
        if self._resizing:
            d=e.globalPosition().toPoint()-self._start_global; self.resize(max(self.minimumWidth(),self._start_size.width()+d.x()),max(self.minimumHeight(),self._start_size.height()+d.y())); self.update()
        elif self._dragging: self.move(e.globalPosition().toPoint()-self._drag_offset)
    def mouseReleaseEvent(self,e:QMouseEvent)->None:
        if (self._dragging or self._resizing) and e.button()==Qt.MouseButton.LeftButton:
            self._dragging=self._resizing=False; s=self.screen().geometry(); self.geometry_changed.emit(self.widget_id,(self.x()-s.x())/s.width(),(self.y()-s.y())/s.height(),self.width()/s.width(),self.height()/s.height())
