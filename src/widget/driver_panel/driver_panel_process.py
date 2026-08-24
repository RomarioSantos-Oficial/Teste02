from __future__ import annotations

import ctypes
import json
import multiprocessing
import os
import queue
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from src.telemetry.lmu_workers import FastTelemetryWorker

from .driver_panel_widget import DriverPanelWidget


class DriverPanelProcessController:
    """Controla a Telemetry que vive em um processo Qt independente."""

    def __init__(self, config_path: str | Path) -> None:
        context = multiprocessing.get_context("spawn")
        self.config_path = Path(config_path)
        self._session_active = context.Value("b", False, lock=False)
        self._edit_mode = context.Value("b", False, lock=False)
        self._stop = context.Event()
        self._geometry = context.Queue()
        self._process = context.Process(
            target=run_driver_panel_process,
            args=(
                str(self.config_path),
                self._session_active,
                self._edit_mode,
                self._stop,
                self._geometry,
                os.getpid(),
            ),
            name="SectorFlowTelemetryUI",
            daemon=True,
        )

    def start(self) -> None:
        if not self._process.is_alive():
            self._process.start()

    def set_session_active(self, active: bool) -> None:
        self._session_active.value = bool(active)

    def set_edit_mode(self, enabled: bool) -> None:
        self._edit_mode.value = bool(enabled)

    def pending_geometry(self) -> list[tuple[str, float, float, float, float]]:
        changes: list[tuple[str, float, float, float, float]] = []
        while True:
            try:
                raw = self._geometry.get_nowait()
            except queue.Empty:
                break
            if isinstance(raw, tuple) and len(raw) == 5:
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


class _DriverPanelHost:
    def __init__(
        self,
        config_path: str | Path,
        session_active: Any,
        edit_mode: Any,
        stop: Any,
        geometry: Any,
        parent_pid: int,
    ) -> None:
        self.config_path = Path(config_path)
        self.session_active = session_active
        self.edit_mode = edit_mode
        self.stop = stop
        self.geometry = geometry
        self.parent_pid = int(parent_pid)
        self.config: dict[str, Any] = self._read_config() or {
            "enabled": False
        }
        self.widget = DriverPanelWidget(
            "driver_panel",
            deepcopy(self.config),
        )
        self.widget.geometry_changed.connect(self._publish_geometry)
        self.fast_telemetry = FastTelemetryWorker(interval_s=0.010)
        self._last_fast_sequence = -1
        self._last_edit_mode = False
        self._last_config_check = 0.0
        self._config_mtime_ns = self._mtime_ns()
        self._closed = False
        self._parent_handle = self._open_parent_handle()
        self.timer = QTimer(self.widget)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._tick)

        self._apply_config(force_geometry=True)
        self.fast_telemetry.start()
        self.timer.start(16)

    def _read_config(self) -> dict[str, Any] | None:
        try:
            root = json.loads(self.config_path.read_text(encoding="utf-8"))
            config = root.get("widgets", {}).get("driver_panel", {})
            if isinstance(config, dict):
                return deepcopy(config)
        except (OSError, json.JSONDecodeError):
            pass
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
            self.config = config
            self._apply_config(force_geometry=True)

    def _apply_config(self, *, force_geometry: bool) -> None:
        self.widget.update_config(deepcopy(self.config))
        screens = QGuiApplication.screens()
        if screens:
            index = min(
                max(int(self.config.get("monitor", 0)), 0),
                len(screens) - 1,
            )
            screen = screens[index]
            self.widget.setScreen(screen)
            if force_geometry:
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

    def _publish_geometry(
        self,
        widget_id: str,
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> None:
        try:
            self.geometry.put_nowait((widget_id, x, y, width, height))
        except (OSError, ValueError):
            pass

    def _tick(self) -> None:
        if self.stop.is_set() or not self._parent_is_alive():
            app = QApplication.instance()
            if app is not None:
                app.quit()
            return

        now = time.monotonic()
        self._reload_config_if_changed(now)
        editing = bool(self.edit_mode.value)
        if editing != self._last_edit_mode:
            self._last_edit_mode = editing
            self.widget.set_edit_mode(editing)
            self._apply_window_flags()

        enabled = bool(self.config.get("enabled", False))
        driving = bool(self.session_active.value)
        should_show = enabled and (driving or editing)
        if should_show and not self.widget.isVisible():
            self.widget.show()
        elif not should_show and self.widget.isVisible():
            self.widget.hide()

        if should_show and driving:
            frame = self.fast_telemetry.snapshot()
            if frame.sequence != self._last_fast_sequence and frame.has_player:
                self._last_fast_sequence = frame.sequence
                self.widget.update_telemetry(frame)

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
        self.fast_telemetry.close()
        self.widget.close()
        if os.name == "nt" and self._parent_handle is not None:
            ctypes.windll.kernel32.CloseHandle(self._parent_handle)
            self._parent_handle = None


def run_driver_panel_process(
    config_path: str,
    session_active: Any,
    edit_mode: Any,
    stop: Any,
    geometry: Any,
    parent_pid: int,
) -> None:
    app = QApplication([])
    app.setApplicationName("SectorFlow Telemetry")
    host = _DriverPanelHost(
        config_path,
        session_active,
        edit_mode,
        stop,
        geometry,
        parent_pid,
    )
    app.aboutToQuit.connect(host.close)
    app.exec()
    host.close()
