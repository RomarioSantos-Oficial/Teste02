from __future__ import annotations

from copy import deepcopy
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QPushButton, QVBoxLayout, QWidget, QTabWidget,
)

from src.widget.base.editor_layout import add_editor_tab


class DamageEditor(QDialog):
    config_changed = Signal(dict)
    restore_requested = Signal()

    def __init__(self, config: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = deepcopy(config)
        self.setWindowTitle("Editar Damage")
        self.resize(760, 620)
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        root.addWidget(tabs, 1)
        page = add_editor_tab(tabs, "Exibição")
        group = QGroupBox("Elementos do painel")
        form = QFormLayout(group)
        for key, label in (
            ("show_integrity", "Mostrar integridade"),
            ("show_last_impact", "Mostrar direção do impacto"),
            ("show_suspension_links", "Mostrar linhas da suspensão"),
        ):
            box = QCheckBox()
            box.setChecked(bool(self.config.get(key, True)))
            box.toggled.connect(lambda value, current=key: self._set(current, value))
            form.addRow(label, box)
        page.addWidget(group)
        page.addStretch(1)
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
