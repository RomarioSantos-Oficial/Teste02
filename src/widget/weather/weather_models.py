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

from dataclasses import dataclass


@dataclass(slots=True)
class WeatherSample:
    timestamp_s: float
    track_temp_c: float
    air_temp_c: float
    rain: float
    wetness: float
    dark_cloud: float
    cloud_coverage: int
    time_of_day_s: float
    wind_speed_kmh: float


@dataclass(slots=True)
class WeatherForecast:
    minutes_ahead: int
    air_temp_c: float
    rain: float
    wetness: float
    dark_cloud: float
    cloud_coverage: int
    time_of_day_s: float
    weather_state: str
    estimated: bool = True
