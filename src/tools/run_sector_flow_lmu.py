from __future__ import annotations

import sys
import os
import shutil
import ctypes
from ctypes import wintypes
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
FACTORY_CONFIG = PROJECT_ROOT / "src" / "config" / "widgets.json"


def user_config_path() -> Path:
    """Return a writable per-user config, seeded from factory defaults."""
    base = Path(
        os.environ.get("LOCALAPPDATA")
        or os.environ.get("APPDATA")
        or (Path.home() / "AppData" / "Local")
    )
    destination = base / "SectorFlow" / "widgets.json"
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(FACTORY_CONFIG, destination)
    return destination

# =====================================================================
# IMPORTS DO PROJETO E BIBLIOTECAS (Agora seguros para carregar)
# =====================================================================
from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from src.telemetry.lmu_adapter import LMUAdapter
from src.telemetry.session_state import SessionActivityTracker
from src.i18n import install_translator, tr
from src.ui.edit_mode_manager import EditModeManager
from src.ui.main_menu_window import MainMenuWindow
from src.ui.overlay_manager import OverlayManager


INSTANCE_SERVER_NAME = "SectorFlow_ALFA_single_instance_v1"
INSTANCE_MUTEX_NAME = "Local\\SectorFlow_ALFA_single_instance_v1"
ERROR_ALREADY_EXISTS = 183
KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
KERNEL32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
KERNEL32.CreateMutexW.restype = wintypes.HANDLE
KERNEL32.CloseHandle.argtypes = (wintypes.HANDLE,)
KERNEL32.CloseHandle.restype = wintypes.BOOL


class SingleInstanceGuard:
    """Mantem uma unica instancia e pede para a existente abrir a janela."""

    def __init__(self) -> None:
        ctypes.set_last_error(0)
        self._mutex = KERNEL32.CreateMutexW(
            None,
            False,
            INSTANCE_MUTEX_NAME,
        )
        if not self._mutex:
            raise ctypes.WinError(ctypes.get_last_error())
        self.is_primary = ctypes.get_last_error() != ERROR_ALREADY_EXISTS
        self.server = QLocalServer()
        self._show_callback = None
        if not self.is_primary:
            socket = QLocalSocket()
            socket.connectToServer(INSTANCE_SERVER_NAME)
            if socket.waitForConnected(1500):
                socket.write(b"SHOW\n")
                socket.waitForBytesWritten(1000)
                socket.disconnectFromServer()
            return

        QLocalServer.removeServer(INSTANCE_SERVER_NAME)
        self.server.listen(INSTANCE_SERVER_NAME)
        self.server.newConnection.connect(self._accept_connection)

    def set_show_callback(self, callback) -> None:
        self._show_callback = callback

    def _accept_connection(self) -> None:
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            socket.waitForReadyRead(500)
            command = bytes(socket.readAll()).strip()
            socket.disconnectFromServer()
            socket.deleteLater()
            if command == b"SHOW" and self._show_callback is not None:
                QTimer.singleShot(0, self._show_callback)

    def close(self) -> None:
        self.server.close()
        if self._mutex:
            KERNEL32.CloseHandle(self._mutex)
            self._mutex = None


