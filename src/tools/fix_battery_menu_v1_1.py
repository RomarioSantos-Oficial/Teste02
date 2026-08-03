from __future__ import annotations

import json
import py_compile
import re
import shutil
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAIN_MENU = PROJECT_ROOT / "src" / "ui" / "main_menu_window.py"
WIDGETS_CONFIG = PROJECT_ROOT / "src" / "config" / "widgets.json"
BATTERY_DEFAULTS = PROJECT_ROOT / "src" / "config" / "battery_defaults.json"


def backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = path.with_name(
        f"{path.name}.battery_menu_{stamp}.bak"
    )
    shutil.copy2(path, target)
    return target


def deep_merge(
    base: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    result = deepcopy(base)

    for key, value in override.items():
        if (
            isinstance(value, dict)
            and isinstance(result.get(key), dict)
        ):
            result[key] = deep_merge(
                result[key],
                value,
            )
        else:
            result[key] = deepcopy(value)

    return result


def patch_main_menu() -> None:
    if not MAIN_MENU.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {MAIN_MENU}"
        )

    source = MAIN_MENU.read_text(encoding="utf-8")
    original = source

    import_line = (
        "from src.widget.battery.battery_editor "
        "import BatteryEditor\n"
    )

    if import_line not in source:
        lines = source.splitlines(keepends=True)

        editor_import_indexes = [
            index
            for index, line in enumerate(lines)
            if (
                line.startswith("from src.widget.")
                and "_editor import" in line
            )
        ]

        if editor_import_indexes:
            insert_at = editor_import_indexes[-1] + 1
        else:
            # Fallback: insere antes da classe principal.
            class_indexes = [
                index
                for index, line in enumerate(lines)
                if line.startswith("class MainMenuWindow")
            ]

            if not class_indexes:
                raise RuntimeError(
                    "Não encontrei onde inserir o import "
                    "BatteryEditor em main_menu_window.py."
                )

            insert_at = class_indexes[0]

        lines.insert(insert_at, import_line)
        source = "".join(lines)

    if 'widget_id == "battery"' not in source:
        lines = source.splitlines(keepends=True)

        method_start = next(
            (
                index
                for index, line in enumerate(lines)
                if re.match(
                    r"^    def _open_editor\s*\(",
                    line,
                )
            ),
            None,
        )

        if method_start is None:
            raise RuntimeError(
                "Não encontrei o método _open_editor "
                "em main_menu_window.py."
            )

        method_end = len(lines)

        for index in range(
            method_start + 1,
            len(lines),
        ):
            if re.match(
                r"^    def \w+\s*\(",
                lines[index],
            ):
                method_end = index
                break

        else_indexes = [
            index
            for index in range(
                method_start + 1,
                method_end,
            )
            if re.match(
                r"^        else:\s*$",
                lines[index].rstrip("\r\n"),
            )
        ]

        if not else_indexes:
            raise RuntimeError(
                "Encontrei _open_editor, mas não encontrei "
                "o else final onde o editor Battery deve entrar."
            )

        insert_at = else_indexes[-1]
        branch = [
            '        elif widget_id == "battery":\n',
            "            editor = BatteryEditor(\n",
            "                deepcopy(\n",
            '                    self.overlay_manager.config_data["widgets"][widget_id]\n',
            "                ),\n",
            "                self,\n",
            "            )\n",
        ]
        lines[insert_at:insert_at] = branch
        source = "".join(lines)

    if source != original:
        backup_path = backup(MAIN_MENU)
        MAIN_MENU.write_text(
            source,
            encoding="utf-8",
        )
        print(f"Backup criado: {backup_path}")
        print(f"Menu corrigido: {MAIN_MENU}")
    else:
        print("O editor Battery já estava integrado ao menu.")

    py_compile.compile(
        str(MAIN_MENU),
        doraise=True,
    )


