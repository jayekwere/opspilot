"""OpsPilot local CLI. Credentials are read only from the environment."""

import argparse
import asyncio
import json
import logging
import os
import secrets
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx

from opspilot.lab import Lab
from opspilot.models import Approval, Principal, Request
from opspilot.service import Service
from opspilot.store import Store

OPERATOR = Principal(name="lab-operator", roles=["diagnose", "execute", "read"])
APPROVER = Principal(name="lab-approver", roles=["approve", "read"])


async def demo(output: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="opspilot-lab-") as directory:
        lab = Lab()
        store = Store(Path(directory))
        service = Service(store, lab)
        try:
            started = time.perf_counter()
            first = await service.diagnose(
                OPERATOR, Request(runbook="service", target="lab"), "demo-diagnosis"
            )
            approval = service.request_approval(OPERATOR, first["id"])
            denied = False
            try:
                await service.execute(OPERATOR, approval["id"])
            except ValueError:
                denied = True
            service.decide(
                APPROVER,
                approval["id"],
                Approval(decision="approve", reason="Disposable lab recovery approved"),
            )
            recovery = await service.execute(OPERATOR, approval["id"])
            replay = await service.execute(OPERATOR, approval["id"])
            healthy = await service.diagnose(
                OPERATOR, Request(runbook="service", target="lab"), "demo-healthy"
            )
            lab.inject()
            stale_run = await service.diagnose(
                OPERATOR, Request(runbook="service", target="lab"), "demo-stale-run"
            )
            stale = service.request_approval(OPERATOR, stale_run["id"])
            service.decide(
                APPROVER,
                stale["id"],
                Approval(decision="approve", reason="Approve generation-specific recovery"),
            )
            lab.inject()
            failed = await service.execute(OPERATOR, stale["id"])
            report = {
                "scope": "controlled disposable HTTP service lab",
                "diagnosis": first,
                "unapproved_execution_denied": denied,
                "recovery": recovery,
                "idempotent_replay": replay == recovery,
                "healthy_verification": healthy,
                "stale_approval_failure": failed,
                "elapsed_seconds": time.perf_counter() - started,
                "audit": store.events(),
                "metrics": service.metrics(),
            }
            assert first["status"] == "finding" and recovery["remediation"]["verified"] and denied
            assert healthy["status"] == "healthy" and failed["remediation"]["outcome"] == "failed"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2) + "\n")
            return report
        finally:
            store.close()
            lab.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("credentials", help="generate distinct local operator and approver credentials")
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8080)
    lab = sub.add_parser("demo")
    lab.add_argument("--output", type=Path, default=Path("docs/demo-result.json"))
    diagnose = sub.add_parser("run")
    diagnose.add_argument(
        "runbook", choices=list(__import__("opspilot.runbooks", fromlist=["DESCRIPTIONS"]).DESCRIPTIONS)
    )
    diagnose.add_argument("--target", choices=["fixture", "local", "lab"], default="fixture")
    diagnose.add_argument("--scenario", choices=["healthy", "failure", "unavailable"], default="failure")
    diagnose.add_argument("--url", default="http://127.0.0.1:8080")
    args = parser.parse_args()
    if args.command == "credentials":
        print(
            json.dumps(
                {
                    secrets.token_urlsafe(32): OPERATOR.model_dump(),
                    secrets.token_urlsafe(32): APPROVER.model_dump(),
                }
            )
        )
    elif args.command == "serve":
        import uvicorn

        logging.basicConfig(level=logging.INFO, format="%(message)s")
        uvicorn.run(
            "opspilot.api:create_app",
            factory=True,
            host="127.0.0.1" if not os.environ.get("OPSPILOT_CONTAINER") else "0.0.0.0",  # nosec B104
            port=args.port,
            workers=1,
            limit_concurrency=16,
            timeout_keep_alive=5,
        )
    elif args.command == "demo":
        report = asyncio.run(demo(args.output))
        print(json.dumps({"recovery": report["recovery"]["remediation"], "report": str(args.output)}))
    else:
        token = os.environ.get("OPSPILOT_TOKEN", "")
        if not token:
            parser.error("OPSPILOT_TOKEN is required")
        if not args.url.startswith("http://127.0.0.1:"):
            parser.error("CLI only connects to the local API")
        response = httpx.post(
            args.url + "/api/runs",
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": secrets.token_hex(16)},
            json={"runbook": args.runbook, "target": args.target, "scenario": args.scenario},
            timeout=20,
            trust_env=False,
        )
        response.raise_for_status()
        print(json.dumps(response.json(), indent=2))


if __name__ == "__main__":
    main()
