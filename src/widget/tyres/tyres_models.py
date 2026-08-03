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
class TyreWheelViewData:
    index: int = 0
    position: str = ""
    main_temp_c: float = 0.0
    surface_left_c: float = 0.0
    surface_center_c: float = 0.0
    surface_right_c: float = 0.0
    inner_left_c: float = 0.0
    inner_center_c: float = 0.0
    inner_right_c: float = 0.0
    carcass_temp_c: float = 0.0
    optimal_temp_c: float = 0.0
    pressure_kpa: float = 0.0
    wear_used_pct: float = 0.0
    wear_remaining_pct: float = 100.0
    brake_temp_c: float = 0.0
    brake_pressure: float = 0.0
    tire_load_n: float = 0.0
    grip_fraction: float = 0.0
    camber_rad: float = 0.0
    toe_rad: float = 0.0
    suspension_deflection_m: float = 0.0
    vertical_tire_deflection_m: float = 0.0
    ride_height_m: float = 0.0
    rotation_rad_s: float = 0.0
    surface_type: int = 0
    terrain_name: str = ""
    compound_type: int = 0
    compound_index: int = 0
    flat: bool = False
    detached: bool = False

    @property
    def inner_average_c(self) -> float:
        values = [
            self.inner_left_c,
            self.inner_center_c,
            self.inner_right_c,
        ]
        valid = [value for value in values if value > -100.0]

        if not valid:
            return 0.0

        return sum(valid) / len(valid)

    @property
    def surface_average_c(self) -> float:
        values = [
            self.surface_left_c,
            self.surface_center_c,
            self.surface_right_c,
        ]
        valid = [value for value in values if value > -100.0]

        if not valid:
            return 0.0

        return sum(valid) / len(valid)


@dataclass(slots=True)
class TyresViewData:
    front_compound: str = ""
    rear_compound: str = ""
    wheels: list[TyreWheelViewData] = field(default_factory=list)
