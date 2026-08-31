from __future__ import annotations

import unittest

from PySide6.QtCore import QRectF

from src.ui.overlay_manager import OverlayManager
from src.widget.relative.relative_widget import RelativeWidget
from src.widget.standings.standings_models import StandingRow
from src.widget.standings.standings_widget import (
    StandingsWidget,
    tyre_icon_fill,
    tyre_position_tokens,
)


class StandingsLayoutUnitTests(unittest.TestCase):
    class PainterProbe:
        def __init__(self) -> None:
            self.ellipses: list[QRectF] = []
            self.arcs: list[QRectF] = []

        def setPen(self, _pen) -> None:
            pass

        def setBrush(self, _brush) -> None:
            pass

        def drawEllipse(self, rect: QRectF) -> None:
            self.ellipses.append(QRectF(rect))

        def drawArc(self, rect: QRectF, _start: int, _span: int) -> None:
            self.arcs.append(QRectF(rect))

    class TyreWidgetProbe:
        def __init__(self, scale: float = 1.25) -> None:
            self.config = {"tyre_icon_scale": scale, "colors": {}}
            self._scale = 1.0

    def test_tyre_tokens_keep_fl_fr_rl_rr_positions(self) -> None:
        self.assertEqual(
            tyre_position_tokens(["Soft", "", "Hard", "Wet"]),
            ("S", "", "H", "W"),
        )

    def test_tyre_icon_editor_scale_changes_visible_fill(self) -> None:
        small = tyre_icon_fill(0.70)
        normal = tyre_icon_fill(1.25)
        large = tyre_icon_fill(2.00)
        self.assertLess(small, normal)
        self.assertLess(normal, large)
        self.assertLessEqual(large, 1.0)

    def test_uniform_compound_draws_one_wheel(self) -> None:
        painter = self.PainterProbe()
        StandingsWidget._draw_tyre(
            self.TyreWidgetProbe(),
            painter,
            QRectF(0.0, 0.0, 80.0, 40.0),
            ("Soft", "Soft", "Soft", "Soft"),
        )
        self.assertEqual(len(painter.arcs), 1)
        self.assertEqual(len(painter.ellipses), 2)

    def test_mixed_compounds_draw_four_wheels(self) -> None:
        painter = self.PainterProbe()
        StandingsWidget._draw_tyre(
            self.TyreWidgetProbe(),
            painter,
            QRectF(0.0, 0.0, 80.0, 40.0),
            ("Soft", "Medium", "Hard", "Wet"),
        )
        self.assertEqual(len(painter.arcs), 4)
        self.assertEqual(len(painter.ellipses), 8)

    def test_tyre_scale_changes_the_drawn_wheel_size(self) -> None:
        small_painter = self.PainterProbe()
        large_painter = self.PainterProbe()
        rect = QRectF(0.0, 0.0, 80.0, 40.0)
        compounds = ("Soft",) * 4
        StandingsWidget._draw_tyre(
            self.TyreWidgetProbe(0.70), small_painter, rect, compounds
        )
        StandingsWidget._draw_tyre(
            self.TyreWidgetProbe(2.00), large_painter, rect, compounds
        )
        self.assertLess(
            small_painter.ellipses[0].width(),
            large_painter.ellipses[0].width(),
        )

    def test_str_editor_keeps_geometry_saved_after_drag(self) -> None:
        dragged = {
            "position": {"x": 0.0, "y": 0.0},
            "size": {"width": 0.3385, "height": 0.2518},
            "scale": 1.0,
            "monitor": 0,
            "column_width_reference_total": 968.2,
            "font_size": 26,
        }
        stale_editor = {
            "position": {"x": 0.01, "y": 0.02},
            "size": {"width": 0.74, "height": 0.72},
            "scale": 1.0,
            "monitor": 0,
            "column_width_reference_total": 1200.0,
            "font_size": 28,
        }

        merged = OverlayManager._preserve_editor_geometry(
            "standings",
            dragged,
            stale_editor,
            preserve_geometry=True,
        )

        self.assertEqual(merged["position"], dragged["position"])
        self.assertEqual(merged["size"], dragged["size"])
        self.assertEqual(
            merged["column_width_reference_total"],
            dragged["column_width_reference_total"],
        )
        self.assertEqual(merged["font_size"], 28)

    def test_restore_default_may_restore_str_geometry(self) -> None:
        current = {"size": {"width": 0.3385, "height": 0.2518}}
        defaults = {"size": {"width": 0.74, "height": 0.72}}

        merged = OverlayManager._preserve_editor_geometry(
            "standings",
            current,
            defaults,
            preserve_geometry=False,
        )

        self.assertEqual(merged["size"], defaults["size"])

    def test_str_editor_does_not_reapply_automatic_geometry(self) -> None:
        self.assertFalse(
            OverlayManager._should_reapply_normalized_geometry(
                "standings",
                preserve_geometry=True,
            )
        )

    def test_str_restore_default_reapplies_automatic_geometry(self) -> None:
        self.assertTrue(
            OverlayManager._should_reapply_normalized_geometry(
                "standings",
                preserve_geometry=False,
            )
        )

    def test_relative_keeps_its_previous_geometry_update(self) -> None:
        self.assertTrue(
            OverlayManager._should_reapply_normalized_geometry(
                "relative",
                preserve_geometry=True,
            )
        )

    def test_str_places_pit_between_driver_and_brand(self) -> None:
        columns = [key for key, _width in StandingsWidget.BASE_COLUMNS]
        driver_index = columns.index("driver")
        self.assertEqual(columns[driver_index : driver_index + 3], ["driver", "pit", "brand"])

    def test_relative_keeps_its_previous_pit_order(self) -> None:
        columns = [key for key, _width in RelativeWidget.BASE_COLUMNS]
        self.assertLess(columns.index("brand"), columns.index("pit"))
        self.assertEqual(columns.index("pit"), columns.index("number") + 1)

    def test_only_str_uses_black_brand_cell_and_full_width_logo(self) -> None:
        self.assertTrue(StandingsWidget.BRAND_CELL_BLACK_BACKGROUND)
        self.assertTrue(StandingsWidget.BRAND_LOGO_FILL_WIDTH)
        self.assertFalse(RelativeWidget.BRAND_CELL_BLACK_BACKGROUND)
        self.assertFalse(RelativeWidget.BRAND_LOGO_FILL_WIDTH)

        cell = QRectF(12.0, 5.0, 72.0, 40.0)
        target = StandingsWidget._brand_logo_target(cell, 120, 30)
        self.assertEqual(target.left(), cell.left())
        self.assertEqual(target.width(), cell.width())
        self.assertAlmostEqual(target.height(), 18.0)
        self.assertAlmostEqual(target.center().y(), cell.center().y())

    def test_finish_has_highest_priority_in_str_status(self) -> None:
        row = StandingRow(
            finish_status=1,
            in_garage=True,
            in_pits=True,
            current_lap_invalidated=True,
            under_yellow=True,
            penalty_text="DT",
        )
        self.assertEqual(StandingsWidget._automatic_status_kind(row), "finish")

    def test_relative_does_not_move_finish_to_penalty_column(self) -> None:
        row = StandingRow(finish_status=1, in_garage=True)
        self.assertEqual(RelativeWidget._automatic_status_kind(row), "garage")

    def test_invalid_lap_is_not_shown_in_external_penalty_column(self) -> None:
        row = StandingRow(current_lap_invalidated=True)
        self.assertEqual(StandingsWidget._automatic_status_kind(row, False), "")
        self.assertEqual(RelativeWidget._automatic_status_kind(row, False), "")
        self.assertEqual(StandingsWidget._automatic_status_kind(row, True), "invalid")

    def test_driver_width_delta_is_exact(self) -> None:
        previous = {"column_widths": {"driver": 108.0, "brand": 52.0}}
        current = {"column_widths": {"driver": 158.0, "brand": 52.0}}
        self.assertEqual(
            StandingsWidget.configured_flexible_width_delta(previous, current),
            50.0,
        )

    def test_inactive_pit_space_is_lent_to_driver(self) -> None:
        cells = [
            ("driver", QRectF(100.0, 0.0, 120.0, 30.0)),
            ("pit", QRectF(220.0, 0.0, 90.0, 30.0)),
            ("brand", QRectF(310.0, 0.0, 60.0, 30.0)),
        ]
        result = StandingsWidget._row_cells_with_pit_borrow(
            cells,
            StandingRow(pit_status_visible=False),
        )
        by_key = dict(result)
        self.assertNotIn("pit", by_key)
        self.assertEqual(by_key["driver"].left(), 100.0)
        self.assertEqual(by_key["driver"].right(), 310.0)
        self.assertEqual(by_key["brand"].left(), 310.0)

    def test_active_pit_keeps_separate_cells(self) -> None:
        cells = [
            ("driver", QRectF(100.0, 0.0, 120.0, 30.0)),
            ("pit", QRectF(220.0, 0.0, 90.0, 30.0)),
            ("brand", QRectF(310.0, 0.0, 60.0, 30.0)),
        ]
        result = StandingsWidget._row_cells_with_pit_borrow(
            cells,
            StandingRow(pit_status_visible=True),
        )
        self.assertEqual(result, cells)

    def test_relative_does_not_borrow_non_adjacent_pit_space(self) -> None:
        cells = [
            ("driver", QRectF(100.0, 0.0, 120.0, 30.0)),
            ("brand", QRectF(220.0, 0.0, 60.0, 30.0)),
            ("pit", QRectF(280.0, 0.0, 90.0, 30.0)),
        ]
        result = RelativeWidget._row_cells_with_pit_borrow(
            cells,
            StandingRow(pit_status_visible=False),
        )
        self.assertEqual(result, cells)


if __name__ == "__main__":
    unittest.main()
