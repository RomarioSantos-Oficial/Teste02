from __future__ import annotations

import unittest
from types import SimpleNamespace

from src.widget.delta.delta_sector_tracker import DeltaSectorTracker
from src.widget.delta.delta_models import SECTOR_BETTER, SECTOR_WORSE


class DeltaSectorTrackerPersonalBestTests(unittest.TestCase):
    def test_sector_deltas_use_archived_personal_best_splits(self) -> None:
        player = SimpleNamespace(
            is_player=True, vehicle_class="LMGT3",
            current_sector1_s=34.4, current_sector2_s=35.6, last_sector3_s=34.2,
            best_sector1_s=30.0, best_sector2_s=30.0, best_sector3_s=30.0,
        )
        tracker = DeltaSectorTracker(tolerance_s=0.001)
        tracker.update(
            SimpleNamespace(drivers=[player]),
            "silverstone-race",
            personal_best_sectors=(34.0, 35.0, 33.0),
        )
        shown = {item.label: item for item in tracker._display}
        self.assertAlmostEqual(shown["S1"].delta_s, 0.4)
        self.assertAlmostEqual(shown["S2"].delta_s, 0.6)
        self.assertAlmostEqual(shown["S3"].delta_s, 1.2)
        self.assertEqual(shown["S1"].status, SECTOR_WORSE)
        self.assertEqual(shown["S2"].status, SECTOR_WORSE)
        self.assertEqual(shown["S3"].status, SECTOR_WORSE)

    def test_sector_reference_does_not_drift_to_an_isolated_faster_split(self) -> None:
        player = SimpleNamespace(
            is_player=True, vehicle_class="LMGT3",
            current_sector1_s=33.0, current_sector2_s=35.5, last_sector3_s=34.0,
            best_sector1_s=30.0, best_sector2_s=30.0, best_sector3_s=30.0,
        )
        tracker = DeltaSectorTracker(tolerance_s=0.001)
        session = SimpleNamespace(drivers=[player])
        tracker.update(session, "silverstone-race", personal_best_sectors=(34.0, 35.0, 33.0))
        player.current_sector1_s = 33.5
        tracker.update(session, "silverstone-race", personal_best_sectors=(34.0, 35.0, 33.0))
        shown = {item.label: item for item in tracker._display}
        self.assertAlmostEqual(shown["S1"].delta_s, -0.5)
        self.assertEqual(shown["S1"].status, SECTOR_BETTER)


if __name__ == "__main__":
    unittest.main()
