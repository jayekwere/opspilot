"""Authorization, idempotency, audit, independent approval, and toil accounting."""

import asyncio
import json
import logging
import re
import time
import uuid
from typing import Any

from opspilot.lab import Lab
from opspilot.models import Approval, Principal, Request
from opspilot.runbooks import collect
from opspilot.store import Store, sanitize

logger = logging.getLogger("opspilot")


class Conflict(ValueError):
    pass


def require(principal: Principal, role: str) -> None:
    if role not in principal.roles:
        raise PermissionError(f"{role} permission required")


class Service:
    def __init__(self, store: Store, lab: Lab) -> None:
        self.store, self.lab = store, lab
        self.gate = asyncio.Lock()

    async def diagnose(self, principal: Principal, request: Request, key: str) -> dict[str, Any]:
        require(principal, "diagnose")
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", key):
            raise ValueError("idempotency key must contain 8 to 80 safe characters")
        if (request.manual_seconds is None) != (request.baseline_source is None):
            raise ValueError("manual time requires a baseline source and vice versa")
        serialized = request.model_dump_json()
        # Serial execution bounds resource usage and prevents overlapping writes.
        async with self.gate:
            with self.store.transaction() as db:
                previous = db.execute(
                    "SELECT request,data FROM runs WHERE actor=? AND key=?", (principal.name, key)
                ).fetchone()
                if previous:
                    if previous["request"] != serialized:
                        raise Conflict("idempotency key reused for different input")
                    return dict(json.loads(previous["data"]))
                if db.execute("SELECT COUNT(*) FROM runs").fetchone()[0] >= 1000:
                    raise Conflict("run capacity reached; archive state offline")
                identifier = str(uuid.uuid4())
                record: dict[str, Any] = {
                    "id": identifier,
                    "actor": principal.name,
                    "request": request.model_dump(),
                    "status": "running",
                    "started_at": time.time(),
                    "seconds": 0.0,
                    "intervention_required": False,
                    "findings": [],
                    "evidence": {},
                }
                db.execute(
                    "INSERT INTO runs VALUES(?,?,?,?,?)",
                    (identifier, principal.name, key, serialized, json.dumps(record)),
                )
                self.store.audit(db, principal.name, "diagnosis_started", identifier)
            started = time.perf_counter()
            try:
                async with asyncio.timeout(12):
                    result = await collect(request, self.lab)
                record.update(result.model_dump())
            except Exception as error:
                # Persist operational failure instead of leaving a completed request running.
                record.update(status="failed", evidence={"error_type": type(error).__name__})
            record["seconds"] = time.perf_counter() - started
            record["evidence"] = sanitize(record["evidence"])
            record["intervention_required"] = record["status"] != "healthy"
            record["manual_effort_avoided_seconds"] = (
                max(0, request.manual_seconds - record["seconds"])
                if request.manual_seconds is not None and record["status"] in ("healthy", "finding")
                else None
            )
            with self.store.transaction() as db:
                db.execute("UPDATE runs SET data=? WHERE id=?", (json.dumps(record), identifier))
                self.store.audit(db, principal.name, "diagnosis_" + record["status"], identifier)
            logger.info(
                json.dumps(
                    {
                        "event": "diagnosis_completed",
                        "run_id": identifier,
                        "status": record["status"],
                        "seconds": record["seconds"],
                    }
                )
            )
            return record

    def request_approval(self, principal: Principal, run_id: str) -> dict[str, Any]:
        require(principal, "diagnose")
        run = self.store.run(run_id)
        if run["actor"] != principal.name:
            raise PermissionError("only the diagnosing operator may request remediation")
        if (
            run["request"]["target"] != "lab"
            or run["request"]["runbook"] not in ("service", "security")
            or run["status"] != "finding"
        ):
            raise Conflict("only supported disposable lab findings allow remediation")
        with self.store.transaction() as db:
            previous = db.execute("SELECT * FROM approvals WHERE run_id=?", (run_id,)).fetchone()
            if previous:
                return dict(previous)
            identifier = str(uuid.uuid4())
            db.execute(
                "INSERT INTO approvals VALUES(?,?,?,NULL,?,?,?,NULL)",
                (
                    identifier,
                    run_id,
                    principal.name,
                    "pending",
                    time.time() + 600,
                    run["evidence"]["generation"],
                ),
            )
            self.store.audit(db, principal.name, "approval_requested", identifier)
            return dict(db.execute("SELECT * FROM approvals WHERE id=?", (identifier,)).fetchone())

    def decide(self, principal: Principal, identifier: str, decision: Approval) -> dict[str, Any]:
        require(principal, "approve")
        with self.store.transaction() as db:
            row = db.execute("SELECT * FROM approvals WHERE id=?", (identifier,)).fetchone()
            if row is None:
                raise KeyError(identifier)
            if row["requester"] == principal.name:
                raise PermissionError("independent approver required")
            if row["state"] != "pending" or row["expires"] < time.time():
                raise Conflict("approval is no longer pending or has expired")
            state = "approved" if decision.decision == "approve" else "rejected"
            db.execute(
                "UPDATE approvals SET state=?,approver=?,reason=? WHERE id=?",
                (state, principal.name, sanitize(decision.reason), identifier),
            )
            self.store.audit(db, principal.name, "approval_" + state, identifier)
            return dict(db.execute("SELECT * FROM approvals WHERE id=?", (identifier,)).fetchone())

    async def execute(self, principal: Principal, identifier: str) -> dict[str, Any]:
        require(principal, "execute")
        async with self.gate:
            with self.store.transaction() as db:
                row = db.execute("SELECT * FROM approvals WHERE id=?", (identifier,)).fetchone()
                if row is None:
                    raise KeyError(identifier)
                if principal.name == row["approver"]:
                    raise PermissionError("approver cannot execute the same remediation")
                if row["state"] == "succeeded":
                    return self.store.run(row["run_id"])
                if row["state"] != "approved" or row["expires"] < time.time():
                    raise Conflict("a current independent approval is required")
                db.execute("UPDATE approvals SET state=? WHERE id=?", ("executing", identifier))
                self.store.audit(db, principal.name, "remediation_started", identifier)
            started = time.perf_counter()
            outcome = "failed"
            failure_reason = "verification_failed"
            try:
                book = self.store.run(row["run_id"])["request"]["runbook"]
                self.lab.repair(row["generation"], book)
                verified = await collect(Request(runbook=book, target="lab"), self.lab)
                if verified.status == "healthy":
                    outcome = "succeeded"
            except ValueError:
                failure_reason = "stale_lab_generation"
            except OSError:
                failure_reason = "lab_action_failed"
            record = self.store.run(row["run_id"])
            record["remediation"] = {
                "outcome": outcome,
                "seconds": time.perf_counter() - started,
                "verified": outcome == "succeeded",
                "failure_reason": failure_reason if outcome == "failed" else None,
                "action": "recover_disposable_" + self.store.run(row["run_id"])["request"]["runbook"],
            }
            with self.store.transaction() as db:
                db.execute("UPDATE approvals SET state=? WHERE id=?", (outcome, identifier))
                db.execute("UPDATE runs SET data=? WHERE id=?", (json.dumps(record), row["run_id"]))
                self.store.audit(db, principal.name, "remediation_" + outcome, identifier)
            return record

    def metrics(self) -> dict[str, Any]:
        runs = self.store.runs()
        complete = [r for r in runs if r["status"] != "running"]
        successes = sum(r["status"] in ("healthy", "finding") for r in complete)
        measured = [r for r in complete if r.get("manual_effort_avoided_seconds") is not None]
        groups: dict[str, list[str]] = {}
        for run in complete:
            key = json.dumps(run["request"], sort_keys=True)
            groups.setdefault(key, []).append(run["status"])
        repeats = [v for v in groups.values() if len(v) > 1]
        return {
            "total_runs": len(runs),
            "completed_runs": len(complete),
            "success_rate": successes / len(complete) if complete else None,
            "failure_rate": (len(complete) - successes) / len(complete) if complete else None,
            "intervention_runs": sum(r["intervention_required"] for r in complete),
            "automated_seconds": sum(r["seconds"] for r in complete),
            "manual_seconds": sum(r["request"]["manual_seconds"] for r in measured),
            "estimated_effort_avoided_seconds": sum(r["manual_effort_avoided_seconds"] for r in measured),
            "baseline_runs": len(measured),
            "baseline_automated_seconds": sum(r["seconds"] for r in measured),
            "repeat_groups": len(repeats),
            "repeatability": sum(len(set(v)) == 1 for v in repeats) / len(repeats) if repeats else None,
            "scope": "latest 200 runs; baseline values supplied by operator; repeatability means identical outcome status",
        }
