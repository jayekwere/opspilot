"""Private SQLite records with transactional workflow transitions."""

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SECRET = re.compile(
    r'(?i)(authorization\s*:\s*(?:bearer\s+)?|(?:token|password|secret|api[_-]?key)\s*[=:]\s*)[^\s,;"}]+'
)


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(k): "[REDACTED]"
            if re.search(r"(?i)token|password|secret|credential|authorization", str(k))
            else sanitize(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [sanitize(v) for v in value[:200]]
    if isinstance(value, str):
        return SECRET.sub(r"\1[REDACTED]", value[:32768])
    return value


class Store:
    def __init__(self, directory: Path) -> None:
        if directory.is_symlink():
            raise ValueError("state directory cannot be a symlink")
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)
        database = directory / "opspilot.db"
        if database.is_symlink():
            raise ValueError("database cannot be a symlink")
        descriptor = os.open(database, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.close(descriptor)
        database.chmod(0o600)
        self.lock = threading.RLock()
        self.connection = sqlite3.connect(database, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
          PRAGMA journal_mode=DELETE;
          PRAGMA foreign_keys=ON;
          CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, actor TEXT NOT NULL,
            key TEXT NOT NULL, request TEXT NOT NULL, data TEXT NOT NULL, UNIQUE(actor,key));
          CREATE TABLE IF NOT EXISTS approvals(id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
            requester TEXT NOT NULL, approver TEXT, state TEXT NOT NULL, expires REAL NOT NULL,
            generation INTEGER NOT NULL, reason TEXT);
          CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY, at REAL NOT NULL,
            actor TEXT NOT NULL, event TEXT NOT NULL, subject TEXT NOT NULL, previous TEXT NOT NULL, digest TEXT NOT NULL);
        """)

        # A restarted process owns a new lab. Old approvals must never affect it.
        with self.transaction() as db:
            db.execute(
                "UPDATE approvals SET state='interrupted' WHERE state IN ('pending','approved','executing')"
            )
            for row in db.execute("SELECT id,data FROM runs").fetchall():
                record = json.loads(row["data"])
                if record["status"] == "running":
                    record["status"] = "failed"
                    record["intervention_required"] = True
                    record["evidence"] = {"error_type": "ProcessInterrupted"}
                    db.execute("UPDATE runs SET data=? WHERE id=?", (json.dumps(record), row["id"]))
                    self.audit(db, "system", "interrupted_run_recovered", row["id"])

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.lock, self.connection:
            yield self.connection

    def audit(self, db: sqlite3.Connection, actor: str, event: str, subject: str) -> None:
        if db.execute("SELECT COUNT(*) FROM audit").fetchone()[0] >= 10000:
            raise ValueError("audit capacity reached; archive state offline")
        row = db.execute("SELECT digest FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        previous = row["digest"] if row else "0" * 64
        at = time.time()
        payload = json.dumps([at, actor, event, subject, previous], separators=(",", ":"))
        digest = hashlib.sha256(payload.encode()).hexdigest()
        db.execute(
            "INSERT INTO audit(at,actor,event,subject,previous,digest) VALUES(?,?,?,?,?,?)",
            (at, actor, event, subject, previous, digest),
        )

    def runs(self) -> list[dict[str, Any]]:
        with self.lock:
            return [
                json.loads(row["data"])
                for row in self.connection.execute("SELECT data FROM runs ORDER BY rowid DESC LIMIT 200")
            ]

    def run(self, identifier: str) -> dict[str, Any]:
        with self.lock:
            row = self.connection.execute("SELECT data FROM runs WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise KeyError(identifier)
        return dict(json.loads(row["data"]))

    def approvals(self) -> list[dict[str, Any]]:
        with self.lock:
            return [
                dict(row)
                for row in self.connection.execute("SELECT * FROM approvals ORDER BY rowid DESC LIMIT 200")
            ]

    def events(self) -> list[dict[str, Any]]:
        with self.lock:
            return [
                dict(row)
                for row in self.connection.execute("SELECT * FROM audit ORDER BY seq DESC LIMIT 200")
            ]

    def close(self) -> None:
        self.connection.close()
