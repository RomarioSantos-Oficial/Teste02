from __future__ import annotations

import math
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.ui.edit_mode_manager import EditModeManager
from src.widget.delta.delta_editor import DeltaEditor
from src.widget.delta.delta_renderer import DeltaSectorData, DeltaViewData
from src.widget.delta.delta_widget import DeltaWidget


class DeltaTestWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Teste Delta Widget")
        self.resize(360, 160)

        layout = QVBoxLayout(self)
        edit = QPushButton("Abrir editor")
        edit_mode = QPushButton("Modo edição (F12)")
        layout.addWidget(edit)
        layout.addWidget(edit_mode)

        config_path = PROJECT_ROOT / "src" / "config" / "widgets_delta_example.json"

        import json
        config_data = json.loads(config_path.read_text(encoding="utf-8"))
        self.delta_config = config_data["widgets"]["delta"]

        self.delta = DeltaWidget("delta", self.delta_config)

        screen = QApplication.primaryScreen()
        self.delta.apply_normalized_geometry(screen.geometry())
        self.delta.show()

        self.edit_manager = EditModeManager(self)
        self.edit_manager.register_widget(self.delta)
        edit_mode.clicked.connect(self.edit_manager.toggle)

        self.editor = DeltaEditor(self.delta_config, self)
        self.editor.config_changed.connect(self._update_config)
        edit.clicked.connect(self.editor.show)

        self.time_value = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(50)

    def _update_config(self, config) -> None:
        self.delta_config = config
        self.delta.update_config(config)

    def animate(self) -> None:
        self.time_value += 0.04
        delta = math.sin(self.time_value) * 1.5

        sectors = [
            DeltaSectorData("S1", math.sin(self.time_value) * 0.20),
            DeltaSectorData("S2", math.sin(self.time_value + 1.4) * 0.28),
            DeltaSectorData("S3", math.sin(self.time_value + 2.8) * 0.18),
        ]

        data = DeltaViewData(
            delta_s=delta,
            session_time_text="01:53:39",
            session_name="Race",
            track_state="Dry",
            penalties=2,
            fastest_driver="R. Santos",
            fastest_vehicle="BMW",
            fastest_lap_text="1:28.111",
            fastest_position=2,
            sectors=sectors,
        )
        self.delta.update_delta_data(data)

    def closeEvent(self, event) -> None:
        self.delta.close()
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    window = DeltaTestWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
