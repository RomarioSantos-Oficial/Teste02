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
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class TyresEditor(QDialog):
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
            "Editar Tyres"
        )
        self.resize(610, 820)

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
        self._build_gte_temperature()
        self._build_units()
        self._build_thresholds()
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
                "show_compound",
                "Composto dianteiro/traseiro:",
                True,
            ),
            (
                "show_position_labels",
                "Identificação FL/FR/RL/RR:",
                True,
            ),
            (
                "show_pressure",
                "Pressão dos pneus:",
                True,
            ),
            (
                "show_surface_temperatures",
                "Temperaturas L/C/R:",
                True,
            ),
            (
                "show_carcass_temperature",
                "Temperatura da carcaça:",
                False,
            ),
            (
                "show_optimal_temperature",
                "Temperatura ótima do jogo:",
                False,
            ),
            (
                "show_brake_pressure",
                "Pressão dos freios:",
                False,
            ),
            (
                "show_tire_load",
                "Carga do pneu:",
                False,
            ),
            (
                "show_grip_fraction",
                "Fração de deslizamento:",
                False,
            ),
            (
                "show_camber",
                "Cambagem:",
                False,
            ),
            (
                "show_toe",
                "Convergência/toe:",
                False,
            ),
            (
                "show_deflection",
                "Deflexão do pneu:",
                False,
            ),
            (
                "show_value_prefixes",
                "Prefixos nos valores:",
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
            "Jogo/MFD - carcaça + camada interna",
            "lmu_weighted",
        )
        source.addItem(
            "Camada interna — média",
            "inner_average",
        )
        source.addItem(
            "Camada interna — centro",
            "inner_center",
        )
        source.addItem(
            "Superfície — média",
            "surface_average",
        )
        source.addItem(
            "Superfície — centro",
            "surface_center",
        )
        source.addItem(
            "Carcaça",
            "carcass",
        )
        index = source.findData(
            self.config.get(
                "temperature_source",
                "lmu_weighted",
            )
        )
        source.setCurrentIndex(
            max(0, index)
        )
        source.currentIndexChanged.connect(
            lambda:
            self._set(
                "temperature_source",
                source.currentData(),
            )
        )

        wear = QComboBox()
        wear.addItem(
            "Vida restante — 100% novo",
            "remaining",
        )
        wear.addItem(
            "Desgaste usado — 0% novo",
            "used",
        )
        index = wear.findData(
            self.config.get(
                "wear_display",
                "remaining",
            )
        )
        wear.setCurrentIndex(
            max(0, index)
        )
        wear.currentIndexChanged.connect(
            lambda:
            self._set(
                "wear_display",
                wear.currentData(),
            )
        )

        form.addRow(
            "Temperatura principal:",
            source,
        )
        form.addRow(
            "Exibição do desgaste:",
            wear,
        )
        self.content_layout.addWidget(
            group
        )

    def _build_gte_temperature(self) -> None:
        group = QGroupBox("Temperatura especial — GTE")
        form = QFormLayout(group)

        enabled = QCheckBox()
        enabled.setChecked(bool(self.config.get("gte_temperature_mode", True)))
        enabled.toggled.connect(
            lambda value: self._set("gte_temperature_mode", value)
        )

        source = QComboBox()
        source.addItem("Carcaça (igual ao painel do jogo)", "carcass")
        source.addItem("Camada interna — média", "inner_average")
        source.addItem("Camada interna — centro", "inner_center")
        source.addItem("Superfície — média", "surface_average")
        source.addItem("Superfície — centro", "surface_center")
        source.addItem("Média atual do overlay", "lmu_weighted")
        index = source.findData(
            self.config.get("gte_temperature_source", "carcass")
        )
        source.setCurrentIndex(max(0, index))
        source.currentIndexChanged.connect(
            lambda: self._set("gte_temperature_source", source.currentData())
        )

        offset = QDoubleSpinBox()
        offset.setRange(-40.0, 40.0)
        offset.setDecimals(1)
        offset.setSingleStep(0.5)
        offset.setSuffix(" °C")
        offset.setValue(float(self.config.get("gte_temperature_offset_c", 0.0)))
        offset.valueChanged.connect(
            lambda value: self._set("gte_temperature_offset_c", value)
        )

        keywords = QLineEdit(
            str(self.config.get("gte_detection_keywords", "gte,lmgt3,gt3"))
        )
        keywords.setPlaceholderText("gte,lmgt3,gt3")
        keywords.editingFinished.connect(
            lambda: self._set("gte_detection_keywords", keywords.text())
        )

        form.addRow("Ativar somente nos GTE/GT3:", enabled)
        form.addRow("Leitura principal:", source)
        form.addRow("Ajuste fino:", offset)
        form.addRow("Identificação do carro:", keywords)
        self.content_layout.addWidget(group)

    def _build_units(self) -> None:
        group = QGroupBox(
            "Unidades"
        )
        form = QFormLayout(group)

        temperature = QComboBox()
        temperature.addItem(
            "Celsius",
            "C",
        )
        temperature.addItem(
            "Fahrenheit",
            "F",
        )
        index = temperature.findData(
            str(
                self.config.get(
                    "temperature_unit",
                    "C",
                )
            ).upper()
        )
        temperature.setCurrentIndex(
            max(0, index)
        )
        temperature.currentIndexChanged.connect(
            lambda:
            self._set(
                "temperature_unit",
                temperature.currentData(),
            )
        )

        pressure = QComboBox()
        pressure.addItem(
            "kPa",
            "kpa",
        )
        pressure.addItem(
            "PSI",
            "psi",
        )
        pressure.addItem(
            "bar",
            "bar",
        )
        index = pressure.findData(
            str(
                self.config.get(
                    "pressure_unit",
                    "kpa",
                )
            ).lower()
        )
        pressure.setCurrentIndex(
            max(0, index)
        )
        pressure.currentIndexChanged.connect(
            lambda:
            self._set(
                "pressure_unit",
                pressure.currentData(),
            )
        )

        form.addRow(
            "Temperatura:",
            temperature,
        )
        form.addRow(
            "Pressão:",
            pressure,
        )
        self.content_layout.addWidget(
            group
        )

    def _build_thresholds(self) -> None:
        group = QGroupBox(
            "Faixas de temperatura"
        )
        form = QFormLayout(group)

        mode = QComboBox()
        mode.addItem(
            "Temperatura ótima fornecida pelo LMU",
            "optimal",
        )
        mode.addItem(
            "Limites fixos da referência",
            "fixed",
        )
        index = mode.findData(
            self.config.get(
                "temperature_color_mode",
                "optimal",
            )
        )
        mode.setCurrentIndex(
            max(0, index)
        )
        mode.currentIndexChanged.connect(
            lambda:
            self._set(
                "temperature_color_mode",
                mode.currentData(),
            )
        )
        form.addRow(
            "Cores do pneu:",
            mode,
        )

        settings = [
            (
                "tyre_cold_limit_c",
                "Pneu: fim do azul:",
                0.0,
                150.0,
                70.0,
            ),
            (
                "tyre_optimal_limit_c",
                "Pneu: fim do verde:",
                0.0,
                180.0,
                90.0,
            ),
            (
                "tyre_warm_limit_c",
                "Pneu: fim do amarelo:",
                0.0,
                220.0,
                100.0,
            ),
            (
                "brake_cool_limit_c",
                "Freio: fim do frio:",
                0.0,
                1200.0,
                200.0,
            ),
            (
                "brake_optimal_limit_c",
                "Freio: fim do verde:",
                0.0,
                1500.0,
                500.0,
            ),
            (
                "brake_hot_limit_c",
                "Freio: fim do laranja:",
                0.0,
                1800.0,
                700.0,
            ),
        ]

        for (
            key,
            label,
            minimum,
            maximum,
            default,
        ) in settings:
            spin = QDoubleSpinBox()
            spin.setRange(
                minimum,
                maximum,
            )
            spin.setSingleStep(
                5.0
            )
            spin.setSuffix(" °C")
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

        self.content_layout.addWidget(
            group
        )

    def _build_responsive(self) -> None:
        group = QGroupBox(
            "Redimensionamento"
        )
        form = QFormLayout(group)

        settings = [
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
        ]

        for (
            key,
            label,
            minimum,
            maximum,
            step,
            default,
        ) in settings:
            spin = QDoubleSpinBox()
            spin.setRange(
                minimum,
                maximum,
            )
            spin.setSingleStep(step)
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

        tyre_width = QSpinBox()
        tyre_width.setRange(45, 140)
        tyre_width.setValue(
            int(
                self.config.get(
                    "tyre_base_width",
                    70,
                )
            )
        )
        tyre_width.valueChanged.connect(
            lambda value:
            self._set(
                "tyre_base_width",
                value,
            )
        )

        tyre_height = QSpinBox()
        tyre_height.setRange(60, 190)
        tyre_height.setValue(
            int(
                self.config.get(
                    "tyre_base_height",
                    105,
                )
            )
        )
        tyre_height.valueChanged.connect(
            lambda value:
            self._set(
                "tyre_base_height",
                value,
            )
        )

        form.addRow(
            "Largura base do pneu:",
            tyre_width,
        )
        form.addRow(
            "Altura base do pneu:",
            tyre_height,
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
        font_size.setRange(8, 36)
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
        opacity.setRange(0.10, 1.00)
        opacity.setSingleStep(0.05)
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
            "border": "Borda",
            "text": "Texto",
            "muted": "Texto secundário",
            "tyre_cold": "Pneu frio",
            "tyre_optimal": "Pneu ideal",
            "tyre_warm": "Pneu quente",
            "tyre_hot": "Pneu crítico",
            "brake_cold": "Freio frio",
            "brake_optimal": "Freio ideal",
            "brake_hot": "Freio quente",
            "brake_critical": "Freio crítico",
            "wear_new": "Desgaste novo",
            "wear_good": "Desgaste bom",
            "wear_warning": "Desgaste atenção",
            "wear_critical": "Desgaste crítico",
            "flat": "Pneu furado",
            "detached": "Roda solta",
            "warning": "Avisos",
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
