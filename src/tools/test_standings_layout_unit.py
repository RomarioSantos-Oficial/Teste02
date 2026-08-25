from __future__ import annotations

import unittest

from PySide6.QtCore import QRectF

from src.widget.relative.relative_widget import RelativeWidget
from src.widget.standings.standings_models import StandingRow
from src.widget.standings.standings_widget import StandingsWidget


class StandingsLayoutUnitTests(unittest.TestCase):
    def test_str_places_pit_between_driver_and_brand(self) -> None:
        columns = [key for key, _width in StandingsWidget.BASE_COLUMNS]
        driver_index = columns.index("driver")
        self.assertEqual(columns[driver_index : driver_index + 3], ["driver", "pit", "brand"])

    def test_relative_keeps_its_previous_pit_order(self) -> None:
        columns = [key for key, _width in RelativeWidget.BASE_COLUMNS]
        self.assertLess(columns.index("brand"), columns.index("pit"))
        self.assertEqual(columns.index("pit"), columns.index("number") + 1)

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
