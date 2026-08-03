from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QPixmap


@dataclass(slots=True)
class LogoMatch:
    manufacturer: str
    path: Path | None


class DeltaLogoManager:
    """Localiza a logo do fabricante usando o nome informado pelo LMU."""

    DEFAULT_ALIASES: dict[str, list[str]] = {
        "alpine": ["alpine", "a424"],
        "aston_martin": ["aston martin", "vantage", "valkyrie"],
        "bmw": ["bmw", "m hybrid", "m4 gt3", "m8 gte"],
        "cadillac": ["cadillac", "v-series", "v series"],
        "chevrolet": ["chevrolet", "corvette", "z06 gt3"],
        "ferrari": ["ferrari", "499p", "296 gt3", "488 gte"],
        "ford": ["ford", "mustang gt3"],
        "genesis": ["genesis", "gmr-001", "gmr 001"],
        "lamborghini": ["lamborghini", "sc63", "huracan"],
        "lexus": ["lexus", "rc f gt3"],
        "mclaren": ["mclaren", "720s"],
        "mercedes": ["mercedes", "amg gt3", "mercedes-amg"],
        "peugeot": ["peugeot", "9x8"],
        "porsche": ["porsche", "963", "911 gt3", "911 rsr"],
        "toyota": ["toyota", "gr010"],
        "vanwall": ["vanwall", "vandervell"],
        "oreca": ["oreca", "07 gibson"],
        "ligier": ["ligier", "js p"],
        "dallara": ["dallara"],
    }

    def __init__(
        self,
        project_root: Path,
        configured_directory: str | None = None,
    ) -> None:
        self.project_root = Path(project_root)
        self.logo_directory = self._resolve_directory(configured_directory)
        self.aliases = self._load_aliases()
        self._path_index = self._index_files()
        self._pixmap_cache: dict[Path, QPixmap] = {}

    def set_directory(self, configured_directory: str | None) -> None:
        self.logo_directory = self._resolve_directory(configured_directory)
        self.aliases = self._load_aliases()
        self._path_index = self._index_files()
        self._pixmap_cache.clear()

    def match(self, vehicle_text: str) -> LogoMatch:
        normalized = self._normalize(vehicle_text)

        for manufacturer, aliases in self.aliases.items():
            if any(self._normalize(alias) in normalized for alias in aliases):
                return LogoMatch(
                    manufacturer=self._display_name(manufacturer),
                    path=self._path_index.get(manufacturer),
                )

        for filename_key, path in self._path_index.items():
            if filename_key in normalized:
                return LogoMatch(
                    manufacturer=self._display_name(filename_key),
                    path=path,
                )

        return LogoMatch(
            manufacturer="Car",
            path=self._path_index.get("default"),
        )

    def pixmap(self, path: Path | None) -> QPixmap | None:
        if path is None or not path.exists():
            return None

        cached = self._pixmap_cache.get(path)
        if cached is not None:
            return cached

        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return None

        self._pixmap_cache[path] = pixmap
        return pixmap

    def _resolve_directory(self, configured_directory: str | None) -> Path:
        candidates: list[Path] = []

        if configured_directory:
            configured = Path(configured_directory)
            candidates.append(
                configured if configured.is_absolute() else self.project_root / configured
            )

        candidates.extend(
            [
                self.project_root / "images" / "logos",
                self.project_root / "images" / "logo",
                self.project_root / "src" / "images" / "logos",
                self.project_root / "images",
            ]
        )

        for candidate in candidates:
            if candidate.exists() and candidate.is_dir():
                return candidate

        fallback = self.project_root / "images" / "logos"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback

    def _load_aliases(self) -> dict[str, list[str]]:
        aliases = {key: list(value) for key, value in self.DEFAULT_ALIASES.items()}
        aliases_file = self.logo_directory / "manufacturer_aliases.json"

        if aliases_file.exists():
            try:
                custom = json.loads(aliases_file.read_text(encoding="utf-8"))
                for key, values in custom.items():
                    if isinstance(values, list):
                        aliases[str(key)] = [str(value) for value in values]
            except (OSError, json.JSONDecodeError):
                pass

        return aliases

    def _index_files(self) -> dict[str, Path]:
        result: dict[str, Path] = {}
        allowed = {".png", ".jpg", ".jpeg", ".webp", ".svg"}

        if not self.logo_directory.exists():
            return result

        for path in self.logo_directory.iterdir():
            if path.is_file() and path.suffix.lower() in allowed:
                result[self._normalize(path.stem).replace(" ", "_")] = path

        return result

    @staticmethod
    def _normalize(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", str(value or ""))
        normalized = "".join(char for char in normalized if not unicodedata.combining(char))
        normalized = normalized.lower().replace("_", "-")
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
        return re.sub(r"\s+", " ", normalized).strip()

    @staticmethod
    def _display_name(value: str) -> str:
        return value.replace("_", " ").title()
