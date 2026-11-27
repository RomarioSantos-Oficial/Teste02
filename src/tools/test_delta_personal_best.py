from __future__ import annotations

import unittest

from src.widget.delta.delta_personal_best import (
    DeltaPositionSynchronizer,
    interpolate_trace_elapsed,
)


class DeltaPersonalBestTests(unittest.TestCase):
    def test_interpolates_elapsed_at_same_track_distance(self) -> None:
        trace = [
            {"distance": 0.0, "elapsed_s": 0.0},
            {"distance": 0.25, "elapsed_s": 25.0},
            {"distance": 0.50, "elapsed_s": 48.0},
            {"distance": 0.75, "elapsed_s": 74.0},
            {"distance": 1.0, "elapsed_s": 100.0},
        ]
        self.assertAlmostEqual(interpolate_trace_elapsed(trace, 0.625), 61.0)

    def test_clamps_to_trace_boundaries(self) -> None:
        trace = [
            {"distance": 0.1, "elapsed_s": 5.0},
            {"distance": 0.9, "elapsed_s": 95.0},
        ]
        self.assertEqual(interpolate_trace_elapsed(trace, -0.1), 5.0)
        self.assertEqual(interpolate_trace_elapsed(trace, 1.1), 95.0)

    def test_ignores_invalid_samples_and_orders_points(self) -> None:
        trace = [
            {"distance": 1.0, "elapsed_s": 100.0},
            {"distance": "bad", "elapsed_s": 20.0},
            {"distance": 0.0, "elapsed_s": 0.0},
            {"distance": 0.5, "elapsed_s": float("nan")},
            {"distance": 0.5, "elapsed_s": 50.0},
        ]
        self.assertAlmostEqual(interpolate_trace_elapsed(trace, 0.25), 25.0)

    def test_completed_lap_delta_uses_full_lap_times(self) -> None:
        from src.widget.delta.delta_personal_best import completed_lap_delta

        self.assertAlmostEqual(completed_lap_delta(56.0, 52.0), 4.0)
        self.assertAlmostEqual(completed_lap_delta(50.0, 52.0), -2.0)
        self.assertIsNone(completed_lap_delta(56.0, 52.0, invalidated=True))
        self.assertIsNone(completed_lap_delta(0.0, 52.0))

    def test_position_sync_estimates_distance_when_shared_memory_is_static(self) -> None:
        sync = DeltaPositionSynchronizer()
        self.assertAlmostEqual(sync.update(100.0, 2.0, 100.0, 1), 100.0)
        estimated = sync.update(100.0, 2.1, 100.0, 1)
        self.assertAlmostEqual(estimated, 100.0 + (100.0 / 3.6) * 0.1, places=5)

    def test_position_sync_holds_small_backward_jitter_and_resets_on_new_lap(self) -> None:
        sync = DeltaPositionSynchronizer()
        start = sync.update(1000.0, 20.0, 180.0, 5)
        held = sync.update(995.0, 20.05, 180.0, 5)
        self.assertEqual(start, held)
        next_lap = sync.update(3.0, 0.1, 100.0, 6)
        self.assertEqual(next_lap, 3.0)

    def test_returns_none_when_trace_has_insufficient_valid_points(self) -> None:
        self.assertIsNone(interpolate_trace_elapsed([], 0.5))
        self.assertIsNone(interpolate_trace_elapsed(
            [{"distance": 0.5, "elapsed_s": 50.0}], 0.5
        ))
        self.assertIsNone(interpolate_trace_elapsed(
            [
                {"distance": 0.5, "elapsed_s": 50.0},
                {"distance": 0.5, "elapsed_s": 51.0},
            ],
            0.5,
        ))


if __name__ == "__main__":
    unittest.main()
