from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.widget.standings.lmu_online_client import LMUOnlineIdentityClient


def main() -> None:
    config_path = PROJECT_ROOT / "src/config/widgets.json"
    data = json.loads(config_path.read_text(encoding="utf-8"))
    config = data.get("widgets", {}).get("standings", {})
    client = LMUOnlineIdentityClient(PROJECT_ROOT, config)

    print("DIAGNÓSTICO STANDINGS ONLINE")
    print("============================")
    print("Abra o LMU e entre em uma sessão online.")
    print()
    snapshot = client.refresh_sync()
    print("REST local:", snapshot.local_api_available)
    print("Sessão online detectada:", snapshot.session_online)
    print("Event ID detectado:", bool(snapshot.event_id))
    print("Perfis online DR/SR:", snapshot.cloud_available)
    print("Identidades encontradas:", len(snapshot.identities))
    print("Fonte:", snapshot.source_message)
    if snapshot.error:
        print("Aviso:", snapshot.error)
    print()
    print("AMOSTRA")
    print("-------")
    for identity in snapshot.identities[:20]:
        print(
            f"{identity.display_name or identity.username} | "
            f"DR={identity.driver_rank or '--'} | "
            f"DR%={identity.driver_rank_progress} | "
            f"SR={identity.safety_rank or '--'} | "
            f"PAÍS={identity.nationality or '--'} | "
            f"BADGE={identity.badge or '--'}"
        )

    destination = (
        PROJECT_ROOT
        / "data"
        / "online_profiles"
        / "standings_online_sanitized.json"
    )
    client.export_sanitized_snapshot(destination)
    print()
    print("Diagnóstico sanitizado salvo em:")
    print(destination)
    print("Nenhum ticket ou token é salvo nesse arquivo.")


if __name__ == "__main__":
    main()
