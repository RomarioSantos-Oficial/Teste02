from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.ui.edit_mode_manager import EditModeManager
from src.ui.main_menu_window import MainMenuWindow
from src.ui.overlay_manager import OverlayManager


def main() -> None:
    app = QApplication(sys.argv)

    config_path = PROJECT_ROOT / "src" / "config" / "widgets.json"
    overlay_manager = OverlayManager(config_path)

    menu = MainMenuWindow(
        overlay_manager=overlay_manager,
        edit_mode_manager=None,
    )

    edit_manager = EditModeManager(menu)
    menu.edit_mode_manager = edit_manager
    edit_manager.edit_mode_changed.connect(overlay_manager.set_edit_mode)

    overlay_manager.create_driver_panel()

    menu.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
