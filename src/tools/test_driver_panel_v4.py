from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.ui.edit_mode_manager import EditModeManager
from src.ui.overlay_manager import OverlayManager
from src.widget.driver_panel.driver_panel_editor import DriverPanelEditor


@dataclass
class FakePlayer:
    speed_kmh: float = 180.0
    rpm: float = 3000.0
    max_rpm: float = 9000.0
    gear: int = 4
    throttle: float = 0.0
    brake: float = 0.0
    steering: float = 0.0


class TestWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle(
            "Teste Telemetry V4 Responsiva"
        )
        self.resize(380, 180)

        layout = QVBoxLayout(self)

        edit = QPushButton("Abrir editor")
        mode = QPushButton("Modo edição (F12)")
        clear = QPushButton("Limpar gráfico")
        small = QPushButton("Deixar overlay pequeno")
        normal = QPushButton("Tamanho normal")

        layout.addWidget(edit)
        layout.addWidget(mode)
        layout.addWidget(clear)
        layout.addWidget(small)
        layout.addWidget(normal)

        config_path = (
            PROJECT_ROOT
            / "src"
            / "config"
            / "widgets.json"
        )

        self.manager = OverlayManager(config_path)
        self.panel = self.manager.create_driver_panel()

        self.edit_manager = EditModeManager(self)
        self.edit_manager.register_widget(self.panel)
        self.edit_manager.edit_mode_changed.connect(
            self.manager.set_edit_mode
        )

        self.editor = DriverPanelEditor(
            self.manager.config_data[
                "widgets"
            ]["driver_panel"],
            self,
        )

        self.editor.config_changed.connect(
            lambda cfg:
            self.manager.update_widget_config(
                "driver_panel",
                cfg,
            )
        )

        edit.clicked.connect(self.editor.show)
        mode.clicked.connect(
            self.edit_manager.toggle
        )
        clear.clicked.connect(
            self.panel.clear_graph
        )
        small.clicked.connect(
            lambda:
            self.panel.resize(520, 190)
        )
        normal.clicked.connect(
            lambda:
            self.panel.resize(1200, 360)
        )

        self.player = FakePlayer()
        self.time_value = 0.0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(50)

    def animate(self) -> None:
        self.time_value += 0.08

        self.player.throttle = max(
            0.0,
            min(
                1.0,
                0.50
                + 0.50
                * math.sin(self.time_value),
            ),
        )
        self.player.brake = max(
            0.0,
            min(
                1.0,
                0.50
                + 0.50
                * math.sin(
                    self.time_value + 2.2
                ),
            ),
        )
        self.player.steering = math.sin(
            self.time_value * 0.65
        )

        self.player.rpm = (
            2500
            + self.player.throttle * 6500
        )
        self.player.speed_kmh = (
            70
            + self.player.throttle * 250
        )
        self.player.gear = max(
            1,
            min(
                7,
                int(
                    self.player.speed_kmh // 45
                )
                + 1,
            ),
        )

        self.manager.update_player_data(
            self.player
        )

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
