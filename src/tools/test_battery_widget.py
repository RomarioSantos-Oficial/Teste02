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

from src.telemetry.models import (
    PlayerData,
)
from src.widget.battery.battery_editor import (
    BatteryEditor,
)
from src.widget.battery.battery_widget import (
    BatteryWidget,
)


@dataclass
class Driver:
    vehicle_class: str = "HYPERCAR"
    lap_distance_m: float = 0.0
    in_pits: bool = False
    in_garage: bool = False
    is_player: bool = True


@dataclass
class Session:
    track_name: str = "Le Mans"
    session: int = 10
    max_laps: int = 24
    current_time_s: float = 0.0
    track_length_m: float = 13626.0
    player: PlayerData | None = None
    drivers: list[Driver] = field(
        default_factory=list
    )


class TestWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle(
            "Teste Battery Hybrid V1"
        )
        self.resize(430, 400)
        layout = QVBoxLayout(self)

        self.status = QLabel(
            "Simulando duas voltas"
        )
        smaller = QPushButton(
            "Diminuir widget"
        )
        larger = QPushButton(
            "Aumentar widget"
        )
        boost = QPushButton(
            "Alternar BOOST/REGEN"
        )
        new_lap = QPushButton(
            "Finalizar volta"
        )
        editor = QPushButton(
            "Abrir editor"
        )

        for widget in (
            self.status,
            smaller,
            larger,
            boost,
            new_lap,
            editor,
        ):
            layout.addWidget(widget)

        config = json.loads(
            (
                PROJECT_ROOT
                / "src"
                / "config"
                / "battery_defaults.json"
            ).read_text(
                encoding="utf-8"
            )
        )
        config["enabled"] = True
        config["click_through"] = False
        config["always_show"] = True

        self.player = PlayerData(
            vehicle_name="Hypercar Test",
            vehicle_model="LMDh",
            lap=1,
            battery_fraction=0.78,
            state_of_charge=78.0,
            virtual_energy=0.64,
            regen_kw=0.0,
            electric_motor_torque_nm=285.0,
            electric_motor_rpm=5600.0,
            electric_motor_temp_c=70.0,
            electric_motor_water_temp_c=58.0,
            electric_motor_state=2,
        )
        self.driver = Driver()
        self.session = Session(
            player=self.player,
            drivers=[
                self.driver
            ],
        )

        self.battery = BatteryWidget(
            "battery",
            config,
        )
        screen = (
            QApplication.primaryScreen()
        )
        self.battery.apply_normalized_geometry(
            screen.geometry()
        )
        self.battery.show()

        self.editor_window = BatteryEditor(
            config,
            self,
        )
        self.editor_window.config_changed.connect(
            self.battery.update_config
        )

        smaller.clicked.connect(
            lambda:
            self.battery.resize(
                max(
                    self.battery.minimumWidth(),
                    self.battery.width() - 80,
                ),
                self.battery.height(),
            )
        )
        larger.clicked.connect(
            lambda:
            self.battery.resize(
                self.battery.width() + 80,
                self.battery.height(),
            )
        )
        boost.clicked.connect(
            self.toggle_motor
        )
        new_lap.clicked.connect(
            self.finish_lap
        )
        editor.clicked.connect(
            self.editor_window.show
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
        self.timer.start(200)

    def tick(self) -> None:
        self.session.current_time_s += 0.2
        self.driver.lap_distance_m += 55.0

        if (
            self.driver.lap_distance_m
            >= self.session.track_length_m
        ):
            self.finish_lap()
            return

        if (
            self.player.electric_motor_state
            == 3
        ):
            self.player.battery_fraction = min(
                1.0,
                self.player.battery_fraction
                + 0.00035,
            )
            self.player.regen_kw = 48.0
            self.player.electric_motor_torque_nm = (
                -120.0
            )
        else:
            multiplier = (
                1.15
                if self.player.lap >= 2
                else 1.0
            )
            self.player.battery_fraction = max(
                0.0,
                self.player.battery_fraction
                - 0.00055
                * multiplier,
            )
            self.player.regen_kw = 0.0
            self.player.electric_motor_torque_nm = (
                285.0
            )

        self.player.state_of_charge = (
            self.player.battery_fraction
            * 100.0
        )
        self.battery.update_from_session(
            self.session
        )

    def toggle_motor(self) -> None:
        self.player.electric_motor_state = (
            3
            if self.player.electric_motor_state
            == 2
            else 2
        )

    def finish_lap(self) -> None:
        self.player.lap += 1
        self.driver.lap_distance_m = 0.0
        self.status.setText(
            f"Volta atual: "
            f"{self.player.lap}"
        )
        self.battery.update_from_session(
            self.session
        )

    def toggle_edit(self) -> None:
        self.battery.set_edit_mode(
            not self.battery.edit_mode
        )

    def closeEvent(
        self,
        event,
    ) -> None:
        self.battery.close()
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
