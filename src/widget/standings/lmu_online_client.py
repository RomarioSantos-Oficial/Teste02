from __future__ import annotations

import json
import os
import re
import ssl
import threading
import time
import unicodedata
import urllib.error
import urllib.request
from dataclasses import asdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

try:
    import winreg
except ImportError:  # pragma: no cover - somente Windows possui o LMU
    winreg = None

from .standings_models import OnlineDriverIdentity, OnlineSnapshot


_EVENT_ID_PATTERN = re.compile(
    r"Joining race server for online event\s+([0-9a-fA-F-]{36})",
    re.IGNORECASE,
)


class LMUOnlineIdentityClient:
    """Leitor direto do LMU: memória é tratada fora; aqui entram REST e perfis online."""

    LOCAL_ENDPOINTS = {
        "profile": "/rest/profile/",
        "profile_info": "/rest/profile/profileInfo/getProfileInfo",
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
        self._last_event_probe = 0.0
        self._observed_event_id = ""
        self._split_session_signature = ""
        self._session_signature = ""
        self._generation = 0
        # A divisao e imutavel dentro do mesmo evento. Depois da primeira
        # resposta valida, reutiliza o valor sem consultar RaceOS novamente.
        self._split_by_event_id: dict[str, str] = {}
        self._ssl_context = ssl.create_default_context()
        # Python 3.13 ativa X509_STRICT por padrao. Algumas cadeias aceitas
        # pelo Windows e pelo cliente oficial do LMU nao marcam Basic
        # Constraints como "critical". Mantemos hostname, validade e CA
        # verificados, removendo somente essa exigencia de compatibilidade.
        if hasattr(ssl, "VERIFY_X509_STRICT"):
            self._ssl_context.verify_flags &= ~ssl.VERIFY_X509_STRICT

    def update_config(self, config: dict[str, Any]) -> None:
        with self._lock:
            self.config = config

    def reset(self) -> None:
        with self._lock:
            self._snapshot = OnlineSnapshot()
            self._index = {}
            self._last_refresh = 0.0
            self._last_event_probe = 0.0
            self._observed_event_id = ""
            self._split_session_signature = ""
            self._split_by_event_id.clear()
            self._session_signature = ""
            self._generation += 1

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

    def hide_split(self) -> None:
        """Oculta o valor sem descartar ranks e paises ja recebidos."""
        with self._lock:
            self._snapshot.split_label = ""

    def request_split_recheck(self, session: Any | None = None) -> None:
        """Forca uma nova consulta no proximo quadro de coleta valido."""
        current_event_id = self._find_event_id_in_logs()
        with self._lock:
            event_id = current_event_id
            if event_id:
                self._split_by_event_id.pop(event_id, None)
            self._observed_event_id = current_event_id
            if not current_event_id:
                self._snapshot.event_id = ""
            self._snapshot.split_label = ""
            self._split_session_signature = self._make_split_session_signature(
                session
            )
            self._last_refresh = 0.0
            # Invalida uma resposta antiga que ainda esteja em andamento.
            self._generation += 1

    def trigger_refresh(self, session: Any | None = None, force: bool = False) -> None:
        # A leitura REST local normal e feita por LocalStandingsEnrichment.
        # Este cliente usa o mesmo fluxo RaceOS do cliente oficial do LMU.
        # O ticket temporario nunca e persistido pelo Sector Flow.
        if not bool(self.config.get("online_enrichment", False)):
            return
        if not bool(self.config.get("use_cloud_profiles", False)):
            return
        now = time.monotonic()
        interval = max(
            30.0,
            float(self.config.get("online_refresh_seconds", 900.0)),
        )
        signature = self._make_session_signature(session)
        split_session_signature = self._make_split_session_signature(session)

        # A entrada no servidor pode acontecer sem mudar imediatamente pista,
        # sessao ou lista de pilotos. Nesse caso a assinatura acima permanece
        # igual e o intervalo normal de 15 minutos conservaria o split antigo.
        # Uma sondagem leve e limitada detecta somente a troca do eventId.
        event_changed = False
        current_event_id = ""
        if now - self._last_event_probe >= 2.0:
            self._last_event_probe = now
            current_event_id = self._find_event_id_in_logs()
            with self._lock:
                event_changed = bool(
                    current_event_id
                    and current_event_id != self._observed_event_id
                )
                if current_event_id:
                    # Marca imediatamente o evento observado. A consulta
                    # RaceOS pode levar mais que os dois segundos da sonda;
                    # comparar com o snapshot ainda vazio cancelava cada
                    # worker antes que DR/SR/pais/split fossem publicados.
                    self._observed_event_id = current_event_id

        with self._lock:
            split_session_changed = bool(
                split_session_signature
                and split_session_signature != self._split_session_signature
            )
            if split_session_changed:
                self._split_session_signature = split_session_signature
                event_for_split = current_event_id or self._observed_event_id
                if event_for_split:
                    self._split_by_event_id.pop(event_for_split, None)
                # Mantem DR/SR/paises, mas remove o split antigo ate a
                # verificacao unica da nova sessao terminar.
                self._snapshot.split_label = ""
                self._last_refresh = 0.0
            signature_changed = bool(
                signature and signature != self._session_signature
            )
            if event_changed:
                self._session_signature = signature
                self._snapshot = OnlineSnapshot()
                self._index = {}
                self._last_refresh = 0.0
                self._generation += 1
            elif signature_changed:
                # Practice, Quali e Race do mesmo evento usam os mesmos
                # perfis RaceOS. Preserva DR/SR/SOF durante a transicao e
                # apenas agenda uma atualizacao em segundo plano.
                self._session_signature = signature
                self._last_refresh = 0.0
                self._generation += 1
            if self._thread is not None and self._thread.is_alive():
                return
            if not force and now - self._last_refresh < interval:
                return
            self._last_refresh = now
            generation = self._generation
            self._thread = threading.Thread(
                target=self._refresh_worker,
                args=(session, generation),
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

    def _refresh_worker(self, session: Any | None, generation: int) -> None:
        try:
            snapshot = self._collect_snapshot(session)
        except Exception as exc:  # proteção da thread
            snapshot = OnlineSnapshot(
                updated_at_s=time.time(),
                error=f"{type(exc).__name__}: {exc}",
            )
        with self._lock:
            if generation != self._generation:
                return
            self._snapshot = snapshot
            self._index = self._build_index(snapshot.identities)

    @staticmethod
    def _make_session_signature(session: Any | None) -> str:
        if session is None:
            return ""
        names = sorted(
            str(getattr(driver, "driver_name", "") or "").strip().casefold()
            for driver in list(getattr(session, "drivers", []) or [])
            if str(getattr(driver, "driver_name", "") or "").strip()
        )
        return "|".join(
            (
                str(getattr(session, "track_name", "") or ""),
                str(getattr(session, "session", 0) or 0),
                str(getattr(session, "max_laps", 0) or 0),
                ",".join(names),
            )
        )

    def _collect_snapshot(self, session: Any | None) -> OnlineSnapshot:
        timeout = max(0.5, float(self.config.get("online_timeout_seconds", 2.5)))
        configured_base = str(self.config.get("local_api_base", "")).strip()
        if configured_base:
            local_base = configured_base.rstrip("/")
        else:
            local_host = str(self.config.get("local_api_host", "127.0.0.1"))
            local_port = int(self.config.get("local_api_port", 6397))
            local_base = f"http://{local_host}:{local_port}"

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
        session_driver_names = [
            str(getattr(driver, "driver_name", "") or "").strip()
            for driver in list(getattr(session, "drivers", []) or [])
            if str(getattr(driver, "driver_name", "") or "").strip()
        ]
        session_driver_names.extend(
            self._driver_names_from_teams(payloads.get("teams"))
        )
        session_driver_names = list(
            dict.fromkeys(name for name in session_driver_names if name)
        )
        if not session_driver_names:
            session_driver_names = [
                item.display_name
                for item in local_identities
                if item.display_name
            ]
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
        session_online = self._multiplayer_roster_available(
            payloads.get("teams")
        ) or self._payload_looks_online(payloads)

        cloud_identities: list[OnlineDriverIdentity] = []
        cloud_split_label = ""
        cloud_error = ""
        cloud_available = False
        if (
            bool(self.config.get("use_cloud_profiles", False))
            and session_driver_names
        ):
            try:
                cloud_identities, cloud_split_label = self._fetch_cloud_identities(
                    local_base=local_base,
                    driver_names=session_driver_names,
                    event_id=event_id,
                    timeout=timeout,
                )
                cloud_available = bool(cloud_identities)
            except Exception as exc:
                cloud_error = self._short_error(exc)

        identities = self._merge_identities(local_identities, cloud_identities)
        split_label = cloud_split_label or split_label
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
        driver_names: list[str],
        event_id: str,
        timeout: float,
    ) -> tuple[list[OnlineDriverIdentity], str]:
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

        cloud_base = str(
            self.config.get(
                "raceos_base_url",
                "https://raceos.gg",
            )
        ).rstrip("/")
        auth_response = self._request_json(
            cloud_base + "/authenticate",
            method="POST",
            body={
                "token": ticket,
                "game": "lmu",
                "platform": "steam",
            },
            timeout=timeout,
        )
        session_token = self._find_first_string_by_keys(
            auth_response, {"accesstoken", "access_token"}
        )
        if not session_token:
            raise RuntimeError("autenticação online recusada")

        headers = {"Game-Authorization": "Bearer " + session_token}
        profile_payloads: list[Any] = []
        if isinstance(auth_response, dict) and auth_response.get("player"):
            profile_payloads.append(auth_response.get("player"))
        else:
            profile_payloads.append(
                self._request_json(
                    cloud_base + "/api/v1/player",
                    headers=headers,
                    timeout=timeout,
                )
            )

        usernames = sorted(
            {
                candidate
                for value in driver_names
                for candidate in (value, self._strip_driver_hash_suffix(value))
                if candidate
            }
        )
        for start in range(0, len(usernames), 40):
            profile_payloads.append(
                self._request_json(
                    cloud_base + "/api/v1/players",
                    method="POST",
                    body={"usernames": usernames[start : start + 40]},
                    headers=headers,
                    timeout=timeout,
                )
            )
        split_label = ""
        if event_id:
            with self._lock:
                split_label = self._split_by_event_id.get(event_id, "")
            event_type = str(
                self.config.get("online_event_type", "daily") or "daily"
            ).strip().casefold()
            if event_type not in {"daily", "weekly"}:
                event_type = "daily"
            if not split_label:
                split_url = (
                    f"{cloud_base}/api/v1/event/my-split/"
                    f"{event_type}/{event_id}"
                )
                for attempt in range(5):
                    try:
                        split_payload = self._request_json(
                            split_url,
                            headers=headers,
                            timeout=timeout,
                        )
                        split_label = self._split_label_from_payload(split_payload)
                    except Exception:
                        split_label = ""
                    if split_label:
                        break
                    if attempt < 4:
                        time.sleep(1.0)
                # Ausencia de resposta nao prova que existe somente um split.
                # Mantemos vazio para uma tentativa futura, sem fabricar 1/1.
                if split_label:
                    with self._lock:
                        self._split_by_event_id[event_id] = split_label

        identities = self._identities_from_payloads(
            profile_payloads,
            source="LMU RaceOS",
        )
        return identities, split_label

    @staticmethod
    def _make_split_session_signature(session: Any | None) -> str:
        if session is None or not bool(getattr(session, "connected", True)):
            return ""
        number = int(getattr(session, "session", 0) or 0)
        drivers = list(getattr(session, "drivers", []) or [])
        if not (1 <= number <= 13) or not drivers:
            return ""
        return "|".join(
            (
                str(getattr(session, "track_name", "") or ""),
                str(number),
            )
        )
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
        open_kwargs: dict[str, Any] = {"timeout": timeout}
        if url.casefold().startswith("https://"):
            open_kwargs["context"] = self._ssl_context
        with urllib.request.urlopen(request, **open_kwargs) as response:
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
        # Perfis Nakama guardam profile/driverRank/safetyRank dentro de
        # `metadata`, que por sua vez costuma ser uma string JSON. Duas
        # passagens incluem também os objetos que surgem após decodificá-la.
        for _ in range(2):
            for key in (
                "profile", "metadata", "properties", "data", "driver",
                "user", "account",
            ):
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
        safety_progress = self._first_number(
            merged,
            (
                "safetyRankProgress", "safety_rank_progress",
                "safetyRankPercentage", "safetyRankPercent",
                "safeRankProgress", "srProgress",
            ),
        )
        if safety_progress is None and isinstance(safety_rank_raw, dict):
            safety_progress = self._first_number(
                safety_rank_raw,
                ("progress", "rankProgress", "percentage", "percent"),
            )

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
            safety_rank_progress=safety_progress,
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
        merged: list[OnlineDriverIdentity] = []
        aliases: dict[str, OnlineDriverIdentity] = {}
        for identity in list(first) + list(second):
            keys = {
                self.normalize_name(value)
                for value in (
                    identity.steam_id,
                    identity.username,
                    identity.display_name,
                    self._strip_driver_hash_suffix(identity.display_name),
                )
                if self.normalize_name(value)
            }
            if not keys:
                continue
            existing = next((aliases[key] for key in keys if key in aliases), None)
            if existing is None:
                merged.append(identity)
                for key in keys:
                    aliases[key] = identity
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
                "safety_rank_progress",
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
            for value in (
                existing.steam_id,
                existing.username,
                existing.display_name,
                self._strip_driver_hash_suffix(existing.display_name),
            ):
                key = self.normalize_name(value)
                if key:
                    aliases[key] = existing
        return merged

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
                    [
                        path
                        for path in directory.glob("trace_*.txt")
                        if path.is_file()
                    ],
                    key=lambda path: path.stat().st_mtime,
                    reverse=True,
                )[:1]
            except OSError:
                continue
            # Cada inicializacao do LMU cria um trace novo. Consultar traces
            # anteriores fazia uma sessao offline herdar o eventId/split da
            # execucao anterior do jogo.
            for path in paths:
                try:
                    size = path.stat().st_size
                    with path.open("rb") as handle:
                        if size > 8_000_000:
                            head = handle.read(2_000_000)
                            handle.seek(max(0, size - 2_000_000))
                            raw = head + b"\n" + handle.read()
                        else:
                            raw = handle.read()
                        text = raw.decode("utf-8", errors="ignore")
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
        steam_roots: list[Path] = []
        for variable, fallback in (
            ("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
            ("PROGRAMFILES", r"C:\Program Files"),
        ):
            steam_roots.append(Path(os.environ.get(variable, fallback)) / "Steam")
        if winreg is not None:
            for hive, key_name in (
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
            ):
                try:
                    with winreg.OpenKey(hive, key_name) as key:
                        steam_roots.append(Path(winreg.QueryValueEx(key, "InstallPath")[0]))
                except OSError:
                    continue

        libraries: list[Path] = []
        for steam_root in steam_roots:
            libraries.append(steam_root)
            library_file = steam_root / "steamapps" / "libraryfolders.vdf"
            try:
                text = library_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for raw_path in re.findall(r'"path"\s+"([^"]+)"', text, re.IGNORECASE):
                libraries.append(Path(raw_path.replace(r"\\", "\\")))

        seen: set[str] = set()
        for library in libraries:
            candidate = (
                library
                / "steamapps"
                / "common"
                / "Le Mans Ultimate"
                / "UserData"
                / "Log"
            )
            key = str(candidate).casefold()
            if key not in seen:
                seen.add(key)
                result.append(candidate)
        return result

    @staticmethod
    def normalize_name(value: str) -> str:
        text = unicodedata.normalize("NFKD", str(value or ""))
        text = "".join(character for character in text if not unicodedata.combining(character))
        text = text.casefold()
        text = re.sub(r"#\s*\d+", " ", text)
        text = re.sub(r"[^a-z0-9]+", " ", text)
        return " ".join(text.split())

    @staticmethod
    def _strip_driver_hash_suffix(value: str) -> str:
        return re.sub(r"\s*#\s*\d+\s*$", "", str(value or "")).strip()

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
    def _split_label_from_payload(cls, payload: Any) -> str:
        explicit = cls._find_first_string_by_keys(
            payload,
            {"splitlabel", "splitname", "divisionlabel", "divisionname"},
        )
        if explicit:
            match = re.search(r"(\d+)\s*/\s*(\d+)", explicit)
            return f"S {match.group(1)}/{match.group(2)}" if match else ""
        current = cls._find_first_string_by_keys(
            payload,
            {"split", "splitno", "splitnumber", "currentsplit", "division", "divisionno"},
        )
        total = cls._find_first_string_by_keys(
            payload,
            {
                "totalsplits", "splitcount", "numberofsplits", "totaldivisions",
                "divisioncount", "maxsplit", "maxsplits", "lastsplit",
                "numsplit", "numsplits", "numofsplits", "splittotal",
                "divisiontotal",
            },
        )
        if current and total:
            return f"S {current}/{total}"
        # Um numero isolado nao basta: mantem as tentativas de 1 segundo e
        # nunca grava um cabecalho incompleto como "S 6".
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

    @classmethod
    def _multiplayer_roster_available(cls, payload: Any) -> bool:
        decoded = cls._decode_jsonish(payload)
        if not isinstance(decoded, dict):
            return False
        for key, value in decoded.items():
            if str(key).casefold() != "drivers":
                continue
            value = cls._decode_jsonish(value)
            return isinstance(value, (dict, list)) and bool(value)
        return any(
            cls._multiplayer_roster_available(value)
            for value in decoded.values()
            if isinstance(value, (dict, list, str))
        )

    @classmethod
    def _driver_names_from_teams(cls, payload: Any) -> list[str]:
        """Extrai os nomes que o LMU publica como chaves de ``drivers``."""
        decoded = cls._decode_jsonish(payload)
        if not isinstance(decoded, dict):
            return []
        result: list[str] = []
        for key, value in decoded.items():
            if str(key).casefold() == "drivers":
                roster = cls._decode_jsonish(value)
                if isinstance(roster, dict):
                    result.extend(
                        str(name).strip()
                        for name in roster
                        if str(name).strip()
                    )
                elif isinstance(roster, list):
                    for record in roster:
                        if isinstance(record, dict):
                            name = cls._first_text(
                                record,
                                (
                                    "driverName",
                                    "displayName",
                                    "username",
                                    "name",
                                ),
                            )
                            if name:
                                result.append(name)
            elif isinstance(value, (dict, list, str)):
                result.extend(cls._driver_names_from_teams(value))
        return list(dict.fromkeys(result))

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
