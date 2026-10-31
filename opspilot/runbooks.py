"""Ten diagnostic analyzers, with explicit fixture and live collection modes."""

import asyncio
import json
import os
import socket
import ssl
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from opspilot.lab import Lab
from opspilot.models import Finding, Request, Result
from opspilot.runner import command, job_steps

DESCRIPTIONS = {
    "performance": "CPU load, available memory, and pressure",
    "filesystem": "Capacity, inode exhaustion, and read-only mounts",
    "service": "Service health and controlled lab recovery",
    "network": "DNS resolution and TCP reachability",
    "tls": "Trusted TLS handshake, hostname, and certificate lifetime",
    "kubernetes": "Pod, node, and deployment conditions",
    "pipeline": "GitHub Actions conclusions and failure categories",
    "logs": "Bounded error classification and sanitized evidence",
    "cloud": "EC2 instance health and configuration posture",
    "security": "SSH configuration and sensitive-file permissions",
}


def fixture(book: str, scenario: str) -> dict[str, Any]:
    bad = scenario == "failure"
    fixtures: dict[str, dict[str, Any]] = {
        "performance": {
            "load_per_cpu": 2.4 if bad else 0.1,
            "available_memory_pct": 4 if bad else 60,
            "pressure_avg10": 35 if bad else 0,
        },
        "filesystem": {"used_pct": 96 if bad else 30, "inode_used_pct": 99 if bad else 20, "read_only": bad},
        "service": {"http_status": 503 if bad else 200},
        "network": {"addresses": ["192.0.2.10"], "dns_ok": not bad, "tcp_ok": not bad},
        "tls": {"trusted": not bad, "days_remaining": 3 if bad else 90, "hostname_valid": not bad},
        "kubernetes": {
            "items": [
                {
                    "kind": "Pod",
                    "metadata": {"name": "api"},
                    "status": {
                        "phase": "Running",
                        "containerStatuses": [
                            {
                                "ready": not bad,
                                "state": {"waiting": {"reason": "CrashLoopBackOff"}}
                                if bad
                                else {"running": {}},
                            }
                        ],
                    },
                },
                {
                    "kind": "Node",
                    "metadata": {"name": "worker"},
                    "status": {"conditions": [{"type": "Ready", "status": "False" if bad else "True"}]},
                },
                {
                    "kind": "Deployment",
                    "metadata": {"name": "api"},
                    "spec": {"replicas": 2},
                    "status": {"availableReplicas": 0 if bad else 2},
                },
            ]
        },
        "pipeline": {
            "runs": [{"name": "tests", "status": "completed", "conclusion": "failure" if bad else "success"}],
            "log_excerpt": "pytest: AssertionError" if bad else "completed",
        },
        "logs": {
            "text": "ERROR database connection timeout\nFATAL out of memory\nAuthorization: Bearer secret-value"
            if bad
            else "INFO request completed"
        },
        "cloud": {
            "InstanceStatuses": [
                {
                    "InstanceId": "i-lab",
                    "InstanceState": {"Name": "running"},
                    "SystemStatus": {"Status": "impaired" if bad else "ok"},
                    "InstanceStatus": {"Status": "ok"},
                }
            ],
            "configuration": {"encrypted": not bad, "public_ingress": bad},
        },
        "security": {
            "permit_root_login": "yes" if bad else "no",
            "password_authentication": "yes" if bad else "no",
            "sensitive_mode": 0o644 if bad else 0o600,
        },
    }
    return fixtures[book]


