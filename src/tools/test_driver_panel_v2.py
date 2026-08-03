from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.ui.edit_mode_manager import EditModeManager
from src.ui.overlay_manager import OverlayManager
from src.widget.driver_panel.driver_panel_editor import DriverPanelEditor


@dataclass
class FakePlayer:
    speed_kmh: float = 320
    rpm: float = 3000
    max_rpm: float = 9000
    gear: int = 7
    throttle: float = 0.70
    brake: float = 0.30
    steering: float = 0.0


class TestWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Teste Telemetry V2")
        self.resize(340, 130)

        layout = QVBoxLayout(self)
        edit = QPushButton("Abrir editor")
        mode = QPushButton("Modo edição (F12)")
        layout.addWidget(edit)
        layout.addWidget(mode)

        config_path = PROJECT_ROOT / "src" / "config" / "widgets.json"
        self.manager = OverlayManager(config_path)
        self.panel = self.manager.create_driver_panel()

        self.edit_manager = EditModeManager(self)
        self.edit_manager.register_widget(self.panel)
        self.edit_manager.edit_mode_changed.connect(self.manager.set_edit_mode)

        self.editor = DriverPanelEditor(
            self.manager.config_data["widgets"]["driver_panel"], self
        )
        self.editor.config_changed.connect(
            lambda cfg: self.manager.update_widget_config("driver_panel", cfg)
        )

        edit.clicked.connect(self.editor.show)
        mode.clicked.connect(self.edit_manager.toggle)

        self.player = FakePlayer()
        self.direction = 1

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(50)

    def animate(self) -> None:
        self.player.rpm += 100
        if self.player.rpm >= self.player.max_rpm:
            self.player.rpm = 2500

        self.player.steering += 0.03 * self.direction
        if abs(self.player.steering) >= 1:
            self.direction *= -1

        self.manager.update_player_data(self.player)

    def closeEvent(self, event) -> None:
        self.manager.close_all()
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
