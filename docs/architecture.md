# Architecture and operational workflow

```mermaid
flowchart LR
    CLI[Python CLI] --> API[FastAPI boundary]
    UI[React TypeScript console] --> API
    API --> ID[Configured bearer identities]
    ID --> RBAC[Deny by default role checks]
    RBAC --> SVC[Single process workflow service]
    SVC --> DB[(Private SQLite run and approval store)]
    SVC --> AUDIT[Hash-chained audit events]
    SVC --> DIAG[Ten diagnostic analyzers]
    DIAG --> FIX[Explicit fixture inputs]
    DIAG --> LIVE[Bounded local and provider collectors]
    DIAG --> LAB[Disposable HTTP and configuration lab]
    SVC --> APPROVE[Independent approval and expiry check]
    APPROVE --> GEN[Lab generation check]
    GEN --> REPAIR[Allowlisted lab repair]
    REPAIR --> VERIFY[Recollect and verify]
    VERIFY --> DB
    DB --> METRICS[Toil and repeatability calculations]
    METRICS --> UI
```

```mermaid
sequenceDiagram
    participant Operator
    participant API
    participant Lab
    participant Approver
    participant Store
    Operator->>API: Diagnose service with idempotency key
    API->>Lab: Read health endpoint
    Lab-->>API: HTTP 503
    API->>Store: Evidence, finding, timing, audit
    Operator->>API: Request recovery
    API->>Store: Pending approval bound to generation
    Approver->>API: Approve with reason
    API->>Store: Check independent identity and expiry
    Operator->>API: Execute approved action
    API->>Lab: Recover only if generation is unchanged
    API->>Lab: Recheck health
    Lab-->>API: HTTP 200
    API->>Store: Final outcome, verification, timing, audit
```

Each diagnosis reserves a durable run before collection. Identical actor and idempotency key return the original record; changing input under the same key returns 409. A crash leaves a reserved run which is marked failed during startup recovery. Startup also invalidates old approvals because the new process owns a fresh lab. Diagnostics report `healthy`, `finding`, `unavailable`, or `failed`. A supported finding is a successful diagnosis, not a healthy system.

The disposable service failure is an intentionally injected HTTP 503, not a claim of reproducing a kernel or hardware fault. Recovery toggles the process-owned service to healthy and confirms HTTP 200. The security lab writes an inert temporary SSH configuration and validates permissions; it never reconfigures the host SSH daemon.

SQLite provides transactional workflow changes. The service supports one process and one worker. It does not implement distributed locks, multi-host remediation, or durable remote workers. These are deliberate scope boundaries, not hidden deployment assumptions.