def analyze(book: str, data: dict[str, Any]) -> Result:
    findings: list[Finding] = []

    def add(code: str, summary: str, recommendation: str, critical: bool = False) -> None:
        findings.append(
            Finding(
                code=code,
                severity="critical" if critical else "warning",
                summary=summary,
                recommendation=recommendation,
            )
        )

    if book == "performance":
        if data["load_per_cpu"] > 1.5:
            add(
                "cpu_pressure",
                "Sustained load exceeds CPU capacity",
                "Inspect CPU consumers and I/O wait before scaling",
            )
        if data["available_memory_pct"] < 10:
            add("memory_pressure", "Available memory below 10%", "Inspect working sets and OOM events", True)
        if data.get("pressure_avg10", 0) > 20:
            add(
                "stall_pressure",
                "Linux pressure stalls exceed 20%",
                "Correlate CPU, memory, and I/O pressure",
            )
    elif book == "filesystem":
        if data["used_pct"] >= 90:
            add(
                "disk_capacity",
                "Filesystem capacity at or above 90%",
                "Review retention and largest directories; do not delete automatically",
            )
        if data["inode_used_pct"] >= 90:
            add(
                "inode_exhaustion",
                "Inode usage at or above 90%",
                "Inspect small-file producers and retention",
                True,
            )
        if data["read_only"]:
            add(
                "read_only_mount",
                "Filesystem is mounted read-only",
                "Review kernel and device errors before remounting",
                True,
            )
    elif book == "service":
        if data.get("http_status") != 200 and data.get("active") != "active":
            add(
                "service_unhealthy",
                "Service health check failed",
                "Request independent approval for disposable lab recovery",
                True,
            )
    elif book == "network":
        if not data["dns_ok"]:
            add(
                "dns_failure",
                "DNS resolution failed",
                "Inspect resolver configuration and authoritative records",
            )
        if not data["tcp_ok"]:
            add(
                "connectivity_failure",
                "TCP connection failed",
                "Inspect routes, listener, and firewall policy",
            )
    elif book == "tls":
        if not data["trusted"] or not data["hostname_valid"]:
            add(
                "tls_validation",
                "Certificate trust or hostname validation failed",
                "Replace certificate or repair the chain; retain verification",
                True,
            )
        if data["days_remaining"] < 30:
            add(
                "tls_expiry",
                "Certificate expires in fewer than 30 days",
                "Renew certificate and verify deployment",
            )
    elif book == "kubernetes":
        for item in data["items"]:
            kind, status = item.get("kind"), item.get("status", {})
            if kind == "Pod":
                for container in status.get("containerStatuses", []):
                    if not container.get("ready"):
                        reason = container.get("state", {}).get("waiting", {}).get("reason", "NotReady")
                        add(
                            "pod_not_ready",
                            f"Pod container is not ready: {reason}",
                            "Inspect events, previous logs, probes, and resource limits",
                        )
                if status.get("phase") in ("Failed", "Pending"):
                    add(
                        "pod_phase",
                        "Pod is failed or pending",
                        "Inspect scheduling events and volume bindings",
                    )
            elif kind == "Node":
                conditions = {c["type"]: c["status"] for c in status.get("conditions", [])}
                if conditions.get("Ready") != "True" or any(
                    conditions.get(k) == "True" for k in ("MemoryPressure", "DiskPressure", "PIDPressure")
                ):
                    add(
                        "node_unhealthy",
                        "Node readiness or pressure condition failed",
                        "Inspect kubelet, capacity, and node events",
                        True,
                    )
            elif kind == "Deployment" and status.get("availableReplicas", 0) < item.get("spec", {}).get(
                "replicas", 1
            ):
                add(
                    "deployment_unavailable",
                    "Available replicas below desired count",
                    "Inspect rollout conditions and failing pods",
                )
    elif book == "pipeline":
        for run in data["runs"]:
            if run.get("conclusion") in ("failure", "timed_out", "startup_failure", "action_required"):
                add(
                    "pipeline_failure",
                    f"Workflow conclusion: {run['conclusion']}",
                    "Inspect failed job steps and reproduce using the committed dependency lock",
                )
        for job in data.get("jobs", []):
            for step in job.get("steps", []):
                if step.get("conclusion") == "failure":
                    add(
                        "job_step_failure",
                        f"Failed job step: {step.get('name', 'unknown')}",
                        "Inspect this step's logs and reproduce its command in a disposable runner",
                    )
        excerpt = data.get("log_excerpt", "").lower()
        for marker, code in [
            ("assertionerror", "test_failure"),
            ("no space left", "runner_capacity"),
            ("permission denied", "ci_permission"),
            ("timed out", "ci_timeout"),
        ]:
            if marker in excerpt:
                add(
                    code,
                    f"Job evidence matches {code}",
                    "Review matching job evidence and isolate the failing step",
                )
    elif book == "logs":
        text = data["text"].lower()
        for marker, code in [
            ("error", "error_events"),
            ("fatal", "fatal_events"),
            ("timeout", "timeout_events"),
            ("out of memory", "oom_events"),
        ]:
            count = text.count(marker)
            if count:
                add(
                    code,
                    f"{count} matching {marker} event(s)",
                    "Correlate timestamps with service and resource evidence",
                )
    elif book == "cloud":
        for instance in data["InstanceStatuses"]:
            if instance.get("InstanceState", {}).get("Name") != "running" or any(
                instance.get(k, {}).get("Status") != "ok" for k in ("SystemStatus", "InstanceStatus")
            ):
                add(
                    "ec2_health",
                    "EC2 instance or system status is unhealthy",
                    "Inspect provider status checks and recovery options",
                    True,
                )
        config = data.get("configuration", {})
        if config.get("encrypted") is False:
            add(
                "unencrypted_storage",
                "Unencrypted storage configuration",
                "Plan encrypted replacement through infrastructure review",
            )
        if config.get("public_ingress"):
            add(
                "public_ingress",
                "Unrestricted ingress configuration",
                "Review security group exposure and approved source ranges",
            )
    elif book == "security":
        if data.get("effective_policy_unresolved"):
            add(
                "ssh_policy_unresolved",
                "SSH includes, Match blocks, or duplicate directives need effective-policy review",
                "Validate effective configuration with an approved sshd policy review",
            )
        if data["permit_root_login"] != "no":
            add(
                "ssh_root_login",
                "Root SSH login is not explicitly disabled",
                "Review an approved SSH configuration change",
            )
        if data["password_authentication"] != "no":
            add(
                "ssh_password",
                "SSH password authentication is not explicitly disabled",
                "Validate key access before an approved configuration change",
            )
        if data["sensitive_mode"] & 0o077:
            add(
                "sensitive_permissions",
                "Sensitive file permits group or other access",
                "Review ownership and approved permission correction",
                True,
            )
    return Result(status="finding" if findings else "healthy", findings=findings, evidence=data)


