from __future__ import annotations
from typing import Any
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from src.widget.standings.standings_widget import StandingsWidget


class RelativeWidget(StandingsWidget):
    # Mantém a ordem anterior do Relative. A mudança de posição do PIT e da
    # bandeira de chegada foi aprovada somente para o STR.
    FINISH_FLAG_IN_STATUS_COLUMN = False
    BORROW_INACTIVE_PIT_FOR_DRIVER = False
    BASE_COLUMNS = (
        ("position", 46.0),
        ("change", 60.0),
        ("flag", 62.5),
        ("badge", 60.0),
        ("driver", 105.0),
        ("brand", 72.0),
        ("dr", 110.0),
        ("sr", 88.0),
        ("gain_dr", 76.0),
        ("number", 58.0),
        ("pit", 90.0),
        ("interval", 100.0),
        ("delta", 90.0),
        ("gap", 100.0),
        ("tyre", 76.0),
        ("energy", 105.0),
        ("damage", 80.0),
        ("track_limits", 88.0),
        ("penalty", 90.0),
    )

    def __init__(self, widget_id: str, config: dict[str, Any], parent=None, **shared) -> None:
        config["relative_mode"] = True
        config["show_laps"] = False
        config["show_best_lap"] = False
        config["show_last_lap"] = False
        config["show_driver_rank_progress"] = False
        super().__init__(widget_id, config, parent, **shared)
        self.setWindowTitle("Sector Flow Drive - Relative")

    def update_config(self, config: dict[str, Any]) -> None:
        config["relative_mode"] = True
        config["show_laps"] = False
        config["show_best_lap"] = False
        config["show_last_lap"] = False
        config["show_driver_rank_progress"] = False
        super().update_config(config)

    def _enabled_columns(self) -> dict[str, bool]:
        enabled = super()._enabled_columns()
        enabled.update({"laps": False, "best": False, "last": False, "interval": False, "gap": True})
        return enabled

    def _desired_content_height(self) -> int:
        desired = super()._desired_content_height()
        category_height = max(
            14.0,
            float(self.config.get("category_header_height", 50.0)) * self._scale,
        )
        return max(self.minimumHeight(), round(desired - category_height * len(self.view.categories)))

    def _draw_categories(self, painter: QPainter, rect: QRectF) -> float:
        """Relative não possui cabeçalho de categoria."""
        y = rect.top()
        row_height = max(14.0, float(self.config.get("row_height", 54.0)) * self._scale)
        legend_height = max(12.0, 30.0 * self._scale)
        for category_index, category in enumerate(self.view.categories):
            if bool(self.config.get("show_column_legend", False)) and category_index == 0:
                if y + legend_height > rect.bottom():
                    break
                self._draw_legend(painter, QRectF(rect.left(), y, rect.width(), legend_height))
                y += legend_height
            for row in category.rows:
                if y + row_height > rect.bottom():
                    self._draw_clipped_notice(
                        painter,
                        QRectF(rect.left(), max(rect.top(), rect.bottom()-row_height), rect.width(), row_height),
                    )
                    return y - rect.top()
                self._draw_row(painter, QRectF(rect.left(), y, rect.width(), row_height), row, category)
                y += row_height
        return y - rect.top()
