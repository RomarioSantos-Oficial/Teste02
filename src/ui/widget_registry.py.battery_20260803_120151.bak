from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class WidgetDefinition:
    widget_id: str
    title: str
    category: str
    editable: bool = True
    implemented: bool = False


WIDGET_DEFINITIONS: list[WidgetDefinition] = [
    WidgetDefinition("standings", "Standings", "Corrida", True, False),
    WidgetDefinition("relative", "Relative", "Corrida", True, False),
    WidgetDefinition("delta", "Delta", "Corrida", True, True),
    WidgetDefinition("map", "Mapa", "Corrida", True, False),
    WidgetDefinition("driver_panel", "Telemetry", "Carro", True, True),
    WidgetDefinition("battery", "Battery", "Carro", True, False),
    WidgetDefinition("fuel_time", "Fuel Time", "Estratégia", True, False),
    WidgetDefinition("tires", "Tyres", "Carro", True, True),
    WidgetDefinition("damage", "Damage", "Carro", True, False),
    WidgetDefinition("replay", "Replay", "Sistema", True, False),
    WidgetDefinition("url", "URL", "Sistema", True, False),
    WidgetDefinition("weather", "Weather", "Estratégia", True, True),
    WidgetDefinition("flags", "Flags", "Corrida", True, True),
    WidgetDefinition("pit_window", "Pit Window", "Estratégia", True, False),
    WidgetDefinition("race_control", "Race Control", "Corrida", True, False),
]
