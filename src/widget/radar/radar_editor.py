from __future__ import annotations
from copy import deepcopy
from typing import Any
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QPushButton, QVBoxLayout


class RadarEditor(QDialog):
    config_changed = Signal(dict)
    restore_requested = Signal()

    def __init__(self, config: dict[str, Any], parent=None) -> None:
        super().__init__(parent)
        self.config = deepcopy(config); self.setWindowTitle("Editar Radar")
        root = QVBoxLayout(self); form = QFormLayout(); root.addLayout(form)
        for key, label in (("auto_hide_when_clear", "Ocultar sem carros próximos"), ("show_background", "Mostrar fundo"), ("show_marks", "Mostrar círculos de distância")):
            box = QCheckBox(); box.setChecked(bool(self.config.get(key, True))); box.toggled.connect(lambda value, k=key: self._set(k, value)); form.addRow(label, box)
        for key, label, low, high, step in (("radar_radius_m", "Alcance lateral (m)", 5, 40, 1), ("vehicle_width_m", "Largura do carro (m)", 1, 4, .1), ("vehicle_length_m", "Comprimento do carro (m)", 3, 8, .1), ("nearby_side_distance_m", "Aviso próximo (m)", 2, 8, .1), ("critical_side_distance_m", "Aviso crítico (m)", 1, 5, .1)):
            spin = QDoubleSpinBox(); spin.setRange(low, high); spin.setSingleStep(step); spin.setValue(float(self.config.get(key, low))); spin.valueChanged.connect(lambda value, k=key: self._set(k, value)); form.addRow(label, spin)
        actions = QHBoxLayout(); restore = QPushButton("Restaurar"); close = QPushButton("Fechar")
        restore.clicked.connect(self.restore_requested.emit); close.clicked.connect(self.accept); actions.addWidget(restore); actions.addStretch(); actions.addWidget(close); root.addLayout(actions)

    def _set(self, key: str, value: Any) -> None:
        self.config[key] = value; self.config_changed.emit(deepcopy(self.config))
