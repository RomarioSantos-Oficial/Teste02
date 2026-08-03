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

from copy import deepcopy
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtGui import (
    QColor,
    QFontDatabase,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class BatteryEditor(QDialog):
    config_changed = Signal(dict)
    restore_requested = Signal()

    def __init__(
        self,
        config: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.config = deepcopy(
            config
        )
        self.color_buttons: dict[
            str,
            QPushButton,
        ] = {}

        self.setWindowTitle(
            "Editar Battery"
        )
        self.resize(610, 800)

        root = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        root.addWidget(scroll)

        content = QWidget()
        self.content_layout = QVBoxLayout(
            content
        )
        scroll.setWidget(content)

        self._build_data()
        self._build_tracking()
        self._build_responsive()
        self._build_appearance()

        actions = QHBoxLayout()
        restore = QPushButton(
            "Restaurar padrão"
        )
        close = QPushButton(
            "Fechar"
        )
        restore.clicked.connect(
            self.restore_requested.emit
        )
        close.clicked.connect(
            self.accept
        )
        actions.addWidget(restore)
        actions.addStretch()
        actions.addWidget(close)
        root.addLayout(actions)

    def _build_data(self) -> None:
        group = QGroupBox(
            "Informações exibidas"
        )
        form = QFormLayout(group)

        options = [
            (
                "hide_when_unavailable",
                "Ocultar em carro sem híbrido:",
                True,
            ),
            (
                "always_show",
                "Forçar exibição:",
                False,
            ),
            (
                "show_current_lap_use",
                "Consumo da volta atual:",
                True,
            ),
            (
                "show_last_lap_use",
                "Consumo da última volta:",
                True,
            ),
            (
                "show_delta_vs_last",
                "Diferença para última volta:",
                True,
            ),
            (
                "show_comparison_bar",
                "Barra comparativa:",
                True,
            ),
            (
                "show_drain",
                "Descarga acumulada:",
                True,
            ),
            (
                "show_regen",
                "Regeneração acumulada:",
                True,
            ),
            (
                "show_projected_use",
                "Estimativa por volta:",
                True,
            ),
            (
                "show_laps_remaining",
                "Voltas restantes estimadas:",
                True,
            ),
            (
                "show_motor_power",
                "Potência do motor elétrico:",
                True,
            ),
            (
                "show_regen_kw",
                "Regeneração em kW:",
                True,
            ),
            (
                "show_motor_temperature",
                "Temperatura do motor:",
                True,
            ),
            (
                "show_virtual_energy",
                "Virtual Energy:",
                False,
            ),
            (
                "show_lap_progress",
                "Progresso da volta:",
                False,
            ),
        ]

        for key, label, default in options:
            check = QCheckBox()
            check.setChecked(
                bool(
                    self.config.get(
                        key,
                        default,
                    )
                )
            )
            check.toggled.connect(
                lambda value, current=key:
                self._set(
                    current,
                    value,
                )
            )
            form.addRow(
                label,
                check,
            )

        source = QComboBox()
        source.addItem(
            "Automático",
            "auto",
        )
        source.addItem(
            "Battery Charge Fraction",
            "battery_fraction",
        )
        source.addItem(
            "State of Charge",
            "state_of_charge",
        )
        source.addItem(
            "Virtual Energy",
            "virtual_energy",
        )
        index = source.findData(
            self.config.get(
                "charge_source",
                "auto",
            )
        )
        source.setCurrentIndex(
            max(0, index)
        )
        source.currentIndexChanged.connect(
            lambda:
            self._set(
                "charge_source",
                source.currentData(),
            )
        )
        form.addRow(
            "Fonte da carga:",
            source,
        )

        self.content_layout.addWidget(
            group
        )

    def _build_tracking(self) -> None:
        group = QGroupBox(
            "Comparação entre voltas"
        )
        form = QFormLayout(group)

        settings = [
            (
                "sample_distance_m",
                "Amostra a cada:",
                5.0,
                250.0,
                5.0,
                25.0,
                " m",
            ),
            (
                "comparison_max_delta_pct",
                "Escala máxima da barra:",
                0.1,
                10.0,
                0.1,
                2.0,
                " %",
            ),
            (
                "projection_min_progress",
                "Projeção após:",
                0.05,
                0.90,
                0.05,
                0.15,
                "",
            ),
            (
                "maximum_valid_step_pct",
                "Mudança máxima por leitura:",
                0.1,
                20.0,
                0.5,
                5.0,
                " %",
            ),
        ]

        for (
            key,
            label,
            minimum,
            maximum,
            step,
            default,
            suffix,
        ) in settings:
            spin = QDoubleSpinBox()
            spin.setRange(
                minimum,
                maximum,
            )
            spin.setSingleStep(
                step
            )
            spin.setValue(
                float(
                    self.config.get(
                        key,
                        default,
                    )
                )
            )
            spin.setSuffix(
                suffix
            )
            spin.valueChanged.connect(
                lambda value, current=key:
                self._set(
                    current,
                    value,
                )
            )
            form.addRow(
                label,
                spin,
            )

        ignore_pit = QCheckBox()
        ignore_pit.setChecked(
            bool(
                self.config.get(
                    "ignore_pit_charge_changes",
                    True,
                )
            )
        )
        ignore_pit.toggled.connect(
            lambda value:
            self._set(
                "ignore_pit_charge_changes",
                value,
            )
        )
        form.addRow(
            "Ignorar mudanças no box:",
            ignore_pit,
        )

        low = QDoubleSpinBox()
        low.setRange(0.0, 50.0)
        low.setSuffix(" %")
        low.setValue(
            float(
                self.config.get(
                    "low_battery_threshold",
                    10.0,
                )
            )
        )
        low.valueChanged.connect(
            lambda value:
            self._set(
                "low_battery_threshold",
                value,
            )
        )

        high = QDoubleSpinBox()
        high.setRange(50.0, 100.0)
        high.setSuffix(" %")
        high.setValue(
            float(
                self.config.get(
                    "high_battery_threshold",
                    95.0,
                )
            )
        )
        high.valueChanged.connect(
            lambda value:
            self._set(
                "high_battery_threshold",
                value,
            )
        )

        form.addRow(
            "Alerta de bateria baixa:",
            low,
        )
        form.addRow(
            "Bateria alta:",
            high,
        )

        self.content_layout.addWidget(
            group
        )

    def _build_responsive(self) -> None:
        group = QGroupBox(
            "Redimensionamento"
        )
        form = QFormLayout(group)

        for (
            key,
            label,
            minimum,
            maximum,
            step,
            default,
        ) in (
            (
                "internal_scale",
                "Escala interna:",
                0.50,
                2.00,
                0.05,
                1.0,
            ),
            (
                "responsive_min_scale",
                "Escala mínima:",
                0.25,
                1.00,
                0.05,
                0.55,
            ),
            (
                "responsive_max_scale",
                "Escala máxima:",
                1.00,
                3.00,
                0.10,
                2.20,
            ),
        ):
            spin = QDoubleSpinBox()
            spin.setRange(
                minimum,
                maximum,
            )
            spin.setSingleStep(
                step
            )
            spin.setValue(
                float(
                    self.config.get(
                        key,
                        default,
                    )
                )
            )
            spin.valueChanged.connect(
                lambda value, current=key:
                self._set(
                    current,
                    value,
                )
            )
            form.addRow(
                label,
                spin,
            )

        gauge_width = QSpinBox()
        gauge_width.setRange(35, 130)
        gauge_width.setValue(
            int(
                self.config.get(
                    "battery_base_width",
                    62,
                )
            )
        )
        gauge_width.valueChanged.connect(
            lambda value:
            self._set(
                "battery_base_width",
                value,
            )
        )

        gauge_height = QSpinBox()
        gauge_height.setRange(
            80,
            280,
        )
        gauge_height.setValue(
            int(
                self.config.get(
                    "battery_base_height",
                    154,
                )
            )
        )
        gauge_height.valueChanged.connect(
            lambda value:
            self._set(
                "battery_base_height",
                value,
            )
        )

        form.addRow(
            "Largura base da bateria:",
            gauge_width,
        )
        form.addRow(
            "Altura base da bateria:",
            gauge_height,
        )
        self.content_layout.addWidget(
            group
        )

    def _build_appearance(self) -> None:
        group = QGroupBox(
            "Aparência"
        )
        form = QFormLayout(group)

        font_name = QComboBox()
        font_name.addItems(
            QFontDatabase.families()
        )
        font_name.setCurrentText(
            str(
                self.config.get(
                    "font_name",
                    "Arial",
                )
            )
        )
        font_name.currentTextChanged.connect(
            lambda value:
            self._set(
                "font_name",
                value,
            )
        )

        font_size = QSpinBox()
        font_size.setRange(
            8,
            36,
        )
        font_size.setValue(
            int(
                self.config.get(
                    "font_size",
                    14,
                )
            )
        )
        font_size.valueChanged.connect(
            lambda value:
            self._set(
                "font_size",
                value,
            )
        )

        opacity = QDoubleSpinBox()
        opacity.setRange(
            0.10,
            1.00,
        )
        opacity.setSingleStep(
            0.05
        )
        opacity.setValue(
            float(
                self.config.get(
                    "opacity",
                    0.98,
                )
            )
        )
        opacity.valueChanged.connect(
            lambda value:
            self._set(
                "opacity",
                value,
            )
        )

        form.addRow(
            "Fonte:",
            font_name,
        )
        form.addRow(
            "Fonte base:",
            font_size,
        )
        form.addRow(
            "Opacidade:",
            opacity,
        )

        labels = {
            "background": "Fundo",
            "panel": "Painéis",
            "border": "Borda",
            "text": "Texto",
            "muted": "Texto secundário",
            "normal": "Carga normal",
            "high": "Carga alta",
            "low": "Carga baixa",
            "regen": "Regeneração",
            "better": "Menos consumo",
            "worse": "Mais consumo",
            "mode_boost": "Modo boost",
            "mode_regen": "Modo regeneração",
            "mode_idle": "Modo inativo",
            "bar_background": "Fundo da barra",
            "bar_center": "Centro da barra",
            "gauge_border": "Contorno da bateria",
            "gauge_terminal": "Terminal da bateria",
            "edit_border": "Borda de edição",
        }

        for key, label in labels.items():
            button = QPushButton(
                self.config
                .setdefault(
                    "colors",
                    {},
                )
                .get(
                    key,
                    "#FFFFFF",
                )
            )
            button.clicked.connect(
                lambda checked=False, current=key:
                self._choose_color(
                    current
                )
            )
            self.color_buttons[key] = button
            form.addRow(
                label + ":",
                button,
            )

        self.content_layout.addWidget(
            group
        )
        self.content_layout.addStretch()

    def _choose_color(
        self,
        key: str,
    ) -> None:
        current = QColor(
            self.config
            .setdefault(
                "colors",
                {},
            )
            .get(
                key,
                "#FFFFFF",
            )
        )
        selected = QColorDialog.getColor(
            current,
            self,
        )

        if not selected.isValid():
            return

        value = selected.name(
            QColor.NameFormat.HexRgb
        )
        self.config["colors"][key] = (
            value
        )
        self.color_buttons[key].setText(
            value
        )
        self._emit()

    def _set(
        self,
        key: str,
        value: Any,
    ) -> None:
        self.config[key] = value
        self._emit()

    def _emit(self) -> None:
        self.config_changed.emit(
            deepcopy(
                self.config
            )
        )
