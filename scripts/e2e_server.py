"""Isolated loopback server for browser tests. Never use these public test tokens elsewhere."""

import hashlib
import tempfile
from pathlib import Path

import uvicorn

from opspilot.api import create_app
from opspilot.models import Principal

identities = {
    hashlib.sha256(("test-" + name + "-" + "x" * 40).encode()).hexdigest(): Principal(name=name, roles=roles)
    for name, roles in [("operator", ["read", "diagnose", "execute"]), ("approver", ["read", "approve"])]
}
with tempfile.TemporaryDirectory(prefix="opspilot-e2e-") as directory:
    uvicorn.run(create_app(Path(directory), identities), host="127.0.0.1", port=8091, access_log=False)
