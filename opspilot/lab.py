"""Disposable HTTP service. The main process owns it; no host service controls."""

import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Lab:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.directory = tempfile.TemporaryDirectory(prefix="opspilot-security-")
        self.config = Path(self.directory.name) / "sshd_config"
        self.config.write_text("PermitRootLogin yes\nPasswordAuthentication yes\n")
        self.config.chmod(0o644)
        self.healthy = False
        self.generation = 0
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self.send_response(200 if owner.healthy else 503)
                self.end_headers()
                self.wfile.write(b"healthy" if owner.healthy else b"dependency unavailable")

            def log_message(self, format: str, *args: object) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(
            target=lambda: self.server.serve_forever(poll_interval=0.05), daemon=True
        )
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/health"

    def inject(self, healthy: bool = False) -> None:
        with self.lock:
            self.healthy = healthy
            self.generation += 1

    def repair(self, generation: int, book: str = "service") -> None:
        with self.lock:
            if generation != self.generation:
                raise ValueError("lab changed since diagnosis; diagnose again")
            if book == "service":
                self.healthy = True
            elif book == "security":
                self.config.write_text("PermitRootLogin no\nPasswordAuthentication no\n")
                self.config.chmod(0o600)
            else:
                raise ValueError("unsupported lab action")

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.directory.cleanup()
