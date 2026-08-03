from __future__ import annotations

import json
import py_compile
import shutil
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = PROJECT_ROOT
PAYLOAD_ROOT = PACKAGE_ROOT / "payload"


PAYLOAD_FILES = [
    "src/telemetry/models.py",
    "src/telemetry/lmu_adapter.py",
    "src/widget/flags/flags_models.py",
    "src/widget/flags/flags_logic.py",
    "src/widget/flags/flags_widget.py",
    "src/widget/flags/flags_editor.py",
    "src/widget/flags/__init__.py",
    "src/config/flags_v3_defaults.json",
    "src/tools/test_flags_v3.py",
    "src/tools/diagnose_flags_lmu.py",
]


def backup(path: Path) -> None:
    if not path.exists():
        return

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )
    backup_path = path.with_name(
        f"{path.name}.flags_v3_{stamp}.bak"
    )
    shutil.copy2(
        path,
        backup_path,
    )
    print(
        f"Backup: {backup_path}"
    )


def copy_payload() -> None:
    if not PAYLOAD_ROOT.exists():
        raise FileNotFoundError(
            f"Pasta payload não encontrada: "
            f"{PAYLOAD_ROOT}"
        )

    for relative in PAYLOAD_FILES:
        source = PAYLOAD_ROOT / relative
        target = PROJECT_ROOT / relative

        if not source.exists():
            raise FileNotFoundError(
                f"Arquivo do pacote ausente: "
                f"{source}"
            )

        target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        backup(target)
        shutil.copy2(
            source,
            target,
        )
        print(
            f"Instalado: {target}"
        )


