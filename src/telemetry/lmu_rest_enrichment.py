from __future__ import annotations

import math
import time
from typing import Any

from .lmu_rest_client import LMURestSnapshot
from .models import DriverData, SessionData, WheelData


_SESSION_NUMBERS = {
    "PRACTICE1": 1,
    "PRACTICE2": 2,
    "PRACTICE3": 3,
    "PRACTICE4": 4,
    "QUALIFY1": 5,
    "QUALIFY2": 6,
    "QUALIFY3": 7,
    "QUALIFY4": 8,
    "WARMUP": 9,
    "RACE1": 10,
    "RACE2": 11,
    "RACE3": 12,
    "RACE4": 13,
}

_FLAG_CODES = {
    "GREEN": 0,
    "YELLOW": 1,
    "BLUE": 6,
    "WHITE": 7,
    "BLACK": 8,
    "CHEQUERED": 9,
    "CHECKERED": 9,
}

_FINISH_CODES = {
    "FSTAT_NONE": 0,
    "FSTAT_FINISHED": 1,
    "FSTAT_DNF": 2,
    "FSTAT_DQ": 3,
    "FSTAT_DISQUALIFIED": 3,
}

_WHEEL_KEYS = ("frontLeft", "frontRight", "rearLeft", "rearRight")

_SECTOR_CODES = {
    "SECTOR1": 1,
    "SECTOR2": 2,
    "SECTOR3": 3,
}


def apply_rest_snapshot(
    session: SessionData,
    snapshot: LMURestSnapshot,
) -> SessionData:
    now = time.monotonic()
    session.local_api_available = snapshot.available
    session.local_api_error = snapshot.last_error
    if snapshot.last_success_at > 0.0:
        session.local_api_age_s = max(0.0, now - snapshot.last_success_at)

    _apply_game_state(session, snapshot.value("game_state", max_age_s=2.0, now=now))
    _apply_navigation(
        session,
        snapshot.value("navigation_state", max_age_s=3.0, now=now),
    )
    _apply_session_info(
        session,
        snapshot.value("session_info", max_age_s=2.5, now=now),
    )
    _apply_standings(
        session,
        snapshot.value("standings", max_age_s=2.5, now=now),
    )
    _apply_player_condition(
        session,
        snapshot.value("vehicle_condition", max_age_s=3.0, now=now),
    )
    _apply_tire_info(
        session,
        snapshot.value("tire_info", max_age_s=3.0, now=now),
    )

    weather = snapshot.value("weather", max_age_s=30.0, now=now)
    if isinstance(weather, dict):
        session.weather_schedule = weather

    event_sessions = snapshot.value(
        "event_sessions",
        max_age_s=45.0,
        now=now,
    )
    if isinstance(event_sessions, dict):
        scheduled = event_sessions.get("scheduledSessions", event_sessions)
        session.scheduled_sessions = (
            scheduled if isinstance(scheduled, (dict, list)) else {}
        )

    pitstop = snapshot.value("pitstop_estimate", max_age_s=8.0, now=now)
    if isinstance(pitstop, dict):
        session.pitstop_estimate = pitstop

    usage = snapshot.value("strategy_usage", max_age_s=12.0, now=now)
    if isinstance(usage, dict):
        session.strategy_usage = usage

    incidents = snapshot.value("incidents", max_age_s=10.0, now=now)
    if isinstance(incidents, (dict, list)):
        session.incidents = incidents

    loading = snapshot.value("loading_screen", max_age_s=90.0, now=now)
    if isinstance(loading, dict):
        session.loading_screen = loading

    return session


def _apply_game_state(session: SessionData, payload: Any) -> None:
    if not isinstance(payload, dict):
        return
    session.in_control_of_vehicle = _optional_bool(
        payload.get("inControlOfVehicle")
    )
    session.in_monitor = _optional_bool(payload.get("inMonitor"))
    session.player_vehicle_loaded = _optional_bool(
        payload.get("playerVehicleLoaded")
    )
    session.is_replay_active = _optional_bool(payload.get("isReplayActive"))
    session.race_finished = _optional_bool(payload.get("raceFinished"))
    session.game_phase_name = str(payload.get("gamePhase", "") or "")
    session.team_vehicle_state = str(
        payload.get("teamVehicleState", "") or ""
    )
    session.multi_stint_state = str(payload.get("MultiStintState", "") or "")
    session.pit_state_name = str(payload.get("PitState", "") or "")
    session.pit_entry_distance_m = _finite(
        payload.get("PitEntryDist"),
        session.pit_entry_distance_m,
    )
    session.time_of_day = _positive_or_zero(
        payload.get("timeOfDay"),
        session.time_of_day,
    )
    closest = payload.get("closeestWeatherNode")
    if not isinstance(closest, dict):
        closest = payload.get("closestWeatherNode")
    if isinstance(closest, dict):
        session.closest_weather_node = dict(closest)


