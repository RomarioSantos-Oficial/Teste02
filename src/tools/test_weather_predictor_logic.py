from __future__ import annotations

import unittest
from types import SimpleNamespace

from src.widget.weather.weather_models import WeatherSample
from src.widget.weather.weather_predictor import WeatherTrendPredictor


class WeatherClassificationTests(unittest.TestCase):
    def test_live_cloud_index_does_not_mean_rain_when_raining_is_zero(self) -> None:
        predictor = WeatherTrendPredictor()
        session = SimpleNamespace(
            track_name="Track",
            session=1,
            max_laps=0,
            track_temp_c=22.0,
            ambient_temp_c=23.0,
            raining=0.0,
            avg_path_wetness=0.0,
            dark_cloud=0.0,
            cloud_coverage=7,
            time_of_day=12 * 3600,
            wind_speed_kmh=0.0,
        )

        sample = predictor.add_session(session, now_s=10.0)

        self.assertEqual(sample.cloud_coverage, 4)
        self.assertEqual(
            predictor.weather_state(
                rain=sample.rain,
                wetness=sample.wetness,
                dark_cloud=sample.dark_cloud,
                cloud_coverage=sample.cloud_coverage,
                time_of_day_s=sample.time_of_day_s,
            ),
            "nublado",
        )

    def test_live_rain_severity_maps_to_rain_sky_type(self) -> None:
        predictor = WeatherTrendPredictor()
        session = SimpleNamespace(
            track_name="Track",
            session=1,
            max_laps=0,
            track_temp_c=22.0,
            ambient_temp_c=23.0,
            raining=0.12,
            avg_path_wetness=0.0,
            dark_cloud=0.0,
            cloud_coverage=2,
            time_of_day=12 * 3600,
            wind_speed_kmh=0.0,
        )

        sample = predictor.add_session(session, now_s=10.0)

        self.assertEqual(sample.cloud_coverage, 6)
        self.assertEqual(
            predictor.weather_state(
                rain=sample.rain,
                wetness=sample.wetness,
                dark_cloud=sample.dark_cloud,
                cloud_coverage=sample.cloud_coverage,
                time_of_day_s=sample.time_of_day_s,
            ),
            "Chuva",
        )

    def test_official_forecast_uses_equal_blocks_without_interpolating(self) -> None:
        predictor = WeatherTrendPredictor()
        sample = WeatherSample(
            timestamp_s=0.0,
            track_temp_c=22.0,
            air_temp_c=23.0,
            rain=0.0,
            wetness=0.0,
            dark_cloud=0.0,
            cloud_coverage=2,
            time_of_day_s=12 * 3600,
            wind_speed_kmh=0.0,
        )

        def field(value: int | float) -> dict[str, int | float]:
            return {"currentValue": value}

        def node(
            sky: int,
            chance: int,
            temperature: int = 25,
        ) -> dict[str, dict[str, int | float]]:
            return {
                "WNV_TEMPERATURE": field(temperature),
                "WNV_RAIN_CHANCE": field(chance),
                "WNV_SKY": field(sky),
            }

        session = SimpleNamespace(
            session=1,
            current_time_s=20500.0,
            remaining_time_s=15500.0,
            weather_schedule={
                "PRACTICE": {
                    "START": node(2, 0),
                    "NODE_25": node(3, 0),
                    "NODE_50": node(7, 60),
                    "NODE_75": node(4, 0, 27),
                    "FINISH": node(2, 0, 23),
                }
            },
        )

        forecast = predictor.official_forecast(session, sample, count=5, interval_minutes=5)

        self.assertIsNotNone(forecast)
        assert forecast is not None
        # At 57% progress each configured horizon is closest to NODE_75.
        # The past rainy NODE_50 must not be repeated in all five cards.
        self.assertEqual([item.minutes_ahead for item in forecast], [5, 10, 15, 20, 25])
        self.assertTrue(all(item.rain == 0.0 for item in forecast))
        self.assertEqual([item.air_temp_c for item in forecast], [27] * 5)
        self.assertEqual([item.cloud_coverage for item in forecast], [4] * 5)
        self.assertEqual(forecast[0].weather_state, "nublado")

    def test_warmup_uses_race_weather_schedule(self) -> None:
        predictor = WeatherTrendPredictor()
        sample = WeatherSample(0, 22, 23, 0, 0, 0, 2, 12 * 3600, 0)

        def node(sky: int, chance: int) -> dict[str, dict[str, int]]:
            return {
                "WNV_TEMPERATURE": {"currentValue": 25},
                "WNV_RAIN_CHANCE": {"currentValue": chance},
                "WNV_SKY": {"currentValue": sky},
            }

        session = SimpleNamespace(
            session=9,
            current_time_s=100,
            remaining_time_s=900,
            weather_schedule={
                "QUALIFY": {"START": node(7, 80)},
                "RACE": {
                    name: node(3, 0)
                    for name in ("START", "NODE_25", "NODE_50", "NODE_75", "FINISH")
                },
            },
        )
        forecast = predictor.official_forecast(session, sample, count=1)

        self.assertIsNotNone(forecast)
        assert forecast is not None
        self.assertEqual(forecast[0].weather_state, "nublado")
        self.assertEqual(forecast[0].rain, 0.0)


if __name__ == "__main__":
    unittest.main()
