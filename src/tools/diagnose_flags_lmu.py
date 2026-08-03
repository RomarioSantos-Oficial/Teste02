from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.telemetry.lmu_adapter import LMUAdapter
from src.widget.flags.flags_logic import FlagsLogic


def main() -> None:
    adapter = LMUAdapter(copy_access=True)
    config = {
        "show_yellow_flag": True,
        "show_blue_flag": True,
        "show_startlights": True,
        "yellow_lookahead_seconds": 10.0,
        "yellow_max_ahead_m": 900.0,
        "yellow_max_behind_m": 100.0,
        "yellow_hazard_speed_kmh": 15.12,
    }
    logic = FlagsLogic(config)

    try:
        session = adapter.read()

        if not session.connected:
            print(
                f"LMU não conectado: "
                f"{session.error}"
            )
            return

        print("SESSÃO")
        print("======")
        print(
            "Pista:",
            session.track_name,
        )
        print(
            "Fase:",
            session.game_phase,
        )
        print(
            "Bandeiras dos setores:",
            session.sector_flags,
        )
        print(
            "Comprimento:",
            session.track_length_m,
        )
        print()

        player = next(
            (
                row
                for row in session.drivers
                if row.is_player
            ),
            None,
        )

        if player is None:
            print("Jogador não encontrado.")
            return

        print("JOGADOR")
        print("=======")
        print(
            "Piloto:",
            player.driver_name,
        )
        print(
            "Posição:",
            player.position,
        )
        print(
            "Velocidade:",
            player.speed_kmh,
        )
        print(
            "Flag:",
            player.flag,
        )
        print(
            "Pit:",
            player.in_pits,
            player.in_garage,
            player.pit_state,
        )
        print(
            "Vetor frontal:",
            (
                player.forward_x,
                player.forward_y,
                player.forward_z,
            ),
        )
        print()

        print("CARROS PRÓXIMOS PELO RADAR")
        print("==========================")

        rows = sorted(
            (
                row
                for row in session.drivers
                if not row.is_player
            ),
            key=lambda row:
            abs(row.relative_rotated_y_m),
        )[:12]

        for row in rows:
            distance = (
                -row.relative_rotated_y_m
            )
            print()
            print(
                f"{row.driver_name} | "
                f"{row.vehicle_class}"
            )
            print(
                "  X lateral:",
                round(
                    row.relative_rotated_x_m,
                    2,
                ),
            )
            print(
                "  Y radar:",
                round(
                    row.relative_rotated_y_m,
                    2,
                ),
            )
            print(
                "  Distância exibida:",
                round(distance, 2),
            )
            print(
                "  Velocidade:",
                round(
                    row.speed_kmh,
                    1,
                ),
            )
            print(
                "  Flag/Yellow:",
                row.flag,
                row.under_yellow,
            )
            print(
                "  Pit:",
                row.in_pits,
                row.in_garage,
                row.pit_state,
            )

        snapshot = logic.update(session)

        print()
        print("RESULTADO FLAGS")
        print("===============")
        print(
            "Amarela ativa:",
            snapshot.yellow.active,
        )
        print(
            "Alvo amarelo:",
            snapshot.yellow.driver,
            snapshot.yellow.distance,
        )
        print(
            "Azul ativa:",
            snapshot.blue.active,
        )
        print(
            "Alvo azul:",
            snapshot.blue.driver,
            snapshot.blue.distance,
        )
        print(
            "Verde ativa:",
            snapshot.green_active,
        )

    finally:
        adapter.close()


if __name__ == "__main__":
    main()
