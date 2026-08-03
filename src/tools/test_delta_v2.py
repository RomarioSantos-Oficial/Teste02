from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ui.edit_mode_manager import EditModeManager
from src.widget.delta.delta_editor import DeltaEditor
from src.widget.delta.delta_widget import DeltaWidget


@dataclass
class FakePlayer:
    delta_best_s: float = 0.0
    sector_deltas: list[float | None] = field(default_factory=lambda: [None, None, None])


@dataclass
class FakeDriver:
    driver_name: str
    vehicle_name: str
    vehicle_class: str
    position: int
    best_lap_s: float = 0.0
    penalties: int = 0
    is_player: bool = False


@dataclass
class FakeSession:
    track_name: str = "Le Mans"
    session: int = 10
    current_time_s: float = 0.0
    remaining_time_s: float = 7200.0
    max_laps: int = 0
    raining: float = 0.0
    track_grip_level: int = 3
    player: FakePlayer = field(default_factory=FakePlayer)
    drivers: list[FakeDriver] = field(default_factory=list)


class DeltaV2Test(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Teste Delta V2")
        self.resize(380, 190)

        layout = QVBoxLayout(self)
        edit = QPushButton("Abrir editor")
        edit_mode = QPushButton("Modo edição (F12)")
        new_session = QPushButton("Simular nova sessão")
        clear = QPushButton("Limpar histórico")
        layout.addWidget(edit)
        layout.addWidget(edit_mode)
        layout.addWidget(new_session)
        layout.addWidget(clear)

        import json

        config = json.loads(
            (PROJECT_ROOT / "src" / "config" / "delta_v2_defaults.json").read_text(
                encoding="utf-8"
            )
        )
        config["click_through"] = False

        self.delta = DeltaWidget("delta", config)
        screen = QApplication.primaryScreen()
        self.delta.apply_normalized_geometry(screen.geometry())
        self.delta.show()

        self.editor = DeltaEditor(config, self)
        self.editor.config_changed.connect(self.delta.update_config)
        edit.clicked.connect(self.editor.show)

        self.edit_manager = EditModeManager(self)
        self.edit_manager.register_widget(self.delta)
        edit_mode.clicked.connect(self.edit_manager.toggle)

        new_session.clicked.connect(self.simulate_new_session)
        clear.clicked.connect(self.delta.clear_history)

        self.session = FakeSession(
            drivers=[
                FakeDriver(
                    driver_name="R. Santos",
                    vehicle_name="BMW M Hybrid V8",
                    vehicle_class="Hypercar",
                    position=2,
                    is_player=True,
                ),
                FakeDriver(
                    driver_name="A. Martin",
                    vehicle_name="Ferrari 499P",
                    vehicle_class="Hypercar",
                    position=1,
                ),
                FakeDriver(
                    driver_name="GT Driver",
                    vehicle_name="Porsche 911 GT3",
                    vehicle_class="LMGT3",
                    position=18,
                ),
            ]
        )

        self.elapsed = 0.0
        self.event_stage = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_simulation)
        self.timer.start(50)

    def update_simulation(self) -> None:
        self.elapsed += 0.05
        self.session.current_time_s += 0.05
        self.session.remaining_time_s = max(0.0, self.session.remaining_time_s - 0.05)

        self.session.player.delta_best_s = math.sin(self.elapsed * 0.75) * 1.1
        self.session.player.sector_deltas = [
            math.sin(self.elapsed * 0.45) * 0.18,
            math.sin(self.elapsed * 0.45 + 1.5) * 0.22,
            math.sin(self.elapsed * 0.45 + 3.0) * 0.16,
        ]

        if self.elapsed >= 3.0 and self.event_stage == 0:
            self.session.drivers[0].best_lap_s = 88.111
            self.event_stage = 1

        if self.elapsed >= 10.0 and self.event_stage == 1:
            self.session.drivers[1].best_lap_s = 87.900
            self.event_stage = 2

        self.delta.update_from_session(self.session)

    def simulate_new_session(self) -> None:
        self.session.session = 5 if self.session.session == 10 else 10
        self.session.current_time_s = 0.0
        self.session.remaining_time_s = 1800.0
        for driver in self.session.drivers:
            driver.best_lap_s = 0.0
        self.elapsed = 0.0
        self.event_stage = 0

    def closeEvent(self, event) -> None:
        self.delta.close()
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    window = DeltaV2Test()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
