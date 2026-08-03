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
    speed_kmh: float = 234.0
    rpm: float = 8124.0
    max_rpm: float = 9000.0
    gear: int = 5
    throttle: float = 0.94
    brake: float = 0.18
    fuel_liters: float = 42.3
    delta_best_s: float = -0.253
    lap: int = 12
    sector: int = 2
    vehicle_model: str = "Ferrari 296 LMGT3"


class TestWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Sector Flow Drive - Teste Driver Panel")
        self.resize(360, 160)

        layout = QVBoxLayout(self)
        edit_button = QPushButton("Abrir editor")
        mode_button = QPushButton("Alternar modo edição (F12)")
        layout.addWidget(edit_button)
        layout.addWidget(mode_button)

        config_path = PROJECT_ROOT / "src" / "config" / "widgets.json"
        self.overlay_manager = OverlayManager(config_path)
        self.driver_panel = self.overlay_manager.create_driver_panel()

        self.edit_manager = EditModeManager(self)
        self.edit_manager.register_widget(self.driver_panel)
        self.edit_manager.edit_mode_changed.connect(self.overlay_manager.set_edit_mode)

        self.editor = DriverPanelEditor(
            self.overlay_manager.config_data["widgets"]["driver_panel"],
            self,
        )
        self.editor.config_changed.connect(
            lambda config: self.overlay_manager.update_widget_config("driver_panel", config)
        )
        self.editor.restore_requested.connect(
            lambda: self.overlay_manager.restore_widget_default("driver_panel")
        )

        edit_button.clicked.connect(self.editor.show)
        mode_button.clicked.connect(self.edit_manager.toggle)

        self.fake = FakePlayer()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_fake_data)
        self.timer.start(50)

    def update_fake_data(self) -> None:
        self.fake.rpm += 75
        if self.fake.rpm > self.fake.max_rpm:
            self.fake.rpm = 3500

        self.fake.speed_kmh += 0.5
        if self.fake.speed_kmh > 320:
            self.fake.speed_kmh = 80

        self.overlay_manager.update_player_data(self.fake)

    def closeEvent(self, event) -> None:
        self.overlay_manager.close_all()
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
