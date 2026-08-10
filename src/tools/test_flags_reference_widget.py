from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.widget.flags.flags_editor import FlagsEditor
from src.widget.flags.flags_widget import FlagsWidget


@dataclass
class Driver:
    driver_name: str
    vehicle_class: str
    position: int
    position_in_class: int
    lap_distance_m: float
    path_lateral_m: float
    speed_kmh: float
    current_sector: int = 1
    flag: int = 0
    pit_state: int = 0
    individual_phase: int = 0
    under_yellow: bool = False
    in_pits: bool = False
    in_garage: bool = False
    is_player: bool = False
    world_x: float = 0.0
    world_y: float = 0.0
    world_z: float = 0.0
    right_x: float = 1.0
    right_y: float = 0.0
    right_z: float = 0.0
    forward_x: float = 0.0
    forward_y: float = 0.0
    forward_z: float = 1.0


@dataclass
class Session:
    track_name: str = "Le Mans"
    session: int = 10
    max_laps: int = 24
    current_time_s: float = 30.0
    track_length_m: float = 13626.0
    game_phase: int = 5
    sector_flags: tuple[int, int, int] = (0, 0, 0)
    drivers: list[Driver] = field(default_factory=list)


class TestWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Teste Flags V2 - Referência")
        self.resize(390, 270)

        layout = QVBoxLayout(self)
        self.status = QLabel()
        next_button = QPushButton("Próximo estado")
        editor_button = QPushButton("Abrir editor")
        layout.addWidget(self.status)
        layout.addWidget(next_button)
        layout.addWidget(editor_button)

        config = json.loads(
            (
                PROJECT_ROOT
                / "src"
                / "config"
                / "flags_reference_defaults.json"
            ).read_text(encoding="utf-8")
        )
        config["enabled"] = True
        config["click_through"] = False
        config["auto_hide_when_clear"] = False

        self.flags = FlagsWidget("flags", config)
        screen = QApplication.primaryScreen()
        self.flags.apply_normalized_geometry(screen.geometry())
        self.flags.show()

        self.editor = FlagsEditor(config, self)
        self.editor.config_changed.connect(
            self.flags.update_config
        )
        editor_button.clicked.connect(self.editor.show)
        next_button.clicked.connect(self.next_state)

        self.shortcut = QShortcut(QKeySequence("F12"), self)
        self.shortcut.setContext(
            Qt.ShortcutContext.ApplicationShortcut
        )
        self.shortcut.activated.connect(self.toggle_edit)

        self.player = Driver(
            driver_name="Player Test",
            vehicle_class="LMGT3",
            position=14,
            position_in_class=7,
            lap_distance_m=5000,
            path_lateral_m=0,
            speed_kmh=210,
            is_player=True,
            world_z=0,
        )
        self.yellow_car = Driver(
            driver_name="Mattia Drudi",
            vehicle_class="LMGT3",
            position=11,
            position_in_class=4,
            lap_distance_m=5184,
            path_lateral_m=-1.5,
            speed_kmh=8,
            current_sector=2,
            world_x=-1.5,
            world_z=184,
        )
        self.blue_car = Driver(
            driver_name="Mike Conway",
            vehicle_class="HYPERCAR",
            position=2,
            position_in_class=2,
            lap_distance_m=4908,
            path_lateral_m=1.2,
            speed_kmh=285,
            world_x=1.2,
            world_z=-92,
        )
        self.session = Session(
            drivers=[
                self.player,
                self.yellow_car,
                self.blue_car,
            ]
        )

        self.states = [
            "yellow",
            "blue",
            "yellow_blue",
            "green",
            "clear",
        ]
        self.index = -1

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(100)

        self.next_state()

    def next_state(self) -> None:
        self.index = (self.index + 1) % len(self.states)
        state = self.states[self.index]

        self.session.sector_flags = (0, 0, 0)
        self.player.flag = 0
        self.session.game_phase = 5
        self.yellow_car.speed_kmh = 120

        if state == "yellow":
            self.session.sector_flags = (0, 1, 0)
            self.yellow_car.speed_kmh = 8
        elif state == "blue":
            self.player.flag = 6
        elif state == "yellow_blue":
            self.session.sector_flags = (0, 1, 0)
            self.yellow_car.speed_kmh = 8
            self.player.flag = 6
        elif state == "green":
            self.session.game_phase = 4
            self.flags.update_from_session(self.session)
            self.session.game_phase = 5

        self.status.setText(f"Estado: {state.upper()}")
        self.flags.update_from_session(self.session)

    def tick(self) -> None:
        self.session.current_time_s += 0.1
        self.flags.update_from_session(self.session)

    def toggle_edit(self) -> None:
        self.flags.set_edit_mode(not self.flags.edit_mode)

    def closeEvent(self, event) -> None:
        self.flags.close()
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
