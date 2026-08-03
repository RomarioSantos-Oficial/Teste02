from __future__ import annotations
from dataclasses import dataclass, field

@dataclass
class WheelData:
    pressure_kpa: float = 0.0
    wear: float = 0.0
    brake_temp_c: float = 0.0
    surface_left_c: float = 0.0
    surface_center_c: float = 0.0
    surface_right_c: float = 0.0
    flat: bool = False
    detached: bool = False
    compound_type: int = 0

@dataclass
class DriverData:
    driver_name: str = ""
    vehicle_name: str = ""
    vehicle_class: str = ""
    position: int = 0
    laps: int = 0
    best_lap_s: float = 0.0
    last_lap_s: float = 0.0
    gap_ahead_s: float = 0.0
    gap_leader_s: float = 0.0
    in_pits: bool = False
    penalties: int = 0
    flag: int = 0
    lap_distance_m: float = 0.0
    is_player: bool = False

@dataclass
class PlayerData:
    vehicle_name: str = ""
    vehicle_model: str = ""
    speed_kmh: float = 0.0
    rpm: float = 0.0
    max_rpm: float = 0.0
    gear: int = 0
    throttle: float = 0.0
    brake: float = 0.0
    steering: float = 0.0
    clutch: float = 0.0
    fuel_liters: float = 0.0
    fuel_capacity_liters: float = 0.0
    lap: int = 0
    sector: int = 0
    delta_best_s: float = 0.0
    gap_ahead_s: float = 0.0
    gap_behind_s: float = 0.0
    battery_fraction: float = 0.0
    state_of_charge: float = 0.0
    virtual_energy: float = 0.0
    front_tire_compound: str = ""
    rear_tire_compound: str = ""
    wheels: list[WheelData] = field(default_factory=list)

@dataclass
class SessionData:
    connected: bool = False
    game_version: int = 0
    track_name: str = ""
    player_name: str = ""
    session: int = 0
    current_time_s: float = 0.0
    remaining_time_s: float = 0.0
    max_laps: int = 0
    game_phase: int = 0
    yellow_flag_state: int = 0
    raining: float = 0.0
    ambient_temp_c: float = 0.0
    track_temp_c: float = 0.0
    time_of_day: float = 0.0
    track_grip_level: int = 0
    player: PlayerData | None = None
    drivers: list[DriverData] = field(default_factory=list)
    error: str = ""
