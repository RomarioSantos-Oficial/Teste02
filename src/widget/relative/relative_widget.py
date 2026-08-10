from __future__ import annotations
from typing import Any
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from src.widget.standings.standings_widget import StandingsWidget


class RelativeWidget(StandingsWidget):
    BASE_COLUMNS = tuple(
        item for item in StandingsWidget.BASE_COLUMNS
        if item[0] not in {"laps", "best", "last"}
    )

    def __init__(self, widget_id: str, config: dict[str, Any], parent=None) -> None:
        config["relative_mode"] = True
        config["show_laps"] = False
        config["show_best_lap"] = False
        config["show_last_lap"] = False
        config["show_driver_rank_progress"] = False
        super().__init__(widget_id, config, parent)
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
        enabled.update({"laps": False, "best": False, "last": False, "gap": True})
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
