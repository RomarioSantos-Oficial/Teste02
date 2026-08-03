from __future__ import annotations

import math
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .models import DriverData, PlayerData, SessionData, WheelData


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LMU_LIBRARY = PROJECT_ROOT / "vendor" / "pyLMUSharedMemory"

if str(LMU_LIBRARY) not in sys.path:
    sys.path.insert(0, str(LMU_LIBRARY))

try:
    import lmu_data
    import lmu_mmap
except ImportError as exc:
    raise ImportError(
        "pyLMUSharedMemory nao encontrado em vendor/pyLMUSharedMemory."
    ) from exc


def decode_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.split(b"\x00", 1)[0].decode(
            "utf-8",
            errors="replace",
        ).strip()

    try:
        raw = bytes(value)
        return raw.split(b"\x00", 1)[0].decode(
            "utf-8",
            errors="replace",
        ).strip()
    except Exception:
        return str(value) if value is not None else ""


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def positive_difference(total: float, previous: float) -> float:
    if total <= 0 or previous < 0:
        return 0.0

    result = total - previous
    return result if result > 0 else 0.0


class LMUAdapter:
    def __init__(self, copy_access: bool = True) -> None:
        self.copy_access = copy_access
        self.memory: lmu_mmap.MMapControl | None = None
        self._weather_schedule: dict[str, Any] = {}
        self._last_weather_poll_at = 0.0

    def connect(self) -> bool:
        if self.memory is not None:
            return self.is_connected()

        try:
            self.memory = lmu_mmap.MMapControl(
                lmu_data.LMUConstants.LMU_SHARED_MEMORY_FILE,
                lmu_data.LMUObjectOut,
            )
            self.memory.create(0 if self.copy_access else 1)
            self.memory.update()
            return self.is_connected()
        except (OSError, ValueError, BufferError):
            self.close()
            return False

    def is_connected(self) -> bool:
        if self.memory is None or self.memory.data is None:
            return False

        try:
            return safe_int(self.memory.data.generic.gameVersion) > 0
        except AttributeError:
            return False

    def read(self) -> SessionData:
        if self.memory is None and not self.connect():
            return SessionData(
                connected=False,
                error="Aguardando o LMU.",
            )

        try:
            assert self.memory is not None
            self.memory.update()

            if not self.is_connected():
                return SessionData(
                    connected=False,
                    error="LMU nao esta fornecendo dados.",
                )

            data = self.memory.data
            info = data.scoring.scoringInfo
            telemetry = data.telemetry

            drivers: list[DriverData] = []
            vehicle_count = max(
                0,
                min(
                    safe_int(info.mNumVehicles),
                    int(lmu_data.LMUConstants.MAX_MAPPED_VEHICLES),
                ),
            )

            for index in range(vehicle_count):
                score = data.scoring.vehScoringInfo[index]

                best_s1 = safe_float(getattr(score, "mBestSector1", 0.0))
                best_s12 = safe_float(getattr(score, "mBestSector2", 0.0))
                best_lap = safe_float(getattr(score, "mBestLapTime", 0.0))

                last_s1 = safe_float(getattr(score, "mLastSector1", 0.0))
                last_s12 = safe_float(getattr(score, "mLastSector2", 0.0))
                last_lap = safe_float(getattr(score, "mLastLapTime", 0.0))

                score_velocity = getattr(score, "mLocalVel", None)
                score_speed_kmh = 0.0
                if score_velocity is not None:
                    score_speed_kmh = math.sqrt(
                        safe_float(score_velocity.x) ** 2
                        + safe_float(score_velocity.y) ** 2
                        + safe_float(score_velocity.z) ** 2
                    ) * 3.6

                score_pos = getattr(score, "mPos", None)
                score_ori = getattr(score, "mOri", None)
                right = score_ori[0] if score_ori is not None else None
                forward = score_ori[2] if score_ori is not None else None

                drivers.append(
                    DriverData(
                        slot_id=safe_int(getattr(score, "mID", index)),
                        driver_name=decode_text(score.mDriverName),
                        vehicle_name=decode_text(score.mVehicleName),
                        vehicle_filename=decode_text(
                            getattr(score, "mVehFilename", b"")
                        ),
                        pit_group=decode_text(
                            getattr(score, "mPitGroup", b"")
                        ),
                        vehicle_class=decode_text(score.mVehicleClass),
                        position=safe_int(score.mPlace),
                        laps=safe_int(score.mTotalLaps),
                        current_sector=safe_int(getattr(score, "mSector", 0)),
                        best_lap_s=best_lap,
                        last_lap_s=last_lap,
                        best_sector1_s=best_s1,
                        best_sector2_s=positive_difference(best_s12, best_s1),
                        best_sector3_s=positive_difference(best_lap, best_s12),
                        last_sector1_s=last_s1,
                        last_sector2_s=positive_difference(last_s12, last_s1),
                        last_sector3_s=positive_difference(last_lap, last_s12),
                        gap_ahead_s=safe_float(score.mTimeBehindNext),
                        gap_leader_s=safe_float(score.mTimeBehindLeader),
                        in_pits=bool(score.mInPits),
                        penalties=safe_int(score.mNumPenalties),
                        flag=safe_int(score.mFlag),
                        lap_distance_m=safe_float(score.mLapDist),
                        path_lateral_m=safe_float(
                            getattr(score, "mPathLateral", 0.0)
                        ),
                        track_edge_m=safe_float(
                            getattr(score, "mTrackEdge", 0.0)
                        ),
                        speed_kmh=score_speed_kmh,
                        pit_state=safe_int(
                            getattr(score, "mPitState", 0)
                        ),
                        individual_phase=safe_int(
                            getattr(score, "mIndividualPhase", 0)
                        ),
                        under_yellow=bool(
                            getattr(score, "mUnderYellow", False)
                        ),
                        in_garage=bool(
                            getattr(score, "mInGarageStall", False)
                        ),
                        world_x=safe_float(score_pos.x) if score_pos is not None else 0.0,
                        world_y=safe_float(score_pos.y) if score_pos is not None else 0.0,
                        world_z=safe_float(score_pos.z) if score_pos is not None else 0.0,
                        right_x=safe_float(right.x) if right is not None else 0.0,
                        right_y=safe_float(right.y) if right is not None else 0.0,
                        right_z=safe_float(right.z) if right is not None else 0.0,
                        forward_x=safe_float(forward.x) if forward is not None else 0.0,
                        forward_y=safe_float(forward.y) if forward is not None else 0.0,
                        forward_z=safe_float(forward.z) if forward is not None else 0.0,
                        is_player=bool(score.mIsPlayer),
                    )
                )

            class_positions: dict[str, int] = {}
            for driver in sorted(
                drivers,
                key=lambda item: item.position or 999,
            ):
                class_name = driver.vehicle_class or "UNKNOWN"
                class_positions[class_name] = (
                    class_positions.get(class_name, 0) + 1
                )
                driver.position_in_class = class_positions[class_name]

            player_row = next(
                (driver for driver in drivers if driver.is_player),
                None,
            )
            if player_row is not None:
                for driver in drivers:
                    delta_x = driver.world_x - player_row.world_x
                    delta_y = driver.world_y - player_row.world_y
                    delta_z = driver.world_z - player_row.world_z
                    driver.relative_rotated_x_m = (
                        delta_x * player_row.right_x
                        + delta_y * player_row.right_y
                        + delta_z * player_row.right_z
                    )
                    driver.relative_rotated_y_m = (
                        delta_x * player_row.forward_x
                        + delta_y * player_row.forward_y
                        + delta_z * player_row.forward_z
                    )

            player = None
            player_index = safe_int(telemetry.playerVehicleIdx, -1)

            if (
                bool(telemetry.playerHasVehicle)
                and 0 <= player_index < int(
                    lmu_data.LMUConstants.MAX_MAPPED_VEHICLES
                )
            ):
                player = self._read_player(
                    telemetry.telemInfo[player_index]
                )

            yellow_raw = info.mYellowFlagState
            if isinstance(yellow_raw, bytes):
                yellow_state = int.from_bytes(
                    yellow_raw[:1],
                    "little",
                    signed=True,
                )
            else:
                yellow_state = safe_int(yellow_raw)

            self._update_weather_schedule()

            return SessionData(
                connected=True,
                game_version=safe_int(data.generic.gameVersion),
                track_name=decode_text(info.mTrackName),
                player_name=decode_text(info.mPlayerName),
                session=safe_int(info.mSession),
                current_time_s=safe_float(info.mCurrentET),
                remaining_time_s=safe_float(info.mSessionTimeRemaining),
                max_laps=safe_int(info.mMaxLaps),
                track_length_m=safe_float(
                    getattr(info, "mLapDist", 0.0)
                ),
                sector_flags=tuple(
                    safe_int(value)
                    for value in list(
                        getattr(info, "mSectorFlag", (0, 0, 0))
                    )[:3]
                ),
                start_light=safe_int(
                    getattr(info, "mStartLight", 0)
                ),
                num_red_lights=safe_int(
                    getattr(info, "mNumRedLights", 0)
                ),
                in_realtime=bool(
                    getattr(info, "mInRealtime", False)
                ),
                game_phase=safe_int(info.mGamePhase),
                yellow_flag_state=yellow_state,
                raining=safe_float(info.mRaining),
                ambient_temp_c=safe_float(info.mAmbientTemp),
                track_temp_c=safe_float(info.mTrackTemp),
                time_of_day=safe_float(info.mTimeOfDay),
                track_grip_level=safe_int(info.mTrackGripLevel),
                dark_cloud=safe_float(
                    getattr(info, "mDarkCloud", 0.0)
                ),
                cloud_coverage=safe_int(
                    getattr(info, "mCloudCoverage", 0)
                ),
                min_path_wetness=safe_float(
                    getattr(info, "mMinPathWetness", 0.0)
                ),
                avg_path_wetness=safe_float(
                    getattr(info, "mAvgPathWetness", 0.0)
                ),
                max_path_wetness=safe_float(
                    getattr(info, "mMaxPathWetness", 0.0)
                ),
                wind_x_ms=safe_float(
                    getattr(getattr(info, "mWind", None), "x", 0.0)
                ),
                wind_y_ms=safe_float(
                    getattr(getattr(info, "mWind", None), "y", 0.0)
                ),
                wind_z_ms=safe_float(
                    getattr(getattr(info, "mWind", None), "z", 0.0)
                ),
                wind_speed_kmh=math.hypot(
                    safe_float(getattr(getattr(info, "mWind", None), "x", 0.0)),
                    safe_float(getattr(getattr(info, "mWind", None), "y", 0.0)),
                    safe_float(getattr(getattr(info, "mWind", None), "z", 0.0)),
                ) * 3.6,
                weather_schedule=self._weather_schedule,
                track_limits_steps_per_penalty=safe_int(
                    getattr(
                        info,
                        "mTrackLimitsStepsPerPenalty",
                        0,
                    )
                ),
                track_limits_steps_per_point=safe_int(
                    getattr(
                        info,
                        "mTrackLimitsStepsPerPoint",
                        0,
                    )
                ),
                player=player,
                drivers=drivers,
            )

        except (
            AttributeError,
            IndexError,
            OSError,
            ValueError,
            BufferError,
        ) as exc:
            return SessionData(
                connected=False,
                error=f"Erro de leitura: {exc}",
            )

    def _update_weather_schedule(self) -> None:
        now = time.monotonic()
        if now - self._last_weather_poll_at < 10.0:
            return

        self._last_weather_poll_at = now
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:6397/rest/sessions/weather",
                timeout=0.35,
            ) as response:
                payload = json.loads(
                    response.read().decode("utf-8")
                )
            if isinstance(payload, dict):
                self._weather_schedule = payload
        except (
            OSError,
            TimeoutError,
            ValueError,
            json.JSONDecodeError,
            urllib.error.URLError,
        ):
            # A telemetria continua funcionando mesmo quando a API REST
            # do LMU ainda nao esta pronta ou muda de disponibilidade.
            pass

    def _read_player(self, raw: Any) -> PlayerData:
        velocity = raw.mLocalVel
        speed_ms = math.sqrt(
            safe_float(velocity.x) ** 2
            + safe_float(velocity.y) ** 2
            + safe_float(velocity.z) ** 2
        )

        wheels: list[WheelData] = []

        for wheel in raw.mWheels:
            temps = wheel.mTemperature
            inner_temps = getattr(
                wheel, "mTireInnerLayerTemperature", (0.0, 0.0, 0.0)
            )
            carcass_kelvin = safe_float(
                getattr(wheel, "mTireCarcassTemperature", 0.0)
            )

            wheels.append(
                WheelData(
                    pressure_kpa=safe_float(wheel.mPressure),
                    wear=safe_float(wheel.mWear),
                    brake_temp_c=safe_float(wheel.mBrakeTemp),
                    surface_left_c=safe_float(temps[0]) - 273.15,
                    surface_center_c=safe_float(temps[1]) - 273.15,
                    surface_right_c=safe_float(temps[2]) - 273.15,
                    flat=bool(wheel.mFlat),
                    detached=bool(wheel.mDetached),
                    compound_type=safe_int(wheel.mCompoundType),
                    suspension_deflection_m=safe_float(
                        getattr(wheel, "mSuspensionDeflection", 0.0)
                    ),
                    ride_height_m=safe_float(
                        getattr(wheel, "mRideHeight", 0.0)
                    ),
                    susp_force_n=safe_float(
                        getattr(wheel, "mSuspForce", 0.0)
                    ),
                    brake_pressure=safe_float(
                        getattr(wheel, "mBrakePressure", 0.0)
                    ),
                    rotation_rad_s=safe_float(
                        getattr(wheel, "mRotation", 0.0)
                    ),
                    lateral_patch_velocity_ms=safe_float(
                        getattr(wheel, "mLateralPatchVel", 0.0)
                    ),
                    longitudinal_patch_velocity_ms=safe_float(
                        getattr(wheel, "mLongitudinalPatchVel", 0.0)
                    ),
                    lateral_ground_velocity_ms=safe_float(
                        getattr(wheel, "mLateralGroundVel", 0.0)
                    ),
                    longitudinal_ground_velocity_ms=safe_float(
                        getattr(wheel, "mLongitudinalGroundVel", 0.0)
                    ),
                    camber_rad=safe_float(
                        getattr(wheel, "mCamber", 0.0)
                    ),
                    toe_rad=safe_float(
                        getattr(wheel, "mToe", 0.0)
                    ),
                    lateral_force_n=safe_float(
                        getattr(wheel, "mLateralForce", 0.0)
                    ),
                    longitudinal_force_n=safe_float(
                        getattr(wheel, "mLongitudinalForce", 0.0)
                    ),
                    tire_load_n=safe_float(
                        getattr(wheel, "mTireLoad", 0.0)
                    ),
                    grip_fraction=safe_float(
                        getattr(wheel, "mGripFract", 0.0)
                    ),
                    terrain_name=decode_text(
                        getattr(wheel, "mTerrainName", b"")
                    ),
                    surface_type=safe_int(
                        getattr(wheel, "mSurfaceType", 0)
                    ),
                    static_undeflected_radius_cm=safe_float(
                        getattr(wheel, "mStaticUndeflectedRadius", 0.0)
                    ),
                    vertical_tire_deflection_m=safe_float(
                        getattr(wheel, "mVerticalTireDeflection", 0.0)
                    ),
                    wheel_y_location_m=safe_float(
                        getattr(wheel, "mWheelYLocation", 0.0)
                    ),
                    carcass_temp_c=(
                        carcass_kelvin - 273.15
                        if carcass_kelvin > 100.0
                        else 0.0
                    ),
                    inner_left_c=(
                        safe_float(inner_temps[0]) - 273.15
                        if safe_float(inner_temps[0]) > 100.0
                        else 0.0
                    ),
                    inner_center_c=(
                        safe_float(inner_temps[1]) - 273.15
                        if safe_float(inner_temps[1]) > 100.0
                        else 0.0
                    ),
                    inner_right_c=(
                        safe_float(inner_temps[2]) - 273.15
                        if safe_float(inner_temps[2]) > 100.0
                        else 0.0
                    ),
                    optimal_temp_c=safe_float(
                        getattr(wheel, "mOptimalTemp", 0.0)
                    ),
                    compound_index=safe_int(
                        getattr(wheel, "mCompoundIndex", 0)
                    ),
                )
            )

        sector = safe_int(raw.mCurrentSector) & 0x7FFFFFFF

        return PlayerData(
            vehicle_name=decode_text(raw.mVehicleName),
            vehicle_model=decode_text(raw.mVehicleModel),
            speed_kmh=speed_ms * 3.6,
            rpm=safe_float(raw.mEngineRPM),
            max_rpm=safe_float(raw.mEngineMaxRPM),
            gear=safe_int(raw.mGear),
            throttle=safe_float(raw.mFilteredThrottle),
            brake=safe_float(raw.mFilteredBrake),
            steering=safe_float(raw.mFilteredSteering),
            clutch=safe_float(raw.mFilteredClutch),
            fuel_liters=safe_float(raw.mFuel),
            fuel_capacity_liters=safe_float(raw.mFuelCapacity),
            lap=safe_int(raw.mLapNumber),
            sector=sector,
            delta_best_s=safe_float(raw.mDeltaBest),
            gap_ahead_s=safe_float(raw.mTimeGapCarAhead),
            gap_behind_s=safe_float(raw.mTimeGapCarBehind),
            battery_fraction=safe_float(raw.mBatteryChargeFraction),
            state_of_charge=safe_float(raw.mStateOfCharge),
            virtual_energy=safe_float(raw.mVirtualEnergy),
            regen_kw=safe_float(
                getattr(raw, "mRegen", 0.0)
            ),
            electric_motor_torque_nm=safe_float(
                getattr(raw, "mElectricBoostMotorTorque", 0.0)
            ),
            electric_motor_rpm=safe_float(
                getattr(raw, "mElectricBoostMotorRPM", 0.0)
            ),
            electric_motor_temp_c=safe_float(
                getattr(raw, "mElectricBoostMotorTemperature", 0.0)
            ),
            electric_motor_water_temp_c=safe_float(
                getattr(raw, "mElectricBoostWaterTemperature", 0.0)
            ),
            electric_motor_state=safe_int(
                getattr(raw, "mElectricBoostMotorState", 0)
            ),
            track_limits_steps=safe_int(
                getattr(raw, "mTrackLimitsSteps", 0)
            ),
            front_tire_compound=decode_text(raw.mFrontTireCompoundName),
            rear_tire_compound=decode_text(raw.mRearTireCompoundName),
            wheels=wheels,
        )

    def close(self) -> None:
        if self.memory is not None:
            try:
                self.memory.close()
            except (
                AttributeError,
                OSError,
                BufferError,
            ):
                pass

        self.memory = None
