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
class FakePlayer:
    speed_kmh: float = 210.0


@dataclass
class FakeDriver:
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


@dataclass
class FakeSession:
    track_name: str = "Le Mans"
    session: int = 10
    max_laps: int = 24
    current_time_s: float = 0.0
    track_length_m: float = 13626.0
    game_phase: int = 5
    yellow_flag_state: int = 0
    sector_flags: tuple[int, int, int] = (0, 0, 0)
    player: FakePlayer = field(
        default_factory=FakePlayer
    )
    drivers: list[FakeDriver] = field(
        default_factory=list
    )


class FlagsTestWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle(
            "Teste Flags V1"
        )
        self.resize(390, 320)

        layout = QVBoxLayout(self)
        self.status = QLabel()
        layout.addWidget(self.status)

        edit = QPushButton("Abrir editor")
        next_state = QPushButton(
            "Próxima bandeira"
        )
        layout.addWidget(edit)
        layout.addWidget(next_state)

        config = json.loads(
            (
                PROJECT_ROOT
                / "src"
                / "config"
                / "flags_defaults.json"
            ).read_text(
                encoding="utf-8"
            )
        )
        config["enabled"] = True
        config["click_through"] = False
        config["auto_hide_when_clear"] = False

        self.flags = FlagsWidget(
            "flags",
            config,
        )
        screen = QApplication.primaryScreen()
        self.flags.apply_normalized_geometry(
            screen.geometry()
        )
        self.flags.show()

        self.editor = FlagsEditor(
            config,
            self,
        )
        self.editor.config_changed.connect(
            self.flags.update_config
        )
        edit.clicked.connect(
            self.editor.show
        )
        next_state.clicked.connect(
            self.next_state
        )

        self.shortcut = QShortcut(
            QKeySequence("F12"),
            self,
        )
        self.shortcut.setContext(
            Qt.ShortcutContext.ApplicationShortcut
        )
        self.shortcut.activated.connect(
            self.toggle_edit
        )

        self.session = FakeSession(
            drivers=[
                FakeDriver(
                    driver_name="Player Test",
                    vehicle_class="LMGT3",
                    position=14,
                    position_in_class=7,
                    lap_distance_m=5200,
                    path_lateral_m=0.0,
                    speed_kmh=210,
                    is_player=True,
                ),
                FakeDriver(
                    driver_name="Mattia Drudi",
                    vehicle_class="LMGT3",
                    position=11,
                    position_in_class=4,
                    lap_distance_m=5380,
                    path_lateral_m=-1.5,
                    speed_kmh=8,
                    current_sector=2,
                ),
                FakeDriver(
                    driver_name="Mike Conway",
                    vehicle_class="Hypercar",
                    position=2,
                    position_in_class=2,
                    lap_distance_m=5100,
                    path_lateral_m=1.0,
                    speed_kmh=285,
                ),
            ]
        )
        self.states = [
            "green",
            "yellow",
            "blue",
            "fcy",
            "red",
            "checkered",
            "clear",
        ]
        self.index = -1

        self.timer = QTimer(self)
        self.timer.timeout.connect(
            self.tick
        )
        self.timer.start(100)

        self.next_state()

    def next_state(self) -> None:
        self.index = (
            self.index + 1
        ) % len(self.states)
        current = self.states[self.index]

        self.session.game_phase = 5
        self.session.yellow_flag_state = 0
        self.session.sector_flags = (0, 0, 0)
        self.session.drivers[0].flag = 0

        if current == "green":
            self.session.game_phase = 4
            self.flags.update_from_session(
                self.session
            )
            self.session.game_phase = 5
        elif current == "yellow":
            self.session.sector_flags = (
                0,
                1,
                0,
            )
        elif current == "blue":
            self.session.drivers[0].flag = 6
        elif current == "fcy":
            self.session.game_phase = 6
            self.session.yellow_flag_state = 2
        elif current == "red":
            self.session.game_phase = 7
        elif current == "checkered":
            self.session.game_phase = 8

        self.status.setText(
            f"Estado atual: {current.upper()}"
        )
        self.flags.update_from_session(
            self.session
        )

    def tick(self) -> None:
        self.session.current_time_s += 0.1

        for driver in self.session.drivers:
            driver.lap_distance_m = (
                driver.lap_distance_m
                + driver.speed_kmh / 3.6 * 0.1
            ) % self.session.track_length_m

        self.flags.update_from_session(
            self.session
        )

    def toggle_edit(self) -> None:
        self.flags.set_edit_mode(
            not self.flags.edit_mode
        )

    def closeEvent(self, event) -> None:
        self.flags.close()
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    window = FlagsTestWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
