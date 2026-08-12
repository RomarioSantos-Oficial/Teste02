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
    steam_id: str = ""
    driver_name: str = ""
    vehicle_name: str = ""

    # Identificador do arquivo VEH e grupo de boxes. Esses campos são
    # muito mais úteis quando mVehicleName contém equipe/livery em vez
    # do fabricante.
    vehicle_filename: str = ""
    pit_group: str = ""
    car_number: str = ""
    team_name: str = ""
    nationality: str = ""
    country_code: str = ""

    vehicle_class: str = ""
    position: int = 0
    laps: int = 0
    current_sector: int = 0

    best_lap_s: float = 0.0
    estimated_lap_s: float = 0.0
    last_lap_s: float = 0.0
    current_lap_invalidated: bool = False
    last_lap_invalidated: bool = False

    best_sector1_s: float = 0.0
    best_sector2_s: float = 0.0
    best_sector3_s: float = 0.0

    last_sector1_s: float = 0.0
    last_sector2_s: float = 0.0
    last_sector3_s: float = 0.0

    gap_ahead_s: float = 0.0
    gap_leader_s: float = 0.0
    laps_behind_ahead: int = 0
    laps_behind_leader: int = 0
    in_pits: bool = False
    penalties: int = 0
    penalty_type: str = ""
    penalty_time_s: float = 0.0
    track_limits_steps: int | None = None
    track_limits_points: float | None = None
    flag: int = 0
    lap_distance_m: float = 0.0
    # Tempo decorrido desde a ultima passagem pela linha. A API REST publica
    # timeIntoLap e a memoria compartilhada publica mTimeIntoLap.
    time_into_lap_s: float = 0.0
    lap_start_event_time_s: float = 0.0
    path_lateral_m: float = 0.0
    track_edge_m: float = 0.0
    speed_kmh: float = 0.0
    pit_state: int = 0
    individual_phase: int = 0
    under_yellow: bool = False
    in_garage: bool = False
    finish_status: int = 0
    finish_status_name: str = ""
    count_lap_flag_name: str = ""
    pit_state_name: str = ""
    drs_active: bool = False
    headlights: bool = False
    pitting: bool = False
    pitstops: int = 0
    qualification_position: int = 0
    server_scored: bool = True
    fuel_fraction: float | None = None
    virtual_energy_fraction: float | None = None
    tire_compounds: list[str] = field(default_factory=list)
    damage_percent: float | None = None
    damage_is_estimated: bool = False
    attack_mode_remaining_count: int = 0
    attack_mode_total_count: int = 0
    attack_mode_time_remaining_s: float = 0.0
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
    api_spatial_position: bool = False
    is_player: bool = False


@dataclass
class PlayerData:
    vehicle_name: str = ""
    vehicle_model: str = ""
    ignition_starter: int = 0
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
    fuel_fraction: float | None = None
    vehicle_damage: float = 0.0
    body_damage: list[int] = field(default_factory=list)
    body_detached: bool = False
    last_impact_time_s: float = 0.0
    vehicle_elapsed_time_s: float = 0.0
    last_impact_magnitude: float = 0.0
    last_impact_position: tuple[float, float] = (0.0, 0.0)
    brake_condition: list[float] = field(default_factory=list)
    suspension_damage: list[float] = field(default_factory=list)
    tire_condition: list[float] = field(default_factory=list)
    current_lap_invalidated: bool = False
    last_lap_invalidated: bool = False

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
    # LMUApplicationState.mOptionsLocation:
    # 0=menu principal, 1=carregando, 2=monitor, 3=na pista.
    application_location: int = 0
    player_has_vehicle: bool = False
    # Estado sincronizado do jogador e relógio da memória compartilhada.
    # Estes campos permitem pausar consumidores antes de usar quadros antigos.
    player_synced: bool = False
    telemetry_paused: bool = False
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

    # Estado complementar publicado pela API REST local do LMU. Os campos
    # opcionais preservam o fallback da memoria compartilhada quando o
    # servidor HTTP ainda nao estiver pronto.
    local_api_available: bool = False
    local_api_age_s: float = 0.0
    local_api_error: str = ""
    in_control_of_vehicle: bool | None = None
    in_monitor: bool | None = None
    player_vehicle_loaded: bool | None = None
    is_replay_active: bool | None = None
    race_finished: bool | None = None
    in_realtime_rest: bool | None = None
    game_phase_name: str = ""
    game_state_name: str = ""
    game_session_name: str = ""
    session_name: str = ""
    navigation_state: str = ""
    internal_state_code: str = ""
    navigation_loading: bool | None = None
    navigation_loading_percent: float = 0.0
    team_vehicle_state: str = ""
    multi_stint_state: str = ""
    pit_state_name: str = ""
    pit_entry_distance_m: float = 0.0
    yellow_flag_state_name: str = ""
    server_name: str = ""
    split_label: str = ""
    game_mode_name: str = ""
    max_players: int = 0
    number_of_players: int = 0
    number_of_vehicles: int = 0
    max_session_time_s: float = 0.0
    start_event_time_s: float = 0.0
    current_event_time_s: float = 0.0
    end_event_time_s: float = 0.0
    closest_weather_node: dict = field(default_factory=dict)
    scheduled_sessions: dict | list = field(default_factory=dict)
    pitstop_estimate: dict = field(default_factory=dict)
    strategy_usage: dict = field(default_factory=dict)
    session_settings: dict = field(default_factory=dict)
    # Valor real publicado por /rest/sessions (SESSSET_Fuel_Usage). Nao ha
    # limite artificial: servidores podem usar valores fracionarios ou altos.
    fuel_usage_multiplier: float | None = None
    incidents: dict | list = field(default_factory=list)
    loading_screen: dict = field(default_factory=dict)

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
