from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

from PySide6.QtGui import QPixmap


@dataclass(slots=True)
class LogoMatch:
    manufacturer: str
    path: Path | None
    matched_text: str = ""
    category: str = ""


class DeltaLogoManager:
    """Seleciona a logo pelo modelo e pela categoria do carro."""

    def __init__(
        self,
        project_root: Path,
        configured_directory: str | None = None,
    ) -> None:
        self.project_root = Path(project_root)
        self.logo_directory = self._resolve_directory(configured_directory)
        self.catalog_path = (
            self.project_root / "src" / "config" / "lmu_car_logo_catalog.json"
        )
        self.catalog = self._load_catalog()
        self._path_index = self._index_files()
        self._pixmap_cache: dict[Path, QPixmap] = {}
        self._directory_stamp = self._directory_signature()

    def set_directory(self, configured_directory: str | None) -> None:
        self.logo_directory = self._resolve_directory(configured_directory)
        self.refresh()

    def refresh(self) -> None:
        self.catalog = self._load_catalog()
        self._path_index = self._index_files()
        self._pixmap_cache.clear()
        self._directory_stamp = self._directory_signature()

    def match(
        self,
        *vehicle_texts: str,
        vehicle_class: str = "",
    ) -> LogoMatch:
        self._refresh_if_changed()

        category = self._category_from_class(vehicle_class)
        category_data = self._category_data(category)
        combined = " ".join(
            self._normalize(value)
            for value in vehicle_texts
            if str(value or "").strip()
        )

        forced = str(category_data.get("force_manufacturer", "") or "")
        if forced:
            car = self._car_by_manufacturer(category_data, forced)
            return self._result(car, category, vehicle_class or forced)

        matches: list[tuple[int, dict[str, Any], str]] = []
        for car in category_data.get("cars", []):
            for model in car.get("models", []):
                normalized_model = self._normalize(model)
                if normalized_model and normalized_model in combined:
                    matches.append((len(normalized_model), car, model))

        if matches:
            _, car, matched = max(matches, key=lambda item: item[0])
            return self._result(car, category, matched)

        for car in category_data.get("cars", []):
            manufacturer = str(car.get("manufacturer", "") or "")
            normalized_manufacturer = self._normalize(
                manufacturer.replace("_", " ")
            )
            if normalized_manufacturer and normalized_manufacturer in combined:
                return self._result(car, category, manufacturer)

        if not category:
            global_match = self._global_match(combined)
            if global_match is not None:
                car, found_category, matched = global_match
                return self._result(car, found_category, matched)

        return LogoMatch(
            manufacturer="Car",
            path=self._path_for_names(["default"]),
            matched_text=combined,
            category=category,
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

    def diagnostics(self) -> dict[str, object]:
        return {
            "logo_directory": str(self.logo_directory),
            "catalog_path": str(self.catalog_path),
            "categories": sorted(self.catalog.get("categories", {}).keys()),
            "indexed_files": sorted(
                path.name for path in set(self._path_index.values())
            ),
        }

    def _result(
        self,
        car: dict[str, Any] | None,
        category: str,
        matched_text: str,
    ) -> LogoMatch:
        if not car:
            return LogoMatch(
                manufacturer="Car",
                path=self._path_for_names(["default"]),
                matched_text=matched_text,
                category=category,
            )

        manufacturer = str(car.get("manufacturer", "") or "")
        names = list(car.get("logo_files", []))
        names.extend(
            [
                manufacturer,
                manufacturer.replace("_", " "),
                manufacturer.replace("_", ""),
            ]
        )

        return LogoMatch(
            manufacturer=manufacturer.replace("_", " ").title(),
            path=self._path_for_names(names),
            matched_text=matched_text,
            category=category,
        )

    def _global_match(
        self,
        combined: str,
    ) -> tuple[dict[str, Any], str, str] | None:
        matches: list[tuple[int, dict[str, Any], str, str]] = []

        for category, data in self.catalog.get("categories", {}).items():
            for car in data.get("cars", []):
                for model in car.get("models", []):
                    normalized_model = self._normalize(model)
                    if normalized_model and normalized_model in combined:
                        matches.append(
                            (len(normalized_model), car, category, model)
                        )

        if not matches:
            return None

        _, car, category, model = max(matches, key=lambda item: item[0])
        return car, category, model

    def _category_from_class(self, vehicle_class: str) -> str:
        normalized = self._normalize(vehicle_class)
        if not normalized:
            return ""

        priorities = ["lmgt3", "gte", "lmp2", "lmp3", "hypercar"]
        categories = self.catalog.get("categories", {})

        for category in priorities:
            for alias in categories.get(category, {}).get("class_aliases", []):
                normalized_alias = self._normalize(alias)
                if normalized == normalized_alias or normalized_alias in normalized:
                    return category

        return ""

    def _category_data(self, category: str) -> dict[str, Any]:
        return self.catalog.get("categories", {}).get(category, {})

    @staticmethod
    def _car_by_manufacturer(
        category_data: dict[str, Any],
        manufacturer: str,
    ) -> dict[str, Any] | None:
        for car in category_data.get("cars", []):
            if str(car.get("manufacturer", "")) == manufacturer:
                return car
        return None

    def _load_catalog(self) -> dict[str, Any]:
        try:
            return json.loads(self.catalog_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"categories": {}}

    def _resolve_directory(self, configured_directory: str | None) -> Path:
        candidates: list[Path] = []
        if configured_directory:
            configured = Path(str(configured_directory).strip())
            candidates.append(
                configured if configured.is_absolute()
                else self.project_root / configured
            )

        candidates.extend(
            [
                self.project_root / "images" / "logos",
                self.project_root / "images" / "logo",
            ]
        )

        for candidate in candidates:
            if candidate.exists() and candidate.is_dir():
                return candidate.resolve()

        fallback = self.project_root / "images" / "logos"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback.resolve()

    def _index_files(self) -> dict[str, Path]:
        result: dict[str, Path] = {}
        allowed = {".png", ".jpg", ".jpeg", ".webp"}

        if not self.logo_directory.exists():
            return result

        for path in self.logo_directory.iterdir():
            if not path.is_file() or path.suffix.lower() not in allowed:
                continue

            normalized = self._normalize(path.stem)
            for key in {
                normalized,
                normalized.replace(" ", "_"),
                self._compact(normalized),
            }:
                if key:
                    result.setdefault(key, path)

        return result

    def _path_for_names(self, names: Iterable[str]) -> Path | None:
        normalized_names = [
            self._normalize(name)
            for name in names
            if str(name or "").strip()
        ]

        for name in normalized_names:
            for key in {
                name,
                name.replace(" ", "_"),
                self._compact(name),
            }:
                path = self._path_index.get(key)
                if path is not None:
                    return path

        best_ratio = 0.0
        best_path: Path | None = None

        for name in normalized_names:
            for key, path in self._path_index.items():
                ratio = SequenceMatcher(
                    None,
                    self._compact(name),
                    self._compact(key),
                ).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_path = path

        return best_path if best_ratio >= 0.76 else None

    def _refresh_if_changed(self) -> None:
        current = self._directory_signature()
        if current != self._directory_stamp:
            self.refresh()

    def _directory_signature(self) -> tuple[tuple[str, int, int], ...]:
        if not self.logo_directory.exists():
            return ()

        result: list[tuple[str, int, int]] = []
        try:
            for path in self.logo_directory.iterdir():
                if not path.is_file():
                    continue
                stat = path.stat()
                result.append(
                    (path.name.lower(), int(stat.st_mtime_ns), int(stat.st_size))
                )
        except OSError:
            return ()

        return tuple(sorted(result))

    @staticmethod
    def _compact(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

    @staticmethod
    def _normalize(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", str(value or ""))
        normalized = "".join(
            char for char in normalized
            if not unicodedata.combining(char)
        )
        normalized = normalized.lower().replace("_", " ")
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
        return re.sub(r"\s+", " ", normalized).strip()
