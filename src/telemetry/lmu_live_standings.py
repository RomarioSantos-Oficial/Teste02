from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Any

try:
    from websockets.sync.client import connect
except ImportError:  # pragma: no cover
    connect = None


@dataclass(frozen=True, slots=True)
class LivePenalty:
    driver_name: str = ""
    position: int = 0
    drive_through: int = 0
    stop_go: int = 0
    time_s: float = 0.0
    finish_status: str = ""
    time_into_lap_s: float = 0.0
    lap_distance_m: float = 0.0

    @property
    def count(self) -> int:
        return self.drive_through + self.stop_go + int(self.time_s > 0.0)


class LMULiveStandingsClient:
    """Le DT, SG e TIME publicados pela UI interna do LMU."""

    URL = "ws://127.0.0.1:6398/websocket/ui"
    FRESH_SECONDS = 5.0

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = bool(enabled and connect is not None)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._by_name: dict[str, LivePenalty] = {}
        self._by_position: dict[int, LivePenalty] = {}
        self._updated_at = 0.0
        self._thread: threading.Thread | None = None
        if self.enabled:
            self._thread = threading.Thread(
                target=self._run,
                name="SectorFlow-LMULiveStandings",
                daemon=True,
            )
            self._thread.start()

    def enrich(self, session: Any) -> None:
        with self._lock:
            if time.monotonic() - self._updated_at > self.FRESH_SECONDS:
                return
            by_name = dict(self._by_name)
            by_position = dict(self._by_position)
        for driver in list(getattr(session, "drivers", []) or []):
            key = self._normalize_name(getattr(driver, "driver_name", ""))
            position = int(getattr(driver, "position", 0) or 0)
            penalty = by_name.get(key) or by_position.get(position)
            if penalty is None:
                continue
            if penalty.drive_through > 0:
                driver.penalty_type = "Drive Thru"
                driver.penalty_time_s = 0.0
            elif penalty.stop_go > 0:
                driver.penalty_type = "Stop/Go"
                driver.penalty_time_s = (
                    float(penalty.stop_go) if penalty.stop_go > 1 else 0.0
                )
            elif penalty.time_s > 0.0:
                driver.penalty_type = "Time"
                driver.penalty_time_s = penalty.time_s
            else:
                driver.penalty_type = ""
                driver.penalty_time_s = 0.0
            if penalty.count > 0:
                driver.penalties = max(
                    int(getattr(driver, "penalties", 0) or 0), penalty.count
                )
            if "DQ" in penalty.finish_status.upper():
                driver.finish_status = 3
                driver.finish_status_name = "DQ"
            # O websocket da UI e a fonte de API realmente em tempo real.
            # Ele atualiza estes campos com muito mais frequencia que o REST.
            if penalty.time_into_lap_s >= 0.0:
                driver.time_into_lap_s = penalty.time_into_lap_s
            if penalty.lap_distance_m >= 0.0:
                driver.lap_distance_m = penalty.lap_distance_m

    def close(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.5)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                assert connect is not None
                with connect(
                    self.URL, open_timeout=2.0, close_timeout=0.5
                ) as socket:
                    socket.send(json.dumps({
                        "messageType": "SUB", "topic": "LiveStandings"
                    }))
                    while not self._stop.is_set():
                        self._process_message(socket.recv(timeout=2.0))
            except Exception:
                self._stop.wait(1.0)

    def _process_message(self, message: str | bytes) -> bool:
        try:
            payload = json.loads(message)
        except (TypeError, ValueError, json.JSONDecodeError):
            return False
        if str(payload.get("topic", "")).casefold() != "livestandings":
            return False
        body = payload.get("body")
        if not isinstance(body, list):
            return False
        by_name: dict[str, LivePenalty] = {}
        by_position: dict[int, LivePenalty] = {}
        for raw in body:
            if not isinstance(raw, dict):
                continue
            values = raw.get("penalties")
            values = values if isinstance(values, dict) else {}
            driver_name = str(
                raw.get("driverName") or raw.get("name")
                or raw.get("driver") or ""
            ).strip()
            position = self._integer(
                raw.get("position") or raw.get("place")
                or raw.get("racePosition")
            )
            item = LivePenalty(
                driver_name=driver_name,
                position=position,
                drive_through=self._integer(values.get("DT")),
                stop_go=self._integer(values.get("SG")),
                time_s=self._number(values.get("TIME")),
                finish_status=str(raw.get("finishStatus", "") or ""),
                time_into_lap_s=self._signed_number(raw.get("timeIntoLap")),
                lap_distance_m=self._signed_number(raw.get("lapDist")),
            )
            key = self._normalize_name(driver_name)
            if key:
                by_name[key] = item
            if position > 0:
                by_position[position] = item
        with self._lock:
            self._by_name = by_name
            self._by_position = by_position
            self._updated_at = time.monotonic()
        return True

    @staticmethod
    def _normalize_name(value: Any) -> str:
        text = re.sub(r"#\d+$", "", str(value or "").strip())
        return " ".join(text.casefold().split())

    @staticmethod
    def _number(value: Any) -> float:
        try:
            return max(0.0, float(value or 0.0))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _signed_number(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return -1.0

    @classmethod
    def _integer(cls, value: Any) -> int:
        return int(round(cls._number(value)))
