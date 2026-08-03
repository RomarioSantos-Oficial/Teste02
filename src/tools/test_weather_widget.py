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
from dataclasses import dataclass
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

from src.widget.weather.weather_editor import (
    WeatherEditor,
)
from src.widget.weather.weather_widget import (
    WeatherWidget,
)


@dataclass
class FakeSession:
    track_name: str = "Le Mans"
    session: int = 10
    max_laps: int = 24
    track_temp_c: float = 34.5
    ambient_temp_c: float = 24.0
    raining: float = 0.0
    avg_path_wetness: float = 0.0
    dark_cloud: float = 0.05
    cloud_coverage: int = 0
    time_of_day: float = 14 * 3600
    wind_speed_kmh: float = 12.0


class TestWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle(
            "Teste Weather Widget V1"
        )
        self.resize(430, 380)

        layout = QVBoxLayout(self)
        self.status = QLabel(
            "Estado: SECO"
        )
        next_button = QPushButton(
            "Próximo clima"
        )
        smaller = QPushButton(
            "Diminuir widget"
        )
        larger = QPushButton(
            "Aumentar widget"
        )
        editor_button = QPushButton(
            "Abrir editor"
        )

        layout.addWidget(
            self.status
        )
        layout.addWidget(
            next_button
        )
        layout.addWidget(
            smaller
        )
        layout.addWidget(
            larger
        )
        layout.addWidget(
            editor_button
        )

        config = json.loads(
            (
                PROJECT_ROOT
                / "src"
                / "config"
                / "weather_defaults.json"
            ).read_text(
                encoding="utf-8"
            )
        )
        config["enabled"] = True
        config["click_through"] = False

        self.weather = WeatherWidget(
            "weather",
            config,
        )
        screen = (
            QApplication.primaryScreen()
        )
        self.weather.apply_normalized_geometry(
            screen.geometry()
        )
        self.weather.show()

        self.editor = WeatherEditor(
            config,
            self,
        )
        self.editor.config_changed.connect(
            self.weather.update_config
        )

        self.session = FakeSession()
        self.states = [
            "dry",
            "cloud",
            "rain",
            "wet",
            "night",
        ]
        self.index = -1

        next_button.clicked.connect(
            self.next_state
        )
        smaller.clicked.connect(
            lambda:
            self.weather.resize(
                max(
                    self.weather.minimumWidth(),
                    self.weather.width() - 90,
                ),
                self.weather.height(),
            )
        )
        larger.clicked.connect(
            lambda:
            self.weather.resize(
                self.weather.width() + 90,
                self.weather.height(),
            )
        )
        editor_button.clicked.connect(
            self.editor.show
        )

        shortcut = QShortcut(
            QKeySequence("F12"),
            self,
        )
        shortcut.setContext(
            Qt.ShortcutContext.ApplicationShortcut
        )
        shortcut.activated.connect(
            self.toggle_edit
        )
        self.shortcut = shortcut

        self.timer = QTimer(self)
        self.timer.timeout.connect(
            self.tick
        )
        self.timer.start(500)

        self.next_state()

    def next_state(self) -> None:
        self.index = (
            self.index + 1
        ) % len(self.states)
        state = self.states[
            self.index
        ]

        self.session.raining = 0.0
        self.session.avg_path_wetness = 0.0
        self.session.dark_cloud = 0.05
        self.session.cloud_coverage = 0
        self.session.time_of_day = (
            14 * 3600
        )

        if state == "cloud":
            self.session.dark_cloud = 0.55
            self.session.cloud_coverage = 4
        elif state == "rain":
            self.session.raining = 0.55
            self.session.avg_path_wetness = 0.25
            self.session.dark_cloud = 0.90
            self.session.cloud_coverage = 8
        elif state == "wet":
            self.session.avg_path_wetness = 0.42
            self.session.dark_cloud = 0.30
            self.session.cloud_coverage = 2
        elif state == "night":
            self.session.time_of_day = (
                22 * 3600
            )

        self.status.setText(
            f"Estado: {state.upper()}"
        )
        self.weather.update_from_session(
            self.session
        )

    def tick(self) -> None:
        # Cria uma tendência real de teste durante chuva.
        if self.session.raining > 0:
            self.session.raining = min(
                1.0,
                self.session.raining + 0.005,
            )
            self.session.avg_path_wetness = min(
                1.0,
                self.session.avg_path_wetness
                + 0.004,
            )
            self.session.ambient_temp_c -= 0.01

        self.weather.update_from_session(
            self.session
        )

    def toggle_edit(self) -> None:
        self.weather.set_edit_mode(
            not self.weather.edit_mode
        )

    def closeEvent(
        self,
        event,
    ) -> None:
        self.weather.close()
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
