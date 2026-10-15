"""Historique des exécutions, planifications et suggestions (SQLite)."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    target_type TEXT NOT NULL,          -- automation | recipe
    target_id TEXT NOT NULL,
    target_name TEXT NOT NULL,
    user TEXT NOT NULL,
    trigger TEXT NOT NULL DEFAULT 'manual', -- manual | schedule
    params TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL,               -- queued | running | success | error | cancelled
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    duration_ms INTEGER,
    summary TEXT,
    error TEXT,
    error_hint TEXT,
    outputs TEXT NOT NULL DEFAULT '[]',
    minutes_saved INTEGER NOT NULL DEFAULT 0,
    data_mode TEXT,
    demo INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_runs_created ON runs(created_at DESC);
CREATE INDEX IF NOT EXISTS ix_runs_target ON runs(target_id);

CREATE TABLE IF NOT EXISTS run_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    type TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_events_run ON run_events(run_id, id);

CREATE TABLE IF NOT EXISTS schedules (
    id TEXT PRIMARY KEY,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    label TEXT NOT NULL,
    params TEXT NOT NULL DEFAULT '{}',
    frequency TEXT NOT NULL,            -- daily | weekly | monthly
    hour INTEGER NOT NULL DEFAULT 8,
    minute INTEGER NOT NULL DEFAULT 0,
    weekday INTEGER,                    -- 0 = lundi
    day_of_month INTEGER,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS suggestions (
    id TEXT PRIMARY KEY,
    user TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    urgency TEXT NOT NULL DEFAULT 'normal',
    created_at TEXT NOT NULL
);
"""

JSON_FIELDS = {"params", "outputs", "payload"}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Database:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        data = dict(row)
        for key in JSON_FIELDS & data.keys():
            data[key] = json.loads(data[key]) if data[key] else None
        for key in ("enabled", "demo"):
            if key in data:
                data[key] = bool(data[key])
        return data

    def execute(self, sql: str, args: tuple | dict = ()) -> None:
        with self._lock, self.connect() as conn:
            conn.execute(sql, args)

    def one(self, sql: str, args: tuple | dict = ()) -> dict[str, Any] | None:
        with self.connect() as conn:
            return self._row(conn.execute(sql, args).fetchone())

    def all(self, sql: str, args: tuple | dict = ()) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [self._row(r) for r in conn.execute(sql, args).fetchall()]

    def scalar(self, sql: str, args: tuple | dict = ()) -> Any:
        with self.connect() as conn:
            row = conn.execute(sql, args).fetchone()
            return row[0] if row else None

    # ------------------------------------------------------------------ runs
    def create_run(self, **fields: Any) -> dict[str, Any]:
        fields.setdefault("id", new_id("run"))
        fields.setdefault("created_at", now_iso())
        fields.setdefault("status", "queued")
        fields["params"] = json.dumps(fields.get("params") or {}, ensure_ascii=False, default=str)
        fields["outputs"] = json.dumps(fields.get("outputs") or [], ensure_ascii=False)
        columns = ", ".join(fields)
        placeholders = ", ".join(f":{k}" for k in fields)
        self.execute(f"INSERT INTO runs ({columns}) VALUES ({placeholders})", fields)
        return self.get_run(fields["id"])  # type: ignore[return-value]

    def update_run(self, run_id: str, **fields: Any) -> None:
        if "outputs" in fields:
            fields["outputs"] = json.dumps(fields["outputs"], ensure_ascii=False)
        assignments = ", ".join(f"{k} = :{k}" for k in fields)
        self.execute(f"UPDATE runs SET {assignments} WHERE id = :_id", {**fields, "_id": run_id})

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return self.one("SELECT * FROM runs WHERE id = ?", (run_id,))

    def list_runs(self, limit: int = 50, target_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        clauses, args = [], []
        if target_id:
            clauses.append("target_id = ?")
            args.append(target_id)
        if status:
            clauses.append("status = ?")
            args.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return self.all(f"SELECT * FROM runs {where} ORDER BY created_at DESC LIMIT ?", (*args, limit))

    def add_event(self, run_id: str, event: dict[str, Any]) -> None:
        self.execute(
            "INSERT INTO run_events (run_id, type, payload) VALUES (?, ?, ?)",
            (run_id, event.get("type", "log"), json.dumps(event, ensure_ascii=False, default=str)),
        )

    def events(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.all("SELECT payload FROM run_events WHERE run_id = ? ORDER BY id", (run_id,))
        return [r["payload"] for r in rows]