def _apply_navigation(session: SessionData, payload: Any) -> None:
    if not isinstance(payload, dict):
        return
    loading = payload.get("loadingStatus")
    if isinstance(loading, dict):
        session.navigation_loading = _optional_bool(loading.get("loading"))
        session.navigation_loading_percent = _finite(
            loading.get("percentage"),
            session.navigation_loading_percent,
        )
    state = payload.get("state")
    if not isinstance(state, dict):
        return
    session.navigation_state = str(state.get("navigationState", "") or "")
    session.game_state_name = str(state.get("gameState", "") or "")
    session.game_session_name = str(state.get("gameSession", "") or "")
    session.internal_state_code = str(
        state.get("internalStateCode", "") or ""
    )


def _apply_session_info(session: SessionData, payload: Any) -> None:
    if not isinstance(payload, dict):
        return
    session.session_name = str(payload.get("session", "") or "")
    session.session = _SESSION_NUMBERS.get(session.session_name, session.session)
    session.server_name = str(payload.get("serverName", "") or "")
    session.game_mode_name = str(payload.get("gameMode", "") or "")
    session.player_name = str(
        payload.get("playerName", "") or session.player_name
    )
    session.track_name = str(
        payload.get("trackName", "") or session.track_name
    )
    session.max_players = _positive_integer(
        payload.get("maxPlayers"),
        session.max_players,
    )
    session.number_of_players = _positive_or_zero_integer(
        payload.get("numberOfPlayers"),
        session.number_of_players,
    )
    session.number_of_vehicles = _positive_or_zero_integer(
        payload.get("numberOfVehicles"),
        session.number_of_vehicles,
    )
    session.max_session_time_s = _positive_or_zero(
        payload.get("maxTime"),
        session.max_session_time_s,
    )
    session.start_event_time_s = _positive_or_zero(
        payload.get("startEventTime"),
        session.start_event_time_s,
    )
    session.current_event_time_s = _positive_or_zero(
        payload.get("currentEventTime"),
        session.current_event_time_s,
    )
    session.end_event_time_s = _positive_or_zero(
        payload.get("endEventTime"),
        session.end_event_time_s,
    )
    session.game_phase = _integer(payload.get("gamePhase"), session.game_phase)
    session.in_realtime_rest = _optional_bool(payload.get("inRealtime"))
    session.yellow_flag_state_name = str(
        payload.get("yellowFlagState", "") or ""
    )
    session.ambient_temp_c = _finite(
        payload.get("ambientTemp"),
        session.ambient_temp_c,
    )
    session.track_temp_c = _finite(
        payload.get("trackTemp"),
        session.track_temp_c,
    )
    session.raining = _finite(payload.get("raining"), session.raining)
    session.dark_cloud = _finite(payload.get("darkCloud"), session.dark_cloud)
    session.min_path_wetness = _finite(
        payload.get("minPathWetness"),
        session.min_path_wetness,
    )
    session.avg_path_wetness = _finite(
        payload.get("averagePathWetness"),
        session.avg_path_wetness,
    )
    session.max_path_wetness = _finite(
        payload.get("maxPathWetness"),
        session.max_path_wetness,
    )
    session.track_length_m = _positive(
        payload.get("lapDistance"),
        session.track_length_m,
    )
    session.remaining_time_s = _positive_or_zero(
        payload.get("timeRemainingInGamePhase"),
        session.remaining_time_s,
    )

    wind = payload.get("windSpeed")
    if isinstance(wind, dict):
        session.wind_x_ms = _finite(wind.get("x"), session.wind_x_ms)
        session.wind_y_ms = _finite(wind.get("y"), session.wind_y_ms)
        session.wind_z_ms = _finite(wind.get("z"), session.wind_z_ms)
        velocity = _number(wind.get("velocity"))
        if velocity is None:
            velocity = math.sqrt(
                session.wind_x_ms**2
                + session.wind_y_ms**2
                + session.wind_z_ms**2
            )
        session.wind_speed_kmh = max(0.0, velocity * 3.6)

    raw_sector_flags = payload.get("sectorFlag")
    if isinstance(raw_sector_flags, list):
        converted = [
            _FLAG_CODES.get(str(value or "").upper(), -1)
            for value in raw_sector_flags[:3]
        ]
        while len(converted) < 3:
            converted.append(-1)
        if converted and any(value >= 0 for value in converted):
            original = list(session.sector_flags)
            while len(original) < 3:
                original.append(0)
            session.sector_flags = tuple(
                converted[index] if converted[index] >= 0 else original[index]
                for index in range(3)
            )  # type: ignore[assignment]


