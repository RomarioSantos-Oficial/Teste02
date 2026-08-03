"""
Alterações para integrar o Delta ao menu principal.

No widget_registry.py, deixe o Delta como implementado:

WidgetDefinition("delta", "Delta", "Corrida", True, True)

No main_menu_window.py, importe:

from src.widget.delta.delta_editor import DeltaEditor

Dentro de _toggle_widget(), antes do bloco de erro:

elif widget_id == "delta":
    self.overlay_manager.create_delta()

Dentro de _open_editor(), adicione:
"""

def open_delta_editor_example(self):
    config = deepcopy(
        self.overlay_manager.config_data["widgets"]["delta"]
    )

    editor = DeltaEditor(config, self)

    editor.config_changed.connect(
        lambda new_config:
        self.overlay_manager.update_widget_config(
            "delta",
            new_config,
        )
    )

    editor.restore_requested.connect(
        lambda:
        self.overlay_manager.restore_widget_default(
            "delta"
        )
    )

    editor.show()
    self.editors["delta"] = editor
