from __future__ import annotations

import math
import sys
import platform
from pathlib import Path
from typing import Any

from .lmu_rest_client import LMULocalRestClient
from .lmu_rest_enrichment import apply_rest_snapshot
from .lmu_penalty_log import LMUPenaltyLogReader
from .lmu_live_standings import LMULiveStandingsClient
from .models import DriverData, PlayerData, SessionData, WheelData


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LMU_LIBRARY = PROJECT_ROOT / "vendor" / "pyLMUSharedMemory"

# Em executáveis empacotados pelo PyInstaller os dados podem ser colocados
# em locais diferentes (por exemplo em sys._MEIPASS ou dentro de pastas
# internas). Tentar detectar locais alternativos para tornar o import
# resiliente tanto durante o desenvolvimento quanto no build.
def _locate_pyLMU_shared():
    # candidato original no repositório
    candidates = [LMU_LIBRARY]
    # PyInstaller unpack location
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "vendor" / "pyLMUSharedMemory")
        candidates.append(Path(meipass) / "pyLMUSharedMemory")
    # procurar em sys.path por pastas que contenham o pacote
    for p in list(sys.path):
        try:
            base = Path(p)
        except Exception:
            continue
        candidates.append(base / "vendor" / "pyLMUSharedMemory")
        candidates.append(base / "pyLMUSharedMemory")

    for cand in candidates:
        try:
            if cand and cand.exists():
                return cand.resolve()
        except Exception:
            continue
    return LMU_LIBRARY

LMU_LIBRARY = _locate_pyLMU_shared()

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


_COMPOUND_NAMES = {
    0: "Soft",
    1: "Medium",
    2: "Hard",
    3: "Wet",
}


