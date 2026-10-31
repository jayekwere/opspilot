import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from conftest import headers

from opspilot.cli import demo
from opspilot.runbooks import live
from opspilot.runner import Output, job_steps


def test_demo(tmp_path):
    report = asyncio.run(demo(tmp_path / "report.json"))
    assert report["unapproved_execution_denied"]
    assert report["idempotent_replay"]
    assert report["stale_approval_failure"]["remediation"]["outcome"] == "failed"


def test_security_recovery(client):
    run = client.post("/api/runs", headers=headers(), json={"runbook": "security", "target": "lab"}).json()
    assert run["status"] == "finding"
    approval = client.post(f"/api/runs/{run['id']}/approval", headers=headers()).json()
    assert (
        client.post(
            f"/api/approvals/{approval['id']}/decision",
            headers=headers("approver"),
            json={"decision": "approve", "reason": "Approved disposable configuration repair"},
        ).status_code
        == 200
    )
    recovered = client.post(f"/api/approvals/{approval['id']}/execute", headers=headers()).json()
    assert recovered["remediation"]["verified"]
    healthy = client.post(
        "/api/runs", headers=headers(key="healthy-security"), json={"runbook": "security", "target": "lab"}
    ).json()
    assert healthy["status"] == "healthy"


def test_restart_invalidation(tmp_path):
    from conftest import IDENTITIES
    from fastapi.testclient import TestClient

    from opspilot.api import create_app

    directory = tmp_path / "state"
    with TestClient(create_app(directory, IDENTITIES)) as client:
        run = client.post("/api/runs", headers=headers(), json={"runbook": "service", "target": "lab"}).json()
        approval = client.post(f"/api/runs/{run['id']}/approval", headers=headers()).json()
        client.post(
            f"/api/approvals/{approval['id']}/decision",
            headers=headers("approver"),
            json={"decision": "approve", "reason": "Approved lab recovery"},
        )
    with TestClient(create_app(directory, IDENTITIES)) as client:
        assert client.post(f"/api/approvals/{approval['id']}/execute", headers=headers()).status_code == 409
        assert client.get("/api/runs", headers=headers()).json()[0]["id"] == run["id"]


def test_filesystem_live():
    result = asyncio.run(live("filesystem"))
    assert 0 <= result["used_pct"] <= 100


def test_performance_linux_parser():
    with (
        patch("pathlib.Path.read_text", return_value="MemTotal: 1000 kB\nMemAvailable: 500 kB\n"),
        patch("pathlib.Path.exists", return_value=False),
    ):
        assert asyncio.run(live("performance"))["available_memory_pct"] == 50


def test_security_live_parser():
    with (
        patch(
            "opspilot.runbooks.read_configuration",
            return_value="PermitRootLogin no\nPasswordAuthentication no\n",
        ),
        patch("pathlib.Path.stat", return_value=SimpleNamespace(st_mode=0o600)),
    ):
        result = asyncio.run(live("security"))
        assert result["permit_root_login"] == "no"


def test_cloud_configuration_parser():
    async def command(key):
        data = {
            "cloud": {"InstanceStatuses": []},
            "cloud_volumes": {"Volumes": [{"Encrypted": False}]},
            "cloud_groups": {
                "SecurityGroups": [{"IpPermissions": [{"IpRanges": [{"CidrIp": "0.0.0.0/0"}]}]}]
            },
        }[key]
        return Output(0, json.dumps(data), False)

    with patch("opspilot.runbooks.command", command):
        result = asyncio.run(live("cloud"))
        assert result["configuration"] == {"encrypted": False, "public_ingress": True}


def test_pipeline_steps():
    with (
        patch(
            "opspilot.runbooks.command",
            AsyncMock(return_value=Output(0, '[{"conclusion":"failure","databaseId":123}]', False)),
        ),
        patch(
            "opspilot.runbooks.job_steps", AsyncMock(return_value=Output(0, '{"jobs":[{"steps":[]}]}', False))
        ),
    ):
        assert "jobs" in asyncio.run(live("pipeline"))


def test_bad_provider_id():
    for value in (";id", -1, True):
        with pytest.raises(ValueError):
            asyncio.run(job_steps(value))


def test_empty_metrics(client):
    metrics = client.get("/api/metrics", headers=headers()).json()
    assert metrics["success_rate"] is None
    assert metrics["repeatability"] is None


def test_kubernetes_evidence_excludes_secrets():
    raw = {
        "items": [
            {
                "kind": "Pod",
                "metadata": {"name": "api", "namespace": "lab"},
                "spec": {"containers": [{"env": [{"name": "API_TOKEN", "value": "raw-sensitive"}]}]},
                "status": {
                    "phase": "Running",
                    "containerStatuses": [
                        {
                            "ready": False,
                            "restartCount": 2,
                            "state": {"waiting": {"reason": "CrashLoopBackOff"}},
                        }
                    ],
                },
            }
        ]
    }
    with patch("opspilot.runbooks.command", AsyncMock(return_value=Output(0, json.dumps(raw), False))):
        data = asyncio.run(live("kubernetes"))
        assert "raw-sensitive" not in json.dumps(data)
        assert data["items"][0]["status"]["containerStatuses"][0]["restartCount"] == 2


def test_dns_supported_failure():
    import socket

    async def failure(*args, **kwargs):
        raise socket.gaierror("no resolver")

    async def check():
        loop = asyncio.get_running_loop()
        with patch.object(loop, "getaddrinfo", failure):
            return await live("network")

    assert asyncio.run(check())["dns_ok"] is False


@pytest.mark.skipif(
    not __import__("sys").platform.startswith("linux"), reason="Linux /proc integration runs in Docker and CI"
)
def test_actual_linux_performance():
    data = asyncio.run(live("performance"))
    assert data["load_per_cpu"] >= 0
    assert 0 <= data["available_memory_pct"] <= 100


def test_ssh_policy_ambiguity_is_not_healthy():
    from opspilot.runbooks import analyze

    config = "PermitRootLogin no\nPasswordAuthentication no\nInclude /etc/ssh/sshd_config.d/*.conf\nMatch User root\n"
    with (
        patch("opspilot.runbooks.read_configuration", return_value=config),
        patch("pathlib.Path.stat", return_value=SimpleNamespace(st_mode=0o600)),
    ):
        result = analyze("security", asyncio.run(live("security")))
        assert result.status == "finding"
        assert any(f.code == "ssh_policy_unresolved" for f in result.findings)
