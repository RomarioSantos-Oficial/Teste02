#  SectorFlow is an open-source overlay application for racing simulation.
#  Copyright (C) 2022-2026 SectorFlow developers
#  Based on TinyPedal - Copyright (C) 2022-2026 TinyPedal developers
#
#  This file is part of SectorFlow.
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

from __future__ import annotations

import json
import py_compile
import re
import shutil
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(
    __file__
).resolve().parents[2]
DEFAULTS_PATH = (
    PROJECT_ROOT
    / "src"
    / "config"
    / "battery_defaults.json"
)


def backup(
    path: Path,
) -> None:
    if not path.exists():
        return

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )
    target = path.with_name(
        f"{path.name}.battery_{stamp}.bak"
    )
    shutil.copy2(
        path,
        target,
    )
    print(
        f"Backup: {target}"
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
            result[key] = deepcopy(
                value
            )

    return result


def patch_models() -> None:
    path = (
        PROJECT_ROOT
        / "src"
        / "telemetry"
        / "models.py"
    )
    backup(path)
    source = path.read_text(
        encoding="utf-8"
    )

    start = source.find(
        "class PlayerData:"
    )
    end = source.find(
        "\n\n@dataclass",
        start + 1,
    )

    if start < 0 or end < 0:
        raise RuntimeError(
            "Não encontrei PlayerData em models.py."
        )

    block = source[start:end]
    fields = [
        (
            "regen_kw",
            "    regen_kw: float = 0.0\n",
        ),
        (
            "electric_motor_torque_nm",
            "    electric_motor_torque_nm: float = 0.0\n",
        ),
        (
            "electric_motor_rpm",
            "    electric_motor_rpm: float = 0.0\n",
        ),
        (
            "electric_motor_temp_c",
            "    electric_motor_temp_c: float = 0.0\n",
        ),
        (
            "electric_motor_water_temp_c",
            "    electric_motor_water_temp_c: float = 0.0\n",
        ),
        (
            "electric_motor_state",
            "    electric_motor_state: int = 0\n",
        ),
    ]

    missing = [
        line
        for name, line in fields
        if re.search(
            rf"^\s*{re.escape(name)}\s*:",
            block,
            flags=re.MULTILINE,
        )
        is None
    ]

    if missing:
        anchor = (
            "    virtual_energy: float = 0.0\n"
        )

        if anchor not in block:
            raise RuntimeError(
                "Não encontrei virtual_energy "
                "em PlayerData."
            )

        block = block.replace(
            anchor,
            anchor
            + "\n"
            + "    # Sistema híbrido / bateria.\n"
            + "".join(missing),
            1,
        )
        source = (
            source[:start]
            + block
            + source[end:]
        )

    path.write_text(
        source,
        encoding="utf-8",
    )
    print(
        f"Atualizado: {path}"
    )


def patch_adapter() -> None:
    path = (
        PROJECT_ROOT
        / "src"
        / "telemetry"
        / "lmu_adapter.py"
    )
    backup(path)
    source = path.read_text(
        encoding="utf-8"
    )

    if (
        "regen_kw=safe_float("
        not in source
    ):
        anchor = (
            "            virtual_energy="
            "safe_float(raw.mVirtualEnergy),\n"
        )

        if anchor not in source:
            raise RuntimeError(
                "Não encontrei virtual_energy "
                "no retorno de PlayerData."
            )

        fields = (
            anchor
            + "            regen_kw=safe_float(\n"
            + '                getattr(raw, "mRegen", 0.0)\n'
            + "            ),\n"
            + "            electric_motor_torque_nm=safe_float(\n"
            + '                getattr(raw, "mElectricBoostMotorTorque", 0.0)\n'
            + "            ),\n"
            + "            electric_motor_rpm=safe_float(\n"
            + '                getattr(raw, "mElectricBoostMotorRPM", 0.0)\n'
            + "            ),\n"
            + "            electric_motor_temp_c=safe_float(\n"
            + '                getattr(raw, "mElectricBoostMotorTemperature", 0.0)\n'
            + "            ),\n"
            + "            electric_motor_water_temp_c=safe_float(\n"
            + '                getattr(raw, "mElectricBoostWaterTemperature", 0.0)\n'
            + "            ),\n"
            + "            electric_motor_state=safe_int(\n"
            + '                getattr(raw, "mElectricBoostMotorState", 0)\n'
            + "            ),\n"
        )
        source = source.replace(
            anchor,
            fields,
            1,
        )

    path.write_text(
        source,
        encoding="utf-8",
    )
    print(
        f"Atualizado: {path}"
    )


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
    old = (
        'WidgetDefinition("battery", '
        '"Battery", "Carro", True, False)'
    )
    new = (
        'WidgetDefinition("battery", '
        '"Battery", "Carro", True, True)'
    )

    if old in source:
        source = source.replace(
            old,
            new,
            1,
        )
    elif new not in source:
        raise RuntimeError(
            "Definição Battery não encontrada "
            "em widget_registry.py."
        )

    path.write_text(
        source,
        encoding="utf-8",
    )
    print(
        f"Atualizado: {path}"
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
        "from src.widget.battery.battery_widget "
        "import BatteryWidget\n"
    )

    if import_line not in source:
        anchors = [
            (
                "from src.widget.flags.flags_widget "
                "import FlagsWidget\n"
            ),
            (
                "from src.widget.delta.delta_widget "
                "import DeltaWidget\n"
            ),
        ]
        anchor = next(
            (
                item
                for item in anchors
                if item in source
            ),
            None,
        )

        if anchor is None:
            raise RuntimeError(
                "Ponto de imports não encontrado "
                "em overlay_manager.py."
            )

        source = source.replace(
            anchor,
            anchor + import_line,
            1,
        )

    if (
        "def create_battery("
        not in source
    ):
        anchor = (
            "    def create_widget("
            "self, widget_id: str"
            ") -> QWidget:\n"
        )
        method = (
            "    def create_battery(self) -> BatteryWidget:\n"
            "        existing = self.widgets.get(\"battery\")\n"
            "        if isinstance(existing, BatteryWidget):\n"
            "            return existing\n"
            "        config = deepcopy(\n"
            "            self.config_data[\"widgets\"][\"battery\"]\n"
            "        )\n"
            "        widget = BatteryWidget(\"battery\", config)\n"
            "        self._prepare_widget(\"battery\", widget, config)\n"
            "        return widget\n\n"
        )

        if anchor not in source:
            raise RuntimeError(
                "create_widget não encontrado "
                "em overlay_manager.py."
            )

        source = source.replace(
            anchor,
            method + anchor,
            1,
        )

    if (
        '"battery": self.create_battery'
        not in source
    ):
        anchor = (
            '            "flags": self.create_flags,\n'
        )

        if anchor not in source:
            anchor = (
                '            "delta": self.create_delta,\n'
            )

        if anchor not in source:
            raise RuntimeError(
                "Dicionário de creators não encontrado."
            )

        source = source.replace(
            anchor,
            anchor
            + '            "battery": self.create_battery,\n',
            1,
        )

    enabled_start = source.find(
        "    def create_enabled_widgets"
    )
    enabled_end = source.find(
        "    def _prepare_widget",
        enabled_start,
    )

    if enabled_start < 0 or enabled_end < 0:
        raise RuntimeError(
            "create_enabled_widgets não encontrado."
        )

    enabled_block = source[
        enabled_start:enabled_end
    ]

    if '"battery"' not in enabled_block:
        set_match = re.search(
            r"widget_id\s+in\s+\{(?P<items>[^}]*)\}",
            enabled_block,
            flags=re.DOTALL,
        )

        if set_match is None:
            raise RuntimeError(
                "Conjunto de widgets habilitados "
                "não encontrado."
            )

        items = set_match.group(
            "items"
        ).rstrip()
        separator = (
            ", "
            if "\n" not in items
            else ",\n                "
        )
        replacement = (
            "widget_id in {"
            + items
            + separator
            + '"battery"'
            + "}"
        )
        enabled_block = (
            enabled_block[
                :set_match.start()
            ]
            + replacement
            + enabled_block[
                set_match.end():
            ]
        )
        source = (
            source[:enabled_start]
            + enabled_block
            + source[enabled_end:]
        )

    if (
        "battery.update_from_session(session)"
        not in source
    ):
        anchor = (
            '        delta = self.widgets.get("delta")\n'
        )

        if anchor not in source:
            raise RuntimeError(
                "Ponto antes do Delta não encontrado "
                "em update_session_data."
            )

        block = (
            '        battery = self.widgets.get("battery")\n'
            "        battery_config = "
            "self.config_data.get(\"widgets\", {}).get(\n"
            '            "battery", {}\n'
            "        )\n"
            "        if battery is not None and bool(\n"
            '            battery_config.get("enabled", False)\n'
            "        ):\n"
            "            # Continua atualizando mesmo oculto para "
            "reaparecer ao entrar em um Hypercar.\n"
            "            battery.update_from_session(session)\n\n"
        )
        source = source.replace(
            anchor,
            block + anchor,
            1,
        )

    path.write_text(
        source,
        encoding="utf-8",
    )
    print(
        f"Atualizado: {path}"
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
        "from src.widget.battery.battery_editor "
        "import BatteryEditor\n"
    )

    if import_line not in source:
        anchors = [
            (
                "from src.widget.flags.flags_editor "
                "import FlagsEditor\n"
            ),
            (
                "from src.widget.delta.delta_editor "
                "import DeltaEditor\n"
            ),
        ]
        anchor = next(
            (
                item
                for item in anchors
                if item in source
            ),
            None,
        )

        if anchor is None:
            raise RuntimeError(
                "Ponto de imports não encontrado "
                "em main_menu_window.py."
            )

        source = source.replace(
            anchor,
            anchor + import_line,
            1,
        )

    if (
        'elif widget_id == "battery":'
        not in source
    ):
        anchor = (
            '        elif widget_id == "flags":\n'
            "            editor = FlagsEditor(\n"
            '                deepcopy(self.overlay_manager.'
            'config_data["widgets"][widget_id]), self\n'
            "            )\n"
        )

        if anchor not in source:
            anchor = (
                '        elif widget_id == "delta":\n'
                "            editor = DeltaEditor(\n"
                '                deepcopy(self.overlay_manager.'
                'config_data["widgets"][widget_id]), self\n'
                "            )\n"
            )

        if anchor not in source:
            raise RuntimeError(
                "Bloco de editor não encontrado."
            )

        branch = (
            anchor
            + '        elif widget_id == "battery":\n'
            "            editor = BatteryEditor(\n"
            '                deepcopy(self.overlay_manager.'
            'config_data["widgets"][widget_id]), self\n'
            "            )\n"
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
        f"Atualizado: {path}"
    )


def merge_config() -> None:
    path = (
        PROJECT_ROOT
        / "src"
        / "config"
        / "widgets.json"
    )
    backup(path)
    data = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )
    defaults = json.loads(
        DEFAULTS_PATH.read_text(
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
            "battery",
            {},
        )
    )
    preserved = {
        key: deepcopy(
            current[key]
        )
        for key in (
            "enabled",
            "monitor",
            "position",
            "size",
            "scale",
        )
        if key in current
    }
    data["widgets"]["battery"] = (
        deep_merge(
            defaults,
            preserved,
        )
    )
    data.setdefault(
        "defaults",
        {},
    )["battery"] = deepcopy(
        defaults
    )
    data["version"] = max(
        int(
            data.get(
                "version",
                1,
            )
        ),
        19,
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
        f"Atualizado: {path}"
    )


