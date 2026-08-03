from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.ui.edit_mode_manager import EditModeManager
from src.widget.delta.delta_editor import DeltaEditor
from src.widget.delta.delta_widget import DeltaWidget


@dataclass
class FakePlayer:
    delta_best_s: float = 0.0
    track_limits_steps: int = 0


@dataclass
class FakeDriver:
    driver_name: str
    vehicle_name: str
    vehicle_class: str
    vehicle_filename: str = ""
    pit_group: str = ""
    position: int
    best_lap_s: float = 0.0
    penalties: int = 0
    is_player: bool = False

    best_sector1_s: float = 0.0
    best_sector2_s: float = 0.0
    best_sector3_s: float = 0.0

    last_sector1_s: float = 0.0
    last_sector2_s: float = 0.0
    last_sector3_s: float = 0.0


@dataclass
class FakeSession:
    track_name: str = "Le Mans"
    session: int = 10
    current_time_s: float = 0.0
    remaining_time_s: float = 7200.0
    max_laps: int = 0
    raining: float = 0.0
    track_grip_level: int = 3

    track_limits_steps_per_penalty: int = 20
    track_limits_steps_per_point: int = 4

    player: FakePlayer = field(
        default_factory=FakePlayer
    )
    drivers: list[FakeDriver] = field(
        default_factory=list
    )

    @property
    def track_limits_current(self) -> float:
        return (
            self.player.track_limits_steps
            / max(
                1,
                self.track_limits_steps_per_point,
            )
        )

    @property
    def track_limits_limit(self) -> float:
        return (
            self.track_limits_steps_per_penalty
            / max(
                1,
                self.track_limits_steps_per_point,
            )
        )


class DeltaV21Test(QWidget):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle(
            "Teste Delta V2.2"
        )
        self.resize(400, 220)

        layout = QVBoxLayout(self)
        edit = QPushButton("Abrir editor")
        edit_mode = QPushButton(
            "Modo edição (F12)"
        )
        new_session = QPushButton(
            "Simular nova sessão"
        )
        add_limit = QPushButton(
            "Adicionar limite de pista"
        )
        clear = QPushButton(
            "Limpar histórico"
        )

        layout.addWidget(edit)
        layout.addWidget(edit_mode)
        layout.addWidget(new_session)
        layout.addWidget(add_limit)
        layout.addWidget(clear)

        config = json_load(
            PROJECT_ROOT
            / "src"
            / "config"
            / "delta_v2_defaults.json"
        )
        config["click_through"] = False

        self.delta = DeltaWidget(
            "delta",
            config,
        )
        screen = QApplication.primaryScreen()
        self.delta.apply_normalized_geometry(
            screen.geometry()
        )
        self.delta.show()

        self.editor = DeltaEditor(
            config,
            self,
        )
        self.editor.config_changed.connect(
            self.delta.update_config
        )
        edit.clicked.connect(
            self.editor.show
        )

        self.edit_manager = EditModeManager(
            self
        )
        self.edit_manager.register_widget(
            self.delta
        )
        edit_mode.clicked.connect(
            self.edit_manager.toggle
        )

        new_session.clicked.connect(
            self.simulate_new_session
        )
        add_limit.clicked.connect(
            self.add_track_limit
        )
        clear.clicked.connect(
            self.delta.clear_history
        )

        self.session = FakeSession(
            drivers=[
                FakeDriver(
                    driver_name="R. Santos",
                    vehicle_name="BMW M Hybrid V8",
                    vehicle_class="Hypercar",
                    vehicle_filename="BMW_M_Hybrid_V8.veh",
                    pit_group="BMW M Team",
                    position=2,
                    is_player=True,
                    best_sector1_s=29.400,
                    best_sector2_s=30.200,
                    best_sector3_s=28.511,
                ),
                FakeDriver(
                    driver_name="A. Martin",
                    vehicle_name="Ferrari 499P",
                    vehicle_class="Hypercar",
                    vehicle_filename="Ferrari_499P.veh",
                    pit_group="Ferrari AF Corse",
                    position=1,
                    best_sector1_s=29.100,
                    best_sector2_s=30.000,
                    best_sector3_s=28.400,
                ),
                FakeDriver(
                    driver_name="GT Driver",
                    vehicle_name="Porsche 911 GT3",
                    vehicle_class="LMGT3",
                    vehicle_filename="AstonMartin_Vantage_AMR_LMGT3.veh",
                    pit_group="Heart of Racing",
                    position=18,
                    best_sector1_s=35.000,
                    best_sector2_s=36.000,
                    best_sector3_s=34.000,
                ),
            ]
        )

        self.elapsed = 0.0
        self.event_stage = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(
            self.update_simulation
        )
        self.timer.start(50)

    def update_simulation(self) -> None:
        self.elapsed += 0.05
        self.session.current_time_s += 0.05
        self.session.remaining_time_s = max(
            0.0,
            self.session.remaining_time_s - 0.05,
        )

        # Positivo = pior: carrega vermelho para a esquerda.
        # Negativo = melhor: carrega verde para a direita.
        self.session.player.delta_best_s = (
            math.sin(self.elapsed * 0.75)
            * 1.1
        )

        player = self.session.drivers[0]

        if self.elapsed >= 2.0 and self.event_stage == 0:
            # Pior que o melhor pessoal: amarelo.
            player.last_sector1_s = 29.700
            self.event_stage = 1

        if self.elapsed >= 5.0 and self.event_stage == 1:
            # Novo melhor pessoal, mas não o melhor da categoria: verde.
            player.last_sector2_s = 30.100
            player.best_sector2_s = 30.100
            self.event_stage = 2

        if self.elapsed >= 8.0 and self.event_stage == 2:
            # Melhor da categoria: roxo.
            player.last_sector3_s = 28.300
            player.best_sector3_s = 28.300
            self.event_stage = 3

        if self.elapsed >= 3.0:
            player.best_lap_s = 88.111

        if self.elapsed >= 10.0:
            self.session.drivers[1].best_lap_s = 87.900

        self.delta.update_from_session(
            self.session
        )

    def add_track_limit(self) -> None:
        # Um passo bruto representa 0.25 ponto:
        # 1 / 4 = 0.25
        self.session.player.track_limits_steps = min(
            self.session.track_limits_steps_per_penalty,
            self.session.player.track_limits_steps + 1,
        )

    def simulate_new_session(self) -> None:
        self.session.session = (
            5
            if self.session.session == 10
            else 10
        )
        self.session.current_time_s = 0.0
        self.session.remaining_time_s = 1800.0
        self.session.player.track_limits_steps = 0

        for driver in self.session.drivers:
            driver.best_lap_s = 0.0
            driver.last_sector1_s = 0.0
            driver.last_sector2_s = 0.0
            driver.last_sector3_s = 0.0

        self.elapsed = 0.0
        self.event_stage = 0

    def closeEvent(self, event) -> None:
        self.delta.close()
        event.accept()


def json_load(path: Path) -> dict:
    import json
    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def main() -> None:
    app = QApplication(sys.argv)
    window = DeltaV21Test()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
