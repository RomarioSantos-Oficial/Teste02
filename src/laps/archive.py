from __future__ import annotations

import gzip
import json
import math
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TRACE_POINTS = 240
_OWNER_CONTEXT_LOCK = threading.Lock()
_ACTIVE_OWNER_KEY = "offline"
_OWNER_CONTEXT_CHECKED_AT = 0.0
_OWNER_CONTEXT_MTIME_NS = -1


def archive_path() -> Path:
    base = Path(
        os.environ.get("LOCALAPPDATA")
        or os.environ.get("APPDATA")
        or (Path.home() / "AppData" / "Local")
    )
    return base / "SectorFlow" / "lap_archive.sqlite3"


def cloud_settings_path() -> Path:
    base = Path(
        os.environ.get("LOCALAPPDATA")
        or os.environ.get("APPDATA")
        or (Path.home() / "AppData" / "Local")
    )
    return base / "SectorFlow" / "lap_cloud.json"


def local_owner_key() -> str:
    """Return the active local profile, refreshing shared process state at most once per second."""
    global _ACTIVE_OWNER_KEY, _OWNER_CONTEXT_CHECKED_AT, _OWNER_CONTEXT_MTIME_NS
    now = time.monotonic()
    if now - _OWNER_CONTEXT_CHECKED_AT < 1.0:
        return _ACTIVE_OWNER_KEY
    with _OWNER_CONTEXT_LOCK:
        now = time.monotonic()
        if now - _OWNER_CONTEXT_CHECKED_AT < 1.0:
            return _ACTIVE_OWNER_KEY
        path = cloud_settings_path()
        try:
            mtime_ns = path.stat().st_mtime_ns
            if mtime_ns != _OWNER_CONTEXT_MTIME_NS:
                settings = json.loads(path.read_text(encoding="utf-8"))
                _ACTIVE_OWNER_KEY = _clean(settings.get("active_owner_key", "offline")) or "offline"
                _OWNER_CONTEXT_MTIME_NS = mtime_ns
        except (OSError, ValueError, TypeError):
            _ACTIVE_OWNER_KEY = "offline"
            _OWNER_CONTEXT_MTIME_NS = -1
        _OWNER_CONTEXT_CHECKED_AT = now
        return _ACTIVE_OWNER_KEY


def set_active_owner_key(owner_key: str) -> None:
    """Activate a local/Discord profile and publish it for isolated overlay processes."""
    global _ACTIVE_OWNER_KEY, _OWNER_CONTEXT_CHECKED_AT, _OWNER_CONTEXT_MTIME_NS
    normalized = _clean(owner_key) or "offline"
    path = cloud_settings_path()
    with _OWNER_CONTEXT_LOCK:
        try:
            settings = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(settings, dict):
                settings = {}
        except (OSError, ValueError, TypeError):
            settings = {}
        settings.pop("owner_key", None)
        settings["active_owner_key"] = normalized
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)
        _ACTIVE_OWNER_KEY = normalized
        _OWNER_CONTEXT_CHECKED_AT = time.monotonic()
        try:
            _OWNER_CONTEXT_MTIME_NS = path.stat().st_mtime_ns
        except OSError:
            _OWNER_CONTEXT_MTIME_NS = -1


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _key(value: str) -> str:
    return _clean(value).casefold()


def is_online_session(session: Any) -> bool:
    """Only persist laps when LMU exposes a real multiplayer server name.

    An empty/placeholder server name is treated as offline so a temporary
    missing REST field cannot turn a single-player lap into a shared record.
    """
    if session is None or not bool(getattr(session, "connected", False)):
        return False
    server_name = _clean(getattr(session, "server_name", "")).casefold()
    return bool(server_name and server_name not in {"-none-", "none", "offline", "single player"})


