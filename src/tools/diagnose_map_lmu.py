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

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(
    __file__
).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )

from src.telemetry.lmu_adapter import LMUAdapter
from src.widget.map.map_builder import TrackMapBuilder


def main() -> None:
    adapter = LMUAdapter(
        copy_access=True
    )
    config = {
        "cache_directory": "data/track_maps",
        "load_map_cache": True,
        "save_map_cache": True,
        "mapping_sample_distance_m": 18.0,
        "minimum_mapping_points": 120,
        "minimum_mapping_coverage": 0.82,
        "maximum_mapping_path_lateral_m": 35.0,
    }
    builder = TrackMapBuilder(
        PROJECT_ROOT,
        config,
    )

    print(
        "Capturando coordenadas do LMU por 15 segundos..."
    )
    print(
        "Permaneça dirigindo dentro da pista."
    )
    print()

    started = time.monotonic()
    last_print = 0.0

    try:
        while (
            time.monotonic() - started
            < 15.0
        ):
            session = adapter.read()

            if not session.connected:
                print(
                    "LMU não conectado:",
                    session.error,
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

            if row is None:
                print(
                    "Jogador não encontrado."
                )
                return

            data = builder.update(session)
            elapsed = (
                time.monotonic()
                - started
            )

            if elapsed - last_print >= 1.0:
                last_print = elapsed
                print(
                    f"{elapsed:4.0f}s | "
                    f"pista={session.track_name} | "
                    f"volta={session.player.lap if session.player else 0} | "
                    f"dist={row.lap_distance_m:.0f}m | "
                    f"x={row.world_x:.1f} | "
                    f"z={row.world_z:.1f} | "
                    f"pontos={len(data.points)} | "
                    f"cobertura={data.coverage * 100:.0f}% | "
                    f"completo={data.complete}"
                )

            time.sleep(0.05)

        print()
        print(
            "Pasta do cache:",
            builder.cache_dir,
        )
        print(
            "O mapa é salvo automaticamente "
            "após uma volta válida e suficientemente completa."
        )

    finally:
        adapter.close()


if __name__ == "__main__":
    main()
