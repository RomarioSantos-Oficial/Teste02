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
    suspension_deflection_m: float = 0.0
    ride_height_m: float = 0.0
    susp_force_n: float = 0.0
    brake_pressure: float = 0.0
    rotation_rad_s: float = 0.0
    lateral_patch_velocity_ms: float = 0.0
    longitudinal_patch_velocity_ms: float = 0.0
    lateral_ground_velocity_ms: float = 0.0
    longitudinal_ground_velocity_ms: float = 0.0
    camber_rad: float = 0.0
    toe_rad: float = 0.0
    lateral_force_n: float = 0.0
    longitudinal_force_n: float = 0.0
    tire_load_n: float = 0.0
    grip_fraction: float = 0.0
    terrain_name: str = ""
    surface_type: int = 0
    static_undeflected_radius_cm: float = 0.0
    vertical_tire_deflection_m: float = 0.0
    wheel_y_location_m: float = 0.0
    carcass_temp_c: float = 0.0
    inner_left_c: float = 0.0
    inner_center_c: float = 0.0
    inner_right_c: float = 0.0
    optimal_temp_c: float = 0.0
    compound_index: int = 0


@dataclass
class DriverData:
    slot_id: int = 0
    driver_name: str = ""
    vehicle_name: str = ""

    # Identificador do arquivo VEH e grupo de boxes. Esses campos são
    # muito mais úteis quando mVehicleName contém equipe/livery em vez
    # do fabricante.
    vehicle_filename: str = ""
    pit_group: str = ""

    vehicle_class: str = ""
    position: int = 0
    laps: int = 0
    current_sector: int = 0

    best_lap_s: float = 0.0
    last_lap_s: float = 0.0

    best_sector1_s: float = 0.0
    best_sector2_s: float = 0.0
    best_sector3_s: float = 0.0

    last_sector1_s: float = 0.0
    last_sector2_s: float = 0.0
    last_sector3_s: float = 0.0

    gap_ahead_s: float = 0.0
    gap_leader_s: float = 0.0
    in_pits: bool = False
    penalties: int = 0
    flag: int = 0
    lap_distance_m: float = 0.0
    path_lateral_m: float = 0.0
    track_edge_m: float = 0.0
    speed_kmh: float = 0.0
    pit_state: int = 0
    individual_phase: int = 0
    under_yellow: bool = False
    in_garage: bool = False
    position_in_class: int = 0
    world_x: float = 0.0
    world_y: float = 0.0
    world_z: float = 0.0
    right_x: float = 0.0
    right_y: float = 0.0
    right_z: float = 0.0
    forward_x: float = 0.0
    forward_y: float = 0.0
    forward_z: float = 0.0
    relative_rotated_x_m: float = 0.0
    relative_rotated_y_m: float = 0.0
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

    # Sistema híbrido / bateria.
    regen_kw: float = 0.0
    electric_motor_torque_nm: float = 0.0
    electric_motor_rpm: float = 0.0
    electric_motor_temp_c: float = 0.0
    electric_motor_water_temp_c: float = 0.0
    electric_motor_state: int = 0

    # Valor bruto do LMU: TrackLimitPoints * TrackLimitStepsPerPoint.
    track_limits_steps: int = 0

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
    track_length_m: float = 0.0
    sector_flags: tuple[int, int, int] = (0, 0, 0)
    start_light: int = 0
    num_red_lights: int = 0
    in_realtime: bool = False
    game_phase: int = 0
    yellow_flag_state: int = 0
    raining: float = 0.0
    ambient_temp_c: float = 0.0
    track_temp_c: float = 0.0
    time_of_day: float = 0.0
    track_grip_level: int = 0

    # Clima e condições reais da pista.
    dark_cloud: float = 0.0
    cloud_coverage: int = 0
    min_path_wetness: float = 0.0
    avg_path_wetness: float = 0.0
    max_path_wetness: float = 0.0
    wind_x_ms: float = 0.0
    wind_y_ms: float = 0.0
    wind_z_ms: float = 0.0
    wind_speed_kmh: float = 0.0
    weather_schedule: dict = field(default_factory=dict)

    # Parâmetros reais da sessão do LMU.
    track_limits_steps_per_penalty: int = 0
    track_limits_steps_per_point: int = 0

    player: PlayerData | None = None
    drivers: list[DriverData] = field(default_factory=list)
    error: str = ""

    @property
    def track_limits_current(self) -> float:
        if self.player is None:
            return 0.0

        steps_per_point = max(1, int(self.track_limits_steps_per_point or 0))
        return float(self.player.track_limits_steps) / steps_per_point

    @property
    def track_limits_limit(self) -> float:
        steps_per_point = max(1, int(self.track_limits_steps_per_point or 0))
        steps_per_penalty = max(0, int(self.track_limits_steps_per_penalty or 0))

        if steps_per_penalty <= 0:
            return 0.0

        return float(steps_per_penalty) / steps_per_point
