from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget


PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from src.telemetry.lmu_adapter import LMUAdapter
from src.ui.edit_mode_manager import EditModeManager
from src.ui.overlay_manager import OverlayManager
from src.widget.driver_panel.driver_panel_editor import DriverPanelEditor


class LMUDriverPanelWindow(QWidget):

    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("Sector Flow Drive - LMU")
        self.resize(380, 180)

        layout = QVBoxLayout(self)

        self.status_button = QPushButton(
            "Aguardando Le Mans Ultimate..."
        )

        self.editor_button = QPushButton(
            "Abrir editor do Driver Panel"
        )

        self.edit_button = QPushButton(
            "Ativar modo edição - F12"
        )

        layout.addWidget(self.status_button)
        layout.addWidget(self.editor_button)
        layout.addWidget(self.edit_button)

        config_path = (
            PROJECT_ROOT
            / "src"
            / "config"
            / "widgets.json"
        )

        self.overlay_manager = OverlayManager(config_path)

        self.driver_panel = (
            self.overlay_manager.create_driver_panel()
        )

        self.edit_manager = EditModeManager(self)

        self.edit_manager.register_widget(
            self.driver_panel
        )

        self.edit_manager.edit_mode_changed.connect(
            self.overlay_manager.set_edit_mode
        )

        self.editor = DriverPanelEditor(
            self.overlay_manager
            .config_data["widgets"]["driver_panel"],
            self
        )

        self.editor.config_changed.connect(
            self.update_driver_panel_config
        )

        self.editor.restore_requested.connect(
            self.restore_default
        )

        self.editor_button.clicked.connect(
            self.editor.show
        )

        self.edit_button.clicked.connect(
            self.edit_manager.toggle
        )

        self.adapter = LMUAdapter(copy_access=True)

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)

        self.timer.timeout.connect(
            self.read_lmu
        )

        # Mesma frequência do aplicativo principal: aproximadamente 60 Hz.
        self.timer.start(16)

    def update_driver_panel_config(
        self,
        config: dict
    ) -> None:

        self.overlay_manager.update_widget_config(
            "driver_panel",
            config
        )

    def restore_default(self) -> None:

        self.overlay_manager.restore_widget_default(
            "driver_panel"
        )

    def read_lmu(self) -> None:

        session = self.adapter.read()

        if not session.connected:

            self.status_button.setText(
                f"Aguardando LMU: {session.error}"
            )

            return

        if session.player is None:

            self.status_button.setText(
                "LMU conectado. Aguardando carro do jogador..."
            )

            return

        player = session.player

        self.status_button.setText(
            f"LMU conectado | "
            f"{session.track_name} | "
            f"{player.speed_kmh:.0f} km/h"
        )

        self.overlay_manager.update_player_data(
            player
        )

    def closeEvent(self, event) -> None:

        self.timer.stop()
        self.adapter.close()
        self.overlay_manager.close_all()

        event.accept()


def main() -> None:

    app = QApplication(sys.argv)

    window = LMUDriverPanelWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