def _apply_standings(session: SessionData, payload: Any) -> None:
    if not isinstance(payload, list):
        return
    by_slot = {driver.slot_id: driver for driver in session.drivers}
    by_name = {
        _identity(driver.driver_name): driver
        for driver in session.drivers
        if _identity(driver.driver_name)
    }
    player_rest: dict[str, Any] | None = None
    for record in payload:
        if not isinstance(record, dict):
            continue
        slot_id = _integer(record.get("slotID"), -1)
        name = str(record.get("driverName", "") or "")
        driver = by_slot.get(slot_id) or by_name.get(_identity(name))
        if driver is None:
            continue
        _merge_driver(driver, record)
        if bool(record.get("player", False)) or driver.is_player:
            player_rest = record
    if session.player is not None and player_rest is not None:
        ve_fraction = _fraction(player_rest.get("veFraction"))
        if ve_fraction is not None:
            session.player.virtual_energy = ve_fraction
        fuel_fraction = _fraction(player_rest.get("fuelFraction"))
        if fuel_fraction is not None:
            session.player.fuel_fraction = fuel_fraction


def _merge_driver(driver: DriverData, record: dict[str, Any]) -> None:
    steam_id = _integer(record.get("steamID"), 0)
    if steam_id > 0:
        driver.steam_id = str(steam_id)
    driver.car_number = str(record.get("carNumber", driver.car_number) or "")
    driver.team_name = str(record.get("fullTeamName", driver.team_name) or "")
    driver.vehicle_filename = str(
        record.get("vehicleFilename", driver.vehicle_filename) or ""
    )
    driver.vehicle_name = str(
        record.get("vehicleName", driver.vehicle_name) or driver.vehicle_name
    )
    driver.vehicle_class = str(
        driver.vehicle_class or record.get("carClass", "") or ""
    )
    driver.pit_group = str(record.get("pitGroup", driver.pit_group) or "")
    driver.position = _positive_integer(
        record.get("position"),
        driver.position,
    )
    driver.laps = _positive_or_zero_integer(
        record.get("lapsCompleted"),
        driver.laps,
    )
    sector_name = str(record.get("sector", "") or "").upper()
    if sector_name in _SECTOR_CODES:
        driver.current_sector = _SECTOR_CODES[sector_name]
    driver.lap_distance_m = _positive_or_zero(
        record.get("lapDistance"),
        driver.lap_distance_m,
    )
    driver.best_lap_s = _positive(
        record.get("bestLapTime"),
        driver.best_lap_s,
    )
    driver.last_lap_s = _positive(
        record.get("lastLapTime"),
        driver.last_lap_s,
    )
    driver.gap_leader_s = _positive_or_zero(
        record.get("timeBehindLeader"),
        driver.gap_leader_s,
    )
    driver.gap_ahead_s = _positive_or_zero(
        record.get("timeBehindNext"),
        driver.gap_ahead_s,
    )
    count_lap_flag = str(record.get("countLapFlag", "") or "").upper()
    if count_lap_flag:
        driver.count_lap_flag_name = count_lap_flag
        driver.current_lap_invalidated = (
            count_lap_flag != "COUNT_LAP_AND_TIME"
        )
    driver.drs_active = bool(record.get("drsActive", driver.drs_active))
    driver.headlights = bool(record.get("headlights", driver.headlights))
    driver.pitting = bool(record.get("pitting", driver.pitting))
    driver.in_garage = bool(record.get("inGarageStall", driver.in_garage))
    driver.under_yellow = bool(record.get("underYellow", driver.under_yellow))
    driver.server_scored = bool(record.get("serverScored", driver.server_scored))
    driver.pitstops = _integer(record.get("pitstops"), driver.pitstops)
    driver.qualification_position = _integer(
        record.get("qualification"),
        driver.qualification_position,
    )
    driver.penalties = _integer(record.get("penalties"), driver.penalties)
    driver.fuel_fraction = _fraction(record.get("fuelFraction"))
    driver.virtual_energy_fraction = _fraction(record.get("veFraction"))
    driver.finish_status_name = str(record.get("finishStatus", "") or "")
    if driver.finish_status_name:
        driver.finish_status = _FINISH_CODES.get(
            driver.finish_status_name.upper(),
            driver.finish_status,
        )
    flag_name = str(record.get("flag", "") or "").upper()
    if flag_name in _FLAG_CODES:
        driver.flag = _FLAG_CODES[flag_name]
    pit_state = str(record.get("pitState", "") or "")
    if pit_state:
        driver.pit_state_name = pit_state
    attack = record.get("attackMode")
    if isinstance(attack, dict):
        driver.attack_mode_remaining_count = _integer(
            attack.get("remainingCount"),
            driver.attack_mode_remaining_count,
        )
        driver.attack_mode_total_count = _integer(
            attack.get("totalCount"),
            driver.attack_mode_total_count,
        )
        driver.attack_mode_time_remaining_s = _finite(
            attack.get("timeRemaining"),
            driver.attack_mode_time_remaining_s,
        )


