"""Exercise the packaged API under the same restrictions as the lab deployment."""

import json
import os
import secrets
import subprocess
import time
from pathlib import Path

import httpx


def docker(*args: str, env: dict[str, str] | None = None) -> str:
    return subprocess.run(
        ["docker", *args], check=True, text=True, capture_output=True, timeout=60, env=env
    ).stdout.strip()


def smoke() -> None:
    operator, approver = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    identities = {
        operator: {"name": "smoke-operator", "roles": ["read", "diagnose", "execute"]},
        approver: {"name": "smoke-approver", "roles": ["read", "approve"]},
    }
    name = "opspilot-smoke-" + secrets.token_hex(5)
    started = False
    try:
        docker(
            "run",
            "-d",
            "--name",
            name,
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--memory",
            "256m",
            "--cpus",
            "1",
            "--pids-limit",
            "64",
            "--tmpfs",
            "/tmp:size=16m,mode=1777",
            "--tmpfs",
            "/state:size=32m,uid=10001,gid=10001,mode=0700",
            "-p",
            "127.0.0.1::8080",
            "-e",
            "OPSPILOT_IDENTITIES",
            "opspilot:local",
            env={**os.environ, "OPSPILOT_IDENTITIES": json.dumps(identities)},
        )
        started = True
        address = docker("port", name, "8080/tcp").splitlines()[0]
        with httpx.Client(base_url="http://" + address, timeout=15, trust_env=False) as client:
            for _ in range(30):
                try:
                    if client.get("/api/health").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.2)
            headers = {"Authorization": "Bearer " + operator, "Idempotency-Key": "container-smoke-0001"}
            assert client.get("/api/runs").status_code == 401
            response = client.post("/api/runs", headers=headers, json={"runbook": "service", "target": "lab"})
            response.raise_for_status()
            run = response.json()
            assert run["status"] == "finding"
            approval = client.post("/api/runs/" + run["id"] + "/approval", headers=headers).json()
            path = "/api/approvals/" + approval["id"]
            assert client.post(path + "/execute", headers=headers).status_code == 409
            decision = client.post(
                path + "/decision",
                headers={"Authorization": "Bearer " + approver},
                json={"decision": "approve", "reason": "Approved disposable container smoke recovery"},
            )
            decision.raise_for_status()
            recovery = client.post(path + "/execute", headers=headers)
            recovery.raise_for_status()
            assert recovery.json()["remediation"]["verified"]
            assert client.get("/").status_code == 200
            report = {
                "scope": "packaged runtime; non-root, read-only root, no capabilities, bounded resources",
                "unauthenticated_denied": True,
                "unapproved_denied": True,
                "recovery_verified": True,
                "dashboard_served": True,
                "container_user": docker("inspect", name, "--format", "{{.Config.User}}"),
            }
            Path("docs/container-smoke.json").write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report))
    finally:
        if started:
            docker("rm", "-f", name)


if __name__ == "__main__":
    smoke()
