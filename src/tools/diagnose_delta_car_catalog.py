from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.widget.delta.delta_logo_manager import DeltaLogoManager


def main() -> None:
    manager = DeltaLogoManager(PROJECT_ROOT, "images/logos")

    tests = [
        ("LMP2", "Equipe sem nome do carro"),
        ("LMP3", "Ligier JS P325"),
        ("LMP3", "Ginetta G61-LT-P325-Evo"),
        ("LMP3", "Duqueine D09"),
        ("LMP3", "ADESS AD25"),
    ]

    for vehicle_class, car in tests:
        result = manager.match(car, vehicle_class=vehicle_class)
        print()
        print(f"Classe: {vehicle_class}")
        print(f"Carro: {car}")
        print(f"Marca: {result.manufacturer}")
        print(f"Logo: {result.path}")


if __name__ == "__main__":
    main()
