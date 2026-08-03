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
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QKeySequence,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
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
    WheelData,
)
from src.widget.tyres.tyres_editor import (
    TyresEditor,
)
from src.widget.tyres.tyres_widget import (
    TyresWidget,
)


class TestWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle(
            "Teste Tyres Widget V1"
        )
        self.resize(410, 340)
        layout = QVBoxLayout(self)

        smaller = QPushButton(
            "Diminuir widget"
        )
        larger = QPushButton(
            "Aumentar widget"
        )
        heat = QPushButton(
            "Aquecer pneus e freios"
        )
        wear = QPushButton(
            "Aplicar desgaste"
        )
        editor = QPushButton(
            "Abrir editor"
        )

        for button in (
            smaller,
            larger,
            heat,
            wear,
            editor,
        ):
            layout.addWidget(button)

        config = json.loads(
            (
                PROJECT_ROOT
                / "src"
                / "config"
                / "tyres_defaults.json"
            ).read_text(
                encoding="utf-8"
            )
        )
        config["enabled"] = True
        config["click_through"] = False

        self.player = PlayerData(
            front_tire_compound="MEDIUM",
            rear_tire_compound="MEDIUM",
            wheels=[
                self._wheel(
                    78.0,
                    0.03,
                    420,
                    176,
                ),
                self._wheel(
                    80.0,
                    0.04,
                    440,
                    177,
                ),
                self._wheel(
                    85.0,
                    0.07,
                    505,
                    173,
                ),
                self._wheel(
                    87.0,
                    0.08,
                    525,
                    174,
                ),
            ],
        )

        self.tyres = TyresWidget(
            "tires",
            config,
        )
        screen = (
            QApplication.primaryScreen()
        )
        self.tyres.apply_normalized_geometry(
            screen.geometry()
        )
        self.tyres.update_telemetry(
            self.player
        )
        self.tyres.show()

        self.editor_window = TyresEditor(
            config,
            self,
        )
        self.editor_window.config_changed.connect(
            self.tyres.update_config
        )

        smaller.clicked.connect(
            lambda:
            self.tyres.resize(
                max(
                    self.tyres.minimumWidth(),
                    self.tyres.width() - 70,
                ),
                self.tyres.height(),
            )
        )
        larger.clicked.connect(
            lambda:
            self.tyres.resize(
                self.tyres.width() + 70,
                self.tyres.height(),
            )
        )
        heat.clicked.connect(
            self.heat_up
        )
        wear.clicked.connect(
            self.apply_wear
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

    @staticmethod
    def _wheel(
        temp_c: float,
        wear: float,
        brake_c: float,
        pressure_kpa: float,
    ) -> WheelData:
        return WheelData(
            pressure_kpa=pressure_kpa,
            wear=wear,
            brake_temp_c=brake_c,
            surface_left_c=temp_c - 2,
            surface_center_c=temp_c,
            surface_right_c=temp_c + 1,
            inner_left_c=temp_c - 1,
            inner_center_c=temp_c,
            inner_right_c=temp_c + 1,
            carcass_temp_c=temp_c - 4,
            optimal_temp_c=82.0,
            brake_pressure=0.42,
            tire_load_n=3200,
            grip_fraction=0.08,
            camber_rad=-0.052,
            toe_rad=0.002,
            suspension_deflection_m=0.028,
            vertical_tire_deflection_m=0.012,
            ride_height_m=0.065,
            rotation_rad_s=-82,
            compound_index=1,
            compound_type=1,
        )

    def heat_up(self) -> None:
        for wheel in self.player.wheels:
            wheel.surface_left_c += 7
            wheel.surface_center_c += 7
            wheel.surface_right_c += 7
            wheel.inner_left_c += 7
            wheel.inner_center_c += 7
            wheel.inner_right_c += 7
            wheel.carcass_temp_c += 5
            wheel.brake_temp_c += 130

        self.tyres.update_telemetry(
            self.player
        )

    def apply_wear(self) -> None:
        for wheel in self.player.wheels:
            wheel.wear = min(
                1.0,
                wheel.wear + 0.16,
            )

        self.tyres.update_telemetry(
            self.player
        )

    def toggle_edit(self) -> None:
        self.tyres.set_edit_mode(
            not self.tyres.edit_mode
        )

    def closeEvent(
        self,
        event,
    ) -> None:
        self.tyres.close()
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
