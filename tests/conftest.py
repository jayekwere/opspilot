import hashlib

import pytest
from fastapi.testclient import TestClient

from opspilot.api import create_app
from opspilot.models import Principal

TOKENS = {name: name + "-" + "x" * 40 for name in ("operator", "approver", "reader", "dual")}
IDENTITIES = {
    hashlib.sha256(TOKENS["operator"].encode()).hexdigest(): Principal(
        name="operator", roles=["read", "diagnose", "execute"]
    ),
    hashlib.sha256(TOKENS["approver"].encode()).hexdigest(): Principal(
        name="approver", roles=["read", "approve"]
    ),
    hashlib.sha256(TOKENS["reader"].encode()).hexdigest(): Principal(name="reader", roles=["read"]),
    hashlib.sha256(TOKENS["dual"].encode()).hexdigest(): Principal(
        name="dual", roles=["read", "diagnose", "approve", "execute"]
    ),
}


def headers(name="operator", key="test-key-0001"):
    return {"Authorization": "Bearer " + TOKENS[name], "Idempotency-Key": key}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "state", IDENTITIES)) as client:
        yield client
