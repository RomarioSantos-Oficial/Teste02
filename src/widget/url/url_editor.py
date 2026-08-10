from __future__ import annotations

from copy import deepcopy
import socket
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

AVAILABLE = (
    "standings", "relative", "delta", "map", "driver_panel", "battery",
    "fuel_time", "tires", "damage", "weather", "flags", "radar",
)


class UrlEditor(QDialog):
    config_changed = Signal(dict)
    restore_requested = Signal()

    def __init__(self, config: dict[str, Any], parent=None) -> None:
        super().__init__(parent)
        self.config = deepcopy(config)
        self.url_rows: dict[str, tuple[QLineEdit, QPushButton]] = {}
        self.setWindowTitle("Editar servidor URL")
        root = QVBoxLayout(self)
        root.addWidget(QLabel(
            "Ative os widgets que deseja publicar. Cada URL pode ser usada "
            "separadamente no OBS."
        ))
        form = QFormLayout()
        root.addLayout(form)

        host = QLineEdit(str(self.config.get("bind_host", "0.0.0.0")))
        host.editingFinished.connect(
            lambda: self._set("bind_host", host.text().strip() or "0.0.0.0")
        )
        form.addRow("Escutar em:", host)
        port = QSpinBox(); port.setRange(1024, 65535)
        port.setValue(int(self.config.get("port", 8765)))
        port.valueChanged.connect(lambda value: self._set("port", value))
        form.addRow("Porta:", port)
        fps = QSpinBox(); fps.setRange(1, 30)
        fps.setValue(int(self.config.get("fps", 10)))
        fps.valueChanged.connect(lambda value: self._set("fps", value))
        form.addRow("Atualizações/segundo:", fps)

        chosen = set(self.config.get("published_widgets", []))
        for key in AVAILABLE:
            box = QCheckBox("Publicar")
            box.setChecked(key in chosen)
            box.toggled.connect(lambda value, current=key: self._toggle(current, value))
            form.addRow(key.replace("_", " ").title() + ":", box)

            url_line = QLineEdit(); url_line.setReadOnly(True)
            copy_button = QPushButton("Copiar")
            copy_button.clicked.connect(
                lambda _checked=False, current=key: self._copy_url(current)
            )
            line = QWidget(); line_layout = QHBoxLayout(line)
            line_layout.setContentsMargins(0, 0, 0, 6)
            line_layout.addWidget(url_line, 1); line_layout.addWidget(copy_button)
            form.addRow("", line)
            self.url_rows[key] = (url_line, copy_button)

        actions = QHBoxLayout()
        restore = QPushButton("Restaurar"); close = QPushButton("Fechar")
        restore.clicked.connect(self.restore_requested.emit); close.clicked.connect(self.accept)
        actions.addWidget(restore); actions.addStretch(); actions.addWidget(close)
        root.addLayout(actions)
        self._refresh_links()

    def _set(self, key: str, value: Any) -> None:
        self.config[key] = value
        self.config_changed.emit(deepcopy(self.config))
        self._refresh_links()

    def _toggle(self, key: str, value: bool) -> None:
        selected = [item for item in self.config.get("published_widgets", []) if item != key]
        if value: selected.append(key)
        self._set("published_widgets", selected)

    def _network_ip(self) -> str:
        try:
            addresses = socket.gethostbyname_ex(socket.gethostname())[2]
            return next((value for value in addresses if not value.startswith("127.")), "127.0.0.1")
        except OSError:
            return "127.0.0.1"

    def _refresh_links(self) -> None:
        host = self._network_ip(); port = int(self.config.get("port", 8765))
        selected = set(self.config.get("published_widgets", []))
        for key, (line, button) in self.url_rows.items():
            line.setText(f"http://{host}:{port}/widget/{key}")
            active = key in selected
            line.setEnabled(active); button.setEnabled(active)
            line.setToolTip("URL ativa para OBS" if active else "Ative Publicar para liberar esta URL")

    def _copy_url(self, key: str) -> None:
        line, _button = self.url_rows[key]
        if not line.isEnabled(): return
        clipboard = QApplication.clipboard()
        if clipboard is not None: clipboard.setText(line.text())
