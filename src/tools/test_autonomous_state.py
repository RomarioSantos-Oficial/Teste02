from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.autonomous.driver import ObserveDriver
from src.autonomous.recorder import TelemetryRecorder
from src.autonomous.route import RecordedRouteRepository
from src.autonomous.state import build_unified_state
from src.telemetry.models import DriverData, PlayerData, SessionData, WheelData


class AutonomousStateTests(unittest.TestCase):
    def test_builds_state_from_existing_session_models(self) -> None:
        session = SessionData(
            connected=True,
            track_name="Le Mans",
            track_length_m=13000.0,
            session_name="Practice",
                raining=0.2,
                avg_path_wetness=0.3,
                local_api_available=True,
                in_control_of_vehicle=True,
                track_limits_steps_per_penalty=12,
                track_limits_steps_per_point=4,
                player=PlayerData(
                vehicle_model="Example GT3",
                vehicle_class="LMGT3",
                speed_kmh=180.0,
                gear=4,
                fuel_liters=42.0,
                    lap=2,
                    track_limits_steps=8,
                    last_impact_magnitude=2.5,
                    current_lap_invalidated=True,
                    wheels=[WheelData(pressure_kpa=180.0, grip_fraction=0.9)],
            ),
            drivers=[
                DriverData(
                    slot_id=1, is_player=True, lap_distance_m=1250.0,
                    path_lateral_m=0.2, track_edge_m=6.5,
                ),
                DriverData(
                    slot_id=3, vehicle_class="Hypercar", speed_kmh=200.0,
                    lap_distance_m=1300.0, path_lateral_m=-0.4,
                ),
            ],
        )
        state = build_unified_state(session, timestamp_s=123.0)
        self.assertEqual(state.vehicle.speed_m_s, 50.0)
        self.assertEqual(state.vehicle.wheels[0]["pressure_kpa"], 180.0)
        self.assertEqual(state.weather.wetness_average, 0.3)
        self.assertEqual(state.vehicle.lap_distance_m, 1250.0)
        self.assertEqual(state.vehicle.lateral_position_m, 0.2)
        self.assertEqual(state.vehicle.track_limits_current, 2.0)
        self.assertEqual(state.vehicle.track_limits_limit, 3.0)
        self.assertEqual(state.vehicle.last_impact_magnitude, 2.5)
        self.assertTrue(state.vehicle.current_lap_invalidated)
        self.assertTrue(state.in_control_of_vehicle)
        self.assertTrue(state.local_api_available)
        self.assertEqual(state.traffic[0].relative_distance_m, 50.0)
        self.assertIn("track_curvature", state.provenance)

    def test_observe_never_emits_or_applies_controls(self) -> None:
        state = build_unified_state(SessionData(connected=True), timestamp_s=1.0)
        decision = ObserveDriver().decide(state)
        self.assertEqual(decision.mode, "OBSERVE")
        self.assertIsNone(decision.steering)
        self.assertIsNone(decision.throttle)
        self.assertIsNone(decision.brake)
        self.assertFalse(decision.applied)

    def test_recorder_writes_versioned_jsonl(self) -> None:
        state = build_unified_state(SessionData(), timestamp_s=2.0)
        decision = ObserveDriver().decide(state)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "samples.jsonl"
            TelemetryRecorder(path).append(state, decision)
            row = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(row["schema_version"], 1)
        self.assertEqual(row["decision"]["mode"], "OBSERVE")

    def test_recorded_route_preview_matches_track_and_wraps_lap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test_track.json"
            path.write_text(json.dumps({
                "track_key": "test_track_1000", "track_name": "Test Track",
                "track_length_m": 1000.0, "points": [
                    {"distance_m": 10.0, "world_x": 1.0, "world_y": 2.0},
                    {"distance_m": 40.0, "world_x": 3.0, "world_y": 4.0},
                ],
            }), encoding="utf-8")
            session = SessionData(
                connected=True, track_name="Test Track", track_length_m=1000.0,
                player=PlayerData(speed_kmh=100.0),
                drivers=[DriverData(is_player=True, lap_distance_m=990.0)],
            )
            state = build_unified_state(session, timestamp_s=1.0)
            decision = ObserveDriver(RecordedRouteRepository(directory)).decide(state)
        self.assertEqual(decision.route_preview["source"], "RECORDED_MAP")
        self.assertEqual(decision.route_preview["target_distance_m"], 40.0)
        self.assertEqual(decision.route_preview["target_world_xy_m"], (3.0, 4.0))
        self.assertIsNone(decision.steering)

    def test_route_monitor_flags_off_route_and_wrong_direction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "test_track.json").write_text(json.dumps({
                "track_key": "test_track_1000", "track_name": "Test Track",
                "track_length_m": 1000.0, "points": [
                    {"distance_m": 10.0, "world_x": 0.0, "world_y": 0.0},
                    {"distance_m": 40.0, "world_x": 10.0, "world_y": 0.0},
                    {"distance_m": 70.0, "world_x": 10.0, "world_y": 10.0},
                ],
            }), encoding="utf-8")
            repository = RecordedRouteRepository(directory)
            def get_assessment(x: float, z: float, forward_x: float, forward_z: float) -> str:
                session = SessionData(
                    connected=True, track_name="Test Track", track_length_m=1000.0,
                    player=PlayerData(speed_kmh=60.0),
                    drivers=[DriverData(
                        is_player=True, lap_distance_m=20.0, world_x=x, world_z=z,
                        forward_x=forward_x, forward_z=forward_z,
                    )],
                )
                state = build_unified_state(session, timestamp_s=1.0)
                return repository.assess(state).status
            self.assertEqual(get_assessment(5.0, 0.0, 1.0, 0.0), "ON_ROUTE")
            self.assertEqual(get_assessment(5.0, -30.0, 1.0, 0.0), "OFF_ROUTE")
            self.assertEqual(get_assessment(5.0, 0.0, -1.0, 0.0), "WRONG_DIRECTION")


if __name__ == "__main__":
    unittest.main()
