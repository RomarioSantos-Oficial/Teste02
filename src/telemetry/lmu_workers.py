from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Callable

from .lmu_adapter import LMUAdapter, lmu_data, lmu_mmap, safe_float, safe_int
from .models import SessionData


@dataclass(frozen=True, slots=True)
class FastPlayerFrame:
    """Snapshot mínimo e imutável para o painel de direção."""

    connected: bool = False
    has_player: bool = False
    sampled_at: float = 0.0
    sequence: int = 0
    speed_kmh: float = 0.0
    rpm: float = 0.0
    max_rpm: float = 9000.0
    gear: int = 0
    throttle: float = 0.0
    brake: float = 0.0
    clutch: float = 0.0
    steering: float = 0.0


class FastTelemetryWorker:
    """Lê somente o jogador em background e nunca cria fila de quadros."""

    def __init__(self, interval_s: float = 0.010) -> None:
        self.interval_s = max(0.005, float(interval_s))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._memory: lmu_mmap.MMapControl | None = None
        self._latest = FastPlayerFrame()
        self._sequence = 0

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="SectorFlowFastTelemetry",
            daemon=True,
        )
        self._thread.start()

    def snapshot(self) -> FastPlayerFrame:
        # A troca de referência é atômica no CPython. O dataclass é imutável.
        return self._latest

    def close(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.5)
        self._thread = None
        self._close_memory()

    def _connect(self) -> bool:
        if self._memory is not None:
            return True
        try:
            memory = lmu_mmap.MMapControl(
                lmu_data.LMUConstants.LMU_SHARED_MEMORY_FILE,
                lmu_data.LMUObjectOut,
            )
            memory.create(0)
            self._memory = memory
            return True
        except (OSError, ValueError, BufferError):
            self._close_memory()
            return False

    def _close_memory(self) -> None:
        memory, self._memory = self._memory, None
        if memory is not None:
            try:
                memory.close()
            except (OSError, ValueError, BufferError):
                pass

    def _publish_empty(self) -> None:
        self._sequence += 1
        self._latest = FastPlayerFrame(sequence=self._sequence)

    def _run(self) -> None:
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                if not self._connect():
                    self._publish_empty()
                    self._stop.wait(0.25)
                    continue
                assert self._memory is not None
                self._memory.update()
                data = self._memory.data
                connected = bool(
                    data is not None
                    and safe_int(data.generic.gameVersion) > 0
                )
                telemetry = data.telemetry if connected else None
                player_index = safe_int(
                    getattr(telemetry, "playerVehicleIdx", -1), -1
                )
                has_player = bool(
                    telemetry is not None
                    and getattr(telemetry, "playerHasVehicle", False)
                    and 0 <= player_index
                    < int(lmu_data.LMUConstants.MAX_MAPPED_VEHICLES)
                )
                if not has_player:
                    self._sequence += 1
                    self._latest = FastPlayerFrame(
                        connected=connected,
                        sampled_at=time.monotonic(),
                        sequence=self._sequence,
                    )
                else:
                    raw = telemetry.telemInfo[player_index]
                    velocity = raw.mLocalVel
                    speed_ms = math.sqrt(
                        safe_float(velocity.x) ** 2
                        + safe_float(velocity.y) ** 2
                        + safe_float(velocity.z) ** 2
                    )
                    self._sequence += 1
                    self._latest = FastPlayerFrame(
                        connected=True,
                        has_player=True,
                        sampled_at=time.monotonic(),
                        sequence=self._sequence,
                        speed_kmh=speed_ms * 3.6,
                        rpm=safe_float(raw.mEngineRPM),
                        max_rpm=max(1.0, safe_float(raw.mEngineMaxRPM, 9000.0)),
                        gear=safe_int(raw.mGear),
                        throttle=safe_float(
                            getattr(raw, "mUnfilteredThrottle", raw.mFilteredThrottle)
                        ),
                        brake=safe_float(
                            getattr(raw, "mUnfilteredBrake", raw.mFilteredBrake)
                        ),
                        clutch=safe_float(
                            getattr(raw, "mUnfilteredClutch", raw.mFilteredClutch)
                        ),
                        steering=safe_float(
                            getattr(raw, "mUnfilteredSteering", raw.mFilteredSteering)
                        ),
                    )
            except (AttributeError, IndexError, OSError, ValueError, BufferError):
                self._publish_empty()
                self._close_memory()

            elapsed = time.monotonic() - started
            self._stop.wait(max(0.0, self.interval_s - elapsed))


class SessionTelemetryWorker:
    """Executa a leitura completa da sessão fora do event loop do Qt."""

    def __init__(
        self,
        interval_s: float = 0.050,
        adapter_factory: Callable[[], LMUAdapter] | None = None,
    ) -> None:
        self.interval_s = max(0.020, float(interval_s))
        self._adapter_factory = adapter_factory or (
            lambda: LMUAdapter(copy_access=True)
        )
        self._adapter: LMUAdapter | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._latest = SessionData(connected=False, error="Aguardando o LMU.")
        self._sequence = 0

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="SectorFlowSessionTelemetry",
            daemon=True,
        )
        self._thread.start()

    def snapshot(self) -> tuple[int, SessionData]:
        return self._sequence, self._latest

    def close(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        self._thread = None
        adapter, self._adapter = self._adapter, None
        if adapter is not None:
            adapter.close()

    def _run(self) -> None:
        self._adapter = self._adapter_factory()
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                session = self._adapter.read()
            except Exception as exc:  # protege o worker sem derrubar a UI
                session = SessionData(
                    connected=False,
                    error=f"Erro de leitura: {exc}",
                )
            self._latest = session
            self._sequence += 1
            elapsed = time.monotonic() - started
            wait = 0.25 if not session.connected else max(
                0.0, self.interval_s - elapsed
            )
            self._stop.wait(wait)
