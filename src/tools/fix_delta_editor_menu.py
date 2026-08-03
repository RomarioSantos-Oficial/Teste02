from __future__ import annotations

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TARGET = PROJECT_ROOT / "src" / "ui" / "main_menu_window.py"

DELTA_IMPORT = "from src.widget.delta.delta_editor import DeltaEditor"
DRIVER_IMPORT = "from src.widget.driver_panel.driver_panel_editor import DriverPanelEditor"

NEW_METHOD = '    def _open_editor(self, widget_id: str) -> None:\n        if widget_id == "driver_panel":\n            config = deepcopy(\n                self.overlay_manager.config_data["widgets"]["driver_panel"]\n            )\n            editor = DriverPanelEditor(config, self)\n\n        elif widget_id == "delta":\n            config = deepcopy(\n                self.overlay_manager.config_data["widgets"]["delta"]\n            )\n            editor = DeltaEditor(config, self)\n\n        else:\n            QMessageBox.information(\n                self,\n                "Editor ainda não criado",\n                f"O editor de \'{widget_id}\' ainda não foi implementado.",\n            )\n            return\n\n        editor.config_changed.connect(\n            lambda new_config, current_id=widget_id:\n            self.overlay_manager.update_widget_config(\n                current_id,\n                new_config,\n            )\n        )\n\n        editor.restore_requested.connect(\n            lambda current_id=widget_id:\n            self.overlay_manager.restore_widget_default(\n                current_id\n            )\n        )\n\n        editor.show()\n        self.editors[widget_id] = editor\n'


def ensure_import(source: str, import_line: str) -> str:
    if import_line in source:
        return source

    lines = source.splitlines()
    last_import_index = -1

    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("from ") or stripped.startswith("import "):
            last_import_index = index

    if last_import_index >= 0:
        lines.insert(last_import_index + 1, import_line)
    else:
        lines.insert(0, import_line)

    return "\n".join(lines) + "\n"


def replace_method(source: str) -> str:
    pattern = re.compile(
        r"(?ms)^    def _open_editor\(self, widget_id: str\) -> None:\n"
        r".*?"
        r"(?=^    def |\Z)"
    )

    if not pattern.search(source):
        raise RuntimeError(
            "Nao encontrei o metodo _open_editor dentro de MainMenuWindow."
        )

    return pattern.sub(NEW_METHOD.rstrip() + "\n\n", source, count=1)


def main() -> None:
    if not TARGET.exists():
        raise FileNotFoundError(f"Arquivo nao encontrado: {TARGET}")

    source = TARGET.read_text(encoding="utf-8")

    backup = TARGET.with_suffix(".py.bak")
    backup.write_text(source, encoding="utf-8")

    source = ensure_import(source, DRIVER_IMPORT)
    source = ensure_import(source, DELTA_IMPORT)
    source = replace_method(source)

    TARGET.write_text(source, encoding="utf-8")

    print("OK - DeltaEditor integrado ao menu.")
    print("Backup criado em:")
    print(backup)
    print()
    print("Agora execute:")
    print(r"python .\src\tools\run_sector_flow_lmu.py")


if __name__ == "__main__":
    main()
