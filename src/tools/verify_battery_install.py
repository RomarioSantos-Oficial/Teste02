from __future__ import annotations

import json
import py_compile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    files = {
        "registry": (
            PROJECT_ROOT
            / "src"
            / "ui"
            / "widget_registry.py"
        ),
        "manager": (
            PROJECT_ROOT
            / "src"
            / "ui"
            / "overlay_manager.py"
        ),
        "menu": (
            PROJECT_ROOT
            / "src"
            / "ui"
            / "main_menu_window.py"
        ),
        "config": (
            PROJECT_ROOT
            / "src"
            / "config"
            / "widgets.json"
        ),
    }

    for path in files.values():
        if not path.exists():
            raise FileNotFoundError(path)

    registry = files["registry"].read_text(encoding="utf-8")
    manager = files["manager"].read_text(encoding="utf-8")
    menu = files["menu"].read_text(encoding="utf-8")
    config = json.loads(
        files["config"].read_text(
            encoding="utf-8",
        )
    )

    print(
        "Registro implementado:",
        'WidgetDefinition("battery", "Battery", "Carro", True, True)'
        in registry,
    )
    print(
        "create_battery:",
        "def create_battery(" in manager,
    )
    print(
        "Atualização da sessão:",
        "battery.update_from_session(session)" in manager,
    )
    print(
        "Editor no menu:",
        'widget_id == "battery"' in menu,
    )
    print(
        "Configuração Battery:",
        "battery" in config.get("widgets", {}),
    )

    for path in (
        files["registry"],
        files["manager"],
        files["menu"],
    ):
        py_compile.compile(
            str(path),
            doraise=True,
        )

    print("OK - Battery integrado e sintaxe válida.")


if __name__ == "__main__":
    main()
