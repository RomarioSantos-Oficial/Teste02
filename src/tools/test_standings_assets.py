from __future__ import annotations

import unittest

from src.widget.standings.standings_assets import (
    badge_asset_key,
    detect_manufacturer,
)


class StandingsAssetsTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
