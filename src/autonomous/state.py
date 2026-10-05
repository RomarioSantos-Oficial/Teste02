from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from src.telemetry.models import DriverData, PlayerData, SessionData, WheelData


@dataclass(slots=True)
class VehicleState:
    model: str
    vehicle_class: str
    speed_m_s: float
    speed_km_h: float
    rpm: float
    max_rpm: float
    gear: int
    throttle: float
    brake: float
    steering: float
    clutch: float
    fuel_l: float
    fuel_fraction: float | None
    battery_fraction: float | None
    damage_percent: float | None
    front_tire_compound: str | None
    rear_tire_compound: str | None
    world_position_m: tuple[float, float, float] | None
    forward_direction: tuple[float, float, float] | None
    lap: int
    sector: int
    lap_distance_m: float | None
    lateral_position_m: float | None
    track_edge_m: float | None
    body_damage: list[int] = field(default_factory=list)
    body_detached: bool = False
    current_lap_invalidated: bool = False
    last_impact_time_s: float = 0.0
    last_impact_magnitude: float = 0.0
    last_impact_position_m: tuple[float, float] = (0.0, 0.0)
    track_limits_steps: int = 0
    track_limits_current: float = 0.0
    track_limits_limit: float = 0.0
    wheels: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class WeatherState:
    rain: float | None
    wetness_min: float | None
    wetness_average: float | None
    wetness_max: float | None
    track_temperature_c: float | None
    ambient_temperature_c: float | None
    wind_speed_km_h: float | None
    time_of_day: float | None
    wind_vector_m_s: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass(slots=True)
class TrafficVehicle:
    slot_id: int
    vehicle_model: str
    vehicle_class: str
    lap: int
    speed_km_h: float
    relative_distance_m: float | None
    relative_speed_km_h: float | None
    lateral_position_m: float | None
    in_pits: bool


@dataclass(slots=True)
class UnifiedState:
    schema_version: int
    timestamp_s: float
    connected: bool
    track_name: str
    track_length_m: float | None
    session_name: str
    game_phase: int
    in_realtime: bool
    telemetry_paused: bool
    in_control_of_vehicle: bool | None
    in_monitor: bool | None
    player_vehicle_loaded: bool | None
    is_replay_active: bool | None
    race_finished: bool | None
    game_phase_name: str
    game_state_name: str
    application_location: int
    local_api_available: bool
    local_api_age_s: float
    track_limits_steps_per_penalty: int
    track_limits_steps_per_point: int
    vehicle: VehicleState | None
    weather: WeatherState
    traffic: list[TrafficVehicle]
    provenance: dict[str, str]
    unavailable: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _optional_positive(value: float | None) -> float | None:
    if value is None:
        return None
    return float(value) if value > 0 else None


def _wheel_state(wheel: WheelData) -> dict[str, Any]:
    """Keep the adapter's wheel fields and explicitly named SI units."""
    return {
        "pressure_kpa": wheel.pressure_kpa,
        "wear": wheel.wear,
        "brake_temp_c": wheel.brake_temp_c,
        "surface_left_c": wheel.surface_left_c,
        "surface_center_c": wheel.surface_center_c,
        "surface_right_c": wheel.surface_right_c,
        "carcass_temp_c": wheel.carcass_temp_c,
        "inner_left_c": wheel.inner_left_c,
        "inner_center_c": wheel.inner_center_c,
        "inner_right_c": wheel.inner_right_c,
        "optimal_temp_c": wheel.optimal_temp_c,
        "grip_fraction": wheel.grip_fraction,
        "tire_load_n": wheel.tire_load_n,
        "lateral_force_n": wheel.lateral_force_n,
        "longitudinal_force_n": wheel.longitudinal_force_n,
        "lateral_patch_velocity_m_s": wheel.lateral_patch_velocity_ms,
        "longitudinal_patch_velocity_m_s": wheel.longitudinal_patch_velocity_ms,
        "camber_rad": wheel.camber_rad,
        "toe_rad": wheel.toe_rad,
        "compound_index": wheel.compound_index,
        "compound_type": wheel.compound_type,
        "flat": wheel.flat,
        "detached": wheel.detached,
    }


