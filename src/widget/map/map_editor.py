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


class MapEditor(QDialog):
    config_changed = Signal(dict)
    restore_requested = Signal()

    def __init__(
        self,
        config: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.config = deepcopy(config)
        self.color_buttons: dict[
            str,
            QPushButton,
        ] = {}

        self.setWindowTitle(
            "Editar Mapa"
        )
        self.resize(
            620,
            840,
        )

        root = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        root.addWidget(scroll)

        content = QWidget()
        self.content_layout = QVBoxLayout(
            content
        )
        scroll.setWidget(content)

        self._build_display()
        self._build_mapping()
        self._build_sizes()
        self._build_appearance()

        actions = QHBoxLayout()
        rebuild = QPushButton(
            "Reconstruir mapa na próxima volta"
        )
        restore = QPushButton(
            "Restaurar padrão"
        )
        close = QPushButton(
            "Fechar"
        )
        rebuild.clicked.connect(
            self._request_rebuild
        )
        restore.clicked.connect(
            self.restore_requested.emit
        )
        close.clicked.connect(
            self.accept
        )
        actions.addWidget(rebuild)
        actions.addWidget(restore)
        actions.addStretch()
        actions.addWidget(close)
        root.addLayout(actions)

    def _build_display(self) -> None:
        group = QGroupBox(
            "Elementos do mapa"
        )
        form = QFormLayout(group)

        options = [
            (
                "show_background",
                "Fundo do widget:",
                True,
            ),
            (
                "show_header",
                "Nome e estado da pista:",
                True,
            ),
            (
                "show_map_background",
                "Preenchimento do circuito:",
                True,
            ),
            (
                "show_start_line",
                "Linha de chegada:",
                True,
            ),
            (
                "show_sector_lines",
                "Linhas de setor:",
                True,
            ),
            (
                "show_vehicle_standings",
                "Posição dentro dos carros:",
                True,
            ),
            (
                "enable_multi_class_styling",
                "Cores por categoria:",
                True,
            ),
            (
                "show_position_in_class",
                "Posição da categoria:",
                True,
            ),
            (
                "show_lap_difference_outline",
                "Contorno por diferença de volta:",
                True,
            ),
            (
                "show_only_same_class",
                "Mostrar somente mesma categoria:",
                False,
            ),
            (
                "lock_aspect_ratio",
                "Manter mapa quadrado:",
                True,
            ),
            (
                "flip_vertical",
                "Inverter eixo vertical:",
                True,
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

        lap_difference = QSpinBox()
        lap_difference.setRange(
            0,
            99,
        )
        lap_difference.setSpecialValueText(
            "Somente mesma volta"
        )
        lap_difference.setValue(
            int(
                self.config.get(
                    "maximum_visible_lap_difference",
                    99,
                )
            )
        )
        lap_difference.valueChanged.connect(
            lambda value:
            self._set(
                "maximum_visible_lap_difference",
                value,
            )
        )
        form.addRow(
            "Diferença máxima de voltas:",
            lap_difference,
        )

        self.content_layout.addWidget(
            group
        )

    def _build_mapping(self) -> None:
        group = QGroupBox(
            "Aprendizado e cache da pista"
        )
        form = QFormLayout(group)

        for key, label, default in (
            (
                "save_map_cache",
                "Salvar mapa automaticamente:",
                True,
            ),
            (
                "load_map_cache",
                "Carregar mapa salvo:",
                True,
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

        sample = QDoubleSpinBox()
        sample.setRange(
            2.0,
            100.0,
        )
        sample.setSingleStep(
            2.0
        )
        sample.setSuffix(" m")
        sample.setValue(
            float(
                self.config.get(
                    "mapping_sample_distance_m",
                    18.0,
                )
            )
        )
        sample.valueChanged.connect(
            lambda value:
            self._set(
                "mapping_sample_distance_m",
                value,
            )
        )

        minimum_points = QSpinBox()
        minimum_points.setRange(
            30,
            1000,
        )
        minimum_points.setValue(
            int(
                self.config.get(
                    "minimum_mapping_points",
                    120,
                )
            )
        )
        minimum_points.valueChanged.connect(
            lambda value:
            self._set(
                "minimum_mapping_points",
                value,
            )
        )

        coverage = QDoubleSpinBox()
        coverage.setRange(
            50.0,
            98.0,
        )
        coverage.setSuffix(" %")
        coverage.setValue(
            float(
                self.config.get(
                    "minimum_mapping_coverage",
                    0.82,
                )
            )
            * 100.0
        )
        coverage.valueChanged.connect(
            lambda value:
            self._set(
                "minimum_mapping_coverage",
                value / 100.0,
            )
        )

        lateral = QDoubleSpinBox()
        lateral.setRange(
            5.0,
            100.0,
        )
        lateral.setSuffix(" m")
        lateral.setValue(
            float(
                self.config.get(
                    "maximum_mapping_path_lateral_m",
                    35.0,
                )
            )
        )
        lateral.valueChanged.connect(
            lambda value:
            self._set(
                "maximum_mapping_path_lateral_m",
                value,
            )
        )

        orientation = QSpinBox()
        orientation.setRange(
            0,
            359,
        )
        orientation.setSuffix("°")
        orientation.setValue(
            int(
                self.config.get(
                    "display_orientation",
                    0,
                )
            )
        )
        orientation.valueChanged.connect(
            lambda value:
            self._set(
                "display_orientation",
                value,
            )
        )

        detail = QSpinBox()
        detail.setRange(
            0,
            4,
        )
        detail.setValue(
            int(
                self.config.get(
                    "display_detail_level",
                    1,
                )
            )
        )
        detail.valueChanged.connect(
            lambda value:
            self._set(
                "display_detail_level",
                value,
            )
        )

        form.addRow(
            "Amostra de coordenadas:",
            sample,
        )
        form.addRow(
            "Mínimo de pontos:",
            minimum_points,
        )
        form.addRow(
            "Cobertura mínima:",
            coverage,
        )
        form.addRow(
            "Lateral máxima para mapear:",
            lateral,
        )
        form.addRow(
            "Orientação:",
            orientation,
        )
        form.addRow(
            "Detalhe do traçado:",
            detail,
        )

        self.content_layout.addWidget(
            group
        )

    def _build_sizes(self) -> None:
        group = QGroupBox(
            "Tamanhos e redimensionamento"
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
                "",
            ),
            (
                "responsive_min_scale",
                "Escala mínima:",
                0.25,
                1.00,
                0.05,
                0.48,
                "",
            ),
            (
                "responsive_max_scale",
                "Escala máxima:",
                1.00,
                3.00,
                0.10,
                2.20,
                "",
            ),
            (
                "area_margin",
                "Margem do mapa:",
                8.0,
                80.0,
                2.0,
                24.0,
                " px",
            ),
            (
                "map_width",
                "Espessura do traçado:",
                1.0,
                15.0,
                0.5,
                3.0,
                " px",
            ),
            (
                "map_outline_width",
                "Contorno do traçado:",
                0.0,
                20.0,
                0.5,
                5.0,
                " px",
            ),
            (
                "vehicle_size",
                "Tamanho dos carros:",
                7.0,
                40.0,
                1.0,
                18.0,
                " px",
            ),
            (
                "vehicle_outline_width",
                "Contorno dos carros:",
                0.0,
                8.0,
                0.5,
                2.0,
                " px",
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
            spin.setSuffix(suffix)
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
            32,
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
                    0.96,
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

        map_opacity = QDoubleSpinBox()
        map_opacity.setRange(
            0.0,
            1.0,
        )
        map_opacity.setSingleStep(
            0.05
        )
        map_opacity.setValue(
            float(
                self.config.get(
                    "map_background_opacity",
                    0.58,
                )
            )
        )
        map_opacity.valueChanged.connect(
            lambda value:
            self._set(
                "map_background_opacity",
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
            "Opacidade do widget:",
            opacity,
        )
        form.addRow(
            "Opacidade interna da pista:",
            map_opacity,
        )

        labels = {
            "background": "Fundo",
            "border": "Borda",
            "text": "Texto",
            "map": "Traçado",
            "map_outline": "Contorno do traçado",
            "map_background": "Área interna",
            "start_line": "Linha de chegada",
            "sector_line": "Linhas de setor",
            "vehicle_player": "Jogador",
            "vehicle_leader": "Líder",
            "vehicle_in_pit": "Carro nos boxes",
            "vehicle_yellow": "Carro em amarela",
            "vehicle_same_lap": "Mesma volta",
            "vehicle_laps_ahead": "Voltas à frente",
            "vehicle_laps_behind": "Voltas atrás",
            "vehicle_outline": "Contorno normal",
            "vehicle_outline_player": "Contorno do jogador",
            "vehicle_outline_laps_ahead": "Contorno à frente",
            "vehicle_outline_laps_behind": "Contorno atrás",
            "vehicle_text": "Texto dos carros",
            "vehicle_text_player": "Texto do jogador",
            "status_ready": "Status pronto",
            "status_recording": "Status gravando",
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

    def _request_rebuild(self) -> None:
        self.config["rebuild_request"] = (
            int(
                self.config.get(
                    "rebuild_request",
                    0,
                )
                or 0
            )
            + 1
        )
        self._emit()

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
        self.config["colors"][key] = value
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
            deepcopy(self.config)
        )
