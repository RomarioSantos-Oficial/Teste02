from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class EndpointSpec:
    name: str
    path: str
    interval_s: float
    timeout_s: float = 0.45
    scope: str = "session"


@dataclass(slots=True)
class LMURestSnapshot:
    payloads: dict[str, Any] = field(default_factory=dict)
    updated_at: dict[str, float] = field(default_factory=dict)
    available: bool = False
    last_success_at: float = 0.0
    last_error: str = ""

    def value(
        self,
        name: str,
        *,
        max_age_s: float | None = None,
        now: float | None = None,
    ) -> Any:
        if name not in self.payloads:
            return None
        if max_age_s is not None:
            checked_at = time.monotonic() if now is None else now
            updated = self.updated_at.get(name, 0.0)
            if updated <= 0.0 or checked_at - updated > max_age_s:
                return None
        return self.payloads[name]


class LMULocalRestClient:
    """Coleta a API local do LMU sem bloquear a telemetria de alta frequencia."""

    ENDPOINTS = (
        EndpointSpec(
            "game_state",
            "/rest/sessions/GetGameState",
            0.50,
            scope="always",
        ),
        EndpointSpec(
            "navigation_state",
            "/navigation/state",
            1.00,
            scope="session",
        ),
        EndpointSpec(
            "session_info",
            "/rest/watch/sessionInfo",
            1.00,
        ),
        EndpointSpec(
            "session_settings",
            "/rest/sessions",
            30.00,
            timeout_s=0.60,
        ),
        EndpointSpec(
            "standings",
            "/rest/watch/standings",
            1.00,
            timeout_s=0.60,
        ),
        EndpointSpec(
            "vehicle_condition",
            "/rest/garage/getVehicleCondition",
            1.00,
            scope="vehicle",
        ),
        EndpointSpec(
            "strategy_usage",
            "/rest/strategy/usage",
            3.00,
            timeout_s=0.60,
        ),
        EndpointSpec(
            "pitstop_estimate",
            "/rest/strategy/pitstop-estimate",
            2.00,
        ),
        EndpointSpec(
            "incidents",
            "/rest/watch/getIncidentsList/1",
            3.00,
        ),
        EndpointSpec(
            "weather",
            "/rest/sessions/weather",
            10.00,
            timeout_s=0.60,
        ),
        EndpointSpec(
            "event_sessions",
            "/rest/sessions/GetSessionsInfoForEvent",
            15.00,
        ),
        EndpointSpec(
            "loading_screen",
            "/navigation/GetLoadingScreen",
            30.00,
            timeout_s=0.60,
        ),
    )

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 6397,
        *,
        enabled: bool = True,
    ) -> None:
        self.base_url = f"http://{host}:{int(port)}"
        self.enabled = bool(enabled)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._payloads: dict[str, Any] = {}
        self._updated_at: dict[str, float] = {}
        self._next_due: dict[str, float] = {
            spec.name: 0.0 for spec in self.ENDPOINTS
        }
        self._last_success_at = 0.0
        self._last_error = ""
        self._errors: dict[str, str] = {}
        self._failure_counts: dict[str, int] = {}
        self._circuit_open_until = 0.0
        self._session_available = False
        self._vehicle_available = False
        # Trava de seguranca: fora do carro apenas GetGameState continua
        # ativo. A saida precisa persistir por 1 s e a volta exige duas
        # confirmacoes consecutivas do probe de 500 ms.
        self._data_flow_active = True
        self._outside_since: float | None = None
        self._inside_confirmations = 0
        self._session_identity: tuple[str, str, str] | None = None
        self._thread: threading.Thread | None = None
        if self.enabled:
            self._thread = threading.Thread(
                target=self._worker,
                name="SectorFlow-LMURest",
                daemon=True,
            )
            self._thread.start()

    def snapshot(self) -> LMURestSnapshot:
        with self._lock:
            return LMURestSnapshot(
                # Cada resposta e substituida por inteiro e nunca e alterada
                # pela thread coletora. Copiar apenas o dicionario externo
                # evita duplicar standings e previsao 20 vezes por segundo.
                payloads=dict(self._payloads),
                updated_at=dict(self._updated_at),
                available=(
                    self._last_success_at > 0.0
                    and time.monotonic() - self._last_success_at <= 5.0
                ),
                last_success_at=self._last_success_at,
                last_error=self._last_error,
            )

    def close(self) -> None:
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.5)

    def trigger(self) -> None:
        self._wake.set()

    @property
    def data_flow_active(self) -> bool:
        with self._lock:
            return self._data_flow_active

    def _set_data_flow_active(self, active: bool, now: float) -> None:
        if active == self._data_flow_active:
            return
        self._data_flow_active = active
        self._session_available = active
        self._vehicle_available = active
        if active:
            # Nao aguarda os intervalos antigos ao voltar para o carro.
            for spec in self.ENDPOINTS:
                if spec.scope != "always":
                    self._next_due[spec.name] = 0.0
        else:
            # Impede que dados da garagem/carro anterior sejam reaplicados.
            retained = {"game_state"}
            self._payloads = {
                name: value for name, value in self._payloads.items()
                if name in retained
            }
            self._updated_at = {
                name: value for name, value in self._updated_at.items()
                if name in retained
            }
            for spec in self.ENDPOINTS:
                if spec.scope != "always":
                    self._next_due[spec.name] = now + spec.interval_s

    def _update_vehicle_presence(self, payload: dict[str, Any], now: float) -> None:
        inside = bool(payload.get("playerVehicleLoaded", False)) and bool(
            payload.get("inControlOfVehicle", False)
        ) and not bool(payload.get("inMonitor", False)) and not bool(
            payload.get("isReplayActive", False)
        )
        if inside:
            self._outside_since = None
            self._inside_confirmations += 1
            if self._inside_confirmations >= 2:
                self._set_data_flow_active(True, now)
            return

        self._inside_confirmations = 0
        if self._outside_since is None:
            self._outside_since = now
        if now - self._outside_since >= 1.0:
            self._set_data_flow_active(False, now)

    def _worker(self) -> None:
        while not self._stop.is_set():
            now = time.monotonic()
            if now < self._circuit_open_until:
                self._wake.wait(
                    timeout=min(0.5, self._circuit_open_until - now)
                )
                self._wake.clear()
                continue
            due = [
                spec
                for spec in self.ENDPOINTS
                if now >= self._next_due.get(spec.name, 0.0)
                and self._scope_enabled(spec.scope)
            ]
            if not due:
                future = [
                    self._next_due.get(spec.name, now + 0.25)
                    for spec in self.ENDPOINTS
                    if self._scope_enabled(spec.scope)
                ]
                delay = max(
                    0.05,
                    min(0.25, min(future, default=now + 0.25) - now),
                )
                self._wake.wait(timeout=delay)
                self._wake.clear()
                continue

            for spec in due:
                if self._stop.is_set():
                    break
                self._poll(spec)

    def _scope_enabled(self, scope: str) -> bool:
        if scope == "always":
            return True
        if scope == "vehicle":
            return self._vehicle_available
        return self._session_available

    def _poll(self, spec: EndpointSpec) -> None:
        requested_at = time.monotonic()
        try:
            request = urllib.request.Request(
                self.base_url + spec.path,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "SectorFlow/LMULocalRestV2",
                },
                method="GET",
            )
            with urllib.request.urlopen(
                request,
                timeout=max(0.15, spec.timeout_s),
            ) as response:
                raw = response.read()
            payload = (
                json.loads(raw.decode("utf-8", errors="replace"))
                if raw
                else None
            )
        except (
            OSError,
            TimeoutError,
            ValueError,
            json.JSONDecodeError,
            urllib.error.URLError,
        ) as exc:
            with self._lock:
                failures = self._failure_counts.get(spec.name, 0) + 1
                self._failure_counts[spec.name] = failures
                self._errors[spec.name] = type(exc).__name__
                self._last_error = "; ".join(
                    f"{name}: {error}"
                    for name, error in sorted(self._errors.items())
                )
                # Backoff por endpoint. Evita martelar o servidor HTTP
                # embutido do LMU durante loading, garagem ou encerramento.
                self._next_due[spec.name] = requested_at + min(
                    30.0,
                    max(spec.interval_s, 2.0) * (2 ** min(failures - 1, 4)),
                )
                if failures >= 5:
                    self._circuit_open_until = max(
                        self._circuit_open_until,
                        requested_at + 5.0,
                    )
            return

        completed_at = time.monotonic()
        with self._lock:
            self._payloads[spec.name] = payload
            self._updated_at[spec.name] = completed_at
            self._last_success_at = completed_at
            self._errors.pop(spec.name, None)
            self._failure_counts.pop(spec.name, None)
            self._last_error = "; ".join(
                f"{name}: {error}"
                for name, error in sorted(self._errors.items())
            )
            self._next_due[spec.name] = completed_at + spec.interval_s
            if spec.name == "session_info" and isinstance(payload, dict):
                identity = (
                    str(payload.get("session", "") or ""),
                    str(payload.get("trackName", "") or ""),
                    str(payload.get("startEventTime", "") or ""),
                )
                if identity != self._session_identity:
                    self._session_identity = identity
                    # Descarta o multiplicador anterior e solicita novamente
                    # imediatamente ao entrar em cada nova sessao.
                    self._payloads.pop("session_settings", None)
                    self._updated_at.pop("session_settings", None)
                    self._next_due["session_settings"] = 0.0
            if spec.name == "game_state" and isinstance(payload, dict):
                self._update_vehicle_presence(payload, completed_at)
                if self._data_flow_active:
                    self._vehicle_available = bool(
                        payload.get("playerVehicleLoaded", False)
                    ) and not bool(payload.get("inMonitor", False))
                    self._session_available = True
            elif spec.name == "navigation_state" and isinstance(payload, dict):
                state = payload.get("state")
                navigation = (
                    str(state.get("navigationState", "") or "")
                    if isinstance(state, dict)
                    else ""
                )
                if navigation == "NAV_EVENT":
                    self._session_available = True
                elif navigation in {"NAV_MAIN_MENU", "NAV_OPTIONS"}:
                    self._session_available = False
                    self._vehicle_available = False
