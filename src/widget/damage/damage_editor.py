from __future__ import annotations
from copy import deepcopy
from typing import Any
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QDialog, QFormLayout, QHBoxLayout, QPushButton, QVBoxLayout

class DamageEditor(QDialog):
    config_changed = Signal(dict)
    restore_requested = Signal()
    def __init__(self, config: dict[str, Any], parent=None) -> None:
        super().__init__(parent); self.config = deepcopy(config)
        self.setWindowTitle("Editar Damage")
        root = QVBoxLayout(self); form = QFormLayout(); root.addLayout(form)
        for key, label in (("show_integrity","Mostrar integridade"),("show_last_impact","Mostrar direção do impacto"),("show_suspension_links","Mostrar linhas da suspensão")):
            box = QCheckBox(); box.setChecked(bool(self.config.get(key, True)))
            box.toggled.connect(lambda value, k=key: self._set(k, value)); form.addRow(label, box)
        actions = QHBoxLayout(); restore = QPushButton("Restaurar"); close = QPushButton("Fechar")
        restore.clicked.connect(self.restore_requested.emit); close.clicked.connect(self.accept)
        actions.addWidget(restore); actions.addStretch(); actions.addWidget(close); root.addLayout(actions)
    def _set(self, key: str, value: Any) -> None:
        self.config[key] = value; self.config_changed.emit(deepcopy(self.config))
