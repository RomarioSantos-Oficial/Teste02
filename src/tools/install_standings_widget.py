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
    destination = path.with_name(f"{path.name}.standings_{stamp}.bak")
    shutil.copy2(path, destination)
    print(f"Backup: {destination}")


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def insert_widget_import(source: str, import_line: str, class_name: str) -> str:
    if import_line in source:
        return source
    lines = source.splitlines(keepends=True)
    indexes = [
        index
        for index, line in enumerate(lines)
        if line.startswith("from src.widget.")
    ]
    if indexes:
        lines.insert(indexes[-1] + 1, import_line)
        return "".join(lines)
    class_index = next(
        (
            index
            for index, line in enumerate(lines)
            if line.startswith(f"class {class_name}")
        ),
        None,
    )
    if class_index is None:
        raise RuntimeError(f"Não encontrei onde inserir {import_line.strip()}.")
    lines.insert(class_index, import_line + "\n")
    return "".join(lines)


def patch_registry() -> None:
    path = PROJECT_ROOT / "src" / "ui" / "widget_registry.py"
    backup(path)
    source = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r'WidgetDefinition\("standings",\s*"Standings",\s*"Corrida",\s*True,\s*(?:False|True)\)'
    )
    if not pattern.search(source):
        raise RuntimeError("Definição standings não encontrada em widget_registry.py.")
    source = pattern.sub(
        'WidgetDefinition("standings", "Standings", "Corrida", True, True)',
        source,
        count=1,
    )
    path.write_text(source, encoding="utf-8")
    print(f"Atualizado: {path}")


def patch_overlay_manager() -> None:
    path = PROJECT_ROOT / "src" / "ui" / "overlay_manager.py"
    backup(path)
    source = path.read_text(encoding="utf-8")
    source = insert_widget_import(
        source,
        "from src.widget.standings.standings_widget import StandingsWidget\n",
        "OverlayManager",
    )

    if "    def create_standings(" not in source:
        marker = "    def create_widget(self, widget_id: str) -> QWidget:\n"
        if marker not in source:
            raise RuntimeError("create_widget não encontrado em overlay_manager.py.")
        method = (
            "    def create_standings(self) -> StandingsWidget:\n"
            "        existing = self.widgets.get(\"standings\")\n"
            "        if isinstance(existing, StandingsWidget):\n"
            "            return existing\n"
            "        config = deepcopy(\n"
            "            self.config_data[\"widgets\"][\"standings\"]\n"
            "        )\n"
            "        widget = StandingsWidget(\"standings\", config)\n"
            "        self._prepare_widget(\"standings\", widget, config)\n"
            "        return widget\n\n"
        )
        source = source.replace(marker, method + marker, 1)

    if '"standings": self.create_standings' not in source:
        match = re.search(
            r"(?P<indent>\s*)creators:\s*dict\[[^\n]+\]\s*=\s*\{(?P<body>.*?)^(?P=indent)\}",
            source,
            flags=re.DOTALL | re.MULTILINE,
        )
        if match is None:
            raise RuntimeError("Dicionário creators não encontrado.")
        closing = match.end() - 1
        insertion = '            "standings": self.create_standings,\n'
        source = source[:closing] + insertion + source[closing:]

    enabled_start = source.find("    def create_enabled_widgets")
    enabled_end = source.find("    def _prepare_widget", enabled_start)
    if enabled_start < 0 or enabled_end < 0:
        raise RuntimeError("create_enabled_widgets não encontrado.")
    enabled_block = source[enabled_start:enabled_end]
    if '"standings"' not in enabled_block:
        match = re.search(
            r"widget_id\s+in\s+\{(?P<items>[^}]*)\}",
            enabled_block,
            flags=re.DOTALL,
        )
        if match is None:
            raise RuntimeError("Conjunto de widgets habilitados não encontrado.")
        items = match.group("items").rstrip()
        separator = ", " if "\n" not in items else ",\n                "
        replacement = "widget_id in {" + items + separator + '"standings"}'
        enabled_block = (
            enabled_block[: match.start()]
            + replacement
            + enabled_block[match.end() :]
        )
        source = source[:enabled_start] + enabled_block + source[enabled_end:]

    if "standings.update_from_session(session)" not in source:
        update_start = source.find("    def update_session_data")
        update_end = source.find("    def set_edit_mode", update_start)
        if update_start < 0 or update_end < 0:
            raise RuntimeError("update_session_data não encontrado.")
        block = (
            "\n"
            '        standings = self.widgets.get("standings")\n'
            "        standings_config = self.config_data.get(\"widgets\", {}).get(\n"
            '            "standings", {}\n'
            "        )\n"
            "        if standings is not None and bool(\n"
            '            standings_config.get("enabled", False)\n'
            "        ):\n"
            "            standings.update_from_session(session)\n"
        )
        source = source[:update_end] + block + source[update_end:]

    path.write_text(source, encoding="utf-8")
    print(f"Atualizado: {path}")


