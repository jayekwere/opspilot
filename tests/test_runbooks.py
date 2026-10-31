import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from opspilot.models import Request
from opspilot.runbooks import DESCRIPTIONS, analyze, collect, fixture, live
from opspilot.runner import Output, _execute, command


@pytest.mark.parametrize("book", DESCRIPTIONS)
@pytest.mark.parametrize("scenario", ["healthy", "failure"])
def test_analyzer(book, scenario):
    result = analyze(book, fixture(book, scenario))
    assert result.status == ("healthy" if scenario == "healthy" else "finding")
    assert bool(result.findings) == (scenario == "failure")
    for finding in result.findings:
        assert finding.code and finding.summary and finding.recommendation


@pytest.mark.parametrize("book", DESCRIPTIONS)
def test_offline(book, client):
    result = asyncio.run(
        collect(Request(runbook=book, target="fixture", scenario="unavailable"), client.app.state.lab)
    )
    assert result.status == "unavailable"


@pytest.mark.parametrize(
    "payload",
    [
        {"runbook": ";id"},
        {"runbook": "performance", "target": "../../etc/passwd"},
        {"runbook": "logs", "command": "cat /etc/shadow"},
        {"runbook": "tls", "host": "169.254.169.254"},
        {"runbook": "cloud", "manual_seconds": -1},
        {"runbook": "performance", "manual_seconds": "30"},
    ],
)
def test_strict_input(payload):
    with pytest.raises(ValidationError):
        Request.model_validate(payload)


def test_bounded_output():
    result = asyncio.run(_execute(("python3", "-c", 'print("x" * 100000)'), limit=100))
    assert result.truncated and len(result.text) == 100


def test_command_timeout():
    with pytest.raises(TimeoutError):
        asyncio.run(_execute(("python3", "-c", "import time; time.sleep(10)"), timeout=0.05))


def test_command_registry():
    with pytest.raises(KeyError):
        asyncio.run(command("sh -c id"))


def test_missing_executable():
    with pytest.raises(OSError):
        asyncio.run(_execute(("opspilot-nonexistent",)))


@pytest.mark.parametrize(
    "book,output",
    [
        ("service", "ActiveState=active\nSubState=running"),
        ("kubernetes", '{"items":[]}'),
        ("pipeline", '[{"conclusion":"success"}]'),
        ("cloud", '{"InstanceStatuses":[]}'),
        ("logs", "INFO test"),
    ],
)
def test_live_command_parsers(book, output):
    with patch("opspilot.runbooks.command", AsyncMock(return_value=Output(0, output, False))):
        assert isinstance(asyncio.run(live(book)), dict)


@pytest.mark.parametrize("output", [Output(1, "denied", False), Output(0, "oversized", True)])
def test_failed_commands(output):
    with patch("opspilot.runbooks.command", AsyncMock(return_value=output)):
        with pytest.raises(OSError):
            asyncio.run(live("cloud"))


def test_dns_failure_returns_unavailable(client):
    with patch("opspilot.runbooks.live", AsyncMock(side_effect=OSError)):
        result = asyncio.run(collect(Request(runbook="network", target="local"), client.app.state.lab))
        assert result.status == "unavailable"


def test_lab_wrong_book(client):
    result = asyncio.run(collect(Request(runbook="cloud", target="lab"), client.app.state.lab))
    assert result.status == "unavailable"


def test_credentials_do_not_reach_unrelated_collectors(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "synthetic-credential")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "synthetic-cloud-credential")
    result = asyncio.run(
        _execute(
            (
                "python3",
                "-c",
                'import os; print(os.getenv("GH_TOKEN")); print(os.getenv("AWS_SECRET_ACCESS_KEY"))',
            )
        )
    )
    assert result.text == "None\nNone\n"
