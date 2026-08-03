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


NAMES = ("FL", "FR", "RL", "RR")


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

        print("PNEUS DO JOGADOR")
        print("================")
        print(
            "Carro:",
            player.vehicle_name,
        )
        print(
            "Modelo:",
            player.vehicle_model,
        )
        print(
            "Composto dianteiro:",
            player.front_tire_compound,
        )
        print(
            "Composto traseiro:",
            player.rear_tire_compound,
        )

        for index, wheel in enumerate(
            player.wheels[:4]
        ):
            print()
            print(NAMES[index])
            print("-" * 24)
            print(
                "Pressão:",
                round(
                    wheel.pressure_kpa,
                    2,
                ),
                "kPa",
            )
            print(
                "Desgaste usado:",
                round(
                    (1.0 - wheel.wear)
                    * 100,
                    2,
                ),
                "%",
            )
            print(
                "Vida restante:",
                round(
                    wheel.wear
                    * 100,
                    2,
                ),
                "%",
            )
            print(
                "Temperatura superfície L/C/R:",
                round(
                    wheel.surface_left_c,
                    1,
                ),
                round(
                    wheel.surface_center_c,
                    1,
                ),
                round(
                    wheel.surface_right_c,
                    1,
                ),
                "°C",
            )
            print(
                "Temperatura interna L/C/R:",
                round(
                    wheel.inner_left_c,
                    1,
                ),
                round(
                    wheel.inner_center_c,
                    1,
                ),
                round(
                    wheel.inner_right_c,
                    1,
                ),
                "°C",
            )
            print(
                "Carcaça:",
                round(
                    wheel.carcass_temp_c,
                    1,
                ),
                "°C",
            )
            print(
                "Temperatura ótima:",
                round(
                    wheel.optimal_temp_c,
                    1,
                ),
                "°C",
            )
            print(
                "Freio:",
                round(
                    wheel.brake_temp_c,
                    1,
                ),
                "°C",
            )
            print(
                "Pressão do freio:",
                round(
                    wheel.brake_pressure
                    * 100,
                    1,
                ),
                "%",
            )
            print(
                "Carga:",
                round(
                    wheel.tire_load_n,
                    1,
                ),
                "N",
            )
            print(
                "Fração deslizando:",
                round(
                    wheel.grip_fraction
                    * 100,
                    1,
                ),
                "%",
            )
            print(
                "Cambagem:",
                round(
                    math.degrees(
                        wheel.camber_rad
                    ),
                    2,
                ),
                "°",
            )
            print(
                "Toe:",
                round(
                    math.degrees(
                        wheel.toe_rad
                    ),
                    2,
                ),
                "°",
            )
            print(
                "Deflexão suspensão:",
                round(
                    wheel.suspension_deflection_m
                    * 1000,
                    2,
                ),
                "mm",
            )
            print(
                "Deflexão pneu:",
                round(
                    wheel.vertical_tire_deflection_m
                    * 1000,
                    2,
                ),
                "mm",
            )
            print(
                "Altura:",
                round(
                    wheel.ride_height_m
                    * 1000,
                    2,
                ),
                "mm",
            )
            print(
                "Rotação:",
                round(
                    wheel.rotation_rad_s,
                    2,
                ),
                "rad/s",
            )
            print(
                "Piso:",
                wheel.terrain_name,
                "tipo",
                wheel.surface_type,
            )
            print(
                "Composto:",
                wheel.compound_index,
                wheel.compound_type,
            )
            print(
                "Furado:",
                wheel.flat,
            )
            print(
                "Solto:",
                wheel.detached,
            )

    finally:
        adapter.close()


if __name__ == "__main__":
    main()
