from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.autonomous.driver import ObserveDriver
from src.autonomous.recorder import TelemetryRecorder
from src.autonomous.route import RecordedRouteRepository
from src.autonomous.state import build_unified_state
from src.telemetry.lmu_adapter import LMUAdapter


def main() -> None:
    config_path = PROJECT_ROOT / "src" / "config" / "autonomous_driver.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        config = {}
    parser = argparse.ArgumentParser(description="Registra telemetria LMU em modo OBSERVE.")
    parser.add_argument("--output", default=config.get("recording_path", "data/autonomous/observe.jsonl"))
    parser.add_argument("--hz", type=float, default=config.get("update_hz", 20.0))
    parser.add_argument("--no-record", action="store_true", default=not config.get("recording_enabled", True))
    args = parser.parse_args()
    hz = min(60.0, max(1.0, args.hz))

    adapter = LMUAdapter(copy_access=True)
    recorder = None if args.no_record else TelemetryRecorder(PROJECT_ROOT / args.output)
    route_repository = RecordedRouteRepository(PROJECT_ROOT / "data" / "track_maps")
    driver = ObserveDriver(route_repository)
    print("SectorFlow Pilot | OBSERVE | nenhum comando será enviado ao jogo")
    try:
        while True:
            started = time.monotonic()
            session = adapter.read()
            state = build_unified_state(session, time.time())
            decision = driver.decide(state)
            if recorder is not None and state.connected:
                recorder.append(state, decision)
            if state.vehicle:
                print(
                    f"\r{state.track_name[:20]:20} | {state.vehicle.speed_km_h:6.1f} km/h "
                    f"| gear {state.vehicle.gear:2d} | traffic {len(state.traffic):2d} "
                    f"| rota {'sim' if decision.route_preview else 'n/a':3} "
                    f"| rota-status {(decision.route_assessment or {}).get('status', 'n/a'):18} "
                    f"| {decision.status:7}",
                    end="",
                    flush=True,
                )
            else:
                print(f"\r{decision.reason:<85}", end="", flush=True)
            time.sleep(max(0.0, 1.0 / hz - (time.monotonic() - started)))
    except KeyboardInterrupt:
        print("\nObservação encerrada.")
    finally:
        adapter.close()


if __name__ == "__main__":
    main()
