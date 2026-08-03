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
    / "weather_defaults.json"
)


def backup(
    path: Path,
) -> None:
    if not path.exists():
        return

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )
    destination = path.with_name(
        f"{path.name}.weather_{stamp}.bak"
    )
    shutil.copy2(
        path,
        destination,
    )
    print(
        f"Backup: {destination}"
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

    fields = [
        (
            "dark_cloud",
            "    dark_cloud: float = 0.0\n",
        ),
        (
            "cloud_coverage",
            "    cloud_coverage: int = 0\n",
        ),
        (
            "min_path_wetness",
            "    min_path_wetness: float = 0.0\n",
        ),
        (
            "avg_path_wetness",
            "    avg_path_wetness: float = 0.0\n",
        ),
        (
            "max_path_wetness",
            "    max_path_wetness: float = 0.0\n",
        ),
        (
            "wind_x_ms",
            "    wind_x_ms: float = 0.0\n",
        ),
        (
            "wind_y_ms",
            "    wind_y_ms: float = 0.0\n",
        ),
        (
            "wind_z_ms",
            "    wind_z_ms: float = 0.0\n",
        ),
        (
            "wind_speed_kmh",
            "    wind_speed_kmh: float = 0.0\n",
        ),
    ]
    missing = [
        line
        for name, line in fields
        if re.search(
            rf"^\s*{re.escape(name)}\s*:",
            source,
            flags=re.MULTILINE,
        )
        is None
    ]

    if missing:
        marker = (
            "    track_grip_level: int = 0\n"
        )

        if marker not in source:
            raise RuntimeError(
                "Não encontrei track_grip_level "
                "em SessionData."
            )

        source = source.replace(
            marker,
            marker
            + "\n"
            + "    # Clima e condições reais da pista.\n"
            + "".join(missing),
            1,
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
        "dark_cloud=safe_float("
        not in source
    ):
        pattern = re.compile(
            r"(?P<indent>[ \\t]*)"
            r"track_grip_level="
            r"safe_int\(info\.mTrackGripLevel\),"
        )
        match = pattern.search(source)

        if match is None:
            raise RuntimeError(
                "Não encontrei track_grip_level "
                "no retorno de SessionData."
            )

        indent = match.group(
            "indent"
        )
        replacement = (
            match.group(0)
            + "\n"
            + indent
            + "dark_cloud=safe_float(\n"
            + indent
            + '    getattr(info, "mDarkCloud", 0.0)\n'
            + indent
            + "),\n"
            + indent
            + "cloud_coverage=safe_int(\n"
            + indent
            + '    getattr(info, "mCloudCoverage", 0)\n'
            + indent
            + "),\n"
            + indent
            + "min_path_wetness=safe_float(\n"
            + indent
            + '    getattr(info, "mMinPathWetness", 0.0)\n'
            + indent
            + "),\n"
            + indent
            + "avg_path_wetness=safe_float(\n"
            + indent
            + '    getattr(info, "mAvgPathWetness", 0.0)\n'
            + indent
            + "),\n"
            + indent
            + "max_path_wetness=safe_float(\n"
            + indent
            + '    getattr(info, "mMaxPathWetness", 0.0)\n'
            + indent
            + "),\n"
            + indent
            + "wind_x_ms=safe_float(\n"
            + indent
            + '    getattr(getattr(info, "mWind", None), "x", 0.0)\n'
            + indent
            + "),\n"
            + indent
            + "wind_y_ms=safe_float(\n"
            + indent
            + '    getattr(getattr(info, "mWind", None), "y", 0.0)\n'
            + indent
            + "),\n"
            + indent
            + "wind_z_ms=safe_float(\n"
            + indent
            + '    getattr(getattr(info, "mWind", None), "z", 0.0)\n'
            + indent
            + "),\n"
            + indent
            + "wind_speed_kmh=math.hypot(\n"
            + indent
            + '    safe_float(getattr(getattr(info, "mWind", None), "x", 0.0)),\n'
            + indent
            + '    safe_float(getattr(getattr(info, "mWind", None), "y", 0.0)),\n'
            + indent
            + '    safe_float(getattr(getattr(info, "mWind", None), "z", 0.0)),\n'
            + indent
            + ") * 3.6,"
        )
        source = (
            source[:match.start()]
            + replacement
            + source[match.end():]
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
        'WidgetDefinition("weather", '
        '"Weather", "Estratégia", True, False)'
    )
    new = (
        'WidgetDefinition("weather", '
        '"Weather", "Estratégia", True, True)'
    )

    if old in source:
        source = source.replace(
            old,
            new,
            1,
        )
    elif new not in source:
        raise RuntimeError(
            "Definição Weather não encontrada "
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
        "from src.widget.weather.weather_widget "
        "import WeatherWidget\n"
    )

    if import_line not in source:
        anchor = (
            "from src.widget.flags.flags_widget "
            "import FlagsWidget\n"
        )

        if anchor not in source:
            raise RuntimeError(
                "Import de FlagsWidget não encontrado."
            )

        source = source.replace(
            anchor,
            anchor + import_line,
            1,
        )

    if (
        "def create_weather("
        not in source
    ):
        anchor = (
            "    def create_widget("
            "self, widget_id: str"
            ") -> QWidget:\n"
        )
        method = (
            "    def create_weather(self) -> WeatherWidget:\n"
            "        existing = self.widgets.get(\"weather\")\n"
            "        if isinstance(existing, WeatherWidget):\n"
            "            return existing\n"
            "        config = deepcopy(\n"
            "            self.config_data[\"widgets\"][\"weather\"]\n"
            "        )\n"
            "        widget = WeatherWidget(\"weather\", config)\n"
            "        self._prepare_widget(\"weather\", widget, config)\n"
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
        '"weather": self.create_weather'
        not in source
    ):
        anchor = (
            '            "flags": self.create_flags,\n'
        )

        if anchor not in source:
            raise RuntimeError(
                "Registro de Flags não encontrado."
            )

        source = source.replace(
            anchor,
            anchor
            + '            "weather": self.create_weather,\n',
            1,
        )

    source = source.replace(
        '{"driver_panel", "delta", "flags"}',
        '{"driver_panel", "delta", "flags", "weather"}',
    )

    if (
        "weather.update_from_session(session)"
        not in source
    ):
        anchor = (
            "            "
            "flags.update_from_session(session)\n"
        )
        block = (
            anchor
            + "\n"
            '        weather = self.widgets.get("weather")\n'
            "        if weather is not None "
            "and weather.isVisible():\n"
            "            weather.update_from_session(session)\n"
        )

        if anchor not in source:
            raise RuntimeError(
                "Atualização de Flags não encontrada."
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
        "from src.widget.weather.weather_editor "
        "import WeatherEditor\n"
    )

    if import_line not in source:
        anchor = (
            "from src.widget.flags.flags_editor "
            "import FlagsEditor\n"
        )

        if anchor not in source:
            raise RuntimeError(
                "Import de FlagsEditor não encontrado."
            )

        source = source.replace(
            anchor,
            anchor + import_line,
            1,
        )

    if (
        'elif widget_id == "weather":'
        not in source
    ):
        anchor = (
            '        elif widget_id == "flags":\n'
            "            editor = FlagsEditor(\n"
            '                deepcopy(self.overlay_manager.'
            'config_data["widgets"][widget_id]), self\n'
            "            )\n"
        )
        branch = (
            anchor
            + '        elif widget_id == "weather":\n'
            "            editor = WeatherEditor(\n"
            '                deepcopy(self.overlay_manager.'
            'config_data["widgets"][widget_id]), self\n'
            "            )\n"
        )

        if anchor not in source:
            raise RuntimeError(
                "Editor de Flags não encontrado."
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
            "weather",
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

    merged = deep_merge(
        defaults,
        preserved,
    )
    data["widgets"]["weather"] = merged
    data.setdefault(
        "defaults",
        {},
    )["weather"] = deepcopy(
        defaults
    )
    data["version"] = max(
        int(
            data.get(
                "version",
                1,
            )
        ),
        17,
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
        / "src/widget/weather/weather_models.py",
        PROJECT_ROOT
        / "src/widget/weather/weather_predictor.py",
        PROJECT_ROOT
        / "src/widget/weather/weather_icons.py",
        PROJECT_ROOT
        / "src/widget/weather/weather_widget.py",
        PROJECT_ROOT
        / "src/widget/weather/weather_editor.py",
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
        / "src/widget/weather/weather_widget.py",
        PROJECT_ROOT
        / "src/widget/weather/weather_editor.py",
    ]
    missing = [
        path
        for path in required
        if not path.exists()
    ]

    if missing:
        raise FileNotFoundError(
            "Extraia o ZIP na raiz do projeto. "
            "Arquivos ausentes:\n"
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
        "Weather Widget V1 instalado."
    )
    print()
    print(
        "Teste sem LMU:"
    )
    print(
        r"python .\src\tools\test_weather_widget.py"
    )
    print()
    print(
        "Diagnóstico com LMU:"
    )
    print(
        r"python .\src\tools\diagnose_weather_lmu.py"
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
