from __future__ import annotations

import time
import unittest

from src.telemetry.lmu_rest_client import LMURestSnapshot
from src.telemetry.lmu_rest_enrichment import _driver_compounds, apply_rest_snapshot
from src.telemetry.models import DriverData, PlayerData, SessionData, WheelData
from src.ui.overlay_manager import OverlayManager


class LMURestEnrichmentTests(unittest.TestCase):
    def test_driver_compounds_keep_wheel_positions(self) -> None:
        self.assertEqual(
            _driver_compounds(
                {"tireCompounds": ["Soft", "", "Hard", "Wet"]}
            ),
            ["Soft", "", "Hard", "Wet"],
        )

    class OverlayProbe:
        @staticmethod
        def _log_overlay_decision(*_args, **_kwargs) -> None:
            pass

    def make_session(self) -> SessionData:
        return SessionData(
            connected=True,
            session=1,
            in_realtime=True,
            application_location=3,
            player_has_vehicle=True,
            player_synced=True,
            game_phase=5,
            remaining_time_s=600.0,
            player=PlayerData(
                fuel_liters=10.0,
                fuel_capacity_liters=100.0,
                wheels=[WheelData() for _ in range(4)],
            ),
            drivers=[
                DriverData(
                    slot_id=18,
                    driver_name="Alice Driver",
                    is_player=True,
                ),
                DriverData(
                    slot_id=12,
                    driver_name="Bob Driver",
                ),
            ],
        )

    def test_merges_authoritative_local_values(self) -> None:
        now = time.monotonic()
        payloads = {
            "game_state": {
                "inControlOfVehicle": True,
                "inMonitor": False,
                "playerVehicleLoaded": True,
                "isReplayActive": False,
                "raceFinished": False,
                "gamePhase": "GPHASE_GREEN",
                "PitState": "NONE",
            },
            "navigation_state": {
                "state": {
                    "navigationState": "NAV_EVENT",
                    "gameState": "GSTATE_DYN",
                    "gameSession": "PRACTICE1",
                }
            },
            "session_info": {
                "session": "PRACTICE1",
                "serverName": "Test Server",
                "splitLabel": "18/30",
                "gameMode": "RACE",
                "playerName": "Alice Driver",
                "trackName": "Test Circuit",
                "maxPlayers": 38,
                "numberOfPlayers": 20,
                "numberOfVehicles": 19,
                "maxTime": 3600.0,
                "maximumLaps": 4294967295,
                "currentEventTime": 123.0,
                "gamePhase": 5,
                "inRealtime": True,
                "ambientTemp": 27.5,
                "trackTemp": 38.25,
                "raining": 0.2,
                "averagePathWetness": 0.3,
                "timeRemainingInGamePhase": 512.0,
                "sectorFlag": ["GREEN", "YELLOW", "GREEN"],
                "windSpeed": {"velocity": 2.0, "x": 2.0, "y": 0.0, "z": 0.0},
            },
            "session_settings": {
                "SESSSET_Fuel_Usage": {
                    "currentValue": 250.75,
                    "stringValue": "250.75x",
                }
            },
            "standings": [
                {
                    "slotID": 18,
                    "driverName": "Alice Driver",
                    "player": True,
                    "carNumber": "69",
                    "fullTeamName": "Team Test",
                    "position": 3,
                    "lapsCompleted": 4,
                    "sector": "SECTOR2",
                    "lapDistance": 1234.5,
                    "bestLapTime": 88.2,
                    "lastLapTime": 89.3,
                    "timeBehindLeader": 4.5,
                    "timeBehindNext": 1.2,
                    "lapsBehindLeader": 1,
                    "lapsBehindNext": 0,
                    "tireCompounds": ["Wet", "Wet", "Medium", "Medium"],
                    "damagePercent": 18,
                    "penalties": 1,
                    "penaltyType": "DRIVE_THROUGH",
                    "trackLimitsSteps": 12,
                    "countLapFlag": "COUNT_LAP_ONLY",
                    "veFraction": 0.72,
                    "fuelFraction": 0.55,
                    "drsActive": True,
                    "pitting": False,
                    "pitstops": 1,
                    "flag": "BLUE",
                    "finishStatus": "FSTAT_NONE",
                    "attackMode": {
                        "remainingCount": 2,
                        "totalCount": 3,
                        "timeRemaining": 12.5,
                    },
                }
            ],
            "vehicle_condition": {
                "fuel": 55.0,
                "fuelCapacity": 100.0,
                "vehicleDamage": 0.12,
                "tireCondition": [0.9, 0.8, 0.7, 0.6],
                "brakeCondition": [1.0, 0.9, 0.8, 0.7],
                "suspensionDamage": [0.0, 0.1, 0.0, 0.0],
            },
            "tire_info": {
                "frontLeft": {
                    "leftTemperature": 300.15,
                    "centerTemperature": 301.15,
                    "rightTemperature": 302.15,
                    "pressure": 140.0,
                    "load": 350.0,
                }
            },
            "weather": {"practice": {"START": {"RainChance": 20}}},
        }
        session = apply_rest_snapshot(
            self.make_session(),
            LMURestSnapshot(
                payloads=payloads,
                updated_at={key: now for key in payloads},
                available=True,
                last_success_at=now,
            ),
        )

        self.assertEqual(session.sector_flags, (0, 1, 0))
        self.assertAlmostEqual(session.ambient_temp_c, 27.5)
        self.assertAlmostEqual(session.track_temp_c, 38.25)
        self.assertAlmostEqual(session.remaining_time_s, 512.0)
        self.assertEqual(session.max_laps, 0)
        self.assertEqual(session.server_name, "Test Server")
        self.assertEqual(session.split_label, "18/30")
        self.assertEqual(session.track_name, "Test Circuit")
        self.assertEqual(session.max_players, 38)
        self.assertEqual(session.number_of_players, 20)
        self.assertEqual(session.number_of_vehicles, 19)
        self.assertAlmostEqual(session.fuel_usage_multiplier or 0.0, 250.75)
        self.assertIn("SESSSET_Fuel_Usage", session.session_settings)
        self.assertAlmostEqual(session.current_event_time_s, 123.0)
        self.assertEqual(session.navigation_state, "NAV_EVENT")
        self.assertTrue(session.in_control_of_vehicle)
        self.assertFalse(session.in_monitor)
        self.assertEqual(session.player.fuel_liters, 55.0)
        self.assertAlmostEqual(session.player.vehicle_damage, 0.12)
        self.assertAlmostEqual(session.player.wheels[0].wear, 0.9)
        self.assertAlmostEqual(session.player.wheels[0].surface_left_c, 27.0)
        self.assertAlmostEqual(session.player.wheels[0].pressure_kpa, 140.0)
        player_row = session.drivers[0]
        self.assertEqual(player_row.car_number, "69")
        self.assertEqual(player_row.team_name, "Team Test")
        self.assertEqual(player_row.position, 3)
        self.assertEqual(player_row.laps, 4)
        self.assertEqual(player_row.current_sector, 2)
        self.assertAlmostEqual(player_row.best_lap_s, 88.2)
        self.assertAlmostEqual(player_row.last_lap_s, 89.3)
        self.assertAlmostEqual(player_row.gap_leader_s, 4.5)
        self.assertAlmostEqual(player_row.gap_ahead_s, 1.2)
        self.assertEqual(player_row.laps_behind_leader, 1)
        self.assertEqual(
            player_row.tire_compounds,
            ["Wet", "Wet", "Medium", "Medium"],
        )
        self.assertEqual(player_row.damage_percent, 18.0)
        self.assertFalse(player_row.damage_is_estimated)
        self.assertEqual(player_row.penalty_type, "DRIVE_THROUGH")
        self.assertEqual(player_row.track_limits_steps, 12)
        self.assertTrue(player_row.current_lap_invalidated)
        self.assertEqual(player_row.count_lap_flag_name, "COUNT_LAP_ONLY")
        self.assertAlmostEqual(player_row.virtual_energy_fraction or 0.0, 0.72)
        self.assertTrue(player_row.drs_active)
        self.assertEqual(player_row.flag, 6)
        self.assertEqual(player_row.attack_mode_remaining_count, 2)

    def test_overlay_visibility_prefers_fresh_rest_state(self) -> None:
        session = self.make_session()
        session.local_api_available = True
        session.local_api_age_s = 0.1
        session.in_control_of_vehicle = True
        session.player_vehicle_loaded = True
        session.in_monitor = False
        session.in_realtime_rest = True
        session.is_replay_active = False
        session.race_finished = False
        session.navigation_state = "NAV_EVENT"
        probe = self.OverlayProbe()
        self.assertTrue(
            OverlayManager._session_allows_overlays(probe, session)
        )

        session.in_monitor = True
        session.in_control_of_vehicle = False
        self.assertFalse(
            OverlayManager._session_allows_overlays(probe, session)
        )

    def test_stale_rest_state_keeps_shared_memory_fallback(self) -> None:
        session = self.make_session()
        session.local_api_available = True
        session.local_api_age_s = 20.0
        session.in_monitor = True
        self.assertTrue(
            OverlayManager._session_allows_overlays(
                self.OverlayProbe(),
                session,
            )
        )

        session.application_location = 2
        self.assertFalse(
            OverlayManager._session_allows_overlays(
                self.OverlayProbe(),
                session,
            )
        )

    def test_fresh_api_hides_menu_loading_and_uncontrolled_car(self) -> None:
        session = self.make_session()
        session.local_api_available = True
        session.local_api_age_s = 0.1
        session.in_control_of_vehicle = False
        session.player_vehicle_loaded = True
        session.in_monitor = False
        session.is_replay_active = False
        session.navigation_state = "NAV_MAIN_MENU"
        self.assertFalse(
            OverlayManager._session_allows_overlays(
                self.OverlayProbe(),
                session,
            )
        )

        session.navigation_state = "NAV_EVENT"
        session.navigation_loading = True
        self.assertFalse(
            OverlayManager._session_allows_overlays(
                self.OverlayProbe(),
                session,
            )
        )

        session.navigation_loading = False
        self.assertFalse(
            OverlayManager._session_allows_overlays(
                self.OverlayProbe(),
                session,
            )
        )

    def test_overlay_stays_visible_after_leader_finishes_while_player_drives(self) -> None:
        session = self.make_session()
        session.local_api_available = True
        session.local_api_age_s = 0.1
        session.in_control_of_vehicle = True
        session.player_vehicle_loaded = True
        session.in_monitor = False
        session.is_replay_active = False
        session.navigation_state = "NAV_EVENT"
        session.race_finished = True
        session.remaining_time_s = 0.0
        session.game_phase = 8
        self.assertTrue(
            OverlayManager._session_allows_overlays(self.OverlayProbe(), session)
        )

    def test_quick_lap_transient_phase_stays_visible_while_in_control(self) -> None:
        session = self.make_session()
        session.local_api_available = True
        session.local_api_age_s = 0.1
        session.in_control_of_vehicle = True
        session.player_vehicle_loaded = True
        session.in_monitor = False
        session.is_replay_active = False
        session.navigation_state = "NAV_EVENT"
        session.game_phase = 9
        self.assertTrue(
            OverlayManager._session_allows_overlays(self.OverlayProbe(), session)
        )

    def test_finished_phase_hides_after_player_loses_control(self) -> None:
        session = self.make_session()
        session.local_api_available = True
        session.local_api_age_s = 0.1
        session.in_control_of_vehicle = False
        session.player_vehicle_loaded = True
        session.in_monitor = False
        session.is_replay_active = False
        session.navigation_state = "NAV_EVENT"
        session.game_phase = 8
        self.assertFalse(
            OverlayManager._session_allows_overlays(self.OverlayProbe(), session)
        )

if __name__ == "__main__":
    unittest.main()
