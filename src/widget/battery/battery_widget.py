#  SectorFlow is an open-source overlay application for racing simulation.
#  Copyright (C) 2022-2026 SectorFlow developers
#  Based on TinyPedal - Copyright (C) 2022-2026 TinyPedal developers
#
#  This file is part of SectorFlow.
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

from __future__ import annotations

from typing import Any

from PySide6.QtCore import (
    QPoint,
    QLineF,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPen,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .battery_models import (
    BatteryViewData,
)
from .battery_tracker import (
    BatteryLapTracker,
)


class BatteryGauge(QWidget):
    def __init__(
        self,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.charge_pct = 0.0
        self.motor_state = 0
        self.low_threshold = 10.0
        self.high_threshold = 95.0
        self.colors: dict[
            str,
            str,
        ] = {}
        self.scale = 1.0
        self.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )

    def set_data(
        self,
        charge_pct: float,
        motor_state: int,
        config: dict[str, Any],
        scale: float,
    ) -> None:
        self.charge_pct = max(
            0.0,
            min(
                100.0,
                float(charge_pct),
            ),
        )
        self.motor_state = int(
            motor_state
        )
        self.low_threshold = float(
            config.get(
                "low_battery_threshold",
                10.0,
            )
        )
        self.high_threshold = float(
            config.get(
                "high_battery_threshold",
                95.0,
            )
        )
        self.colors = dict(
            config.get(
                "colors",
                {},
            )
        )
        self.scale = max(
            0.35,
            float(scale),
        )
        width = max(
            34,
            round(
                float(
                    config.get(
                        "battery_base_width",
                        62,
                    )
                )
                * self.scale
            ),
        )
        height = max(
            84,
            round(
                float(
                    config.get(
                        "battery_base_height",
                        154,
                    )
                )
                * self.scale
            ),
        )
        self.setFixedSize(
            width,
            height,
        )
        self.update()

    def _fill_color(self) -> QColor:
        if self.motor_state == 3:
            return QColor(
                self.colors.get(
                    "regen",
                    "#16C784",
                )
            )

        if (
            self.charge_pct
            >= self.high_threshold
        ):
            return QColor(
                self.colors.get(
                    "high",
                    "#9333EA",
                )
            )

        if (
            self.charge_pct
            <= self.low_threshold
        ):
            return QColor(
                self.colors.get(
                    "low",
                    "#DC2626",
                )
            )

        return QColor(
            self.colors.get(
                "normal",
                "#2563EB",
            )
        )

    def paintEvent(
        self,
        event: QPaintEvent,
    ) -> None:
        del event

        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing,
            True,
        )

        w = float(
            self.width()
        )
        h = float(
            self.height()
        )
        s = self.scale
        text_height = max(
            18.0,
            30.0 * s,
        )
        battery_area_h = max(
            40.0,
            h - text_height,
        )

        nipple_h = max(
            3.0,
            battery_area_h * 0.055,
        )
        nipple_w = w * 0.40
        nipple_x = (
            w - nipple_w
        ) / 2.0
        nipple_y = max(
            1.0,
            2.0 * s,
        )

        body_x = max(
            2.0,
            4.0 * s,
        )
        body_y = (
            nipple_y
            + nipple_h
        )
        body_w = (
            w - body_x * 2.0
        )
        body_h = max(
            20.0,
            battery_area_h
            - body_y
            - max(
                2.0,
                3.0 * s,
            ),
        )
        radius = max(
            3.0,
            7.0 * s,
        )
        border_width = max(
            1.0,
            2.0 * s,
        )

        painter.setPen(
            QPen(
                QColor(
                    self.colors.get(
                        "gauge_border",
                        "#5B6573",
                    )
                ),
                border_width,
            )
        )
        painter.setBrush(
            Qt.BrushStyle.NoBrush
        )
        painter.drawRoundedRect(
            QRectF(
                body_x,
                body_y,
                body_w,
                body_h,
            ),
            radius,
            radius,
        )

        painter.setPen(
            Qt.PenStyle.NoPen
        )
        painter.setBrush(
            QBrush(
                QColor(
                    self.colors.get(
                        "gauge_terminal",
                        "#C8CDD4",
                    )
                )
            )
        )
        painter.drawRoundedRect(
            QRectF(
                nipple_x,
                nipple_y,
                nipple_w,
                nipple_h + 1.0,
            ),
            max(1.0, 2.0 * s),
            max(1.0, 2.0 * s),
        )

        fill_ratio = (
            self.charge_pct
            / 100.0
        )
        pad = max(
            2.0,
            4.0 * s,
        )
        maximum_fill_h = max(
            0.0,
            body_h - pad * 2.0,
        )
        fill_h = (
            maximum_fill_h
            * fill_ratio
        )

        if fill_h > 0.0:
            painter.setBrush(
                QBrush(
                    self._fill_color()
                )
            )
            painter.drawRoundedRect(
                QRectF(
                    body_x + pad,
                    body_y
                    + body_h
                    - pad
                    - fill_h,
                    body_w - pad * 2.0,
                    fill_h,
                ),
                max(1.0, 3.0 * s),
                max(1.0, 3.0 * s),
            )

        font = QFont(
            str(
                self.property(
                    "fontFamily"
                )
                or "Arial"
            )
        )
        font.setBold(True)
        font.setPixelSize(
            max(
                9,
                round(18 * s),
            )
        )
        painter.setFont(font)
        painter.setPen(
            QPen(
                QColor(
                    self.colors.get(
                        "text",
                        "#E5E7EB",
                    )
                )
            )
        )
        painter.drawText(
            QRectF(
                0,
                battery_area_h,
                w,
                h - battery_area_h,
            ),
            Qt.AlignmentFlag.AlignCenter,
            f"{self.charge_pct:.0f}%",
        )