def patch_main_menu() -> None:
    path = PROJECT_ROOT / "src" / "ui" / "main_menu_window.py"
    backup(path)
    source = path.read_text(encoding="utf-8")
    source = insert_widget_import(
        source,
        "from src.widget.standings.standings_editor import StandingsEditor\n",
        "MainMenuWindow",
    )

    if 'widget_id == "standings"' not in source:
        lines = source.splitlines(keepends=True)
        method_start = next(
            (
                index
                for index, line in enumerate(lines)
                if re.match(r"^    def _open_editor\s*\(", line)
            ),
            None,
        )
        if method_start is None:
            raise RuntimeError("_open_editor não encontrado em main_menu_window.py.")
        method_end = len(lines)
        for index in range(method_start + 1, len(lines)):
            if re.match(r"^    def \w+\s*\(", lines[index]):
                method_end = index
                break
        else_indexes = [
            index
            for index in range(method_start + 1, method_end)
            if re.match(r"^        else:\s*$", lines[index].rstrip("\r\n"))
        ]
        if not else_indexes:
            raise RuntimeError("Else final de _open_editor não encontrado.")
        insert_at = else_indexes[-1]
        branch = [
            '        elif widget_id == "standings":\n',
            "            editor = StandingsEditor(\n",
            "                deepcopy(\n",
            '                    self.overlay_manager.config_data["widgets"][widget_id]\n',
            "                ),\n",
            "                None,\n",
            "            )\n",
        ]
        lines[insert_at:insert_at] = branch
        source = "".join(lines)

    path.write_text(source, encoding="utf-8")
    print(f"Atualizado: {path}")


def merge_config() -> None:
    path = PROJECT_ROOT / "src" / "config" / "widgets.json"
    backup(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    defaults = json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))
    current = data.setdefault("widgets", {}).get("standings", {})
    preserved = {
        key: deepcopy(current[key])
        for key in ("enabled", "monitor", "position", "size", "scale")
        if key in current
    }
    data["widgets"]["standings"] = deep_merge(defaults, preserved)
    data.setdefault("defaults", {})["standings"] = deepcopy(defaults)
    data["version"] = max(int(data.get("version", 1)), 21)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Atualizado: {path}")


def validate() -> None:
    paths = [
        PROJECT_ROOT / "src/widget/standings/standings_models.py",
        PROJECT_ROOT / "src/widget/standings/lmu_online_client.py",
        PROJECT_ROOT / "src/widget/standings/standings_logic.py",
        PROJECT_ROOT / "src/widget/standings/standings_widget.py",
        PROJECT_ROOT / "src/widget/standings/standings_editor.py",
        PROJECT_ROOT / "src/ui/widget_registry.py",
        PROJECT_ROOT / "src/ui/overlay_manager.py",
        PROJECT_ROOT / "src/ui/main_menu_window.py",
    ]
    for path in paths:
        py_compile.compile(str(path), doraise=True)
    print("Sintaxe Python validada.")


def main() -> None:
    required = [
        DEFAULTS_PATH,
        PROJECT_ROOT / "src/widget/standings/standings_widget.py",
        PROJECT_ROOT / "src/widget/standings/standings_editor.py",
    ]
    missing = [path for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Extraia o ZIP diretamente na raiz do projeto. Arquivos ausentes:\n"
            + "\n".join(str(path) for path in missing)
        )

    patch_registry()
    patch_overlay_manager()
    patch_main_menu()
    merge_config()
    validate()

    print()
    print("Standings Online V1 instalado.")
    print()
    print("Teste visual:")
    print(r"python .\src\tools\test_standings_widget.py")
    print()
    print("Diagnóstico online:")
    print(r"python .\src\tools\diagnose_standings_online.py")
    print()
    print("Executar projeto:")
    print(r"python .\src\tools\run_sector_flow_lmu.py")


if __name__ == "__main__":
    main()