class SectorFlowApplication:
    def __init__(self) -> None:
        config_path = user_config_path()
        self.overlay_manager = OverlayManager(config_path)
        self.menu = MainMenuWindow(self.overlay_manager, None)
        self.edit_manager = EditModeManager(self.menu)
        self.menu.edit_mode_manager = self.edit_manager
        self.edit_manager.edit_mode_changed.connect(self.overlay_manager.set_edit_mode)
        self.overlay_manager.create_enabled_widgets()
        self.overlays_enabled = True
        self.tray: QSystemTrayIcon | None = None
        self.tray_open_action: QAction | None = None
        self.tray_toggle_action: QAction | None = None
        self.tray_quit_action: QAction | None = None
        self._quit_requested = False
        self._closed = False
        self._create_tray()
        app = QApplication.instance()
        if app is not None:
            install_translator(app).language_changed.connect(
                self._refresh_tray_translations
            )

        self.adapter = LMUAdapter(copy_access=True)
        self.session_tracker = SessionActivityTracker()
        self.timer = QTimer(self.menu)
        self.timer.timeout.connect(self.update_lmu)
        # Memoria compartilhada e leve. Os widgets pesados conservam seus
        # limitadores individuais; o tick rapido beneficia Telemetry/volante.
        self.timer.start(16)

    def show(self) -> None:
        self.menu.show()

    def _create_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icon = QIcon(str(APPLICATION_LOGO)) if APPLICATION_LOGO.is_file() else QIcon()
        self.tray = QSystemTrayIcon(icon, self.menu)
        self.tray.setToolTip(f"SectorFlow Overley - {tr('overlays ativados')}")

        tray_menu = QMenu()
        self.tray_open_action = tray_menu.addAction(tr("Abrir SectorFlow"))
        self.tray_open_action.triggered.connect(self.show_menu)
        self.tray_toggle_action = tray_menu.addAction(tr("Desativar overlays"))
        self.tray_toggle_action.triggered.connect(self.toggle_overlays)
        tray_menu.addSeparator()
        self.tray_quit_action = tray_menu.addAction(tr("Sair"))
        self.tray_quit_action.triggered.connect(self.request_quit)

        self.tray.setContextMenu(tray_menu)
        self.tray.activated.connect(self._tray_activated)
        self.menu.tray_mode_enabled = True
        self.menu.tray_icon = self.tray
        self.tray.show()

    def show_menu(self) -> None:
        self.menu.showNormal()
        self.menu.raise_()
        self.menu.activateWindow()

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_menu()

    def toggle_overlays(self) -> None:
        self.set_overlays_enabled(not self.overlays_enabled)

    def _refresh_tray_translations(self, _language: str = "") -> None:
        if self.tray_open_action is not None:
            self.tray_open_action.setText(tr("Abrir SectorFlow"))
        if self.tray_toggle_action is not None:
            self.tray_toggle_action.setText(
                tr("Desativar overlays")
                if self.overlays_enabled
                else tr("Ativar overlays")
            )
        if self.tray_quit_action is not None:
            self.tray_quit_action.setText(tr("Sair"))
        if self.tray is not None:
            state = (
                tr("overlays ativados")
                if self.overlays_enabled
                else tr("overlays desativados")
            )
            self.tray.setToolTip(f"SectorFlow Overley - {state}")

    def request_quit(self) -> None:
        """Encerra toda a aplicacao com um unico clique na bandeja."""
        if self._quit_requested:
            return
        self._quit_requested = True

        if self.tray_quit_action is not None:
            self.tray_quit_action.setEnabled(False)
        if self.tray is not None:
            self.tray.hide()

        # A janela normalmente ignora closeEvent para permanecer na bandeja.
        # Ao sair de verdade, desative esse comportamento antes de fecha-la.
        self.menu.tray_mode_enabled = False
        self.timer.stop()
        self.menu.hide()

        app = QApplication.instance()
        if app is not None:
            QTimer.singleShot(0, app.quit)

    def set_overlays_enabled(self, enabled: bool) -> None:
        self.overlays_enabled = bool(enabled)
        if not self.overlays_enabled:
            self.overlay_manager.set_edit_mode(False)
            self.overlay_manager.set_session_active(False)
        if self.tray_toggle_action is not None:
            self.tray_toggle_action.setText(
                tr("Desativar overlays") if self.overlays_enabled else tr("Ativar overlays")
            )
        if self.tray is not None:
            state = tr("overlays ativados") if self.overlays_enabled else tr("overlays desativados")
            self.tray.setToolTip(f"SectorFlow Overley - {state}")
            self.tray.showMessage(
                "SectorFlow Overley",
                f"Overlays {state}.",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )

    def update_lmu(self) -> None:
        if not self.overlays_enabled:
            self.overlay_manager.set_session_active(False)
            self.menu.set_lmu_status(False, "overlays desativados pela bandeja")
            return
        try:
            session = self.adapter.read()
        except Exception as exc:
            self.overlay_manager.set_session_active(False)
            self.menu.set_lmu_status(False, f"{tr('erro')}: {exc}")
            return

        self.session_tracker.update(session)
        self.timer.setInterval(500 if session.telemetry_paused else 16)

        if not session.connected:
            self.overlay_manager.set_session_active(False)
            self.menu.set_lmu_status(False, session.error or "abra o jogo e entre na pista")
            return

        if session.telemetry_paused:
            self.overlay_manager.set_session_active(False)
            self.menu.set_lmu_status(False, "telemetria pausada")
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
        if self._closed:
            return
        self._closed = True
        self.timer.stop()
        self.adapter.close()
        self.overlay_manager.close_all()
        self.menu.tray_mode_enabled = False
        self.menu.close()
        if self.tray is not None:
            self.tray.hide()


def main() -> None:
    app = QApplication(sys.argv)
    install_translator(app)
    app.setQuitOnLastWindowClosed(False)
    instance_guard = SingleInstanceGuard()
    if not instance_guard.is_primary:
        return
    if APPLICATION_LOGO.is_file():
        app.setWindowIcon(QIcon(str(APPLICATION_LOGO)))
    program = SectorFlowApplication()
    instance_guard.set_show_callback(program.show_menu)
    program.show()
    app.aboutToQuit.connect(instance_guard.close)
    app.aboutToQuit.connect(program.close)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