class ComparisonBar(QWidget):
    def __init__(
        self,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.delta: float | None = None
        self.maximum = 2.0
        self.colors: dict[
            str,
            str,
        ] = {}
        self.scale = 1.0
        self.setMinimumHeight(10)

    def set_data(
        self,
        delta: float | None,
        config: dict[str, Any],
        scale: float,
    ) -> None:
        self.delta = delta
        self.maximum = max(
            0.1,
            float(
                config.get(
                    "comparison_max_delta_pct",
                    2.0,
                )
            ),
        )
        self.colors = dict(
            config.get(
                "colors",
                {},
            )
        )
        self.scale = max(
            0.35,
            float(scale),
        )
        self.setFixedHeight(
            max(
                10,
                round(18 * self.scale),
            )
        )
        self.update()

    def paintEvent(
        self,
        event: QPaintEvent,
    ) -> None:
        del event

        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing
        )
        rect = QRectF(
            self.rect()
        ).adjusted(
            1,
            2,
            -1,
            -2,
        )
        radius = max(
            2.0,
            4.0 * self.scale,
        )

        painter.setPen(
            Qt.PenStyle.NoPen
        )
        painter.setBrush(
            QColor(
                self.colors.get(
                    "bar_background",
                    "#27313E",
                )
            )
        )
        painter.drawRoundedRect(
            rect,
            radius,
            radius,
        )

        center = rect.center().x()
        painter.setPen(
            QPen(
                QColor(
                    self.colors.get(
                        "bar_center",
                        "#D1D5DB",
                    )
                ),
                max(
                    1.0,
                    1.5 * self.scale,
                ),
            )
        )
        painter.drawLine(
            QLineF(
                center,
                rect.top(),
                center,
                rect.bottom(),
            )
        )

        if self.delta is None:
            return

        normalized = max(
            -1.0,
            min(
                1.0,
                self.delta
                / self.maximum,
            ),
        )
        half = rect.width() / 2.0
        width = abs(
            normalized
        ) * half

        if width <= 0.5:
            return

        # Menos consumo que a volta anterior = esquerda e verde.
        if normalized < 0.0:
            fill = QRectF(
                center - width,
                rect.top(),
                width,
                rect.height(),
            )
            color = QColor(
                self.colors.get(
                    "better",
                    "#16C784",
                )
            )
        else:
            fill = QRectF(
                center,
                rect.top(),
                width,
                rect.height(),
            )
            color = QColor(
                self.colors.get(
                    "worse",
                    "#EF4444",
                )
            )

        painter.setPen(
            Qt.PenStyle.NoPen
        )
        painter.setBrush(color)
        painter.drawRoundedRect(
            fill,
            radius,
            radius,
        )


