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

import copy
import json
import socket
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable

from .standings_models import DriverMetadata, normalize_identity


def _key(value: Any) -> str:
    return "".join(c for c in str(value or "").casefold() if c.isalnum())


def _walk(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _decode(value: Any) -> Any:
    current = value
    for _ in range(4):
        if not isinstance(current, str):
            break
        text = current.strip()
        if not text or text[0] not in "[{":
            break
        try:
            current = json.loads(text)
        except json.JSONDecodeError:
            break
    if isinstance(current, dict) and isinstance(current.get("payload"), str):
        current = dict(current)
        current["payload"] = _decode(current["payload"])
    return current


def _flat(source: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}

    def visit(value: Any, prefix: str = "") -> None:
        if isinstance(value, dict):
            for name, child in value.items():
                name_key = _key(name)
                compound = prefix + name_key
                if not isinstance(child, (dict, list)):
                    result.setdefault(name_key, child)
                    result.setdefault(compound, child)
                visit(child, compound)
        elif isinstance(value, list):
            for child in value:
                visit(child, prefix)

    visit(source)
    return result


def _first(values: dict[str, Any], *aliases: str, default: Any = None) -> Any:
    for alias in aliases:
        value = values.get(_key(alias))
        if value not in (None, ""):
            return value
    return default


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result or result in (float("inf"), float("-inf")):
        return None
    return result


def _percent(value: Any) -> float | None:
    number = _float(value)
    if number is None:
        return None
    if 0.0 <= number <= 1.0:
        number *= 100.0
    return max(0.0, min(100.0, number))


class HttpJson:
    def get(self, url: str, timeout: float) -> tuple[bool, Any, str]:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "SectorFlowDrive/StandingsHybridClassicV2",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=max(0.2, timeout)) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            return False, None, f"HTTP {exc.code}"
        except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as exc:
            return False, None, str(exc)
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            return True, None, ""
        try:
            return True, _decode(json.loads(text)), ""
        except json.JSONDecodeError:
            return True, text, ""


