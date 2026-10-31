"""Real TLS handshake against a temporary self-signed local server."""

import asyncio
import shutil
import ssl
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import pytest

from opspilot.runbooks import live


@pytest.mark.parametrize("trusted", [True, False])
def test_real_tls(tmp_path, trusted):
    executable = shutil.which("openssl")
    if not executable:
        pytest.skip("openssl CLI not installed")
    key = tmp_path / "key.pem"
    cert = tmp_path / "cert.pem"
    subprocess.run(
        [
            executable,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-days",
            "2",
            "-subj",
            "/CN=example.com",
            "-addext",
            "subjectAltName=DNS:example.com",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
    )

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.05), daemon=True)
    thread.start()
    real_open = asyncio.open_connection
    client_context = ssl.create_default_context(cafile=str(cert)) if trusted else ssl.create_default_context()

    async def local_connection(host, port, **kwargs):
        return await real_open("127.0.0.1", server.server_port, ssl=client_context, server_hostname=host)

    try:
        with patch("opspilot.runbooks.asyncio.open_connection", local_connection):
            result = asyncio.run(live("tls"))
        assert result["trusted"] == trusted
        if trusted:
            assert 0 < result["days_remaining"] < 3
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
