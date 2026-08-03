from __future__ import annotations

import time
from typing import Any

from .flags_models import FlagAlert, FlagCar, FlagsSnapshot


class FlagsLogic:
    """Transforma a telemetria real do LMU em dados para os widgets visuais."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self._session_key = ""
        self._last_game_phase: int | None = None
        self._green_until = 0.0

    def update_config(self, config: dict[str, Any]) -> None:
        self.config = config

    def reset(self) -> None:
        self._session_key = ""
        self._last_game_phase = None
        self._green_until = 0.0

    def update(self, session: Any) -> FlagsSnapshot:
        now = time.monotonic()
        session_key = self._make_session_key(session)
        if session_key != self._session_key:
            self._session_key = session_key
            self._last_game_phase = None
            self._green_until = 0.0

        # LMU: 1-4 = Practice, 5-8 = Qualifying e 10-13 = Race.
        # Test Day (0), Warmup (9) e estados sem sessão não exibem Flags.
        if not self._session_allows_flags(session):
            self._last_game_phase = self._int(session, "game_phase")
            return FlagsSnapshot()

        snapshot = FlagsSnapshot(
            yellow=(
                self.get_yellow_flag_car_info(session)
                if bool(self.config.get("show_yellow_flag", True))
                else FlagAlert()
            ),
            blue=(
                self.get_blue_flag_car_info(session)
                if bool(self.config.get("show_blue_flag", True))
                else FlagAlert()
            ),
            green_active=self._update_green(session, now),
        )
        self._last_game_phase = self._int(session, "game_phase")
        return snapshot

    def get_yellow_flag_car_info(self, session: Any) -> FlagAlert:
        player = self._player_row(session)
        if player is None or self._in_paddock(player):
            return FlagAlert()

        player_speed = max(0.0, self._float(player, "speed_kmh"))
        player_speed_ms = max(1.0, player_speed / 3.6)
        max_ahead = max(
            50.0,
            float(self.config.get("yellow_max_ahead_m", 900.0)),
        )
        lookahead = max(
            1.0,
            float(self.config.get("yellow_lookahead_seconds", 10.0)),
        )
        ahead_limit = min(max_ahead, player_speed_ms * lookahead)
        behind_limit = max(
            0.0,
            float(self.config.get("yellow_max_behind_m", 100.0)),
        )
        phase = self._int(session, "game_phase")
        yellow_state = self._int(session, "yellow_flag_state")
        full_course_yellow = (
            phase == 6 or yellow_state in {1, 2, 3, 4, 5}
        )
        sector_flags = tuple(getattr(session, "sector_flags", ()) or ())
        # Na memória real do LMU, 1 representa setor sob amarela. Valores
        # como 11 também aparecem durante pista verde e não são amarelas.
        any_sector_yellow = any(int(value or 0) == 1 for value in sector_flags)

        # Só existe alerta amarelo quando o próprio LMU informa uma
        # bandeira local ou Full Course Yellow. Um carro lento sozinho
        # não deve criar uma bandeira.
        if not (full_course_yellow or any_sector_yellow):
            return FlagAlert()

        hazard_speed = max(
            1.0,
            float(self.config.get("yellow_hazard_speed_kmh", 15.12)),
        )
        player_causing_local_yellow = (
            any_sector_yellow
            and player_speed < hazard_speed
        )
        if player_causing_local_yellow:
            player_category = str(
                getattr(player, "vehicle_class", "") or "PERIGO LOCAL"
            ).upper()
            player_position = self._int(player, "position_in_class")
            if player_position <= 0:
                player_position = self._int(player, "position")
            return FlagAlert(
                active=True,
                driver="VOCÊ",
                category=player_category[:12],
                position=player_position,
                distance=0.0,
                tempo_gap=0.0,
                cars=[],
                player_is_hazard=True,
            )

        candidates: list[FlagCar] = []

        for row in self._drivers(session)[:64]:
            if self._bool(row, "is_player") or self._in_paddock(row):
                continue

            distance = self._signed_track_gap(session, player, row)
            if distance >= 0.0:
                if distance > ahead_limit:
                    continue
            elif abs(distance) > behind_limit:
                continue

            row_speed = max(0.0, self._float(row, "speed_kmh"))

            closing_speed_ms = max(1.0, (player_speed - row_speed) / 3.6)
            candidates.append(
                self._to_flag_car(
                    row,
                    distance=distance,
                    tempo_gap=abs(distance) / closing_speed_ms,
                    raw_pos_x=self._relative_lateral(player, row),
                    raw_pos_y=-distance,
                    is_blue=False,
                )
            )

        candidates.sort(key=lambda car: (car.distance < 0.0, abs(car.distance)))
        if not candidates:
            # O LMU informa o setor amarelo, mas não identifica diretamente
            # qual veículo causou o incidente. A bandeira oficial ainda deve
            # ser exibida, sem inventar piloto, categoria ou distância.
            return FlagAlert(
                active=True,
                driver="BANDEIRA AMARELA",
                category="SETOR" if any_sector_yellow else "FCY",
                position=0,
                distance=0.0,
                tempo_gap=0.0,
                cars=[],
            )

        target = candidates[0]
        return FlagAlert(
            active=True,
            driver=target.driver,
            category=target.category,
            position=target.position,
            distance=target.distance,
            tempo_gap=target.tempo_gap,
            cars=candidates,
        )

    def get_blue_flag_car_info(self, session: Any) -> FlagAlert:
        player = self._player_row(session)
        if player is None or self._in_paddock(player):
            return FlagAlert()

        receiving_blue = (
            self._int(player, "flag") == 6
            or self._int(player, "individual_phase") == 11
        )
        if not receiving_blue:
            return FlagAlert()

        player_position = self._int(player, "position")
        candidates: list[FlagCar] = []
        for row in self._drivers(session)[:64]:
            if self._bool(row, "is_player") or self._in_paddock(row):
                continue

            distance = self._signed_track_gap(session, player, row)
            car_position = self._int(row, "position")
            if not (
                -300.0 <= distance < 0.0
                and car_position > 0
                and (player_position <= 0 or car_position < player_position)
            ):
                continue

            candidates.append(
                self._to_flag_car(
                    row,
                    distance=distance,
                    tempo_gap=abs(distance)
                    / max(1.0, self._float(row, "speed_kmh") / 3.6),
                    raw_pos_x=self._relative_lateral(player, row),
                    raw_pos_y=-distance,
                    is_blue=True,
                )
            )

        candidates.sort(key=lambda car: abs(car.distance))
        if not candidates:
            return FlagAlert()

        target = candidates[0]
        return FlagAlert(
            active=True,
            driver=target.driver,
            category=target.category,
            position=target.position,
            distance=target.distance,
            tempo_gap=target.tempo_gap,
            cars=candidates,
        )

    def preview(self, mode: str = "yellow") -> FlagsSnapshot:
        yellow = FlagAlert(
            active=True,
            driver="EXEMPLO",
            category="LMGT3",
            position=1,
            distance=184.0,
            tempo_gap=3.2,
            cars=[
                FlagCar(
                    slot_id=11,
                    driver="EXEMPLO",
                    category="LMGT3",
                    position=1,
                    distance=184.0,
                    tempo_gap=3.2,
                    raw_pos_x=-1.7,
                    raw_pos_y=-80.0,
                    speed_kmh=12.0,
                )
            ],
        )
        blue = FlagAlert(
            active=True,
            driver="EXEMPLO",
            category="HYPER",
            position=2,
            distance=-92.0,
            cars=[
                FlagCar(
                    slot_id=2,
                    driver="EXEMPLO",
                    category="HYPER",
                    position=2,
                    distance=-92.0,
                    raw_pos_x=1.2,
                    raw_pos_y=92.0,
                    speed_kmh=285.0,
                    is_blue_context=True,
                )
            ],
        )
        normalized = str(mode or "yellow").lower()
        if normalized == "blue":
            return FlagsSnapshot(blue=blue)
        if normalized == "green":
            return FlagsSnapshot(green_active=True)
        if normalized == "yellow_blue":
            return FlagsSnapshot(yellow=yellow, blue=blue)
        if normalized == "clear":
            return FlagsSnapshot()
        return FlagsSnapshot(yellow=yellow)

    def _signed_track_gap(self, session: Any, player: Any, row: Any) -> float:
        gap = self._float(row, "lap_distance_m") - self._float(
            player, "lap_distance_m"
        )
        track_length = max(0.0, self._float(session, "track_length_m"))
        if track_length > 100.0:
            half = track_length / 2.0
            gap = (gap + half) % track_length - half
        return gap

    def _relative_lateral(self, player: Any, row: Any) -> float:
        # mPathLateral acompanha o traçado e continua correto nas curvas;
        # projeção em coordenadas mundiais só funciona para carros muito
        # próximos e fazia o radar saltar centenas de metros lateralmente.
        return self._float(row, "path_lateral_m") - self._float(
            player, "path_lateral_m"
        )

    def _sector_is_yellow(self, session: Any, row: Any) -> bool:
        flags = tuple(getattr(session, "sector_flags", ()) or ())
        sector = self._int(row, "current_sector")
        if 0 <= sector < len(flags):
            return int(flags[sector] or 0) == 1
        return any(int(value or 0) == 1 for value in flags)

    def _update_green(self, session: Any, now: float) -> bool:
        if not bool(self.config.get("show_startlights", True)):
            return False
        phase = self._int(session, "game_phase")
        duration = max(
            0.5,
            float(self.config.get("green_flag_duration_seconds", 3.0)),
        )
        changed_to_green = (
            self._last_game_phase is not None
            and self._last_game_phase != 5
            and phase == 5
        )
        initial_green = (
            self._last_game_phase is None
            and phase == 5
            and self._float(session, "current_time_s") <= 10.0
        )
        if changed_to_green or initial_green:
            self._green_until = now + duration
        return now <= self._green_until

    def _to_flag_car(
        self,
        row: Any,
        distance: float,
        tempo_gap: float,
        raw_pos_x: float,
        raw_pos_y: float,
        is_blue: bool,
    ) -> FlagCar:
        driver_name = str(getattr(row, "driver_name", "") or "").strip()
        parts = driver_name.split()
        driver = parts[-1].upper() if parts else "---"
        category = str(getattr(row, "vehicle_class", "") or "").strip()
        if not category:
            category = str(getattr(row, "vehicle_name", "") or "CARRO")
        position = self._int(row, "position_in_class")
        if position <= 0:
            position = self._int(row, "position")
        return FlagCar(
            slot_id=self._int(row, "slot_id"),
            driver=driver[:12],
            category=category[:12].upper(),
            position=position,
            distance=distance,
            tempo_gap=round(tempo_gap, 1),
            raw_pos_x=raw_pos_x,
            raw_pos_y=raw_pos_y,
            speed_kmh=self._float(row, "speed_kmh"),
            is_blue_context=is_blue,
        )

    @staticmethod
    def _in_paddock(row: Any) -> bool:
        return (
            bool(getattr(row, "in_pits", False))
            or bool(getattr(row, "in_garage", False))
            or int(getattr(row, "pit_state", 0) or 0) > 0
        )

    @staticmethod
    def _drivers(session: Any) -> list[Any]:
        return list(getattr(session, "drivers", []) or [])

    def _player_row(self, session: Any) -> Any | None:
        return next(
            (row for row in self._drivers(session) if self._bool(row, "is_player")),
            None,
        )

    def _session_allows_flags(self, session: Any) -> bool:
        session_type = self._int(session, "session")
        return 1 <= session_type <= 8 or 10 <= session_type <= 13

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
    def _int(source: Any, name: str) -> int:
        try:
            return int(getattr(source, name, 0) or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _float(source: Any, name: str) -> float:
        try:
            return float(getattr(source, name, 0.0) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _bool(source: Any, name: str) -> bool:
        return bool(getattr(source, name, False))
