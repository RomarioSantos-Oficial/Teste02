from __future__ import annotations

import json
import threading
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from PySide6.QtCore import QObject, Signal

from .archive import LapRecord


class LapCloudClient(QObject):
    """Async HTTP client; the desktop never holds Discord client secrets."""

    login_url_ready = Signal(str)
    login_changed = Signal(str)
    server_check_finished = Signal(bool, str)
    rankings_ready = Signal(object, str)
    all_rankings_ready = Signal(object, str)
    telemetry_ready = Signal(object, str)
    upload_finished = Signal(object, str)
    profile_sync_finished = Signal(str, str)
    cloud_data_deleted = Signal(str)
    request_failed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.base_url = ""
        self._access_token = ""
        self._user_name = ""
        self.account_key = ""
        self._lock = threading.Lock()
        self._uploading_ids: set[str] = set()

    @property
    def authenticated(self) -> bool:
        return bool(self._access_token)

    @property
    def display_account(self) -> str:
        return self._user_name

    def configure(self, base_url: str) -> None:
        self.base_url = str(base_url or "").strip().rstrip("/")

    def check_server(self) -> None:
        def work() -> None:
            try:
                result = self._request("/health")
                healthy = result.get("status") == "ok" and result.get("database") == "ok"
                if not healthy:
                    raise RuntimeError("O servidor respondeu, mas não confirmou a conexão com o banco de dados.")
                self.server_check_finished.emit(True, "")
            except Exception as exc:
                self.server_check_finished.emit(False, str(exc))

        threading.Thread(target=work, name="SectorFlowServerHealth", daemon=True).start()

    def logout(self) -> None:
        self._access_token = ""
        self._user_name = ""
        self.account_key = ""
        self.login_changed.emit("")

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _request(
        self, path: str, *, method: str = "GET", payload: dict | None = None,
        authenticated: bool = False, auth_token: str | None = None,
    ) -> Any:
        if not self.base_url:
            raise ValueError("Configure o endereço do backend SectorFlow primeiro.")
        headers = {"Accept": "application/json", "User-Agent": "SectorFlow-Overlay"}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if authenticated:
            token = auth_token if auth_token is not None else self._access_token
            if not token:
                raise ValueError("Conecte sua conta Discord para usar o ranking online.")
            if auth_token is not None and token != self._access_token:
                raise RuntimeError("A conta Discord mudou durante a sincronizaÃ§Ã£o.")
            headers["Authorization"] = f"Bearer {token}"
        request = Request(self._url(path), data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=18.0) as response:
                raw = response.read(2_000_000)
        except HTTPError as exc:
            detail = exc.read(8192).decode("utf-8", errors="replace")
            raise RuntimeError(f"Backend respondeu HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"Falha ao acessar o backend: {exc}") from exc
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Resposta inválida do backend SectorFlow.") from exc

    def start_login(self) -> None:
        def work() -> None:
            try:
                flow = self._request("/v1/auth/start", method="POST", payload={})
                authorization_url = str(flow.get("authorization_url", ""))
                flow_id = str(flow.get("flow_id", ""))
                poll_secret = str(flow.get("poll_secret", ""))
                if not authorization_url or not flow_id or not poll_secret:
                    raise RuntimeError("O backend não retornou um fluxo Discord válido.")
                self.login_url_ready.emit(authorization_url)
                deadline = time.monotonic() + 240.0
                while time.monotonic() < deadline:
                    time.sleep(2.0)
                    result = self._request(
                        "/v1/auth/poll", method="POST",
                        payload={"flow_id": flow_id, "poll_secret": poll_secret},
                    )
                    if result.get("status") == "complete":
                        self._access_token = str(result.get("access_token", ""))
                        self._user_name = str(result.get("display_name", ""))
                        self.account_key = str(result.get("account_key", ""))
                        if not self._access_token:
                            raise RuntimeError("Login concluído sem token de sessão.")
                        self.login_changed.emit(self._user_name)
                        return
                    if result.get("status") == "expired":
                        raise RuntimeError("O prazo do login Discord expirou.")
                raise RuntimeError("Login não concluído em quatro minutos.")
            except Exception as exc:
                self.request_failed.emit(str(exc))

        threading.Thread(target=work, name="SectorFlowDiscordLogin", daemon=True).start()

    def fetch_rankings(self, track: str, category: str, scope: str, car_model: str = "") -> None:
        def work() -> None:
            try:
                query = urlencode({"track": track, "category": category, "scope": scope, "car_model": car_model})
                result = self._request(f"/v1/rankings?{query}", authenticated=True)
                self.rankings_ready.emit(result.get("items", []), "")
            except Exception as exc:
                self.rankings_ready.emit([], str(exc))

        threading.Thread(target=work, name="SectorFlowLapRanking", daemon=True).start()

    def fetch_all_rankings(self) -> None:
        def work() -> None:
            try:
                items: list[dict[str, Any]] = []
                offset = 0
                while True:
                    result = self._request(
                        f"/v1/rankings/all?limit=5000&offset={offset}",
                        authenticated=True,
                    )
                    items.extend(result.get("items", []))
                    next_offset = result.get("next_offset")
                    if next_offset is None:
                        break
                    offset = int(next_offset)
                self.all_rankings_ready.emit(items, "")
            except Exception as exc:
                self.all_rankings_ready.emit([], str(exc))

        threading.Thread(target=work, name="SectorFlowAllLapRankings", daemon=True).start()

    def fetch_telemetry(self, record_id: str) -> None:
        def work() -> None:
            try:
                result = self._request(
                    f"/v1/rankings/{record_id}/telemetry",
                    authenticated=True,
                )
                self.telemetry_ready.emit(result, "")
            except Exception as exc:
                self.telemetry_ready.emit({}, str(exc))

        threading.Thread(target=work, name="SectorFlowLapTrace", daemon=True).start()

    def upload_records(self, records: list[LapRecord], display_name: str) -> None:
        self.sync_session(records, display_name)

    def sync_session(self, records: list[LapRecord], driver_name: str) -> None:
        # A sync may outlive a logout/account switch. Keep its original token
        # so one Discord account's queue can never be sent as another user.
        auth_token = self._access_token
        if not auth_token:
            return
        fresh = [record for record in records if record.record_id not in self._uploading_ids]
        for record in fresh:
            self._uploading_ids.add(record.record_id)

        def work() -> None:
            results: list[tuple[str, bool, str]] = []
            profile_error = ""
            if driver_name.strip():
                try:
                    self._request(
                        "/v1/me/profile", method="PUT",
                        payload={"driver_name": driver_name.strip()[:48]},
                        authenticated=True, auth_token=auth_token,
                    )
                    self.profile_sync_finished.emit(driver_name.strip()[:48], "")
                except Exception as exc:
                    profile_error = str(exc)
                    self.profile_sync_finished.emit("", profile_error)
            for record in fresh:
                try:
                    result = self._request(
                        "/v1/laps/best", method="POST",
                        payload=record.public_payload(driver_name or record.driver_name), authenticated=True,
                        auth_token=auth_token,
                    )
                    results.append((record.record_id, True, str(result.get("status", "ok"))))
                except Exception as exc:
                    results.append((record.record_id, False, str(exc)))
                finally:
                    self._uploading_ids.discard(record.record_id)
            errors = "; ".join(message for _record_id, ok, message in results if not ok)
            errors = "; ".join(value for value in (profile_error, errors) if value)
            self.upload_finished.emit(results, errors)

        threading.Thread(target=work, name="SectorFlowLapSync", daemon=True).start()

    def delete_cloud_profile(self) -> None:
        def work() -> None:
            try:
                self._request("/v1/me", method="DELETE", authenticated=True)
                self.cloud_data_deleted.emit(self.account_key)
                self.logout()
            except Exception as exc:
                self.request_failed.emit(str(exc))

        threading.Thread(target=work, name="SectorFlowDeleteCloudProfile", daemon=True).start()
