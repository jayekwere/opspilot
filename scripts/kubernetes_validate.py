"""Validate against an explicitly supplied disposable kind kubeconfig.

Creates and deletes only its own namespace. Cluster lifecycle is managed separately.
"""

import asyncio
import json
import os
import subprocess
from pathlib import Path

from opspilot.runbooks import analyze, live

NAMESPACE = "opspilot-validation"


def kubectl(*args: str) -> str:
    return subprocess.run(
        ["kubectl", "--kubeconfig", os.environ["KUBECONFIG"], *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout


async def validate() -> None:
    # Never mutate an ambient context or a non-lab cluster.
    if "kind-opspilot-validation" not in kubectl("config", "current-context"):
        raise ValueError("requires kind-opspilot-validation context")
    kubectl("create", "namespace", NAMESPACE)
    try:
        kubectl(
            "-n", NAMESPACE, "create", "deployment", "broken", "--image=busybox:1.37.0", "--", "/bin/false"
        )
        observed = None
        for _ in range(30):
            data = await live("kubernetes")
            data["items"] = [
                i for i in data["items"] if i["kind"] == "Node" or i["metadata"].get("namespace") == NAMESPACE
            ]
            result = analyze("kubernetes", data)
            if (
                any(
                    c.get("restartCount", 0) > 0
                    for i in data["items"]
                    if i["kind"] == "Pod"
                    for c in i.get("status", {}).get("containerStatuses", [])
                )
                and any(f.code == "pod_not_ready" for f in result.findings)
                and any(f.code == "deployment_unavailable" for f in result.findings)
            ):
                observed = result
                break
            await asyncio.sleep(2)
        if observed is None:
            raise AssertionError("failed pod and deployment not detected")
        kubectl("-n", NAMESPACE, "delete", "deployment", "broken", "--wait=true")
        kubectl(
            "-n",
            NAMESPACE,
            "create",
            "deployment",
            "healthy",
            "--image=busybox:1.37.0",
            "--",
            "/bin/sleep",
            "3600",
        )
        subprocess.run(
            [
                "kubectl",
                "--kubeconfig",
                os.environ["KUBECONFIG"],
                "-n",
                NAMESPACE,
                "rollout",
                "status",
                "deployment/healthy",
                "--timeout=90s",
            ],
            check=True,
            timeout=100,
        )
        healthy_data = await live("kubernetes")
        healthy_data["items"] = [
            i
            for i in healthy_data["items"]
            if i["kind"] == "Node" or i["metadata"].get("namespace") == NAMESPACE
        ]
        healthy = analyze("kubernetes", healthy_data)
        if healthy.status != "healthy":
            raise AssertionError("healthy deployment did not validate")
        report = {
            "scope": "disposable kind cluster; failed workload diagnosed, no cluster remediation",
            "failure": observed.model_dump(),
            "healthy": healthy.model_dump(),
            "nodes_collected": sum(i["kind"] == "Node" for i in data["items"]),
        }
        Path("docs/kubernetes-validation.json").write_text(json.dumps(report, indent=2) + "\n")
        print("Kubernetes failed pod and deployment detected; node conditions collected")
    finally:
        kubectl("delete", "namespace", NAMESPACE, "--wait=false")


if __name__ == "__main__":
    asyncio.run(validate())