def build_unified_state(session: SessionData, timestamp_s: float) -> UnifiedState:
    player = session.player
    track_length = _optional_positive(session.track_length_m)
    unavailable: list[str] = []

    vehicle: VehicleState | None = None
    traffic: list[TrafficVehicle] = []
    if player is None:
        unavailable.append("player_vehicle")
    else:
        player_scoring = next(
            (driver for driver in session.drivers if driver.is_player),
            None,
        )
        lap_distance = player_scoring.lap_distance_m if player_scoring else None
        lateral_position = player_scoring.path_lateral_m if player_scoring else None
        track_edge = player_scoring.track_edge_m if player_scoring else None
        world_position = (
            (player_scoring.world_x, player_scoring.world_y, player_scoring.world_z)
            if player_scoring
            else None
        )
        forward_direction = (
            (player_scoring.forward_x, player_scoring.forward_y, player_scoring.forward_z)
            if player_scoring
            else None
        )
        vehicle = VehicleState(
            model=player.vehicle_model or player.vehicle_name,
            vehicle_class=player.vehicle_class,
            speed_m_s=player.speed_kmh / 3.6,
            speed_km_h=player.speed_kmh,
            rpm=player.rpm,
            max_rpm=player.max_rpm,
            gear=player.gear,
            throttle=player.throttle,
            brake=player.brake,
            steering=player.steering,
            clutch=player.clutch,
            fuel_l=player.fuel_liters,
            fuel_fraction=player.fuel_fraction,
            battery_fraction=player.battery_fraction if player.battery_fraction > 0 else None,
            damage_percent=player.vehicle_damage if player.vehicle_damage > 0 else None,
            front_tire_compound=player.front_tire_compound or None,
            rear_tire_compound=player.rear_tire_compound or None,
            world_position_m=world_position,
            forward_direction=forward_direction,
            lap=player.lap,
            sector=player.sector,
            lap_distance_m=lap_distance,
            lateral_position_m=lateral_position,
            track_edge_m=track_edge,
            body_damage=list(player.body_damage),
            body_detached=player.body_detached,
            current_lap_invalidated=player.current_lap_invalidated,
            last_impact_time_s=player.last_impact_time_s,
            last_impact_magnitude=player.last_impact_magnitude,
            last_impact_position_m=player.last_impact_position,
            track_limits_steps=player.track_limits_steps,
            track_limits_current=session.track_limits_current,
            track_limits_limit=session.track_limits_limit,
            wheels=[_wheel_state(wheel) for wheel in player.wheels],
        )
        if player_scoring is None:
            unavailable.extend(["lap_distance_m", "lateral_position_m", "track_edge_m"])
        unavailable.extend(["track_curvature", "vehicle_mass_kg", "vehicle_power_w"])

        for other in session.drivers:
            if other.is_player:
                continue
            traffic.append(
                TrafficVehicle(
                    slot_id=other.slot_id,
                    vehicle_model=other.vehicle_model or other.vehicle_name,
                    vehicle_class=other.vehicle_class,
                    lap=other.laps,
                    speed_km_h=other.speed_kmh,
                    relative_distance_m=(
                        (other.lap_distance_m - lap_distance + (track_length or 0.0) / 2.0)
                        % track_length - (track_length or 0.0) / 2.0
                        if lap_distance is not None and other.lap_distance_m > 0 and track_length
                        else None
                    ),
                    relative_speed_km_h=other.speed_kmh - player.speed_kmh,
                    lateral_position_m=other.path_lateral_m,
                    in_pits=other.in_pits,
                )
            )

    weather = WeatherState(
        rain=session.raining,
        wetness_min=session.min_path_wetness,
        wetness_average=session.avg_path_wetness,
        wetness_max=session.max_path_wetness,
        track_temperature_c=session.track_temp_c,
        ambient_temperature_c=session.ambient_temp_c,
        wind_speed_km_h=session.wind_speed_kmh,
        time_of_day=session.time_of_day,
        wind_vector_m_s=(session.wind_x_ms, session.wind_y_ms, session.wind_z_ms),
    )
    return UnifiedState(
        schema_version=1,
        timestamp_s=timestamp_s,
        connected=session.connected,
        track_name=session.track_name,
        track_length_m=track_length,
        session_name=session.session_name or session.game_session_name,
        game_phase=session.game_phase,
        in_realtime=session.in_realtime,
        telemetry_paused=session.telemetry_paused,
        in_control_of_vehicle=session.in_control_of_vehicle,
        in_monitor=session.in_monitor,
        player_vehicle_loaded=session.player_vehicle_loaded,
        is_replay_active=session.is_replay_active,
        race_finished=session.race_finished,
        game_phase_name=session.game_phase_name,
        game_state_name=session.game_state_name,
        application_location=session.application_location,
        local_api_available=session.local_api_available,
        local_api_age_s=session.local_api_age_s,
        track_limits_steps_per_penalty=session.track_limits_steps_per_penalty,
        track_limits_steps_per_point=session.track_limits_steps_per_point,
        vehicle=vehicle,
        weather=weather,
        traffic=traffic,
        provenance={
            "vehicle.motion_controls_rpm_gear": "MEASURED: existing LMUAdapter Shared Memory telemetry; direct/unfiltered control fields when published, filtered fallback otherwise",
            "vehicle.wheels_tires_damage": "MEASURED: existing LMUAdapter Shared Memory telemetry; damage_percent may be estimated from dent severity when REST condition data is unavailable",
            "vehicle.fuel_and_condition": "MEASURED: Shared Memory fallback, enriched by the existing local REST API when fields are published",
            "vehicle.position_orientation": "MEASURED: LMU scoring mPos/mOri via existing LMUAdapter",
            "vehicle.lap_distance_m": "MEASURED: LMU scoring mLapDist via existing LMUAdapter",
            "vehicle.lateral_position_m": "MEASURED: LMU scoring mPathLateral; approximate scoring reference, not surveyed track centerline",
            "vehicle.track_limits": "MEASURED: LMU telemetry mTrackLimitsSteps and scoring session penalty thresholds",
            "vehicle.impact": "MEASURED: LMU Shared Memory impact fields; magnitude/time/position are game telemetry values",
            "weather": "MEASURED: LMU Shared Memory; local REST enrichment can update session/weather fields",
            "traffic": "MEASURED: LMU scoring and active-vehicle telemetry via existing LMUAdapter; some identity/session fields enriched from REST",
            "session_control_state": "MEASURED: local LMU REST API snapshot plus Shared Memory game/application state",
            "relative_distance_m": "MEASURED/DERIVED: wrapped difference of LMU scoring lap distances",
            "track_curvature": "UNKNOWN: not exposed by current SessionData",
        },
        unavailable=unavailable,
    )
