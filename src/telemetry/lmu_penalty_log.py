from __future__ import annotations

import html
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_XML_PENALTY = re.compile(r"<Penalty\s+([^>]+)>", re.IGNORECASE)
_XML_ATTRIBUTE = re.compile(r'(\w+)="([^"]*)"')
_TRACE_MESSAGE = re.compile(
    r"Msg:\s*(.+?)\s+received\s+(.+?)\s+penalty,\s*"
    r"([0-9.]+)s,\s*([0-9]+)laps",
    re.IGNORECASE,
)
_LOCAL_PENALTY = re.compile(
    r"Local penalty\s+et=([0-9.]+)\s+(-?\d+)\s+"
    r"([0-9.]+)\s+(-?\d+)\s+(-?\d+)\s+\"([^\"]*)\"",
    re.IGNORECASE,
)

_TRACE_TYPES = {
    0: "Stop/Go",
    1: "Drive Thru",
    3: "Time",
}


@dataclass(frozen=True, slots=True)
class PenaltyEvent:
    driver_name: str = ""
    penalty_type: str = ""
    time_s: float = 0.0
    laps: int = 0
    reason: str = ""
    event_time_s: float = 0.0


class LMUPenaltyLogReader:
    """Le os eventos de punicao gravados pelo LMU sem reler o arquivo."""

    def __init__(self, log_dir: Path | None = None) -> None:
        self.log_dir = log_dir or self._find_log_dir()
        self._trace_path: Path | None = None
        self._trace_offset = 0
        self._result_path: Path | None = None
        self._result_offset = 0
        self._by_driver: dict[str, PenaltyEvent] = {}
        self._anonymous: list[PenaltyEvent] = []
        self._previous_counts: dict[int, int] = {}
        self._session_marker = ""
        self._next_refresh_at = 0.0
        self._next_path_scan_at = 0.0
        self._trace_fragment = ""
        self._result_fragment = ""

    @staticmethod
    def _find_log_dir() -> Path | None:
        configured = os.environ.get("LMU_LOG_DIR", "").strip()
        candidates = [Path(configured)] if configured else []
        for drive in "CDEFG":
            candidates.append(
                Path(
                    f"{drive}:\\SteamLibrary\\steamapps\\common\\"
                    "Le Mans Ultimate\\UserData\\Log"
                )
            )
        candidates.extend(
            [
                Path(
                    "C:\\Program Files (x86)\\Steam\\steamapps\\common\\"
                    "Le Mans Ultimate\\UserData\\Log"
                ),
                Path(
                    "C:\\Program Files\\Steam\\steamapps\\common\\"
                    "Le Mans Ultimate\\UserData\\Log"
                ),
            ]
        )
        return next((path for path in candidates if path.is_dir()), None)

    def enrich(self, session: Any) -> None:
        if self.log_dir is None:
            return
        now = time.monotonic()
        if now < self._next_refresh_at:
            self._apply_events(session, [])
            return
        self._next_refresh_at = now + 0.25
        marker = "|".join(
            (
                str(getattr(session, "track_name", "") or ""),
                str(int(getattr(session, "session", 0) or 0)),
                str(getattr(session, "server_name", "") or ""),
            )
        )
        if self._session_marker and marker != self._session_marker:
            self._by_driver.clear()
            self._anonymous.clear()
            self._previous_counts.clear()
            self._next_path_scan_at = 0.0
        self._session_marker = marker

        # Enumerar todos os traces e XMLs do LMU pode levar 80-100 ms em
        # instalações com muitos resultados. A execução a cada 0,25 s
        # bloqueava toda a interface quatro vezes por segundo. Os arquivos
        # ativos raramente mudam durante uma sessão, portanto só refazemos a
        # descoberta periodicamente; a leitura incremental continua a 4 Hz.
        if now >= self._next_path_scan_at:
            self._refresh_files()
            self._next_path_scan_at = now + 30.0
        self._read_result_updates()
        new_anonymous = self._read_trace_updates()

        self._apply_events(session, new_anonymous)

    def _apply_events(
        self, session: Any, new_anonymous: list[PenaltyEvent]
    ) -> None:
        current_time = float(
            getattr(session, "current_event_time_s", 0.0) or 0.0
        )
        drivers = list(getattr(session, "drivers", []) or [])
        for driver in drivers:
            slot_id = int(getattr(driver, "slot_id", 0) or 0)
            count = max(0, int(getattr(driver, "penalties", 0) or 0))
            previous = self._previous_counts.get(slot_id, 0)
            self._previous_counts[slot_id] = count
            if count <= 0:
                driver.penalty_type = ""
                driver.penalty_time_s = 0.0
                continue
            # O WebSocket LiveStandings publica DT/SG/TIME diretamente.
            if str(getattr(driver, "penalty_type", "") or "").strip():
                continue

            event = self._by_driver.get(
                self._normalize_name(getattr(driver, "driver_name", ""))
            )
            if bool(getattr(driver, "is_player", False)):
                candidates = new_anonymous or self._anonymous[-8:]
                candidates = [
                    item
                    for item in candidates
                    if current_time <= 0.0
                    or item.event_time_s <= 0.0
                    or item.event_time_s <= current_time + 3.0
                ]
                if candidates:
                    newest = max(
                        candidates,
                        key=lambda item: item.event_time_s,
                    )
                    # O XML pode continuar contendo uma punicao antiga ja
                    # cumprida enquanto mNumPenalties permanece em 1 por uma
                    # punicao nova. O codigo numerico do trace nao e usado
                    # como tipo final: ele apenas invalida o XML antigo ate
                    # chegar uma mensagem textual/XML autoritativa.
                    if (
                        event is None
                        or newest.event_time_s > event.event_time_s + 0.001
                    ):
                        event = None
                        driver.penalty_type = ""
                        driver.penalty_time_s = 0.0
            if event is not None:
                driver.penalty_type = event.penalty_type
                driver.penalty_time_s = event.time_s

    def close(self) -> None:
        return

    def _refresh_files(self) -> None:
        trace = self._newest(self.log_dir, "trace_*.txt")
        result = self._newest(self.log_dir / "Results", "*.xml")
        if trace != self._trace_path:
            self._trace_path = trace
            self._trace_offset = 0
            self._anonymous.clear()
            self._trace_fragment = ""
        if result != self._result_path:
            self._result_path = result
            self._result_offset = 0
            self._result_fragment = ""

    @staticmethod
    def _newest(directory: Path, pattern: str) -> Path | None:
        try:
            return max(
                directory.glob(pattern),
                key=lambda path: path.stat().st_mtime_ns,
                default=None,
            )
        except OSError:
            return None

    def _read_result_updates(self) -> None:
        text, self._result_offset = self._read_new_text(
            self._result_path, self._result_offset
        )
        text = self._result_fragment + text
        split = text.rfind(">") + 1
        self._result_fragment = text[split:]
        text = text[:split]
        for match in _XML_PENALTY.finditer(text):
            attrs = {
                key.casefold(): html.unescape(value)
                for key, value in _XML_ATTRIBUTE.findall(match.group(1))
            }
            driver = attrs.get("driver", "").strip()
            penalty_type = attrs.get("penalty", "").strip()
            if not driver or not penalty_type:
                continue
            event = PenaltyEvent(
                driver_name=driver,
                penalty_type=penalty_type,
                time_s=self._float(attrs.get("time")),
                laps=int(self._float(attrs.get("laps"))),
                reason=attrs.get("reason", "").strip(),
                event_time_s=self._float(attrs.get("et")),
            )
            self._by_driver[self._normalize_name(driver)] = event

    def _read_trace_updates(self) -> list[PenaltyEvent]:
        text, self._trace_offset = self._read_new_text(
            self._trace_path, self._trace_offset
        )
        text = self._trace_fragment + text
        lines = text.splitlines(keepends=True)
        if lines and not lines[-1].endswith(("\n", "\r")):
            self._trace_fragment = lines.pop()
        else:
            self._trace_fragment = ""
        added: list[PenaltyEvent] = []
        for line in lines:
            explicit = _TRACE_MESSAGE.search(line)
            if explicit:
                event = PenaltyEvent(
                    driver_name=explicit.group(1).strip(),
                    penalty_type=explicit.group(2).strip(),
                    time_s=self._float(explicit.group(3)),
                    laps=int(explicit.group(4)),
                )
                self._by_driver[
                    self._normalize_name(event.driver_name)
                ] = event
                continue
            raw = _LOCAL_PENALTY.search(line)
            if raw is None:
                continue
            code = int(raw.group(2))
            penalty_type = _TRACE_TYPES.get(code, "")
            if not penalty_type:
                continue
            event = PenaltyEvent(
                penalty_type=penalty_type,
                time_s=self._float(raw.group(3)),
                laps=int(raw.group(4)),
                reason=raw.group(6).strip(),
                event_time_s=self._float(raw.group(1)),
            )
            self._anonymous.append(event)
            added.append(event)
        if len(self._anonymous) > 64:
            del self._anonymous[:-64]
        return added

    @staticmethod
    def _read_new_text(path: Path | None, offset: int) -> tuple[str, int]:
        if path is None:
            return "", offset
        try:
            size = path.stat().st_size
            if size < offset:
                offset = 0
            with path.open("rb") as stream:
                stream.seek(offset)
                raw = stream.read()
                return raw.decode("utf-8", errors="replace"), stream.tell()
        except OSError:
            return "", offset

    @staticmethod
    def _normalize_name(value: Any) -> str:
        text = re.sub(r"#\d+$", "", str(value or "").strip())
        return " ".join(text.casefold().split())

    @staticmethod
    def _float(value: Any) -> float:
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0