@dataclass(slots=True)
class LapRecord:
    record_id: str
    scope: str
    track: str
    category: str
    car_model: str
    car_filename: str
    car_number: str
    slot_id: int
    lap_seconds: float
    sector1: float
    sector2: float
    sector3: float
    trace: list[dict[str, float]]
    saved_at: float
    session_key: str = ""
    pending_upload: bool = False
    upload_after: float | None = None
    owner_key: str = "offline"
    driver_name: str = ""

    def public_payload(self, display_name: str) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "scope": self.scope,
            "track": self.track,
            "category": self.category,
            "car_model": self.car_model,
            "car_filename": self.car_filename,
            "car_number": self.car_number,
            "lap_seconds": self.lap_seconds,
            "sector1": self.sector1,
            "sector2": self.sector2,
            "sector3": self.sector3,
            "display_name": _clean(display_name or self.driver_name)[:48],
            "trace": self.trace,
        }


class LapArchiveStore:
    """Small local PB database; only the fastest lap per scope is retained."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else archive_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=8.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=8000")
        return connection

    @contextmanager
    def _connection(self):
        """Commit/rollback and close each SQLite handle after a store operation."""
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialise(self) -> None:
        connection = sqlite3.connect(self.path, timeout=8.0)
        try:
            try:
                connection.execute("PRAGMA journal_mode=WAL")
            except sqlite3.OperationalError:
                # Another process may initialize the same per-user archive at
                # launch; SQLite's busy timeout will serialize the DDL below.
                pass
        finally:
            connection.close()
        with self._connection() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS personal_bests (
                    record_id TEXT PRIMARY KEY,
                    scope TEXT NOT NULL,
                    track TEXT NOT NULL,
                    track_key TEXT NOT NULL,
                    category TEXT NOT NULL,
                    category_key TEXT NOT NULL,
                    car_model TEXT NOT NULL,
                    car_filename TEXT NOT NULL,
                    car_key TEXT NOT NULL,
                    car_number TEXT NOT NULL,
                    slot_id INTEGER NOT NULL,
                    lap_seconds REAL NOT NULL,
                    sector1 REAL NOT NULL,
                    sector2 REAL NOT NULL,
                    sector3 REAL NOT NULL,
                    trace_gzip BLOB NOT NULL,
                    saved_at REAL NOT NULL,
                    session_key TEXT NOT NULL,
                    owner_key TEXT NOT NULL DEFAULT 'offline',
                    driver_name TEXT NOT NULL DEFAULT '',
                    pending_upload INTEGER NOT NULL DEFAULT 0,
                    upload_after REAL
                )"""
            )
            db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS pb_scope_key ON personal_bests "
                "(owner_key, scope, track_key, category_key, car_key)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS archive_migrations (migration_key TEXT PRIMARY KEY)"
            )

    def save_if_better(self, record: LapRecord) -> list[LapRecord]:
        """Store category and exact-model PBs from one validated lap."""
        scopes = ["category"]
        if record.car_model or record.car_filename:
            scopes.append("model")
        saved: list[LapRecord] = []
        for scope in scopes:
            candidate = LapRecord(
                record_id=str(uuid.uuid4()),
                scope=scope,
                track=record.track,
                category=record.category,
                car_model=record.car_model,
                car_filename=record.car_filename,
                car_number=record.car_number,
                slot_id=record.slot_id,
                lap_seconds=record.lap_seconds,
                sector1=record.sector1,
                sector2=record.sector2,
                sector3=record.sector3,
                trace=record.trace,
                saved_at=time.time(),
                session_key=record.session_key,
                pending_upload=False,
                owner_key=record.owner_key,
                driver_name=record.driver_name,
            )
            if self._save_scope_if_better(candidate):
                saved.append(candidate)
        return saved

    def _save_scope_if_better(self, record: LapRecord) -> bool:
        track_key, category_key = _key(record.track), _key(record.category)
        car_key = _key(record.car_filename or record.car_model) if record.scope == "model" else ""
        compressed = gzip.compress(
            json.dumps(record.trace, separators=(",", ":")).encode("utf-8"),
            compresslevel=6,
        )
        with self._connection() as db:
            current = db.execute(
                "SELECT lap_seconds FROM personal_bests WHERE owner_key=? AND scope=? AND track_key=? "
                "AND category_key=? AND car_key=?",
                (record.owner_key, record.scope, track_key, category_key, car_key),
            ).fetchone()
            if current is not None and float(current["lap_seconds"]) <= record.lap_seconds:
                return False
            db.execute(
                """INSERT INTO personal_bests (
                    record_id, scope, track, track_key, category, category_key,
                    car_model, car_filename, car_key, car_number, slot_id,
                    lap_seconds, sector1, sector2, sector3, trace_gzip,
                    saved_at, session_key, owner_key, driver_name, pending_upload, upload_after
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL)
                ON CONFLICT(owner_key, scope, track_key, category_key, car_key) DO UPDATE SET
                    record_id=excluded.record_id, track=excluded.track,
                    category=excluded.category, car_model=excluded.car_model,
                    car_filename=excluded.car_filename, car_number=excluded.car_number,
                    slot_id=excluded.slot_id, lap_seconds=excluded.lap_seconds,
                    sector1=excluded.sector1, sector2=excluded.sector2,
                    sector3=excluded.sector3, trace_gzip=excluded.trace_gzip,
                    saved_at=excluded.saved_at, session_key=excluded.session_key,
                    driver_name=excluded.driver_name,
                    pending_upload=0, upload_after=NULL""",
                (
                    record.record_id, record.scope, record.track, track_key,
                    record.category, category_key, record.car_model,
                    record.car_filename, car_key, record.car_number,
                    record.slot_id, record.lap_seconds, record.sector1,
                    record.sector2, record.sector3, compressed, record.saved_at,
                    record.session_key, record.owner_key, record.driver_name,
                ),
            )
        return True

    def _from_row(self, row: sqlite3.Row) -> LapRecord:
        trace = json.loads(gzip.decompress(row["trace_gzip"]).decode("utf-8"))
        return LapRecord(
            record_id=str(row["record_id"]), scope=str(row["scope"]),
            track=str(row["track"]), category=str(row["category"]),
            car_model=str(row["car_model"]), car_filename=str(row["car_filename"]),
            car_number=str(row["car_number"]), slot_id=int(row["slot_id"]),
            lap_seconds=float(row["lap_seconds"]), sector1=float(row["sector1"]),
            sector2=float(row["sector2"]), sector3=float(row["sector3"]),
            trace=trace, saved_at=float(row["saved_at"]),
            session_key=str(row["session_key"]),
            pending_upload=bool(row["pending_upload"]),
            upload_after=float(row["upload_after"]) if row["upload_after"] is not None else None,
            owner_key=str(row["owner_key"]), driver_name=str(row["driver_name"]),
        )

    def best(self, track: str, category: str, car_model: str = "", car_filename: str = "", scope: str = "category", owner_key: str | None = None) -> LapRecord | None:
        car_key = _key(car_filename or car_model) if scope == "model" else ""
        with self._connection() as db:
            row = db.execute(
                "SELECT * FROM personal_bests WHERE owner_key=? AND scope=? AND track_key=? AND category_key=? AND car_key=?",
                (owner_key or local_owner_key(), scope, _key(track), _key(category), car_key),
            ).fetchone()
        return self._from_row(row) if row else None

    def all_personal_bests(self, owner_key: str | None = None) -> list[LapRecord]:
        with self._connection() as db:
            rows = db.execute(
                "SELECT * FROM personal_bests WHERE owner_key=? ORDER BY track, category, scope, lap_seconds",
                (owner_key or local_owner_key(),),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def copy_profiles_to_local(self) -> int:
        """Copy existing profile records into the local-only profile without deleting originals."""
        with self._connection() as db:
            migrated = db.execute(
                "SELECT 1 FROM archive_migrations WHERE migration_key='local_only_profile_v1'"
            ).fetchone()
            if migrated:
                return 0
            rows = db.execute(
                "SELECT * FROM personal_bests WHERE owner_key!='offline' ORDER BY lap_seconds"
            ).fetchall()
        copied = 0
        for source in (self._from_row(row) for row in rows):
            local = LapRecord(
                record_id=str(uuid.uuid4()), scope=source.scope,
                track=source.track, category=source.category,
                car_model=source.car_model, car_filename=source.car_filename,
                car_number=source.car_number, slot_id=source.slot_id,
                lap_seconds=source.lap_seconds, sector1=source.sector1,
                sector2=source.sector2, sector3=source.sector3,
                trace=source.trace, saved_at=source.saved_at,
                session_key=source.session_key, pending_upload=False,
                owner_key="offline", driver_name=source.driver_name,
            )
            copied += int(self._save_scope_if_better(local))
        with self._connection() as db:
            db.execute("UPDATE personal_bests SET pending_upload=0, upload_after=NULL")
            db.execute(
                "INSERT OR IGNORE INTO archive_migrations (migration_key) VALUES ('local_only_profile_v1')"
            )
        return copied

    def import_offline_records(self, owner_key: str) -> int:
        """Copy offline PBs into a chosen Discord profile after explicit consent."""
        target_owner = _clean(owner_key)
        if not target_owner or target_owner == "offline":
            return 0
        with self._connection() as db:
            rows = db.execute(
                "SELECT * FROM personal_bests WHERE owner_key='offline' ORDER BY saved_at"
            ).fetchall()
        imported = 0
        session_keys: set[str] = set()
        for row in rows:
            source = self._from_row(row)
            candidate = LapRecord(
                record_id=str(uuid.uuid4()), scope=source.scope,
                track=source.track, category=source.category,
                car_model=source.car_model, car_filename=source.car_filename,
                car_number=source.car_number, slot_id=source.slot_id,
                lap_seconds=source.lap_seconds, sector1=source.sector1,
                sector2=source.sector2, sector3=source.sector3,
                trace=source.trace, saved_at=time.time(),
                session_key=f"import|{uuid.uuid4().hex}",
                pending_upload=True, owner_key=target_owner,
                driver_name=source.driver_name,
            )
            if self._save_scope_if_better(candidate):
                imported += 1
                session_keys.add(candidate.session_key)
        due_at = time.time() + 60.0
        for session_key in session_keys:
            self.mark_session_finished(session_key, due_at)
        return imported

    def mark_session_finished(self, session_key: str, due_at: float) -> None:
        if not session_key:
            return
        with self._connection() as db:
            db.execute(
                "UPDATE personal_bests SET upload_after=? WHERE pending_upload=1 AND session_key=?",
                (float(due_at), session_key),
            )

    def pending_uploads(self, now: float | None = None, limit: int = 20) -> list[LapRecord]:
        checked_at = time.time() if now is None else float(now)
        with self._connection() as db:
            rows = db.execute(
                "SELECT * FROM personal_bests WHERE pending_upload=1 AND upload_after IS NOT NULL "
                "AND upload_after<=? AND owner_key=? ORDER BY saved_at LIMIT ?",
                (checked_at, local_owner_key(), max(1, min(100, int(limit)))),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def mark_uploaded(self, record_id: str) -> None:
        with self._connection() as db:
            db.execute(
                "UPDATE personal_bests SET pending_upload=0, upload_after=NULL WHERE record_id=?",
                (str(record_id),),
            )

    def discard_pending(self, owner_key: str) -> None:
        with self._connection() as db:
            db.execute(
                "UPDATE personal_bests SET pending_upload=0, upload_after=NULL WHERE owner_key=?",
                (str(owner_key),),
            )

    def retry_later(self, record_id: str, delay_s: float = 60.0) -> None:
        with self._connection() as db:
            db.execute(
                "UPDATE personal_bests SET upload_after=? WHERE record_id=? AND pending_upload=1",
                (time.time() + max(30.0, delay_s), str(record_id)),
            )


class LapRecorder:
    """Builds a full-lap pedal trace and stores only validated PBs."""

    def __init__(self, store: LapArchiveStore) -> None:
        self.store = store
        self._session_key = ""
        self._session_identity_key = ""
        self._track = ""
        self._session = 0
        self._driver_slot = -1
        self._lap_marker: int | None = None
        self._samples: list[tuple[float, float, float, float, float]] = []
        self._last_sample_at = 0.0
        self._active = False
        self._last_finished_key = ""
        self._last_trace_time = 0.0
        self._driver_name = ""
        self._owner_key = local_owner_key()

    def set_owner_key(self, owner_key: str) -> None:
        normalized = _clean(owner_key) or "offline"
        if normalized == self._owner_key:
            return
        # Never assign samples captured under a previous local/Discord profile
        # to the account that becomes active halfway through a lap.
        self.finish_session()
        self._owner_key = normalized
        self._lap_marker = None
        self._samples.clear()

    @staticmethod
    def _player_driver(session: Any) -> Any | None:
        return next(
            (driver for driver in (getattr(session, "drivers", []) or []) if bool(getattr(driver, "is_player", False))),
            None,
        )

    @staticmethod
    def _session_identity(session: Any) -> str:
        track = _clean(getattr(session, "track_name", ""))
        number = int(getattr(session, "session", 0) or 0)
        start = float(getattr(session, "start_event_time_s", 0.0) or 0.0)
        return f"{_key(track)}|{number}|{start:.3f}"

    def observe(self, session: Any) -> list[LapRecord]:
        saved: list[LapRecord] = []
        # The archive is local-only: a live LMU session is sufficient; it does
        # not need a multiplayer server name or an online account.
        driver = self._player_driver(session) if bool(getattr(session, "connected", False)) else None
        player = getattr(session, "player", None)
        valid_stream = bool(
            driver is not None and player is not None
            and not bool(getattr(session, "telemetry_paused", False))
            and not bool(getattr(session, "is_replay_active", False))
            and bool(getattr(session, "player_has_vehicle", True))
            and bool(getattr(session, "in_realtime", True))
            and not bool(getattr(session, "race_finished", False))
        )
        incoming_key = self._session_identity(session) if valid_stream else ""
        if self._session_key and incoming_key and incoming_key != self._session_identity_key:
            self.finish_session()
        elif self._session_key and not incoming_key:
            self.finish_session()

        if not valid_stream or driver is None or player is None:
            return saved

        if not self._session_key:
            self._session_key = f"{incoming_key}|{uuid.uuid4().hex}"
            self._session_identity_key = incoming_key
            self._track = _clean(getattr(session, "track_name", ""))
            self._session = int(getattr(session, "session", 0) or 0)
            self._driver_slot = int(getattr(driver, "slot_id", -1))
        self._driver_name = _clean(getattr(driver, "driver_name", ""))
        if self._driver_slot != int(getattr(driver, "slot_id", -1)):
            self._samples.clear()
        self._driver_slot = int(getattr(driver, "slot_id", -1))

        lap_marker = int(getattr(driver, "laps", getattr(player, "lap", 0)) or 0)
        if self._lap_marker is None:
            self._lap_marker = lap_marker
        elif lap_marker > self._lap_marker:
            if lap_marker == self._lap_marker + 1:
                record = self._complete_lap(session, driver)
                if record is not None:
                    saved.extend(self.store.save_if_better(record))
            self._samples.clear()
            self._lap_marker = lap_marker
        elif lap_marker < self._lap_marker:
            self._samples.clear()
            self._lap_marker = lap_marker

        now = time.monotonic()
        if now - self._last_sample_at >= 0.035:
            self._last_sample_at = now
            if bool(getattr(player, "current_lap_invalidated", False)):
                self._samples.clear()
            else:
                length = float(getattr(session, "track_length_m", 0.0) or 0.0)
                distance = float(getattr(driver, "lap_distance_m", 0.0) or 0.0)
                elapsed = float(getattr(driver, "time_into_lap_s", 0.0) or 0.0)
                if elapsed <= 0.0:
                    event = float(getattr(session, "current_event_time_s", 0.0) or getattr(session, "current_time_s", 0.0) or 0.0)
                    start = float(getattr(driver, "lap_start_event_time_s", 0.0) or 0.0)
                    elapsed = event - start if event > start > 0.0 else 0.0
                if length > 0.0 and -1.0 <= distance <= length * 1.05 and elapsed >= 0.0:
                    self._samples.append((
                        max(0.0, min(1.0, distance / length)), elapsed,
                        max(0.0, min(1.0, float(getattr(player, "throttle", 0.0) or 0.0))),
                        max(0.0, min(1.0, float(getattr(player, "brake", 0.0) or 0.0))),
                        max(0.0, float(getattr(player, "speed_kmh", 0.0) or 0.0)),
                    ))

        if bool(getattr(session, "race_finished", False)):
            self.finish_session()
        return saved

    def _complete_lap(self, session: Any, driver: Any) -> LapRecord | None:
        lap_seconds = float(getattr(driver, "last_lap_s", 0.0) or 0.0)
        if bool(getattr(driver, "last_lap_invalidated", False)) or not (1.0 < lap_seconds < 3600.0):
            self._samples.clear()
            return None
        length = float(getattr(session, "track_length_m", 0.0) or 0.0)
        trace = self._resample(self._samples, length, lap_seconds=lap_seconds)
        self._samples.clear()
        if trace is None:
            return None
        sector1 = float(getattr(driver, "last_sector1_s", 0.0) or 0.0)
        sector2 = float(getattr(driver, "last_sector2_s", 0.0) or 0.0)
        sector3 = float(getattr(driver, "last_sector3_s", 0.0) or 0.0)
        if min(sector1, sector2, sector3) < 0.0 or sum((sector1, sector2, sector3)) <= 0.0:
            return None
        return LapRecord(
            record_id=str(uuid.uuid4()), scope="category",
            track=self._track, category=_clean(getattr(driver, "vehicle_class", "")),
            car_model=_clean(getattr(driver, "vehicle_model", "")),
            car_filename=_clean(getattr(driver, "vehicle_filename", "")),
            car_number=_clean(getattr(driver, "car_number", "")),
            slot_id=int(getattr(driver, "slot_id", -1)),
            lap_seconds=lap_seconds, sector1=sector1, sector2=sector2, sector3=sector3,
            trace=trace, saved_at=time.time(), session_key=self._session_key,
            owner_key=self._owner_key,
            driver_name=_clean(getattr(driver, "driver_name", "")),
        )

    @staticmethod
    def _resample(
        samples: list[tuple[float, float, float, float, float]],
        track_length: float,
        lap_seconds: float | None = None,
    ) -> list[dict[str, float]] | None:
        if track_length <= 0.0 or len(samples) < 30:
            return None
        ordered = sorted(samples, key=lambda sample: sample[0])
        unique: list[tuple[float, float, float, float, float]] = []
        for sample in ordered:
            if unique and sample[0] - unique[-1][0] < 0.0005:
                unique[-1] = sample
            else:
                unique.append(sample)
        if len(unique) < 30 or unique[0][0] > 0.035 or unique[-1][0] < 0.965:
            return None
        if max(b[0] - a[0] for a, b in zip(unique, unique[1:])) > 0.12:
            return None
        output: list[dict[str, float]] = []
        cursor = 0
        for index in range(TRACE_POINTS):
            x = index / (TRACE_POINTS - 1)
            while cursor + 1 < len(unique) and unique[cursor + 1][0] < x:
                cursor += 1
            left = unique[cursor]
            right = unique[min(cursor + 1, len(unique) - 1)]
            span = right[0] - left[0]
            ratio = 0.0 if span <= 1e-9 else max(0.0, min(1.0, (x - left[0]) / span))
            values = [left[column] + (right[column] - left[column]) * ratio for column in range(1, 5)]
            elapsed_at_point = max(0.0, values[0])
            if (
                index == TRACE_POINTS - 1
                and lap_seconds is not None
                and math.isfinite(float(lap_seconds))
                and float(lap_seconds) > 0.0
            ):
                # O ultimo ponto usa o tempo oficial da volta mesmo se o
                # ultimo quadro de telemetria chegou pouco antes da linha.
                elapsed_at_point = float(lap_seconds)
            output.append({
                "distance": x, "elapsed_s": elapsed_at_point,
                "throttle": max(0.0, min(1.0, values[1])),
                "brake": max(0.0, min(1.0, values[2])),
                "speed_kmh": max(0.0, values[3]),
            })
        return output

    def finish_session(self) -> None:
        if self._session_key and self._session_key != self._last_finished_key:
            self._last_finished_key = self._session_key
        self._session_key = ""
        self._session_identity_key = ""
        self._lap_marker = None
        self._samples.clear()
        self._active = False
