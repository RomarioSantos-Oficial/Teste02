from __future__ import annotations
import math
import sys
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
    raise ImportError("pyLMUSharedMemory nao encontrado em vendor/pyLMUSharedMemory.") from exc

def decode_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.split(b"\x00", 1)[0].decode("utf-8", errors="replace").strip()
    try:
        raw = bytes(value)
        return raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace").strip()
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

class LMUAdapter:
    def __init__(self, copy_access: bool = True) -> None:
        self.copy_access = copy_access
        self.memory: lmu_mmap.MMapControl | None = None

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
            return SessionData(connected=False, error="Aguardando o LMU.")
        try:
            assert self.memory is not None
            self.memory.update()
            if not self.is_connected():
                return SessionData(connected=False, error="LMU nao esta fornecendo dados.")

            data = self.memory.data
            info = data.scoring.scoringInfo
            telemetry = data.telemetry
            drivers: list[DriverData] = []
            vehicle_count = max(0, min(safe_int(info.mNumVehicles), 104))

            for index in range(vehicle_count):
                score = data.scoring.vehScoringInfo[index]
                drivers.append(DriverData(
                    driver_name=decode_text(score.mDriverName),
                    vehicle_name=decode_text(score.mVehicleName),
                    vehicle_class=decode_text(score.mVehicleClass),
                    position=safe_int(score.mPlace),
                    laps=safe_int(score.mTotalLaps),
                    best_lap_s=safe_float(score.mBestLapTime),
                    last_lap_s=safe_float(score.mLastLapTime),
                    gap_ahead_s=safe_float(score.mTimeBehindNext),
                    gap_leader_s=safe_float(score.mTimeBehindLeader),
                    in_pits=bool(score.mInPits),
                    penalties=safe_int(score.mNumPenalties),
                    flag=safe_int(score.mFlag),
                    lap_distance_m=safe_float(score.mLapDist),
                    is_player=bool(score.mIsPlayer),
                ))

            player = None
            player_index = safe_int(telemetry.playerVehicleIdx, -1)
            if bool(telemetry.playerHasVehicle) and 0 <= player_index < 104:
                player = self._read_player(telemetry.telemInfo[player_index])

            yellow_raw = info.mYellowFlagState
            if isinstance(yellow_raw, bytes):
                yellow_state = int.from_bytes(yellow_raw[:1], "little", signed=True)
            else:
                yellow_state = safe_int(yellow_raw)

            return SessionData(
                connected=True,
                game_version=safe_int(data.generic.gameVersion),
                track_name=decode_text(info.mTrackName),
                player_name=decode_text(info.mPlayerName),
                session=safe_int(info.mSession),
                current_time_s=safe_float(info.mCurrentET),
                remaining_time_s=safe_float(info.mSessionTimeRemaining),
                max_laps=safe_int(info.mMaxLaps),
                game_phase=safe_int(info.mGamePhase),
                yellow_flag_state=yellow_state,
                raining=safe_float(info.mRaining),
                ambient_temp_c=safe_float(info.mAmbientTemp),
                track_temp_c=safe_float(info.mTrackTemp),
                time_of_day=safe_float(info.mTimeOfDay),
                track_grip_level=safe_int(info.mTrackGripLevel),
                player=player,
                drivers=drivers,
            )
        except (AttributeError, IndexError, OSError, ValueError, BufferError) as exc:
            return SessionData(connected=False, error=f"Erro de leitura: {exc}")

    def _read_player(self, raw: Any) -> PlayerData:
        velocity = raw.mLocalVel
        speed_ms = math.sqrt(safe_float(velocity.x)**2 + safe_float(velocity.y)**2 + safe_float(velocity.z)**2)
        wheels: list[WheelData] = []
        for wheel in raw.mWheels:
            temps = wheel.mTemperature
            wheels.append(WheelData(
                pressure_kpa=safe_float(wheel.mPressure),
                wear=safe_float(wheel.mWear),
                brake_temp_c=safe_float(wheel.mBrakeTemp),
                surface_left_c=safe_float(temps[0]) - 273.15,
                surface_center_c=safe_float(temps[1]) - 273.15,
                surface_right_c=safe_float(temps[2]) - 273.15,
                flat=bool(wheel.mFlat),
                detached=bool(wheel.mDetached),
                compound_type=safe_int(wheel.mCompoundType),
            ))
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
            front_tire_compound=decode_text(raw.mFrontTireCompoundName),
            rear_tire_compound=decode_text(raw.mRearTireCompoundName),
            wheels=wheels,
        )

    def close(self) -> None:
        if self.memory is not None:
            try:
                self.memory.close()
            except (AttributeError, OSError, BufferError):
                pass
        self.memory = None
