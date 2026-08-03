from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.telemetry.lmu_adapter import LMUAdapter
from src.widget.delta.delta_logo_manager import DeltaLogoManager


def print_manager(manager: DeltaLogoManager) -> None:
    info = manager.diagnostics()

    print("Projeto:")
    print(info["project_root"])
    print()
    print("Pasta de logos encontrada:")
    print(info["logo_directory"])
    print()
    print("Arquivos indexados:")

    files = info["indexed_files"]

    if not files:
        print("  NENHUMA IMAGEM ENCONTRADA")
    else:
        for name in files:
            print(f"  - {name}")


def test_text(manager: DeltaLogoManager, values: list[str]) -> None:
    result = manager.match(*values)

    print()
    print("Textos testados:")
    for value in values:
        print(f"  {value!r}")

    print()
    print("Resultado:")
    print(f"  fabricante: {result.manufacturer}")
    print(f"  texto reconhecido: {result.matched_text!r}")
    print(f"  arquivo: {result.path}")


def inspect_lmu(manager: DeltaLogoManager) -> None:
    print()
    print("Lendo carros do LMU...")

    adapter = LMUAdapter(copy_access=True)
    session = adapter.read()

    try:
        if not session.connected:
            print(f"LMU não conectado: {session.error}")
            return

        rows = sorted(
            session.drivers,
            key=lambda row: (
                row.best_lap_s <= 0,
                row.best_lap_s if row.best_lap_s > 0 else 999999,
            ),
        )

        for row in rows:
            result = manager.match(
                row.vehicle_name,
                row.vehicle_filename,
                row.pit_group,
            )

            print()
            print(f"Piloto: {row.driver_name}")
            print(f"  mVehicleName: {row.vehicle_name!r}")
            print(f"  mVehFilename: {row.vehicle_filename!r}")
            print(f"  mPitGroup: {row.pit_group!r}")
            print(f"  classe: {row.vehicle_class!r}")
            print(f"  logo: {result.path}")
            print(f"  fabricante: {result.manufacturer}")

    finally:
        adapter.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--text",
        action="append",
        default=[],
        help="Texto de veículo para testar. Pode repetir.",
    )
    parser.add_argument(
        "--lmu",
        action="store_true",
        help="Ler os textos reais de todos os carros do LMU.",
    )
    args = parser.parse_args()

    manager = DeltaLogoManager(
        PROJECT_ROOT,
        "images/logos",
    )
    print_manager(manager)

    if args.text:
        test_text(manager, args.text)

    if args.lmu:
        inspect_lmu(manager)

    if not args.text and not args.lmu:
        print()
        print("Exemplos:")
        print(
            r'python .\src\tools\diagnose_delta_logos.py '
            r'--text "Aston Martin Vantage AMR LMGT3"'
        )
        print(
            r"python .\src\tools\diagnose_delta_logos.py --lmu"
        )


if __name__ == "__main__":
    main()
