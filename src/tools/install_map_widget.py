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
    / "map_defaults.json"
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
        f"{path.name}.map_{stamp}.bak"
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
    pattern = re.compile(
        r'WidgetDefinition\('
        r'"map",\s*"Mapa",\s*"Corrida",\s*'
        r'True,\s*(?:False|True)\)'
    )

    if not pattern.search(source):
        raise RuntimeError(
            "Definição do widget map não encontrada."
        )

    source = pattern.sub(
        'WidgetDefinition("map", "Mapa", "Corrida", True, True)',
        source,
        count=1,
    )
    path.write_text(
        source,
        encoding="utf-8",
    )
    print(
        f"Atualizado: {path}"
    )


def insert_import(
    source: str,
    import_line: str,
    prefix: str,
    class_name: str,
) -> str:
    if import_line in source:
        return source

    lines = source.splitlines(
        keepends=True
    )
    indexes = [
        index
        for index, line in enumerate(lines)
        if line.startswith(prefix)
    ]

    if indexes:
        lines.insert(
            indexes[-1] + 1,
            import_line,
        )
        return "".join(lines)

    class_indexes = [
        index
        for index, line in enumerate(lines)
        if line.startswith(
            f"class {class_name}"
        )
    ]

    if not class_indexes:
        raise RuntimeError(
            f"Não encontrei onde inserir "
            f"{import_line.strip()}."
        )

    lines.insert(
        class_indexes[0],
        import_line + "\n",
    )
    return "".join(lines)


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

    source = insert_import(
        source,
        (
            "from src.widget.map.map_widget "
            "import TrackMapWidget\n"
        ),
        "from src.widget.",
        "OverlayManager",
    )

    if (
        "    def create_map(self)"
        not in source
    ):
        marker = (
            "    def create_widget("
            "self, widget_id: str"
            ") -> QWidget:\n"
        )

        if marker not in source:
            raise RuntimeError(
                "create_widget não encontrado "
                "em overlay_manager.py."
            )

        method = (
            "    def create_map(self) -> TrackMapWidget:\n"
            "        existing = self.widgets.get(\"map\")\n"
            "        if isinstance(existing, TrackMapWidget):\n"
            "            return existing\n"
            "        config = deepcopy(\n"
            "            self.config_data[\"widgets\"][\"map\"]\n"
            "        )\n"
            "        widget = TrackMapWidget(\"map\", config)\n"
            "        self._prepare_widget(\"map\", widget, config)\n"
            "        return widget\n\n"
        )
        source = source.replace(
            marker,
            method + marker,
            1,
        )

    if (
        '"map": self.create_map'
        not in source
    ):
        creators_start = source.find(
            "        creators:"
        )
        creators_end = source.find(
            "        }",
            creators_start,
        )

        if creators_start < 0 or creators_end < 0:
            raise RuntimeError(
                "Dicionário creators não encontrado."
            )

        source = (
            source[:creators_end]
            + '            "map": self.create_map,\n'
            + source[creators_end:]
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

    if '"map"' not in enabled_block:
        match = re.search(
            r"widget_id\s+in\s+\{"
            r"(?P<items>[^}]*)\}",
            enabled_block,
            flags=re.DOTALL,
        )

        if match is None:
            raise RuntimeError(
                "Conjunto de widgets habilitados "
                "não encontrado."
            )

        items = match.group(
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
            + '"map"'
            + "}"
        )
        enabled_block = (
            enabled_block[:match.start()]
            + replacement
            + enabled_block[match.end():]
        )
        source = (
            source[:enabled_start]
            + enabled_block
            + source[enabled_end:]
        )

    if (
        "map_widget.update_from_session(session)"
        not in source
    ):
        update_start = source.find(
            "    def update_session_data"
        )
        update_end = source.find(
            "    def set_edit_mode",
            update_start,
        )

        if update_start < 0 or update_end < 0:
            raise RuntimeError(
                "update_session_data não encontrado."
            )

        block = (
            "\n"
            '        map_widget = self.widgets.get("map")\n'
            "        map_config = "
            "self.config_data.get(\"widgets\", {}).get(\n"
            '            "map", {}\n'
            "        )\n"
            "        if map_widget is not None and bool(\n"
            '            map_config.get("enabled", False)\n'
            "        ):\n"
            "            # Continua aprendendo o traçado enquanto "
            "o widget está habilitado.\n"
            "            map_widget.update_from_session(session)\n"
        )
        source = (
            source[:update_end]
            + block
            + source[update_end:]
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

    source = insert_import(
        source,
        (
            "from src.widget.map.map_editor "
            "import MapEditor\n"
        ),
        "from src.widget.",
        "MainMenuWindow",
    )

    if (
        'widget_id == "map"'
        not in source
    ):
        lines = source.splitlines(
            keepends=True
        )
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
                "_open_editor não encontrado."
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
                lines[index].rstrip(
                    "\r\n"
                ),
            )
        ]

        if not else_indexes:
            raise RuntimeError(
                "Else final de _open_editor "
                "não encontrado."
            )

        insert_at = else_indexes[-1]
        branch = [
            '        elif widget_id == "map":\n',
            "            editor = MapEditor(\n",
            "                deepcopy(\n",
            '                    self.overlay_manager.config_data["widgets"][widget_id]\n',
            "                ),\n",
            "                None,\n",
            "            )\n",
        ]
        lines[
            insert_at:insert_at
        ] = branch
        source = "".join(lines)

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
            "map",
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
    data["widgets"]["map"] = (
        deep_merge(
            defaults,
            preserved,
        )
    )
    data.setdefault(
        "defaults",
        {},
    )["map"] = deepcopy(
        defaults
    )
    data["version"] = max(
        int(
            data.get(
                "version",
                1,
            )
        ),
        20,
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
        / "src/widget/map/map_models.py",
        PROJECT_ROOT
        / "src/widget/map/map_builder.py",
        PROJECT_ROOT
        / "src/widget/map/map_widget.py",
        PROJECT_ROOT
        / "src/widget/map/map_editor.py",
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
        / "src/widget/map/map_widget.py",
        PROJECT_ROOT
        / "src/widget/map/map_editor.py",
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

    patch_registry()
    patch_overlay_manager()
    patch_main_menu()
    merge_config()
    validate()

    print()
    print(
        "Track Map Widget V1 instalado."
    )
    print()
    print(
        "Teste sem LMU:"
    )
    print(
        r"python .\src\tools\test_map_widget.py"
    )
    print()
    print(
        "Diagnóstico com LMU:"
    )
    print(
        r"python .\src\tools\diagnose_map_lmu.py"
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