async def collect(request: Request, lab: Lab) -> Result:
    try:
        if request.target == "fixture":
            if request.scenario == "unavailable":
                raise OSError("simulated offline integration")
            data = fixture(request.runbook, request.scenario)
        elif request.target == "lab":
            if request.runbook == "service":
                async with httpx.AsyncClient(timeout=2, trust_env=False) as client:
                    response = await client.get(lab.url)
                data = {"http_status": response.status_code, "generation": lab.generation}
            elif request.runbook == "security":
                config = dict(line.lower().split() for line in lab.config.read_text().splitlines())
                data = {
                    "permit_root_login": config["permitrootlogin"],
                    "password_authentication": config["passwordauthentication"],
                    "sensitive_mode": lab.config.stat().st_mode & 0o777,
                    "generation": lab.generation,
                }
            else:
                raise ValueError("lab supports service and security only")
        else:
            data = await live(request.runbook)
        return analyze(request.runbook, data)
    except (OSError, TimeoutError, httpx.HTTPError, ValueError, KeyError, TypeError) as error:
        return Result(
            status="unavailable",
            findings=[],
            evidence={
                "error_type": type(error).__name__,
                "message": "Collection unavailable or unsupported; inspect integration configuration",
            },
        )


def read_configuration(path: Path) -> str:
    """Bound allocation before parsing even a misconfigured oversized host file."""
    with path.open(encoding="utf-8") as stream:
        text = stream.read(32769)
    if len(text) > 32768:
        raise ValueError("configuration exceeds collection limit")
    return text


