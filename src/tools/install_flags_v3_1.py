from __future__ import annotations

import json
import py_compile
import shutil
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def backup(path: Path) -> None:
    if not path.exists():
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = path.with_name(f"{path.name}.flags_v3_1_{stamp}.bak")
    shutil.copy2(path, target)
    print(f"Backup: {target}")


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
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)

    return result


def require_files() -> None:
    required = [
        PROJECT_ROOT / "src" / "telemetry" / "models.py",
        PROJECT_ROOT / "src" / "telemetry" / "lmu_adapter.py",
        PROJECT_ROOT / "src" / "widget" / "flags" / "flags_widget.py",
        PROJECT_ROOT / "src" / "widget" / "flags" / "flags_logic.py",
        PROJECT_ROOT / "src" / "widget" / "flags" / "flags_editor.py",
        PROJECT_ROOT / "src" / "config" / "flags_v3_defaults.json",
    ]

    missing = [path for path in required if not path.exists()]

    if missing:
        lines = "\n".join(f"  - {path}" for path in missing)
        raise FileNotFoundError(
            "Os arquivos da V3.1 não foram extraídos na raiz do projeto.\n"
            "Arquivos ausentes:\n"
            f"{lines}\n\n"
            "Extraia novamente o ZIP dentro de:\n"
            f"{PROJECT_ROOT}"
        )


def patch_registry() -> None:
    path = PROJECT_ROOT / "src" / "ui" / "widget_registry.py"
    backup(path)
    source = path.read_text(encoding="utf-8")

    old = 'WidgetDefinition("flags", "Flags", "Corrida", True, False)'
    new = 'WidgetDefinition("flags", "Flags", "Corrida", True, True)'

    if old in source:
        source = source.replace(old, new, 1)
    elif new not in source:
        raise RuntimeError(
            "Não encontrei a definição do widget Flags em widget_registry.py."
        )

    path.write_text(source, encoding="utf-8")
    print(f"Integrado: {path}")


def patch_overlay_manager() -> None:
    path = PROJECT_ROOT / "src" / "ui" / "overlay_manager.py"
    backup(path)
    source = path.read_text(encoding="utf-8")

    import_line = "from src.widget.flags.flags_widget import FlagsWidget\n"
    if import_line not in source:
        anchor = (
            "from src.widget.driver_panel.driver_panel_widget "
            "import DriverPanelWidget\n"
        )
        if anchor not in source:
            raise RuntimeError(
                "Não encontrei o import do DriverPanel em overlay_manager.py."
            )
        source = source.replace(anchor, anchor + import_line, 1)

    if "    def create_flags(self) -> FlagsWidget:" not in source:
        anchor = "    def create_widget(self, widget_id: str) -> QWidget:\n"
        method = (
            "    def create_flags(self) -> FlagsWidget:\n"
            "        existing = self.widgets.get(\"flags\")\n"
            "        if isinstance(existing, FlagsWidget):\n"
            "            return existing\n"
            "        config = deepcopy(self.config_data[\"widgets\"][\"flags\"])\n"
            "        widget = FlagsWidget(\"flags\", config)\n"
            "        self._prepare_widget(\"flags\", widget, config)\n"
            "        return widget\n\n"
        )
        if anchor not in source:
            raise RuntimeError(
                "Não encontrei create_widget em overlay_manager.py."
            )
        source = source.replace(anchor, method + anchor, 1)

    if '"flags": self.create_flags' not in source:
        anchor = '            "delta": self.create_delta,\n'
        if anchor not in source:
            raise RuntimeError(
                "Não encontrei o registro do Delta em overlay_manager.py."
            )
        source = source.replace(
            anchor,
            anchor + '            "flags": self.create_flags,\n',
            1,
        )

    # Compatível com a versão original e com versões parcialmente modificadas.
    source = source.replace(
        'widget_id in {"driver_panel", "delta"}',
        'widget_id in {"driver_panel", "delta", "flags"}',
    )
    source = source.replace(
        'widget_id in {"driver_panel", "delta", "flags", "flags"}',
        'widget_id in {"driver_panel", "delta", "flags"}',
    )

    if "flags.update_from_session(session)" not in source:
        anchor = (
            '        delta = self.widgets.get("delta")\n'
            "        if delta is not None and delta.isVisible():\n"
            "            delta.update_from_session(session)\n"
        )
        block = (
            anchor
            + "\n"
            '        flags = self.widgets.get("flags")\n'
            '        flags_config = self.config_data.get("widgets", {}).get(\n'
            '            "flags", {}\n'
            "        )\n"
            "        if flags is not None and bool(\n"
            '            flags_config.get("enabled", False)\n'
            "        ):\n"
            "            # Atualiza mesmo oculto para reaparecer quando surgir bandeira.\n"
            "            flags.update_from_session(session)\n"
        )

        if anchor not in source:
            raise RuntimeError(
                "Não encontrei update_session_data em overlay_manager.py."
            )
        source = source.replace(anchor, block, 1)

    path.write_text(source, encoding="utf-8")
    print(f"Integrado: {path}")


