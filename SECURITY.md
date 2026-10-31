# Security policy

OpsPilot 0.1 is a single-process local operations lab. It implements an authenticated API, independent remediation approval, and bounded diagnostic execution. It is not a production identity provider, remote privileged agent, or fleet orchestrator.

## Trust and permissions

The server operator configures distinct identities through `OPSPILOT_IDENTITIES`. Tokens must have at least 32 characters; use the credential generator for random tokens. Tokens are hashed in memory and compared with constant-time comparison. The server environment remains trusted. There is no self-registration or token-issuing endpoint. Rotate credentials by restarting with a new identity map. Roles are deny by default: `read`, `diagnose`, `approve`, and `execute`.

Operators may request remediation for their own lab findings. A different named identity must approve. The approver cannot execute the approved change. Approvals expire after ten minutes and bind to a specific lab generation. Restarting invalidates pending, approved, or executing approvals. Completed remediation is idempotent. Failed or interrupted remediation is not retried automatically. Diagnose again after a new failure. Service and SSH-configuration repairs affect only objects owned by the disposable lab. Host recovery and privileged configuration changes are unsupported and cannot be selected through the API.

The CLI is an authenticated API client. Diagnostic names, targets, and scenarios use strict enums. The public input contract contains no command, executable, arbitrary path, URL, or host field. External collectors use fixed argument arrays with no shell. Executables resolve only from fixed system directories. Trusted administrators must control those directories and installed tools.

## Credentials and evidence

Provider credentials are inherited only from a small environment allowlist. AWS uses explicit environment credentials and region; instance metadata access is disabled. GitHub uses `GH_TOKEN` and `GH_REPO`. Kubernetes uses an explicitly trusted `KUBECONFIG`; kubeconfig exec plugins run as the operator and must be reviewed before use. Do not accept kubeconfigs from users or mount the Docker socket into the app.

SQLite state uses a mode-0700 directory and mode-0600 database. Kubernetes evidence projects only names and diagnostic status, excluding pod environment and workload specs. Known secret keys and common inline token/password patterns are redacted before persistence. Pattern redaction is not a DLP guarantee: logs can contain unrecognized secrets or personal data. Limit collection to authorized systems. Do not publish production state or run reports. The browser keeps bearer tokens in memory, not browser storage. Authentication headers and raw output are not written to structured logs.

Audit entries use an application hash chain. This detects accidental edits when checked against a trusted root; it is not cryptographic protection against a host administrator rewriting the entire database. Export audit records to an independently protected sink for production use. API read access includes the shared workspace history, so identities must belong to the same trust domain.

## Resource and transport limits

One diagnostic or remediation executes at a time. Eight HTTP requests may enter concurrently; excess work receives 429. Collectors have an eight-second process timeout and 32 KiB retained output, or 256 KiB for Kubernetes. Pipe draining continues without retaining overflow. Diagnostic collection has a twelve-second overall timeout. Process groups are terminated, including descendants. Evidence strings and arrays are bounded. Requests are limited to 8 KiB, runs to 1,000, and audit entries to 10,000. Archive state offline when capacity is reached. The dashboard and metrics show the most recent 200 runs. SQLite writes fail closed on unavailable storage.

The API binds loopback by default. Container binding uses all container interfaces but Compose publishes only loopback. Host and Origin checks, a restrictive CSP, no CORS grant, and bearer authentication protect local use. TLS termination, centralized identity, tenant isolation, distributed rate limits, external audit export, and durable job queues are required before remote production exposure. Only one API worker is supported.

## Reporting

Report a vulnerability privately through the repository owner's GitHub profile. Include the affected version, reproduction steps, and sanitized evidence. Never put real credentials or production logs in a public issue. This repository has no established private response SLA.
