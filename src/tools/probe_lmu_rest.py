from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DESTINATION = PROJECT_ROOT / "data" / "online_profiles" / "lmu_rest_probe.json"
BASE = "http://127.0.0.1:6397"
ENDPOINTS = (
    "/rest/profile/",
    "/rest/profile/profileInfo/getProfileInfo",
    "/rest/watch/standings",
    "/rest/watch/sessionInfo",
    "/rest/sessions",
    "/rest/multiplayer/teams",
)
SENSITIVE = {
    "token",
    "ticket",
    "authsessionticket",
    "auth_session_ticket",
    "password",
    "authorization",
}


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if str(key).casefold() in SENSITIVE:
                result[key] = "<redacted>"
            else:
                result[key] = redact(item)
        return result
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def main() -> None:
    results: dict[str, Any] = {}
    for endpoint in ENDPOINTS:
        try:
            request = urllib.request.Request(
                BASE + endpoint,
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=3.0) as response:
                text = response.read().decode("utf-8", errors="replace")
            try:
                results[endpoint] = redact(json.loads(text))
            except json.JSONDecodeError:
                results[endpoint] = text[:20000]
            print("OK:", endpoint)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            results[endpoint] = {"error": str(exc)}
            print("ERRO:", endpoint, exc)

    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    DESTINATION.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("Arquivo sanitizado salvo em:")
    print(DESTINATION)


if __name__ == "__main__":
    main()
