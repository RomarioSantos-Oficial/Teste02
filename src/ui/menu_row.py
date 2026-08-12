from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QCheckBox,
)


class MenuRow(QFrame):
    toggled = Signal(str, bool)
    edit_requested = Signal(str)

    def __init__(
        self,
        widget_id: str,
        title: str,
        enabled: bool,
        editable: bool,
        implemented: bool,
        parent=None,
    ) -> None:
        super().__init__(parent)

        self.widget_id = widget_id
        self.setObjectName("menuRow")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 10, 8)
        layout.setSpacing(12)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("rowTitle")

        self.status_label = QLabel()
        self.status_label.setObjectName("rowStatus")

        self.toggle = QCheckBox()
        self.toggle.setChecked(enabled)
        self.toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle.toggled.connect(
            lambda value: self.toggled.emit(self.widget_id, value)
        )

        self.edit_button = QPushButton("Editar")
        self.edit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.edit_button.setEnabled(editable and implemented)
        self.edit_button.clicked.connect(
            lambda: self.edit_requested.emit(self.widget_id)
        )

        layout.addWidget(self.title_label, 1)
        layout.addWidget(self.status_label)
        layout.addWidget(self.toggle)
        layout.addWidget(self.edit_button)

        self._apply_implemented_state(implemented)
        self._apply_enabled_status(enabled)

    def set_enabled_state(self, enabled: bool) -> None:
        self.toggle.blockSignals(True)
        self.toggle.setChecked(enabled)
        self.toggle.blockSignals(False)
        self._apply_enabled_status(enabled)

    def _apply_enabled_status(self, enabled: bool) -> None:
        self.status_label.setText("Ativo" if enabled else "Desativado")
        self.status_label.setProperty("active", bool(enabled))
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _apply_implemented_state(self, implemented: bool) -> None:
        if not implemented:
            self.toggle.setEnabled(False)
