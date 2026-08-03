from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .delta_logo_manager import DeltaLogoManager
from .delta_models import FastestLapData


@dataclass(slots=True)
class SessionTrackingResult:
    session_key: str
    session_changed: bool
    current_fastest: FastestLapData | None
    new_announcement: FastestLapData | None


class DeltaSessionTracker:
    def __init__(self, logo_manager: DeltaLogoManager) -> None:
        self.logo_manager = logo_manager
        self._session_key = ""
        self._player_class = ""
        self._fastest_time = 0.0
        self._current_fastest: FastestLapData | None = None
        self._observed_session_once = False
        self._last_current_time = 0.0

    def reset(self) -> None:
        self.__init__(self.logo_manager)

    def update(
        self,
        session: Any,
        announce_initial_fastest: bool = False,
    ) -> SessionTrackingResult:
        session_key = self._make_session_key(session)
        session_changed = self._session_changed(session_key, session)

        if session_changed:
            self._session_key = session_key
            self._player_class = ""
            self._fastest_time = 0.0
            self._current_fastest = None
            self._observed_session_once = False

        player_row = self._player_row(session)
        player_class = str(getattr(player_row, "vehicle_class", "") or "")

        if self._player_class and player_class != self._player_class:
            self._fastest_time = 0.0
            self._current_fastest = None
            self._observed_session_once = False

        if player_class:
            self._player_class = player_class

        fastest = self._find_fastest(session, self._player_class)
        announcement = None

        if fastest is not None:
            if self._fastest_time <= 0:
                self._fastest_time = fastest.lap_time_s
                self._current_fastest = fastest
                if announce_initial_fastest or self._observed_session_once:
                    announcement = fastest
            elif fastest.lap_time_s < self._fastest_time - 0.0005:
                self._fastest_time = fastest.lap_time_s
                self._current_fastest = fastest
                announcement = fastest
            else:
                self._current_fastest = fastest

        self._observed_session_once = True
        self._last_current_time = float(
            getattr(session, "current_time_s", 0.0) or 0.0
        )

        return SessionTrackingResult(
            session_key=self._session_key,
            session_changed=session_changed,
            current_fastest=self._current_fastest,
            new_announcement=announcement,
        )

    def _find_fastest(
        self,
        session: Any,
        player_class: str,
    ) -> FastestLapData | None:
        best_row = None
        best_time = 0.0

        for row in getattr(session, "drivers", []) or []:
            row_class = str(getattr(row, "vehicle_class", "") or "")
            lap_time = float(getattr(row, "best_lap_s", 0.0) or 0.0)

            if player_class and row_class != player_class:
                continue
            if lap_time <= 0:
                continue
            if best_time <= 0 or lap_time < best_time:
                best_time = lap_time
                best_row = row

        if best_row is None:
            return None

        vehicle_name = str(getattr(best_row, "vehicle_name", "") or "")
        vehicle_filename = str(
            getattr(best_row, "vehicle_filename", "") or ""
        )
        pit_group = str(getattr(best_row, "pit_group", "") or "")
        vehicle_class = str(
            getattr(best_row, "vehicle_class", "") or ""
        )

        player_model = ""
        if bool(getattr(best_row, "is_player", False)):
            player_model = str(
                getattr(getattr(session, "player", None), "vehicle_model", "")
                or ""
            )

        logo = self.logo_manager.match(
            vehicle_name,
            vehicle_filename,
            pit_group,
            player_model,
            vehicle_class=vehicle_class,
        )

        return FastestLapData(
            driver_name=str(getattr(best_row, "driver_name", "") or ""),
            vehicle_name=vehicle_name,
            vehicle_class=vehicle_class,
            manufacturer=logo.manufacturer,
            logo_path=logo.path,
            lap_time_s=best_time,
            position=int(getattr(best_row, "position", 0) or 0),
        )

    def _session_changed(self, session_key: str, session: Any) -> bool:
        if not self._session_key or session_key != self._session_key:
            return True

        current_time = float(
            getattr(session, "current_time_s", 0.0) or 0.0
        )
        return (
            self._last_current_time > 30
            and current_time + 30 < self._last_current_time
        )

    @staticmethod
    def _make_session_key(session: Any) -> str:
        return "|".join(
            [
                str(getattr(session, "track_name", "") or ""),
                str(getattr(session, "session", 0)),
                str(getattr(session, "max_laps", 0)),
            ]
        )

    @staticmethod
    def _player_row(session: Any) -> Any | None:
        for row in getattr(session, "drivers", []) or []:
            if bool(getattr(row, "is_player", False)):
                return row
        return None
