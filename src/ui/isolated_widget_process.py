from __future__ import annotations

import ctypes
import json
import multiprocessing
import os
import pickle
import queue
import threading
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QWidget

from src.widget.standings.standings_assets import (
    hydrate_session_driver_countries,
)


SESSION_BUFFER_SIZE = 1024 * 1024
AUTO_HIDE_WIDGETS = {"flags", "radar"}


class SharedSessionBus:
    """Publica um unico SessionData para todos os processos isolados."""

    def __init__(self) -> None:
        context = multiprocessing.get_context("spawn")
        self.buffer = context.RawArray("B", SESSION_BUFFER_SIZE)
        self.length = context.RawValue("I", 0)
        self.sequence = context.RawValue("Q", 0)
        self.lock = context.Lock()

    def publish(self, sequence: int, session: Any) -> bool:
        payload = pickle.dumps(session, protocol=pickle.HIGHEST_PROTOCOL)
        if len(payload) > SESSION_BUFFER_SIZE:
            return False
        with self.lock:
            target = memoryview(self.buffer).cast("B")
            target[: len(payload)] = payload
            self.length.value = len(payload)
            self.sequence.value = max(0, int(sequence))
        return True


class SessionBusPublisher:
    """Copia o snapshot pronto e inclui metadados destinados a outros processos."""

    def __init__(self, source: Any, bus: SharedSessionBus) -> None:
        self.source = source
        self.bus = bus
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="SectorFlowSessionBus",
            daemon=True,
        )
        self._thread.start()

    def _run(self) -> None:
        last_sequence = -1
        while not self._stop.wait(0.010):
            sequence, session = self.source.snapshot()
            if sequence == last_sequence:
                continue
            # O Standings descobre países pela API online no processo
            # principal. Colocar o resultado no próprio SessionData faz a
            # informação atravessar o pickle usado por Delta/Mapa/etc.
            hydrate_session_driver_countries(session)
            if self.bus.publish(sequence, session):
                last_sequence = sequence

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._thread = None


class IsolatedWidgetProcessController:
    def __init__(
        self,
        config_path: str | Path,
        widget_id: str,
        bus: SharedSessionBus,
        update_interval_s: float,
    ) -> None:
        context = multiprocessing.get_context("spawn")
        self.widget_id = str(widget_id)
        self._session_active = context.Value("b", False, lock=False)
        self._edit_mode = context.Value("b", False, lock=False)
        self._stop = context.Event()
        self._geometry = context.Queue()
        self._process = context.Process(
            target=run_isolated_widget_process,
            args=(
                str(config_path),
                self.widget_id,
                max(0.016, float(update_interval_s)),
                bus.buffer,
                bus.length,
                bus.sequence,
                bus.lock,
                self._session_active,
                self._edit_mode,
                self._stop,
                self._geometry,
                os.getpid(),
            ),
            name=f"SectorFlow-{self.widget_id}-UI",
            daemon=True,
        )

    def start(self) -> None:
        if not self._process.is_alive():
            self._process.start()

    def set_session_active(self, active: bool) -> None:
        self._session_active.value = bool(active)

    def set_edit_mode(self, enabled: bool) -> None:
        self._edit_mode.value = bool(enabled)

    def pending_geometry(self) -> list[tuple[Any, ...]]:
        changes: list[tuple[Any, ...]] = []
        while True:
            try:
                raw = self._geometry.get_nowait()
            except queue.Empty:
                break
            if isinstance(raw, tuple) and len(raw) in {5, 6}:
                changes.append(raw)
        return changes

    def close(self) -> None:
        self._stop.set()
        if self._process.is_alive():
            self._process.join(timeout=2.0)
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=1.0)
        self._geometry.close()
        self._geometry.join_thread()


