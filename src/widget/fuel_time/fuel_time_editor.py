from __future__ import annotations
from copy import deepcopy
from typing import Any
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout, QPushButton, QSpinBox, QVBoxLayout

class FuelTimeEditor(QDialog):
    config_changed=Signal(dict); restore_requested=Signal()
    def __init__(self, config: dict[str,Any], parent=None) -> None:
        super().__init__(parent); self.config=deepcopy(config); self.setWindowTitle("Editar Fuel Time")
        root=QVBoxLayout(self); form=QFormLayout(); root.addLayout(form)
        avg=QSpinBox(); avg.setRange(1,20); avg.setValue(int(self.config.get("average_laps",5))); avg.valueChanged.connect(lambda v:self._set("average_laps",v)); form.addRow("Voltas na media:",avg)
        reserve=QDoubleSpinBox(); reserve.setRange(0,5); reserve.setDecimals(1); reserve.setSingleStep(.1); reserve.setValue(float(self.config.get("reserve_laps",1))); reserve.valueChanged.connect(lambda v:self._set("reserve_laps",v)); form.addRow("Margem (voltas):",reserve)
        energy=QCheckBox(); energy.setChecked(bool(self.config.get("show_energy",True))); energy.toggled.connect(lambda v:self._set("show_energy",v)); form.addRow("Energia e Fuel Ratio:",energy)
        actions=QHBoxLayout(); restore=QPushButton("Restaurar"); close=QPushButton("Fechar"); restore.clicked.connect(self.restore_requested.emit); close.clicked.connect(self.accept); actions.addWidget(restore); actions.addStretch(); actions.addWidget(close); root.addLayout(actions)
    def _set(self,key:str,value:Any)->None: self.config[key]=value; self.config_changed.emit(deepcopy(self.config))
