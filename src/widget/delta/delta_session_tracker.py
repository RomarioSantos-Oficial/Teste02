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
    current_fastest_laps: list[FastestLapData]
    new_announcement: FastestLapData | None


class DeltaSessionTracker:
    def __init__(self, logo_manager: DeltaLogoManager) -> None:
        self.logo_manager = logo_manager
        self._session_key = ""
        self._player_class = ""
        self._scope = "player_class"
        self._fastest_times: dict[str, float] = {}
        self._current_by_class: dict[str, FastestLapData] = {}
        self._observed_session_once = False
        self._last_current_time = 0.0

    def reset(self) -> None:
        self.__init__(self.logo_manager)

    def update(
        self,
        session: Any,
        announce_initial_fastest: bool = False,
        scope: str = "player_class",
    ) -> SessionTrackingResult:
        scope = (
            "all_classes"
            if str(scope).strip().casefold() == "all_classes"
            else "player_class"
        )
        session_key = self._make_session_key(session)
        session_changed = self._session_changed(session_key, session)

        if session_changed:
            self._session_key = session_key
            self._player_class = ""
            self._fastest_times.clear()
            self._current_by_class.clear()
            self._observed_session_once = False

        player_row = self._player_row(session)
        player_class = str(getattr(player_row, "vehicle_class", "") or "")
        player_class_key = self._class_key(player_class)

        if (
            self._scope != scope
            or (
                scope == "player_class"
                and self._player_class
                and player_class_key != self._player_class
            )
        ):
            self._fastest_times.clear()
            self._current_by_class.clear()
            self._observed_session_once = False

        self._scope = scope
        if player_class_key:
            self._player_class = player_class_key

        fastest_by_class = self._find_fastest_by_class(session)
        if scope == "all_classes":
            selected = list(fastest_by_class.items())
        else:
            fastest = fastest_by_class.get(self._player_class)
            selected = [(self._player_class, fastest)] if fastest else []
        selected.sort(
            key=lambda item: item[1].overall_position or 9999
        )
        announcement = None

        for class_key, fastest in selected:
            previous = self._fastest_times.get(class_key, 0.0)
            if previous <= 0:
                if announce_initial_fastest or self._observed_session_once:
                    announcement = announcement or fastest
            elif fastest.lap_time_s < previous - 0.0005:
                announcement = announcement or fastest
            self._fastest_times[class_key] = fastest.lap_time_s
            self._current_by_class[class_key] = fastest

        current_laps = [
            self._current_by_class[class_key]
            for class_key, _ in selected
            if class_key in self._current_by_class
        ]

        self._observed_session_once = True
        self._last_current_time = float(
            getattr(session, "current_time_s", 0.0) or 0.0
        )

        return SessionTrackingResult(
            session_key=self._session_key,
            session_changed=session_changed,
            current_fastest=current_laps[0] if current_laps else None,
            current_fastest_laps=current_laps,
            new_announcement=announcement,
        )

    def _find_fastest_by_class(
        self,
        session: Any,
    ) -> dict[str, FastestLapData]:
        best_rows: dict[str, Any] = {}
        best_times: dict[str, float] = {}
        drivers = list(getattr(session, "drivers", []) or [])

        for row in drivers:
            row_class = str(getattr(row, "vehicle_class", "") or "")
            class_key = self._class_key(row_class)
            lap_time = float(getattr(row, "best_lap_s", 0.0) or 0.0)

            if not class_key or lap_time <= 0:
                continue
            if (
                class_key not in best_times
                or lap_time < best_times[class_key]
            ):
                best_times[class_key] = lap_time
                best_rows[class_key] = row

        result: dict[str, FastestLapData] = {}
        for class_key, best_row in best_rows.items():
            result[class_key] = self._fastest_data(
                session,
                drivers,
                best_row,
                best_times[class_key],
            )
        return result

    def _fastest_data(
        self,
        session: Any,
        drivers: list[Any],
        best_row: Any,
        best_time: float,
    ) -> FastestLapData:
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

        class_position = int(
            getattr(best_row, "position_in_class", 0) or 0
        )
        if class_position <= 0:
            same_class = sorted(
                (
                    row for row in drivers
                    if self._class_key(
                        str(getattr(row, "vehicle_class", "") or "")
                    ) == self._class_key(vehicle_class)
                ),
                key=lambda row: int(getattr(row, "position", 9999) or 9999),
            )
            class_position = next(
                (
                    index
                    for index, row in enumerate(same_class, start=1)
                    if row is best_row
                ),
                0,
            )

        overall_position = int(
            getattr(best_row, "position", 0) or 0
        )
        return FastestLapData(
            driver_name=str(getattr(best_row, "driver_name", "") or ""),
            vehicle_name=vehicle_name,
            vehicle_class=vehicle_class,
            manufacturer=logo.manufacturer,
            logo_path=logo.path,
            lap_time_s=best_time,
            position=class_position,
            class_position=class_position,
            overall_position=overall_position,
        )

    @staticmethod
    def _class_key(value: str) -> str:
        return "".join(
            character
            for character in str(value or "").casefold()
            if character.isalnum()
        )

    def _session_changed(self, session_key: str, session: Any) -> bool:
        if not self._session_key or session_key != self._session_key:
            return True

        current_time = float(
            getattr(session, "current_time_s", 0.0) or 0.0
        )

        # O LMU pode iniciar outra sessão com a mesma pista, mesmo tipo e
        # mesmo limite de voltas. Nesse caso a chave textual não muda, mas o
        # relógio da sessão volta ao início. Uma tolerância pequena evita
        # reagir a oscilações de leitura sem deixar recordes atravessarem para
        # a sessão seguinte.
        return (
            self._last_current_time > 2.0
            and current_time + 2.0 < self._last_current_time
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
