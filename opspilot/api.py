"""Local-first authenticated API and static console."""

import asyncio
import hashlib
import hmac
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi import Request as HTTPRequest
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from opspilot.lab import Lab
from opspilot.models import Approval, Principal, Request
from opspilot.runbooks import DESCRIPTIONS
from opspilot.service import Conflict, Service, require
from opspilot.store import Store


def load_identities() -> dict[str, Principal]:
    """Environment maps high-entropy bearer tokens to distinct operator identities."""
    raw = json.loads(os.environ.get("OPSPILOT_IDENTITIES", "{}"))
    if not isinstance(raw, dict) or not raw:
        raise ValueError("OPSPILOT_IDENTITIES must configure at least one operator")
    result = {}
    for token, identity in raw.items():
        if len(token) < 32:
            raise ValueError("bearer tokens must be at least 32 characters")
        result[hashlib.sha256(token.encode()).hexdigest()] = Principal.model_validate(identity)
    return result


def create_app(directory: Path | None = None, identities: dict[str, Principal] | None = None) -> FastAPI:
    configured = identities if identities is not None else load_identities()
    state_path = directory or Path(os.environ.get("OPSPILOT_STATE", ".opspilot"))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = Store(state_path)
        lab = Lab()
        app.state.service = Service(store, lab)
        app.state.lab = lab
        try:
            yield
        finally:
            lab.close()
            store.close()

    app = FastAPI(title="OpsPilot", version="0.1.0", lifespan=lifespan)
    slots = asyncio.Semaphore(8)

    @app.middleware("http")
    async def boundary(request: HTTPRequest, call_next: Any) -> Any:
        if request.headers.get("host", "").split(":")[0] not in ("127.0.0.1", "localhost", "testserver"):
            return JSONResponse({"detail": "untrusted host"}, status_code=400)
        if request.method in ("POST", "PUT", "PATCH"):
            if request.headers.get("origin") and request.headers["origin"] != str(request.base_url).rstrip(
                "/"
            ):
                return JSONResponse({"detail": "cross-origin mutation denied"}, status_code=403)
            try:
                size = int(request.headers.get("content-length", "0"))
            except ValueError:
                return JSONResponse({"detail": "invalid content length"}, status_code=400)
            if size > 8192 or "transfer-encoding" in request.headers:
                return JSONResponse({"detail": "body exceeds limit or uses streaming"}, status_code=413)
            body = bytearray()
            try:
                async with asyncio.timeout(3):
                    async for chunk in request.stream():
                        if len(body) + len(chunk) > 8192:
                            return JSONResponse({"detail": "body exceeds limit"}, status_code=413)
                        body.extend(chunk)
            except TimeoutError:
                return JSONResponse({"detail": "request body timed out"}, status_code=408)
            request._body = bytes(body)
        try:
            await asyncio.wait_for(slots.acquire(), 0.05)
        except TimeoutError:
            return JSONResponse({"detail": "busy; retry later"}, status_code=429)
        try:
            response = await call_next(request)
            response.headers.update(
                {
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                    "Referrer-Policy": "no-referrer",
                    "Content-Security-Policy": "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'",
                }
            )
            return response
        finally:
            slots.release()

    async def identity(
        request: HTTPRequest, authorization: Annotated[str | None, Header()] = None
    ) -> Principal:
        token = authorization[7:] if authorization and authorization.startswith("Bearer ") else ""
        digest = hashlib.sha256(token.encode()).hexdigest()
        for expected, principal in configured.items():
            if hmac.compare_digest(expected, digest):
                request.state.principal = principal.name
                return principal
        with request.app.state.service.store.transaction() as db:
            request.app.state.service.store.audit(
                db, "anonymous", "authentication_denied", request.url.path[:100]
            )
        raise HTTPException(401, "valid bearer credential required")

    Auth = Annotated[Principal, Depends(identity)]

    # Avoid local type-alias forward-reference resolution under future annotations.
    @app.exception_handler(PermissionError)
    async def denied(request: HTTPRequest, error: PermissionError) -> JSONResponse:
        with request.app.state.service.store.transaction() as db:
            request.app.state.service.store.audit(
                db,
                getattr(request.state, "principal", "authenticated"),
                "authorization_denied",
                request.url.path[:100],
            )
        return JSONResponse({"detail": str(error)}, status_code=403)

    @app.exception_handler(Conflict)
    async def conflict(request: HTTPRequest, error: Conflict) -> JSONResponse:
        return JSONResponse({"detail": str(error)}, status_code=409)

    @app.exception_handler(KeyError)
    async def missing(request: HTTPRequest, error: KeyError) -> JSONResponse:
        return JSONResponse({"detail": "record not found"}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(request: HTTPRequest, error: ValueError) -> JSONResponse:
        return JSONResponse({"detail": str(error)}, status_code=422)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/me")
    async def me(principal: Auth) -> Principal:
        return principal

    @app.get("/api/catalog")
    async def catalog(principal: Auth) -> list[dict[str, Any]]:
        require(principal, "read")
        return [
            {
                "id": key,
                "description": description,
                "targets": ["fixture", "local"] + (["lab"] if key in ("service", "security") else []),
                "remediation": key in ("service", "security"),
            }
            for key, description in DESCRIPTIONS.items()
        ]

    @app.post("/api/runs", status_code=201)
    async def diagnose(
        body: Request,
        principal: Auth,
        request: HTTPRequest,
        idempotency_key: Annotated[str, Header(max_length=80)],
    ) -> dict[str, Any]:
        return await request.app.state.service.diagnose(principal, body, idempotency_key)

    @app.get("/api/runs")
    async def runs(principal: Auth, request: HTTPRequest) -> list[dict[str, Any]]:
        require(principal, "read")
        return request.app.state.service.store.runs()

    @app.get("/api/runs/{identifier}")
    async def run(identifier: str, principal: Auth, request: HTTPRequest) -> dict[str, Any]:
        require(principal, "read")
        return request.app.state.service.store.run(identifier)

    @app.post("/api/runs/{identifier}/approval")
    async def approval(identifier: str, principal: Auth, request: HTTPRequest) -> dict[str, Any]:
        return request.app.state.service.request_approval(principal, identifier)

    @app.get("/api/approvals")
    async def approvals(principal: Auth, request: HTTPRequest) -> list[dict[str, Any]]:
        require(principal, "read")
        return request.app.state.service.store.approvals()

    @app.post("/api/approvals/{identifier}/decision")
    async def decision(
        identifier: str, body: Approval, principal: Auth, request: HTTPRequest
    ) -> dict[str, Any]:
        return request.app.state.service.decide(principal, identifier, body)

    @app.post("/api/approvals/{identifier}/execute")
    async def execute(identifier: str, principal: Auth, request: HTTPRequest) -> dict[str, Any]:
        return await request.app.state.service.execute(principal, identifier)

    @app.get("/api/metrics")
    async def metrics(principal: Auth, request: HTTPRequest) -> dict[str, Any]:
        require(principal, "read")
        return request.app.state.service.metrics()

    @app.get("/api/audit")
    async def audit(principal: Auth, request: HTTPRequest) -> list[dict[str, Any]]:
        require(principal, "read")
        return request.app.state.service.store.events()

    @app.post("/api/lab/inject")
    async def inject(principal: Auth, request: HTTPRequest) -> dict[str, int]:
        require(principal, "execute")
        service = request.app.state.service
        async with service.gate:
            service.lab.inject()
            with service.store.transaction() as db:
                service.store.audit(db, principal.name, "lab_failure_injected", str(service.lab.generation))
        return {"generation": service.lab.generation}

    dist = Path(__file__).resolve().parent.parent / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="dashboard")
    return app
