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
import time
import unicodedata
from collections import OrderedDict
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Qt, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import (
    QNetworkAccessManager,
    QNetworkReply,
    QNetworkRequest,
)


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

# Países resolvidos pelo Standings durante a sessão. O Delta consulta apenas
# este pequeno índice para reutilizar exatamente a mesma identificação e a
# mesma bandeira, sem depender de o cache em disco já ter sido atualizado.
_LIVE_DRIVER_COUNTRIES: dict[str, tuple[str, str]] = {}


def publish_driver_country(driver_name: str, nationality: str, code: str) -> None:
    key = _asset_key(driver_name)
    nationality = str(nationality or "").strip()
    code = str(code or "").strip().upper()
    if key and (nationality or code):
        _LIVE_DRIVER_COUNTRIES[key] = (nationality, code)


def live_driver_country(driver_name: str) -> tuple[str, str]:
    return _LIVE_DRIVER_COUNTRIES.get(_asset_key(driver_name), ("", ""))

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
    "gmr001": "Genesis", "genesis": "Genesis",
    "ad25": "Adess", "adess": "Adess", "d09": "Duqueine",
    "jsp325": "Ligier", "g61": "Ginetta",
    "vandervell": "Vanwall", "vanwall": "Vanwall",
    "sgc_007": "Glickenhaus", "chevrolet": "Corvette",
}

