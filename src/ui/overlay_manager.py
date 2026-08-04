from __future__ import annotations

import ctypes
import json
import sys
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget

from src.widget.delta.delta_widget import DeltaWidget
from src.widget.driver_panel.driver_panel_widget import DriverPanelWidget
from src.widget.flags.flags_widget import FlagsWidget
from src.widget.battery.battery_widget import BatteryWidget
from src.widget.tyres.tyres_widget import TyresWidget
from src.widget.weather.weather_widget import WeatherWidget
from src.widget.map.map_widget import TrackMapWidget
from src.widget.standings.standings_widget import StandingsWidget


class OverlayManager(QObject):
    config_saved = Signal(Path)
    widget_created = Signal(str, QWidget)

    # Intervalos independentes evitam redesenhar informações lentas na mesma
    # frequência da telemetria de direção (20 Hz).
    UPDATE_INTERVALS = {
        "driver_panel": 0.05,
        "delta": 0.05,
        "map": 0.05,
        "tires": 0.10,
        "battery": 0.10,
        "flags": 0.10,
        "weather": 0.50,
    }

    def __init__(self, config_path: str | Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.config_path = Path(config_path)
        self.config_data = self._load_config()
        self.widgets: dict[str, QWidget] = {}
        self.session_active = False
        self.edit_mode = False
        self._last_widget_update: dict[str, float] = {}
        # caminho de log para debug de decisões de overlay
        try:
            project_root = Path(self.config_path).resolve().parents[2]
        except Exception:
            project_root = Path.cwd()
        self._overlay_check_log = project_root / "data" / "online_debug" / "overlay_checks.log"

    def create_driver_panel(self) -> DriverPanelWidget:
        existing = self.widgets.get("driver_panel")
        if isinstance(existing, DriverPanelWidget):
            return existing
        config = deepcopy(self.config_data["widgets"]["driver_panel"])
        widget = DriverPanelWidget("driver_panel", config)
        self._prepare_widget("driver_panel", widget, config)
        return widget

    def create_delta(self) -> DeltaWidget:
        existing = self.widgets.get("delta")
        if isinstance(existing, DeltaWidget):
            return existing
        config = deepcopy(self.config_data["widgets"]["delta"])
        widget = DeltaWidget("delta", config)
        self._prepare_widget("delta", widget, config)
        return widget

    def create_flags(self) -> FlagsWidget:
        existing = self.widgets.get("flags")
        if isinstance(existing, FlagsWidget):
            return existing
        config = deepcopy(self.config_data["widgets"]["flags"])
        widget = FlagsWidget("flags", config)
        self._prepare_widget("flags", widget, config)
        return widget

    def create_weather(self) -> WeatherWidget:
        existing = self.widgets.get("weather")
        if isinstance(existing, WeatherWidget):
            return existing
        config = deepcopy(
            self.config_data["widgets"]["weather"]
        )
        widget = WeatherWidget("weather", config)
        self._prepare_widget("weather", widget, config)
        return widget

    def create_tires(self) -> TyresWidget:
        existing = self.widgets.get("tires")
        if isinstance(existing, TyresWidget):
            return existing
        config = deepcopy(
            self.config_data["widgets"]["tires"]
        )
        widget = TyresWidget("tires", config)
        self._prepare_widget("tires", widget, config)
        return widget

    def create_battery(self) -> BatteryWidget:
        existing = self.widgets.get("battery")
        if isinstance(existing, BatteryWidget):
            return existing
        config = deepcopy(
            self.config_data["widgets"]["battery"]
        )
        widget = BatteryWidget("battery", config)
        self._prepare_widget("battery", widget, config)
        return widget

    def create_map(self) -> TrackMapWidget:
        existing = self.widgets.get("map")
        if isinstance(existing, TrackMapWidget):
            return existing
        config = deepcopy(
            self.config_data["widgets"]["map"]
        )
        widget = TrackMapWidget("map", config)
        self._prepare_widget("map", widget, config)
        return widget

    def create_standings(self) -> StandingsWidget:
        existing = self.widgets.get("standings")
        if isinstance(existing, StandingsWidget):
            return existing
        config = deepcopy(self.config_data["widgets"]["standings"])
        widget = StandingsWidget("standings", config)
        self._prepare_widget("standings", widget, config)
        return widget

    def create_widget(self, widget_id: str) -> QWidget:
        creators: dict[str, Callable[[], QWidget]] = {
            "driver_panel": self.create_driver_panel,
            "delta": self.create_delta,
            "flags": self.create_flags,
            "battery": self.create_battery,
            "tires": self.create_tires,
            "weather": self.create_weather,
            "map": self.create_map,
                    "standings": self.create_standings,
}
        creator = creators.get(widget_id)
        if creator is None:
            raise KeyError(f"Widget ainda não implementado: {widget_id}")
        return creator()

    def create_enabled_widgets(self) -> None:
        for widget_id, config in self.config_data.get("widgets", {}).items():
            if bool(config.get("enabled", False)) and widget_id in {"driver_panel", "delta", "flags", "weather", "tires", "battery", "map", "standings"}:
                self.create_widget(widget_id)

    def _prepare_widget(
        self,
        widget_id: str,
        widget: QWidget,
        config: dict[str, Any],
    ) -> None:
        self._apply_window_flags(widget, config)
        screens = QGuiApplication.screens()
        if not screens:
            raise RuntimeError("Nenhum monitor detectado.")

        index = min(max(int(config.get("monitor", 0)), 0), len(screens) - 1)
        screen = screens[index]
        widget.setScreen(screen)

        if hasattr(widget, "apply_normalized_geometry"):
            widget.apply_normalized_geometry(screen.geometry())
        if hasattr(widget, "geometry_changed"):
            widget.geometry_changed.connect(self._save_widget_geometry)

        self.widgets[widget_id] = widget
        if bool(config.get("enabled", True)) and (
            self.session_active or self.edit_mode
        ):
            widget.show()
        else:
            widget.hide()
        self.widget_created.emit(widget_id, widget)

    def show_widget(self, widget_id: str) -> None:
        widget = self.widgets.get(widget_id) or self.create_widget(widget_id)
        self.config_data["widgets"][widget_id]["enabled"] = True
        if self.session_active or self.edit_mode:
            widget.show()
        else:
            widget.hide()
        self.save_config()

    def hide_widget(self, widget_id: str) -> None:
        widget = self.widgets.get(widget_id)
        if widget is not None:
            widget.hide()
        if widget_id in self.config_data.get("widgets", {}):
            self.config_data["widgets"][widget_id]["enabled"] = False
            self.save_config()

    def set_widget_enabled(self, widget_id: str, enabled: bool) -> None:
        self.show_widget(widget_id) if enabled else self.hide_widget(widget_id)

    def update_widget_config(self, widget_id: str, config: dict[str, Any]) -> None:
        self.config_data["widgets"][widget_id] = deepcopy(config)
        widget = self.widgets.get(widget_id)

        if widget is not None:
            if hasattr(widget, "update_config"):
                widget.update_config(deepcopy(config))
            self._apply_window_flags(widget, config)
            screen = widget.screen()
            if screen is not None and hasattr(widget, "apply_normalized_geometry"):
                widget.apply_normalized_geometry(screen.geometry())

        self.save_config()

    def restore_widget_default(self, widget_id: str) -> None:
        default = self.config_data.get("defaults", {}).get(widget_id)
        if default is not None:
            self.update_widget_config(widget_id, deepcopy(default))

    def update_player_data(self, player_data: Any) -> None:
        widget = self.widgets.get("driver_panel")
        if widget is not None and widget.isVisible():
            widget.update_telemetry(player_data)


        tires = self.widgets.get("tires")
        if tires is not None and tires.isVisible():
            tires.update_telemetry(player_data)
    def update_session_data(self, session: Any) -> None:
        self.set_session_active(self._session_allows_overlays(session))
        if not self.session_active:
            return

        now = time.monotonic()

        driver_panel = self.widgets.get("driver_panel")
        if (
            driver_panel is not None
            and driver_panel.isVisible()
            and getattr(session, "player", None) is not None
            and self._update_due("driver_panel", now)
        ):
            driver_panel.update_telemetry(session.player)

        tires = self.widgets.get("tires")
        if (
            tires is not None
            and tires.isVisible()
            and getattr(session, "player", None) is not None
            and self._update_due("tires", now)
        ):
            tires.update_telemetry(session.player)

        battery = self.widgets.get("battery")
        battery_config = self.config_data.get("widgets", {}).get(
            "battery", {}
        )
        if battery is not None and bool(
            battery_config.get("enabled", False)
        ) and self._update_due("battery", now):
            # Continua atualizando mesmo oculto para reaparecer ao entrar em um Hypercar.
            battery.update_from_session(session)

        delta = self.widgets.get("delta")
        if (
            delta is not None
            and delta.isVisible()
            and self._update_due("delta", now)
        ):
            delta.update_from_session(session)

        # Flags pode se ocultar automaticamente quando a pista
        # está limpa. Mesmo oculto, ele precisa continuar
        # recebendo telemetria para reaparecer sozinho.
        flags = self.widgets.get("flags")
        flags_config = self.config_data.get("widgets", {}).get(
            "flags", {}
        )
        if flags is not None and bool(
            flags_config.get("enabled", False)
        ) and self._update_due("flags", now):
            flags.update_from_session(session)

        weather = self.widgets.get("weather")
        if (
            weather is not None
            and weather.isVisible()
            and self._update_due("weather", now)
        ):
            weather.update_from_session(session)


        map_widget = self.widgets.get("map")
        map_config = self.config_data.get("widgets", {}).get(
            "map", {}
        )
        if map_widget is not None and bool(
            map_config.get("enabled", False)
        ) and self._update_due("map", now):
            # Continua aprendendo o traçado enquanto o widget está habilitado.
            map_widget.update_from_session(session)

        standings = self.widgets.get("standings")
        standings_config = self.config_data.get("widgets", {}).get(
            "standings", {}
        )
        if standings is not None and bool(
            standings_config.get("enabled", False)
        ):
            standings.update_from_session(session)
    def set_edit_mode(self, enabled: bool) -> None:
        self.edit_mode = bool(enabled)
        for widget_id, widget in self.widgets.items():
            config = self.config_data["widgets"][widget_id]
            if hasattr(widget, "set_edit_mode"):
                widget.set_edit_mode(enabled)
            click_through = bool(config.get("click_through", True)) and not enabled
            self._set_click_through(widget, click_through)

            is_enabled = bool(config.get("enabled", False))
            if is_enabled and (self.edit_mode or self.session_active):
                widget.show()
            else:
                widget.hide()

    def set_session_active(self, active: bool) -> None:
        active = bool(active)
        if active == self.session_active:
            return
        self.session_active = active
        self._last_widget_update.clear()
        for widget_id, widget in self.widgets.items():
            config = self.config_data.get("widgets", {}).get(widget_id, {})
            is_enabled = bool(config.get("enabled", False))
            if is_enabled and (self.session_active or self.edit_mode):
                widget.show()
            else:
                widget.hide()

    def _update_due(self, widget_id: str, now: float) -> bool:
        interval = self.UPDATE_INTERVALS.get(widget_id, 0.05)
        previous = self._last_widget_update.get(widget_id)
        tolerance = min(0.005, interval * 0.10)
        if (
            previous is not None
            and now - previous < interval - tolerance
        ):
            return False
        self._last_widget_update[widget_id] = now
        return True

    def _session_allows_overlays(self, session: Any) -> bool:
        if not bool(getattr(session, "connected", True)):
            self._log_overlay_decision(session, False, "not_connected")
            return False

        # A API local distingue monitor, replay, carregamento e controle do
        # carro. Ela corrige os quadros congelados de mInRealtime que o LMU
        # pode manter ao entrar/sair da garagem. Sem REST, conserva o fallback
        # da memoria compartilhada.
        try:
            api_age_s = float(getattr(session, "local_api_age_s", 99.0))
        except (TypeError, ValueError):
            api_age_s = 99.0
        api_available = bool(
            getattr(session, "local_api_available", False)
        ) and api_age_s <= 5.0
        in_control = getattr(session, "in_control_of_vehicle", None)
        in_monitor = getattr(session, "in_monitor", None)
        vehicle_loaded = getattr(session, "player_vehicle_loaded", None)
        replay_active = getattr(session, "is_replay_active", None)
        race_finished = getattr(session, "race_finished", None)
        realtime_rest = getattr(session, "in_realtime_rest", None)
        rest_state_complete = api_available and all(
            value is not None
            for value in (in_control, in_monitor, vehicle_loaded)
        )

        # Pré-calcula presença/atividade do jogador para uso em ambas
        # as ramificações (REST disponível ou não).
        drivers = list(getattr(session, "drivers", []) or [])
        player_driver = next((d for d in drivers if bool(getattr(d, "is_player", False))), None)
        player_present = bool(player_driver) or bool(getattr(session, "player_vehicle_loaded", False)) or (getattr(session, "player", None) is not None)

        def _player_active_on_track_fallback_local(s_driver, player_obj) -> bool:
            pd = s_driver
            if pd is not None:
                in_garage = bool(getattr(pd, "in_garage", False))
                in_pits = bool(getattr(pd, "in_pits", False))
                laps = int(getattr(pd, "laps", 0) or 0)
                lap_dist = float(getattr(pd, "lap_distance_m", 0.0) or 0.0)
                speed = float(getattr(pd, "speed_kmh", 0.0) or 0.0)
                if not in_garage and not in_pits:
                    return True
                if laps > 0 or lap_dist > 0.0 or speed > 0.0:
                    return True
            if player_obj is not None:
                if float(getattr(player_obj, "speed_kmh", 0.0) or 0.0) > 0.0:
                    return True
                if int(getattr(player_obj, "lap", 0) or 0) > 0:
                    return True
            return False

        player_active = _player_active_on_track_fallback_local(player_driver, getattr(session, "player", None))

        navigation_state = str(
            getattr(session, "navigation_state", "") or ""
        )
        if api_available and navigation_state in {
            "NAV_MAIN_MENU",
            "NAV_OPTIONS",
        }:
            self._log_overlay_decision(session, False, "navigation_menu")
            return False

        if rest_state_complete:
            # Determinar se o jogador está presente e/ou ativo no carro
            drivers = list(getattr(session, "drivers", []) or [])
            player_driver = next((d for d in drivers if bool(getattr(d, "is_player", False))), None)
            player_present = bool(player_driver) or bool(getattr(session, "player_vehicle_loaded", False)) or (getattr(session, "player", None) is not None)

            def _player_active_on_track() -> bool:
                pd = player_driver
                player_obj = getattr(session, "player", None)
                if pd is not None:
                    in_garage = bool(getattr(pd, "in_garage", False))
                    in_pits = bool(getattr(pd, "in_pits", False))
                    laps = int(getattr(pd, "laps", 0) or 0)
                    lap_dist = float(getattr(pd, "lap_distance_m", 0.0) or 0.0)
                    speed = float(getattr(pd, "speed_kmh", 0.0) or 0.0)
                    # Se não está na garagem nem no pit, considerar na pista
                    if not in_garage and not in_pits:
                        return True
                    # Volta válida ou movimento também conta
                    if laps > 0 or lap_dist > 0.0 or speed > 0.0:
                        return True
                if player_obj is not None:
                    if float(getattr(player_obj, "speed_kmh", 0.0) or 0.0) > 0.0:
                        return True
                    if int(getattr(player_obj, "lap", 0) or 0) > 0:
                        return True
                return False

            player_active = _player_active_on_track()

            # Regras de ocultação:
            # - ocultar se replay ativo
            # - ocultar se corrida terminou e jogador não está presente/nem ativo
            #   (exceto quando `in_control` indica que o jogador ainda controla o carro)
            # - ocultar se não há jogador presente e o veículo não está carregado
            hide_due_to_race_finished = bool(race_finished) and (not player_present and not player_active) and not bool(in_control)
            if bool(replay_active) or hide_due_to_race_finished or (not player_present and not bool(vehicle_loaded)):
                self._log_overlay_decision(session, False, "rest_state_failed", {
                    "in_control": in_control,
                    "in_monitor": in_monitor,
                    "vehicle_loaded": vehicle_loaded,
                    "replay_active": replay_active,
                    "race_finished": race_finished,
                    "player_present": player_present,
                    "player_active": player_active,
                    "in_realtime_rest": realtime_rest,
                    "api_available": api_available,
                    "api_age_s": api_age_s,
                })
                return False
        elif not bool(getattr(session, "in_realtime", False)):
            if not bool(vehicle_loaded):
                return False

        try:
            session_type = int(getattr(session, "session", -1))
        except (TypeError, ValueError):
            return False
        if not (1 <= session_type <= 8 or 10 <= session_type <= 13):
            self._log_overlay_decision(session, False, "session_type_invalid", {"session_type": session_type})
            return False

        game_phase = getattr(session, "game_phase", None)
        if game_phase is not None:
            try:
                # A fase rejeita o ultimo mInRealtime=True que o LMU pode
                # manter congelado depois que a sessao termina.
                # 0 = antes da sessao; 8 = sessao encerrada; 9 = pausado.
                gp = int(game_phase)
                if not 1 <= gp <= 7:
                    # Permitir overlays se a sessão já acabou (8/9) mas o
                    # jogador ainda está presente/ativo na pista.
                    if gp in (8, 9) and (player_present or player_active):
                        pass
                    else:
                        self._log_overlay_decision(session, False, "game_phase_out_of_range", {"game_phase": game_phase, "player_present": player_present, "player_active": player_active})
                        return False
            except (TypeError, ValueError):
                self._log_overlay_decision(session, False, "game_phase_invalid", {"game_phase": game_phase})
                return False
        # todas as checagens passaram
        self._log_overlay_decision(session, True, "allowed")
        return True

    def _log_overlay_decision(self, session: Any, allowed: bool, reason: str, extra: dict | None = None) -> None:
        try:
            self._overlay_check_log.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "ts": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                "allowed": bool(allowed),
                "reason": reason,
                "session": {
                    "connected": bool(getattr(session, "connected", False)),
                    "session": getattr(session, "session", None),
                    "game_phase": getattr(session, "game_phase", None),
                    "in_monitor": getattr(session, "in_monitor", None),
                    "player_vehicle_loaded": getattr(session, "player_vehicle_loaded", None),
                    "race_finished": getattr(session, "race_finished", None),
                    "current_time_s": getattr(session, "current_time_s", None),
                    "remaining_time_s": getattr(session, "remaining_time_s", None),
                },
            }
            if extra:
                entry["extra"] = extra
            with self._overlay_check_log.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def save_config(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(self.config_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.config_saved.emit(self.config_path)

    def close_all(self) -> None:
        for widget in self.widgets.values():
            widget.close()
        self.widgets.clear()

    def _load_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuração não encontrada: {self.config_path}")
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"JSON inválido em {self.config_path}: linha {exc.lineno}, coluna {exc.colno}"
            ) from exc

    def _save_widget_geometry(
        self,
        widget_id: str,
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> None:
        config = self.config_data["widgets"][widget_id]
        config.setdefault("position", {})
        config.setdefault("size", {})
        config["position"]["x"] = max(0.0, min(1.0, x))
        config["position"]["y"] = max(0.0, min(1.0, y))
        config["size"]["width"] = max(0.05, min(1.0, width))
        config["size"]["height"] = max(0.05, min(1.0, height))
        config["scale"] = 1.0
        self.save_config()

    def _apply_window_flags(self, widget: QWidget, config: dict[str, Any]) -> None:
        visible = widget.isVisible()
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if bool(config.get("always_on_top", True)):
            flags |= Qt.WindowType.WindowStaysOnTopHint
        widget.setWindowFlags(flags)
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        if visible:
            widget.show()
        self._set_click_through(widget, bool(config.get("click_through", True)))

    @staticmethod
    def _set_click_through(widget: QWidget, enabled: bool) -> None:
        widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, enabled)
        if sys.platform != "win32":
            return

        hwnd = int(widget.winId())
        user32 = ctypes.windll.user32
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_TOOLWINDOW = 0x00000080

        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style |= WS_EX_LAYERED | WS_EX_TOOLWINDOW
        style = style | WS_EX_TRANSPARENT if enabled else style & ~WS_EX_TRANSPARENT
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
