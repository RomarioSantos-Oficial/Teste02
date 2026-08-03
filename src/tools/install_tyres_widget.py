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
    / "tyres_defaults.json"
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
        f"{path.name}.tyres_{stamp}.bak"
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
        "class WheelData:"
    )
    end = source.find(
        "\n\n@dataclass",
        start + 1,
    )

    if start < 0 or end < 0:
        raise RuntimeError(
            "Não encontrei WheelData em "
            "src/telemetry/models.py."
        )

    block = source[start:end]
    fields = [
        (
            "suspension_deflection_m",
            "    suspension_deflection_m: float = 0.0\n",
        ),
        (
            "ride_height_m",
            "    ride_height_m: float = 0.0\n",
        ),
        (
            "susp_force_n",
            "    susp_force_n: float = 0.0\n",
        ),
        (
            "brake_pressure",
            "    brake_pressure: float = 0.0\n",
        ),
        (
            "rotation_rad_s",
            "    rotation_rad_s: float = 0.0\n",
        ),
        (
            "lateral_patch_velocity_ms",
            "    lateral_patch_velocity_ms: float = 0.0\n",
        ),
        (
            "longitudinal_patch_velocity_ms",
            "    longitudinal_patch_velocity_ms: float = 0.0\n",
        ),
        (
            "lateral_ground_velocity_ms",
            "    lateral_ground_velocity_ms: float = 0.0\n",
        ),
        (
            "longitudinal_ground_velocity_ms",
            "    longitudinal_ground_velocity_ms: float = 0.0\n",
        ),
        (
            "camber_rad",
            "    camber_rad: float = 0.0\n",
        ),
        (
            "toe_rad",
            "    toe_rad: float = 0.0\n",
        ),
        (
            "lateral_force_n",
            "    lateral_force_n: float = 0.0\n",
        ),
        (
            "longitudinal_force_n",
            "    longitudinal_force_n: float = 0.0\n",
        ),
        (
            "tire_load_n",
            "    tire_load_n: float = 0.0\n",
        ),
        (
            "grip_fraction",
            "    grip_fraction: float = 0.0\n",
        ),
        (
            "terrain_name",
            '    terrain_name: str = ""\n',
        ),
        (
            "surface_type",
            "    surface_type: int = 0\n",
        ),
        (
            "static_undeflected_radius_cm",
            "    static_undeflected_radius_cm: float = 0.0\n",
        ),
        (
            "vertical_tire_deflection_m",
            "    vertical_tire_deflection_m: float = 0.0\n",
        ),
        (
            "wheel_y_location_m",
            "    wheel_y_location_m: float = 0.0\n",
        ),
        (
            "carcass_temp_c",
            "    carcass_temp_c: float = 0.0\n",
        ),
        (
            "inner_left_c",
            "    inner_left_c: float = 0.0\n",
        ),
        (
            "inner_center_c",
            "    inner_center_c: float = 0.0\n",
        ),
        (
            "inner_right_c",
            "    inner_right_c: float = 0.0\n",
        ),
        (
            "optimal_temp_c",
            "    optimal_temp_c: float = 0.0\n",
        ),
        (
            "compound_index",
            "    compound_index: int = 0\n",
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
        updated_block = (
            block.rstrip()
            + "\n"
            + "".join(missing)
        )
        source = (
            source[:start]
            + updated_block
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
        "inner_temps = getattr("
        not in source
    ):
        anchor = (
            "            temps = wheel.mTemperature\n"
        )

        if anchor not in source:
            raise RuntimeError(
                "Não encontrei a leitura de "
                "mTemperature em lmu_adapter.py."
            )

        insertion = (
            anchor
            + "            inner_temps = getattr(\n"
            + '                wheel, "mTireInnerLayerTemperature", (0.0, 0.0, 0.0)\n'
            + "            )\n"
            + "            carcass_kelvin = safe_float(\n"
            + '                getattr(wheel, "mTireCarcassTemperature", 0.0)\n'
            + "            )\n"
        )
        source = source.replace(
            anchor,
            insertion,
            1,
        )

    if (
        "suspension_deflection_m="
        not in source
    ):
        anchor = (
            "                    compound_type="
            "safe_int(wheel.mCompoundType),\n"
        )

        if anchor not in source:
            raise RuntimeError(
                "Não encontrei compound_type "
                "no WheelData do adapter."
            )

        extra = (
            anchor
            + "                    suspension_deflection_m=safe_float(\n"
            + '                        getattr(wheel, "mSuspensionDeflection", 0.0)\n'
            + "                    ),\n"
            + "                    ride_height_m=safe_float(\n"
            + '                        getattr(wheel, "mRideHeight", 0.0)\n'
            + "                    ),\n"
            + "                    susp_force_n=safe_float(\n"
            + '                        getattr(wheel, "mSuspForce", 0.0)\n'
            + "                    ),\n"
            + "                    brake_pressure=safe_float(\n"
            + '                        getattr(wheel, "mBrakePressure", 0.0)\n'
            + "                    ),\n"
            + "                    rotation_rad_s=safe_float(\n"
            + '                        getattr(wheel, "mRotation", 0.0)\n'
            + "                    ),\n"
            + "                    lateral_patch_velocity_ms=safe_float(\n"
            + '                        getattr(wheel, "mLateralPatchVel", 0.0)\n'
            + "                    ),\n"
            + "                    longitudinal_patch_velocity_ms=safe_float(\n"
            + '                        getattr(wheel, "mLongitudinalPatchVel", 0.0)\n'
            + "                    ),\n"
            + "                    lateral_ground_velocity_ms=safe_float(\n"
            + '                        getattr(wheel, "mLateralGroundVel", 0.0)\n'
            + "                    ),\n"
            + "                    longitudinal_ground_velocity_ms=safe_float(\n"
            + '                        getattr(wheel, "mLongitudinalGroundVel", 0.0)\n'
            + "                    ),\n"
            + "                    camber_rad=safe_float(\n"
            + '                        getattr(wheel, "mCamber", 0.0)\n'
            + "                    ),\n"
            + "                    toe_rad=safe_float(\n"
            + '                        getattr(wheel, "mToe", 0.0)\n'
            + "                    ),\n"
            + "                    lateral_force_n=safe_float(\n"
            + '                        getattr(wheel, "mLateralForce", 0.0)\n'
            + "                    ),\n"
            + "                    longitudinal_force_n=safe_float(\n"
            + '                        getattr(wheel, "mLongitudinalForce", 0.0)\n'
            + "                    ),\n"
            + "                    tire_load_n=safe_float(\n"
            + '                        getattr(wheel, "mTireLoad", 0.0)\n'
            + "                    ),\n"
            + "                    grip_fraction=safe_float(\n"
            + '                        getattr(wheel, "mGripFract", 0.0)\n'
            + "                    ),\n"
            + "                    terrain_name=decode_text(\n"
            + '                        getattr(wheel, "mTerrainName", b"")\n'
            + "                    ),\n"
            + "                    surface_type=safe_int(\n"
            + '                        getattr(wheel, "mSurfaceType", 0)\n'
            + "                    ),\n"
            + "                    static_undeflected_radius_cm=safe_float(\n"
            + '                        getattr(wheel, "mStaticUndeflectedRadius", 0.0)\n'
            + "                    ),\n"
            + "                    vertical_tire_deflection_m=safe_float(\n"
            + '                        getattr(wheel, "mVerticalTireDeflection", 0.0)\n'
            + "                    ),\n"
            + "                    wheel_y_location_m=safe_float(\n"
            + '                        getattr(wheel, "mWheelYLocation", 0.0)\n'
            + "                    ),\n"
            + "                    carcass_temp_c=(\n"
            + "                        carcass_kelvin - 273.15\n"
            + "                        if carcass_kelvin > 100.0\n"
            + "                        else 0.0\n"
            + "                    ),\n"
            + "                    inner_left_c=(\n"
            + "                        safe_float(inner_temps[0]) - 273.15\n"
            + "                        if safe_float(inner_temps[0]) > 100.0\n"
            + "                        else 0.0\n"
            + "                    ),\n"
            + "                    inner_center_c=(\n"
            + "                        safe_float(inner_temps[1]) - 273.15\n"
            + "                        if safe_float(inner_temps[1]) > 100.0\n"
            + "                        else 0.0\n"
            + "                    ),\n"
            + "                    inner_right_c=(\n"
            + "                        safe_float(inner_temps[2]) - 273.15\n"
            + "                        if safe_float(inner_temps[2]) > 100.0\n"
            + "                        else 0.0\n"
            + "                    ),\n"
            + "                    optimal_temp_c=safe_float(\n"
            + '                        getattr(wheel, "mOptimalTemp", 0.0)\n'
            + "                    ),\n"
            + "                    compound_index=safe_int(\n"
            + '                        getattr(wheel, "mCompoundIndex", 0)\n'
            + "                    ),\n"
        )
        source = source.replace(
            anchor,
            extra,
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
        'WidgetDefinition("tires", '
        '"Tires", "Carro", True, False)'
    )
    new = (
        'WidgetDefinition("tires", '
        '"Tyres", "Carro", True, True)'
    )

    if old in source:
        source = source.replace(
            old,
            new,
            1,
        )
    elif new not in source:
        raise RuntimeError(
            "Definição tires não encontrada "
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
        "from src.widget.tyres.tyres_widget "
        "import TyresWidget\n"
    )

    if import_line not in source:
        anchors = [
            (
                "from src.widget.flags.flags_widget "
                "import FlagsWidget\n"
            ),
            (
                "from src.widget.driver_panel."
                "driver_panel_widget import "
                "DriverPanelWidget\n"
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
        "def create_tires("
        not in source
    ):
        anchor = (
            "    def create_widget("
            "self, widget_id: str"
            ") -> QWidget:\n"
        )
        method = (
            "    def create_tires(self) -> TyresWidget:\n"
            "        existing = self.widgets.get(\"tires\")\n"
            "        if isinstance(existing, TyresWidget):\n"
            "            return existing\n"
            "        config = deepcopy(\n"
            "            self.config_data[\"widgets\"][\"tires\"]\n"
            "        )\n"
            "        widget = TyresWidget(\"tires\", config)\n"
            "        self._prepare_widget(\"tires\", widget, config)\n"
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
        '"tires": self.create_tires'
        not in source
    ):
        anchors = [
            '            "flags": self.create_flags,\n',
            '            "delta": self.create_delta,\n',
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
                "Dicionário de creators não encontrado."
            )

        source = source.replace(
            anchor,
            anchor
            + '            "tires": self.create_tires,\n',
            1,
        )

    set_pattern = re.compile(
        r'widget_id in \{(?P<items>[^}]*)\}'
    )
    match = set_pattern.search(
        source
    )

    if match is not None and '"tires"' not in match.group(
        "items"
    ):
        items = match.group(
            "items"
        ).rstrip()
        separator = (
            ", "
            if "\n" not in items
            else ",\n"
        )
        replacement = (
            "widget_id in {"
            + items
            + separator
            + '"tires"'
            + "}"
        )
        source = (
            source[:match.start()]
            + replacement
            + source[match.end():]
        )

    if (
        "tires.update_telemetry(player_data)"
        not in source
    ):
        anchor = (
            "    def update_session_data("
            "self, session: Any"
            ") -> None:\n"
        )
        method_end = source.find(
            anchor
        )

        if method_end < 0:
            raise RuntimeError(
                "update_session_data não encontrado."
            )

        player_method_start = source.find(
            "    def update_player_data(",
        )

        if player_method_start >= 0:
            insertion_point = source.find(
                anchor,
                player_method_start,
            )
            block = (
                "\n"
                '        tires = self.widgets.get("tires")\n'
                "        if tires is not None "
                "and tires.isVisible():\n"
                "            tires.update_telemetry(player_data)\n"
            )
            source = (
                source[:insertion_point]
                + block
                + source[insertion_point:]
            )

    if (
        "tires.update_telemetry(session.player)"
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
            '        tires = self.widgets.get("tires")\n'
            "        if (\n"
            "            tires is not None\n"
            "            and tires.isVisible()\n"
            "            and getattr(session, \"player\", None) is not None\n"
            "        ):\n"
            "            tires.update_telemetry(session.player)\n\n"
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
        "from src.widget.tyres.tyres_editor "
        "import TyresEditor\n"
    )

    if import_line not in source:
        anchors = [
            (
                "from src.widget.flags.flags_editor "
                "import FlagsEditor\n"
            ),
            (
                "from src.widget.driver_panel."
                "driver_panel_editor import "
                "DriverPanelEditor\n"
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
        'elif widget_id == "tires":'
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
            + '        elif widget_id == "tires":\n'
            "            editor = TyresEditor(\n"
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
            "tires",
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
    data["widgets"]["tires"] = deep_merge(
        defaults,
        preserved,
    )
    data.setdefault(
        "defaults",
        {},
    )["tires"] = deepcopy(
        defaults
    )
    data["version"] = max(
        int(
            data.get(
                "version",
                1,
            )
        ),
        18,
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
        / "src/widget/tyres/tyres_models.py",
        PROJECT_ROOT
        / "src/widget/tyres/tyres_logic.py",
        PROJECT_ROOT
        / "src/widget/tyres/tyres_widget.py",
        PROJECT_ROOT
        / "src/widget/tyres/tyres_editor.py",
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
        / "src/widget/tyres/tyres_widget.py",
        PROJECT_ROOT
        / "src/widget/tyres/tyres_editor.py",
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
        "Tyres Widget V1 instalado."
    )
    print()
    print(
        "Teste sem LMU:"
    )
    print(
        r"python .\src\tools\test_tyres_widget.py"
    )
    print()
    print(
        "Diagnóstico com LMU:"
    )
    print(
        r"python .\src\tools\diagnose_tyres_lmu.py"
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