class LMUAdapter:
    def __init__(
        self,
        copy_access: bool = True,
        *,
        local_api_enabled: bool = True,
        local_api_host: str = "127.0.0.1",
        local_api_port: int = 6397,
    ) -> None:
        self.copy_access = copy_access
        self.memory: lmu_mmap.MMapControl | None = None
        self.local_api = LMULocalRestClient(
            host=local_api_host,
            port=local_api_port,
            enabled=local_api_enabled,
        )
        self.penalty_log = LMUPenaltyLogReader()
        self.live_standings = LMULiveStandingsClient()
        self._validity_vehicle_id: int | None = None
        self._validity_lap: int | None = None
        self._current_lap_was_invalid = False
        self._last_lap_was_invalid = False
        self._driver_lap_state: dict[
            int,
            tuple[int, float, float, bool],
        ] = {}
        self._driver_session_key = ""
        self._driver_last_current_et = 0.0

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
            self._prepare_driver_lap_tracking(info)

            # A API REST tem prioridade no enriquecimento posterior, mas a
            # telemetria compartilhada e a fonte mais confiavel para pneus e
            # danos dos carros que o LMU publica no quadro atual.
            telemetry_by_slot: dict[int, Any] = {}
            active_telemetry = max(
                0,
                min(
                    safe_int(getattr(telemetry, "activeVehicles", 0)),
                    int(lmu_data.LMUConstants.MAX_MAPPED_VEHICLES),
                ),
            )
            for telemetry_index in range(active_telemetry):
                raw_vehicle = telemetry.telemInfo[telemetry_index]
                raw_slot = safe_int(getattr(raw_vehicle, "mID", -1), -1)
                if raw_slot >= 0:
                    telemetry_by_slot[raw_slot] = raw_vehicle

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
                slot_id = safe_int(getattr(score, "mID", index))
                steam_id = safe_int(getattr(score, "mSteamID", 0))
                completed_laps = safe_int(
                    getattr(score, "mTotalLaps", 0)
                )
                lap_start_et = safe_float(
                    getattr(score, "mLapStartET", 0.0)
                )

                best_s1 = safe_float(getattr(score, "mBestSector1", 0.0))
                best_s12 = safe_float(getattr(score, "mBestSector2", 0.0))
                best_lap = safe_float(getattr(score, "mBestLapTime", 0.0))

                last_s1 = safe_float(getattr(score, "mLastSector1", 0.0))
                last_s12 = safe_float(getattr(score, "mLastSector2", 0.0))
                last_lap, last_lap_invalidated = (
                    self._resolve_driver_last_lap(
                        slot_id,
                        completed_laps,
                        lap_start_et,
                        safe_float(
                            getattr(score, "mLastLapTime", 0.0)
                        ),
                    )
                )

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
                raw_vehicle = telemetry_by_slot.get(slot_id)
                tire_compounds: list[str] = []
                damage_percent: float | None = None
                if raw_vehicle is not None:
                    raw_wheels = list(getattr(raw_vehicle, "mWheels", []) or [])
                    tire_compounds = [
                        _COMPOUND_NAMES.get(
                            safe_int(getattr(wheel, "mCompoundType", -1), -1),
                            "",
                        )
                        for wheel in raw_wheels[:4]
                    ]
                    # mDentSeverity possui oito regioes, normalmente 0..2.
                    # O percentual e deliberadamente marcado como estimado.
                    dent = list(getattr(raw_vehicle, "mDentSeverity", []) or [])
                    if dent:
                        severity = sum(
                            max(0, min(2, safe_int(value)))
                            for value in dent[:8]
                        )
                        detached = sum(
                            1 for wheel in raw_wheels[:4]
                            if bool(getattr(wheel, "mDetached", False))
                        )
                        damage_percent = min(
                            100.0,
                            severity / 16.0 * 100.0 + detached * 25.0,
                        )

                drivers.append(
                    DriverData(
                        slot_id=slot_id,
                        steam_id=str(steam_id) if steam_id > 0 else "",
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
                        laps=completed_laps,
                        current_sector=safe_int(getattr(score, "mSector", 0)),
                        best_lap_s=best_lap,
                        estimated_lap_s=safe_float(
                            getattr(score, "mEstimatedLapTime", 0.0)
                        ),
                        last_lap_s=last_lap,
                        last_lap_invalidated=last_lap_invalidated,
                        best_sector1_s=best_s1,
                        best_sector2_s=positive_difference(best_s12, best_s1),
                        best_sector3_s=positive_difference(best_lap, best_s12),
                        last_sector1_s=last_s1,
                        last_sector2_s=positive_difference(last_s12, last_s1),
                        last_sector3_s=positive_difference(last_lap, last_s12),
                        gap_ahead_s=safe_float(score.mTimeBehindNext),
                        gap_leader_s=safe_float(score.mTimeBehindLeader),
                        laps_behind_ahead=safe_int(
                            getattr(score, "mLapsBehindNext", 0)
                        ),
                        laps_behind_leader=safe_int(
                            getattr(score, "mLapsBehindLeader", 0)
                        ),
                        in_pits=bool(score.mInPits),
                        penalties=safe_int(score.mNumPenalties),
                        track_limits_steps=(
                            safe_int(getattr(raw_vehicle, "mTrackLimitsSteps", 0))
                            if raw_vehicle is not None
                            else None
                        ),
                        tire_compounds=tire_compounds,
                        damage_percent=damage_percent,
                        damage_is_estimated=damage_percent is not None,
                        flag=safe_int(score.mFlag),
                        lap_distance_m=safe_float(score.mLapDist),
                        time_into_lap_s=safe_float(
                            getattr(score, "mTimeIntoLap", 0.0)
                        ),
                        lap_start_event_time_s=safe_float(
                            getattr(score, "mLapStartET", 0.0)
                        ),
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
                        finish_status=safe_int(
                            getattr(score, "mFinishStatus", 0)
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
            else:
                self._reset_lap_validity()

            yellow_raw = info.mYellowFlagState
            if isinstance(yellow_raw, bytes):
                yellow_state = int.from_bytes(
                    yellow_raw[:1],
                    "little",
                    signed=True,
                )
            else:
                yellow_state = safe_int(yellow_raw)

            session = SessionData(
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
                application_location=safe_int(
                    getattr(
                        getattr(data.generic, "appInfo", None),
                        "mOptionsLocation",
                        0,
                    )
                ),
                player_has_vehicle=bool(
                    getattr(telemetry, "playerHasVehicle", False)
                ),
                player_synced=bool(player_row is not None and player is not None),
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
            session = apply_rest_snapshot(
                session,
                self.local_api.snapshot(),
            )
            # Fora do carro a thread REST mantem somente o probe leve. Nao
            # consulta nem aplica fontes auxiliares ate duas confirmacoes de
            # que o jogador voltou ao cockpit.
            if self.local_api.data_flow_active:
                self.live_standings.enrich(session)
                self.penalty_log.enrich(session)
            return session

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
                    surface_left_c=(
                        safe_float(temps[0]) - 273.15
                        if safe_float(temps[0]) > 100.0
                        else 0.0
                    ),
                    surface_center_c=(
                        safe_float(temps[1]) - 273.15
                        if safe_float(temps[1]) > 100.0
                        else 0.0
                    ),
                    surface_right_c=(
                        safe_float(temps[2]) - 273.15
                        if safe_float(temps[2]) > 100.0
                        else 0.0
                    ),
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

        lap_number = safe_int(raw.mLapNumber)
        current_invalid, last_invalid = self._update_lap_validity(
            safe_int(getattr(raw, "mID", -1), -1),
            lap_number,
            bool(getattr(raw, "mLapInvalidated", False)),
        )

        return PlayerData(
            vehicle_name=decode_text(raw.mVehicleName),
            vehicle_model=decode_text(raw.mVehicleModel),
            ignition_starter=safe_int(
                getattr(raw, "mIgnitionStarter", 0)
            ),
            speed_kmh=speed_ms * 3.6,
            rpm=safe_float(raw.mEngineRPM),
            max_rpm=safe_float(raw.mEngineMaxRPM),
            gear=safe_int(raw.mGear),
            throttle=safe_float(raw.mFilteredThrottle),
            brake=safe_float(raw.mFilteredBrake),
            # Comando direto do volante, sem o atraso do filtro interno do
            # jogo. O fallback preserva compatibilidade com mapas antigos.
            steering=safe_float(
                getattr(raw, "mUnfilteredSteering", raw.mFilteredSteering)
            ),
            clutch=safe_float(raw.mFilteredClutch),
            fuel_liters=safe_float(raw.mFuel),
            fuel_capacity_liters=safe_float(raw.mFuelCapacity),
            lap=lap_number,
            sector=sector,
            delta_best_s=safe_float(raw.mDeltaBest),
            gap_ahead_s=safe_float(raw.mTimeGapCarAhead),
            gap_behind_s=safe_float(raw.mTimeGapCarBehind),
            battery_fraction=safe_float(raw.mBatteryChargeFraction),
            state_of_charge=safe_float(raw.mStateOfCharge),
            virtual_energy=safe_float(raw.mVirtualEnergy),
            body_damage=[
                safe_int(value)
                for value in list(
                    getattr(raw, "mDentSeverity", ())
                )[:8]
            ],
            body_detached=bool(
                getattr(raw, "mDetached", False)
            ),
            last_impact_time_s=safe_float(
                getattr(raw, "mLastImpactET", 0.0)
            ),
            vehicle_elapsed_time_s=safe_float(
                getattr(raw, "mElapsedTime", 0.0)
            ),
            last_impact_magnitude=safe_float(
                getattr(raw, "mLastImpactMagnitude", 0.0)
            ),
            last_impact_position=(
                -safe_float(
                    getattr(getattr(raw, "mLastImpactPos", None), "x", 0.0)
                ),
                safe_float(
                    getattr(getattr(raw, "mLastImpactPos", None), "z", 0.0)
                ),
            ),
            current_lap_invalidated=current_invalid,
            last_lap_invalidated=last_invalid,
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

    def _update_lap_validity(
        self,
        vehicle_id: int,
        lap_number: int,
        invalidated: bool,
    ) -> tuple[bool, bool]:
        if (
            self._validity_vehicle_id != vehicle_id
            or self._validity_lap is None
            or lap_number < self._validity_lap
        ):
            self._validity_vehicle_id = vehicle_id
            self._validity_lap = lap_number
            self._current_lap_was_invalid = bool(invalidated)
            self._last_lap_was_invalid = False
        elif lap_number > self._validity_lap:
            self._last_lap_was_invalid = (
                self._current_lap_was_invalid
                if lap_number == self._validity_lap + 1
                else False
            )
            self._validity_lap = lap_number
            self._current_lap_was_invalid = bool(invalidated)
        else:
            # Conserva a invalidacao ate o fim da volta, mesmo que o jogo
            # deixe de sinaliza-la em algum quadro da telemetria.
            self._current_lap_was_invalid |= bool(invalidated)
        return self._current_lap_was_invalid, self._last_lap_was_invalid

    def _reset_lap_validity(self) -> None:
        self._validity_vehicle_id = None
        self._validity_lap = None
        self._current_lap_was_invalid = False
        self._last_lap_was_invalid = False

    def _prepare_driver_lap_tracking(self, info: Any) -> None:
        session_key = "|".join(
            (
                decode_text(getattr(info, "mTrackName", b"")),
                str(safe_int(getattr(info, "mSession", 0))),
                str(safe_int(getattr(info, "mMaxLaps", 0))),
            )
        )
        current_et = safe_float(getattr(info, "mCurrentET", 0.0))
        clock_restarted = (
            self._driver_last_current_et > 2.0
            and current_et + 2.0 < self._driver_last_current_et
        )
        if session_key != self._driver_session_key or clock_restarted:
            self._driver_lap_state.clear()
            self._driver_session_key = session_key
        self._driver_last_current_et = current_et

    def _resolve_driver_last_lap(
        self,
        slot_id: int,
        completed_laps: int,
        lap_start_et: float,
        official_last_lap: float,
    ) -> tuple[float, bool]:
        """Preserva o tempo de voltas que o scoring marcou como inválidas."""
        previous = self._driver_lap_state.get(slot_id)
        lap_time = official_last_lap if official_last_lap > 0.0 else 0.0
        invalidated = False

        if previous is not None:
            previous_laps, previous_start, cached_time, cached_invalid = previous
            if completed_laps < previous_laps:
                previous = None
            elif completed_laps == previous_laps:
                if lap_time <= 0.0:
                    lap_time = cached_time
                    invalidated = cached_invalid
            else:
                derived = lap_start_et - previous_start
                if lap_time <= 0.0 and 10.0 <= derived <= 1800.0:
                    lap_time = derived
                    invalidated = True

        self._driver_lap_state[slot_id] = (
            completed_laps,
            lap_start_et,
            lap_time,
            invalidated,
        )
        return lap_time, invalidated

    def close(self) -> None:
        self.local_api.close()
        self.live_standings.close()
        self.penalty_log.close()
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
        self._reset_lap_validity()
