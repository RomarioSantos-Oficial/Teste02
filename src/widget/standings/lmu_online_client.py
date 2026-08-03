from __future__ import annotations

import base64
import json
import os
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

from .standings_models import OnlineDriverIdentity, OnlineSnapshot


_EVENT_ID_PATTERN = re.compile(
    r"Joining race server for online event\s+([0-9a-fA-F-]{36})",
    re.IGNORECASE,
)


class LMUOnlineIdentityClient:
    """Leitor direto do LMU: memória é tratada fora; aqui entram REST e perfis online."""

    LOCAL_ENDPOINTS = {
        "standings": "/rest/watch/standings",
        "session_info": "/rest/watch/sessionInfo",
        "sessions": "/rest/sessions",
        "teams": "/rest/multiplayer/teams",
    }

    def __init__(self, project_root: Path, config: dict[str, Any]) -> None:
        self.project_root = Path(project_root)
        self.config = config
        self._lock = threading.RLock()
        self._snapshot = OnlineSnapshot()
        self._index: dict[str, OnlineDriverIdentity] = {}
        self._thread: threading.Thread | None = None
        self._last_refresh = 0.0

    def update_config(self, config: dict[str, Any]) -> None:
        with self._lock:
            self.config = config

    def reset(self) -> None:
        with self._lock:
            self._snapshot = OnlineSnapshot()
            self._index = {}
            self._last_refresh = 0.0

    def snapshot(self) -> OnlineSnapshot:
        with self._lock:
            src = self._snapshot
            return OnlineSnapshot(
                local_api_available=src.local_api_available,
                cloud_available=src.cloud_available,
                session_online=src.session_online,
                event_id=src.event_id,
                split_label=src.split_label,
                updated_at_s=src.updated_at_s,
                source_message=src.source_message,
                error=src.error,
                identities=list(src.identities),
            )

    def set_test_snapshot(self, snapshot: OnlineSnapshot) -> None:
        with self._lock:
            self._snapshot = snapshot
            self._index = self._build_index(snapshot.identities)

    def trigger_refresh(self, session: Any | None = None, force: bool = False) -> None:
        if not bool(self.config.get("online_enrichment", True)):
            return

        now = time.monotonic()
        interval = max(2.0, float(self.config.get("online_refresh_seconds", 8.0)))

        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            if not force and now - self._last_refresh < interval:
                return
            self._last_refresh = now
            self._thread = threading.Thread(
                target=self._refresh_worker,
                args=(session,),
                daemon=True,
                name="SectorFlow-LMUOnline",
            )
            self._thread.start()

    def refresh_sync(self, session: Any | None = None) -> OnlineSnapshot:
        snapshot = self._collect_snapshot(session)
        with self._lock:
            self._snapshot = snapshot
            self._index = self._build_index(snapshot.identities)
        return self.snapshot()

    def lookup(self, driver_name: str, *, username: str = "", steam_id: str = "") -> OnlineDriverIdentity | None:
        targets = [steam_id, username, driver_name]
        with self._lock:
            for target in targets:
                key = self.normalize_name(target)
                if key and key in self._index:
                    return self._index[key]

            normalized = self.normalize_name(driver_name)
            if not normalized:
                return None

            threshold = max(
                0.60,
                min(0.99, float(self.config.get("online_name_match_threshold", 0.86))),
            )
            best: OnlineDriverIdentity | None = None
            best_ratio = 0.0
            for identity in self._snapshot.identities:
                for candidate in (identity.display_name, identity.username):
                    candidate_norm = self.normalize_name(candidate)
                    if not candidate_norm:
                        continue
                    ratio = SequenceMatcher(None, normalized, candidate_norm).ratio()
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best = identity
            return best if best_ratio >= threshold else None

    def export_sanitized_snapshot(self, destination: Path) -> Path:
        payload = asdict(self.snapshot())
        for identity in payload.get("identities", []):
            identity.pop("raw", None)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return destination

    def _refresh_worker(self, session: Any | None) -> None:
        try:
            snapshot = self._collect_snapshot(session)
        except Exception as exc:  # proteção da thread
            snapshot = OnlineSnapshot(
                updated_at_s=time.time(),
                error=f"{type(exc).__name__}: {exc}",
            )
        with self._lock:
            self._snapshot = snapshot
            self._index = self._build_index(snapshot.identities)

    def _collect_snapshot(self, session: Any | None) -> OnlineSnapshot:
        del session
        timeout = max(0.5, float(self.config.get("online_timeout_seconds", 2.5)))
        local_base = str(
            self.config.get("local_api_base", "http://127.0.0.1:6397")
        ).rstrip("/")

        payloads: dict[str, Any] = {}
        errors: list[str] = []
        for name, endpoint in self.LOCAL_ENDPOINTS.items():
            try:
                payloads[name] = self._request_json(local_base + endpoint, timeout=timeout)
            except Exception as exc:
                errors.append(f"{name}: {self._short_error(exc)}")

        local_available = bool(payloads)
        local_identities = self._identities_from_payloads(
            payloads.values(), source="LMU REST local"
        )
        event_id = self._find_first_string_by_keys(
            payloads,
            {
                "eventid",
                "event_id",
                "onlineeventid",
                "online_event_id",
                "raceeventid",
            },
        ) or self._find_event_id_in_logs()
        split_label = self._find_first_string_by_keys(
            payloads,
            {"split", "splitlabel", "splitname", "server_split"},
        )
        session_online = bool(event_id) or self._payload_looks_online(payloads)

        cloud_identities: list[OnlineDriverIdentity] = []
        cloud_error = ""
        cloud_available = False
        if bool(self.config.get("use_cloud_profiles", True)) and event_id:
            try:
                cloud_identities = self._fetch_cloud_identities(
                    local_base=local_base,
                    event_id=event_id,
                    timeout=timeout,
                )
                cloud_available = bool(cloud_identities)
            except Exception as exc:
                cloud_error = self._short_error(exc)

        identities = self._merge_identities(local_identities, cloud_identities)
        if cloud_available:
            source_message = "LMU REST + perfis online"
        elif local_available:
            source_message = "LMU REST local"
        else:
            source_message = "Somente memória compartilhada"

        messages: list[str] = []
        if not local_available and errors:
            messages.append("REST local indisponível: " + "; ".join(errors[:2]))
        if cloud_error:
            messages.append("Perfis online: " + cloud_error)

        return OnlineSnapshot(
            local_api_available=local_available,
            cloud_available=cloud_available,
            session_online=session_online,
            event_id=event_id,
            split_label=split_label,
            updated_at_s=time.time(),
            source_message=source_message,
            error=" | ".join(messages),
            identities=identities,
        )

    def _fetch_cloud_identities(
        self,
        *,
        local_base: str,
        event_id: str,
        timeout: float,
    ) -> list[OnlineDriverIdentity]:
        ticket_payload = self._request_json(
            local_base + "/rest/profile/getAuthSessionTicket",
            timeout=timeout,
        )
        ticket = self._find_first_string_by_keys(
            ticket_payload,
            {"authsessionticket", "auth_session_ticket", "ticket", "token"},
        )
        if not ticket and isinstance(ticket_payload, str):
            ticket = ticket_payload.strip()
        if not ticket:
            raise RuntimeError("LMU não retornou authSessionTicket")

        client_key = self._resolve_client_key()
        if not client_key:
            raise RuntimeError(
                "chave cliente Nakama não configurada; use o editor ou a variável "
                "SECTOR_FLOW_NAKAMA_KEY"
            )

        cloud_base = str(
            self.config.get(
                "nakama_base_url",
                "https://lmu-prod.eu-central1-a.nakamacloud.io",
            )
        ).rstrip("/")
        basic = base64.b64encode((client_key + ":").encode("utf-8")).decode("ascii")
        auth_response = self._request_json(
            cloud_base + "/v2/account/authenticate/steam?create=false&sync=false",
            method="POST",
            body={"token": ticket},
            headers={"Authorization": "Basic " + basic},
            timeout=timeout,
        )
        session_token = self._find_first_string_by_keys(
            auth_response, {"token", "sessiontoken", "session_token"}
        )
        if not session_token:
            raise RuntimeError("autenticação online recusada")

        headers = {"Authorization": "Bearer " + session_token}
        event_type = str(self.config.get("online_event_type", "daily") or "daily")
        event_info = self._call_rpc(
            cloud_base,
            "event_get",
            {"eventType": event_type, "eventId": event_id},
            headers,
            timeout,
        )

        records: list[Any] = []
        max_pages = max(1, min(20, int(self.config.get("online_max_pages", 8))))
        for page in range(max_pages):
            response = self._call_rpc(
                cloud_base,
                "event_entries_get",
                {
                    "eventType": event_type,
                    "eventId": event_id,
                    "page": page,
                    "take": 100,
                    "class": "",
                },
                headers,
                timeout,
            )
            page_records = self._find_record_list(response)
            if not page_records:
                break
            records.extend(page_records)
            if len(page_records) < 100:
                break

        identities = self._identities_from_payloads(
            [event_info, records], source="LMU Online"
        )
        usernames = sorted({item.username for item in identities if item.username})
        if usernames:
            user_payloads: list[Any] = []
            for start in range(0, len(usernames), 40):
                query = urllib.parse.urlencode(
                    [("usernames", value) for value in usernames[start : start + 40]]
                )
                user_payloads.append(
                    self._request_json(
                        cloud_base + "/v2/user?" + query,
                        headers=headers,
                        timeout=timeout,
                    )
                )
            profiles = self._identities_from_payloads(
                user_payloads, source="LMU Online Profile"
            )
            identities = self._merge_identities(identities, profiles)
        return identities

    def _resolve_client_key(self) -> str:
        configured = str(self.config.get("nakama_client_key", "")).strip()
        if configured:
            return configured
        environment = os.environ.get("SECTOR_FLOW_NAKAMA_KEY", "").strip()
        if environment:
            return environment
        key_file = self.project_root / "data" / "online_profiles" / "nakama_client_key.txt"
        if key_file.exists():
            try:
                return key_file.read_text(encoding="utf-8").strip()
            except OSError:
                return ""
        return ""

    def _call_rpc(
        self,
        base: str,
        name: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> Any:
        endpoint = base + "/v2/rpc/" + name
        attempts = [
            (endpoint, {"payload": json.dumps(payload, ensure_ascii=False)}),
            (endpoint + "?unwrap", payload),
        ]
        last_error: Exception | None = None
        for url, body in attempts:
            try:
                return self._decode_jsonish(
                    self._request_json(
                        url,
                        method="POST",
                        body=body,
                        headers=headers,
                        timeout=timeout,
                    )
                )
            except Exception as exc:
                last_error = exc
        raise last_error or RuntimeError(f"RPC {name} sem resposta")

    def _request_json(
        self,
        url: str,
        *,
        method: str = "GET",
        body: Any | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 2.5,
    ) -> Any:
        request_headers = {
            "Accept": "application/json",
            "User-Agent": "SectorFlowDrive/StandingsOnlineV1",
        }
        if headers:
            request_headers.update(headers)
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            url,
            data=data,
            headers=request_headers,
            method=method,
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
        if not raw:
            return None
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            return None
        try:
            return self._decode_jsonish(json.loads(text))
        except json.JSONDecodeError:
            return text

    def _identities_from_payloads(
        self,
        payloads: Iterable[Any],
        *,
        source: str,
    ) -> list[OnlineDriverIdentity]:
        identities: list[OnlineDriverIdentity] = []
        for payload in payloads:
            for record in self._walk_records(self._decode_jsonish(payload)):
                identity = self._identity_from_record(record, source)
                if identity is not None:
                    identities.append(identity)
        return self._merge_identities(identities, [])

    def _identity_from_record(
        self,
        record: dict[str, Any],
        source: str,
    ) -> OnlineDriverIdentity | None:
        merged = dict(record)
        for key in ("profile", "metadata", "properties", "data", "driver", "user", "account"):
            nested = self._decode_jsonish(merged.get(key))
            if isinstance(nested, dict):
                for nested_key, value in nested.items():
                    merged.setdefault(nested_key, value)

        display_name = self._first_text(
            merged, ("driverName", "displayName", "display_name", "nickname", "name")
        )
        username = self._first_text(
            merged, ("username", "userName", "user_name", "nakamaUsername")
        )
        steam_id = self._first_text(
            merged, ("steamId", "steamID", "steam_id", "platformId")
        )
        driver_rank_raw = self._first_value(merged, ("driverRank", "driver_rank"))
        safety_rank_raw = self._first_value(
            merged, ("safetyRank", "safeRank", "safety_rank", "sr")
        )
        driver_rank = self._format_rank(driver_rank_raw)
        safety_rank = self._format_rank(safety_rank_raw)
        progress = self._first_number(
            merged,
            ("driverRankProgress", "driver_rank_progress", "rankProgress"),
        )
        if progress is None and isinstance(driver_rank_raw, dict):
            progress = self._first_number(driver_rank_raw, ("progress", "rankProgress"))

        nationality = self._first_text(
            merged, ("nationality", "countryCode", "country_code", "country")
        )
        badge = self._first_text(
            merged, ("badge", "driverBadge", "contactBadge", "srBadge")
        )
        incidents = self._first_int(
            merged, ("incidents", "incidentCount", "incident_count")
        )
        estimated_gain = self._first_number(
            merged,
            (
                "estimatedDriverRankGain",
                "estimated_driver_rank_gain",
                "driverRankGain",
            ),
        )
        team_name = self._first_text(merged, ("teamName", "team_name", "team"))
        car_number = self._first_text(
            merged, ("carNumber", "car_number", "vehicleNumber", "number")
        )
        vehicle_class = self._first_text(
            merged, ("carClass", "vehicleClass", "vehicle_class", "className")
        )

        has_identity = any((display_name, username, steam_id))
        has_useful_data = any(
            (
                driver_rank,
                safety_rank,
                nationality,
                badge,
                team_name,
                car_number,
                vehicle_class,
            )
        )
        if not (has_identity and has_useful_data):
            return None

        return OnlineDriverIdentity(
            display_name=display_name or username,
            username=username,
            steam_id=steam_id,
            team_name=team_name,
            car_number=car_number,
            vehicle_class=vehicle_class,
            driver_rank=driver_rank,
            driver_rank_progress=progress,
            safety_rank=safety_rank,
            nationality=nationality.upper() if len(nationality.strip()) <= 3 else nationality,
            badge=badge,
            incidents=incidents,
            estimated_driver_rank_gain=estimated_gain,
            source=source,
            raw=merged,
        )

    def _merge_identities(
        self,
        first: list[OnlineDriverIdentity],
        second: list[OnlineDriverIdentity],
    ) -> list[OnlineDriverIdentity]:
        merged: dict[str, OnlineDriverIdentity] = {}
        for identity in list(first) + list(second):
            key = (
                self.normalize_name(identity.steam_id)
                or self.normalize_name(identity.username)
                or self.normalize_name(identity.display_name)
            )
            if not key:
                continue
            existing = merged.get(key)
            if existing is None:
                merged[key] = identity
                continue
            for field_name in (
                "display_name",
                "username",
                "steam_id",
                "team_name",
                "car_number",
                "vehicle_class",
                "driver_rank",
                "driver_rank_progress",
                "safety_rank",
                "nationality",
                "badge",
                "incidents",
                "estimated_driver_rank_gain",
                "source",
            ):
                value = getattr(identity, field_name)
                if value not in ("", None):
                    setattr(existing, field_name, value)
            existing.raw.update(identity.raw)
        return list(merged.values())

    def _build_index(
        self, identities: list[OnlineDriverIdentity]
    ) -> dict[str, OnlineDriverIdentity]:
        index: dict[str, OnlineDriverIdentity] = {}
        for identity in identities:
            for value in (identity.steam_id, identity.username, identity.display_name):
                key = self.normalize_name(value)
                if key:
                    index[key] = identity
        return index

    def _find_event_id_in_logs(self) -> str:
        newest = ""
        newest_mtime = -1.0
        for directory in self._log_directories():
            if not directory.exists():
                continue
            try:
                paths = sorted(
                    [path for path in directory.iterdir() if path.is_file()],
                    key=lambda path: path.stat().st_mtime,
                    reverse=True,
                )[:12]
            except OSError:
                continue
            for path in paths:
                try:
                    size = path.stat().st_size
                    with path.open("rb") as handle:
                        if size > 2_000_000:
                            handle.seek(size - 2_000_000)
                        text = handle.read().decode("utf-8", errors="ignore")
                    matches = list(_EVENT_ID_PATTERN.finditer(text))
                    if matches and path.stat().st_mtime > newest_mtime:
                        newest_mtime = path.stat().st_mtime
                        newest = matches[-1].group(1)
                except OSError:
                    continue
        return newest

    def _log_directories(self) -> list[Path]:
        configured = str(self.config.get("lmu_log_directory", "")).strip()
        result: list[Path] = []
        if configured:
            result.append(Path(configured))
        for variable, fallback in (
            ("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
            ("PROGRAMFILES", r"C:\Program Files"),
        ):
            result.append(
                Path(os.environ.get(variable, fallback))
                / "Steam"
                / "steamapps"
                / "common"
                / "Le Mans Ultimate"
                / "UserData"
                / "Log"
            )
        return result

    @staticmethod
    def normalize_name(value: str) -> str:
        text = unicodedata.normalize("NFKD", str(value or ""))
        text = "".join(character for character in text if not unicodedata.combining(character))
        text = text.casefold()
        text = re.sub(r"#\s*\d+", " ", text)
        text = re.sub(r"[^a-z0-9]+", " ", text)
        return " ".join(text.split())

    @classmethod
    def _walk_records(cls, payload: Any) -> Iterable[dict[str, Any]]:
        payload = cls._decode_jsonish(payload)
        if isinstance(payload, dict):
            yield payload
            for value in payload.values():
                yield from cls._walk_records(value)
        elif isinstance(payload, list):
            for value in payload:
                yield from cls._walk_records(value)

    @classmethod
    def _find_record_list(cls, payload: Any) -> list[Any]:
        payload = cls._decode_jsonish(payload)
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in (
                "entries",
                "eventEntries",
                "event_entries",
                "standings",
                "participants",
                "results",
                "items",
                "data",
            ):
                value = cls._decode_jsonish(payload.get(key))
                if isinstance(value, list):
                    return value
            for value in payload.values():
                found = cls._find_record_list(value)
                if found:
                    return found
        return []

    @classmethod
    def _decode_jsonish(cls, value: Any) -> Any:
        current = value
        for _ in range(4):
            if isinstance(current, dict):
                if set(current) == {"payload"}:
                    current = current["payload"]
                    continue
                return current
            if not isinstance(current, str):
                return current
            text = current.strip()
            if not text or text[0] not in '[{"':
                return current
            try:
                current = json.loads(text)
            except json.JSONDecodeError:
                return current
        return current

    @classmethod
    def _find_first_string_by_keys(cls, payload: Any, keys: set[str]) -> str:
        normalized_keys = {key.casefold() for key in keys}
        for record in cls._walk_records(payload):
            for key, value in record.items():
                if str(key).casefold() in normalized_keys and value not in (None, ""):
                    return str(cls._decode_jsonish(value)).strip()
        return ""

    @classmethod
    def _payload_looks_online(cls, payload: Any) -> bool:
        for record in cls._walk_records(payload):
            for key, value in record.items():
                if str(key).casefold() in {
                    "online",
                    "isonline",
                    "sessionisonline",
                    "multiplayer",
                    "connectiontype",
                }:
                    if str(value).strip().casefold() in {
                        "true",
                        "1",
                        "online",
                        "multiplayer",
                        "dedicated",
                    }:
                        return True
        return False

    @staticmethod
    def _first_value(mapping: dict[str, Any], keys: tuple[str, ...]) -> Any:
        lower = {str(key).casefold(): value for key, value in mapping.items()}
        for key in keys:
            value = lower.get(key.casefold())
            if value not in (None, ""):
                return value
        return None

    @classmethod
    def _first_text(cls, mapping: dict[str, Any], keys: tuple[str, ...]) -> str:
        value = cls._decode_jsonish(cls._first_value(mapping, keys))
        if value in (None, ""):
            return ""
        if isinstance(value, dict):
            for key in ("name", "label", "value", "code"):
                nested = value.get(key)
                if nested not in (None, ""):
                    return str(nested).strip()
            return ""
        return str(value).strip()

    @classmethod
    def _first_number(cls, mapping: dict[str, Any], keys: tuple[str, ...]) -> float | None:
        value = cls._first_value(mapping, keys)
        if isinstance(value, dict):
            value = cls._first_value(value, ("value", "progress", "amount"))
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _first_int(cls, mapping: dict[str, Any], keys: tuple[str, ...]) -> int | None:
        value = cls._first_number(mapping, keys)
        return int(value) if value is not None else None

    @classmethod
    def _format_rank(cls, value: Any) -> str:
        value = cls._decode_jsonish(value)
        if isinstance(value, dict):
            rank = cls._first_text(value, ("rank", "name", "label", "code"))
            tier = cls._first_int(value, ("tier", "level"))
            return f"{rank} {tier}" if rank and tier is not None else rank
        return "" if value in (None, "") else str(value).strip()

    @staticmethod
    def _short_error(error: Exception) -> str:
        if isinstance(error, urllib.error.HTTPError):
            return f"HTTP {error.code}"
        if isinstance(error, urllib.error.URLError):
            return str(error.reason)
        return str(error)
