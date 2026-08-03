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
class BatteryLapMetrics:
    drain_pct: float = 0.0
    regen_pct: float = 0.0
    net_use_pct: float = 0.0
    completed: bool = False


@dataclass(slots=True)
class BatteryViewData:
    available: bool = False
    charge_pct: float = 0.0
    virtual_energy_pct: float = 0.0

    current_lap: int = 0
    lap_progress_pct: float = 0.0
    current: BatteryLapMetrics = field(default_factory=BatteryLapMetrics)
    last: BatteryLapMetrics = field(default_factory=BatteryLapMetrics)

    delta_vs_last_pct: float | None = None
    projected_lap_use_pct: float | None = None
    laps_remaining: float | None = None

    regen_kw: float = 0.0
    motor_power_kw: float = 0.0
    motor_torque_nm: float = 0.0
    motor_rpm: float = 0.0
    motor_temp_c: float = 0.0
    motor_water_temp_c: float = 0.0
    motor_state: int = 0
    motor_state_text: str = "OFF"

    source_name: str = ""
    comparison_ready: bool = False
