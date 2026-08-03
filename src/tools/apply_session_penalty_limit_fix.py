from __future__ import annotations

import json
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def backup(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")
    backup_path = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, backup_path)
    print(f"Backup: {backup_path}")


def patch_delta_widget() -> None:
    path = PROJECT_ROOT / "src" / "widget" / "delta" / "delta_widget.py"
    backup(path)
    source = path.read_text(encoding="utf-8")

    source = source.replace(
        'Fallback: usa o limite configurado para manter o formato 0/5 em\n'
        '        versões antigas do adapter.',
        'O denominador vem exclusivamente dos dados da sessão do LMU.\n'
        '        Quando a API não fornece o limite, nenhum valor inventado é usado.',
        1,
    )

    old = (
        '        fallback_limit = max(\n'
        '            0.0,\n'
        '            float(\n'
        '                self.config.get(\n'
        '                    "penalty_limit_fallback",\n'
        '                    5.0,\n'
        '                )\n'
        '            ),\n'
        '        )\n'
    )
    new = (
        '        # Não inventa um limite fixo. O valor deve vir da sessão.\n'
        '        fallback_limit = 0.0\n'
    )

    if old not in source:
        raise RuntimeError("Trecho fallback_limit não encontrado em delta_widget.py")

    path.write_text(source.replace(old, new, 1), encoding="utf-8")
    print(f"Atualizado: {path}")


def patch_renderer() -> None:
    path = PROJECT_ROOT / "src" / "widget" / "delta" / "delta_renderer.py"
    backup(path)
    source = path.read_text(encoding="utf-8")

    old = (
        '            else:\n'
        '                label = f"PEN  {data.penalties}"\n'
        '                color = warning if data.penalties > 0 else muted\n'
    )
    new = (
        '            else:\n'
        '                label = f"PEN  {self._format_counter(current)}/?"\n'
        '                color = warning if current > 0 else muted\n'
    )

    if old not in source:
        raise RuntimeError("Trecho de punição não encontrado em delta_renderer.py")

    path.write_text(source.replace(old, new, 1), encoding="utf-8")
    print(f"Atualizado: {path}")


def patch_editor() -> None:
    path = PROJECT_ROOT / "src" / "widget" / "delta" / "delta_editor.py"
    backup(path)
    source = path.read_text(encoding="utf-8")

    source = source.replace(
        '"penalty_limit_fallback",\n                    5.0,',
        '"penalty_limit_fallback",\n                    0.0,',
        1,
    )
    source = source.replace(
        '"Limite reserva (API antiga):",',
        '"Reserva (0 = somente sessão):",',
        1,
    )

    path.write_text(source, encoding="utf-8")
    print(f"Atualizado: {path}")


def patch_json(path: Path) -> None:
    backup(path)
    data = json.loads(path.read_text(encoding="utf-8"))

    if path.name == "widgets.json":
        data.setdefault("widgets", {}).setdefault("delta", {})[
            "penalty_limit_fallback"
        ] = 0.0
        data.setdefault("defaults", {}).setdefault("delta", {})[
            "penalty_limit_fallback"
        ] = 0.0
        data["version"] = max(int(data.get("version", 1)), 10)
    else:
        data["penalty_limit_fallback"] = 0.0

    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Atualizado: {path}")


def main() -> None:
    patch_delta_widget()
    patch_renderer()
    patch_editor()
    patch_json(PROJECT_ROOT / "src" / "config" / "delta_v2_defaults.json")
    patch_json(PROJECT_ROOT / "src" / "config" / "widgets.json")

    print()
    print("Correção concluída.")
    print("O denominador agora vem da sessão:")
    print("mTrackLimitsStepsPerPenalty / mTrackLimitsStepsPerPoint")
    print()
    print("Exemplos: PEN 0/3, PEN 0/50, PEN 0/100")
    print("Sem dados válidos: PEN 0/?")
    print()
    print(r"Teste: python .\src\tools\diagnose_session_penalty_limit.py")


if __name__ == "__main__":
    main()
