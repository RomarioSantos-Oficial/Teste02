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

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DriverMetadata:
    driver_name: str = ""
    username: str = ""
    steam_id: str = ""
    team_name: str = ""
    vehicle_name: str = ""
    vehicle_model: str = ""
    car_number: str = ""
    manufacturer: str = ""
    nationality: str = ""
    country_code: str = ""
    badge: str = ""
    driver_rank: str = ""
    driver_rank_progress: float | None = None
    safety_rank: str = ""
    safety_rank_progress: float | None = None
    estimated_driver_rank_gain: float | None = None
    tyre_compound: str = ""
    # Ordem LMU: dianteiro esquerdo/direito, traseiro esquerdo/direito.
    # Mantemos os quatro valores para conseguir mostrar montagens mistas.
    tyre_compounds: tuple[str, ...] = ()
    energy_percent: float | None = None
    energy_remaining_fraction: float | None = None
    energy_use_per_lap: float | None = None
    energy_reference_lap: float | None = None
    current_lap_invalidated: bool | None = None
    last_lap_invalidated: bool | None = None
    damage_percent: float | None = None
    finish_state: str = ""
    source: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class StandingRow:
    slot_id: int = 0
    delta_identity: str = ""
    overall_position: int = 0
    class_position: int = 0
    position_change: int = 0
    driver_name: str = ""
    team_name: str = ""
    vehicle_name: str = ""
    vehicle_model: str = ""
    class_name: str = "UNKNOWN"
    class_key: str = "UNKNOWN"
    car_number: str = ""
    manufacturer: str = ""
    nationality: str = ""
    country_code: str = ""
    badge: str = ""
    driver_rank: str = ""
    driver_rank_progress: float | None = None
    safety_rank: str = ""
    safety_rank_progress: float | None = None
    estimated_driver_rank_gain: float | None = None
    laps: int = 0
    display_lap: int = 0
    lap_distance_m: float = 0.0
    time_into_lap_s: float = 0.0
    lap_start_event_time_s: float = 0.0
    best_lap_s: float = 0.0
    estimated_lap_s: float = 0.0
    last_lap_s: float = 0.0
    is_session_fastest: bool = False
    personal_best_highlight: bool = False
    current_lap_invalidated: bool = False
    last_lap_invalidated: bool = False
    gap_leader_s: float = 0.0
    interval_s: float = 0.0
    laps_behind_leader: int = 0
    laps_behind_ahead: int = 0
    gap_text: str = "--"
    interval_text: str = "--"
    rolling_delta_s: float | None = None
    rolling_delta_text: str = "--"
    tyre_compound: str = ""
    tyre_compounds: tuple[str, ...] = ()
    energy_percent: float | None = None
    fuel_liters: float | None = None
    fuel_percent: float | None = None
    fuel_is_estimated: bool = False
    damage_percent: float | None = None
    damage_is_estimated: bool = False
    penalties: int = 0
    track_limits_text: str = "--"
    penalty_text: str = ""
    finish_state: str = ""
    finish_status: int = 0
    in_pits: bool = False
    in_garage: bool = False
    under_yellow: bool = False
    flag: int = 0
    is_player: bool = False
    pit_time_s: float = 0.0
    pit_status_visible: bool = False


@dataclass(slots=True)
class CategoryBlock:
    class_name: str = "UNKNOWN"
    class_key: str = "UNKNOWN"
    color: str = "#1E5D93"
    started: int = 0
    total: int = 0
    current_lap: int = 0
    total_laps_text: str = "--"
    # Explicação curta do cálculo usado para estimar total de voltas (ex: "ref=leader lap=92.3s rem=600s est=18.3")
    total_laps_calc: str = ""
    show_count: bool = False
    dr_sof_rank: str = ""
    dr_sof_progress: float | None = None
    dr_sof_drivers: int = 0
    rows: list[StandingRow] = field(default_factory=list)


@dataclass(slots=True)
class StandingsView:
    connected: bool = False
    session_type: str = "AGUARDANDO"
    session_time: str = "--:--"
    server_time: str = "--:--"
    local_time: str = "--:--"
    grip_text: str = "--"
    track_limits_text: str = "-- / --"
    source_text: str = "MEM"
    split_label: str = ""
    track_name: str = ""
    categories: list[CategoryBlock] = field(default_factory=list)


@dataclass(slots=True)
class OnlineDriverIdentity:
    display_name: str = ""
    username: str = ""
    steam_id: str = ""
    team_name: str = ""
    car_number: str = ""
    vehicle_class: str = ""
    driver_rank: str = ""
    driver_rank_progress: float | None = None
    safety_rank: str = ""
    safety_rank_progress: float | None = None
    nationality: str = ""
    badge: str = ""
    incidents: int | None = None
    estimated_driver_rank_gain: float | None = None
    source: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OnlineSnapshot:
    local_api_available: bool = False
    cloud_available: bool = False
    session_online: bool = False
    event_id: str = ""
    split_label: str = ""
    updated_at_s: float = 0.0
    source_message: str = ""
    error: str = ""
    identities: list[OnlineDriverIdentity] = field(default_factory=list)


def normalize_identity(value: Any) -> str:
    return "".join(
        character
        for character in str(value or "").casefold()
        if character.isalnum()
    )
