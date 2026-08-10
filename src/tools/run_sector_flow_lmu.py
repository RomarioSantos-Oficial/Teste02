from __future__ import annotations

import sys
import os
from pathlib import Path

# =====================================================================
# CONFIGURAÇÃO DE CAMINHOS (Deve vir antes de qualquer import do 'src')
# =====================================================================
# Suporte dinâmico para PyInstaller (sys._MEIPASS) vs Desenvolvimento
if getattr(sys, 'frozen', False):
    # Se estiver rodando no executável congelado pelo PyInstaller
    PROJECT_ROOT = Path(sys._MEIPASS)
else:
    # Se estiver rodando como script Python normal
    PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Adiciona a raiz do projeto no sys.path
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

APPLICATION_LOGO = PROJECT_ROOT / "images" / "logo" / "Logo.png"

# =====================================================================
# IMPORTS DO PROJETO E BIBLIOTECAS (Agora seguros para carregar)
# =====================================================================
from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from src.telemetry.lmu_adapter import LMUAdapter
from src.ui.edit_mode_manager import EditModeManager
from src.ui.main_menu_window import MainMenuWindow
from src.ui.overlay_manager import OverlayManager


class SectorFlowApplication:
    def __init__(self) -> None:
        config_path = PROJECT_ROOT / "src" / "config" / "widgets.json"
        self.overlay_manager = OverlayManager(config_path)
        self.menu = MainMenuWindow(self.overlay_manager, None)
        self.edit_manager = EditModeManager(self.menu)
        self.menu.edit_mode_manager = self.edit_manager
        self.edit_manager.edit_mode_changed.connect(self.overlay_manager.set_edit_mode)
        self.overlay_manager.create_enabled_widgets()

        self.adapter = LMUAdapter(copy_access=True)
        self.timer = QTimer(self.menu)
        self.timer.timeout.connect(self.update_lmu)
        self.timer.start(50)

    def show(self) -> None:
        self.menu.show()

    def update_lmu(self) -> None:
        try:
            session = self.adapter.read()
        except Exception as exc:
            self.overlay_manager.set_session_active(False)
            self.menu.set_lmu_status(False, f"erro: {exc}")
            return

        if not session.connected:
            self.overlay_manager.set_session_active(False)
            self.menu.set_lmu_status(False, session.error or "abra o jogo e entre na pista")
            return

        if not self.overlay_manager._session_allows_overlays(session):
            self.overlay_manager.set_session_active(False)
            phase = int(getattr(session, "game_phase", 0))
            navigation = str(
                getattr(session, "navigation_state", "") or ""
            )
            if navigation == "NAV_MAIN_MENU":
                status = "— menu do jogo"
            elif bool(getattr(session, "is_replay_active", False)):
                status = "— replay"
            elif bool(getattr(session, "in_monitor", False)):
                status = "— garagem/monitor"
            elif 1 <= phase <= 7:
                status = "— garagem/monitor"
            elif phase == 8:
                status = "— sessão encerrada/menu"
            elif phase == 9:
                status = "— jogo pausado"
            else:
                status = "— aguardando sessão"
            self.menu.set_lmu_status(True, status)
            return

        if session.player is None:
            self.overlay_manager.set_session_active(False)
            self.menu.set_lmu_status(True, "— aguardando veículo")
            return

        self.menu.set_lmu_status(
            True,
            f"— {session.track_name} — {session.player.speed_kmh:.0f} km/h",
        )
        self.overlay_manager.update_session_data(session)

    def close(self) -> None:
        self.timer.stop()
        self.adapter.close()
        self.overlay_manager.close_all()


def main() -> None:
    app = QApplication(sys.argv)
    if APPLICATION_LOGO.is_file():
        app.setWindowIcon(QIcon(str(APPLICATION_LOGO)))
    program = SectorFlowApplication()
    program.show()
    app.aboutToQuit.connect(program.close)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()