def merge_battery_config() -> None:
    if not BATTERY_DEFAULTS.exists():
        raise FileNotFoundError(
            "battery_defaults.json não encontrado. "
            "Extraia primeiro o pacote Battery Hybrid V1 "
            "na raiz do projeto."
        )

    if not WIDGETS_CONFIG.exists():
        raise FileNotFoundError(
            f"Configuração não encontrada: {WIDGETS_CONFIG}"
        )

    data = json.loads(
        WIDGETS_CONFIG.read_text(
            encoding="utf-8",
        )
    )
    defaults = json.loads(
        BATTERY_DEFAULTS.read_text(
            encoding="utf-8",
        )
    )

    current = (
        data
        .setdefault("widgets", {})
        .get("battery", {})
    )

    # Preserva ajustes já existentes e preenche apenas o que falta.
    merged = deep_merge(
        defaults,
        current,
    )
    data["widgets"]["battery"] = merged
    data.setdefault(
        "defaults",
        {},
    )["battery"] = deepcopy(defaults)
    data["version"] = max(
        int(data.get("version", 1)),
        19,
    )

    backup_path = backup(WIDGETS_CONFIG)
    WIDGETS_CONFIG.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Backup criado: {backup_path}")
    print(f"Config Battery integrada: {WIDGETS_CONFIG}")


def verify_integration() -> None:
    required = [
        PROJECT_ROOT / "src" / "telemetry" / "models.py",
        PROJECT_ROOT / "src" / "telemetry" / "lmu_adapter.py",
        PROJECT_ROOT / "src" / "ui" / "widget_registry.py",
        PROJECT_ROOT / "src" / "ui" / "overlay_manager.py",
        PROJECT_ROOT / "src" / "ui" / "main_menu_window.py",
        PROJECT_ROOT / "src" / "widget" / "battery" / "battery_models.py",
        PROJECT_ROOT / "src" / "widget" / "battery" / "battery_tracker.py",
        PROJECT_ROOT / "src" / "widget" / "battery" / "battery_widget.py",
        PROJECT_ROOT / "src" / "widget" / "battery" / "battery_editor.py",
    ]

    missing = [
        path
        for path in required
        if not path.exists()
    ]

    if missing:
        raise FileNotFoundError(
            "Arquivos ausentes:\n"
            + "\n".join(
                f"  - {path}"
                for path in missing
            )
        )

    registry = (
        PROJECT_ROOT
        / "src"
        / "ui"
        / "widget_registry.py"
    ).read_text(encoding="utf-8")
    manager = (
        PROJECT_ROOT
        / "src"
        / "ui"
        / "overlay_manager.py"
    ).read_text(encoding="utf-8")
    menu = MAIN_MENU.read_text(encoding="utf-8")

    checks = {
        "Battery implementado no registro":
            'WidgetDefinition("battery", "Battery", "Carro", True, True)'
            in registry,
        "Battery importado no OverlayManager":
            "BatteryWidget" in manager,
        "create_battery criado":
            "def create_battery(" in manager,
        "Battery recebe dados da sessão":
            "battery.update_from_session(session)" in manager,
        "BatteryEditor importado no menu":
            "BatteryEditor" in menu,
        "Branch do editor Battery criado":
            'widget_id == "battery"' in menu,
    }

    failed = [
        label
        for label, passed in checks.items()
        if not passed
    ]

    if failed:
        raise RuntimeError(
            "A instalação parcial ainda possui problemas:\n"
            + "\n".join(
                f"  - {label}"
                for label in failed
            )
        )

    for path in required:
        if path.suffix == ".py":
            py_compile.compile(
                str(path),
                doraise=True,
            )

    print("Integração Battery verificada.")
    print("Sintaxe Python validada.")


def main() -> None:
    print("Aplicando Battery V1.1 Menu Hotfix...")
    print()

    patch_main_menu()
    merge_battery_config()
    verify_integration()

    print()
    print("Battery Hybrid V1.1 finalizado corretamente.")
    print()
    print("Teste visual:")
    print(r"python .\src\tools\test_battery_widget.py")
    print()
    print("Diagnóstico com LMU:")
    print(r"python .\src\tools\diagnose_battery_lmu.py")
    print()
    print("Executar projeto:")
    print(r"python .\src\tools\run_sector_flow_lmu.py")


if __name__ == "__main__":
    main()
