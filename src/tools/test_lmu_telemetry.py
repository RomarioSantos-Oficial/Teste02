from __future__ import annotations
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from src.telemetry.lmu_adapter import LMUAdapter

print("=" * 90)
print("SECTOR FLOW DRIVE - TESTE DE TELEMETRIA LMU")
print("=" * 90)
print("Abra o LMU, entre em uma sessao e coloque o carro na pista.")
print("CTRL+C encerra.\n")

adapter = LMUAdapter(copy_access=True)
try:
    while True:
        session = adapter.read()
        if not session.connected:
            print(f"\r[AGUARDANDO] {session.error:<65}", end="", flush=True)
            time.sleep(0.5)
            continue
        player = session.player
        if player is None:
            print("\r[LMU OK] Aguardando veiculo do jogador...", end="", flush=True)
            time.sleep(0.25)
            continue
        print(
            "\r"
            f"LMU OK | {session.track_name[:20]:20} | "
            f"Carros {len(session.drivers):3d} | "
            f"Vel {player.speed_kmh:7.2f} km/h | "
            f"RPM {player.rpm:7.0f} | "
            f"G {player.gear:2d} | "
            f"THR {player.throttle*100:5.1f}% | "
            f"BRK {player.brake*100:5.1f}% | "
            f"Fuel {player.fuel_liters:6.2f} L",
            end="", flush=True,
        )
        time.sleep(0.05)
except KeyboardInterrupt:
    print("\nTeste encerrado.")
finally:
    adapter.close()
