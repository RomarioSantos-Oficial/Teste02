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
    BRAND_CELL_BLACK_BACKGROUND = True
    BRAND_LOGO_FILL_WIDTH = False
    BASE_COLUMNS = (
        ("position", 46.0),
        ("change", 60.0),
        ("flag", 62.5),
        ("badge", 60.0),
        ("driver", 105.0),
        ("brand", 72.0),
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
        super().__init__(widget_id, config, parent, **shared)
        self.setWindowTitle("Sector Flow Drive - Relative")

    def update_config(self, config: dict[str, Any]) -> None:
        config["relative_mode"] = True
        config["show_laps"] = False
        config["show_best_lap"] = False
        config["show_last_lap"] = False
        super().update_config(config)

    @staticmethod
    def _relative_name_tone(
        row,
        player,
        session_type: str,
        track_length_m: float,
    ) -> str:
        """Classifica a diferença de voltas somente durante uma corrida.

        Usa o progresso completo (voltas concluídas + fração da volta) para
        não marcar como uma volta de diferença dois carros que acabaram de
        cruzar a linha de chegada em momentos diferentes.
        """
        if session_type != "Race" or row.is_player:
            return "normal"

        try:
            track_length = float(track_length_m or 0.0)
            row_laps = max(0, int(row.laps))
            player_laps = max(0, int(player.laps))
            if track_length > 1.0:
                row_fraction = max(
                    0.0,
                    min(1.0, float(row.lap_distance_m or 0.0) / track_length),
                )
                player_fraction = max(
                    0.0,
                    min(1.0, float(player.lap_distance_m or 0.0) / track_length),
                )
                progress_delta = (
                    row_laps + row_fraction
                    - player_laps - player_fraction
                )
            else:
                progress_delta = float(row_laps - player_laps)
        except (TypeError, ValueError, OverflowError):
            return "normal"

        if progress_delta >= 1.0 - 1e-6:
            return "ahead"
        if progress_delta <= -1.0 + 1e-6:
            return "behind"
        return "normal"

    def _driver_name_color(self, row, colors: dict[str, Any]) -> QColor:
        normal = QColor(colors.get("text", "#FFFFFF"))
        if row.is_player or self.view.session_type != "Race":
            return normal

        player = next(
            (
                candidate
                for category in self.view.categories
                for candidate in category.rows
                if candidate.is_player
            ),
            None,
        )
        if player is None:
            return normal

        tone = self._relative_name_tone(
            row,
            player,
            self.view.session_type,
            float(getattr(self.session, "track_length_m", 0.0) or 0.0),
        )
        if tone == "ahead":
            return QColor("#268CFF")
        if tone == "behind":
            return QColor("#F04452")
        return normal

    def _enabled_columns(self) -> dict[str, bool]:
        enabled = super()._enabled_columns()
        enabled.update({"laps": False, "best": False, "last": False, "interval": False, "gap": True})
        return enabled

    def _desired_content_height(self) -> int:
        desired = super()._desired_content_height()
        category_count = len(self.view.categories)
        # A lista Relative nao desenha cabecalho nem espacamento entre blocos.
        # Remove exatamente a altura que a classe-base reservou para esses
        # elementos, usando as mesmas metricas do desenho.
        category_height = self._category_header_height()
        category_gap = max(2.0, 7.0 * self._scale)
        unused_height = (category_height + category_gap) * category_count
        return max(self.minimumHeight(), round(desired - unused_height))

    def _draw_categories(self, painter: QPainter, rect: QRectF) -> float:
        """Relative não possui cabeçalho de categoria."""
        y = rect.top()
        row_height = max(14.0, float(self.config.get("row_height", 54.0)) * self._scale)
        legend_height = self._legend_height()
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
