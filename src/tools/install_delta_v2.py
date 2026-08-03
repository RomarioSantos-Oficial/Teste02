from __future__ import annotations

import json
import shutil
from copy import deepcopy
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "src" / "config" / "widgets.json"
DEFAULTS_PATH = PROJECT_ROOT / "src" / "config" / "delta_v2_defaults.json"


def main() -> None:
    if not DEFAULTS_PATH.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {DEFAULTS_PATH}")

    delta_defaults = json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))

    if CONFIG_PATH.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = CONFIG_PATH.with_name(f"widgets_backup_{timestamp}.json")
        shutil.copy2(CONFIG_PATH, backup)
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        print(f"Backup criado: {backup}")
    else:
        config = {"version": 1, "widgets": {}, "defaults": {}}

    config.setdefault("widgets", {})
    config.setdefault("defaults", {})

    previous = config["widgets"].get("delta", {})
    merged = deep_merge(deepcopy(delta_defaults), previous)
    config["widgets"]["delta"] = merged
    config["defaults"]["delta"] = deepcopy(delta_defaults)
    config["version"] = max(int(config.get("version", 1)), 6)

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    required = [
        PROJECT_ROOT / "src" / "widget" / "delta" / "delta_widget.py",
        PROJECT_ROOT / "src" / "widget" / "delta" / "delta_editor.py",
        PROJECT_ROOT / "src" / "ui" / "overlay_manager.py",
        PROJECT_ROOT / "src" / "ui" / "main_menu_window.py",
        PROJECT_ROOT / "src" / "tools" / "run_sector_flow_lmu.py",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Arquivos ausentes:\n" + "\n".join(missing))

    print("Delta V2 instalado e integrado.")
    print("Teste isolado:")
    print(r"python .\src\tools\test_delta_v2.py")
    print("Programa completo:")
    print(r"python .\src\tools\run_sector_flow_lmu.py")


def deep_merge(defaults: dict, existing: dict) -> dict:
    result = deepcopy(defaults)
    for key, value in existing.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


if __name__ == "__main__":
    main()