async def live(book: str) -> dict[str, Any]:
    if book == "performance":
        mem = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            mem[key] = int(value.strip().split()[0])
        pressure = 0.0
        pressure_file = Path("/proc/pressure/cpu")
        if pressure_file.exists():
            values = pressure_file.read_text().splitlines()[0].split()
            pressure = float(next(v.split("=", 1)[1] for v in values if v.startswith("avg10=")))
        return {
            "pressure_avg10": pressure,
            "load_per_cpu": os.getloadavg()[0] / (os.cpu_count() or 1),
            "available_memory_pct": 100 * mem["MemAvailable"] / mem["MemTotal"],
        }
    if book == "filesystem":
        stats = os.statvfs("/")
        return {
            "used_pct": 100 * (stats.f_blocks - stats.f_bavail) / max(stats.f_blocks, 1),
            "inode_used_pct": 100 * (stats.f_files - stats.f_favail) / max(stats.f_files, 1),
            "read_only": bool(stats.f_flag & os.ST_RDONLY),
        }
    if book == "network":
        # Fixed public diagnostic destination prevents user-controlled SSRF.
        loop = asyncio.get_running_loop()
        try:
            addresses = await asyncio.wait_for(
                loop.getaddrinfo("example.com", 443, type=socket.SOCK_STREAM), 3
            )
        except socket.gaierror:
            return {"addresses": [], "dns_ok": False, "tcp_ok": False}
        tcp = True
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection("example.com", 443), 3)
            writer.close()
            await writer.wait_closed()
        except (OSError, TimeoutError):
            tcp = False
        return {
            "addresses": sorted({str(a[4][0]) for a in addresses}),
            "dns_ok": bool(addresses),
            "tcp_ok": tcp,
        }
    if book == "tls":
        context = ssl.create_default_context()
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection("example.com", 443, ssl=context, server_hostname="example.com"), 5
            )
            certificate = writer.get_extra_info("ssl_object").getpeercert()
            writer.close()
            await writer.wait_closed()
            expiry = ssl.cert_time_to_seconds(certificate["notAfter"])
            return {
                "trusted": True,
                "hostname_valid": True,
                "days_remaining": (expiry - time.time()) / 86400,
                "expires": datetime.fromtimestamp(expiry, UTC).isoformat(),
            }
        except ssl.SSLCertVerificationError:
            return {"trusted": False, "hostname_valid": False, "days_remaining": 0}
    if book == "security":
        text = read_configuration(Path("/etc/ssh/sshd_config"))
        config: dict[str, str] = {}
        unresolved = False
        for line in text.splitlines():
            parts = line.split("#", 1)[0].split()
            if parts and parts[0].lower() in ("include", "match"):
                unresolved = True
            if len(parts) == 2:
                key = parts[0].lower()
                unresolved |= key in config
                config.setdefault(key, parts[1].lower())
        return {
            "effective_policy_unresolved": unresolved,
            "permit_root_login": config.get("permitrootlogin", "unknown"),
            "password_authentication": config.get("passwordauthentication", "unknown"),
            "sensitive_mode": Path("/etc/shadow").stat().st_mode & 0o777,
        }
    output = await command(book)
    if output.code or output.truncated:
        raise OSError("collector failed or exceeded evidence limit")
    if book == "service":
        return {"active": "active" if "ActiveState=active" in output.text else "inactive"}
    if book == "logs":
        return {"text": output.text}
    parsed = json.loads(output.text)
    if book == "kubernetes":
        # Do not retain workload specs: they can contain inline credentials.
        items = []
        for item in parsed["items"]:
            status = item.get("status", {})
            kind = item.get("kind")
            if kind == "Pod":
                projected = {
                    "phase": status.get("phase"),
                    "containerStatuses": [
                        {
                            "ready": c.get("ready"),
                            "restartCount": c.get("restartCount", 0),
                            "state": {
                                "waiting": {
                                    "reason": c.get("state", {}).get("waiting", {}).get("reason", "NotReady")
                                }
                            },
                        }
                        for c in status.get("containerStatuses", [])
                    ],
                }
            elif kind == "Node":
                projected = {
                    "conditions": [
                        {"type": c.get("type"), "status": c.get("status")}
                        for c in status.get("conditions", [])
                    ]
                }
            else:
                projected = {"availableReplicas": status.get("availableReplicas", 0)}
            items.append(
                {
                    "kind": kind,
                    "metadata": {
                        "name": item.get("metadata", {}).get("name"),
                        "namespace": item.get("metadata", {}).get("namespace"),
                    },
                    "spec": {"replicas": item.get("spec", {}).get("replicas", 1)},
                    "status": projected,
                }
            )
        return {"items": items}
    if book == "pipeline":
        data = {"runs": parsed}
        failed = next((r for r in parsed if r.get("conclusion") == "failure" and "databaseId" in r), None)
        if failed:
            steps = await job_steps(failed["databaseId"])
            if not steps.code and not steps.truncated:
                data.update(json.loads(steps.text))
        return data
    if book == "cloud":
        volumes, groups = await asyncio.gather(command("cloud_volumes"), command("cloud_groups"))
        if volumes.code or groups.code or volumes.truncated or groups.truncated:
            raise OSError("configuration collection incomplete")
        volume_data = json.loads(volumes.text).get("Volumes", [])
        group_data = json.loads(groups.text).get("SecurityGroups", [])
        parsed["configuration"] = {
            "encrypted": all(v.get("Encrypted", False) for v in volume_data),
            "public_ingress": any(
                ip.get("CidrIp") == "0.0.0.0/0" or ip.get("CidrIpv6") == "::/0"
                for group in group_data
                for permission in group.get("IpPermissions", [])
                for ip in permission.get("IpRanges", []) + permission.get("Ipv6Ranges", [])
            ),
        }
    return dict(parsed)
