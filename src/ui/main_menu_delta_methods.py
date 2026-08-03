from __future__ import annotations

from copy import deepcopy

from PySide6.QtWidgets import QMessageBox

from src.widget.delta.delta_editor import DeltaEditor
from src.widget.driver_panel.driver_panel_editor import DriverPanelEditor

# Este arquivo contém somente os métodos corrigidos.
# Substitua os métodos de mesmo nome dentro de MainMenuWindow.


def _toggle_widget(self, widget_id: str, enabled: bool) -> None:
    try:
        if enabled:
            if widget_id == "driver_panel":
                self.overlay_manager.create_driver_panel()

            elif widget_id == "delta":
                self.overlay_manager.create_delta()

            else:
                QMessageBox.information(
                    self,
                    "Widget ainda não criado",
                    f"O widget '{widget_id}' ainda "
                    "não foi implementado.",
                )

                self.rows[
                    widget_id
                ].set_enabled_state(False)
                return

        self.overlay_manager.set_widget_enabled(
            widget_id,
            enabled,
        )

    except Exception as exc:
        QMessageBox.critical(
            self,
            "Erro ao controlar widget",
            str(exc),
        )

        self.rows[
            widget_id
        ].set_enabled_state(False)


def _open_editor(self, widget_id: str) -> None:
    if widget_id == "driver_panel":
        config = deepcopy(
            self.overlay_manager.config_data[
                "widgets"
            ]["driver_panel"]
        )

        editor = DriverPanelEditor(
            config,
            self,
        )

    elif widget_id == "delta":
        config = deepcopy(
            self.overlay_manager.config_data[
                "widgets"
            ]["delta"]
        )

        editor = DeltaEditor(
            config,
            self,
        )

    else:
        QMessageBox.information(
            self,
            "Editor ainda não criado",
            f"O editor de '{widget_id}' "
            "ainda não foi implementado.",
        )
        return

    editor.config_changed.connect(
        lambda new_config, current_id=widget_id:
        self.overlay_manager.update_widget_config(
            current_id,
            new_config,
        )
    )

    editor.restore_requested.connect(
        lambda current_id=widget_id:
        self.overlay_manager.restore_widget_default(
            current_id
        )
    )

    editor.show()
    self.editors[widget_id] = editor
