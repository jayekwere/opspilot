"""Strict public contracts. No user-provided command or arbitrary file path."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Book(StrEnum):
    performance = "performance"
    filesystem = "filesystem"
    service = "service"
    network = "network"
    tls = "tls"
    kubernetes = "kubernetes"
    pipeline = "pipeline"
    logs = "logs"
    cloud = "cloud"
    security = "security"


class Request(Strict):
    runbook: Literal[
        "performance",
        "filesystem",
        "service",
        "network",
        "tls",
        "kubernetes",
        "pipeline",
        "logs",
        "cloud",
        "security",
    ]
    target: Literal["local", "lab", "fixture"] = "fixture"
    scenario: Literal["healthy", "failure", "unavailable"] = "failure"
    manual_seconds: Annotated[float, Field(ge=0, le=86400)] | None = None
    baseline_source: Annotated[str, Field(max_length=120)] | None = None


class Approval(Strict):
    decision: Literal["approve", "reject"]
    reason: Annotated[str, Field(min_length=8, max_length=300)]


class Finding(Strict):
    code: str
    severity: Literal["info", "warning", "critical"]
    summary: str
    recommendation: str


class Result(Strict):
    status: Literal["healthy", "finding", "unavailable", "failed"]
    findings: list[Finding]
    evidence: dict[str, object]


class Principal(Strict):
    name: str
    roles: list[Literal["diagnose", "approve", "execute", "read"]]
