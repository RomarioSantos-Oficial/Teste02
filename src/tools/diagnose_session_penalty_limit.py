from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.telemetry.lmu_adapter import LMUAdapter


def main() -> None:
    adapter = LMUAdapter(copy_access=True)

    try:
        session = adapter.read()

        if not session.connected:
            print(f"LMU não conectado: {session.error}")
            return

        player = session.player

        print("Sessão atual")
        print("============")
        print(f"Pista: {session.track_name}")
        print(f"Código da sessão: {session.session}")
        print()
        print("Valores brutos")
        print("==============")
        print("mTrackLimitsStepsPerPenalty:", session.track_limits_steps_per_penalty)
        print("mTrackLimitsStepsPerPoint:", session.track_limits_steps_per_point)
        print(
            "mTrackLimitsSteps do jogador:",
            player.track_limits_steps if player else 0,
        )
        print()
        print("Valores calculados")
        print("==================")
        print("Pontos atuais:", session.track_limits_current)
        print("Limite desta sessão:", session.track_limits_limit)

        if session.track_limits_limit > 0:
            print(
                "Exibição esperada:",
                f"PEN {session.track_limits_current:g}/{session.track_limits_limit:g}",
            )
        else:
            print("Exibição esperada: PEN 0/?")

    finally:
        adapter.close()


if __name__ == "__main__":
    main()