BADGE_IMAGE_ALIASES = {
    "srnoob": "rookie",
    "srrookie": "rookie",
    "rookie": "rookie",
    "novato": "rookie",
    "srprobation": "probation",
    "probation": "probation",
    "returnfromban": "probation",
    "srwarning": "warning",
    "srdanger": "warning",
    "warning": "warning",
    "danger": "warning",
    "srclean": "gooddriver",
    "gooddriver": "gooddriver",
    "bompiloto": "gooddriver",
    "srsaint": "trusteddrive",
    "trustedracer": "trusteddrive",
    "trusteddriver": "trusteddrive",
    "trusteddrive": "trusteddrive",
    "pilotoconfiavel": "trusteddrive",
    "s397": "staff",
    "staff": "staff",
    "developer": "staff",
    "admin": "staff",
    "contentcreator": "creator",
    "creator": "creator",
    "partner": "creator",
    "irldriver": "realdriver",
    "realdriver": "realdriver",
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


class BadgeImageStore:
    """Carrega os badges locais usando os codigos oficiais do RaceOS."""

    def __init__(self, project_root: Path, config: dict[str, Any]) -> None:
        self.project_root = Path(project_root)
        self.config = dict(config)
        self._files: dict[str, Path] = {}
        self._pixmaps: dict[tuple[str, int, int], QPixmap] = {}
        self.refresh()

    def update_config(self, config: dict[str, Any]) -> None:
        previous = str(
            self.config.get("badge_directory", "images/badge")
        )
        self.config = dict(config)
        current = str(
            self.config.get("badge_directory", "images/badge")
        )
        if previous != current:
            self.refresh()

    def refresh(self) -> None:
        self._files = {}
        self._pixmaps = {}
        configured = str(
            self.config.get("badge_directory", "images/badge")
            or "images/badge"
        ).strip()
        directories = (
            self.project_root / configured,
            self.project_root / "images" / "badge",
            self.project_root / "images" / "Badge",
        )
        seen: set[str] = set()
        for directory in directories:
            key = str(directory).casefold()
            if key in seen or not directory.is_dir():
                continue
            seen.add(key)
            for path in directory.iterdir():
                if (
                    path.is_file()
                    and path.suffix.casefold()
                    in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
                ):
                    file_key = _asset_key(path.stem)
                    self._files.setdefault(file_key, path)
                    if file_key in {
                        "trusteddrive",
                        "trusteddriver",
                        "pilotoconfiavel",
                    }:
                        self._files.setdefault("trusteddrive", path)

    def pixmap(
        self,
        badge: str,
        width: int,
        height: int,
    ) -> QPixmap | None:
        if not bool(self.config.get("use_badge_images", True)):
            return None
        source_key = badge_asset_key(badge)
        if not source_key:
            return None
        path = self._files.get(source_key)
        if path is None:
            return None
        width = max(1, int(width))
        height = max(1, int(height))
        cache_key = (str(path), width, height)
        cached = self._pixmaps.get(cache_key)
        if cached is None:
            source = QPixmap(str(path))
            cached = source.scaled(
                width,
                height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._pixmaps[cache_key] = cached
        return cached if not cached.isNull() else None


class CountryFlagStore(QObject):
    """Cache leve de bandeiras baixadas do CDN da Flagpedia.

    O Qt faz a requisicao de forma assincrona. Na primeira aparicao de um pais,
    enquanto a imagem baixa, o widget usa o emoji existente. O PNG fica salvo
    para as proximas execucoes.
    """

    DEFAULT_URL = "https://flagcdn.com/40x30/{code}.png"
    MAX_DOWNLOAD_BYTES = 256 * 1024
    MAX_PIXMAP_CACHE = 256

    def __init__(
        self,
        project_root: Path,
        config: dict[str, Any],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.project_root = Path(project_root).resolve()
        self.config = dict(config)
        self._pending: dict[str, QNetworkReply] = {}
        self._failed_until: dict[str, float] = {}
        self._originals: dict[str, QPixmap] = {}
        self._pixmaps: OrderedDict[tuple[str, int, int], QPixmap] = OrderedDict()
        self._manager = QNetworkAccessManager(self)

    def update_config(self, config: dict[str, Any]) -> None:
        previous_url = str(
            self.config.get("flag_provider_url", self.DEFAULT_URL)
        )
        previous_cache = str(
            self.config.get("flag_cache_directory", "data/flags")
        )
        self.config = dict(config)
        current_url = str(
            self.config.get("flag_provider_url", self.DEFAULT_URL)
        )
        current_cache = str(
            self.config.get("flag_cache_directory", "data/flags")
        )
        if (previous_url, previous_cache) != (current_url, current_cache):
            self._originals.clear()
            self._pixmaps.clear()
            self._failed_until.clear()

    def stop(self) -> None:
        for reply in tuple(self._pending.values()):
            reply.abort()
            reply.deleteLater()
        self._pending.clear()

    def pixmap(
        self,
        nationality: str,
        code: str,
        width: int,
        height: int,
    ) -> QPixmap | None:
        iso = country_code(nationality, code)
        if len(iso) != 2 or not iso.isalpha():
            return None
        iso = iso.upper()
        width = max(1, int(width))
        height = max(1, int(height))
        cache_key = (iso, width, height)
        cached = self._pixmaps.get(cache_key)
        if cached is not None:
            self._pixmaps.move_to_end(cache_key)
            return cached

        source = self._originals.get(iso)
        if source is None:
            path = self._cache_path(iso)
            if path.is_file():
                candidate = QPixmap(str(path))
                if not candidate.isNull():
                    source = candidate
                    self._originals[iso] = source
            if source is None:
                self._schedule(iso)
                return None

        scaled = source.scaled(
            width,
            height,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        if scaled.isNull():
            return None
        self._pixmaps[cache_key] = scaled
        self._pixmaps.move_to_end(cache_key)
        while len(self._pixmaps) > self.MAX_PIXMAP_CACHE:
            self._pixmaps.popitem(last=False)
        return scaled

    def _schedule(self, iso: str) -> None:
        if not bool(self.config.get("use_flag_images", True)):
            return
        if iso in self._pending:
            return
        if time.monotonic() < self._failed_until.get(iso, 0.0):
            return
        template = str(
            self.config.get("flag_provider_url", self.DEFAULT_URL)
            or self.DEFAULT_URL
        )
        url = template.format(code=iso.lower(), CODE=iso.upper())
        if not url.startswith("https://"):
            self._mark_failed(iso)
            return
        request = QNetworkRequest(QUrl(url))
        request.setRawHeader(
            b"User-Agent",
            b"SectorFlowDrive/FlagCacheV1",
        )
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy,
        )
        timeout_ms = max(
            500,
            min(
                10_000,
                round(
                    float(
                        self.config.get(
                            "flag_download_timeout_seconds",
                            3.0,
                        )
                    )
                    * 1000.0
                ),
            ),
        )
        request.setTransferTimeout(timeout_ms)
        reply = self._manager.get(request)
        self._pending[iso] = reply
        reply.finished.connect(
            lambda current=reply, country=iso: self._finish_download(
                country,
                current,
            )
        )

    def _finish_download(self, iso: str, reply: QNetworkReply) -> None:
        self._pending.pop(iso, None)
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self._mark_failed(iso)
                return
            content = bytes(reply.readAll())
            if (
                not content.startswith(b"\x89PNG\r\n\x1a\n")
                or len(content) > self.MAX_DOWNLOAD_BYTES
            ):
                self._mark_failed(iso)
                return
            destination = self._cache_path(iso)
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(".tmp")
            temporary.write_bytes(content)
            temporary.replace(destination)
            self._failed_until.pop(iso, None)
        except OSError:
            self._mark_failed(iso)
        finally:
            reply.deleteLater()

    def _mark_failed(self, iso: str) -> None:
        retry_seconds = max(
            30.0,
            float(self.config.get("flag_retry_seconds", 300.0)),
        )
        self._failed_until[iso] = time.monotonic() + retry_seconds

    def _cache_path(self, iso: str) -> Path:
        configured = str(
            self.config.get("flag_cache_directory", "data/flags")
            or "data/flags"
        ).strip()
        candidate = Path(configured)
        if not candidate.is_absolute():
            candidate = self.project_root / candidate
        try:
            resolved = candidate.resolve()
            resolved.relative_to(self.project_root)
        except (OSError, ValueError):
            resolved = self.project_root / "data" / "flags"
        return resolved / f"{iso.lower()}.png"


def _clean(value: str) -> str:
    return "".join(c for c in str(value or "").casefold() if c.isalnum())


def _asset_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = normalized.encode("ascii", errors="ignore").decode("ascii")
    return "".join(c for c in ascii_text.casefold() if c.isalnum())


def badge_asset_key(value: str) -> str:
    clean = _asset_key(value)
    if not clean or clean in {"none", "null", "undefined"}:
        return ""
    return BADGE_IMAGE_ALIASES.get(clean, clean)


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
        "Genesis", "Adess", "Glickenhaus", "Isotta", "Vanwall",
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
