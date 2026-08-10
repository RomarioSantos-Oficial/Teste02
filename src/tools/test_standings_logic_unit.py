from __future__ import annotations

import unittest

from src.telemetry.models import DriverData, PlayerData, SessionData
from src.widget.standings.standings_logic import StandingsLogic
from src.widget.standings.standings_models import DriverMetadata


class StandingsLogicUnitTests(unittest.TestCase):
    def test_slow_car_outside_pits_is_marked_yellow_like_tinypedal(self) -> None:
        session = SessionData(
            connected=True,
            session=10,
            game_phase=5,
            drivers=[
                DriverData(
                    slot_id=4,
                    driver_name="Stopped Car",
                    vehicle_class="LMGT3",
                    position=1,
                    speed_kmh=12.0,
                ),
                DriverData(
                    slot_id=5,
                    driver_name="Moving Car",
                    vehicle_class="LMGT3",
                    position=2,
                    speed_kmh=120.0,
                ),
            ],
        )
        rows = StandingsLogic({}).build(session, {}, "MEM").categories[0].rows
        by_name = {row.driver_name: row for row in rows}
        self.assertTrue(by_name["Stopped Car"].under_yellow)
        self.assertFalse(by_name["Moving Car"].under_yellow)

    def test_race_uses_class_leader_for_header_and_shared_fallbacks(self) -> None:
        session = SessionData(
            connected=True,
            session=10,
            remaining_time_s=900.0,
            track_length_m=5000.0,
            track_limits_steps_per_point=4,
            track_limits_steps_per_penalty=24,
            player=PlayerData(track_limits_steps=20),
            drivers=[
                DriverData(
                    slot_id=1,
                    driver_name="Class Leader",
                    vehicle_class="LMGT3",
                    position=1,
                    laps=12,
                    lap_distance_m=2500.0,
                    last_lap_s=120.0,
                    tire_compounds=["Wet"] * 4,
                    damage_percent=25.0,
                    damage_is_estimated=True,
                ),
                DriverData(
                    slot_id=2,
                    driver_name="Player",
                    vehicle_class="LMGT3",
                    position=2,
                    laps=11,
                    lap_distance_m=1000.0,
                    last_lap_s=121.0,
                    is_player=True,
                    tire_compounds=["Soft", "Soft", "Hard", "Hard"],
                ),
            ],
        )

        metadata = {
            "classleader": DriverMetadata(
                driver_name="Class Leader",
                driver_rank="Bronze 3",
                driver_rank_progress=50.0,
            ),
            "player": DriverMetadata(
                driver_name="Player",
                driver_rank="Silver 0",
                driver_rank_progress=50.0,
                estimated_driver_rank_gain=-5.0,
            ),
        }
        view = StandingsLogic({}).build(session, metadata, "MEM")
        category = view.categories[0]
        rows = {row.driver_name: row for row in category.rows}

        self.assertEqual(category.current_lap, 13)
        self.assertEqual(category.total_laps_text, "20.0")
        self.assertEqual(rows["Class Leader"].tyre_compound, "Wet")
        self.assertEqual(rows["Player"].tyre_compound, "Soft/Hard")
        self.assertEqual(rows["Player"].track_limits_text, "5/6")
        self.assertEqual(rows["Player"].penalty_text, "--")
        self.assertEqual(rows["Class Leader"].damage_percent, 25.0)
        self.assertTrue(rows["Class Leader"].damage_is_estimated)
        self.assertEqual(category.dr_sof_rank, "S1")
        self.assertAlmostEqual(category.dr_sof_progress or 0.0, 0.0)
        self.assertEqual(category.dr_sof_drivers, 2)
        self.assertEqual(rows["Player"].estimated_driver_rank_gain, -5.0)

    def test_practice_uses_player_lap_for_player_class(self) -> None:
        session = SessionData(
            connected=True,
            session=1,
            drivers=[
                DriverData(
                    slot_id=1,
                    driver_name="Leader",
                    vehicle_class="Hypercar",
                    position=1,
                    laps=8,
                ),
                DriverData(
                    slot_id=2,
                    driver_name="Player",
                    vehicle_class="Hypercar",
                    position=2,
                    laps=3,
                    is_player=True,
                ),
            ],
        )

        category = StandingsLogic({}).build(session, {}, "MEM").categories[0]
        self.assertEqual(category.current_lap, 4)
        self.assertEqual(category.total_laps_text, "--")

    def test_category_and_row_limits_are_configurable(self) -> None:
        drivers = [
            DriverData(
                slot_id=index,
                driver_name=f"GT Driver {index}",
                vehicle_class="LMGT3",
                position=index,
                laps=3,
                is_player=index == 4,
            )
            for index in range(1, 8)
        ]
        drivers.extend(
            DriverData(
                slot_id=20 + index,
                driver_name=f"Hyper Driver {index}",
                vehicle_class="Hypercar",
                position=10 + index,
                laps=4,
            )
            for index in range(1, 8)
        )
        session = SessionData(connected=True, session=10, drivers=drivers)

        player_only = StandingsLogic(
            {
                "maximum_categories": 1,
                "player_category_rows": 1,
                "other_category_rows": 5,
            }
        ).build(session, {}, "MEM")
        self.assertEqual(len(player_only.categories), 1)
        self.assertEqual(len(player_only.categories[0].rows), 1)
        self.assertTrue(player_only.categories[0].rows[0].is_player)

        two_classes = StandingsLogic(
            {
                "maximum_categories": 2,
                "player_category_rows": 4,
                "other_category_rows": 2,
            }
        ).build(session, {}, "MEM")
        self.assertEqual(len(two_classes.categories), 2)
        player_category = next(
            category
            for category in two_classes.categories
            if any(row.is_player for row in category.rows)
        )
        other_category = next(
            category
            for category in two_classes.categories
            if category is not player_category
        )
        self.assertEqual(len(player_category.rows), 4)
        self.assertEqual(len(other_category.rows), 2)

    def test_distant_yellow_and_penalty_do_not_override_selected_rows(self) -> None:
        drivers = [
            DriverData(
                slot_id=index,
                driver_name=f"Driver {index}",
                vehicle_class="LMP2",
                position=index,
                laps=4,
                under_yellow=index == 5,
                penalties=1 if index == 4 else 0,
                penalty_time_s=10.0 if index == 4 else 0.0,
            )
            for index in range(1, 6)
        ]
        session = SessionData(connected=True, session=10, drivers=drivers)
        category = StandingsLogic(
            {"maximum_categories": 1, "other_category_rows": 2}
        ).build(session, {}, "MEM").categories[0]

        self.assertEqual([row.slot_id for row in category.rows], [1, 2])

    def test_finish_line_crossing_does_not_create_false_lap_gap(self) -> None:
        session = SessionData(
            connected=True,
            session=10,
            track_length_m=5000.0,
            drivers=[
                DriverData(
                    slot_id=1, driver_name="Ahead", vehicle_class="LMGT3",
                    position=1, laps=10, lap_distance_m=10.0,
                    gap_leader_s=29.0, laps_behind_leader=-1,
                ),
                DriverData(
                    slot_id=2, driver_name="Player", vehicle_class="LMGT3",
                    position=2, laps=9, lap_distance_m=4990.0,
                    gap_leader_s=30.0, laps_behind_leader=0, is_player=True,
                ),
            ],
        )
        rows = StandingsLogic(
            {"maximum_categories": 1, "player_category_rows": 2}
        ).build(session, {}, "API").categories[0].rows
        by_name = {row.driver_name: row for row in rows}
        self.assertEqual(by_name["Ahead"].gap_text, "-1.0")

    def test_relative_excludes_dnf_dq_and_garage(self) -> None:
        session = SessionData(
            connected=True,
            session=10,
            track_length_m=5000.0,
            drivers=[
                DriverData(slot_id=1, driver_name="Player", vehicle_class="LMGT3", position=1, lap_distance_m=1000.0, best_lap_s=100.0, is_player=True),
                DriverData(slot_id=2, driver_name="Active", vehicle_class="LMGT3", position=2, lap_distance_m=1020.0, best_lap_s=100.0),
                DriverData(slot_id=3, driver_name="DNF", vehicle_class="LMGT3", position=3, lap_distance_m=1010.0, best_lap_s=100.0, finish_status=2, finish_status_name="DNF"),
                DriverData(slot_id=4, driver_name="DQ", vehicle_class="LMGT3", position=4, lap_distance_m=990.0, best_lap_s=100.0, finish_status=3, finish_status_name="DQ"),
                DriverData(slot_id=5, driver_name="Garage", vehicle_class="LMGT3", position=5, lap_distance_m=1005.0, best_lap_s=100.0, in_garage=True),
            ],
        )
        rows = StandingsLogic(
            {"relative_mode": True, "relative_cars_ahead": 5, "relative_cars_behind": 5}
        ).build(session, {}, "API").categories[0].rows
        self.assertEqual({row.driver_name for row in rows}, {"Player", "Active"})

    def test_opponent_track_limits_use_per_vehicle_steps(self) -> None:
        session = SessionData(
            connected=True,
            session=10,
            track_limits_steps_per_point=4,
            track_limits_steps_per_penalty=24,
            drivers=[
                DriverData(
                    slot_id=1,
                    driver_name="Opponent",
                    vehicle_class="LMGT3",
                    position=1,
                    track_limits_steps=12,
                )
            ],
        )
        row = StandingsLogic({}).build(session, {}, "MEM").categories[0].rows[0]
        self.assertEqual(row.track_limits_text, "3/6")

    def test_unknown_penalty_type_is_not_reported_as_p1(self) -> None:
        session = SessionData(
            connected=True,
            session=10,
            drivers=[
                DriverData(
                    slot_id=1,
                    driver_name="Penalized",
                    vehicle_class="LMGT3",
                    position=1,
                    penalties=1,
                )
            ],
        )
        row = StandingsLogic({}).build(session, {}, "MEM").categories[0].rows[0]
        self.assertEqual(row.penalty_text, "PEN")


if __name__ == "__main__":
    unittest.main()
