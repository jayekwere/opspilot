import time

import pytest
from conftest import headers

from opspilot.runbooks import DESCRIPTIONS


def diagnose(client, key="test-key-0001", name="operator", target="lab"):
    response = client.post(
        "/api/runs", headers=headers(name, key), json={"runbook": "service", "target": target}
    )
    assert response.status_code == 201, response.text
    return response.json()


def pending(client, key="test-key-0001", name="operator"):
    run = diagnose(client, key, name)
    response = client.post(f"/api/runs/{run['id']}/approval", headers=headers(name))
    assert response.status_code == 200, response.text
    return run, response.json()


def approve(client, approval, name="approver"):
    return client.post(
        f"/api/approvals/{approval['id']}/decision",
        headers=headers(name),
        json={"decision": "approve", "reason": "Disposable sandbox recovery approved"},
    )


@pytest.mark.parametrize(
    "path", ["/api/me", "/api/catalog", "/api/runs", "/api/metrics", "/api/approvals", "/api/audit"]
)
def test_unauthenticated(client, path):
    assert client.get(path).status_code == 401


@pytest.mark.parametrize("book", DESCRIPTIONS)
def test_all_books_api(client, book):
    response = client.post(
        "/api/runs",
        headers=headers(key="book-test-" + book),
        json={"runbook": book, "target": "fixture", "scenario": "failure"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "finding"
    assert client.get("/api/runs/" + response.json()["id"], headers=headers()).status_code == 200


def test_full_recovery(client):
    run, approval = pending(client)
    url = f"/api/approvals/{approval['id']}/execute"
    assert client.post(url, headers=headers(), json={}).status_code == 409
    assert approve(client, approval).status_code == 200
    assert client.post(url, headers=headers("approver"), json={}).status_code == 403
    recovered = client.post(url, headers=headers(), json={})
    assert recovered.status_code == 200, recovered.text
    assert recovered.json()["remediation"]["verified"]
    assert client.post(url, headers=headers(), json={}).json() == recovered.json()
    healthy = diagnose(client, key="healthy-run-0002")
    assert healthy["status"] == "healthy"
    events = client.get("/api/audit", headers=headers()).json()
    assert any(e["event"] == "remediation_succeeded" for e in events)


def test_independent_approval(client):
    _, approval = pending(client, name="dual")
    assert approve(client, approval, "dual").status_code == 403


def test_denied_permissions(client):
    assert client.post("/api/runs", headers=headers("reader"), json={"runbook": "logs"}).status_code == 403
    assert client.post("/api/lab/inject", headers=headers("approver"), json={}).status_code == 403


def test_idempotency(client):
    first = diagnose(client)
    assert diagnose(client) == first
    assert (
        client.post("/api/runs", headers=headers(), json={"runbook": "logs", "target": "fixture"}).status_code
        == 409
    )
    assert len(client.get("/api/runs", headers=headers()).json()) == 1


def test_expired(client):
    _, approval = pending(client)
    assert approve(client, approval).status_code == 200
    with client.app.state.service.store.transaction() as db:
        db.execute("UPDATE approvals SET expires=?", (time.time() - 1,))
    assert (
        client.post(f"/api/approvals/{approval['id']}/execute", headers=headers(), json={}).status_code == 409
    )


def test_stale_generation(client):
    _, approval = pending(client)
    assert approve(client, approval).status_code == 200
    assert client.post("/api/lab/inject", headers=headers(), json={}).status_code == 200
    result = client.post(f"/api/approvals/{approval['id']}/execute", headers=headers(), json={}).json()
    assert result["remediation"]["outcome"] == "failed"
    assert not client.app.state.lab.healthy


def test_rejection(client):
    _, approval = pending(client)
    response = client.post(
        f"/api/approvals/{approval['id']}/decision",
        headers=headers("approver"),
        json={"decision": "reject", "reason": "Evidence is insufficient"},
    )
    assert response.status_code == 200
    assert (
        client.post(f"/api/approvals/{approval['id']}/execute", headers=headers(), json={}).status_code == 409
    )


def test_fixture_cannot_remediate(client):
    run = diagnose(client, target="fixture")
    assert client.post(f"/api/runs/{run['id']}/approval", headers=headers()).status_code == 409


def test_cross_operator_request(client):
    run = diagnose(client)
    assert client.post(f"/api/runs/{run['id']}/approval", headers=headers("dual")).status_code == 403


def test_malicious_api(client):
    assert client.post("/api/runs", headers=headers(), json={"runbook": "logs;id"}).status_code == 422
    assert (
        client.post("/api/runs", headers=headers(key="../../evil"), json={"runbook": "logs"}).status_code
        == 422
    )
    assert (
        client.post(
            "/api/runs", headers={**headers(), "Origin": "https://evil.example"}, json={"runbook": "logs"}
        ).status_code
        == 403
    )
    assert client.post("/api/runs", headers=headers(), content="x" * 9000).status_code == 413
    assert client.get("/api/health", headers={"Host": "evil.example"}).status_code == 400
    assert client.get("/api/runs/missing", headers=headers()).status_code == 404


def test_redaction_and_metrics(client):
    response = client.post(
        "/api/runs",
        headers=headers(),
        json={
            "runbook": "logs",
            "target": "fixture",
            "manual_seconds": 30.0,
            "baseline_source": "controlled lab assumption",
        },
    )
    assert response.status_code == 201
    assert "secret-value" not in response.text
    assert "[REDACTED]" in response.text
    metric = client.get("/api/metrics", headers=headers()).json()
    assert metric["baseline_runs"] == 1
    assert metric["success_rate"] == 1
    assert 0 < metric["estimated_effort_avoided_seconds"] <= 30
    assert client.get("/api/health").headers["X-Content-Type-Options"] == "nosniff"


def test_invalid_baseline(client):
    assert (
        client.post(
            "/api/runs", headers=headers(), json={"runbook": "logs", "manual_seconds": 20.0}
        ).status_code
        == 422
    )
