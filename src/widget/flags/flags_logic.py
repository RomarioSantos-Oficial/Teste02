from __future__ import annotations

import time
from typing import Any

from .flags_models import FlagAlert, FlagCar, FlagsSnapshot


class FlagsLogic:
    """
    Fluxo preservado da referência:

    IDENTIFICA
    → FILTRA BOX/GARAGEM/LATERAL
    → USA POSIÇÃO ROTACIONADA
    → CALCULA DISTÂNCIA/TEMPO
    → RENDERIZA
    """

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

        snapshot = FlagsSnapshot(
            yellow=(
                self.get_yellow_flag_car_info(session)
                if bool(
                    self.config.get(
                        "show_yellow_flag",
                        True,
                    )
                )
                else FlagAlert()
            ),
            blue=(
                self.get_blue_flag_car_info(session)
                if bool(
                    self.config.get(
                        "show_blue_flag",
                        True,
                    )
                )
                else FlagAlert()
            ),
            green_active=self._update_green(
                session,
                now,
            ),
        )

        self._last_game_phase = self._int(
            session,
            "game_phase",
        )
        return snapshot

    def get_yellow_flag_car_info(
        self,
        session: Any,
    ) -> FlagAlert:
        player = self._player_row(session)

        # Igual à referência: não mostra quando o jogador está no box.
        if player is None or self._in_paddock(player):
            return FlagAlert()

        player_speed_kmh = max(
            0.0,
            self._float(player, "speed_kmh"),
        )
        player_speed_ms = max(
            5.0,
            player_speed_kmh / 3.6,
        )

        limite_metros_frente = min(
            max(
                50.0,
                float(
                    self.config.get(
                        "yellow_max_ahead_m",
                        900.0,
                    )
                ),
            ),
            player_speed_ms
            * max(
                1.0,
                float(
                    self.config.get(
                        "yellow_lookahead_seconds",
                        10.0,
                    )
                ),
            ),
        )
        limite_metros_tras = min(
            max(
                0.0,
                float(
                    self.config.get(
                        "yellow_max_behind_m",
                        100.0,
                    )
                ),
            ),
            player_speed_ms * 2.0,
        )

        # A referência usa 4.2 m/s. No modelo atual o valor está em km/h.
        slow_limit_kmh = max(
            1.0,
            float(
                self.config.get(
                    "yellow_hazard_speed_kmh",
                    15.12,
                )
            ),
        )
        session_active = self._int(
            session,
            "game_phase",
        ) != 4

        player_is_hazard = (
            player_speed_kmh < 3.6
            or self._int(player, "flag") == 2
            or self._bool(player, "under_yellow")
        )

        yellow_cars: list[FlagCar] = []

        for row in self._drivers(session)[:64]:
            if self._bool(row, "is_player"):
                continue

            raw_pos_x = self._float(
                row,
                "relative_rotated_x_m",
            )
            raw_pos_y = self._float(
                row,
                "relative_rotated_y_m",
            )

            # Mesmos filtros do arquivo enviado.
            if (
                self._in_paddock(row)
                or abs(raw_pos_x) > 22.0
            ):
                continue

            is_yellow_condition = (
                self._int(row, "flag") == 2
                or self._bool(row, "under_yellow")
                or (
                    self._float(row, "speed_kmh")
                    < slow_limit_kmh
                    and session_active
                )
            )

            if not is_yellow_condition:
                continue

            # raw_pos_y negativo = à frente.
            dist_long = -raw_pos_y

            if dist_long >= 0:
                dentro_do_gap = (
                    dist_long <= limite_metros_frente
                )
                tempo_restante = (
                    dist_long / player_speed_ms
                )
            else:
                dentro_do_gap = (
                    abs(dist_long)
                    <= limite_metros_tras
                )
                tempo_restante = (
                    abs(dist_long)
                    / player_speed_ms
                )

            if not dentro_do_gap:
                continue

            yellow_cars.append(
                self._to_flag_car(
                    row,
                    distance=dist_long,
                    tempo_gap=tempo_restante,
                    raw_pos_x=raw_pos_x,
                    raw_pos_y=raw_pos_y,
                    is_blue=False,
                )
            )

        yellow_cars.sort(
            key=lambda item: abs(item.distance)
        )

        if yellow_cars:
            target = yellow_cars[0]

            return FlagAlert(
                active=True,
                driver=target.driver,
                category=target.category,
                position=target.position,
                distance=target.distance,
                tempo_gap=target.tempo_gap,
                cars=yellow_cars,
                player_is_hazard=player_is_hazard,
            )

        # Igual à referência: o próprio jogador pode ser o perigo.
        if player_is_hazard:
            return FlagAlert(
                active=True,
                driver="ALERTA",
                category="LOCAL",
                position=0,
                distance=0.0,
                tempo_gap=0.0,
                cars=[],
                player_is_hazard=True,
            )

        return FlagAlert()

    def get_blue_flag_car_info(
        self,
        session: Any,
    ) -> FlagAlert:
        player = self._player_row(session)

        if player is None or self._in_paddock(player):
            return FlagAlert()

        receiving_blue = (
            self._int(player, "flag") == 6
            or self._int(
                player,
                "individual_phase",
            )
            == 11
        )

        if not receiving_blue:
            return FlagAlert()

        player_position = self._int(
            player,
            "position",
        )
        blue_cars: list[FlagCar] = []

        for row in self._drivers(session)[:32]:
            if self._bool(row, "is_player"):
                continue

            raw_pos_x = self._float(
                row,
                "relative_rotated_x_m",
            )
            raw_pos_y = self._float(
                row,
                "relative_rotated_y_m",
            )

            if (
                self._in_paddock(row)
                or abs(raw_pos_x) > 16.0
            ):
                continue

            distance = -raw_pos_y
            car_position = self._int(
                row,
                "position",
            )

            if (
                -250.0 <= distance < 0.0
                and car_position > 0
                and (
                    player_position <= 0
                    or car_position < player_position
                )
            ):
                blue_cars.append(
                    self._to_flag_car(
                        row,
                        distance=distance,
                        tempo_gap=0.0,
                        raw_pos_x=raw_pos_x,
                        raw_pos_y=raw_pos_y,
                        is_blue=True,
                    )
                )

        blue_cars.sort(
            key=lambda item: abs(item.distance)
        )

        if not blue_cars:
            return FlagAlert()

        target = blue_cars[0]

        return FlagAlert(
            active=True,
            driver=target.driver,
            category=target.category,
            position=target.position,
            distance=target.distance,
            tempo_gap=0.0,
            cars=[target],
        )

    def preview(
        self,
        mode: str = "yellow",
    ) -> FlagsSnapshot:
        yellow = FlagAlert(
            active=True,
            driver="DRUDI",
            category="LMGT3",
            position=1,
            distance=184,
            tempo_gap=3.2,
            cars=[
                FlagCar(
                    slot_id=11,
                    driver="DRUDI",
                    category="LMGT3",
                    position=1,
                    distance=184,
                    tempo_gap=3.2,
                    raw_pos_x=-1.7,
                    raw_pos_y=-80,
                    speed_kmh=12,
                )
            ],
        )
        blue = FlagAlert(
            active=True,
            driver="CONWAY",
            category="HYPER",
            position=2,
            distance=-92,
            cars=[
                FlagCar(
                    slot_id=2,
                    driver="CONWAY",
                    category="HYPER",
                    position=2,
                    distance=-92,
                    raw_pos_x=1.2,
                    raw_pos_y=92,
                    speed_kmh=285,
                    is_blue_context=True,
                )
            ],
        )

        normalized = str(
            mode or "yellow"
        ).lower()

        if normalized == "blue":
            return FlagsSnapshot(blue=blue)

        if normalized == "green":
            return FlagsSnapshot(
                green_active=True
            )

        if normalized == "yellow_blue":
            return FlagsSnapshot(
                yellow=yellow,
                blue=blue,
            )

        if normalized == "clear":
            return FlagsSnapshot()

        return FlagsSnapshot(yellow=yellow)

    def _update_green(
        self,
        session: Any,
        now: float,
    ) -> bool:
        if not bool(
            self.config.get(
                "show_startlights",
                True,
            )
        ):
            return False

        phase = self._int(
            session,
            "game_phase",
        )
        duration = max(
            0.5,
            float(
                self.config.get(
                    "green_flag_duration_seconds",
                    3.0,
                )
            ),
        )

        changed_to_green = (
            self._last_game_phase is not None
            and self._last_game_phase != 5
            and phase == 5
        )
        initial_green = (
            self._last_game_phase is None
            and phase == 5
            and self._float(
                session,
                "current_time_s",
            )
            <= 10.0
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
        driver_name = str(
            getattr(row, "driver_name", "") or ""
        ).strip()
        parts = driver_name.split()
        surname = (
            parts[-1].upper()
            if parts
            else driver_name[:8].upper()
        )

        position = self._int(
            row,
            "position_in_class",
        )

        if position <= 0:
            position = self._int(
                row,
                "position",
            )

        return FlagCar(
            slot_id=self._int(
                row,
                "slot_id",
            ),
            driver=surname[:8],
            category=str(
                getattr(
                    row,
                    "vehicle_class",
                    "",
                )
                or ""
            )[:6].upper(),
            position=position,
            distance=distance,
            tempo_gap=round(
                tempo_gap,
                1,
            ),
            raw_pos_x=raw_pos_x,
            raw_pos_y=raw_pos_y,
            speed_kmh=self._float(
                row,
                "speed_kmh",
            ),
            is_blue_context=is_blue,
        )

    @staticmethod
    def _in_paddock(row: Any) -> bool:
        return (
            bool(
                getattr(
                    row,
                    "in_pits",
                    False,
                )
            )
            or bool(
                getattr(
                    row,
                    "in_garage",
                    False,
                )
            )
            or int(
                getattr(
                    row,
                    "pit_state",
                    0,
                )
                or 0
            )
            > 0
        )

    @staticmethod
    def _drivers(
        session: Any,
    ) -> list[Any]:
        return list(
            getattr(
                session,
                "drivers",
                [],
            )
            or []
        )

    def _player_row(
        self,
        session: Any,
    ) -> Any | None:
        for row in self._drivers(session):
            if self._bool(
                row,
                "is_player",
            ):
                return row

        return None

    @staticmethod
    def _make_session_key(
        session: Any,
    ) -> str:
        return "|".join(
            [
                str(
                    getattr(
                        session,
                        "track_name",
                        "",
                    )
                    or ""
                ),
                str(
                    getattr(
                        session,
                        "session",
                        0,
                    )
                ),
                str(
                    getattr(
                        session,
                        "max_laps",
                        0,
                    )
                ),
            ]
        )

    @staticmethod
    def _int(
        source: Any,
        name: str,
    ) -> int:
        try:
            return int(
                getattr(
                    source,
                    name,
                    0,
                )
                or 0
            )
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _float(
        source: Any,
        name: str,
    ) -> float:
        try:
            return float(
                getattr(
                    source,
                    name,
                    0.0,
                )
                or 0.0
            )
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _bool(
        source: Any,
        name: str,
    ) -> bool:
        return bool(
            getattr(
                source,
                name,
                False,
            )
        )
