from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QWidget


class EditModeManager(QObject):
    """Controla o modo de edição global dos overlays."""

    edit_mode_changed = Signal(bool)

    def __init__(
        self,
        shortcut_parent: QWidget,
        shortcut: str = "F12",
    ) -> None:
        super().__init__(shortcut_parent)

        self._enabled = False
        self._widgets: list[QWidget] = []

        self._shortcut = QShortcut(QKeySequence(shortcut), shortcut_parent)
        self._shortcut.setContext(
            Qt.ShortcutContext.ApplicationShortcut
        )
        self._shortcut.activated.connect(self.toggle)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def register_widget(self, widget: QWidget) -> None:
        if widget not in self._widgets:
            self._widgets.append(widget)
            if hasattr(widget, "set_edit_mode"):
                widget.set_edit_mode(self._enabled)

    def unregister_widget(self, widget: QWidget) -> None:
        if widget in self._widgets:
            self._widgets.remove(widget)

    def toggle(self) -> None:
        self.set_enabled(not self._enabled)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

        for widget in self._widgets:
            if hasattr(widget, "set_edit_mode"):
                widget.set_edit_mode(self._enabled)

        self.edit_mode_changed.emit(self._enabled)
