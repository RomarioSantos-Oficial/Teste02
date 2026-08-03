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
from src.widget.weather.weather_predictor import (
    WeatherTrendPredictor,
)


def main() -> None:
    adapter = LMUAdapter(
        copy_access=True
    )
    predictor = WeatherTrendPredictor()

    try:
        session = adapter.read()

        if not session.connected:
            print(
                "LMU não conectado:",
                session.error,
            )
            return

        sample = predictor.add_session(
            session
        )
        forecasts = predictor.forecast(
            sample,
            count=5,
            interval_minutes=5,
        )

        print("TEMPO REAL")
        print("==========")
        print(
            "Pista:",
            session.track_name,
        )
        print(
            "Temperatura da pista:",
            session.track_temp_c,
            "°C",
        )
        print(
            "Temperatura do ar:",
            session.ambient_temp_c,
            "°C",
        )
        print(
            "Chuva:",
            round(
                session.raining * 100,
                1,
            ),
            "%",
        )
        print(
            "Pista molhada mínima:",
            round(
                session.min_path_wetness
                * 100,
                1,
            ),
            "%",
        )
        print(
            "Pista molhada média:",
            round(
                session.avg_path_wetness
                * 100,
                1,
            ),
            "%",
        )
        print(
            "Pista molhada máxima:",
            round(
                session.max_path_wetness
                * 100,
                1,
            ),
            "%",
        )
        print(
            "Nuvem escura:",
            round(
                session.dark_cloud
                * 100,
                1,
            ),
            "%",
        )
        print(
            "Cobertura de nuvens:",
            session.cloud_coverage,
            "/10",
        )
        print(
            "Hora da pista:",
            session.time_of_day,
            "s",
        )
        print(
            "Vento:",
            round(
                session.wind_speed_kmh,
                1,
            ),
            "km/h",
        )

        print()
        print("TENDÊNCIA")
        print("=========")

        for item in forecasts:
            print(
                f"+{item.minutes_ahead}m | "
                f"{item.weather_state} | "
                f"{item.air_temp_c:.1f}°C | "
                f"chuva {item.rain * 100:.0f}% | "
                f"pista {item.wetness * 100:.0f}%"
            )

        print()
        print(
            "Observação: os blocos futuros são "
            "estimativas de tendência baseadas nas "
            "amostras reais recentes."
        )

    finally:
        adapter.close()


if __name__ == "__main__":
    main()
