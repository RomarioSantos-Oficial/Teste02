from __future__ import annotations

import unittest

from src.widget.standings.standings_assets import (
    badge_asset_key,
    country_code,
    detect_manufacturer,
    flag_emoji,
)


class StandingsAssetsTests(unittest.TestCase):
    def test_fastest_lap_clock_asset_exists(self) -> None:
        from pathlib import Path

        project_root = Path(__file__).resolve().parents[2]
        self.assertTrue(
            (project_root / "images" / "incos01" / "relogio.png").is_file()
        )


    def test_installed_lmu_manufacturer_aliases(self) -> None:
        expected = {
            "Genesis_GMR001_2026": "Genesis",
            "ADESS_AD25_2026": "Adess",
            "Duqueine_D09LMP3_2026": "Duqueine",
            "Ligier_JSP325_2025": "Ligier",
            "Ginetta_G61Evo_2025": "Ginetta",
            "Vandervell_680_2023": "Vanwall",
            "SGC_007_2023": "Glickenhaus",
        }
        for vehicle, brand in expected.items():
            with self.subTest(vehicle=vehicle):
                self.assertEqual(detect_manufacturer(vehicle), brand)

    def test_local_badge_names_match_api_aliases(self) -> None:
        expected = {
            "SRNoob": "rookie",
            "SRProbation": "probation",
            "SRWarning": "warning",
            "SRClean": "gooddriver",
            "SRSaint": "trusteddrive",
            "S397": "staff",
            "Content Creator": "creator",
            "IRL Driver": "realdriver",
        }
        for value, asset in expected.items():
            with self.subTest(value=value):
                self.assertEqual(badge_asset_key(value), asset)

    def test_country_flags_accept_alpha3_codes_from_online_profiles(self) -> None:
        for value, expected in (("BRA", "BR"), ("GBR", "GB"), ("USA", "US")):
            with self.subTest(value=value):
                self.assertEqual(country_code("", value), expected)

        self.assertEqual(country_code("Brazil", "BRA"), "BR")
        self.assertEqual(flag_emoji("", "BRA"), flag_emoji("", "BR"))


if __name__ == "__main__":
    unittest.main()
