# SectorFlow is an open-source overlay application for racing simulation.
# Copyright (C) 2022-2026 SectorFlow developers
# Based on the user-provided Standings Hybrid reference.
#
# This file is part of SectorFlow.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.


from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.widget.standings.standings_online import LocalStandingsEnrichment


def main() -> None:
    config_path = PROJECT_ROOT / "src" / "config" / "widgets.json"
    data = json.loads(config_path.read_text(encoding="utf-8"))
    config = data.get("widgets", {}).get("standings", {})
    source = LocalStandingsEnrichment(PROJECT_ROOT, config)
    try:
        metadata, source_text, error = source.fetch_once()
        print("STANDINGS HYBRID CLASSIC V2")
        print("===========================")
        print("Fonte:", source_text)
        print("Jogadores enriquecidos:", len(metadata))
        if error:
            print("Aviso:", error)
        print()
        for item in list(metadata.values())[:30]:
            print(
                f"{item.driver_name} | país={item.country_code or item.nationality or '--'} | "
                f"badge={item.badge or '--'} | marca={item.manufacturer or '--'} | "
                f"energia={item.energy_percent} | dano={item.damage_percent}"
            )
        path = source.save_sanitized()
        print()
        print("Diagnóstico sanitizado salvo em:")
        print(path)
    finally:
        source.stop()


if __name__ == "__main__":
    main()