def _create_widget(widget_id: str, config: dict[str, Any]) -> QWidget:
    if widget_id == "delta":
        from src.widget.delta.delta_widget import DeltaWidget

        return DeltaWidget(widget_id, config)
    if widget_id == "map":
        from src.widget.map.map_widget import TrackMapWidget

        return TrackMapWidget(widget_id, config)
    if widget_id == "lap_timer":
        from src.widget.lap_timer.lap_timer_widget import LapTimerWidget

        return LapTimerWidget(widget_id, config)
    if widget_id == "tires":
        from src.widget.tyres.tyres_widget import TyresWidget

        return TyresWidget(widget_id, config)
    if widget_id == "radar":
        from src.widget.radar.radar_widget import RadarWidget

        return RadarWidget(widget_id, config)
    if widget_id == "flags":
        from src.widget.flags.flags_widget import FlagsWidget

        return FlagsWidget(widget_id, config)
    raise KeyError(f"Widget nao suportado em processo isolado: {widget_id}")


class _IsolatedWidgetHost:
    def __init__(
        self,
        config_path: str,
        widget_id: str,
        update_interval_s: float,
        session_buffer: Any,
        session_length: Any,
        session_sequence: Any,
        session_lock: Any,
        session_active: Any,
        edit_mode: Any,
        stop: Any,
        geometry: Any,
        parent_pid: int,
    ) -> None:
        self.config_path = Path(config_path)
        self.widget_id = widget_id
        self.update_interval_s = update_interval_s
        self.session_buffer = session_buffer
        self.session_length = session_length
        self.session_sequence = session_sequence
        self.session_lock = session_lock
        self.session_active = session_active
        self.edit_mode = edit_mode
        self.stop = stop
        self.geometry = geometry
        self.parent_pid = int(parent_pid)
        self.config = self._read_config() or {"enabled": False}
        self.widget = _create_widget(widget_id, deepcopy(self.config))
        self.widget.geometry_changed.connect(self._publish_geometry)
        self._last_sequence = -1
        self._pending_session: Any | None = None
        self._last_data_update = 0.0
        self._last_edit_mode = False
        self._last_driving = False
        self._last_config_check = 0.0
        self._config_mtime_ns = self._mtime_ns()
        self._closed = False
        self._parent_handle = self._open_parent_handle()
        self.timer = QTimer(self.widget)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._tick)
        self._apply_config(force_geometry=True)
        self.timer.start(16)

    def _read_config(self) -> dict[str, Any] | None:
        try:
            root = json.loads(self.config_path.read_text(encoding="utf-8"))
            config = root.get("widgets", {}).get(self.widget_id, {})
            return deepcopy(config) if isinstance(config, dict) else None
        except (OSError, json.JSONDecodeError):
            return None

    def _mtime_ns(self) -> int:
        try:
            return self.config_path.stat().st_mtime_ns
        except OSError:
            return 0

    def _reload_config_if_changed(self, now: float) -> None:
        if now - self._last_config_check < 0.25:
            return
        self._last_config_check = now
        modified = self._mtime_ns()
        if modified == self._config_mtime_ns:
            return
        config = self._read_config()
        if config is None:
            return
        self._config_mtime_ns = modified
        if config != self.config:
            geometry_keys = ("position", "size", "scale", "monitor")
            geometry_changed = any(
                config.get(key) != self.config.get(key) for key in geometry_keys
            )
            self.config = config
            self._apply_config(force_geometry=geometry_changed)

    def _apply_config(self, *, force_geometry: bool) -> None:
        if hasattr(self.widget, "update_config"):
            self.widget.update_config(deepcopy(self.config))
        screens = QGuiApplication.screens()
        if screens:
            index = min(
                max(int(self.config.get("monitor", 0)), 0),
                len(screens) - 1,
            )
            screen = screens[index]
            self.widget.setScreen(screen)
            if force_geometry and hasattr(self.widget, "apply_normalized_geometry"):
                self.widget.apply_normalized_geometry(screen.geometry())
        self._apply_window_flags()

    def _apply_window_flags(self) -> None:
        visible = self.widget.isVisible()
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if bool(self.config.get("always_on_top", True)):
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.widget.setWindowFlags(flags)
        self.widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        click_through = bool(self.config.get("click_through", True)) and not bool(
            self.edit_mode.value
        )
        self._set_click_through(click_through)
        if visible:
            self.widget.show()

    def _set_click_through(self, enabled: bool) -> None:
        self.widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, enabled)
        if os.name != "nt":
            return
        hwnd = int(self.widget.winId())
        user32 = ctypes.windll.user32
        style = user32.GetWindowLongW(hwnd, -20)
        style |= 0x00080000 | 0x00000080
        style = style | 0x00000020 if enabled else style & ~0x00000020
        user32.SetWindowLongW(hwnd, -20, style)

    def _read_latest_session(self) -> None:
        with self.session_lock:
            sequence = int(self.session_sequence.value)
            if sequence == self._last_sequence or sequence <= 0:
                return
            length = int(self.session_length.value)
            payload = bytes(memoryview(self.session_buffer).cast("B")[:length])
        try:
            session = pickle.loads(payload)
        except (pickle.PickleError, EOFError, AttributeError, TypeError, ValueError):
            return
        self._last_sequence = sequence
        self._pending_session = session

    def _apply_pending_session(self, now: float) -> None:
        if self._pending_session is None:
            return
        if now - self._last_data_update < self.update_interval_s:
            return
        session = self._pending_session
        self._pending_session = None
        self._last_data_update = now
        if self.widget_id == "tires":
            self.widget.update_telemetry(getattr(session, "player", None))
        else:
            self.widget.update_from_session(session)

    def _tick(self) -> None:
        if self.stop.is_set() or not self._parent_is_alive():
            app = QApplication.instance()
            if app is not None:
                app.quit()
            return

        now = time.monotonic()
        self._reload_config_if_changed(now)
        editing = bool(self.edit_mode.value)
        driving = bool(self.session_active.value)
        enabled = bool(self.config.get("enabled", False))

        if editing != self._last_edit_mode:
            self._last_edit_mode = editing
            if hasattr(self.widget, "set_edit_mode"):
                self.widget.set_edit_mode(editing)
            self._apply_window_flags()

        if not enabled or not (driving or editing):
            if self.widget.isVisible():
                self.widget.hide()
        elif editing or self.widget_id not in AUTO_HIDE_WIDGETS:
            if not self.widget.isVisible():
                self.widget.show()

        if driving and enabled:
            self._read_latest_session()
            self._apply_pending_session(now)

        self._last_driving = driving

    def _publish_geometry(
        self,
        widget_id: str,
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> None:
        try:
            profile_id = ""
            try:
                root = json.loads(self.config_path.read_text(encoding="utf-8"))
                profile_id = str(root.get("active_profile", "") or "")
            except (OSError, json.JSONDecodeError):
                pass
            self.geometry.put_nowait(
                (widget_id, x, y, width, height, profile_id)
            )
        except (OSError, ValueError):
            pass

    def _open_parent_handle(self):
        if os.name != "nt":
            return None
        handle = ctypes.windll.kernel32.OpenProcess(
            0x00100000,
            False,
            self.parent_pid,
        )
        return handle or None

    def _parent_is_alive(self) -> bool:
        if os.name != "nt" or self._parent_handle is None:
            return True
        return ctypes.windll.kernel32.WaitForSingleObject(
            self._parent_handle,
            0,
        ) == 0x00000102

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.timer.stop()
        self.widget.close()
        if os.name == "nt" and self._parent_handle is not None:
            ctypes.windll.kernel32.CloseHandle(self._parent_handle)
            self._parent_handle = None


def run_isolated_widget_process(
    config_path: str,
    widget_id: str,
    update_interval_s: float,
    session_buffer: Any,
    session_length: Any,
    session_sequence: Any,
    session_lock: Any,
    session_active: Any,
    edit_mode: Any,
    stop: Any,
    geometry: Any,
    parent_pid: int,
) -> None:
    app = QApplication([])
    app.setApplicationName(f"SectorFlow {widget_id}")
    app.setQuitOnLastWindowClosed(False)
    host = _IsolatedWidgetHost(
        config_path,
        widget_id,
        update_interval_s,
        session_buffer,
        session_length,
        session_sequence,
        session_lock,
        session_active,
        edit_mode,
        stop,
        geometry,
        parent_pid,
    )
    app.aboutToQuit.connect(host.close)
    app.exec()
    host.close()
