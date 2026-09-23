from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(slots=True)
class RaceLapProjection:
    final_laps: float
    remaining_laps: float
    class_final_laps: float
    global_finish_horizon_s: float | None
    finish_laps: float
    finish_remaining_laps: float
    confirmed_laps_down: int = 0
    reference: str = ""


def _number(source: Any, name: str) -> float:
    try:
        value = float(getattr(source, name, 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return value if math.isfinite(value) else 0.0


def _integer(source: Any, name: str, default: int = 0) -> int:
    try:
        value = getattr(source, name, default)
        return default if value is None or value == "" else int(value)
    except (TypeError, ValueError):
        return default


def _progress(row: Any, track_length_m: float) -> float:
    completed = max(0, _integer(row, "laps"))
    if track_length_m <= 1.0:
        return float(completed)
    fraction = max(
        0.0,
        min(0.999999, _number(row, "lap_distance_m") / track_length_m),
    )
    return completed + fraction


def _lap_fraction(row: Any, track_length_m: float) -> float:
    return _progress(row, track_length_m) - max(0, _integer(row, "laps"))


def _lap_time(row: Any) -> float:
    for name in ("estimated_lap_s", "last_lap_s", "best_lap_s"):
        value = _number(row, name)
        if 3.0 <= value <= 1800.0:
            return value
    return 0.0


def _time_to_line(row: Any, pace_s: float, track_length_m: float) -> float:
    estimated = _number(row, "estimated_lap_s")
    time_into = _number(row, "time_into_lap_s")
    if estimated >= 3.0 and 0.0 <= time_into < estimated:
        return max(0.001, estimated - time_into)
    fraction = _lap_fraction(row, track_length_m)
    return max(0.001, pace_s * (1.0 - fraction))


def _active(rows: Iterable[Any]) -> list[Any]:
    return [
        row
        for row in rows
        if _integer(row, "position", _integer(row, "overall_position")) > 0
        and _integer(row, "finish_status") not in {2, 3}
        and not bool(getattr(row, "in_garage", False))
    ]


def _overall_position(row: Any) -> int:
    value = _integer(row, "overall_position")
    return value if value > 0 else _integer(row, "position", 9999)


def _class_position(row: Any) -> int:
    value = _integer(row, "class_position")
    if value <= 0:
        value = _integer(row, "position_in_class")
    return value if value > 0 else 9999


def _finish_horizon(
    remaining_s: float,
    leader: Any,
    pace_s: float,
    track_length_m: float,
) -> float:
    if _integer(leader, "finish_status") == 1:
        return 0.0
    next_line_s = _time_to_line(leader, pace_s, track_length_m)
    remaining_s = max(0.0, remaining_s)
    if next_line_s > remaining_s + 1e-6:
        return next_line_s
    # Cruzar antes ou exatamente em 0 inicia mais uma volta. A bandeirada
    # geral começa no primeiro cruzamento estritamente posterior ao tempo.
    full_laps = math.floor((remaining_s - next_line_s) / pace_s + 1e-9) + 1
    return next_line_s + full_laps * pace_s


def _crossings_until_checkered(
    row: Any,
    horizon_s: float,
    pace_s: float,
    track_length_m: float,
) -> int:
    if _integer(row, "finish_status") == 1:
        return 0
    next_line_s = _time_to_line(row, pace_s, track_length_m)
    if next_line_s >= horizon_s - 1e-6:
        return 1
    # O carro cruza normalmente antes da bandeirada e termina no primeiro
    # cruzamento que ocorrer em ou depois do líder geral receber a bandeirada.
    return 1 + int(math.ceil((horizon_s - next_line_s) / pace_s - 1e-9))


def _confirmed_class_laps_down(
    target: Any,
    class_leader: Any,
    track_length_m: float,
    target_progress: float | None = None,
) -> int:
    target_behind = _integer(target, "laps_behind_leader", -1)
    leader_behind = _integer(class_leader, "laps_behind_leader", -1)
    if target_behind >= 0 and leader_behind >= 0:
        official = target_behind - leader_behind
        if official > 0:
            return official
        if official == 0:
            return 0
    progress_gap = _progress(class_leader, track_length_m) - (
        _progress(target, track_length_m)
        if target_progress is None
        else target_progress
    )
    return max(0, int(math.floor(progress_gap + 1e-6)))


def project_race_laps(
    session: Any,
    target: Any | None,
    class_rows: Iterable[Any] | None = None,
    *,
    target_completed_laps: int | None = None,
    target_lap_fraction: float | None = None,
) -> RaceLapProjection | None:
    """Projeta a chegada usando uma única bandeirada definida pelo líder geral."""
    if target is None:
        return None

    track_length_m = max(0.0, _number(session, "track_length_m"))
    target_completed = (
        max(0, _integer(target, "laps"))
        if target_completed_laps is None
        else max(0, int(target_completed_laps))
    )
    target_fraction = (
        _lap_fraction(target, track_length_m)
        if target_lap_fraction is None
        else max(0.0, min(0.999999, float(target_lap_fraction)))
    )
    target_progress = target_completed + target_fraction
    rows = _active(list(getattr(session, "drivers", []) or []))
    candidates = _active(list(class_rows or []))
    class_leader = min(candidates, key=_class_position, default=target)
    if class_leader is None:
        return None

    if (
        _integer(target, "finish_status") == 1
        or bool(getattr(session, "race_finished", False))
    ):
        final = float(target_completed)
        return RaceLapProjection(
            final_laps=final,
            remaining_laps=0.0,
            class_final_laps=float(
                max(0, _integer(class_leader, "laps"))
            ),
            global_finish_horizon_s=0.0,
            finish_laps=final,
            finish_remaining_laps=0.0,
            reference="finished",
        )

    laps_down = _confirmed_class_laps_down(
        target,
        class_leader,
        track_length_m,
        target_progress,
    )
    maximum = _integer(session, "max_laps")
    if 0 < maximum <= 500:
        final = max(float(target_completed), float(maximum - laps_down))
        return RaceLapProjection(
            final_laps=final,
            remaining_laps=max(0.0, final - target_progress),
            class_final_laps=float(maximum),
            global_finish_horizon_s=None,
            finish_laps=final,
            finish_remaining_laps=max(0.0, final - target_progress),
            confirmed_laps_down=laps_down,
            reference="fixed_laps",
        )

    overall_leader = min(rows, key=_overall_position, default=None)
    if overall_leader is None:
        return None

    overall_pace = _lap_time(overall_leader)
    class_pace = _lap_time(class_leader)
    if overall_pace < 3.0 or class_pace < 3.0:
        return None

    remaining_s = max(0.0, _number(session, "remaining_time_s"))
    horizon = _finish_horizon(
        remaining_s,
        overall_leader,
        overall_pace,
        track_length_m,
    )
    class_crossings = _crossings_until_checkered(
        class_leader,
        horizon,
        class_pace,
        track_length_m,
    )
    class_finish = float(
        max(0, _integer(class_leader, "laps")) + class_crossings
    )
    # A previsão exibida conserva a fração que a categoria terá percorrido
    # quando o líder geral iniciar a bandeirada. O total efetivamente
    # completado ao cruzar a linha continua separado para combustível.
    class_progress = _progress(class_leader, track_length_m)
    class_final = min(
        class_finish,
        max(class_progress, class_progress + horizon / class_pace),
    )
    final = max(
        target_progress,
        class_final - laps_down,
    )
    finish = max(
        float(target_completed),
        class_finish - laps_down,
    )
    return RaceLapProjection(
        final_laps=final,
        remaining_laps=max(0.0, final - target_progress),
        class_final_laps=class_final,
        global_finish_horizon_s=horizon,
        finish_laps=finish,
        finish_remaining_laps=max(0.0, finish - target_progress),
        confirmed_laps_down=laps_down,
        reference="overall_leader_checkered",
    )
