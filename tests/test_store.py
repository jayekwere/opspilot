import hashlib
import json

import pytest

from opspilot.api import load_identities
from opspilot.store import Store, sanitize


def test_private_storage(tmp_path):
    store = Store(tmp_path / "state")
    try:
        with store.transaction() as db:
            store.audit(db, "operator", "test", "subject")
            store.audit(db, "approver", "decision", "subject")
        previous = "0" * 64
        for event in reversed(store.events()):
            assert event["previous"] == previous
            payload = json.dumps(
                [event["at"], event["actor"], event["event"], event["subject"], previous],
                separators=(",", ":"),
            )
            assert hashlib.sha256(payload.encode()).hexdigest() == event["digest"]
            previous = event["digest"]
        assert (tmp_path / "state").stat().st_mode & 0o777 == 0o700
        assert (tmp_path / "state" / "opspilot.db").stat().st_mode & 0o777 == 0o600
    finally:
        store.close()


def test_symlink(tmp_path):
    (tmp_path / "real").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "real")
    with pytest.raises(ValueError):
        Store(tmp_path / "link")


def test_nested_redaction():
    assert sanitize({"token": "value", "data": ["password=secret"]}) == {
        "token": "[REDACTED]",
        "data": ["password=[REDACTED]"],
    }


def test_missing_identity(monkeypatch):
    monkeypatch.delenv("OPSPILOT_IDENTITIES", raising=False)
    with pytest.raises(ValueError):
        load_identities()


def test_identity_strength(monkeypatch):
    monkeypatch.setenv("OPSPILOT_IDENTITIES", json.dumps({"short": {"name": "user", "roles": ["read"]}}))
    with pytest.raises(ValueError):
        load_identities()