def deep_merge(
    base: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    result = deepcopy(base)

    for key, value in override.items():
        if (
            isinstance(value, dict)
            and isinstance(
                result.get(key),
                dict,
            )
        ):
            result[key] = deep_merge(
                result[key],
                value,
            )
        else:
            result[key] = deepcopy(value)

    return result


def patch_registry() -> None:
    path = (
        PROJECT_ROOT
        / "src"
        / "ui"
        / "widget_registry.py"
    )
    backup(path)
    source = path.read_text(
        encoding="utf-8"
    )
    source = source.replace(
        'WidgetDefinition("flags", "Flags", "Corrida", True, False)',
        'WidgetDefinition("flags", "Flags", "Corrida", True, True)',
    )
    path.write_text(
        source,
        encoding="utf-8",
    )
    print(
        f"Integrado: {path}"
    )


def patch_overlay_manager() -> None:
    path = (
        PROJECT_ROOT
        / "src"
        / "ui"
        / "overlay_manager.py"
    )
    backup(path)
    source = path.read_text(
        encoding="utf-8"
    )

    import_line = (
        "from src.widget.flags.flags_widget "
        "import FlagsWidget\n"
    )

    if import_line not in source:
        anchor = (
            "from src.widget.driver_panel."
            "driver_panel_widget import "
            "DriverPanelWidget\n"
        )
        source = source.replace(
            anchor,
            anchor + import_line,
            1,
        )

    if "def create_flags(" not in source:
        anchor = (
            "    def create_widget("
            "self, widget_id: str"
            ") -> QWidget:\n"
        )
        method = (
            "    def create_flags(self) -> FlagsWidget:\n"
            "        existing = self.widgets.get(\"flags\")\n"
            "        if isinstance(existing, FlagsWidget):\n"
            "            return existing\n"
            "        config = deepcopy(\n"
            "            self.config_data[\"widgets\"][\"flags\"]\n"
            "        )\n"
            "        widget = FlagsWidget(\"flags\", config)\n"
            "        self._prepare_widget(\"flags\", widget, config)\n"
            "        return widget\n\n"
        )

        if anchor not in source:
            raise RuntimeError(
                "Não encontrei create_widget "
                "em overlay_manager.py."
            )

        source = source.replace(
            anchor,
            method + anchor,
            1,
        )

    if '"flags": self.create_flags' not in source:
        source = source.replace(
            '            "delta": self.create_delta,\n',
            '            "delta": self.create_delta,\n'
            '            "flags": self.create_flags,\n',
            1,
        )

    source = source.replace(
        'widget_id in {"driver_panel", "delta"}',
        'widget_id in '
        '{"driver_panel", "delta", "flags"}',
    )

    if (
        "flags.update_from_session(session)"
        not in source
    ):
        anchor = (
            '        delta = self.widgets.get("delta")\n'
            "        if delta is not None "
            "and delta.isVisible():\n"
            "            delta.update_from_session(session)\n"
        )
        block = (
            anchor
            + "\n"
            '        flags = self.widgets.get("flags")\n'
            "        flags_config = "
            "self.config_data.get("
            '"widgets", {}).get("flags", {})\n'
            "        if flags is not None and bool(\n"
            '            flags_config.get("enabled", False)\n'
            "        ):\n"
            "            # Atualiza mesmo oculto para poder "
            "reaparecer automaticamente.\n"
            "            flags.update_from_session(session)\n"
        )

        if anchor not in source:
            raise RuntimeError(
                "Não encontrei update_session_data "
                "em overlay_manager.py."
            )

        source = source.replace(
            anchor,
            block,
            1,
        )

    path.write_text(
        source,
        encoding="utf-8",
    )
    print(
        f"Integrado: {path}"
    )


def patch_main_menu() -> None:
    path = (
        PROJECT_ROOT
        / "src"
        / "ui"
        / "main_menu_window.py"
    )
    backup(path)
    source = path.read_text(
        encoding="utf-8"
    )

    import_line = (
        "from src.widget.flags.flags_editor "
        "import FlagsEditor\n"
    )

    if import_line not in source:
        anchor = (
            "from src.widget.driver_panel."
            "driver_panel_editor import "
            "DriverPanelEditor\n"
        )
        source = source.replace(
            anchor,
            anchor + import_line,
            1,
        )

    if 'elif widget_id == "flags":' not in source:
        anchor = (
            '        elif widget_id == "delta":\n'
            "            editor = DeltaEditor(\n"
            '                deepcopy(self.overlay_manager.'
            'config_data["widgets"][widget_id]), self\n'
            "            )\n"
        )
        branch = (
            anchor
            + '        elif widget_id == "flags":\n'
            "            editor = FlagsEditor(\n"
            '                deepcopy(self.overlay_manager.'
            'config_data["widgets"][widget_id]), self\n'
            "            )\n"
        )

        if anchor not in source:
            raise RuntimeError(
                "Não encontrei o editor Delta "
                "em main_menu_window.py."
            )

        source = source.replace(
            anchor,
            branch,
            1,
        )

    path.write_text(
        source,
        encoding="utf-8",
    )
    print(
        f"Integrado: {path}"
    )


def merge_widgets_config() -> None:
    path = (
        PROJECT_ROOT
        / "src"
        / "config"
        / "widgets.json"
    )
    defaults_path = (
        PROJECT_ROOT
        / "src"
        / "config"
        / "flags_v3_defaults.json"
    )

    backup(path)

    data = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )
    defaults = json.loads(
        defaults_path.read_text(
            encoding="utf-8"
        )
    )
    current = (
        data
        .setdefault(
            "widgets",
            {},
        )
        .get(
            "flags",
            {},
        )
    )

    # Preserva o estado e a posição do usuário.
    preserved = {
        key: deepcopy(current[key])
        for key in (
            "enabled",
            "monitor",
            "position",
            "size",
            "scale",
        )
        if key in current
    }

    merged = deep_merge(
        defaults,
        preserved,
    )
    data["widgets"]["flags"] = merged
    data.setdefault(
        "defaults",
        {},
    )["flags"] = deepcopy(defaults)
    data["version"] = max(
        int(
            data.get(
                "version",
                1,
            )
        ),
        15,
    )

    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        f"Config integrado: {path}"
    )


def validate() -> None:
    files = [
        PROJECT_ROOT
        / relative
        for relative in PAYLOAD_FILES
        if relative.endswith(".py")
    ]
    files.extend(
        [
            PROJECT_ROOT
            / "src/ui/overlay_manager.py",
            PROJECT_ROOT
            / "src/ui/main_menu_window.py",
            PROJECT_ROOT
            / "src/ui/widget_registry.py",
        ]
    )

    for path in files:
        py_compile.compile(
            str(path),
            doraise=True,
        )

    print(
        "Sintaxe Python validada."
    )


def main() -> None:
    copy_payload()
    patch_registry()
    patch_overlay_manager()
    patch_main_menu()
    merge_widgets_config()
    validate()

    print()
    print(
        "Flags V3 Responsivo instalado."
    )
    print()
    print(
        "Teste visual e redimensionamento:"
    )
    print(
        r"python .\src\tools\test_flags_v3.py"
    )
    print()
    print(
        "Diagnóstico com o LMU aberto:"
    )
    print(
        r"python .\src\tools\diagnose_flags_lmu.py"
    )
    print()
    print(
        "Executar o projeto:"
    )
    print(
        r"python .\src\tools\run_sector_flow_lmu.py"
    )


if __name__ == "__main__":
    main()