def _apply_player_condition(session: SessionData, payload: Any) -> None:
    player = session.player
    if player is None or not isinstance(payload, dict):
        return
    player.fuel_liters = _finite(payload.get("fuel"), player.fuel_liters)
    player.fuel_capacity_liters = _positive(
        payload.get("fuelCapacity"),
        player.fuel_capacity_liters,
    )
    player.vehicle_damage = _finite(
        payload.get("vehicleDamage"),
        player.vehicle_damage,
    )
    player.brake_condition = _float_list(payload.get("brakeCondition"), 4)
    player.suspension_damage = _float_list(payload.get("suspensionDamage"), 4)
    tire_condition = _float_list(payload.get("tireCondition"), 4)
    player.tire_condition = tire_condition
    for index, remaining in enumerate(tire_condition[: len(player.wheels)]):
        if 0.0 <= remaining <= 1.0:
            player.wheels[index].wear = remaining


def _apply_tire_info(session: SessionData, payload: Any) -> None:
    player = session.player
    if player is None or not isinstance(payload, dict):
        return
    while len(player.wheels) < 4:
        player.wheels.append(WheelData())
    for index, key in enumerate(_WHEEL_KEYS):
        record = payload.get(key)
        if not isinstance(record, dict):
            continue
        wheel = player.wheels[index]
        wheel.surface_left_c = _temperature_c(
            record.get("leftTemperature"),
            wheel.surface_left_c,
        )
        wheel.surface_center_c = _temperature_c(
            record.get("centerTemperature"),
            wheel.surface_center_c,
        )
        wheel.surface_right_c = _temperature_c(
            record.get("rightTemperature"),
            wheel.surface_right_c,
        )
        wheel.pressure_kpa = _positive(
            record.get("pressure"),
            wheel.pressure_kpa,
        )
        load_kg = _number(record.get("load"))
        if load_kg is not None and load_kg >= 0.0:
            wheel.tire_load_n = load_kg * 9.80665


def _identity(value: Any) -> str:
    return "".join(
        character
        for character in str(value or "").casefold()
        if character.isalnum()
    )


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _finite(value: Any, fallback: float) -> float:
    number = _number(value)
    return fallback if number is None else number


def _positive(value: Any, fallback: float) -> float:
    number = _number(value)
    return fallback if number is None or number <= 0.0 else number


def _positive_or_zero(value: Any, fallback: float) -> float:
    number = _number(value)
    return fallback if number is None or number < 0.0 else number


def _integer(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _positive_integer(value: Any, fallback: int) -> int:
    result = _integer(value, fallback)
    return result if result > 0 else fallback


def _positive_or_zero_integer(value: Any, fallback: int) -> int:
    result = _integer(value, fallback)
    return result if result >= 0 else fallback


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _fraction(value: Any) -> float | None:
    number = _number(value)
    if number is None or not 0.0 <= number <= 1.0:
        return None
    return number


def _temperature_c(value: Any, fallback: float) -> float:
    number = _number(value)
    if number is None:
        return fallback
    if number > 170.0:
        number -= 273.15
    return number if -50.0 <= number <= 250.0 else fallback


def _float_list(value: Any, maximum: int) -> list[float]:
    if not isinstance(value, list):
        return []
    result: list[float] = []
    for item in value[:maximum]:
        number = _number(item)
        if number is not None:
            result.append(number)
    return result
