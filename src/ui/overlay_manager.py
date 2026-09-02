from __future__ import annotations

import ctypes
import json
import re
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
from src.widget.damage.damage_widget import DamageWidget
from src.widget.relative.relative_widget import RelativeWidget
from src.widget.tyres.tyres_widget import TyresWidget
from src.widget.weather.weather_widget import WeatherWidget
from src.widget.map.map_widget import TrackMapWidget
from src.widget.standings.delta_history_store import DeltaHistoryStore
from src.widget.standings.standings_widget import StandingsWidget
from src.widget.standings.lmu_online_client import LMUOnlineIdentityClient
from src.widget.standings.standings_online import LocalStandingsEnrichment
from src.widget.fuel_time.fuel_time_widget import FuelTimeWidget
from src.widget.lap_timer.lap_timer_widget import LapTimerWidget
from src.widget.url.url_server_widget import UrlServerWidget
from src.widget.radar.radar_widget import RadarWidget


class OverlayManager(QObject):
    config_saved = Signal(Path)
    widget_created = Signal(str, QWidget)
    profile_changed = Signal(str)
    session_active_changed = Signal(bool)

    # Intervalos independentes evitam redesenhar informações lentas na mesma
    # frequência da telemetria de direção (20 Hz).
    UPDATE_INTERVALS = {
        # O loop principal usa 16 ms. Um limite de 1/60 (16,67 ms) fazia
        # alternar os ticks e reduzia a Telemetry para cerca de 31 FPS.
        "driver_panel": 0.0,
        "delta": 0.05,
        "map": 0.05,
        "tires": 0.10,
        "battery": 0.10,
        "damage": 0.10,
        "fuel_time": 0.10,
        "lap_timer": 0.10,
        "relative": 0.10,
        "radar": 0.05,
        "flags": 0.10,
        "weather": 0.50,
        "standings": 0.10,
    }

    def __init__(
        self,
        config_path: str | Path,
        parent: QObject | None = None,
        *,
        external_driver_panel: bool = False,
        external_widget_ids: set[str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.config_path = Path(config_path)
        self.external_widget_ids = set(external_widget_ids or ())
        if external_driver_panel:
            self.external_widget_ids.add("driver_panel")
        # Mantido para compatibilidade com chamadas e testes anteriores.
        self.external_driver_panel = "driver_panel" in self.external_widget_ids
        self.config_data = self._load_config()
        self._ensure_profiles()
        self._delta_history_path = (
            self.config_path.parent
            / "session_cache"
            / "standings_delta_history.json"
        )
        standings_config = self.config_data.get("widgets", {}).get(
            "standings", {}
        )
        if not (
            bool(standings_config.get("enabled", False))
            and bool(standings_config.get("show_delta", False))
        ):
            DeltaHistoryStore(self._delta_history_path).delete()
        self.widgets: dict[str, QWidget] = {}
        self.session_active = False
        self.edit_mode = False
        self._last_widget_update: dict[str, float] = {}
        self._shared_standings_enrichment: LocalStandingsEnrichment | None = None
        self._shared_online_client: LMUOnlineIdentityClient | None = None
        self._split_session_key: tuple[str, str] | None = None
        self._last_split_label = ""
        self._split_server_active = False
        self._split_recheck_authoritative = False
        # O log temporário acompanha a raiz empacotada e é removido ao sair.
        project_root = Path(__file__).resolve().parents[2]
        self._overlay_check_log = project_root / "data" / "online_debug" / "overlay_checks.log"

    @property
    def active_profile_id(self) -> str:
        return str(self.config_data.get("active_profile", "standard"))

    def profile_items(self) -> list[tuple[str, str]]:
        profiles = self.config_data.get("profiles", {})
        return [
            (profile_id, str(profile.get("name", profile_id)))
            for profile_id, profile in profiles.items()
            if isinstance(profile, dict)
        ]

    def active_profile_mode(self) -> str:
        profile = self.config_data.get("profiles", {}).get(
            self.active_profile_id, {}
        )
        return str(profile.get("mode", "standard"))

    def create_profile(self, name: str, mode: str = "standard") -> str:
        cleaned = " ".join(str(name or "").split()).strip()
        if not cleaned:
            raise ValueError("Informe um nome para o perfil.")
        base = re.sub(r"[^a-z0-9]+", "_", cleaned.casefold()).strip("_") or "perfil"
        profile_id = base
        suffix = 2
        profiles = self.config_data.setdefault("profiles", {})
        while profile_id in profiles:
            profile_id = f"{base}_{suffix}"
            suffix += 1
        self._sync_active_profile()
        profiles[profile_id] = {
            "name": cleaned,
            "mode": "engineer" if mode == "engineer" else "standard",
            "widgets": deepcopy(self.config_data.get("widgets", {})),
        }
        self.save_config()
        return profile_id

    def rename_profile(self, profile_id: str, name: str) -> None:
        profiles = self.config_data.get("profiles", {})
        profile = profiles.get(profile_id)
        if not isinstance(profile, dict):
            raise KeyError("Perfil não encontrado.")
        cleaned = " ".join(str(name or "").split()).strip()
        if not cleaned:
            raise ValueError("Informe um nome para o perfil.")
        profile["name"] = cleaned
        self.save_config()
        self.profile_changed.emit(self.active_profile_id)

    def delete_profile(self, profile_id: str) -> None:
        if profile_id in {"standard", "engineer"}:
            raise ValueError("Os perfis Padrão e Engenheiro não podem ser excluídos.")
        profiles = self.config_data.get("profiles", {})
        if profile_id not in profiles:
            raise KeyError("Perfil não encontrado.")
        was_active = profile_id == self.active_profile_id
        if was_active:
            self.switch_profile("standard")
            profiles = self.config_data.get("profiles", {})
        profiles.pop(profile_id, None)
        self.save_config()
        self.profile_changed.emit(self.active_profile_id)

    def switch_profile(self, profile_id: str) -> None:
        profiles = self.config_data.get("profiles", {})
        if profile_id not in profiles or profile_id == self.active_profile_id:
            return
        self._sync_active_profile()
        self.close_all()
        self.config_data["active_profile"] = profile_id
        self.config_data["widgets"] = deepcopy(profiles[profile_id]["widgets"])
        self._last_widget_update.clear()
        self.create_enabled_widgets()
        self.save_config()
        self.profile_changed.emit(profile_id)

    def _ensure_profiles(self) -> None:
        widgets = deepcopy(self.config_data.setdefault("widgets", {}))
        profiles = self.config_data.setdefault("profiles", {})
        profiles.setdefault("standard", {
            "name": "Padrão", "mode": "standard", "widgets": deepcopy(widgets)
        })
        profiles.setdefault("engineer", {
            "name": "Engenheiro", "mode": "engineer", "widgets": deepcopy(widgets)
        })
        # Migra perfis antigos quando um novo widget padrão é adicionado.
        # Sem isso, o perfil salvo substitui `widgets` e perde a configuração
        # recém-injetada (como ocorreu com Telemetry/Driver Panel).
        for profile in profiles.values():
            if not isinstance(profile, dict):
                continue
            profile_widgets = profile.setdefault("widgets", {})
            for widget_id, config in widgets.items():
                profile_widgets.setdefault(widget_id, deepcopy(config))
        active = str(self.config_data.get("active_profile", "standard"))
        if active not in profiles:
            active = "standard"
        self.config_data["active_profile"] = active
        self.config_data["widgets"] = deepcopy(profiles[active].get("widgets", widgets))

    def _sync_active_profile(self) -> None:
        profiles = self.config_data.setdefault("profiles", {})
        profile = profiles.get(self.active_profile_id)
        if isinstance(profile, dict):
            profile["widgets"] = deepcopy(self.config_data.get("widgets", {}))

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

    def create_damage(self) -> DamageWidget:
        existing = self.widgets.get("damage")
        if isinstance(existing, DamageWidget):
            return existing
        config = deepcopy(self.config_data["widgets"]["damage"])
        widget = DamageWidget("damage", config)
        self._prepare_widget("damage", widget, config)
        return widget

    def create_fuel_time(self) -> FuelTimeWidget:
        existing = self.widgets.get("fuel_time")
        if isinstance(existing, FuelTimeWidget): return existing
        config = deepcopy(self.config_data["widgets"]["fuel_time"])
        widget = FuelTimeWidget("fuel_time", config)
        self._prepare_widget("fuel_time", widget, config)
        return widget

    def create_lap_timer(self) -> LapTimerWidget:
        existing = self.widgets.get("lap_timer")
        if isinstance(existing, LapTimerWidget):
            return existing
        config = deepcopy(self.config_data["widgets"]["lap_timer"])
        widget = LapTimerWidget("lap_timer", config)
        self._prepare_widget("lap_timer", widget, config)
        return widget

    def create_url(self) -> UrlServerWidget:
        existing = self.widgets.get("url")
        if isinstance(existing, UrlServerWidget): return existing
        config = deepcopy(self.config_data["widgets"]["url"])
        widget = UrlServerWidget("url", config)
        self._prepare_widget("url", widget, config)
        self._configure_url_sources()
        widget.set_output_active(self.session_active or self.edit_mode)
        return widget

    def create_relative(self) -> RelativeWidget:
        existing = self.widgets.get("relative")
        if isinstance(existing, RelativeWidget):
            return existing
        config = deepcopy(self.config_data["widgets"]["relative"])
        enrichment, online = self._standings_services(config)
        widget = RelativeWidget(
            "relative",
            config,
            shared_enrichment=enrichment,
            shared_online_client=online,
        )
        self._prepare_widget("relative", widget, config)
        return widget

    def create_radar(self) -> RadarWidget:
        existing = self.widgets.get("radar")
        if isinstance(existing, RadarWidget):
            return existing
        config = deepcopy(self.config_data["widgets"]["radar"])
        widget = RadarWidget("radar", config)
        self._prepare_widget("radar", widget, config)
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
        config["_delta_history_path"] = str(self._delta_history_path)
        enrichment, online = self._standings_services(config)
        widget = StandingsWidget(
            "standings",
            config,
            shared_enrichment=enrichment,
            shared_online_client=online,
        )
        self._prepare_widget("standings", widget, config)
        return widget

    def create_widget(self, widget_id: str) -> QWidget:
        creators: dict[str, Callable[[], QWidget]] = {
            "driver_panel": self.create_driver_panel,
            "delta": self.create_delta,
            "flags": self.create_flags,
            "battery": self.create_battery,
            "damage": self.create_damage,
            "fuel_time": self.create_fuel_time,
            "lap_timer": self.create_lap_timer,
            "url": self.create_url,
            "relative": self.create_relative,
            "radar": self.create_radar,
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
            if widget_id in self.external_widget_ids:
                continue
            if bool(config.get("enabled", False)) and widget_id in {"driver_panel", "delta", "flags", "weather", "tires", "battery", "damage", "fuel_time", "lap_timer", "relative", "radar", "map", "standings", "url"}:
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
        self.config_data["widgets"][widget_id]["enabled"] = True
        if widget_id in self.external_widget_ids:
            self.save_config()
            return
        widget = self.widgets.get(widget_id) or self.create_widget(widget_id)
        if hasattr(widget, "update_config"):
            widget.update_config(deepcopy(self.config_data["widgets"][widget_id]))
        if self.session_active or self.edit_mode:
            widget.show()
        else:
            widget.hide()
        self.save_config()

    def hide_widget(self, widget_id: str) -> None:
        if widget_id in self.config_data.get("widgets", {}):
            # Atualize primeiro: controladores invisíveis (URL) consultam a
            # configuração dentro de hide() para encerrar seus recursos.
            self.config_data["widgets"][widget_id]["enabled"] = False
        widget = self.widgets.get(widget_id)
        if widget is not None:
            if hasattr(widget, "update_config"):
                widget.update_config(deepcopy(self.config_data["widgets"][widget_id]))
            widget.hide()
        if widget_id in self.config_data.get("widgets", {}):
            self.save_config()

    def set_widget_enabled(self, widget_id: str, enabled: bool) -> None:
        self.show_widget(widget_id) if enabled else self.hide_widget(widget_id)

    @staticmethod
    def _preserve_editor_geometry(
        widget_id: str,
        previous: dict[str, Any],
        incoming: dict[str, Any],
        *,
        preserve_geometry: bool,
    ) -> dict[str, Any]:
        """Impede que uma cópia antiga do editor desfaça o arraste."""
        config = deepcopy(incoming)
        if not preserve_geometry:
            return config
        for key in (
            "position",
            "size",
            "scale",
            "monitor",
            "column_width_reference_total",
        ):
            if key in previous:
                config[key] = deepcopy(previous[key])
        return config

    @staticmethod
    def _should_reapply_normalized_geometry(
        widget_id: str,
        *,
        preserve_geometry: bool,
    ) -> bool:
        """Evita recalcular a largura mínima após editar o STR."""
        return widget_id != "standings" or not preserve_geometry

    def update_widget_config(
        self,
        widget_id: str,
        config: dict[str, Any],
        *,
        preserve_geometry: bool = True,
    ) -> None:
        previous = self.config_data.get("widgets", {}).get(widget_id, {})
        config = self._preserve_editor_geometry(
            widget_id,
            previous,
            config,
            preserve_geometry=preserve_geometry,
        )
        widget = self.widgets.get(widget_id)
        column_width_delta = 0.0
        size_unchanged = previous.get("size", {}) == config.get("size", {})
        if widget is not None and hasattr(
            widget,
            "configured_flexible_width_delta",
        ):
            column_width_delta = float(
                widget.configured_flexible_width_delta(previous, config)
            )
        if "column_width_reference_total" not in config:
            reference = previous.get("column_width_reference_total")
            widget_for_reference = widget
            if reference is None and widget_for_reference is not None and hasattr(
                widget_for_reference, "column_width_total"
            ):
                reference = float(widget_for_reference.column_width_total())
            if reference is not None:
                config["column_width_reference_total"] = float(reference)
        if widget is not None:
            if hasattr(widget, "update_config"):
                widget.update_config(deepcopy(config))
            self._apply_window_flags(widget, config)
            screen = widget.screen()
            if (
                screen is not None
                and size_unchanged
                and abs(column_width_delta) > 0.01
                and hasattr(widget, "column_width_total")
            ):
                screen_geometry = screen.geometry()
                config.setdefault("size", {})["width"] = max(
                    0.01,
                    min(1.0, widget.width() / max(1, screen_geometry.width())),
                )
                config["column_width_reference_total"] = float(
                    widget.column_width_total()
                )
                if hasattr(widget, "config"):
                    widget.config.setdefault("size", {})["width"] = config["size"][
                        "width"
                    ]
                    widget.config["column_width_reference_total"] = config[
                        "column_width_reference_total"
                    ]
            if (
                screen is not None
                and hasattr(widget, "apply_normalized_geometry")
                and self._should_reapply_normalized_geometry(
                    widget_id,
                    preserve_geometry=preserve_geometry,
                )
            ):
                widget.apply_normalized_geometry(screen.geometry())

        self.config_data["widgets"][widget_id] = deepcopy(config)

        if widget_id == "url":
            self._configure_url_sources()

        self.save_config()

    def restore_widget_default(self, widget_id: str) -> None:
        default = self.config_data.get("defaults", {}).get(widget_id)
        if default is not None:
            self.update_widget_config(
                widget_id,
                deepcopy(default),
                preserve_geometry=False,
            )

    def update_player_data(self, player_data: Any) -> None:
        widget = self.widgets.get("driver_panel")
        if widget is not None and widget.isVisible():
            widget.update_telemetry(player_data)


        tires = self.widgets.get("tires")
        if tires is not None and tires.isVisible():
            tires.update_telemetry(player_data)
        damage = self.widgets.get("damage")
        if damage is not None and damage.isVisible():
            damage.update_telemetry(player_data)

    def update_fast_player_data(self, player_data: Any) -> None:
        """Atualiza somente o painel rápido sem depender da sessão completa."""
        if not self.session_active or not bool(
            getattr(player_data, "has_player", False)
        ):
            return
        widget = self.widgets.get("driver_panel")
        if widget is not None and widget.isVisible():
            widget.update_telemetry(player_data)

    def update_session_data(self, session: Any) -> None:
        self._update_split_server_lifecycle(session)
        standings = self.widgets.get("standings")
        if standings is not None and hasattr(
            standings, "observe_session_lifecycle"
        ):
            standings.observe_session_lifecycle(session)
        was_active = self.session_active
        allowed = self._session_allows_overlays(session)
        if allowed and not was_active:
            # Toda retomada de coleta (entrada inicial, retorno do monitor,
            # box/garagem ou volta ao carro) exige uma leitura nova.
            self._last_split_label = ""
            setattr(session, "split_label", "")
            if self._shared_online_client is not None:
                self._split_recheck_authoritative = self._online_split_enabled()
                self._shared_online_client.request_split_recheck(session)
        elif not allowed:
            # Fora da coleta valida, nenhum valor anterior pode permanecer
            # visivel. DR/SR/paises continuam em cache para a retomada.
            self._last_split_label = ""
            setattr(session, "split_label", "")
            if self._shared_online_client is not None:
                self._shared_online_client.hide_split()
        self.set_session_active(allowed)
        if not self.session_active:
            return

        self._hydrate_split_label(session)
        self._update_session_widgets(
            session,
            time.monotonic(),
            self._update_due,
        )

    def _update_session_widgets(
        self,
        session: Any,
        now: float,
        due: Callable[[str, float], bool],
    ) -> None:

        tires = self.widgets.get("tires")
        if (
            tires is not None
            and tires.isVisible()
            and getattr(session, "player", None) is not None
            and due("tires", now)
        ):
            tires.update_telemetry(session.player)

        damage = self.widgets.get("damage")
        if (
            damage is not None
            and damage.isVisible()
            and getattr(session, "player", None) is not None
            and due("damage", now)
        ):
            damage.update_telemetry(session.player)

        fuel_time = self.widgets.get("fuel_time")
        if fuel_time is not None and fuel_time.isVisible() and due("fuel_time", now):
            fuel_time.update_from_session(session)

        lap_timer = self.widgets.get("lap_timer")
        if lap_timer is not None and lap_timer.isVisible() and due("lap_timer", now):
            lap_timer.update_from_session(session)

        relative = self.widgets.get("relative")
        if (
            relative is not None
            and relative.isVisible()
            and due("relative", now)
        ):
            relative.update_from_session(session)

        radar = self.widgets.get("radar")
        radar_config = self.config_data.get("widgets", {}).get("radar", {})
        # O radar se oculta quando nao ha adversarios proximos. Mesmo oculto,
        # precisa continuar recebendo telemetria para detectar o proximo carro
        # e reaparecer; condicionar a isVisible() o deixava desligado para
        # sempre depois da primeira pista livre.
        if (
            radar is not None
            and bool(radar_config.get("enabled", False))
            and due("radar", now)
        ):
            radar.update_from_session(session)

        battery = self.widgets.get("battery")
        battery_config = self.config_data.get("widgets", {}).get(
            "battery", {}
        )
        if battery is not None and bool(
            battery_config.get("enabled", False)
        ) and due("battery", now):
            # Continua atualizando mesmo oculto para reaparecer ao entrar em um Hypercar.
            battery.update_from_session(session)

        delta = self.widgets.get("delta")
        if (
            delta is not None
            and delta.isVisible()
            and due("delta", now)
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
        ) and due("flags", now):
            flags.update_from_session(session)

        weather = self.widgets.get("weather")
        if (
            weather is not None
            and weather.isVisible()
            and due("weather", now)
        ):
            weather.update_from_session(session)


        map_widget = self.widgets.get("map")
        map_config = self.config_data.get("widgets", {}).get(
            "map", {}
        )
        if map_widget is not None and bool(
            map_config.get("enabled", False)
        ) and due("map", now):
            # Continua aprendendo o traçado enquanto o widget está habilitado.
            map_widget.update_from_session(session)

        standings = self.widgets.get("standings")
        standings_config = self.config_data.get("widgets", {}).get(
            "standings", {}
        )
        if standings is not None and bool(
            standings_config.get("enabled", False)
        ) and due("standings", now):
            standings.update_from_session(session)
        self._update_url_sources(session, now, due)

    def _update_split_server_lifecycle(self, session: Any) -> None:
        """Reseta dados online somente ao realmente voltar ao menu."""
        connected = bool(getattr(session, "connected", False))
        location = int(getattr(session, "application_location", 0) or 0)
        session_number = int(getattr(session, "session", 0) or 0)
        drivers = list(getattr(session, "drivers", []) or [])
        if hasattr(session, "application_location"):
            # O estado oficial do LMU e autoritativo: 0=menu, 1=carregando,
            # 2=monitor, 3=pista. Dados de sessao/pilotos podem ficar antigos
            # por alguns quadros depois de voltar ao menu.
            in_server = connected and location in {1, 2, 3}
        else:
            in_server = connected and (session_number > 0 or bool(drivers))
        if in_server:
            self._split_server_active = True
            return
        if not self._split_server_active:
            return
        self._split_server_active = False
        self._split_session_key = None
        self._last_split_label = ""
        self._split_recheck_authoritative = False
        setattr(session, "split_label", "")
        if self._shared_online_client is not None:
            self._shared_online_client.reset()

    def _hydrate_split_label(self, session: Any) -> None:
        """Mantem o split disponivel antes de qualquer widget ser atualizado."""
        key = (
            str(getattr(session, "track_name", "") or ""),
            str(
                getattr(session, "session_name", "")
                or getattr(session, "game_session_name", "")
                or getattr(session, "session", "")
            ),
        )
        if key != self._split_session_key:
            self._split_session_key = key
            self._last_split_label = ""
            setattr(session, "split_label", "")
            if self._shared_online_client is not None:
                self._split_recheck_authoritative = self._online_split_enabled()
                self._shared_online_client.request_split_recheck(session)

        # Durante uma coleta RaceOS, a resposta online e autoritativa. O REST
        # local pode conservar o split da sessao anterior por alguns quadros;
        # aceitar esse campo aqui fazia o valor antigo reaparecer enquanto a
        # verificacao nova ainda estava em andamento (ou mesmo quando ela
        # terminava sem informar divisao).
        label = "" if self._split_recheck_authoritative else str(
            getattr(session, "split_label", "") or ""
        ).strip()
        if self._shared_online_client is not None:
            online_label = str(
                self._shared_online_client.snapshot().split_label or ""
            ).strip()
            if online_label:
                label = online_label
        if label:
            self._last_split_label = label
        elif self._last_split_label:
            label = self._last_split_label
        setattr(session, "split_label", label)

    def _online_split_enabled(self) -> bool:
        client = self._shared_online_client
        if client is None:
            return False
        config = getattr(client, "config", {}) or {}
        return bool(config.get("online_enrichment", False)) and bool(
            config.get("use_cloud_profiles", False)
        )

    def _configure_url_sources(self) -> None:
        controller = self.widgets.get("url")
        if not isinstance(controller, UrlServerWidget): return
        selected = list(self.config_data.get("widgets", {}).get("url", {}).get("published_widgets", []))
        sources: dict[str, QWidget] = {}
        for widget_id in selected:
            if widget_id == "url": continue
            existing = self.widgets.get(widget_id)
            try:
                source = existing or self.create_widget(widget_id)
            except (KeyError, TypeError):
                continue
            # Fontes usadas apenas para renderizar a saída do navegador não
            # são overlays nativos. Isto é especialmente importante para
            # widgets que também vivem em processos isolados: sem a marcação,
            # o modo de edição mostrava as duas instâncias na tela.
            if existing is None and widget_id in self.external_widget_ids:
                source.setProperty("sectorflow_url_source", True)
                source.hide()
            sources[widget_id] = source
            if not bool(self.config_data.get("widgets", {}).get(widget_id, {}).get("enabled", False)):
                source.hide()
        controller.set_sources(sources)

    def _update_url_sources(
        self,
        session: Any,
        now: float,
        due: Callable[[str, float], bool] | None = None,
    ) -> None:
        controller = self.widgets.get("url")
        if not isinstance(controller, UrlServerWidget) or not bool(
            self.config_data.get("widgets", {}).get("url", {}).get("enabled", False)
        ): return
        is_due = self._update_due if due is None else due
        for widget_id, widget in list(controller.sources.items()):
            # Uma fonte sem OBS/navegador ativo nao recebe trabalho. O mesmo
            # limitador usado pelo widget local impede atualizar duas vezes no
            # mesmo ciclo quando a fonte tambem esta visivel na tela.
            if not controller.is_client_active(widget_id):
                continue
            if not is_due(widget_id, now):
                continue
            if widget_id in {"driver_panel", "tires", "damage"}:
                player = getattr(session, "player", None)
                if player is not None and hasattr(widget, "update_telemetry"):
                    widget.update_telemetry(player)
            elif hasattr(widget, "update_from_session"):
                widget.update_from_session(session)
    def set_edit_mode(self, enabled: bool) -> None:
        self.edit_mode = bool(enabled)
        for widget_id, widget in self.widgets.items():
            config = self.config_data["widgets"][widget_id]
            if hasattr(widget, "set_edit_mode"):
                widget.set_edit_mode(enabled)
            click_through = bool(config.get("click_through", True)) and not enabled
            self._set_click_through(widget, click_through)

            is_enabled = bool(config.get("enabled", False))
            is_url_source = bool(widget.property("sectorflow_url_source"))
            if is_enabled and not is_url_source and (
                self.edit_mode or self.session_active
            ):
                widget.show()
            else:
                widget.hide()
        url_widget = self.widgets.get("url")
        if isinstance(url_widget, UrlServerWidget):
            url_widget.set_output_active(self.session_active or self.edit_mode)

    def set_session_active(self, active: bool) -> None:
        active = bool(active)
        if active == self.session_active:
            return
        self.session_active = active
        self._last_widget_update.clear()
        for widget_id, widget in self.widgets.items():
            config = self.config_data.get("widgets", {}).get(widget_id, {})
            is_enabled = bool(config.get("enabled", False))
            is_url_source = bool(widget.property("sectorflow_url_source"))
            if is_enabled and not is_url_source and (
                self.session_active or self.edit_mode
            ):
                widget.show()
            else:
                widget.hide()
        url_widget = self.widgets.get("url")
        if isinstance(url_widget, UrlServerWidget):
            url_widget.set_output_active(self.session_active or self.edit_mode)
        self.session_active_changed.emit(self.session_active)

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
        profile_mode = getattr(self, "active_profile_mode", lambda: "standard")()
        if profile_mode == "engineer":
            return self._engineer_session_allows_overlays(session)
        if not bool(getattr(session, "connected", True)):
            self._log_overlay_decision(session, False, "not_connected")
            return False
        if bool(getattr(session, "telemetry_paused", False)):
            self._log_overlay_decision(session, False, "telemetry_paused")
            return False
        if not bool(getattr(session, "player_synced", False)):
            self._log_overlay_decision(session, False, "player_not_synced")
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

        # API em primeiro lugar: menu, loading, monitor e replay nunca devem
        # exibir os widgets. Quando o estado REST esta completo, exigimos que
        # o jogador esteja realmente no controle do veiculo carregado.
        navigation_state = str(
            getattr(session, "navigation_state", "") or ""
        )
        navigation_loading = bool(
            getattr(session, "navigation_loading", False)
        )
        if api_available:
            if (
                navigation_state in {
                    "NAV_MAIN_MENU",
                    "NAV_OPTIONS",
                    "NAV_LOADING",
                }
                or navigation_loading
                or bool(replay_active)
                or bool(in_monitor)
            ):
                self._log_overlay_decision(
                    session,
                    False,
                    "rest_not_driving",
                )
                return False
            if rest_state_complete and not (
                bool(in_control) and bool(vehicle_loaded)
            ):
                self._log_overlay_decision(
                    session,
                    False,
                    "rest_no_vehicle_control",
                )
                return False

        # Fallback igual ao TinyPedal: jogador/veiculo sincronizado e estado
        # realtime (ou ignicao ligada). mOptionsLocation reforca que somente
        # o estado 3, na pista, pode mostrar o overlay.
        if not rest_state_complete:
            location = int(
                getattr(session, "application_location", 0) or 0
            )
            player_data = getattr(session, "player", None)
            ignition = int(
                getattr(player_data, "ignition_starter", 0) or 0
            )
            if location in {0, 1, 2}:
                self._log_overlay_decision(
                    session,
                    False,
                    "memory_not_on_track",
                    {"application_location": location},
                )
                return False
            if not bool(getattr(session, "player_has_vehicle", False)):
                self._log_overlay_decision(
                    session,
                    False,
                    "memory_no_player_vehicle",
                )
                return False
            if not (
                bool(getattr(session, "in_realtime", False))
                or ignition > 0
            ):
                self._log_overlay_decision(
                    session,
                    False,
                    "memory_not_realtime",
                )
                return False

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

            # Segue o comportamento do TinyPedal: com REST fresco, monitor e
            # garagem sem controle do carro pausam/ocultam os overlays.
            if bool(in_monitor) and not bool(in_control):
                self._log_overlay_decision(
                    session,
                    False,
                    "rest_monitor",
                )
                return False

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
                    # O LMU muda para 8 quando o líder termina ou o relógio
                    # zera, mesmo que o jogador ainda esteja completando sua
                    # volta. Algumas sessões de volta rápida também publicam
                    # 9 transitoriamente. Nesses dois estados, presença
                    # histórica (voltas/velocidade) não basta: exigimos uma
                    # confirmação atual de controle/realtime/ignição.
                    player_obj = getattr(session, "player", None)
                    currently_driving = bool(in_control) if rest_state_complete else (
                        bool(getattr(session, "in_realtime", False))
                        or int(getattr(player_obj, "ignition_starter", 0) or 0) > 0
                    )
                    if gp not in (8, 9) or not currently_driving:
                        self._log_overlay_decision(session, False, "game_phase_out_of_range", {"game_phase": game_phase, "player_present": player_present, "player_active": player_active, "currently_driving": currently_driving})
                        return False
            except (TypeError, ValueError):
                self._log_overlay_decision(session, False, "game_phase_invalid", {"game_phase": game_phase})
                return False
        # todas as checagens passaram
        self._log_overlay_decision(session, True, "allowed")
        return True

    def _engineer_session_allows_overlays(self, session: Any) -> bool:
        """Keep session widgets available in monitor/driver-swap mode."""
        if not bool(getattr(session, "connected", True)):
            self._log_overlay_decision(session, False, "engineer_not_connected")
            return False
        navigation_state = str(getattr(session, "navigation_state", "") or "")
        if navigation_state in {"NAV_MAIN_MENU", "NAV_OPTIONS", "NAV_LOADING"}:
            self._log_overlay_decision(session, False, "engineer_navigation")
            return False
        if bool(getattr(session, "navigation_loading", False)) or bool(
            getattr(session, "is_replay_active", False)
        ):
            self._log_overlay_decision(session, False, "engineer_loading_or_replay")
            return False
        try:
            session_type = int(getattr(session, "session", -1))
        except (TypeError, ValueError):
            return False
        allowed = 1 <= session_type <= 8 or 10 <= session_type <= 13
        self._log_overlay_decision(
            session, allowed, "engineer_session" if allowed else "engineer_invalid_session"
        )
        return allowed

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
        self._sync_active_profile()
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
        if self._shared_standings_enrichment is not None:
            self._shared_standings_enrichment.stop()
            self._shared_standings_enrichment = None
        if self._shared_online_client is not None:
            self._shared_online_client.reset()
            self._shared_online_client = None

    def _standings_services(
        self, config: dict[str, Any]
    ) -> tuple[LocalStandingsEnrichment, LMUOnlineIdentityClient]:
        """One REST/cache pipeline shared by Standings and Relative."""
        project_root = Path(__file__).resolve().parents[2]
        if self._shared_standings_enrichment is None:
            self._shared_standings_enrichment = LocalStandingsEnrichment(
                project_root, config
            )
        else:
            self._shared_standings_enrichment.update_config(config)
        if self._shared_online_client is None:
            self._shared_online_client = LMUOnlineIdentityClient(
                project_root, config
            )
        else:
            self._shared_online_client.update_config(config)
        return self._shared_standings_enrichment, self._shared_online_client

    def _load_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuração não encontrada: {self.config_path}")
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
            # Configuracoes instaladas vivem em LOCALAPPDATA e nao possuem os
            # arquivos *_defaults.json ao lado. Mescla qualquer widget novo a
            # partir do catalogo de fabrica empacotado, preservando integralmente
            # as escolhas e geometrias que o usuario ja salvou.
            factory_path = Path(__file__).resolve().parents[1] / "config" / "widgets.json"
            if factory_path.resolve() != self.config_path.resolve() and factory_path.exists():
                factory = json.loads(factory_path.read_text(encoding="utf-8"))
                widgets = data.setdefault("widgets", {})
                defaults = data.setdefault("defaults", {})
                for widget_id, widget_config in factory.get("widgets", {}).items():
                    widgets.setdefault(widget_id, deepcopy(widget_config))
                for widget_id, widget_config in factory.get("defaults", {}).items():
                    defaults.setdefault(widget_id, deepcopy(widget_config))
            driver_defaults_path = self.config_path.with_name("driver_panel_defaults.json")
            if not driver_defaults_path.exists():
                driver_defaults_path = (
                    Path(__file__).resolve().parents[1]
                    / "config"
                    / "driver_panel_defaults.json"
                )
            if driver_defaults_path.exists():
                driver_default = json.loads(driver_defaults_path.read_text(encoding="utf-8"))
                data.setdefault("widgets", {}).setdefault("driver_panel", deepcopy(driver_default))
                data.setdefault("defaults", {}).setdefault("driver_panel", deepcopy(driver_default))
            defaults_path = self.config_path.with_name("damage_defaults.json")
            if defaults_path.exists():
                damage_default = json.loads(defaults_path.read_text(encoding="utf-8"))
                data.setdefault("widgets", {}).setdefault("damage", deepcopy(damage_default))
                data.setdefault("defaults", {}).setdefault("damage", deepcopy(damage_default))
            fuel_defaults_path = self.config_path.with_name("fuel_time_defaults.json")
            if fuel_defaults_path.exists():
                fuel_default = json.loads(fuel_defaults_path.read_text(encoding="utf-8"))
                data.setdefault("widgets", {}).setdefault("fuel_time", deepcopy(fuel_default))
                data.setdefault("defaults", {}).setdefault("fuel_time", deepcopy(fuel_default))
            lap_timer_defaults_path = self.config_path.with_name("lap_timer_defaults.json")
            if not lap_timer_defaults_path.exists():
                lap_timer_defaults_path = (
                    Path(__file__).resolve().parents[1]
                    / "config"
                    / "lap_timer_defaults.json"
                )
            if lap_timer_defaults_path.exists():
                lap_timer_default = json.loads(
                    lap_timer_defaults_path.read_text(encoding="utf-8")
                )
                data.setdefault("widgets", {}).setdefault(
                    "lap_timer", deepcopy(lap_timer_default)
                )
                data.setdefault("defaults", {}).setdefault(
                    "lap_timer", deepcopy(lap_timer_default)
                )
            url_defaults_path = self.config_path.with_name("url_defaults.json")
            if url_defaults_path.exists():
                url_default = json.loads(url_defaults_path.read_text(encoding="utf-8"))
                data.setdefault("widgets", {}).setdefault("url", deepcopy(url_default))
                data.setdefault("defaults", {}).setdefault("url", deepcopy(url_default))
            radar_defaults_path = self.config_path.with_name("radar_defaults.json")
            if radar_defaults_path.exists():
                radar_default = json.loads(radar_defaults_path.read_text(encoding="utf-8"))
                data.setdefault("widgets", {}).setdefault("radar", deepcopy(radar_default))
                data.setdefault("defaults", {}).setdefault("radar", deepcopy(radar_default))
            standings_defaults_path = self.config_path.with_name("standings_defaults.json")
            relative_defaults_path = self.config_path.with_name("relative_defaults.json")
            if standings_defaults_path.exists() and relative_defaults_path.exists():
                relative_default = json.loads(standings_defaults_path.read_text(encoding="utf-8"))
                relative_override = json.loads(relative_defaults_path.read_text(encoding="utf-8"))
                def merge(target: dict[str, Any], source: dict[str, Any]) -> None:
                    for key, value in source.items():
                        if isinstance(value, dict) and isinstance(target.get(key), dict):
                            merge(target[key], value)
                        else:
                            target[key] = deepcopy(value)
                merge(relative_default, relative_override)
                data.setdefault("widgets", {}).setdefault("relative", deepcopy(relative_default))
                data.setdefault("defaults", {}).setdefault("relative", deepcopy(relative_default))
            return data
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
        profile_id: str = "",
    ) -> None:
        requested_profile = str(profile_id or "")
        active_profile = self.active_profile_id
        if requested_profile and requested_profile != active_profile:
            profile = self.config_data.get("profiles", {}).get(requested_profile)
            if not isinstance(profile, dict):
                return
            config = profile.get("widgets", {}).get(widget_id)
            if not isinstance(config, dict):
                return
        else:
            config = self.config_data["widgets"][widget_id]
        config.setdefault("position", {})
        config.setdefault("size", {})
        minimum_width, minimum_height = self._geometry_minimum_ratios(widget_id)
        config["position"]["x"] = max(0.0, min(1.0, x))
        config["position"]["y"] = max(0.0, min(1.0, y))
        config["size"]["width"] = max(minimum_width, min(1.0, width))
        config["size"]["height"] = max(minimum_height, min(1.0, height))
        config["scale"] = 1.0
        widget = (
            self.widgets.get(widget_id)
            if not requested_profile or requested_profile == active_profile
            else None
        )
        if widget is not None and hasattr(widget, "config"):
            widget.config.setdefault("position", {}).update(config["position"])
            widget.config.setdefault("size", {}).update(config["size"])
            widget.config["scale"] = 1.0
        if widget is not None and hasattr(widget, "column_width_total"):
            reference_total = float(widget.column_width_total())
            config["column_width_reference_total"] = reference_total
            if hasattr(widget, "config"):
                widget.config["column_width_reference_total"] = reference_total
        self.save_config()

    @staticmethod
    def _geometry_minimum_ratios(widget_id: str) -> tuple[float, float]:
        """Limites normalizados usados ao persistir redimensionamentos."""
        if widget_id == "battery":
            return 0.01, 0.02
        if widget_id == "driver_panel":
            # O limite físico do próprio widget mantém a telemetria legível.
            # Razões menores evitam que monitores 1440p/4K ampliem o painel
            # novamente apenas durante a gravação da geometria.
            return 0.01, 0.01
        if widget_id == "flags":
            # O próprio widget mantém o limite físico de 110 px. Não converta
            # esse limite novamente em 5% da tela, pois em 1440p/4K ele
            # aumentaria assim que o usuário soltasse o puxador.
            return 0.01, 0.01
        return 0.05, 0.05

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
