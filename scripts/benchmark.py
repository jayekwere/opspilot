"""Compare scripted manual-procedure steps with orchestrated diagnostics.

Neither timing represents a human operator. No sleeps or fabricated baselines.
"""

import asyncio
import json
import statistics
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from opspilot.lab import Lab
from opspilot.models import Principal, Request
from opspilot.service import Service
from opspilot.store import Store


async def benchmark(trials: int = 20) -> dict:
    with tempfile.TemporaryDirectory(prefix="opspilot-benchmark-") as directory:
        lab = Lab()
        store = Store(Path(directory))
        service = Service(store, lab)
        principal = Principal(name="benchmark-operator", roles=["diagnose", "read"])
        manual_procedure = []
        automated = []
        try:
            for trial in range(trials):
                start = time.perf_counter()
                # Script a documented three-step manual procedure: probe, inspect,
                # and write a finding. This does not measure human effort.
                try:
                    with urllib.request.urlopen(lab.url, timeout=2) as response:  # nosec B310
                        code = response.status
                        body = response.read(1024).decode()
                except urllib.error.HTTPError as error:
                    code = error.code
                    body = error.read(1024).decode()
                record = {
                    "http_status": code,
                    "body": body,
                    "supported_condition": code == 503,
                    "recommendation": "independent approval for lab recovery" if code == 503 else "none",
                }
                Path(directory, "manual-procedure.json").write_text(json.dumps(record))
                manual_procedure.append(time.perf_counter() - start)
                run = await service.diagnose(
                    principal, Request(runbook="service", target="lab"), f"benchmark-{trial:04d}"
                )
                automated.append(run["seconds"])
            report = {
                "scope": "controlled local HTTP 503 lab; scripted comparator, not measured human work",
                "trials": trials,
                "scripted_manual_procedure_seconds": manual_procedure,
                "automated_diagnosis_seconds": automated,
                "scripted_manual_median_seconds": statistics.median(manual_procedure),
                "automated_median_seconds": statistics.median(automated),
                "human_manual_seconds": None,
                "human_effort_avoided_seconds": None,
                "outcome_repeatability": service.metrics()["repeatability"],
                "limitations": [
                    "Comparator omits human interpretation time",
                    "Automated timing includes HTTP client setup and analysis, but excludes persistence commit",
                    "Manual baseline is unmeasured; no productivity gain is claimed",
                    "Approval and recovery time are reported separately by the demo",
                ],
            }
            return report
        finally:
            store.close()
            lab.close()


if __name__ == "__main__":
    output = Path("docs/benchmark.json")
    output.write_text(json.dumps(asyncio.run(benchmark()), indent=2) + "\n")
    print(output)
