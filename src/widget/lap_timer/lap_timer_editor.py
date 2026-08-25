from __future__ import annotations

from copy import deepcopy
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDoubleSpinBox, QFontComboBox, QFormLayout,
    QGroupBox, QHBoxLayout, QPushButton, QSpinBox, QVBoxLayout,
)

from src.i18n import tr


class LapTimerEditor(QDialog):
    config_changed = Signal(dict)
    restore_requested = Signal()

    def __init__(self, config: dict[str, Any], parent=None) -> None:
        super().__init__(parent)
        self.config = deepcopy(config)
        self.setWindowTitle("Editar Lap Timer")
        self.resize(430, 620)
        root = QVBoxLayout(self)

        fields = QGroupBox("Informações visíveis")
        form = QFormLayout(fields)
        choices = (
            ("show_current", "Cronômetro da volta atual"), ("show_last", "Última volta"),
            ("show_best", "Melhor volta"), ("show_predicted", "Tempo previsto"),
            ("show_theoretical", "Volta teórica (melhores setores)"), ("show_laps", "Voltas atual / total"),
            ("show_remaining", "Voltas restantes"), ("show_position", "Posição geral"),
            ("show_class_position", "Posição na categoria"),
        )
        for key, label in choices:
            check = QCheckBox()
            check.setChecked(bool(self.config.get(key, key not in {"show_theoretical", "show_remaining"})))
            check.toggled.connect(lambda value, name=key: self._set(name, value))
            form.addRow(label + ":", check)
        root.addWidget(fields)

        visual = QGroupBox("Visual")
        vf = QFormLayout(visual)
        family = QFontComboBox()
        configured_family = str(self.config.get("font_name", "Arial"))
        family.setCurrentFont(QFont(configured_family))
        family.currentFontChanged.connect(
            lambda font: self._set("font_name", font.family())
        )
        vf.addRow("Fonte:", family)
        decimals = QComboBox(); decimals.addItem("Milissegundos (3)", 3); decimals.addItem("Centésimos (2)", 2)
        decimals.setCurrentIndex(max(0, decimals.findData(int(self.config.get("decimals", 3)))))
        decimals.currentIndexChanged.connect(lambda _: self._set("decimals", int(decimals.currentData())))
        vf.addRow("Precisão:", decimals)
        for key, label, low, high, step in (
            ("title_font_scale", "Tamanho do título", .25, .85, .01),
            ("value_font_scale", "Tamanho dos valores", .25, .80, .01),
            ("label_font_scale", "Tamanho dos nomes", .18, .55, .01),
            ("opacity", "Opacidade da janela", .10, 1.0, .05),
        ):
            spin = QDoubleSpinBox(); spin.setRange(low, high); spin.setSingleStep(step); spin.setDecimals(2)
            default = {
                "title_font_scale": .52,
                "value_font_scale": .46,
                "label_font_scale": .28,
                "opacity": 1.0,
            }[key]
            spin.setValue(float(self.config.get(key, default)))
            spin.valueChanged.connect(lambda value, name=key: self._set(name, value)); vf.addRow(label + ":", spin)
        background = QCheckBox(); background.setChecked(bool(self.config.get("background_enabled", True))); background.toggled.connect(lambda v: self._set("background_enabled", v)); vf.addRow("Fundo principal:", background)
        panels = QCheckBox(); panels.setChecked(bool(self.config.get("row_backgrounds", True))); panels.toggled.connect(lambda v: self._set("row_backgrounds", v)); vf.addRow("Fundo das linhas:", panels)
        for key, label in (
            ("background", "Cor do fundo principal"),
            ("panel", "Cor do fundo das linhas"),
            ("border", "Cor da borda"),
            ("title", "Cor do título"),
            ("muted", "Cor dos nomes"),
            ("text", "Cor do texto"),
            ("current", "Cor da volta atual"),
            ("best", "Cor da melhor volta"),
            ("predicted", "Cor da previsão"),
            ("theoretical", "Cor da volta teórica"),
            ("invalid", "Cor da volta inválida"),
        ):
            button = QPushButton(str(self.config.get("colors", {}).get(key, "#FFFFFF")))
            button.clicked.connect(lambda _=False, name=key, target=button: self._pick_color(name, target))
            vf.addRow(label + ":", button)
        root.addWidget(visual)

        actions = QHBoxLayout()
        restore = QPushButton("Restaurar"); close = QPushButton("Fechar")
        restore.clicked.connect(self.restore_requested.emit); close.clicked.connect(self.accept)
        actions.addWidget(restore); actions.addStretch(); actions.addWidget(close); root.addLayout(actions)

    def _set(self, key: str, value: Any) -> None:
        self.config[key] = value
        self.config_changed.emit(deepcopy(self.config))

    def _pick_color(self, key: str, button: QPushButton) -> None:
        current = QColor(str(self.config.get("colors", {}).get(key, "#FFFFFF")))
        color = QColorDialog.getColor(
            current,
            self,
            tr("Escolher cor"),
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if not color.isValid():
            return
        value = color.name(QColor.NameFormat.HexArgb if color.alpha() < 255 else QColor.NameFormat.HexRgb)
        self.config.setdefault("colors", {})[key] = value
        button.setText(value)
        self.config_changed.emit(deepcopy(self.config))