class MetricCard(QFrame):
    def __init__(
        self,
        title: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.setObjectName(
            "BatteryMetricCard"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            4,
            3,
            4,
            3,
        )
        layout.setSpacing(0)

        self.title_label = QLabel(title)
        self.title_label.setObjectName(
            "BatteryMetricTitle"
        )
        self.title_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.value_label = QLabel("--")
        self.value_label.setObjectName(
            "BatteryMetricValue"
        )
        self.value_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        layout.addWidget(
            self.title_label
        )
        layout.addWidget(
            self.value_label
        )
        self._layout = layout

    def set_value(
        self,
        value: str,
        color: str | None = None,
    ) -> None:
        self.value_label.setText(
            value
        )

        if color:
            self.value_label.setStyleSheet(
                f"color: {color};"
            )
        else:
            self.value_label.setStyleSheet(
                ""
            )


class BatteryWidget(QWidget):
    geometry_changed = Signal(
        str,
        float,
        float,
        float,
        float,
    )
    selected = Signal(str)

    BASE_WIDTH = 520.0
    COMPACT_BASE_WIDTH = 100.0

    def __init__(
        self,
        widget_id: str,
        config: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.widget_id = widget_id
        self.config = config
        self.tracker = BatteryLapTracker(
            config
        )
        self.view_data = (
            self.tracker.preview()
        )
        self.edit_mode = False

        self._dragging = False
        self._resizing = False
        self._drag_offset = QPoint()
        self._resize_start_global = QPoint()
        self._resize_start_width = 0
        self._responsive_scale = 1.0
        self._metrics_pending = False
        self._fitting = False

        self.setWindowTitle(
            "Sector Flow Drive - Battery"
        )
        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
            True,
        )
        self.setMinimumWidth(290)
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )

        self.root_layout = QVBoxLayout(
            self
        )
        self.root_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        self.main_frame = QFrame()
        self.main_frame.setObjectName(
            "BatteryMainFrame"
        )
        self.main_layout = QHBoxLayout(
            self.main_frame
        )
        self.root_layout.addWidget(
            self.main_frame
        )

        self.gauge = BatteryGauge()
        self.main_layout.addWidget(
            self.gauge,
            0,
            Qt.AlignmentFlag.AlignVCenter,
        )

        self.info_frame = QFrame()
        self.info_frame.setObjectName(
            "BatteryInfoFrame"
        )
        self.info_layout = QVBoxLayout(
            self.info_frame
        )
        self.main_layout.addWidget(
            self.info_frame,
            1,
        )

        self.header_layout = QHBoxLayout()
        self.title_label = QLabel(
            "HYBRID BATTERY"
        )
        self.title_label.setObjectName(
            "BatteryTitle"
        )
        self.mode_label = QLabel("OFF")
        self.mode_label.setObjectName(
            "BatteryMode"
        )
        self.mode_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.header_layout.addWidget(
            self.title_label
        )
        self.header_layout.addStretch()
        self.header_layout.addWidget(
            self.mode_label
        )
        self.info_layout.addLayout(
            self.header_layout
        )

        self.primary_grid = QGridLayout()
        self.this_card = MetricCard(
            "THIS LAP"
        )
        self.last_card = MetricCard(
            "LAST LAP"
        )
        self.delta_card = MetricCard(
            "VS LAST"
        )
        self.primary_grid.addWidget(
            self.this_card,
            0,
            0,
        )
        self.primary_grid.addWidget(
            self.last_card,
            0,
            1,
        )
        self.primary_grid.addWidget(
            self.delta_card,
            0,
            2,
        )
        self.info_layout.addLayout(
            self.primary_grid
        )

        self.comparison_bar = (
            ComparisonBar()
        )
        self.info_layout.addWidget(
            self.comparison_bar
        )

        self.secondary_grid = (
            QGridLayout()
        )
        self.drain_card = MetricCard(
            "DRAIN"
        )
        self.regen_card = MetricCard(
            "REGEN"
        )
        self.projected_card = MetricCard(
            "EST/LAP"
        )
        self.laps_card = MetricCard(
            "LAPS"
        )
        self.secondary_grid.addWidget(
            self.drain_card,
            0,
            0,
        )
        self.secondary_grid.addWidget(
            self.regen_card,
            0,
            1,
        )
        self.secondary_grid.addWidget(
            self.projected_card,
            0,
            2,
        )
        self.secondary_grid.addWidget(
            self.laps_card,
            0,
            3,
        )
        self.info_layout.addLayout(
            self.secondary_grid
        )

        self.details_grid = QGridLayout()
        self.motor_power_card = MetricCard("MOTOR")
        self.regen_kw_card = MetricCard("REGEN kW")
        self.motor_temp_card = MetricCard("TEMP")
        self.virtual_energy_card = MetricCard("VIRTUAL")
        self.lap_progress_card = MetricCard("LAP")
        for column, card in enumerate(
            (
                self.motor_power_card,
                self.regen_kw_card,
                self.motor_temp_card,
                self.virtual_energy_card,
                self.lap_progress_card,
            )
        ):
            self.details_grid.addWidget(card, 0, column)
        self.info_layout.addLayout(self.details_grid)

        self.apply_config()
        self._render()

    def apply_config(self) -> None:
        self.tracker.update_config(
            self.config
        )
        self.setWindowOpacity(
            max(
                0.10,
                min(
                    1.0,
                    float(
                        self.config.get(
                            "opacity",
                            0.98,
                        )
                    ),
                ),
            )
        )
        self.comparison_bar.setVisible(
            bool(
                self.config.get(
                    "show_comparison_bar",
                    True,
                )
            )
        )
        self.this_card.setVisible(
            bool(
                self.config.get(
                    "show_current_lap_use",
                    True,
                )
            )
        )
        self.last_card.setVisible(
            bool(
                self.config.get(
                    "show_last_lap_use",
                    True,
                )
            )
        )
        self.delta_card.setVisible(
            bool(
                self.config.get(
                    "show_delta_vs_last",
                    True,
                )
            )
        )
        self.drain_card.setVisible(
            bool(
                self.config.get(
                    "show_drain",
                    True,
                )
            )
        )
        self.regen_card.setVisible(
            bool(
                self.config.get(
                    "show_regen",
                    True,
                )
            )
        )
        self.projected_card.setVisible(
            bool(
                self.config.get(
                    "show_projected_use",
                    True,
                )
            )
        )
        self.laps_card.setVisible(
            bool(
                self.config.get(
                    "show_laps_remaining",
                    True,
                )
            )
        )
        detail_options = (
            (
                self.motor_power_card,
                "show_motor_power",
                True,
            ),
            (
                self.regen_kw_card,
                "show_regen_kw",
                True,
            ),
            (
                self.motor_temp_card,
                "show_motor_temperature",
                True,
            ),
            (
                self.virtual_energy_card,
                "show_virtual_energy",
                False,
            ),
            (
                self.lap_progress_card,
                "show_lap_progress",
                False,
            ),
        )
        for card, option, default in detail_options:
            card.setVisible(
                bool(self.config.get(option, default))
            )

        optional_widgets = (
            self.comparison_bar,
            self.this_card,
            self.last_card,
            self.delta_card,
            self.drain_card,
            self.regen_card,
            self.projected_card,
            self.laps_card,
            *(card for card, _, _ in detail_options),
        )
        was_compact = getattr(
            self,
            "_compact_mode",
            False,
        )
        self._compact_mode = not any(
            not widget.isHidden()
            for widget in optional_widgets
        )
        if self._compact_mode and not was_compact:
            self._compact_needs_fit = True
        self.info_frame.setVisible(not self._compact_mode)
        self.setMinimumWidth(
            1 if self._compact_mode else 290
        )
        self._schedule_metrics()
        self._render()

    def update_config(
        self,
        config: dict[str, Any],
    ) -> None:
        self.config = config
        self.apply_config()

    def apply_normalized_geometry(
        self,
        screen_geometry,
    ) -> None:
        position = self.config.get(
            "position",
            {},
        )
        size = self.config.get(
            "size",
            {},
        )
        scale = max(
            0.35,
            float(
                self.config.get(
                    "scale",
                    1.0,
                )
            ),
        )
        width = max(
            self.minimumWidth(),
            int(
                screen_geometry.width()
                * float(
                    size.get(
                        "width",
                        0.27,
                    )
                )
                * scale
            ),
        )
        # A largura salva pelo editor representa a escolha do usuário.
        # No modo compacto ela não deve ser substituída pelo ajuste inicial.
        self._compact_needs_fit = False
        x = int(
            screen_geometry.left()
            + screen_geometry.width()
            * float(
                position.get(
                    "x",
                    0.05,
                )
            )
        )
        y = int(
            screen_geometry.top()
            + screen_geometry.height()
            * float(
                position.get(
                    "y",
                    0.18,
                )
            )
        )
        self.resize(
            width,
            max(
                100,
                self.height(),
            ),
        )
        self.move(x, y)
        self._schedule_metrics()

    def update_from_session(
        self,
        session: Any,
    ) -> None:
        self.view_data = (
            self.tracker.update(
                session
            )
        )

        hide_unsupported = bool(
            self.config.get(
                "hide_when_unavailable",
                True,
            )
        )

        if (
            hide_unsupported
            and not self.view_data.available
            and not self.edit_mode
        ):
            self.hide()
        elif (
            self.view_data.available
            and bool(
                self.config.get(
                    "enabled",
                    True,
                )
            )
        ):
            self.show()

        self._render()

    def _render(self) -> None:
        data = self.view_data
        colors = self.config.get(
            "colors",
            {},
        )

        self.gauge.set_data(
            data.charge_pct,
            data.motor_state,
            self.config,
            self._responsive_scale,
        )
        self.mode_label.setText(
            data.motor_state_text
        )

        mode_color = colors.get(
            "mode_idle",
            "#9CA3AF",
        )
        if data.motor_state == 2:
            mode_color = colors.get(
                "mode_boost",
                "#A855F7",
            )
        elif data.motor_state == 3:
            mode_color = colors.get(
                "mode_regen",
                "#16C784",
            )
        self.mode_label.setStyleSheet(
            f"color: {mode_color};"
        )

        self.this_card.set_value(
            f"{data.current.net_use_pct:.2f}%"
        )
        self.last_card.set_value(
            (
                f"{data.last.net_use_pct:.2f}%"
                if data.last.completed
                else "--"
            )
        )

        if data.delta_vs_last_pct is None:
            self.delta_card.set_value(
                "--"
            )
        else:
            delta = (
                data.delta_vs_last_pct
            )
            delta_color = (
                colors.get(
                    "better",
                    "#16C784",
                )
                if delta <= 0.0
                else colors.get(
                    "worse",
                    "#EF4444",
                )
            )
            self.delta_card.set_value(
                f"{delta:+.2f}%",
                delta_color,
            )

        self.drain_card.set_value(
            f"{data.current.drain_pct:.2f}%"
        )
        self.regen_card.set_value(
            f"{data.current.regen_pct:.2f}%"
        )
        self.projected_card.set_value(
            (
                f"{data.projected_lap_use_pct:.2f}%"
                if data.projected_lap_use_pct
                is not None
                else "--"
            )
        )
        self.laps_card.set_value(
            (
                f"{data.laps_remaining:.1f}"
                if data.laps_remaining
                is not None
                else "--"
            )
        )

        self.comparison_bar.set_data(
            data.delta_vs_last_pct,
            self.config,
            self._responsive_scale,
        )

        self.motor_power_card.set_value(
            f"{abs(data.motor_power_kw):.0f} kW"
        )
        self.regen_kw_card.set_value(
            f"{data.regen_kw:.0f} kW"
        )
        self.motor_temp_card.set_value(
            f"{data.motor_temp_c:.0f}°"
        )
        self.virtual_energy_card.set_value(
            f"{data.virtual_energy_pct:.0f}%"
        )
        self.lap_progress_card.set_value(
            f"{data.lap_progress_pct:.0f}%"
        )
        self._schedule_metrics()

    def resizeEvent(
        self,
        event: QResizeEvent,
    ) -> None:
        super().resizeEvent(event)
        self._schedule_metrics()

    def _schedule_metrics(self) -> None:
        if self._metrics_pending:
            return

        self._metrics_pending = True
        QTimer.singleShot(
            0,
            self._apply_responsive_metrics,
        )

    def _apply_responsive_metrics(
        self,
    ) -> None:
        self._metrics_pending = False
        minimum = max(
            0.35,
            float(
                self.config.get(
                    "responsive_min_scale",
                    0.55,
                )
            ),
        )
        maximum = max(
            minimum,
            float(
                self.config.get(
                    "responsive_max_scale",
                    2.20,
                )
            ),
        )
        internal = max(
            0.50,
            float(
                self.config.get(
                    "internal_scale",
                    1.0,
                )
            ),
        )
        reference_width = (
            self.COMPACT_BASE_WIDTH
            if getattr(self, "_compact_mode", False)
            else self.BASE_WIDTH
        )
        self._responsive_scale = max(
            minimum,
            min(
                maximum,
                self.width()
                / reference_width
                * internal,
            ),
        )
        s = self._responsive_scale
        margin = max(
            4,
            round(12 * s),
        )
        gap = max(
            2,
            round(6 * s),
        )

        self.main_layout.setContentsMargins(
            margin,
            margin,
            margin,
            margin,
        )
        self.main_layout.setSpacing(
            gap
        )
        self.info_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )
        self.info_layout.setSpacing(
            max(
                1,
                round(4 * s),
            )
        )
        self.header_layout.setSpacing(
            gap
        )
        self.primary_grid.setHorizontalSpacing(
            gap
        )
        self.primary_grid.setVerticalSpacing(
            gap
        )
        self.secondary_grid.setHorizontalSpacing(
            gap
        )
        self.secondary_grid.setVerticalSpacing(
            gap
        )
        self.details_grid.setHorizontalSpacing(gap)
        self.details_grid.setVerticalSpacing(gap)

        card_margin = max(
            2,
            round(4 * s),
        )
        for card in (
            self.this_card,
            self.last_card,
            self.delta_card,
            self.drain_card,
            self.regen_card,
            self.projected_card,
            self.laps_card,
            self.motor_power_card,
            self.regen_kw_card,
            self.motor_temp_card,
            self.virtual_energy_card,
            self.lap_progress_card,
        ):
            card._layout.setContentsMargins(
                card_margin,
                max(
                    1,
                    round(2 * s),
                ),
                card_margin,
                max(
                    1,
                    round(2 * s),
                ),
            )

        self.gauge.setProperty(
            "fontFamily",
            str(
                self.config.get(
                    "font_name",
                    "Arial",
                )
            ),
        )
        self.gauge.set_data(
            self.view_data.charge_pct,
            self.view_data.motor_state,
            self.config,
            s,
        )
        self.comparison_bar.set_data(
            self.view_data.delta_vs_last_pct,
            self.config,
            s,
        )
        self._apply_style(s)
        QTimer.singleShot(
            0,
            self._fit_content,
        )

    def _apply_style(
        self,
        scale: float,
    ) -> None:
        colors = self.config.get(
            "colors",
            {},
        )
        background = colors.get(
            "background",
            "rgba(10,15,23,238)",
        )
        panel = colors.get(
            "panel",
            "#151B26",
        )
        border = colors.get(
            "border",
            "#344155",
        )
        text = colors.get(
            "text",
            "#F4F7FB",
        )
        muted = colors.get(
            "muted",
            "#9BA8BA",
        )
        font_name = str(
            self.config.get(
                "font_name",
                "Arial",
            )
        )
        base_font = max(
            8,
            int(
                self.config.get(
                    "font_size",
                    14,
                )
            ),
        )
        title_size = max(
            8,
            round(
                base_font
                * 0.88
                * scale
            ),
        )
        value_size = max(
            7,
            round(
                base_font
                * 0.86
                * scale
            ),
        )
        small_size = max(
            6,
            round(
                base_font
                * 0.58
                * scale
            ),
        )
        radius = max(
            4,
            round(10 * scale),
        )
        card_radius = max(
            3,
            round(6 * scale),
        )
        border_width = max(
            1,
            round(1 * scale),
        )
        mode_padding = max(
            2,
            round(4 * scale),
        )

        self.setStyleSheet(
            f"""
            BatteryWidget {{
                background: transparent;
                border: none;
                font-family: "{font_name}";
            }}

            QFrame#BatteryMainFrame {{
                background-color: {background};
                border: {border_width}px
                solid {border};
                border-radius: {radius}px;
            }}

            QFrame#BatteryInfoFrame {{
                background: transparent;
                border: none;
            }}

            QLabel {{
                color: {text};
                background: transparent;
                border: none;
                font-family: "{font_name}";
            }}

            QLabel#BatteryTitle {{
                font-size: {title_size}px;
                font-weight: 900;
            }}

            QLabel#BatteryMode {{
                background-color: {panel};
                border: {border_width}px
                solid {border};
                border-radius: {card_radius}px;
                padding: {mode_padding}px;
                font-size: {small_size}px;
                font-weight: 900;
            }}

            QFrame#BatteryMetricCard {{
                background-color: {panel};
                border: {border_width}px
                solid {border};
                border-radius: {card_radius}px;
            }}

            QLabel#BatteryMetricTitle {{
                color: {muted};
                font-size: {small_size}px;
                font-weight: bold;
            }}

            QLabel#BatteryMetricValue {{
                color: {text};
                font-size: {value_size}px;
                font-weight: 900;
            }}

            """
        )

    def set_edit_mode(
        self,
        enabled: bool,
    ) -> None:
        self.edit_mode = bool(
            enabled
        )

        if self.edit_mode:
            self.view_data = (
                self.tracker.preview()
            )
            self.show()

        self.setCursor(
            Qt.CursorShape.SizeAllCursor
            if self.edit_mode
            else Qt.CursorShape.ArrowCursor
        )
        self._render()
        self.update()

    def reset_session_state(self) -> None:
        self.tracker.reset()

    def paintEvent(
        self,
        event: QPaintEvent,
    ) -> None:
        super().paintEvent(event)

        if not self.edit_mode:
            return

        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing
        )
        color = QColor(
            self.config.get(
                "colors",
                {},
            ).get(
                "edit_border",
                "#9B5CFF",
            )
        )
        pen = QPen(
            color,
            max(
                1.0,
                2.0
                * self._responsive_scale,
            ),
        )
        pen.setStyle(
            Qt.PenStyle.DashLine
        )
        painter.setPen(pen)
        painter.setBrush(
            Qt.BrushStyle.NoBrush
        )
        painter.drawRoundedRect(
            QRectF(self.rect()).adjusted(
                1,
                1,
                -1,
                -1,
            ),
            10,
            10,
        )
        painter.setPen(
            Qt.PenStyle.NoPen
        )
        painter.setBrush(
            QColor("#FFFFFF")
        )
        painter.drawRect(
            self._resize_handle_rect()
        )

    def mousePressEvent(
        self,
        event: QMouseEvent,
    ) -> None:
        if (
            not self.edit_mode
            or event.button()
            != Qt.MouseButton.LeftButton
        ):
            event.ignore()
            return

        self.selected.emit(
            self.widget_id
        )

        if self._resize_handle_rect().contains(
            event.position()
        ):
            self._resizing = True
            self._resize_start_global = (
                event.globalPosition().toPoint()
            )
            self._resize_start_width = (
                self.width()
            )
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

    def mouseMoveEvent(
        self,
        event: QMouseEvent,
    ) -> None:
        if not self.edit_mode:
            event.ignore()
            return

        if self._resizing:
            delta = (
                event.globalPosition().toPoint()
                - self._resize_start_global
            )
            self.resize(
                max(
                    self.minimumWidth(),
                    self._resize_start_width
                    + delta.x(),
                ),
                self.height(),
            )
            self._schedule_metrics()
            event.accept()
            return

        if self._dragging:
            self.move(
                event.globalPosition().toPoint()
                - self._drag_offset
            )
            event.accept()
            return

        self.setCursor(
            Qt.CursorShape.SizeFDiagCursor
            if self._resize_handle_rect().contains(
                event.position()
            )
            else Qt.CursorShape.SizeAllCursor
        )

    def mouseReleaseEvent(
        self,
        event: QMouseEvent,
    ) -> None:
        if (
            event.button()
            != Qt.MouseButton.LeftButton
        ):
            event.ignore()
            return

        changed = (
            self._dragging
            or self._resizing
        )
        self._dragging = False
        self._resizing = False
        self.setCursor(
            Qt.CursorShape.SizeAllCursor
            if self.edit_mode
            else Qt.CursorShape.ArrowCursor
        )

        if changed:
            self._fit_content()
            self._emit_geometry()
            event.accept()
        else:
            event.ignore()

    def _fit_content(self) -> None:
        if self._fitting:
            return

        self._fitting = True
        self.root_layout.activate()
        desired = max(
            95,
            self.root_layout.sizeHint().height(),
        )
        desired_width = self.width()
        if getattr(
            self,
            "_compact_needs_fit",
            False,
        ):
            desired_width = max(
                1,
                self.root_layout.sizeHint().width(),
            )
            self._compact_needs_fit = False

        if abs(
            self.height() - desired
        ) > 1 or abs(
            self.width() - desired_width
        ) > 1:
            self.resize(
                desired_width,
                desired,
            )

        self._fitting = False

    def _resize_handle_rect(
        self,
    ) -> QRectF:
        size = max(
            8,
            round(
                12
                * self._responsive_scale
            ),
        )
        return QRectF(
            self.width() - size - 3,
            self.height() - size - 3,
            size,
            size,
        )

    def _emit_geometry(self) -> None:
        screen = self.screen()

        if screen is None:
            return

        rect = screen.geometry()
        self.geometry_changed.emit(
            self.widget_id,
            (
                self.x()
                - rect.left()
            )
            / rect.width(),
            (
                self.y()
                - rect.top()
            )
            / rect.height(),
            self.width()
            / rect.width(),
            self.height()
            / rect.height(),
        )
