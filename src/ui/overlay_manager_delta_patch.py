"""
Trechos para adicionar ao seu src/ui/overlay_manager.py.

1) Adicione o import:

from src.widget.delta.delta_widget import DeltaWidget

2) Adicione estes métodos dentro da classe OverlayManager:
"""


def create_delta(self):
    widget_id = "delta"

    if widget_id in self.widgets:
        return self.widgets[widget_id]

    widget_config = deepcopy(self.config_data["widgets"][widget_id])
    widget = DeltaWidget(widget_id, widget_config)

    self._apply_window_flags(widget, widget_config)

    screens = QGuiApplication.screens()
    screen_index = int(widget_config.get("monitor", 0))
    screen = screens[min(max(screen_index, 0), len(screens) - 1)]

    widget.setScreen(screen)
    widget.apply_normalized_geometry(screen.geometry())
    widget.geometry_changed.connect(self._save_widget_geometry)

    self.widgets[widget_id] = widget

    if bool(widget_config.get("enabled", True)):
        widget.show()

    self.widget_created.emit(widget_id, widget)
    return widget


def update_session_data(self, session):
    driver_panel = self.widgets.get("driver_panel")

    if driver_panel is not None and session.player is not None:
        driver_panel.update_telemetry(session.player)

    delta = self.widgets.get("delta")

    if delta is not None:
        delta.update_from_session(session)
