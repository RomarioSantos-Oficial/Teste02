from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.private_data import clear_online_debug, ensure_private_data_directories


class PrivateDataTests(unittest.TestCase):
    def test_clear_online_debug_preserves_maps_and_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            debug = root / "data" / "online_debug"
            nested = debug / "nested"
            nested.mkdir(parents=True)
            (debug / "session.log").write_text("private", encoding="utf-8")
            (nested / "dump.json").write_text("{}", encoding="utf-8")
            track_map = root / "data" / "track_maps" / "user_map.json"
            profile = root / "data" / "online_profiles" / "user_cache.json"
            track_map.parent.mkdir(parents=True)
            profile.parent.mkdir(parents=True)
            track_map.write_text("{}", encoding="utf-8")
            profile.write_text("{}", encoding="utf-8")

            self.assertEqual(clear_online_debug(root), 2)

            self.assertTrue(debug.is_dir())
            self.assertEqual(list(debug.iterdir()), [])
            self.assertTrue(track_map.is_file())
            self.assertTrue(profile.is_file())

    def test_ensure_directories_does_not_delete_existing_map(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            track_map = root / "data" / "track_maps" / "saved.json"
            track_map.parent.mkdir(parents=True)
            track_map.write_text("{}", encoding="utf-8")

            directories = ensure_private_data_directories(root)

            self.assertEqual(len(directories), 3)
            self.assertTrue(all(directory.is_dir() for directory in directories))
            self.assertTrue(track_map.is_file())

    def test_build_sources_exclude_private_data_files(self) -> None:
        project_root = Path(__file__).resolve().parents[2]
        spec = (project_root / "build" / "SectorFlow.spec").read_text(
            encoding="utf-8"
        )
        for directory in ("online_debug", "online_profiles", "track_maps"):
            self.assertNotIn(
                f"PROJECT_ROOT / 'data/{directory}'",
                spec,
                directory,
            )


if __name__ == "__main__":
    unittest.main()
