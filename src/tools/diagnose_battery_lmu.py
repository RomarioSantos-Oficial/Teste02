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

import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(
    __file__
).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )

from src.telemetry.lmu_adapter import (
    LMUAdapter,
)


def main() -> None:
    adapter = LMUAdapter(
        copy_access=True
    )

    try:
        session = adapter.read()

        if not session.connected:
            print(
                "LMU não conectado:",
                session.error,
            )
            return

        player = session.player

        if player is None:
            print(
                "O jogador ainda não possui "
                "telemetria de veículo."
            )
            return

        row = next(
            (
                driver
                for driver in session.drivers
                if driver.is_player
            ),
            None,
        )

        battery_pct = (
            player.battery_fraction
            * 100.0
            if 0.0
            <= player.battery_fraction
            <= 1.0
            else player.battery_fraction
        )
        power_kw = (
            player.electric_motor_torque_nm
            * player.electric_motor_rpm
            * 2.0
            * math.pi
            / 60.0
            / 1000.0
        )

        print("BATERIA / SISTEMA HÍBRIDO")
        print("=========================")
        print(
            "Carro:",
            player.vehicle_name,
        )
        print(
            "Modelo:",
            player.vehicle_model,
        )
        print(
            "Classe:",
            getattr(
                row,
                "vehicle_class",
                "",
            ),
        )
        print(
            "Volta:",
            player.lap,
        )
        print(
            "Distância na volta:",
            getattr(
                row,
                "lap_distance_m",
                0.0,
            ),
            "m",
        )
        print(
            "BatteryChargeFraction:",
            player.battery_fraction,
            f"({battery_pct:.1f}%)",
        )
        print(
            "StateOfCharge:",
            player.state_of_charge,
            "%",
        )
        print(
            "VirtualEnergy:",
            player.virtual_energy,
        )
        print(
            "Regen:",
            player.regen_kw,
            "kW",
        )
        print(
            "Estado do motor:",
            player.electric_motor_state,
        )
        print(
            "Torque elétrico:",
            player.electric_motor_torque_nm,
            "Nm",
        )
        print(
            "RPM elétrico:",
            player.electric_motor_rpm,
        )
        print(
            "Potência calculada:",
            round(
                power_kw,
                2,
            ),
            "kW",
        )
        print(
            "Temperatura do motor:",
            player.electric_motor_temp_c,
            "°C",
        )
        print(
            "Temperatura da água:",
            player.electric_motor_water_temp_c,
            "°C",
        )

    finally:
        adapter.close()


if __name__ == "__main__":
    main()