def validate() -> None:
    files = [
        PROJECT_ROOT
        / "src/telemetry/models.py",
        PROJECT_ROOT
        / "src/telemetry/lmu_adapter.py",
        PROJECT_ROOT
        / "src/widget/battery/battery_models.py",
        PROJECT_ROOT
        / "src/widget/battery/battery_tracker.py",
        PROJECT_ROOT
        / "src/widget/battery/battery_widget.py",
        PROJECT_ROOT
        / "src/widget/battery/battery_editor.py",
        PROJECT_ROOT
        / "src/ui/widget_registry.py",
        PROJECT_ROOT
        / "src/ui/overlay_manager.py",
        PROJECT_ROOT
        / "src/ui/main_menu_window.py",
    ]

    for path in files:
        py_compile.compile(
            str(path),
            doraise=True,
        )

    print(
        "Sintaxe Python validada."
    )


def main() -> None:
    required = [
        DEFAULTS_PATH,
        PROJECT_ROOT
        / "src/widget/battery/battery_widget.py",
        PROJECT_ROOT
        / "src/widget/battery/battery_editor.py",
    ]
    missing = [
        path
        for path in required
        if not path.exists()
    ]

    if missing:
        raise FileNotFoundError(
            "Extraia o ZIP diretamente na raiz "
            "do projeto. Arquivos ausentes:\n"
            + "\n".join(
                str(path)
                for path in missing
            )
        )

    patch_models()
    patch_adapter()
    patch_registry()
    patch_overlay_manager()
    patch_main_menu()
    merge_config()
    validate()

    print()
    print(
        "Battery Hybrid Widget V1 instalado."
    )
    print()
    print(
        "Teste sem LMU:"
    )
    print(
        r"python .\src\tools\test_battery_widget.py"
    )
    print()
    print(
        "Diagnóstico com LMU:"
    )
    print(
        r"python .\src\tools\diagnose_battery_lmu.py"
    )
    print()
    print(
        "Executar projeto:"
    )
    print(
        r"python .\src\tools\run_sector_flow_lmu.py"
    )


if __name__ == "__main__":
    main()