def patch_main_menu() -> None:
    path = PROJECT_ROOT / "src" / "ui" / "main_menu_window.py"
    backup(path)
    source = path.read_text(encoding="utf-8")

    import_line = "from src.widget.flags.flags_editor import FlagsEditor\n"
    if import_line not in source:
        anchor = (
            "from src.widget.driver_panel.driver_panel_editor "
            "import DriverPanelEditor\n"
        )
        if anchor not in source:
            raise RuntimeError(
                "Não encontrei o import do DriverPanelEditor."
            )
        source = source.replace(anchor, anchor + import_line, 1)

    if 'elif widget_id == "flags":' not in source:
        anchor = (
            '        elif widget_id == "delta":\n'
            "            editor = DeltaEditor(\n"
            '                deepcopy(self.overlay_manager.config_data["widgets"][widget_id]), self\n'
            "            )\n"
        )
        branch = (
            anchor
            + '        elif widget_id == "flags":\n'
            "            editor = FlagsEditor(\n"
            '                deepcopy(self.overlay_manager.config_data["widgets"][widget_id]), self\n'
            "            )\n"
        )

        if anchor not in source:
            raise RuntimeError(
                "Não encontrei o bloco do editor Delta no menu."
            )
        source = source.replace(anchor, branch, 1)

    path.write_text(source, encoding="utf-8")
    print(f"Integrado: {path}")


def merge_widgets_config() -> None:
    path = PROJECT_ROOT / "src" / "config" / "widgets.json"
    defaults_path = PROJECT_ROOT / "src" / "config" / "flags_v3_defaults.json"

    backup(path)

    data = json.loads(path.read_text(encoding="utf-8"))
    defaults = json.loads(defaults_path.read_text(encoding="utf-8"))
    current = data.setdefault("widgets", {}).get("flags", {})

    # A V3.1 aplica os novos ajustes responsivos, mas preserva layout e estado.
    preserved = {
        key: deepcopy(current[key])
        for key in ("enabled", "monitor", "position", "size", "scale")
        if key in current
    }

    merged = deep_merge(defaults, preserved)
    data["widgets"]["flags"] = merged
    data.setdefault("defaults", {})["flags"] = deepcopy(defaults)
    data["version"] = max(int(data.get("version", 1)), 16)

    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Config integrado: {path}")


def validate() -> None:
    files = [
        PROJECT_ROOT / "src" / "telemetry" / "models.py",
        PROJECT_ROOT / "src" / "telemetry" / "lmu_adapter.py",
        PROJECT_ROOT / "src" / "widget" / "flags" / "flags_models.py",
        PROJECT_ROOT / "src" / "widget" / "flags" / "flags_logic.py",
        PROJECT_ROOT / "src" / "widget" / "flags" / "flags_widget.py",
        PROJECT_ROOT / "src" / "widget" / "flags" / "flags_editor.py",
        PROJECT_ROOT / "src" / "ui" / "overlay_manager.py",
        PROJECT_ROOT / "src" / "ui" / "main_menu_window.py",
        PROJECT_ROOT / "src" / "ui" / "widget_registry.py",
    ]

    for path in files:
        py_compile.compile(str(path), doraise=True)

    print("Sintaxe Python validada.")


def main() -> None:
    require_files()
    patch_registry()
    patch_overlay_manager()
    patch_main_menu()
    merge_widgets_config()
    validate()

    print()
    print("Flags V3.1 instalado corretamente.")
    print()
    print("Teste visual:")
    print(r"python .\src\tools\test_flags_v3.py")
    print()
    print("Diagnóstico com LMU aberto:")
    print(r"python .\src\tools\diagnose_flags_lmu.py")
    print()
    print("Executar o projeto:")
    print(r"python .\src\tools\run_sector_flow_lmu.py")


if __name__ == "__main__":
    main()
