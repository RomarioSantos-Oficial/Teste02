# SectorFlow is an open-source overlay application for racing simulation.
# Copyright (C) 2022-2026 SectorFlow developers
# Based on the user-provided Standings Hybrid reference.
#
# This file is part of SectorFlow.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.


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
DEFAULTS_PATH = PROJECT_ROOT / "src" / "config" / "standings_defaults.json"


def backup(path: Path) -> None:
    if not path.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = path.with_name(f"{path.name}.standings_v2_{stamp}.bak")
    shutil.copy2(path, target)
    print(f"Backup: {target}")


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def insert_import(source: str, import_line: str, class_name: str) -> str:
    source = re.sub(
        r"^from src\.widget\.standings\.[^\n]+\n",
        "",
        source,
        flags=re.MULTILINE,
    )
    lines = source.splitlines(keepends=True)
    indexes = [index for index, line in enumerate(lines) if line.startswith("from src.widget.")]
    if indexes:
        lines.insert(indexes[-1] + 1, import_line)
    else:
        class_index = next((index for index, line in enumerate(lines) if line.startswith(f"class {class_name}")), None)
        if class_index is None:
            raise RuntimeError(f"Não encontrei onde inserir {import_line.strip()}.")
        lines.insert(class_index, import_line + "\n")
    return "".join(lines)


def patch_registry() -> None:
    path = PROJECT_ROOT / "src" / "ui" / "widget_registry.py"
    backup(path)
    source = path.read_text(encoding="utf-8")
    pattern = re.compile(r'WidgetDefinition\("standings",\s*"Standings",\s*"Corrida",\s*True,\s*(?:False|True)\)')
    if not pattern.search(source):
        raise RuntimeError("Definição standings não encontrada em widget_registry.py.")
    source = pattern.sub('WidgetDefinition("standings", "Standings", "Corrida", True, True)', source, count=1)
    path.write_text(source, encoding="utf-8")
    print(f"Atualizado: {path}")


def patch_overlay_manager() -> None:
    path = PROJECT_ROOT / "src" / "ui" / "overlay_manager.py"
    backup(path)
    source = path.read_text(encoding="utf-8")
    source = insert_import(source, "from src.widget.standings.standings_widget import StandingsWidget\n", "OverlayManager")
    method_pattern = re.compile(r"^    def create_standings\(self\).*?(?=^    def \w+\()", re.MULTILINE | re.DOTALL)
    method = (
        "    def create_standings(self) -> StandingsWidget:\n"
        "        existing = self.widgets.get(\"standings\")\n"
        "        if isinstance(existing, StandingsWidget):\n"
        "            return existing\n"
        "        config = deepcopy(self.config_data[\"widgets\"][\"standings\"])\n"
        "        widget = StandingsWidget(\"standings\", config)\n"
        "        self._prepare_widget(\"standings\", widget, config)\n"
        "        return widget\n\n"
    )
    if method_pattern.search(source):
        source = method_pattern.sub(method, source, count=1)
    else:
        marker = re.search(r"^    def create_widget\(", source, re.MULTILINE)
        if marker is None:
            raise RuntimeError("create_widget não encontrado.")
        source = source[:marker.start()] + method + source[marker.start():]
    if '"standings": self.create_standings' not in source:
        start = source.find("        creators:")
        close = source.find("\n        }", start)
        if start < 0 or close < 0:
            raise RuntimeError("Dicionário creators não encontrado.")
        source = source[:close] + '\n            "standings": self.create_standings,' + source[close:]
    enabled_start = source.find("    def create_enabled_widgets")
    enabled_end = source.find("    def _prepare_widget", enabled_start)
    if enabled_start < 0 or enabled_end < 0:
        raise RuntimeError("create_enabled_widgets não encontrado.")
    block = source[enabled_start:enabled_end]
    if '"standings"' not in block:
        match = re.search(r"widget_id\s+in\s+\{(?P<items>[^}]*)\}", block, re.DOTALL)
        if match is None:
            raise RuntimeError("Conjunto de widgets habilitados não encontrado.")
        items = match.group("items").rstrip()
        separator = ", " if "\n" not in items else ",\n                "
        replacement = "widget_id in {" + items + separator + '"standings"}'
        block = block[:match.start()] + replacement + block[match.end():]
        source = source[:enabled_start] + block + source[enabled_end:]
    if "standings.update_from_session(session)" not in source:
        update_start = source.find("    def update_session_data")
        update_end = source.find("    def set_edit_mode", update_start)
        if update_start < 0 or update_end < 0:
            raise RuntimeError("update_session_data não encontrado.")
        addition = (
            "\n        standings = self.widgets.get(\"standings\")\n"
            "        standings_config = self.config_data.get(\"widgets\", {}).get(\"standings\", {})\n"
            "        if standings is not None and bool(standings_config.get(\"enabled\", False)):\n"
            "            standings.update_from_session(session)\n"
        )
        source = source[:update_end] + addition + source[update_end:]
    path.write_text(source, encoding="utf-8")
    print(f"Atualizado: {path}")


