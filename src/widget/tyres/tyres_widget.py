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
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPen,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.i18n import tr

from .tyres_logic import TyresLogic
from .tyres_models import (
    TyreWheelViewData,
    TyresViewData,
)


def tyres_panel_margin(config: dict[str, Any], scale: float) -> int:
    return max(
        0,
        round(float(config.get("panel_margin", 6.0)) * float(scale)),
    )


def tyres_wear_font_size(
    config: dict[str, Any],
    base_font: int,
    scale: float,
) -> int:
    wear_scale = max(0.50, float(config.get("wear_font_scale", 0.95)))
    return max(8, round(base_font * wear_scale * float(scale)))


def tyres_main_frame_style(
    config: dict[str, Any],
    background: str,
    radius: int,
    border_width: int,
    border: str,
) -> str:
    if not bool(config.get("show_background", True)):
        return "background: transparent; border: none;"
    return (
        f"background-color: {background}; "
        f"border-radius: {radius}px; "
        f"border: {border_width}px solid {border};"
    )


class WheelGroup(QWidget):
    def __init__(
        self,
        index: int,
        is_left: bool,
        is_front: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.index = index
        self.is_left = is_left
        self.is_front = is_front
        self.scale = 1.0

        self.group_layout = QVBoxLayout(
            self
        )
        self.group_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        self.wear_label = QLabel("100%")
        self.wear_label.setObjectName(
            "WearLabel"
        )
        self.wear_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.wheel_box = QWidget()
        self.wheel_box_layout = QHBoxLayout(
            self.wheel_box
        )
        self.wheel_box_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        self.tyre_frame = QFrame()
        self.tyre_frame.setObjectName(
            "TyreFrame"
        )
        self.tyre_layout = QVBoxLayout(
            self.tyre_frame
        )
        self.tyre_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        self.position_label = QLabel(
            ("FL", "FR", "RL", "RR")[
                index
            ]
        )
        self.position_label.setObjectName(
            "PositionLabel"
        )
        self.position_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.main_temp_label = QLabel(
            "--.-"
        )
        self.main_temp_label.setObjectName(
            "MainTempLabel"
        )
        self.main_temp_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.surface_label = QLabel(
            "L -- / C -- / R --"
        )
        self.surface_label.setObjectName(
            "SurfaceLabel"
        )
        self.surface_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.pressure_label = QLabel(
            "--- kPa"
        )
        self.pressure_label.setObjectName(
            "PressureLabel"
        )
        self.pressure_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.carcass_label = QLabel(
            "CAR --°"
        )
        self.carcass_label.setObjectName(
            "DetailLabel"
        )
        self.carcass_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.optimal_label = QLabel(
            "OPT --°"
        )
        self.optimal_label.setObjectName(
            "DetailLabel"
        )
        self.optimal_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.advanced_label = QLabel("")
        self.advanced_label.setObjectName(
            "AdvancedLabel"
        )
        self.advanced_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.advanced_label.setWordWrap(
            True
        )

        self.status_label = QLabel("")
        self.status_label.setObjectName(
            "StatusLabel"
        )
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.status_label.hide()

        self.tyre_layout.addWidget(
            self.position_label
        )
        self.tyre_layout.addWidget(
            self.main_temp_label,
            1,
        )
        self.tyre_layout.addWidget(
            self.surface_label
        )
        self.tyre_layout.addWidget(
            self.pressure_label
        )
        self.tyre_layout.addWidget(
            self.carcass_label
        )
        self.tyre_layout.addWidget(
            self.optimal_label
        )
        self.tyre_layout.addWidget(
            self.advanced_label
        )
        self.tyre_layout.addWidget(
            self.status_label
        )

        self.brake_frame = QFrame()
        self.brake_frame.setObjectName(
            "BrakeFrame"
        )
        self.brake_layout = QVBoxLayout(
            self.brake_frame
        )
        self.brake_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        self.brake_temp_label = QLabel(
            "---"
        )
        self.brake_temp_label.setObjectName(
            "BrakeTempLabel"
        )
        self.brake_temp_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.brake_pressure_label = QLabel(
            ""
        )
        self.brake_pressure_label.setObjectName(
            "BrakePressureLabel"
        )
        self.brake_pressure_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.brake_pressure_label.hide()

        self.brake_layout.addWidget(
            self.brake_temp_label
        )
        self.brake_layout.addWidget(
            self.brake_pressure_label
        )

        if self.is_left:
            self.wheel_box_layout.addWidget(
                self.tyre_frame
            )
            self.wheel_box_layout.addWidget(
                self.brake_frame,
                alignment=Qt.AlignmentFlag.AlignVCenter,
            )
            self.wheel_box_layout.setAlignment(
                Qt.AlignmentFlag.AlignRight
                | Qt.AlignmentFlag.AlignVCenter
            )
        else:
            self.wheel_box_layout.addWidget(
                self.brake_frame,
                alignment=Qt.AlignmentFlag.AlignVCenter,
            )
            self.wheel_box_layout.addWidget(
                self.tyre_frame
            )
            self.wheel_box_layout.setAlignment(
                Qt.AlignmentFlag.AlignLeft
                | Qt.AlignmentFlag.AlignVCenter
            )

        if self.is_front:
            self.group_layout.addWidget(
                self.wheel_box
            )
            self.group_layout.addWidget(
                self.wear_label
            )
        else:
            self.group_layout.addWidget(
                self.wear_label
            )
            self.group_layout.addWidget(
                self.wheel_box
            )

    def apply_visibility(
        self,
        config: dict[str, Any],
    ) -> None:
        self.position_label.setVisible(
            bool(
                config.get(
                    "show_position_labels",
                    True,
                )
            )
        )
        self.surface_label.setVisible(
            bool(
                config.get(
                    "show_surface_temperatures",
                    True,
                )
            )
        )
        self.pressure_label.setVisible(
            bool(
                config.get(
                    "show_pressure",
                    True,
                )
            )
        )
        self.carcass_label.setVisible(
            bool(
                config.get(
                    "show_carcass_temperature",
                    False,
                )
            )
        )
        self.optimal_label.setVisible(
            bool(
                config.get(
                    "show_optimal_temperature",
                    False,
                )
            )
        )
        self.advanced_label.setVisible(
            any(
                bool(
                    config.get(
                        key,
                        False,
                    )
                )
                for key in (
                    "show_tire_load",
                    "show_grip_fraction",
                    "show_camber",
                    "show_toe",
                    "show_deflection",
                )
            )
        )
        self.brake_pressure_label.setVisible(
            bool(
                config.get(
                    "show_brake_pressure",
                    False,
                )
            )
        )

    def apply_scale(
        self,
        scale: float,
        config: dict[str, Any],
    ) -> None:
        self.scale = max(
            0.35,
            float(scale),
        )
        s = self.scale
        tyre_width = max(
            36,
            round(
                float(
                    config.get(
                        "tyre_base_width",
                        70,
                    )
                )
                * s
            ),
        )
        tyre_height = max(
            48,
            round(
                float(
                    config.get(
                        "tyre_base_height",
                        105,
                    )
                )
                * s
            ),
        )
        brake_width = max(
            22,
            round(
                float(
                    config.get(
                        "brake_base_width",
                        38,
                    )
                )
                * s
            ),
        )
        brake_height = max(
            20,
            round(
                float(
                    config.get(
                        "brake_base_height",
                        40,
                    )
                )
                * s
            ),
        )
        gap = max(
            1,
            round(4 * s),
        )

        self.group_layout.setSpacing(
            gap
        )
        self.wheel_box_layout.setSpacing(
            max(
                1,
                round(3 * s),
            )
        )
        self.tyre_layout.setSpacing(
            max(
                0,
                round(1 * s),
            )
        )
        self.brake_layout.setSpacing(
            max(
                0,
                round(1 * s),
            )
        )

        tyre_padding = max(
            1,
            round(3 * s),
        )
        self.tyre_layout.setContentsMargins(
            tyre_padding,
            tyre_padding,
            tyre_padding,
            tyre_padding,
        )
        self.brake_layout.setContentsMargins(
            max(1, round(2 * s)),
            max(1, round(2 * s)),
            max(1, round(2 * s)),
            max(1, round(2 * s)),
        )
        self.tyre_frame.setFixedSize(
            tyre_width,
            tyre_height,
        )
        self.brake_frame.setFixedSize(
            brake_width,
            brake_height,
        )

    def render(
        self,
        wheel: TyreWheelViewData,
        logic: TyresLogic,
        config: dict[str, Any],
    ) -> None:
        temp_c = logic.main_temperature_c(
            wheel
        )
        compound_symbols = {
            "soft": "S", "medium": "M", "hard": "H",
            "wet": "W", "intermediate": "I",
        }
        compound_key = wheel.compound_name.casefold()
        compound_symbol = next(
            (symbol for name, symbol in compound_symbols.items() if name in compound_key),
            wheel.compound_name[:1].upper() if wheel.compound_name else "?",
        )
        self.position_label.setText(f"{wheel.position}  {compound_symbol}")
        self.main_temp_label.setText(
            logic.temperature_text(
                temp_c,
                decimals=1,
            )
        )
        self.wear_label.setText(
            logic.wear_text(wheel)
        )
        self.wear_label.setStyleSheet(
            f"color: "
            f"{logic.wear_color(wheel)};"
        )
        self.brake_temp_label.setText(
            logic.temperature_text(
                wheel.brake_temp_c,
                decimals=0,
            )
        )
        self.pressure_label.setText(
            logic.pressure_text(
                wheel.pressure_kpa
            )
        )
        self.surface_label.setText(
            "L "
            + logic.temperature_text(
                wheel.surface_left_c,
                decimals=0,
            )
            + "  C "
            + logic.temperature_text(
                wheel.surface_center_c,
                decimals=0,
            )
            + "  R "
            + logic.temperature_text(
                wheel.surface_right_c,
                decimals=0,
            )
        )
        self.carcass_label.setText(
            "CAR "
            + logic.temperature_text(
                wheel.carcass_temp_c,
                decimals=0,
            )
        )
        self.optimal_label.setText(
            "OPT "
            + logic.temperature_text(
                wheel.optimal_temp_c,
                decimals=0,
            )
        )
        self.brake_pressure_label.setText(
            f"{wheel.brake_pressure * 100:.0f}%"
        )
        advanced = logic.advanced_text(
            wheel
        )
        self.advanced_label.setText(
            advanced
        )
        status = logic.status_text(
            wheel
        )
        self.status_label.setText(
            status
        )
        self.status_label.setVisible(
            bool(status)
        )

        # O fundo representa o estado térmico geral calculado pelo LMU/doX.
        # As temperaturas L/C/R continuam visíveis como números, mas não
        # devem esconder que um pneu Wet inteiro está superaquecido.
        main_thermal_color = logic.temperature_color(wheel, temp_c)
        zone_colors = [main_thermal_color] * 3
        brake_color = logic.brake_color(
            wheel.brake_temp_c
        )
        colors = config.get(
            "colors",
            {},
        )
        compound_borders = {
            "S": "#F4F4F4",
            "M": "#FFD32A",
            "H": "#E53935",
            "W": "#2196F3",
            "I": "#43A047",
        }
        border = compound_borders.get(
            compound_symbol,
            colors.get("tyre_border", "#B9E83B"),
        )
        radius = max(
            3,
            round(7 * self.scale),
        )
        brake_radius = max(
            3,
            round(6 * self.scale),
        )

        if wheel.detached:
            status_color = colors.get(
                "detached",
                "#6D1B1B",
            )
            zone_colors = [status_color] * 3
        elif wheel.flat:
            status_color = colors.get(
                "flat",
                "#7D2222",
            )
            zone_colors = [status_color] * 3

        left_color, center_color, right_color = zone_colors

        # Quando as três amostras possuem o mesmo estado, usar cor sólida.
        # Isso torna inequívoco o alerta de um Wet superaquecido; o gradiente
        # do Qt podia parecer apenas uma faixa decorativa em widgets pequenos.
        if len({left_color, center_color, right_color}) == 1:
            tyre_background = f"background-color: {left_color};"
        else:
            tyre_background = f"""
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 {left_color},
                    stop: 0.32 {left_color},
                    stop: 0.34 {center_color},
                    stop: 0.65 {center_color},
                    stop: 0.67 {right_color},
                    stop: 1 {right_color}
                );
            """

        self.tyre_frame.setStyleSheet(
            f"""
            QFrame#TyreFrame {{
                {tyre_background}
                border-radius: {radius}px;
                border: {max(1, round(2 * self.scale))}px solid {border};
            }}
            """
        )
        self.brake_frame.setStyleSheet(
            f"""
            QFrame#BrakeFrame {{
                background-color: {brake_color};
                border-radius: {brake_radius}px;
                border: none;
            }}
            """
        )


class TyresWidget(QWidget):
    geometry_changed = Signal(
        str,
        float,
        float,
        float,
        float,
    )
    selected = Signal(str)

    BASE_WIDTH = 390.0

    def __init__(
        self,
        widget_id: str,
        config: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.widget_id = widget_id
        self.config = config
        self.logic = TyresLogic(config)
        self.view_data = self.logic.preview()
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
            "Sector Flow Drive - Tyres"
        )
        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
            True,
        )
        self.setMinimumWidth(230)
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
            "TyresMainFrame"
        )
        self.main_layout = QVBoxLayout(
            self.main_frame
        )
        self.root_layout.addWidget(
            self.main_frame
        )

        self.compound_label = QLabel(
            "FRONT --  |  REAR --"
        )
        self.compound_label.setObjectName(
            "CompoundLabel"
        )
        self.compound_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.main_layout.addWidget(
            self.compound_label
        )

        self.front_row = QHBoxLayout()
        self.rear_row = QHBoxLayout()

        self.wheel_groups = [
            WheelGroup(
                0,
                is_left=True,
                is_front=True,
            ),
            WheelGroup(
                1,
                is_left=False,
                is_front=True,
            ),
            WheelGroup(
                2,
                is_left=True,
                is_front=False,
            ),
            WheelGroup(
                3,
                is_left=False,
                is_front=False,
            ),
        ]

        self.front_row.addWidget(
            self.wheel_groups[0],
            1,
        )
        self.front_row.addWidget(
            self.wheel_groups[1],
            1,
        )
        self.rear_row.addWidget(
            self.wheel_groups[2],
            1,
        )
        self.rear_row.addWidget(
            self.wheel_groups[3],
            1,
        )

        self.main_layout.addLayout(
            self.front_row
        )
        self.center_gap = QWidget()
        self.center_gap.setFixedHeight(
            14
        )
        self.main_layout.addWidget(
            self.center_gap
        )
        self.main_layout.addLayout(
            self.rear_row
        )

        self.global_warning = QLabel("")
        self.global_warning.setObjectName(
            "GlobalWarning"
        )
        self.global_warning.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.global_warning.hide()
        self.main_layout.addWidget(
            self.global_warning
        )

        self.apply_config()
        self._render()

    def apply_config(self) -> None:
        self.logic.update_config(
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
        self.compound_label.setVisible(
            bool(
                self.config.get(
                    "show_compound",
                    True,
                )
            )
        )

        for group in self.wheel_groups:
            group.apply_visibility(
                self.config
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
                        0.20,
                    )
                )
                * scale
            ),
        )
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
                    0.45,
                )
            )
        )

        self.resize(
            width,
            max(100, self.height()),
        )
        self.move(x, y)
        self._schedule_metrics()

    def update_telemetry(
        self,
        player: Any,
    ) -> None:
        if player is None:
            return

        self.view_data = (
            self.logic.build_view(
                player
            )
        )
        self._render()

    def _render(self) -> None:
        front = (
            self.view_data.front_compound
            or "--"
        )
        rear = (
            self.view_data.rear_compound
            or "--"
        )
        self.compound_label.setText(
            tr(
                "DIANTEIRO {front}  |  TRASEIRO {rear}",
                front=front,
                rear=rear,
            )
        )

        warnings: list[str] = []

        for index, group in enumerate(
            self.wheel_groups
        ):
            wheel = (
                self.view_data.wheels[index]
                if index
                < len(
                    self.view_data.wheels
                )
                else TyreWheelViewData(
                    index=index,
                )
            )
            group.render(
                wheel,
                self.logic,
                self.config,
            )
            status = self.logic.status_text(
                wheel
            )

            if status:
                warnings.append(
                    f"{wheel.position} {status}"
                )

        self.global_warning.setText(
            " | ".join(warnings)
        )
        self.global_warning.setVisible(
            bool(warnings)
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
                    2.2,
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
        self._responsive_scale = max(
            minimum,
            min(
                maximum,
                self.width()
                / self.BASE_WIDTH
                * internal,
            ),
        )
        s = self._responsive_scale
        margin = tyres_panel_margin(self.config, s)
        row_gap = max(
            3,
            round(6 * s),
        )

        self.main_layout.setContentsMargins(
            margin,
            margin,
            margin,
            margin,
        )
        self.main_layout.setSpacing(
            max(
                1,
                round(2 * s),
            )
        )
        self.front_row.setSpacing(
            row_gap
        )
        self.rear_row.setSpacing(
            row_gap
        )
        self.center_gap.setFixedHeight(
            max(
                4,
                round(14 * s),
            )
        )

        for group in self.wheel_groups:
            group.apply_visibility(
                self.config
            )
            group.apply_scale(
                s,
                self.config,
            )

        self._apply_style(s)
        self._render_without_reschedule()
        QTimer.singleShot(
            0,
            self._fit_content,
        )

    def _render_without_reschedule(
        self,
    ) -> None:
        for index, group in enumerate(
            self.wheel_groups
        ):
            if index < len(
                self.view_data.wheels
            ):
                group.render(
                    self.view_data.wheels[
                        index
                    ],
                    self.logic,
                    self.config,
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
            "rgba(15,15,15,240)",
        )
        text = colors.get(
            "text",
            "#FFFFFF",
        )
        muted = colors.get(
            "muted",
            "#AAAAAA",
        )
        border = colors.get(
            "border",
            "#2E3948",
        )
        warning = colors.get(
            "warning",
            "#FF5252",
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
        main_size = max(
            8,
            round(
                base_font * scale
            ),
        )
        wear_size = tyres_wear_font_size(
            self.config,
            base_font,
            scale,
        )
        detail_size = max(
            5,
            round(
                base_font
                * 0.55
                * scale
            ),
        )
        brake_size = max(
            6,
            round(
                base_font
                * 0.72
                * scale
            ),
        )
        radius = max(
            4,
            round(8 * scale),
        )
        border_width = max(
            1,
            round(1 * scale),
        )
        compound_padding = max(
            1,
            round(3 * scale),
        )

        main_frame_style = tyres_main_frame_style(
            self.config,
            background,
            radius,
            border_width,
            border,
        )

        self.setStyleSheet(
            f"""
            TyresWidget {{
                background: transparent;
                border: none;
                font-family: "{font_name}";
            }}

            QFrame#TyresMainFrame {{
                {main_frame_style}
            }}

            QLabel {{
                background: transparent;
                border: none;
                color: {text};
                font-family: "{font_name}";
            }}

            QLabel#CompoundLabel {{
                color: {muted};
                font-size: {wear_size}px;
                font-weight: 900;
                padding: {compound_padding}px;
            }}

            QLabel#WearLabel {{
                color: {muted};
                font-size: {wear_size}px;
                font-weight: 900;
            }}

            QLabel#PositionLabel {{
                color: rgba(255,255,255,180);
                font-size: {detail_size}px;
                font-weight: 900;
            }}

            QLabel#MainTempLabel {{
                color: {text};
                font-size: {main_size}px;
                font-weight: 900;
            }}

            QLabel#SurfaceLabel,
            QLabel#PressureLabel,
            QLabel#DetailLabel,
            QLabel#AdvancedLabel {{
                color: rgba(255,255,255,215);
                font-size: {detail_size}px;
                font-weight: bold;
            }}

            QLabel#BrakeTempLabel {{
                color: {text};
                font-size: {brake_size}px;
                font-weight: 900;
            }}

            QLabel#BrakePressureLabel {{
                color: rgba(255,255,255,210);
                font-size: {detail_size}px;
                font-weight: bold;
            }}

            QLabel#StatusLabel,
            QLabel#GlobalWarning {{
                color: {warning};
                font-size: {wear_size}px;
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
                self.logic.preview()
            )
            self.show()

        self.setCursor(
            Qt.CursorShape.SizeAllCursor
            if self.edit_mode
            else Qt.CursorShape.ArrowCursor
        )
        self._render()
        self.update()

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
        edit_color = QColor(
            self.config.get(
                "colors",
                {},
            ).get(
                "edit_border",
                "#9B5CFF",
            )
        )
        pen = QPen(
            edit_color,
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
            9,
            9,
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
            90,
            self.root_layout.sizeHint().height(),
        )

        if abs(
            self.height() - desired
        ) > 1:
            self.resize(
                self.width(),
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
