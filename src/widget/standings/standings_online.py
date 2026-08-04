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
import re
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
                if name_key in {
                    "metadata",
                    "profile",
                    "properties",
                    "data",
                    "driver",
                    "user",
                    "account",
                }:
                    # Wrappers de perfil nao fazem parte do nome real do
                    # campo. Visitar também no nível atual produz, por
                    # exemplo, ``driverRankRank`` a partir de
                    # ``metadata.driverRank.rank``.
                    visit(child, prefix)
        elif isinstance(value, list):
            for child in value:
                visit(child, prefix)
        elif isinstance(value, str):
            # Alguns retornos do LMU guardam o perfil RaceControl como JSON
            # dentro de uma string (normalmente em ``metadata``). Decodificar
            # aqui permite ler DR/SR e badges sem depender da API externa.
            decoded = _decode(value)
            if not isinstance(decoded, str):
                visit(decoded, prefix)

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


def _bool(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().casefold()
    if text in {"true", "yes", "sim", "1", "invalid", "invalidated"}:
        return True
    if text in {"false", "no", "nao", "não", "0", "valid"}:
        return False
    return None


def _percent(value: Any) -> float | None:
    number = _float(value)
    if number is None:
        return None
    if 0.0 <= number <= 1.0:
        number *= 100.0
    return max(0.0, min(100.0, number))


def _rank(values: dict[str, Any], prefix: str) -> str:
    name = str(
        _first(
            values,
            f"{prefix}Rank",
            f"{prefix}Name",
            f"{prefix}Label",
            f"{prefix}Title",
            prefix,
            default="",
        )
        or ""
    ).strip()
    tier = _first(
        values,
        f"{prefix}Tier",
        f"{prefix}Level",
        f"{prefix}SubRank",
        f"{prefix}Division",
        default=None,
    )
    if tier in (None, ""):
        return name
    try:
        tier_text = str(int(float(tier)))
    except (TypeError, ValueError):
        tier_text = str(tier).strip()
    return f"{name} {tier_text}".strip()


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
        "/rest/profile/",
        "/rest/profile/profileInfo/getProfileInfo",
        "/rest/multiplayer/teams",
    )
    VEHICLE_ENDPOINTS = (
        "/rest/sessions/getAllVehicles",
        "/rest/race/car",
    )

    def __init__(self, project_root: Path, config: dict[str, Any]) -> None:
        self.project_root = Path(project_root)
        self.config = config
        self.http = HttpJson()
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        # O cache e carregado uma unica vez. Reprocessa-lo em toda consulta
        # REST causava pausas perceptiveis quando a lista de carros mudava.
        self._metadata: dict[str, DriverMetadata] = self._load_profile_cache()
        self._source_text = "MEM"
        self._last_error = ""
        self._raw: dict[str, Any] = {}
        self._vehicle_catalog = self._load_vehicle_catalog()
        self._vehicle_catalog_refreshed = bool(self._vehicle_catalog)
        self._test_mode = False
        # Estado para detectar transições de sessão/conexão e gerar logs
        self._last_connected = False
        self._last_session_id = ""
        self._session_log_path = (
            self.project_root / "data" / "online_debug" / "session_transitions.log"
        )
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
            was_test_mode = self._test_mode
            self._test_mode = False
        if was_test_mode:
            self._wake.set()

    def snapshot(
        self,
        driver_names: Iterable[str] | None = None,
    ) -> tuple[dict[str, DriverMetadata], str, str]:
        with self._lock:
            if driver_names is None:
                metadata = copy.deepcopy(self._metadata)
            else:
                requested = {
                    normalize_identity(name): str(name)
                    for name in driver_names
                    if normalize_identity(name)
                }
                metadata = {}
                for requested_identity, requested_name in requested.items():
                    exact = self._metadata.get(requested_identity)
                    if exact is not None:
                        metadata[requested_identity] = copy.deepcopy(exact)
                        continue
                    requested_aliases = self._identity_aliases(requested_name)
                    for item in self._metadata.values():
                        item_aliases = self._identity_aliases(item.driver_name)
                        item_aliases.update(self._identity_aliases(item.username))
                        if requested_aliases & item_aliases:
                            metadata[requested_identity] = copy.deepcopy(item)
                            break
            return metadata, self._source_text, self._last_error

    def vehicle_catalog(
        self,
        vehicle_names: Iterable[str] | None = None,
    ) -> dict[str, dict[str, str]]:
        with self._lock:
            if vehicle_names is None:
                return copy.deepcopy(self._vehicle_catalog)
            identities = {
                normalize_identity(name)
                for name in vehicle_names
                if normalize_identity(name)
            }
            return {
                identity: dict(item)
                for identity, item in self._vehicle_catalog.items()
                if identity in identities
            }

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
                    "vehicle_model": item.vehicle_model,
                    "car_number": item.car_number,
                    "manufacturer": item.manufacturer,
                    "nationality": item.nationality,
                    "country_code": item.country_code,
                    "badge": item.badge,
                    "driver_rank": item.driver_rank,
                    "driver_rank_progress": item.driver_rank_progress,
                    "safety_rank": item.safety_rank,
                    "estimated_driver_rank_gain": item.estimated_driver_rank_gain,
                    "tyre_compound": item.tyre_compound,
                    "energy_percent": item.energy_percent,
                    "energy_remaining_fraction": item.energy_remaining_fraction,
                    "energy_use_per_lap": item.energy_use_per_lap,
                    "energy_reference_lap": item.energy_reference_lap,
                    "current_lap_invalidated": item.current_lap_invalidated,
                    "last_lap_invalidated": item.last_lap_invalidated,
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

    def _refresh_stint_usage(self, config: dict[str, Any]) -> None:
        if not bool(config.get("enable_local_api", True)):
            return
        host = str(config.get("local_api_host", "127.0.0.1"))
        port = int(config.get("local_api_port", 6397))
        timeout = max(
            0.2,
            float(config.get("local_api_timeout_seconds", 0.8)),
        )
        endpoint = "/rest/strategy/usage"
        ok, data, _ = self.http.get(
            f"http://{host}:{port}{endpoint}",
            timeout,
        )
        if not ok or data is None:
            return
        with self._lock:
            metadata = copy.deepcopy(self._metadata)
        self._parse_stint_usage(data, metadata, endpoint)
        with self._lock:
            self._metadata = metadata

    def _collect(self) -> tuple[dict[str, DriverMetadata], str, str, dict[str, Any]]:
        with self._lock:
            config = dict(self.config)
        with self._lock:
            metadata = copy.deepcopy(self._metadata)
        if not bool(config.get("enable_local_api", True)):
            return metadata, "CACHE" if metadata else "MEM", "REST local desativado", {}
        host = str(config.get("local_api_host", "127.0.0.1"))
        port = int(config.get("local_api_port", 6397))
        timeout = max(0.2, float(config.get("local_api_timeout_seconds", 0.8)))
        raw: dict[str, Any] = {}
        errors: list[str] = []
        connected = False
        session_id = ""
        # Evitar coletar imediatamente ao entrar numa sessão: esperar
        # pelo menos 10 segundos de tempo de sessão para reduzir riscos
        # de falha quando o jogo fecha logo após o carregamento.
        try:
            ok_sess, sess_data, sess_err = self.http.get(
                f"http://{host}:{port}/rest/watch/sessionInfo",
                timeout,
            )
            if ok_sess and isinstance(sess_data, dict):
                sess_values = _flat(sess_data)
                sess_time = _float(
                    _first(
                        sess_values,
                        "currentEventTime",
                        "currentEventTimeS",
                        "current_event_time",
                        "currentEventTime",
                        "time",
                        "elapsed",
                        default=None,
                    )
                )
                # Construir um identificador simples de sessão para detectar troca
                server = str(_first(sess_values, "serverName", "server") or "").strip()
                session_name = str(_first(sess_values, "session", "sessionName") or "").strip()
                session_id = f"{server}|{session_name}"
                if sess_time is not None and sess_time < 10.0:
                    return metadata, "LMU REST", "aguardando 10s de sessão", {}
        except Exception:
            # Falhas na checagem não devem impedir a coleta normal abaixo
            pass
        for endpoint in self.ENDPOINTS:
            ok, data, error = self.http.get(f"http://{host}:{port}{endpoint}", timeout)
            if ok and data is not None:
                connected = True
                raw[endpoint] = data
                self._parse_payload(data, metadata, endpoint)
                if endpoint == "/rest/strategy/usage":
                    self._parse_stint_usage(data, metadata, endpoint)
            elif error:
                errors.append(f"{endpoint}: {error}")

        if not self._vehicle_catalog_refreshed:
            vehicle_errors: list[str] = []
            for endpoint in self.VEHICLE_ENDPOINTS:
                ok, data, error = self.http.get(
                    f"http://{host}:{port}{endpoint}",
                    max(timeout, 3.0),
                )
                if ok and data is not None:
                    catalog = self._parse_vehicle_catalog(data)
                    if catalog:
                        with self._lock:
                            self._vehicle_catalog.update(catalog)
                            self._vehicle_catalog_refreshed = True
                        self._save_vehicle_catalog()
                        raw[endpoint] = data
                        connected = True
                        break
                elif error:
                    vehicle_errors.append(f"{endpoint}: {error}")
            if not self._vehicle_catalog_refreshed:
                errors.extend(vehicle_errors)
        source = "LMU REST" if connected else ("CACHE" if metadata else "MEM")
        # Registrar transições: conectou/desconectou ou troca de sessão
        try:
            previous_connected = bool(self._last_connected)
            previous_session = str(self._last_session_id or "")
            if connected != previous_connected or (session_id and session_id != previous_session):
                details = {
                    "was_connected": previous_connected,
                    "now_connected": connected,
                    "previous_session": previous_session,
                    "current_session": session_id,
                    "errors": errors[:4],
                }
                # Gravar log e dump bruto
                self._append_session_log("transition", details, raw if raw else None)
            self._last_connected = connected
            if session_id:
                self._last_session_id = session_id
        except Exception:
            pass
        return metadata, source, "; ".join(errors[:2]), raw

    def _parse_payload(
        self,
        payload: Any,
        target: dict[str, DriverMetadata],
        source_name: str,
    ) -> None:
        decoded = _decode(payload)
        records = list(_walk(decoded))
        if (
            source_name.endswith("/rest/profile/")
            or source_name.endswith("/rest/profile/profileInfo/getProfileInfo")
        ) and isinstance(decoded, dict):
            values = _flat(decoded)
            profile_name = str(
                _first(
                    values,
                    "driverName",
                    "playerName",
                    "profileName",
                    "displayName",
                    "nickname",
                    "nick",
                    "name",
                    default="",
                )
                or ""
            ).strip()
            if profile_name:
                records.append({**decoded, "driverName": profile_name})
        if source_name.endswith("/rest/multiplayer/teams"):
            for container in list(records):
                drivers = next(
                    (
                        value
                        for key, value in container.items()
                        if _key(key) == "drivers"
                        and isinstance(value, (dict, list))
                    ),
                    None,
                )
                if isinstance(drivers, dict):
                    for driver_name, details in drivers.items():
                        if isinstance(details, dict):
                            records.append(
                                {**details, "driverName": str(driver_name)}
                            )
                elif isinstance(drivers, list):
                    for details in drivers:
                        if not isinstance(details, dict):
                            continue
                        values = _flat(details)
                        driver_name = str(
                            _first(
                                values,
                                "driverName",
                                "playerName",
                                "profileName",
                                "displayName",
                                "nickname",
                                "nick",
                                "username",
                                "name",
                                default="",
                            )
                            or ""
                        ).strip()
                        if driver_name:
                            records.append(
                                {**details, "driverName": driver_name}
                            )
        for record in records:
            direct_keys = {_key(name) for name in record}
            identity_keys = {
                _key("driverName"), _key("playerName"),
                _key("profileName"), _key("displayName"),
            }
            nested_identity = any(
                isinstance(child, dict)
                and bool({_key(name) for name in child} & identity_keys)
                for child in record.values()
            )
            if not direct_keys & identity_keys and not nested_identity:
                continue
            values = _flat(record)
            name = str(
                _first(
                    values,
                    "driverName",
                    "playerName",
                    "profileName",
                    "displayName",
                    default="",
                )
                or ""
            ).strip()
            if not name:
                continue
            marker_fields = (
                "nationality", "countryCode", "badge", "driverBadge",
                "contactBadge", "contactBadgeName", "reputationBadge",
                "driverRank", "driverRankRank", "safetyRank",
                "safetyRankRank", "safeRank",
                "vehicleName", "teamName", "carNumber", "manufacturer",
                "batteryChargeFraction", "virtualEnergy", "damage", "integrity",
                "lapInvalidated", "lastLapInvalidated", "lastLapValid",
            )
            if not any(_first(values, field, default=None) is not None for field in marker_fields):
                continue
            if source_name.startswith("CACHE:"):
                useful_cache_fields = (
                    "nationality", "countryCode", "badge", "driverBadge",
                    "contactBadge", "contactBadgeName", "reputationBadge",
                    "driverRank", "driverRankRank", "safetyRank",
                    "safetyRankRank", "safeRank",
                    "vehicleName", "teamName", "tireCompound",
                    "tyreCompound", "batteryChargeFraction",
                    "virtualEnergy", "damage", "integrity",
                )
                if not any(
                    _first(values, field, default=None) is not None
                    for field in useful_cache_fields
                ):
                    continue
            identity = normalize_identity(name)
            current = target.get(identity, DriverMetadata(driver_name=name))
            current.driver_name = name or current.driver_name
            current.username = str(
                _first(values, "username", "userName", default=current.username)
                or current.username
            )
            current.steam_id = str(
                _first(
                    values,
                    "steamId",
                    "steamID",
                    "platformId",
                    default=current.steam_id,
                )
                or current.steam_id
            )
            current.team_name = str(_first(values, "teamName", "team", "entrantName", default=current.team_name) or current.team_name)
            current.vehicle_name = str(_first(values, "vehicleName", "carName", "vehicle", default=current.vehicle_name) or current.vehicle_name)
            current.vehicle_model = str(_first(values, "vehicleModel", "carModel", "model", default=current.vehicle_model) or current.vehicle_model)
            current.car_number = str(_first(values, "carNumber", "vehicleNumber", "raceNumber", default=current.car_number) or current.car_number)
            current.manufacturer = str(_first(values, "manufacturer", "make", "brand", default=current.manufacturer) or current.manufacturer)
            current.nationality = str(_first(values, "nationality", "country", "countryName", default=current.nationality) or current.nationality)
            current.country_code = str(_first(values, "countryCode", "nationalityCode", "isoCountry", default=current.country_code) or current.country_code).upper()
            if not current.country_code and len(current.nationality.strip()) == 2:
                current.country_code = current.nationality.strip().upper()
            badge = str(
                _first(
                    values,
                    "badge",
                    "driverBadge",
                    "contactBadge",
                    "contactBadgeName",
                    "reputationBadge",
                    "safetyBadge",
                    "srBadge",
                    default=current.badge,
                )
                or current.badge
            ).strip()
            if badge.casefold() in {"", "none", "null", "undefined", "-"}:
                badge = self._badge_from_roles(record) or current.badge
            current.badge = badge
            driver_rank = _rank(values, "driverRank")
            safety_rank = _rank(values, "safetyRank") or _rank(values, "safeRank")
            current.driver_rank = driver_rank or current.driver_rank
            current.safety_rank = safety_rank or current.safety_rank
            progress = _percent(
                _first(
                    values,
                    "driverRankProgress",
                    "driverRankPercentage",
                    "driverRankPercent",
                    "rankProgress",
                    default=None,
                )
            )
            if progress is not None:
                current.driver_rank_progress = progress
            estimated_gain = _float(
                _first(
                    values,
                    "estimatedDriverRankGain",
                    "driverRankGain",
                    "estimatedRankGain",
                    default=None,
                )
            )
            if estimated_gain is not None:
                current.estimated_driver_rank_gain = estimated_gain
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
            current_invalid = _bool(
                _first(
                    values,
                    "lapInvalidated",
                    "currentLapInvalidated",
                    "isLapInvalid",
                    default=None,
                )
            )
            if current_invalid is not None:
                current.current_lap_invalidated = current_invalid
            last_invalid = _bool(
                _first(
                    values,
                    "lastLapInvalidated",
                    "isLastLapInvalid",
                    default=None,
                )
            )
            if last_invalid is None:
                last_valid = _bool(
                    _first(values, "lastLapValid", default=None)
                )
                if last_valid is not None:
                    last_invalid = not last_valid
            if last_invalid is not None:
                current.last_lap_invalidated = last_invalid
            damage = _percent(_first(values, "damagePercent", "damage", default=None))
            integrity = _float(_first(values, "integrity", "vehicleIntegrity", default=None))
            if damage is None and integrity is not None and 0.0 <= integrity <= 1.0:
                damage = (1.0 - integrity) * 100.0
            current.damage_percent = damage if damage is not None else current.damage_percent
            current.finish_state = str(_first(values, "finishState", "finishStatus", "status", default=current.finish_state) or current.finish_state)
            current.source = source_name
            current.raw = record
            target[identity] = current

    @staticmethod
    def _identity_aliases(value: Any) -> set[str]:
        text = str(value or "").strip()
        if not text:
            return set()
        aliases = {normalize_identity(text)}
        without_suffix = re.sub(r"\s*#\d{3,}$", "", text).strip()
        if without_suffix:
            aliases.add(normalize_identity(without_suffix))
        return {alias for alias in aliases if alias}

    @staticmethod
    def _badge_from_roles(record: dict[str, Any]) -> str:
        ignored = {"driver", "owner", "member", "user"}
        preferred = {
            "admin",
            "staff",
            "developer",
            "creator",
            "partner",
            "moderator",
        }
        fallback = ""
        for container in _walk(record):
            for key, value in container.items():
                if _key(key) not in {"role", "roles"}:
                    continue
                roles = value if isinstance(value, list) else [value]
                for role in roles:
                    text = str(role or "").strip()
                    normalized = text.casefold()
                    if not text or normalized in ignored:
                        continue
                    if normalized in preferred:
                        return text
                    fallback = fallback or text
        return fallback

    def _parse_stint_usage(
        self,
        payload: Any,
        target: dict[str, DriverMetadata],
        source_name: str,
    ) -> None:
        decoded = _decode(payload)
        if not isinstance(decoded, dict):
            return
        for driver_name, samples in decoded.items():
            usage = self._stint_virtual_energy_usage(samples)
            if usage is None:
                continue
            remaining, used, reference_lap = usage
            identity = normalize_identity(driver_name)
            if not identity:
                continue
            current = target.get(
                identity,
                DriverMetadata(driver_name=str(driver_name)),
            )
            current.energy_remaining_fraction = remaining
            current.energy_use_per_lap = used
            current.energy_reference_lap = reference_lap
            current.energy_percent = remaining * 100.0
            current.source = source_name
            target[identity] = current

    @staticmethod
    def _stint_virtual_energy_usage(
        samples: Any,
    ) -> tuple[float, float | None, float] | None:
        """Extrai energia restante e consumo usando a regra do LMU.

        A lista é registrada por volta. Variações negativas ao percorrer o
        histórico ao contrário representam recarga no pit e são ignoradas.
        """
        if not isinstance(samples, list) or not samples:
            return None
        valid = [item for item in samples if isinstance(item, dict)]
        if not valid:
            return None
        latest = valid[-1]
        remaining = _float(latest.get("ve"))
        reference_lap = _float(latest.get("lap"))
        if (
            remaining is None
            or not 0.0 <= remaining <= 1.0
            or remaining == 0.0
        ):
            return None

        uses: list[float] = []
        recent = valid[-6:]
        for older, newer in zip(recent, recent[1:]):
            older_ve = _float(older.get("ve"))
            newer_ve = _float(newer.get("ve"))
            if older_ve is None or newer_ve is None:
                continue
            difference = older_ve - newer_ve
            if 0.0 < difference <= 0.5:
                uses.append(difference)
        used = min(uses[-3:]) if uses else None
        return remaining, used, float(reference_lap or 0.0)

    def _parse_vehicle_catalog(self, payload: Any) -> dict[str, dict[str, str]]:
        """Converte a lista do LMU em vehicleName -> fabricante/modelo.

        É o mesmo princípio usado pelo standings de referência: a descrição
        da pintura (`desc`) é a chave recebida na memória compartilhada.
        """
        result: dict[str, dict[str, str]] = {}
        for record in _walk(_decode(payload)):
            direct_keys = {_key(name) for name in record}
            if not direct_keys & {
                _key("desc"), _key("displayName"), _key("name")
            }:
                continue
            values = _flat(record)
            manufacturer = str(
                _first(values, "manufacturer", "make", "brand", default="")
                or ""
            ).strip()
            if not manufacturer:
                continue

            description = str(
                _first(
                    values,
                    "desc",
                    "displayName",
                    "name",
                    default="",
                )
                or ""
            ).strip()
            if not description:
                continue

            # `/rest/race/car` acrescenta a versão ao fim do nome;
            # `/rest/sessions/getAllVehicles` já fornece `desc` sem versão.
            description = re.sub(r"\s+\d+(?:\.\d+)+$", "", description)
            model = str(
                _first(
                    values,
                    "fullPathTree",
                    "fullTreePath",
                    "vehicleModel",
                    "carModel",
                    default="",
                )
                or ""
            ).strip()
            key = normalize_identity(description)
            if key:
                result[key] = {
                    "manufacturer": manufacturer,
                    "model": model,
                    "description": description,
                }
        return result

    @property
    def _vehicle_catalog_path(self) -> Path:
        return (
            self.project_root
            / "data"
            / "vehicle_catalog"
            / "lmu_vehicles.json"
        )

    def _load_vehicle_catalog(self) -> dict[str, dict[str, str]]:
        try:
            payload = json.loads(
                self._vehicle_catalog_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        return {
            str(key): {
                "manufacturer": str(value.get("manufacturer", "")),
                "model": str(value.get("model", "")),
                "description": str(value.get("description", "")),
            }
            for key, value in payload.items()
            if isinstance(value, dict)
        }

    def _save_vehicle_catalog(self) -> None:
        with self._lock:
            payload = copy.deepcopy(self._vehicle_catalog)
        try:
            self._vehicle_catalog_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            self._vehicle_catalog_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

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

    def _append_session_log(self, event: str, details: dict[str, Any], raw_dump: dict[str, Any] | None = None) -> None:
        try:
            self._session_log_path.parent.mkdir(parents=True, exist_ok=True)
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
            entry = {
                "ts": timestamp,
                "event": event,
                "details": details,
            }
            with self._session_log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            if raw_dump:
                dump_path = (
                    self._session_log_path.parent
                    / f"session_dump_{int(time.time())}.json"
                )
                try:
                    dump_path.write_text(json.dumps(raw_dump, ensure_ascii=False, indent=2), encoding="utf-8")
                except OSError:
                    pass
        except Exception:
            pass