def patch_main_menu() -> None:
    path = PROJECT_ROOT / "src" / "ui" / "main_menu_window.py"
    backup(path)
    source = path.read_text(encoding="utf-8")
    source = insert_import(source, "from src.widget.standings.standings_editor import StandingsEditor\n", "MainMenuWindow")
    if 'widget_id == "standings"' not in source:
        lines = source.splitlines(keepends=True)
        start = next((i for i, line in enumerate(lines) if re.match(r"^    def _open_editor\s*\(", line)), None)
        if start is None:
            raise RuntimeError("_open_editor não encontrado.")
        end = next((i for i in range(start + 1, len(lines)) if re.match(r"^    def \w+\s*\(", lines[i])), len(lines))
        final_else = [i for i in range(start + 1, end) if re.match(r"^        else:\s*$", lines[i].rstrip("\r\n"))]
        if not final_else:
            raise RuntimeError("Else final de _open_editor não encontrado.")
        index = final_else[-1]
        lines[index:index] = [
            '        elif widget_id == "standings":\n',
            '            editor = StandingsEditor(\n',
            '                deepcopy(self.overlay_manager.config_data["widgets"][widget_id]), None\n',
            '            )\n',
        ]
        source = "".join(lines)
    path.write_text(source, encoding="utf-8")
    print(f"Atualizado: {path}")


def merge_config() -> None:
    path = PROJECT_ROOT / "src" / "config" / "widgets.json"
    backup(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    defaults = json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))
    current = data.setdefault("widgets", {}).get("standings", {})
    preserved = {key: deepcopy(current[key]) for key in ("enabled", "monitor", "position", "size", "scale") if key in current}
    data["widgets"]["standings"] = deep_merge(defaults, preserved)
    data.setdefault("defaults", {})["standings"] = deepcopy(defaults)
    data["version"] = max(int(data.get("version", 1)), 22)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Atualizado: {path}")


def validate() -> None:
    files = list((PROJECT_ROOT / "src" / "widget" / "standings").glob("*.py")) + [
        PROJECT_ROOT / "src" / "ui" / "widget_registry.py",
        PROJECT_ROOT / "src" / "ui" / "overlay_manager.py",
        PROJECT_ROOT / "src" / "ui" / "main_menu_window.py",
    ]
    for file in files:
        py_compile.compile(str(file), doraise=True)
    json.loads((PROJECT_ROOT / "src" / "config" / "widgets.json").read_text(encoding="utf-8"))
    print("Sintaxe Python e JSON validados.")


def main() -> None:
    required = [
        DEFAULTS_PATH,
        PROJECT_ROOT / "src" / "widget" / "standings" / "standings_widget.py",
        PROJECT_ROOT / "src" / "widget" / "standings" / "standings_editor.py",
    ]
    missing = [path for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Extraia o ZIP diretamente na raiz do projeto. Arquivos ausentes:\n" + "\n".join(str(path) for path in missing))
    patch_registry()
    patch_overlay_manager()
    patch_main_menu()
    merge_config()
    validate()
    print()
    print("Standings Hybrid Classic V2 instalado.")
    print(r"Teste: python .\src\tools\test_standings_hybrid_v2.py")
    print(r"Diagnóstico: python .\src\tools\diagnose_standings_hybrid_v2.py")
    print(r"Programa: python .\src\tools\run_sector_flow_lmu.py")


if __name__ == "__main__":
    main()
