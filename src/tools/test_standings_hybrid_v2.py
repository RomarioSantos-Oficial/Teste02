# SectorFlow is an open-source overlay application for racing simulation.
# Copyright (C) 2022-2026 SectorFlow developers
# Based on the user-provided Standings Hybrid reference.
#
# This file is part of SectorFlow.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.


from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.telemetry.models import DriverData, PlayerData, SessionData
from src.widget.standings.standings_editor import StandingsEditor
from src.widget.standings.standings_models import DriverMetadata
from src.widget.standings.standings_widget import StandingsWidget


class TestWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Teste Standings Hybrid Classic V2")
        self.resize(380, 300)
        layout = QVBoxLayout(self)
        buttons = [QPushButton("Aumentar"), QPushButton("Diminuir"), QPushButton("Trocar posições"), QPushButton("Abrir editor")]
        for button in buttons:
            layout.addWidget(button)
        config = json.loads((PROJECT_ROOT / "src" / "config" / "standings_defaults.json").read_text(encoding="utf-8"))
        config["enabled"] = True
        config["click_through"] = False
        self.session = SessionData(
            connected=True, track_name="Circuit de la Sarthe", session=10,
            remaining_time_s=6819, max_laps=0, track_length_m=13626,
            time_of_day=51240, avg_path_wetness=0.0, raining=0.0,
            in_realtime=True, player=PlayerData(battery_fraction=0.307),
            drivers=[
                DriverData(slot_id=7, driver_name="Hyper Leader", vehicle_name="Ferrari 499P #50", vehicle_class="Hypercar", position=1, laps=15, lap_distance_m=7000, best_lap_s=194.765, last_lap_s=194.699),
                DriverData(slot_id=13, driver_name="Hyper Driver", vehicle_name="Porsche 963 #13", vehicle_class="Hypercar", position=2, laps=15, lap_distance_m=6500, gap_leader_s=1.2, best_lap_s=194.879, last_lap_s=194.869),
                DriverData(slot_id=11, driver_name="Mariana Batolomeu", vehicle_name="Ligier JS P320 #11", vehicle_class="LMP3", position=3, laps=11, best_lap_s=204.765, last_lap_s=205.179),
                DriverData(slot_id=22, driver_name="Nicolas Bratutas", vehicle_name="Duqueine D08 #22", vehicle_class="LMP3", position=4, laps=11, gap_leader_s=15.5, best_lap_s=205.879, last_lap_s=205.879),
                DriverData(slot_id=10, driver_name="Fernando Alonso", vehicle_name="Alpine A110 GT3 #10", vehicle_class="LMGT3", position=5, laps=10, best_lap_s=210.671, last_lap_s=212.279),
                DriverData(slot_id=1, driver_name="Mariano filicionano", vehicle_name="McLaren 720S GT3 #1", vehicle_class="LMGT3", position=15, laps=9, best_lap_s=210.361, last_lap_s=210.361, gap_leader_s=4.7),
                DriverData(slot_id=64, driver_name="Jonas Manuel", vehicle_name="Lexus RCF GT3 #64", vehicle_class="LMGT3", position=16, laps=9, best_lap_s=211.940, last_lap_s=211.999, gap_leader_s=5.2, penalties=1),
                DriverData(slot_id=17, driver_name="Player Test", vehicle_name="BMW M4 GT3 #17", vehicle_class="LMGT3", position=17, laps=9, best_lap_s=208.112, last_lap_s=209.123, gap_leader_s=5.2, is_player=True),
                DriverData(slot_id=2, driver_name="Xun Lee", vehicle_name="Aston Martin Vantage GT3 #2", vehicle_class="LMGT3", position=18, laps=8, best_lap_s=210.121, last_lap_s=212.619, gap_leader_s=12.4),
                DriverData(slot_id=19, driver_name="Atonio Solavares", vehicle_name="Lamborghini Huracan GT3 #19", vehicle_class="LMGT3", position=19, laps=8, best_lap_s=214.619, last_lap_s=215.926, gap_leader_s=17.4, in_pits=True),
            ],
        )
        metadata = [
            DriverMetadata(driver_name="Hyper Leader", country_code="BR", badge="Staff", energy_percent=54.0, damage_percent=0, manufacturer="Ferrari"),
            DriverMetadata(driver_name="Hyper Driver", country_code="FR", badge="Creator", energy_percent=56.4, damage_percent=3, manufacturer="Porsche"),
            DriverMetadata(driver_name="Mariana Batolomeu", country_code="PT", badge="Pro", energy_percent=None, damage_percent=0, manufacturer="Ligier", tyre_compound="Medium"),
            DriverMetadata(driver_name="Nicolas Bratutas", country_code="ES", badge="", energy_percent=None, damage_percent=0, manufacturer="Duqueine", tyre_compound="Medium"),
            DriverMetadata(driver_name="Fernando Alonso", country_code="ES", badge="Legend", energy_percent=54.6, damage_percent=1, manufacturer="Alpine"),
            DriverMetadata(driver_name="Mariano filicionano", country_code="BR", badge="", energy_percent=4.6, damage_percent=0, manufacturer="McLaren"),
            DriverMetadata(driver_name="Jonas Manuel", country_code="DE", badge="Probation", energy_percent=19.6, damage_percent=12, manufacturer="Lexus"),
            DriverMetadata(driver_name="Player Test", country_code="BR", badge="Creator", energy_percent=30.7, damage_percent=15, manufacturer="BMW"),
            DriverMetadata(driver_name="Xun Lee", country_code="CN", badge="", energy_percent=0.1, damage_percent=0, manufacturer="Aston Martin"),
            DriverMetadata(driver_name="Atonio Solavares", country_code="IT", badge="", energy_percent=5.0, damage_percent=13, manufacturer="Lamborghini"),
        ]
        self.overlay = StandingsWidget("standings", config)
        self.overlay.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        screen = QApplication.primaryScreen()
        self.overlay.apply_normalized_geometry(screen.geometry())
        self.overlay.set_preview_data(self.session, metadata)
        self.overlay.show()
        self.editor = StandingsEditor(config, self)
        self.editor.config_changed.connect(self.overlay.update_config)
        buttons[0].clicked.connect(lambda: self.overlay.resize(self.overlay.width() + 120, self.overlay.height() + 60))
        buttons[1].clicked.connect(lambda: self.overlay.resize(max(self.overlay.minimumWidth(), self.overlay.width() - 120), max(self.overlay.minimumHeight(), self.overlay.height() - 60)))
        buttons[2].clicked.connect(self.swap_positions)
        buttons[3].clicked.connect(self.editor.show)
        self.shortcut = QShortcut(QKeySequence("F12"), self)
        self.shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self.shortcut.activated.connect(lambda: self.overlay.set_edit_mode(not self.overlay.edit_mode))

    def swap_positions(self) -> None:
        player = next(driver for driver in self.session.drivers if driver.is_player)
        player.position = 15 if player.position == 17 else 17
        self.overlay.set_preview_data(self.session, list(self.overlay.enrichment.snapshot()[0].values()))

    def closeEvent(self, event) -> None:
        self.overlay.close()
        event.accept()


def main() -> None:
    app = QApplication(sys.argv)
    window = TestWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
