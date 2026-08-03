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

from copy import deepcopy
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QFontDatabase
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDoubleSpinBox, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QSpinBox, QVBoxLayout, QWidget,
)


class StandingsEditor(QDialog):
    config_changed = Signal(dict)
    restore_requested = Signal()

    def __init__(self, config: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = deepcopy(config)
        self.color_buttons: dict[str, QPushButton] = {}
        self.setWindowTitle("Editar Standings Hybrid")
        self.resize(650, 820)
        root = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        root.addWidget(scroll)
        content = QWidget()
        self.layout_content = QVBoxLayout(content)
        scroll.setWidget(content)
        self._build_rules()
        self._build_columns()
        self._build_dimensions()
        self._build_local_source()
        self._build_colors()
        actions = QHBoxLayout()
        restore = QPushButton("Restaurar padrão")
        close = QPushButton("Fechar")
        restore.clicked.connect(self.restore_requested.emit)
        close.clicked.connect(self.accept)
        actions.addWidget(restore)
        actions.addStretch()
        actions.addWidget(close)
        root.addLayout(actions)

    def _build_rules(self) -> None:
        group = QGroupBox("Categorias e regras fixas")
        form = QFormLayout(group)
        text = QLabel(
            "1 categoria: até 10 carros, top 3 + jogador e carros ao redor.\n"
            "2 ou 3 categorias: top 3 das outras categorias e até 8 carros da categoria do jogador.\n"
            "A categoria do jogador aparece por último. Máximo de 3 categorias."
        )
        text.setWordWrap(True)
        form.addRow(text)
        for key, label, default in (
            ("show_global_header", "Cabeçalho global:", True),
            ("show_column_legend", "Legenda das colunas:", False),
            ("position_change_in_class", "Mudança na categoria:", True),
        ):
            check = QCheckBox()
            check.setChecked(bool(self.config.get(key, default)))
            check.toggled.connect(lambda value, current=key: self._set(current, value))
            form.addRow(label, check)
        header_label = QLabel("Informações do cabeçalho")
        header_label.setStyleSheet("font-weight: 700; margin-top: 8px;")
        form.addRow(header_label)
        for key, label in (
            ("show_header_session_type", "Tipo da sessão:"),
            ("show_header_session_time", "Tempo da sessão:"),
            ("show_header_server_time", "Horário do jogo:"),
            ("show_header_local_time", "Horário do computador:"),
            ("show_header_grip", "Estado da pista:"),
            ("show_header_track_limits", "Limites de pista:"),
            ("show_header_source", "Fonte dos dados:"),
        ):
            check = QCheckBox()
            check.setChecked(bool(self.config.get(key, True)))
            check.toggled.connect(
                lambda value, current=key: self._set(current, value)
            )
            form.addRow(label, check)
        self.layout_content.addWidget(group)

    def _build_columns(self) -> None:
        group = QGroupBox("Colunas")
        form = QFormLayout(group)
        options = (
            ("show_country_flag", "Bandeira do piloto:", True),
            ("use_flag_images", "Usar imagem da bandeira:", True),
            ("show_badge", "Badge do piloto:", True),
            ("show_driver_rank", "Driver Rank (DR):", True),
            ("show_driver_rank_progress", "Progresso do DR:", True),
            ("show_safety_rank", "Safety Rank (SR):", True),
            (
                "show_estimated_driver_rank_gain",
                "Estimativa de ganho do DR:",
                False,
            ),
            ("show_brand_logo", "Logo da marca:", True),
            ("show_tyre", "Pneu:", True),
            ("show_invalid_lap_status", "Volta inválida:", True),
            ("show_pit_status", "Tempo/status do pit:", True),
            ("show_penalty_column", "Coluna de punição automática:", True),
            ("show_energy", "Bateria/Energia:", True),
            ("show_damage", "Dano:", True),
        )
        for key, label, default in options:
            check = QCheckBox()
            check.setChecked(bool(self.config.get(key, default)))
            check.toggled.connect(lambda value, current=key: self._set(current, value))
            form.addRow(label, check)
        self.layout_content.addWidget(group)

    def _build_dimensions(self) -> None:
        group = QGroupBox("Tamanho e fonte")
        form = QFormLayout(group)
        font = QComboBox()
        font.addItems(QFontDatabase.families())
        font.setCurrentText(str(self.config.get("font_name", "Bahnschrift Condensed")))
        font.currentTextChanged.connect(lambda value: self._set("font_name", value))
        size = QSpinBox()
        size.setRange(12, 42)
        size.setValue(int(self.config.get("font_size", 26)))
        size.valueChanged.connect(lambda value: self._set("font_size", value))
        row_height = QDoubleSpinBox()
        row_height.setRange(36.0, 80.0)
        row_height.setValue(float(self.config.get("row_height", 54.0)))
        row_height.valueChanged.connect(lambda value: self._set("row_height", value))
        header_height = QDoubleSpinBox()
        header_height.setRange(40.0, 90.0)
        header_height.setValue(float(self.config.get("global_header_height", 58.0)))
        header_height.valueChanged.connect(lambda value: self._set("global_header_height", value))
        scale = QDoubleSpinBox()
        scale.setRange(0.40, 2.00)
        scale.setSingleStep(0.05)
        scale.setValue(float(self.config.get("internal_scale", 1.0)))
        scale.valueChanged.connect(lambda value: self._set("internal_scale", value))
        tyre_scale = QDoubleSpinBox()
        tyre_scale.setRange(0.70, 2.00)
        tyre_scale.setSingleStep(0.05)
        tyre_scale.setValue(float(self.config.get("tyre_icon_scale", 1.25)))
        tyre_scale.valueChanged.connect(
            lambda value: self._set("tyre_icon_scale", value)
        )
        lap_highlight = QDoubleSpinBox()
        lap_highlight.setRange(0.0, 15.0)
        lap_highlight.setSingleStep(0.5)
        lap_highlight.setSuffix(" s")
        lap_highlight.setValue(
            float(self.config.get("lap_highlight_seconds", 5.0))
        )
        lap_highlight.valueChanged.connect(
            lambda value: self._set("lap_highlight_seconds", value)
        )
        pit_status_laps = QSpinBox()
        pit_status_laps.setRange(0, 10)
        pit_status_laps.setSuffix(" voltas")
        pit_status_laps.setValue(
            int(self.config.get("pit_status_laps", 2))
        )
        pit_status_laps.valueChanged.connect(
            lambda value: self._set("pit_status_laps", value)
        )
        auto_fit = QCheckBox()
        auto_fit.setChecked(bool(self.config.get("auto_fit_height", True)))
        auto_fit.toggled.connect(
            lambda value: self._set("auto_fit_height", value)
        )
        opacity = QDoubleSpinBox()
        opacity.setRange(0.10, 1.00)
        opacity.setSingleStep(0.05)
        opacity.setValue(float(self.config.get("opacity", 0.98)))
        opacity.valueChanged.connect(lambda value: self._set("opacity", value))
        logo_dir = QLineEdit(str(self.config.get("logo_directory", "images/logos")))
        logo_dir.editingFinished.connect(lambda: self._set("logo_directory", logo_dir.text().strip()))
        form.addRow("Fonte:", font)
        form.addRow("Tamanho base:", size)
        form.addRow("Altura da linha:", row_height)
        form.addRow("Altura do cabeçalho:", header_height)
        form.addRow("Escala interna:", scale)
        form.addRow("Tamanho do desenho do pneu:", tyre_scale)
        form.addRow("Destaque de nova melhor volta:", lap_highlight)
        form.addRow("Manter tempo do pit por:", pit_status_laps)
        form.addRow("Ajustar fundo ao conteúdo:", auto_fit)
        form.addRow("Opacidade:", opacity)
        form.addRow("Pasta de logos:", logo_dir)
        self.layout_content.addWidget(group)

    def _build_local_source(self) -> None:
        group = QGroupBox("Fontes de dados do LMU")
        form = QFormLayout(group)
        enabled = QCheckBox()
        enabled.setChecked(bool(self.config.get("enable_local_api", True)))
        enabled.toggled.connect(lambda value: self._set("enable_local_api", value))
        interval = QDoubleSpinBox()
        interval.setRange(0.5, 15.0)
        interval.setSuffix(" s")
        interval.setValue(float(self.config.get("local_poll_interval_seconds", 2.0)))
        interval.valueChanged.connect(lambda value: self._set("local_poll_interval_seconds", value))
        timeout = QDoubleSpinBox()
        timeout.setRange(0.2, 5.0)
        timeout.setSuffix(" s")
        timeout.setValue(float(self.config.get("local_api_timeout_seconds", 0.8)))
        timeout.valueChanged.connect(lambda value: self._set("local_api_timeout_seconds", value))
        online = QCheckBox()
        online.setChecked(bool(self.config.get("online_enrichment", False)))
        online.toggled.connect(
            lambda value: self._set("online_enrichment", value)
        )
        online_interval = QDoubleSpinBox()
        online_interval.setRange(5.0, 60.0)
        online_interval.setSuffix(" s")
        online_interval.setValue(
            float(self.config.get("online_refresh_seconds", 10.0))
        )
        online_interval.valueChanged.connect(
            lambda value: self._set("online_refresh_seconds", value)
        )
        online_note = QLabel(
            "O REST local captura país, badge, DR e SR quando o próprio LMU "
            "publica esses campos na sessão. A consulta externa é opcional e "
            "permanece desligada sem uma chave autorizada."
        )
        online_note.setWordWrap(True)
        form.addRow("REST local:", enabled)
        form.addRow("Atualização:", interval)
        form.addRow("Timeout:", timeout)
        form.addRow("Consulta externa:", online)
        form.addRow("Atualizar perfis:", online_interval)
        form.addRow(online_note)
        self.layout_content.addWidget(group)

    def _build_colors(self) -> None:
        group = QGroupBox("Cores principais")
        form = QFormLayout(group)
        labels = {
            "background": "Fundo", "header_background": "Cabeçalho global",
            "text": "Texto", "muted": "Texto secundário", "row_background": "Linha normal",
            "player_background": "Linha do jogador", "position_gain": "Posição ganha",
            "position_loss": "Posição perdida", "personal_best": "Melhor volta",
            "invalid_lap": "Volta inválida",
            "rank_bronze": "DR/SR Bronze",
            "rank_silver": "DR/SR Prata",
            "rank_gold": "DR/SR Ouro",
            "rank_platinum": "DR/SR Platina",
            "energy_low": "Energia baixa", "damage_high": "Dano alto", "edit_border": "Borda de edição",
        }
        for key, label in labels.items():
            value = str(self.config.setdefault("colors", {}).get(key, "#FFFFFF"))
            button = QPushButton(value)
            button.clicked.connect(lambda checked=False, current=key: self._choose_color(current))
            self.color_buttons[key] = button
            form.addRow(label + ":", button)
        self.layout_content.addWidget(group)
        self.layout_content.addStretch()

    def _choose_color(self, key: str) -> None:
        current = QColor(str(self.config.setdefault("colors", {}).get(key, "#FFFFFF")))
        selected = QColorDialog.getColor(current, self)
        if not selected.isValid():
            return
        value = selected.name(QColor.NameFormat.HexRgb)
        self.config["colors"][key] = value
        self.color_buttons[key].setText(value)
        self._emit()

    def _set(self, key: str, value: Any) -> None:
        self.config[key] = value
        self._emit()

    def _emit(self) -> None:
        self.config_changed.emit(deepcopy(self.config))
