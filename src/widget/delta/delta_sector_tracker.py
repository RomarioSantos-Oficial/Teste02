from __future__ import annotations

from typing import Any

from .delta_models import (
    DeltaSectorData,
    SECTOR_BETTER,
    SECTOR_NEUTRAL,
    SECTOR_SESSION_BEST,
    SECTOR_WORSE,
)


class DeltaSectorTracker:
    """
    Classifica os setores do jogador:

    - roxo: melhor setor de todos na categoria;
    - verde: melhor setor pessoal;
    - amarelo: setor pior que o melhor pessoal;
    - neutro: ainda não existe tempo válido.

    O tracker usa os tempos independentes de S1/S2/S3 expostos pelo
    LMUAdapter atualizado.
    """

    def __init__(self, tolerance_s: float = 0.001) -> None:
        self.tolerance_s = max(0.0001, float(tolerance_s))
        self._session_key = ""
        self._last_values: list[float | None] = [None, None, None]
        self._display: list[DeltaSectorData] = self._empty()

    def reset(self) -> None:
        self._session_key = ""
        self._last_values = [None, None, None]
        self._display = self._empty()

    def update(self, session: Any, session_key: str) -> list[DeltaSectorData]:
        if session_key != self._session_key:
            self._session_key = session_key
            self._last_values = [None, None, None]
            self._display = self._empty()

        player_row = self._player_row(session)
        if player_row is None:
            return self._copy_display()

        latest = [
            self._positive(getattr(player_row, "last_sector1_s", 0.0)),
            self._positive(getattr(player_row, "last_sector2_s", 0.0)),
            self._positive(getattr(player_row, "last_sector3_s", 0.0)),
        ]
        personal_best = [
            self._positive(getattr(player_row, "best_sector1_s", 0.0)),
            self._positive(getattr(player_row, "best_sector2_s", 0.0)),
            self._positive(getattr(player_row, "best_sector3_s", 0.0)),
        ]
        session_best = self._session_best_sectors(
            session,
            str(getattr(player_row, "vehicle_class", "") or ""),
        )

        # Permite que um core futuro envie status/deltas prontos.
        player = getattr(session, "player", None)
        provided_deltas = getattr(player, "sector_deltas", None)
        provided_statuses = getattr(player, "sector_statuses", None)

        for index in range(3):
            current = latest[index]

            if isinstance(provided_deltas, (list, tuple)) and index < len(provided_deltas):
                try:
                    provided_delta = provided_deltas[index]
                    if provided_delta is not None:
                        self._display[index].delta_s = float(provided_delta)
                except (TypeError, ValueError):
                    pass

            if isinstance(provided_statuses, (list, tuple)) and index < len(provided_statuses):
                normalized = self._normalize_status(provided_statuses[index])
                if normalized != SECTOR_NEUTRAL:
                    self._display[index].status = normalized

            if current is None:
                continue

            previous = self._last_values[index]
            changed = previous is None or abs(current - previous) > self.tolerance_s

            if not changed:
                continue

            self._last_values[index] = current
            personal = personal_best[index]
            category_best = session_best[index]

            status = SECTOR_WORSE
            if (
                category_best is not None
                and current <= category_best + self.tolerance_s
            ):
                status = SECTOR_SESSION_BEST
            elif (
                personal is not None
                and current <= personal + self.tolerance_s
            ):
                status = SECTOR_BETTER

            delta_s = None
            if personal is not None:
                delta_s = current - personal

            self._display[index] = DeltaSectorData(
                label=f"S{index + 1}",
                delta_s=delta_s,
                time_s=current,
                status=status,
            )

        return self._copy_display()

    @staticmethod
    def _player_row(session: Any) -> Any | None:
        for row in getattr(session, "drivers", []) or []:
            if bool(getattr(row, "is_player", False)):
                return row
        return None

    def _session_best_sectors(
        self,
        session: Any,
        player_class: str,
    ) -> list[float | None]:
        best: list[float | None] = [None, None, None]

        for row in getattr(session, "drivers", []) or []:
            row_class = str(getattr(row, "vehicle_class", "") or "")

            if player_class and row_class != player_class:
                continue

            values = [
                self._positive(getattr(row, "best_sector1_s", 0.0)),
                self._positive(getattr(row, "best_sector2_s", 0.0)),
                self._positive(getattr(row, "best_sector3_s", 0.0)),
            ]

            for index, value in enumerate(values):
                if value is None:
                    continue

                if best[index] is None or value < best[index]:
                    best[index] = value

        return best

    @staticmethod
    def _positive(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None

        return number if number > 0 else None

    @staticmethod
    def _normalize_status(value: Any) -> str:
        normalized = str(value or "").strip().lower()

        aliases = {
            "purple": SECTOR_SESSION_BEST,
            "overall_best": SECTOR_SESSION_BEST,
            "session_best": SECTOR_SESSION_BEST,
            "best_of_all": SECTOR_SESSION_BEST,
            "green": SECTOR_BETTER,
            "personal_best": SECTOR_BETTER,
            "better": SECTOR_BETTER,
            "yellow": SECTOR_WORSE,
            "worse": SECTOR_WORSE,
        }

        return aliases.get(normalized, SECTOR_NEUTRAL)

    @staticmethod
    def _empty() -> list[DeltaSectorData]:
        return [
            DeltaSectorData("S1"),
            DeltaSectorData("S2"),
            DeltaSectorData("S3"),
        ]

    def _copy_display(self) -> list[DeltaSectorData]:
        return [
            DeltaSectorData(
                label=item.label,
                delta_s=item.delta_s,
                time_s=item.time_s,
                status=item.status,
            )
            for item in self._display
        ]
