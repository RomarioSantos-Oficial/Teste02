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

from dataclasses import dataclass, field


@dataclass(slots=True)
class MapPoint:
    distance_m: float = 0.0
    world_x: float = 0.0
    world_y: float = 0.0
    sector: int = 0


@dataclass(slots=True)
class TrackMapData:
    track_key: str = ""
    track_name: str = ""
    track_length_m: float = 0.0
    points: list[MapPoint] = field(default_factory=list)
    sector_points: list[MapPoint] = field(default_factory=list)
    complete: bool = False
    loaded_from_cache: bool = False
    coverage: float = 0.0
