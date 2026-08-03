# SectorFlow is an open-source overlay application for racing simulation.
# Copyright (C) 2022-2026 SectorFlow developers
# Based on the user-provided Standings Hybrid reference.
#
# This file is part of SectorFlow.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.


from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QLineF, QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPaintEvent, QPainter, QPen, QResizeEvent
from PySide6.QtWidgets import QSizePolicy, QWidget

from .standings_assets import BrandLogoStore, badge_color, badge_text, brand_short, flag_emoji
from .standings_logic import StandingsLogic
from .standings_models import CategoryBlock, DriverMetadata, StandingRow, StandingsView
from .standings_online import LocalStandingsEnrichment

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class StandingsWidget(QWidget):
    geometry_changed = Signal(str, float, float, float, float)
    selected = Signal(str)
    DESIGN_WIDTH = 1500.0
    DESIGN_HEIGHT = 820.0

    BASE_COLUMNS = (
        ("position", 46.0),
        ("change", 60.0),
        ("flag", 50.0),
        ("badge", 60.0),
        ("driver", 360.0),
        ("brand", 72.0),
        ("number", 58.0),
        ("laps", 70.0),
        ("best", 140.0),
        ("last", 140.0),
        ("gap", 100.0),
        ("penalty", 76.0),
        ("tyre", 76.0),
        ("energy", 105.0),
        ("damage", 80.0),
    )

    def __init__(self, widget_id: str, config: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.widget_id = widget_id
        self.config = config
        self.logic = StandingsLogic(config)
        self.enrichment = LocalStandingsEnrichment(PROJECT_ROOT, config)
        self.logos = BrandLogoStore(PROJECT_ROOT, config)
        self.view = StandingsView()
        self.session: Any | None = None
        self.edit_mode = False
        self.preview_mode = False
        self._last_build = 0.0
        self._scale = 1.0
        self._dragging = False
        self._resizing = False
        self._drag_offset = QPoint()
        self._resize_origin = QPoint()
        self._resize_width = 0
        self._resize_height = 0
        self._fitting_height = False

        self.setWindowTitle("Sector Flow Drive - Standings")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # O limite antigo de 800x280 impedia o redimensionamento pelo puxador.
        # A altura agora acompanha automaticamente o conteudo desenhado.
        self.setMinimumSize(420, 60)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(120)
        self.apply_config()

    def apply_config(self) -> None:
        self.logic.update_config(self.config)
        self.enrichment.update_config(self.config)
        self.logos.update_config(self.config)
        self.setWindowOpacity(max(0.10, min(1.0, float(self.config.get("opacity", 0.98)))))
        self._update_scale()
        self._rebuild(force=True)

    def update_config(self, config: dict[str, Any]) -> None:
        self.config = config
        self.apply_config()

    def apply_normalized_geometry(self, screen_geometry) -> None:
        position = self.config.get("position", {})
        size = self.config.get("size", {})
        external_scale = max(0.35, float(self.config.get("scale", 1.0)))
        width = max(self.minimumWidth(), int(screen_geometry.width() * float(size.get("width", 0.74)) * external_scale))
        height = max(self.minimumHeight(), int(screen_geometry.height() * float(size.get("height", 0.72)) * external_scale))
        x = int(screen_geometry.left() + screen_geometry.width() * float(position.get("x", 0.01)))
        y = int(screen_geometry.top() + screen_geometry.height() * float(position.get("y", 0.02)))
        self.resize(width, height)
        self.move(x, y)
        self._update_scale()

    def update_from_session(self, session: Any) -> None:
        self.preview_mode = False
        self.session = session
        self.enrichment.use_live_mode()
        self._rebuild()

    def set_preview_data(self, session: Any, metadata: list[DriverMetadata]) -> None:
        self.preview_mode = True
        self.session = session
        self.enrichment.set_test_metadata(metadata)
        self._rebuild(force=True)

    def set_edit_mode(self, enabled: bool) -> None:
        self.edit_mode = bool(enabled)
        self.setCursor(Qt.CursorShape.SizeAllCursor if self.edit_mode else Qt.CursorShape.ArrowCursor)
        self.show()
        self.update()

    def reset_session_state(self) -> None:
        self.session = None
        self.logic.reset()
        self.view = StandingsView()
        self.update()

    def closeEvent(self, event) -> None:
        self.timer.stop()
        self.enrichment.stop()
        event.accept()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_scale()
        self._fit_height_to_content()
        self.update()

    def _tick(self) -> None:
        self._rebuild()

    def _rebuild(self, force: bool = False) -> None:
        now = time.monotonic()
        interval = max(0.05, float(self.config.get("render_interval_seconds", 0.20)))
        if not force and now - self._last_build < interval:
            return
        self._last_build = now
        drivers = list(getattr(self.session, "drivers", []) or [])
        driver_names = [
            str(getattr(driver, "driver_name", "") or "")
            for driver in drivers
        ]
        vehicle_names = [
            str(getattr(driver, "vehicle_name", "") or "")
            for driver in drivers
        ]
        metadata, source, _ = self.enrichment.snapshot(driver_names)
        self.view = self.logic.build(
            self.session,
            metadata,
            source,
            self.enrichment.vehicle_catalog(vehicle_names),
        )
        self._update_scale()
        self._fit_height_to_content()
        self.update()

    def _update_scale(self) -> None:
        internal = max(0.40, float(self.config.get("internal_scale", 1.0)))
        minimum = max(0.20, float(self.config.get("responsive_min_scale", 0.22)))
        maximum = max(minimum, float(self.config.get("responsive_max_scale", 2.25)))
        width_scale = self.width() / self.DESIGN_WIDTH
        responsive = width_scale * internal
        self._scale = max(minimum, min(maximum, responsive))

    def _desired_content_height(self) -> int:
        margin = max(
            2.0,
            float(self.config.get("panel_margin", 8.0)) * self._scale,
        )
        height = 2.0 * margin + 2.0
        if self._header_items():
            height += max(
                18.0,
                float(self.config.get("global_header_height", 58.0))
                * self._scale,
            )
            height += max(2.0, 4.0 * self._scale)
        if not self.view.categories:
            return max(self.minimumHeight(), round(max(100.0, height)))
        if bool(self.config.get("show_column_legend", False)):
            height += max(12.0, 30.0 * self._scale)
        category_height = max(
            14.0,
            float(self.config.get("category_header_height", 50.0))
            * self._scale,
        )
        row_height = max(
            14.0,
            float(self.config.get("row_height", 54.0)) * self._scale,
        )
        for category in self.view.categories:
            height += category_height + len(category.rows) * row_height
            height += max(2.0, 7.0 * self._scale)
        return max(self.minimumHeight(), round(height))

    def _fit_height_to_content(self) -> None:
        if self._fitting_height or not bool(
            self.config.get("auto_fit_height", True)
        ):
            return
        desired = self._desired_content_height()
        if abs(self.height() - desired) <= 1:
            return
        self._fitting_height = True
        try:
            self.resize(self.width(), desired)
        finally:
            self._fitting_height = False

    def _header_items(self) -> list[tuple[str, float, str]]:
        if not bool(self.config.get("show_global_header", True)):
            return []
        definitions = (
            ("show_header_session_type", self.view.session_type, 0.085, ""),
            ("show_header_session_time", self.view.session_time, 0.155, "⏱"),
            ("show_header_server_time", self.view.server_time, 0.155, "◷"),
            ("show_header_local_time", self.view.local_time, 0.145, "▣"),
            ("show_header_grip", self.view.grip_text, 0.145, "♨"),
            ("show_header_track_limits", self.view.track_limits_text, 0.20, "⚠"),
            ("show_header_source", self.view.source_text, 0.115, ""),
        )
        return [
            (str(text), fraction, icon)
            for key, text, fraction, icon in definitions
            if bool(self.config.get(key, True))
        ]

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        colors = self.config.get("colors", {})
        outer = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colors.get("background", "#030711")))
        painter.drawRect(outer)
        margin = max(2.0, float(self.config.get("panel_margin", 8.0)) * self._scale)
        content = outer.adjusted(margin, margin, -margin, -margin)
        y = content.top()
        if self._header_items():
            header_height = max(18.0, float(self.config.get("global_header_height", 58.0)) * self._scale)
            self._draw_global_header(painter, QRectF(content.left(), y, content.width(), header_height))
            y += header_height + max(2.0, 4.0 * self._scale)
        used = self._draw_categories(painter, QRectF(content.left(), y, content.width(), content.bottom() - y))
        if used <= 0 and not self.view.connected:
            painter.setFont(self._font(0.95, True))
            painter.setPen(QColor(colors.get("muted", "#A7AFBA")))
            painter.drawText(
                QRectF(content.left(), y, content.width(), content.bottom() - y),
                Qt.AlignmentFlag.AlignCenter,
                "AGUARDANDO O LMU\nSTANDINGS SEM SIMHUB",
            )
        if self.edit_mode:
            painter.setPen(QPen(QColor(colors.get("edit_border", "#9B5CFF")), max(1.0, 2.0 * self._scale), Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(outer)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#FFFFFF"))
            painter.drawRect(self._resize_handle_rect())

    def _draw_global_header(self, painter: QPainter, rect: QRectF) -> None:
        colors = self.config.get("colors", {})
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colors.get("header_background", "#000000")))
        painter.drawRect(rect)
        items = self._header_items()
        total_fraction = sum(fraction for _, fraction, _ in items) or 1.0
        x = rect.left()
        for index, (text, fraction, icon) in enumerate(items):
            width = rect.width() * fraction / total_fraction
            if index == len(items) - 1:
                width = rect.right() - x
            cell = QRectF(x, rect.top(), width, rect.height())
            x += width
            if index > 0:
                painter.setPen(QPen(QColor(colors.get("header_separator", "#1E2633")), max(1.0, self._scale)))
                painter.drawLine(cell.topLeft(), cell.bottomLeft())
            painter.setFont(self._font(0.88 if index == 0 else 0.75, True))
            painter.setPen(QColor(colors.get("text", "#FFFFFF")))
            label = f"{icon}  {text}".strip()
            painter.drawText(cell.adjusted(8 * self._scale, 0, -5 * self._scale, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
        painter.setPen(QPen(QColor(colors.get("header_line", "#175C9C")), max(1.0, 2.0 * self._scale)))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())

    def _draw_categories(self, painter: QPainter, rect: QRectF) -> float:
        y = rect.top()
        row_height = max(14.0, float(self.config.get("row_height", 54.0)) * self._scale)
        category_height = max(14.0, float(self.config.get("category_header_height", 50.0)) * self._scale)
        legend_height = max(12.0, 30.0 * self._scale)
        for category_index, category in enumerate(self.view.categories):
            if y + category_height > rect.bottom():
                break
            self._draw_category_header(painter, QRectF(rect.left(), y, rect.width(), category_height), category)
            y += category_height
            if bool(self.config.get("show_column_legend", False)) and category_index == 0:
                if y + legend_height > rect.bottom():
                    break
                self._draw_legend(painter, QRectF(rect.left(), y, rect.width(), legend_height))
                y += legend_height
            for row in category.rows:
                if y + row_height > rect.bottom():
                    self._draw_clipped_notice(painter, QRectF(rect.left(), max(rect.top(), rect.bottom() - row_height), rect.width(), row_height))
                    return y - rect.top()
                self._draw_row(painter, QRectF(rect.left(), y, rect.width(), row_height), row, category)
                y += row_height
            y += max(2.0, 7.0 * self._scale)
        return y - rect.top()

    def _draw_category_header(self, painter: QPainter, rect: QRectF, category: CategoryBlock) -> None:
        color = QColor(category.color)
        gap = max(3.0, 6.0 * self._scale)
        class_width = min(rect.width() * 0.20, 190.0 * self._scale)
        count_width = min(rect.width() * 0.18, 180.0 * self._scale)
        lap_width = min(rect.width() * 0.20, 190.0 * self._scale)
        x = rect.left()
        boxes = [
            (
                QRectF(x, rect.top(), class_width, rect.height() - 3 * self._scale),
                category.class_name,
            )
        ]
        x += class_width + gap
        if category.show_count:
            boxes.append(
                (
                    QRectF(x, rect.top(), count_width, rect.height() - 3 * self._scale),
                    f"🏎  {category.started}/{category.total}",
                )
            )
            x += count_width + gap
        boxes.append(
            (
                QRectF(x, rect.top(), lap_width, rect.height() - 3 * self._scale),
                f"🏁  {category.current_lap}/{category.total_laps_text}",
            )
        )
        painter.setFont(self._font(0.78, True))
        for box, text in boxes:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRect(box)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(box.adjusted(8 * self._scale, 0, -8 * self._scale, 0), Qt.AlignmentFlag.AlignCenter, text)
        painter.setPen(QPen(color, max(1.0, 3.0 * self._scale)))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())

    def _draw_legend(self, painter: QPainter, rect: QRectF) -> None:
        colors = self.config.get("colors", {})
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colors.get("legend_background", "#11151D")))
        painter.drawRect(rect)
        labels = {
            "position": "P", "change": "+/-", "flag": "PAÍS", "badge": "BADGE",
            "driver": "PILOTO", "brand": "MAR", "number": "#", "laps": "VLT",
            "best": "BEST", "last": "LAST", "gap": "GAP", "penalty": "PEN",
            "tyre": "TYR",
            "energy": "BAT", "damage": "DMG",
        }
        for key, cell in self._column_rects(rect):
            painter.setFont(self._font(0.48, True))
            painter.setPen(QColor(colors.get("muted", "#A7AFBA")))
            painter.drawText(cell, Qt.AlignmentFlag.AlignCenter, labels.get(key, key.upper()))

    def _draw_row(self, painter: QPainter, rect: QRectF, row: StandingRow, category: CategoryBlock) -> None:
        colors = self.config.get("colors", {})
        background = QColor(colors.get("row_background", "#030711"))
        if row.is_player:
            background = QColor(colors.get("player_background", "#111B2B"))
        elif row.in_pits or row.in_garage:
            background = QColor(colors.get("pit_row_background", "#17191D"))
        elif row.under_yellow or row.flag == 2:
            background = QColor(colors.get("yellow_row_background", "#2A250B"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRect(rect)
        for key, cell in self._column_rects(rect):
            self._draw_cell(painter, key, cell, row, category)
        painter.setPen(QPen(QColor(category.color), max(1.0, 1.2 * self._scale)))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())

    def _draw_cell(self, painter: QPainter, key: str, rect: QRectF, row: StandingRow, category: CategoryBlock) -> None:
        colors = self.config.get("colors", {})
        if key == "position":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(category.color))
            painter.drawRect(rect.adjusted(0, 2 * self._scale, -2 * self._scale, -2 * self._scale))
            self._text(painter, rect, f"{row.class_position}", 0.76, True)
        elif key == "change":
            value = row.position_change
            if value > 0:
                text, color = f"{value} ▲", colors.get("position_gain", "#00A020")
            elif value < 0:
                text, color = f"{abs(value)} ▼", colors.get("position_loss", "#E52B35")
            else:
                text, color = "0  -", colors.get("muted", "#A7AFBA")
            self._text(painter, rect, text, 0.62, True, QColor(color))
        elif key == "flag":
            painter.setFont(self._font(0.70, False, emoji=True))
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, flag_emoji(row.nationality, row.country_code))
        elif key == "badge":
            label = badge_text(row.badge)
            if label:
                target = rect.adjusted(5 * self._scale, 10 * self._scale, -5 * self._scale, -10 * self._scale)
                color = QColor(badge_color(row.badge, colors))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawRect(target)
                self._text(painter, target, label, 0.42, True)
        elif key == "driver":
            target = rect.adjusted(8 * self._scale, 0, -6 * self._scale, 0)
            painter.setFont(self._font(0.78, row.is_player))
            painter.setPen(QColor(colors.get("text", "#FFFFFF")))
            text = painter.fontMetrics().elidedText(row.driver_name, Qt.TextElideMode.ElideRight, max(1, int(target.width())))
            painter.drawText(target, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
            self._draw_driver_status(painter, target, row)
        elif key == "brand":
            pixmap = self.logos.pixmap(row.manufacturer, max(1, int(rect.width() * 0.78)), max(1, int(rect.height() * 0.68)))
            if pixmap is not None:
                x = rect.center().x() - pixmap.width() / 2
                y = rect.center().y() - pixmap.height() / 2
                painter.drawPixmap(int(x), int(y), pixmap)
            else:
                self._text(painter, rect, brand_short(row.manufacturer), 0.48, True, QColor(colors.get("brand_text", "#D8E1EA")))
        elif key == "number":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(category.color))
            painter.drawRect(rect.adjusted(3 * self._scale, 2 * self._scale, -3 * self._scale, -2 * self._scale))
            self._text(painter, rect, row.car_number or "--", 0.68, True)
        elif key == "laps":
            self._text(painter, rect, f"{row.laps:02d}", 0.70, True)
        elif key == "best":
            if row.personal_best_highlight:
                color = QColor(colors.get("personal_best", "#008E16"))
            elif row.is_session_fastest:
                color = QColor(colors.get("best_lap", "#8B4DFF"))
            else:
                color = QColor(colors.get("last_lap", "#FFFFFF"))
            self._text(painter, rect, format_lap(row.best_lap_s), 0.68, True, color)
        elif key == "last":
            if (
                row.last_lap_invalidated
                and bool(self.config.get("show_invalid_lap_status", True))
            ):
                color = QColor(
                    colors.get("invalid_lap", "#FF3B45")
                )
                lap = format_lap(row.last_lap_s)
                text = "INV" if row.last_lap_s <= 0 else f"INV {lap}"
                self._text(painter, rect, text, 0.56, True, color)
                return
            if row.last_lap_s <= 0:
                color = QColor(colors.get("muted", "#A7AFBA"))
            elif (
                row.personal_best_highlight
                and row.best_lap_s > 0
                and row.last_lap_s <= row.best_lap_s + 0.001
            ):
                color = QColor(colors.get("personal_best", "#008E16"))
            else:
                color = QColor(colors.get("last_lap", "#FFFFFF"))
            self._text(painter, rect, format_lap(row.last_lap_s), 0.68, True, color)
        elif key == "gap":
            self._text(painter, rect, row.gap_text, 0.68, True)
        elif key == "penalty":
            if row.penalties > 0:
                text = f"P×{row.penalties}" if row.penalties > 1 else "P"
                self._text(
                    painter,
                    rect,
                    text,
                    0.62,
                    True,
                    QColor(colors.get("invalid_lap", "#FF3B45")),
                )
        elif key == "tyre":
            self._draw_tyre(painter, rect, tyre_short(row.tyre_compound))
        elif key == "energy":
            self._draw_percent(painter, rect, row.energy_percent, "energy")
        elif key == "damage":
            self._draw_percent(painter, rect, row.damage_percent, "damage")

    def _draw_driver_status(self, painter: QPainter, rect: QRectF, row: StandingRow) -> None:
        status = ""
        color = ""
        if row.finish_state.casefold() in {"dnf", "didnotfinish", "2"}:
            status, color = "DNF", "#E5222B"
        elif row.finish_state.casefold() in {"dq", "disqualified", "3"}:
            status, color = "DQ", "#E5222B"
        elif (
            row.current_lap_invalidated
            and bool(self.config.get("show_invalid_lap_status", True))
        ):
            status = "INV"
            color = str(
                self.config.get("colors", {}).get(
                    "invalid_lap",
                    "#FF3B45",
                )
            )
        elif row.in_garage:
            status, color = "GAR", "#666666"
        elif row.pit_status_visible:
            status, color = f"Pit {row.pit_time_s:.0f}s", "#D95B00"
        if not status:
            return
        painter.setFont(self._font(0.48, True))
        width = painter.fontMetrics().horizontalAdvance(status) + 14 * self._scale
        box = QRectF(rect.right() - width, rect.top() + 7 * self._scale, width, rect.height() - 14 * self._scale)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawRect(box)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, status)

    def _draw_percent(self, painter: QPainter, rect: QRectF, value: float | None, kind: str) -> None:
        colors = self.config.get("colors", {})
        if value is None:
            self._text(painter, rect, "--", 0.66, True, QColor(colors.get("muted", "#A7AFBA")))
            return
        value = max(0.0, min(100.0, float(value)))
        if kind == "energy":
            if value < 15.0:
                color = colors.get("energy_low", "#E5222B")
            elif value < 25.0:
                color = colors.get("energy_mid", "#E49127")
            else:
                color = colors.get("energy_high", "#FFFFFF")
        else:
            if value >= 40.0:
                color = colors.get("damage_high", "#E5222B")
            elif value >= 15.0:
                color = colors.get("damage_mid", "#E87531")
            else:
                color = colors.get("damage_low", "#FFFFFF")
        self._text(painter, rect, f"{value:.1f}%" if kind == "energy" else f"{value:.0f}%", 0.68, True, QColor(color))

    def _draw_tyre(self, painter: QPainter, rect: QRectF, compound: str) -> None:
        color = QColor(
            self.config.get("colors", {}).get("tyre", "#C7B87A")
        )
        icon_scale = max(
            0.70,
            min(2.0, float(self.config.get("tyre_icon_scale", 1.25))),
        )
        icon_height = min(
            rect.height() * 0.90,
            max(8.0, rect.height() * 0.62 * icon_scale),
        )
        icon_width = max(5.0, icon_height * 0.48)
        gap = max(2.0, 5.0 * self._scale)
        text_width = 0.0
        if compound:
            painter.setFont(self._font(0.70, True))
            text_width = painter.fontMetrics().horizontalAdvance(compound)
        group_width = icon_width + (gap + text_width if compound else 0.0)
        left = rect.center().x() - group_width / 2.0
        tyre_rect = QRectF(
            left,
            rect.center().y() - icon_height / 2.0,
            icon_width,
            icon_height,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(
            tyre_rect,
            icon_width * 0.36,
            icon_width * 0.36,
        )
        painter.setPen(QPen(QColor(0, 0, 0, 150), max(1.0, self._scale)))
        for fraction in (0.34, 0.66):
            y = tyre_rect.top() + tyre_rect.height() * fraction
            painter.drawLine(QLineF(
                tyre_rect.left() + 1.0,
                y,
                tyre_rect.right() - 1.0,
                y,
            ))
        if compound:
            text_rect = QRectF(
                tyre_rect.right() + gap,
                rect.top(),
                max(1.0, rect.right() - tyre_rect.right() - gap),
                rect.height(),
            )
            self._text(
                painter,
                text_rect,
                compound,
                0.70,
                True,
                color,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            )

    def _draw_clipped_notice(self, painter: QPainter, rect: QRectF) -> None:
        if not self.edit_mode:
            return
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 190))
        painter.drawRect(rect)
        self._text(painter, rect, "AUMENTE A ALTURA PARA MOSTRAR AS OUTRAS LINHAS", 0.48, True, QColor("#FFC42E"))

    def _column_rects(self, rect: QRectF) -> list[tuple[str, QRectF]]:
        enabled = {
            "flag": bool(self.config.get("show_country_flag", True)),
            "badge": bool(self.config.get("show_badge", True)),
            "brand": bool(self.config.get("show_brand_logo", True)),
            "penalty": (
                bool(self.config.get("show_penalty_column", True))
                and self._has_penalties()
            ),
            "tyre": bool(self.config.get("show_tyre", True)),
            "energy": bool(self.config.get("show_energy", True)),
            "damage": bool(self.config.get("show_damage", True)),
        }
        columns = [(key, width) for key, width in self.BASE_COLUMNS if enabled.get(key, True)]
        base_total = sum(width for _, width in columns)
        factor = rect.width() / base_total if base_total > 0 else 1.0
        x = rect.left()
        result: list[tuple[str, QRectF]] = []
        for index, (key, width) in enumerate(columns):
            actual = width * factor
            if index == len(columns) - 1:
                actual = rect.right() - x
            result.append((key, QRectF(x, rect.top(), actual, rect.height())))
            x += actual
        return result

    def _has_penalties(self) -> bool:
        return any(
            row.penalties > 0
            for category in self.view.categories
            for row in category.rows
        )

    def _text(
        self,
        painter: QPainter,
        rect: QRectF,
        text: str,
        multiplier: float,
        bold: bool,
        color: QColor | None = None,
        alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignCenter,
    ) -> None:
        painter.setFont(self._font(multiplier, bold))
        painter.setPen(color or QColor(self.config.get("colors", {}).get("text", "#FFFFFF")))
        painter.drawText(rect, alignment, str(text))

    def _font(self, multiplier: float, bold: bool, emoji: bool = False) -> QFont:
        family = "Segoe UI Emoji" if emoji else str(self.config.get("font_name", "Bahnschrift Condensed"))
        font = QFont(family)
        font.setBold(bold)
        font.setPixelSize(max(6, round(float(self.config.get("font_size", 26)) * multiplier * self._scale)))
        return font

    def _resize_handle_rect(self) -> QRectF:
        size = max(10.0, 15.0 * self._scale)
        return QRectF(self.width() - size - 4, self.height() - size - 4, size, size)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self.edit_mode or event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        self.selected.emit(self.widget_id)
        if self._resize_handle_rect().contains(event.position()):
            self._resizing = True
            self._resize_origin = event.globalPosition().toPoint()
            self._resize_width = self.width()
            self._resize_height = self.height()
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
        if self._resizing:
            delta = event.globalPosition().toPoint() - self._resize_origin
            width = max(self.minimumWidth(), self._resize_width + delta.x())
            if bool(self.config.get("auto_fit_height", True)):
                self.resize(width, self.height())
            else:
                self.resize(
                    width,
                    max(
                        self.minimumHeight(),
                        self._resize_height + delta.y(),
                    ),
                )
            event.accept()
            return
        if self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        self.setCursor(Qt.CursorShape.SizeFDiagCursor if self._resize_handle_rect().contains(event.position()) else Qt.CursorShape.SizeAllCursor)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        changed = self._dragging or self._resizing
        self._dragging = False
        self._resizing = False
        self.setCursor(Qt.CursorShape.SizeAllCursor if self.edit_mode else Qt.CursorShape.ArrowCursor)
        if changed:
            self._emit_geometry()
            event.accept()
        else:
            event.ignore()

    def _emit_geometry(self) -> None:
        screen = self.screen()
        if screen is None:
            return
        geometry = screen.geometry()
        self.geometry_changed.emit(
            self.widget_id,
            (self.x() - geometry.left()) / geometry.width(),
            (self.y() - geometry.top()) / geometry.height(),
            self.width() / geometry.width(),
            self.height() / geometry.height(),
        )


def format_lap(seconds: float) -> str:
    if seconds <= 0:
        return "--:--:---"
    minutes = int(seconds // 60)
    remainder = seconds - minutes * 60
    return f"{minutes}:{remainder:06.3f}"


def tyre_short(value: str) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    for word, short in (("SOFT", "S"), ("MEDIUM", "M"), ("HARD", "H"), ("WET", "W"), ("INTER", "I")):
        if word in text:
            return short
    return text[:3]
