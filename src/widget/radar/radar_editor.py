from __future__ import annotations

from copy import deepcopy
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QPushButton, QVBoxLayout, QWidget, QTabWidget,
)

from src.widget.base.editor_layout import add_editor_tab


class RadarEditor(QDialog):
    config_changed = Signal(dict)
    restore_requested = Signal()

    def __init__(self, config: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = deepcopy(config)
        self.setWindowTitle("Editar Radar")
        self.resize(760, 620)
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        root.addWidget(tabs, 1)

        display_page = add_editor_tab(tabs, "Exibição")
        display = QGroupBox("Elementos do radar")
        display_form = QFormLayout(display)
        for key, label in (
            ("auto_hide_when_clear", "Ocultar sem carros próximos"),
            ("show_background", "Mostrar fundo"),
            ("show_marks", "Mostrar círculos de distância"),
        ):
            box = QCheckBox()
            box.setChecked(bool(self.config.get(key, True)))
            box.toggled.connect(lambda value, current=key: self._set(current, value))
            display_form.addRow(label, box)
        display_page.addWidget(display)
        display_page.addStretch(1)

        range_page = add_editor_tab(tabs, "Distâncias e dimensões")
        dimensions = QGroupBox("Alcance e dimensões dos veículos")
        form = QFormLayout(dimensions)
        for key, label, low, high, step in (
            ("radar_radius_m", "Alcance lateral (m)", 5, 40, 1),
            ("vehicle_width_m", "Largura do carro (m)", 1, 4, 0.1),
            ("vehicle_length_m", "Comprimento do carro (m)", 3, 8, 0.1),
            ("nearby_side_distance_m", "Aviso de proximidade (m)", 2, 8, 0.1),
            ("critical_side_distance_m", "Aviso crítico (m)", 1, 5, 0.1),
        ):
            spin = QDoubleSpinBox()
            spin.setRange(low, high)
            spin.setSingleStep(step)
            spin.setValue(float(self.config.get(key, low)))
            spin.valueChanged.connect(lambda value, current=key: self._set(current, value))
            form.addRow(label, spin)
        range_page.addWidget(dimensions)
        range_page.addStretch(1)

        actions = QHBoxLayout()
        restore = QPushButton("Restaurar padrão")
        close = QPushButton("Fechar")
        restore.clicked.connect(self.restore_requested.emit)
        close.clicked.connect(self.accept)
        actions.addWidget(restore)
        actions.addStretch()
        actions.addWidget(close)
        root.addLayout(actions)

    def _set(self, key: str, value: Any) -> None:
        self.config[key] = value
        self.config_changed.emit(deepcopy(self.config))
