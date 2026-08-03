# SectorFlow is an open-source overlay application for racing simulation.
# Copyright (C) 2022-2026 SectorFlow developers
# Based on the user-provided Standings Hybrid reference.
#
# This file is part of SectorFlow.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.


from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap


COUNTRY_NAMES = {
    "argentina": "AR", "australia": "AU", "austria": "AT", "belgium": "BE",
    "belgica": "BE", "brazil": "BR", "brasil": "BR", "canada": "CA",
    "chile": "CL", "china": "CN", "colombia": "CO", "croatia": "HR",
    "czechia": "CZ", "denmark": "DK", "finland": "FI", "france": "FR",
    "franca": "FR", "germany": "DE", "alemanha": "DE", "greatbritain": "GB",
    "unitedkingdom": "GB", "uk": "GB", "hungary": "HU", "india": "IN",
    "ireland": "IE", "italy": "IT", "italia": "IT", "japan": "JP",
    "japao": "JP", "mexico": "MX", "netherlands": "NL", "newzealand": "NZ",
    "norway": "NO", "poland": "PL", "portugal": "PT", "romania": "RO",
    "southafrica": "ZA", "southkorea": "KR", "spain": "ES", "espanha": "ES",
    "sweden": "SE", "switzerland": "CH", "turkey": "TR", "unitedstates": "US",
    "usa": "US", "uruguay": "UY",
}

BRANDS = {
    "296": "Ferrari", "488": "Ferrari", "499": "Ferrari",
    "911": "Porsche", "963": "Porsche", "992": "Porsche",
    "m4": "BMW", "m hybrid": "BMW", "vantage": "Aston Martin",
    "valkyrie": "Aston Martin", "z06": "Corvette", "c8": "Corvette",
    "huracan": "Lamborghini", "sc63": "Lamborghini", "mustang": "Ford",
    "720s": "McLaren", "artura": "McLaren", "rcf": "Lexus",
    "mercedes": "Mercedes-AMG", "amg": "Mercedes-AMG", "r8": "Audi",
    "oreca": "Oreca", "ligier": "Ligier", "ginetta": "Ginetta",
    "gr010": "Toyota", "9x8": "Peugeot", "a424": "Alpine",
    "v-series": "Cadillac", "007": "Glickenhaus", "isotta": "Isotta",
}


class BrandLogoStore:
    def __init__(self, project_root: Path, config: dict[str, Any]) -> None:
        self.project_root = Path(project_root)
        self.config = config
        self._files: dict[str, Path] = {}
        self._pixmaps: dict[tuple[str, int, int], QPixmap] = {}
        self.refresh()

    def update_config(self, config: dict[str, Any]) -> None:
        old = str(self.config.get("logo_directory", ""))
        self.config = config
        if old != str(config.get("logo_directory", "")):
            self.refresh()

    def refresh(self) -> None:
        self._files = {}
        self._pixmaps = {}
        configured = str(self.config.get("logo_directory", "images/logos")).strip()
        directories = [
            self.project_root / configured,
            self.project_root / "images" / "logo marca",
            self.project_root / "images" / "logos",
            self.project_root / "assets" / "logos",
        ]
        for directory in directories:
            if not directory.exists():
                continue
            for path in directory.iterdir():
                if path.is_file() and path.suffix.casefold() in {".png", ".jpg", ".jpeg", ".bmp"}:
                    self._files.setdefault(_clean(path.stem), path)

    def pixmap(self, brand: str, width: int, height: int) -> QPixmap | None:
        if not brand:
            return None
        clean = _clean(brand)
        path = self._files.get(clean)
        if path is None:
            for key, candidate in self._files.items():
                if key in clean or clean in key:
                    path = candidate
                    break
        if path is None:
            return None
        cache_key = (str(path), width, height)
        if cache_key not in self._pixmaps:
            source = QPixmap(str(path))
            self._pixmaps[cache_key] = source.scaled(
                max(1, width), max(1, height),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        pixmap = self._pixmaps[cache_key]
        return pixmap if not pixmap.isNull() else None


def _clean(value: str) -> str:
    return "".join(c for c in str(value or "").casefold() if c.isalnum())


def detect_manufacturer(vehicle_name: str, vehicle_filename: str = "", supplied: str = "") -> str:
    if supplied:
        return supplied
    text = f"{vehicle_name} {vehicle_filename}".casefold()
    for keyword, brand in BRANDS.items():
        if keyword in text:
            return brand
    for brand in (
        "Ferrari", "Porsche", "BMW", "Toyota", "Peugeot", "Alpine", "Cadillac",
        "Lamborghini", "Aston Martin", "Corvette", "Ford", "McLaren", "Lexus",
        "Mercedes", "Audi", "Oreca", "Ligier", "Ginetta", "Duqueine",
    ):
        if brand.casefold() in text:
            return brand
    return ""


def brand_short(brand: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", brand or "")
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:3].upper()
    return "".join(word[0] for word in words[:3]).upper()


def country_code(nationality: str, code: str) -> str:
    clean_code = str(code or "").strip().upper()
    if len(clean_code) == 2 and clean_code.isalpha():
        return clean_code
    key = _clean(nationality)
    return COUNTRY_NAMES.get(key, clean_code if len(clean_code) == 2 else "")


def flag_emoji(nationality: str, code: str) -> str:
    iso = country_code(nationality, code)
    if len(iso) != 2 or not iso.isalpha():
        return "🌐"
    return "".join(chr(0x1F1E6 + ord(letter) - ord("A")) for letter in iso)


def badge_text(value: str) -> str:
    text = str(value or "").strip()
    if not text or text.casefold() in {"none", "null", "undefined", "-"}:
        return ""
    words = re.findall(r"[A-Za-z0-9]+", text)
    if not words:
        return ""
    if len(words) == 1:
        return words[0][:4].upper()
    return "".join(word[0] for word in words[:4]).upper()


def badge_color(value: str, colors: dict[str, Any]) -> str:
    lower = str(value or "").casefold()
    if any(key in lower for key in ("staff", "developer", "admin")):
        return str(colors.get("badge_staff", "#A855F7"))
    if any(key in lower for key in ("creator", "partner", "pro")):
        return str(colors.get("badge_creator", "#1976D2"))
    if any(key in lower for key in ("warning", "danger", "probation")):
        return str(colors.get("badge_warning", "#E53935"))
    digest = hashlib.sha1(lower.encode("utf-8", errors="ignore")).digest()
    palette = colors.get("badge_palette", ["#1565C0", "#2E7D32", "#6A1B9A", "#EF6C00"])
    return str(palette[digest[0] % len(palette)]) if palette else "#1565C0"
