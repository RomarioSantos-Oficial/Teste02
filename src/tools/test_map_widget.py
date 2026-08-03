#  SectorFlow is an open-source overlay application for racing simulation.
#  Copyright (C) 2022-2026 SectorFlow developers
#  Based on TinyPedal - Copyright (C) 2022-2026 TinyPedal developers
#
#  This file is part of SectorFlow.
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import (
    Qt,
    QTimer,
)
from PySide6.QtGui import (
    QKeySequence,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

PROJECT_ROOT = Path(
    __file__
).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )

from src.telemetry.models import PlayerData
from src.widget.map.map_editor import MapEditor
from src.widget.map.map_widget import TrackMapWidget


@dataclass
class Driver:
    slot_id: int
    driver_name: str
    vehicle_class: str
    position: int
    position_in_class: int
    laps: int
    lap_distance_m: float
    current_sector: int
    world_x: float
    world_z: float
    path_lateral_m: float = 0.0
    in_pits: bool = False
    in_garage: bool = False
    pit_state: int = 0
    under_yellow: bool = False
    flag: int = 0
    is_player: bool = False


@dataclass
class Session:
    track_name: str = "Test Endurance Circuit"
    session: int = 10
    max_laps: int = 30
    current_time_s: float = 0.0
    track_length_m: float = 6000.0
    in_realtime: bool = True
    player: PlayerData | None = None
    drivers: list[Driver] = field(
        default_factory=list
    )


class TestWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle(
            "Teste Track Map Widget V1"
        )
        self.resize(430, 420)
        layout = QVBoxLayout(self)

        self.status = QLabel(
            "Primeira volta: o mapa está sendo aprendido."
        )
        smaller = QPushButton(
            "Diminuir widget"
        )
        larger = QPushButton(
            "Aumentar widget"
        )
        rotate = QPushButton(
            "Girar mapa 15°"
        )
        editor_button = QPushButton(
            "Abrir editor"
        )

        for widget in (
            self.status,
            smaller,
            larger,
            rotate,
            editor_button,
        ):
            layout.addWidget(widget)

        config = json.loads(
            (
                PROJECT_ROOT
                / "src"
                / "config"
                / "map_defaults.json"
            ).read_text(
                encoding="utf-8"
            )
        )
        config["enabled"] = True
        config["click_through"] = False
        config["save_map_cache"] = False
        config["minimum_mapping_points"] = 80

        self.player = PlayerData(
            lap=1
        )
        self.session = Session(
            player=self.player
        )
        classes = [
            "HYPERCAR",
            "LMGT3",
            "LMP2",
            "LMGT3",
            "HYPERCAR",
            "LMP2",
        ]

        for index in range(6):
            self.session.drivers.append(
                Driver(
                    slot_id=index,
                    driver_name=f"Driver {index + 1}",
                    vehicle_class=classes[index],
                    position=index + 1,
                    position_in_class=(
                        1
                        + sum(
                            1
                            for previous
                            in classes[:index]
                            if previous == classes[index]
                        )
                    ),
                    laps=1,
                    lap_distance_m=index * 800.0,
                    current_sector=1,
                    world_x=0.0,
                    world_z=0.0,
                    is_player=index == 2,
                    under_yellow=index == 4,
                    flag=2 if index == 4 else 0,
                )
            )

        self.map_widget = TrackMapWidget(
            "map",
            config,
        )
        screen = QApplication.primaryScreen()
        self.map_widget.apply_normalized_geometry(
            screen.geometry()
        )
        self.map_widget.show()

        self.editor = MapEditor(
            config,
            self,
        )
        self.editor.config_changed.connect(
            self.map_widget.update_config
        )

        smaller.clicked.connect(
            lambda:
            self.map_widget.resize(
                max(
                    self.map_widget.minimumWidth(),
                    self.map_widget.width() - 70,
                ),
                max(
                    self.map_widget.minimumHeight(),
                    self.map_widget.height() - 70,
                ),
            )
        )
        larger.clicked.connect(
            lambda:
            self.map_widget.resize(
                self.map_widget.width() + 70,
                self.map_widget.height() + 70,
            )
        )
        rotate.clicked.connect(
            self.rotate_map
        )
        editor_button.clicked.connect(
            self.editor.show
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

        self.timer = QTimer(self)
        self.timer.timeout.connect(
            self.tick
        )
        self.timer.start(35)

    def track_point(
        self,
        progress: float,
    ) -> tuple[float, float]:
        angle = progress * math.tau
        radius_x = 470 + 90 * math.sin(angle * 3)
        radius_y = 280 + 60 * math.cos(angle * 2)
        return (
            math.cos(angle) * radius_x,
            math.sin(angle) * radius_y,
        )

    def tick(self) -> None:
        self.session.current_time_s += 0.035

        for index, driver in enumerate(
            self.session.drivers
        ):
            progress = (
                driver.lap_distance_m
                / self.session.track_length_m
            ) % 1.0
            x, y = self.track_point(progress)
            driver.world_x = x
            driver.world_z = -y
            driver.current_sector = (
                1
                if progress < 0.33
                else 2
                if progress < 0.66
                else 3
            )
            driver.lap_distance_m += (
                10.0 + index * 0.3
            )

            if (
                driver.lap_distance_m
                >= self.session.track_length_m
            ):
                driver.lap_distance_m -= (
                    self.session.track_length_m
                )
                driver.laps += 1

                if driver.is_player:
                    self.player.lap += 1
                    self.status.setText(
                        f"Volta {self.player.lap}: "
                        "mapa real e carros em movimento."
                    )

        self.map_widget.update_from_session(
            self.session
        )

    def rotate_map(self) -> None:
        config = dict(
            self.map_widget.config
        )
        config["display_orientation"] = (
            int(
                config.get(
                    "display_orientation",
                    0,
                )
            )
            + 15
        ) % 360
        self.map_widget.update_config(
            config
        )

    def toggle_edit(self) -> None:
        self.map_widget.set_edit_mode(
            not self.map_widget.edit_mode
        )

    def closeEvent(
        self,
        event,
    ) -> None:
        self.map_widget.close()
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
