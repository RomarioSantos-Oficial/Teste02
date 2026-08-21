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
    QFileDialog,
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


class WeatherEditor(QDialog):
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
            "Editar Weather"
        )
        self.resize(580, 760)

        root = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        root.addWidget(scroll)

        content = QWidget()
        self.content_layout = QVBoxLayout(
            content
        )
        scroll.setWidget(content)

        self._build_content()
        self._build_forecast()
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

    def _build_content(self) -> None:
        group = QGroupBox(
            "Conteúdo em tempo real"
        )
        form = QFormLayout(group)

        for key, label, default in (
            (
                "show_track_temperature",
                "Temperatura atual da pista:",
                True,
            ),
            (
                "show_air_temperature",
                "Temperatura atual do ar:",
                True,
            ),
            (
                "show_forecast",
                "Linha do tempo:",
                True,
            ),
            (
                "show_wet_status",
                "Aviso de pista molhada:",
                True,
            ),
            (
                "show_rain_indicator",
                "Indicador de chuva:",
                True,
            ),
            (
                "show_wet_indicator",
                "Indicador de pista molhada:",
                True,
            ),
            (
                "show_wind",
                "Velocidade do vento:",
                False,
            ),
            (
                "show_forecast_rain",
                "Chuva nos blocos futuros:",
                False,
            ),
        ):
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

        unit = QComboBox()
        unit.addItem(
            "Celsius",
            "C",
        )
        unit.addItem(
            "Fahrenheit",
            "F",
        )
        index = unit.findData(
            str(
                self.config.get(
                    "temperature_unit",
                    "C",
                )
            ).upper()
        )
        unit.setCurrentIndex(
            max(0, index)
        )
        unit.currentIndexChanged.connect(
            lambda:
            self._set(
                "temperature_unit",
                unit.currentData(),
            )
        )

        rain_threshold = QDoubleSpinBox()
        rain_threshold.setRange(
            0.0,
            100.0,
        )
        rain_threshold.setSuffix("%")
        rain_threshold.setValue(
            float(
                self.config.get(
                    "rain_alert_threshold",
                    0.01,
                )
            )
            * 100
        )
        rain_threshold.valueChanged.connect(
            lambda value:
            self._set(
                "rain_alert_threshold",
                value / 100.0,
            )
        )

        wet_threshold = QDoubleSpinBox()
        wet_threshold.setRange(
            0.0,
            100.0,
        )
        wet_threshold.setSuffix("%")
        wet_threshold.setValue(
            float(
                self.config.get(
                    "wet_alert_threshold",
                    0.02,
                )
            )
            * 100
        )
        wet_threshold.valueChanged.connect(
            lambda value:
            self._set(
                "wet_alert_threshold",
                value / 100.0,
            )
        )

        icon_directory = QLineEdit(
            str(
                self.config.get(
                    "icon_directory",
                    "images/tempo",
                )
            )
        )
        icon_directory.editingFinished.connect(
            lambda:
            self._set(
                "icon_directory",
                icon_directory.text().strip(),
            )
        )

        form.addRow(
            "Unidade:",
            unit,
        )
        form.addRow(
            "Mostrar chuva a partir de:",
            rain_threshold,
        )
        form.addRow(
            "Mostrar pista molhada a partir de:",
            wet_threshold,
        )
        form.addRow(
            "Pasta de ícones:",
            icon_directory,
        )
        for key, label, default in (
            ("rain_indicator_icon", "Imagem da chuva:", "images/tempo/gotas.png"),
            ("wet_indicator_icon", "Imagem da pista molhada:", "images/tempo/Pista_molhada.png"),
        ):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            path_edit = QLineEdit(str(self.config.get(key, default)))
            path_edit.editingFinished.connect(
                lambda current=key, edit=path_edit: self._set(
                    current, edit.text().strip()
                )
            )
            browse = QPushButton("Escolher...")
            browse.clicked.connect(
                lambda _=False, current=key, edit=path_edit: self._choose_icon(
                    current, edit
                )
            )
            row_layout.addWidget(path_edit, 1)
            row_layout.addWidget(browse)
            form.addRow(label, row)

        self.content_layout.addWidget(
            group
        )

    def _build_forecast(self) -> None:
        group = QGroupBox(
            "Linha do tempo preditiva"
        )
        form = QFormLayout(group)

        count = QSpinBox()
        count.setRange(1, 5)
        count.setValue(
            int(
                self.config.get(
                    "forecast_count",
                    5,
                )
            )
        )
        count.valueChanged.connect(
            lambda value:
            self._set(
                "forecast_count",
                value,
            )
        )

        interval = QSpinBox()
        interval.setRange(1, 30)
        interval.setSuffix(" min")
        interval.setValue(
            int(
                self.config.get(
                    "forecast_interval_minutes",
                    5,
                )
            )
        )
        interval.valueChanged.connect(
            lambda value:
            self._set(
                "forecast_interval_minutes",
                value,
            )
        )

        sampling = QDoubleSpinBox()
        sampling.setRange(
            0.25,
            10.0,
        )
        sampling.setSingleStep(
            0.25
        )
        sampling.setSuffix(" s")
        sampling.setValue(
            float(
                self.config.get(
                    "sample_interval_seconds",
                    2.0,
                )
            )
        )
        sampling.valueChanged.connect(
            lambda value:
            self._set(
                "sample_interval_seconds",
                value,
            )
        )

        form.addRow(
            "Quantidade de blocos:",
            count,
        )
        form.addRow(
            "Intervalo:",
            interval,
        )
        form.addRow(
            "Amostragem real:",
            sampling,
        )

        self.content_layout.addWidget(
            group
        )

    def _build_responsive(self) -> None:
        group = QGroupBox(
            "Redimensionamento"
        )
        form = QFormLayout(group)

        internal = QDoubleSpinBox()
        internal.setRange(
            0.50,
            2.00,
        )
        internal.setSingleStep(
            0.05
        )
        internal.setValue(
            float(
                self.config.get(
                    "internal_scale",
                    1.0,
                )
            )
        )
        internal.valueChanged.connect(
            lambda value:
            self._set(
                "internal_scale",
                value,
            )
        )

        minimum = QDoubleSpinBox()
        minimum.setRange(
            0.25,
            1.00,
        )
        minimum.setSingleStep(
            0.05
        )
        minimum.setValue(
            float(
                self.config.get(
                    "responsive_min_scale",
                    0.48,
                )
            )
        )
        minimum.valueChanged.connect(
            lambda value:
            self._set(
                "responsive_min_scale",
                value,
            )
        )

        maximum = QDoubleSpinBox()
        maximum.setRange(
            1.0,
            3.0,
        )
        maximum.setSingleStep(
            0.1
        )
        maximum.setValue(
            float(
                self.config.get(
                    "responsive_max_scale",
                    2.0,
                )
            )
        )
        maximum.valueChanged.connect(
            lambda value:
            self._set(
                "responsive_max_scale",
                value,
            )
        )

        icon_size = QSpinBox()
        icon_size.setRange(
            16,
            80,
        )
        icon_size.setValue(
            int(
                self.config.get(
                    "icon_size",
                    30,
                )
            )
        )
        icon_size.valueChanged.connect(
            lambda value:
            self._set(
                "icon_size",
                value,
            )
        )

        form.addRow(
            "Escala interna:",
            internal,
        )
        form.addRow(
            "Escala mínima:",
            minimum,
        )
        form.addRow(
            "Escala máxima:",
            maximum,
        )
        form.addRow(
            "Tamanho base dos ícones:",
            icon_size,
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
            40,
        )
        font_size.setValue(
            int(
                self.config.get(
                    "font_size",
                    16,
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
            "background": "Fundo dos blocos",
            "panel": "Fundo das temperaturas",
            "track_temp": "Temperatura da pista",
            "air_temp": "Temperatura do ar",
            "muted": "Texto dos minutos",
            "forecast_text": "Temperatura futura",
            "wet_background": "Fundo pista molhada",
            "wet_text": "Texto pista molhada",
            "border": "Bordas",
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
            self.color_buttons[key] = (
                button
            )
            form.addRow(
                label + ":",
                button,
            )

        self.content_layout.addWidget(
            group
        )
        self.content_layout.addStretch()

    def _choose_icon(self, key: str, edit: QLineEdit) -> None:
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "Escolher imagem",
            edit.text().strip(),
            "Imagens (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if not selected:
            return
        edit.setText(selected)
        self._set(key, selected)

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
