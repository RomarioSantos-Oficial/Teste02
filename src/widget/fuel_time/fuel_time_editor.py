from __future__ import annotations

from copy import deepcopy
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QPushButton, QSpinBox, QVBoxLayout, QWidget, QTabWidget,
)

from src.widget.base.editor_layout import add_editor_tab


class FuelTimeEditor(QDialog):
    config_changed = Signal(dict)
    restore_requested = Signal()

    def __init__(self, config: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.config = deepcopy(config)
        self.setWindowTitle("Editar Fuel Time")
        self.resize(760, 620)
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        strategy_page = add_editor_tab(tabs, "Estratégia")
        strategy = QGroupBox("Consumo e margem")
        form = QFormLayout(strategy)
        average = QSpinBox()
        average.setRange(1, 20)
        average.setValue(int(self.config.get("average_laps", 5)))
        average.valueChanged.connect(lambda value: self._set("average_laps", value))
        form.addRow("Voltas usadas na média:", average)
        reserve = QDoubleSpinBox()
        reserve.setRange(0, 5)
        reserve.setDecimals(1)
        reserve.setSingleStep(0.1)
        reserve.setValue(float(self.config.get("reserve_laps", 1)))
        reserve.valueChanged.connect(lambda value: self._set("reserve_laps", value))
        form.addRow("Margem de segurança (voltas):", reserve)
        strategy_page.addWidget(strategy)
        strategy_page.addStretch(1)

        display_page = add_editor_tab(tabs, "Exibição")
        display = QGroupBox("Informações visíveis")
        display_form = QFormLayout(display)
        energy = QCheckBox()
        energy.setChecked(bool(self.config.get("show_energy", True)))
        energy.toggled.connect(lambda value: self._set("show_energy", value))
        display_form.addRow("Mostrar Energia e Fuel Ratio:", energy)
        display_page.addWidget(display)
        display_page.addStretch(1)

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