class LocalStandingsEnrichment:
    """Enriquece a memória compartilhada usando somente fontes locais do LMU.

    Não usa SimHub nem carrega DLL de terceiros. Bandeira e badge são
    extraídos quando o próprio LMU os publica no REST local ou quando já
    existem em um diagnóstico sanitizado criado pelo Sector Flow.
    """

    ENDPOINTS = (
        "/rest/watch/standings",
        "/rest/watch/sessionInfo",
        "/rest/sessions",
        "/rest/multiplayer/teams",
        "/rest/race/car",
    )

    def __init__(self, project_root: Path, config: dict[str, Any]) -> None:
        self.project_root = Path(project_root)
        self.config = config
        self.http = HttpJson()
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._metadata: dict[str, DriverMetadata] = {}
        self._source_text = "MEM"
        self._last_error = ""
        self._raw: dict[str, Any] = {}
        self._test_mode = False
        self._thread = threading.Thread(
            target=self._worker,
            name="SectorFlow-StandingsLocal",
            daemon=True,
        )
        self._thread.start()

    def update_config(self, config: dict[str, Any]) -> None:
        with self._lock:
            self.config = config
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        self._thread.join(timeout=1.5)

    def trigger(self) -> None:
        self._wake.set()

    def use_live_mode(self) -> None:
        with self._lock:
            self._test_mode = False
        self._wake.set()

    def snapshot(self) -> tuple[dict[str, DriverMetadata], str, str]:
        with self._lock:
            return copy.deepcopy(self._metadata), self._source_text, self._last_error

    def set_test_metadata(self, records: list[DriverMetadata]) -> None:
        with self._lock:
            self._test_mode = True
            self._metadata = {
                normalize_identity(item.driver_name): copy.deepcopy(item)
                for item in records
                if normalize_identity(item.driver_name)
            }
            self._source_text = "TEST"

    def fetch_once(self) -> tuple[dict[str, DriverMetadata], str, str]:
        metadata, source, error, raw = self._collect()
        with self._lock:
            self._metadata = metadata
            self._source_text = source
            self._last_error = error
            self._raw = raw
        return self.snapshot()

    def save_sanitized(self) -> Path:
        metadata, source, error = self.snapshot()
        destination = self.project_root / "data" / "online_profiles" / "standings_hybrid_local.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "source": source,
            "error": error,
            "drivers": [
                {
                    "driver_name": item.driver_name,
                    "team_name": item.team_name,
                    "vehicle_name": item.vehicle_name,
                    "car_number": item.car_number,
                    "manufacturer": item.manufacturer,
                    "nationality": item.nationality,
                    "country_code": item.country_code,
                    "badge": item.badge,
                    "tyre_compound": item.tyre_compound,
                    "energy_percent": item.energy_percent,
                    "damage_percent": item.damage_percent,
                    "finish_state": item.finish_state,
                    "source": item.source,
                }
                for item in metadata.values()
            ],
        }
        destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return destination

    def _worker(self) -> None:
        next_fetch = 0.0
        while not self._stop.is_set():
            with self._lock:
                config = dict(self.config)
            now = time.monotonic()
            interval = max(0.5, float(config.get("local_poll_interval_seconds", 2.0)))
            with self._lock:
                test_mode = self._test_mode
            if test_mode:
                self._wake.wait(timeout=0.25)
                self._wake.clear()
                continue
            if now >= next_fetch:
                self.fetch_once()
                next_fetch = now + interval
            self._wake.wait(timeout=0.25)
            self._wake.clear()

    def _collect(self) -> tuple[dict[str, DriverMetadata], str, str, dict[str, Any]]:
        with self._lock:
            config = dict(self.config)
        metadata = self._load_profile_cache()
        if not bool(config.get("enable_local_api", True)):
            return metadata, "CACHE" if metadata else "MEM", "REST local desativado", {}
        host = str(config.get("local_api_host", "127.0.0.1"))
        port = int(config.get("local_api_port", 6397))
        timeout = max(0.2, float(config.get("local_api_timeout_seconds", 0.8)))
        raw: dict[str, Any] = {}
        errors: list[str] = []
        connected = False
        for endpoint in self.ENDPOINTS:
            ok, data, error = self.http.get(f"http://{host}:{port}{endpoint}", timeout)
            if ok and data is not None:
                connected = True
                raw[endpoint] = data
                self._parse_payload(data, metadata, endpoint)
            elif error:
                errors.append(f"{endpoint}: {error}")
        source = "LMU REST" if connected else ("CACHE" if metadata else "MEM")
        return metadata, source, "; ".join(errors[:2]), raw

    def _parse_payload(
        self,
        payload: Any,
        target: dict[str, DriverMetadata],
        source_name: str,
    ) -> None:
        decoded = _decode(payload)
        for record in _walk(decoded):
            values = _flat(record)
            name = str(_first(values, "driverName", "playerName", "displayName", "profileName", default="") or "").strip()
            if not name:
                continue
            marker_fields = (
                "nationality", "countryCode", "badge", "driverBadge",
                "vehicleName", "teamName", "carNumber", "manufacturer",
                "batteryChargeFraction", "virtualEnergy", "damage", "integrity",
            )
            if not any(_first(values, field, default=None) is not None for field in marker_fields):
                continue
            identity = normalize_identity(name)
            current = target.get(identity, DriverMetadata(driver_name=name))
            current.driver_name = name or current.driver_name
            current.team_name = str(_first(values, "teamName", "team", "entrantName", default=current.team_name) or current.team_name)
            current.vehicle_name = str(_first(values, "vehicleName", "carName", "vehicle", default=current.vehicle_name) or current.vehicle_name)
            current.car_number = str(_first(values, "carNumber", "vehicleNumber", "raceNumber", default=current.car_number) or current.car_number)
            current.manufacturer = str(_first(values, "manufacturer", "make", "brand", default=current.manufacturer) or current.manufacturer)
            current.nationality = str(_first(values, "nationality", "country", "countryName", default=current.nationality) or current.nationality)
            current.country_code = str(_first(values, "countryCode", "nationalityCode", "isoCountry", default=current.country_code) or current.country_code).upper()
            current.badge = str(_first(values, "badge", "driverBadge", "contactBadge", "srBadge", default=current.badge) or current.badge)
            front = str(_first(values, "frontTireCompound", "frontTyreCompound", default="") or "")
            rear = str(_first(values, "rearTireCompound", "rearTyreCompound", default="") or "")
            compound = str(_first(values, "tireCompound", "tyreCompound", "compound", default="") or "")
            current.tyre_compound = compound or (front if front == rear else f"{front}/{rear}".strip("/")) or current.tyre_compound
            energy = _percent(_first(values, "energyPercent", "batteryPercent", "batteryChargeFraction", "stateOfCharge", default=None))
            virtual = _float(_first(values, "virtualEnergy", default=None))
            maximum = _float(_first(values, "maxVirtualEnergy", "maximumVirtualEnergy", default=None))
            if energy is None and virtual is not None and maximum and maximum > 0:
                energy = max(0.0, min(100.0, virtual / maximum * 100.0))
            current.energy_percent = energy if energy is not None else current.energy_percent
            damage = _percent(_first(values, "damagePercent", "damage", default=None))
            integrity = _float(_first(values, "integrity", "vehicleIntegrity", default=None))
            if damage is None and integrity is not None and 0.0 <= integrity <= 1.0:
                damage = (1.0 - integrity) * 100.0
            current.damage_percent = damage if damage is not None else current.damage_percent
            current.finish_state = str(_first(values, "finishState", "finishStatus", "status", default=current.finish_state) or current.finish_state)
            current.source = source_name
            current.raw = record
            target[identity] = current

    def _load_profile_cache(self) -> dict[str, DriverMetadata]:
        result: dict[str, DriverMetadata] = {}
        candidates: list[Path] = []
        for directory in (
            self.project_root / "data" / "online_profiles",
            self.project_root / "data" / "online_debug",
        ):
            if directory.exists():
                candidates.extend(directory.glob("*.json"))
        candidates = sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)[:12]
        for path in candidates:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            self._parse_payload(payload, result, f"CACHE:{path.name}")
        return result
