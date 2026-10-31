# Runbook input and output contracts

Every diagnostic request accepts exactly `runbook`, `target`, `scenario`, `manual_seconds`, and `baseline_source`. Only `runbook` is required. Target defaults to `fixture` in both the API and CLI. Use an explicit target for API clients. Unknown fields and values are rejected. Manual seconds must be a number from 0 to 86,400 and require a source string, up to 120 characters. Scenario is `healthy`, `failure`, or `unavailable` and applies only to fixture collection. Fixture collection never mutates the lab.

Targets are `fixture`, `local`, and, for service and security only, `lab`. A target unsupported by a particular runbook returns `unavailable`. There are no free-form executable, shell, hostname, address, path, cluster-context, namespace, or provider-account fields.

Output contains status, structured findings with code/severity/summary/recommendation, sanitized evidence, wall-clock duration, actor, request, and run ID. Status is healthy, finding, unavailable, or failed. Operational errors, missing binaries, invalid provider responses, unsupported platforms, and offline systems produce unavailable evidence without raw credential-bearing exception messages. Unexpected engine errors produce failed records. A supported finding counts as diagnostic success but requires operator intervention.

| Runbook | Evidence and thresholds | Error behavior and limits |
| --- | --- | --- |
| `performance` | One-minute load divided by CPU count over 1.5; available memory below 10%; CPU PSI avg10 over 20% | Linux `/proc` required. These snapshots guide investigation, not root-cause certainty. CPU pressure is optional when PSI is absent. |
| `filesystem` | Root filesystem usage and inode usage at or above 90%, read-only flag | One fixed filesystem, no recursive directory scanning or automatic deletion. |
| `service` | Local `sshd.service` ActiveState, or lab HTTP health status | Missing systemd or service returns unavailable. Lab 503 supports independently approved recovery; local service changes are unsupported. |
| `network` | Addresses for `example.com`, DNS success, TCP 443 reachability | DNS failure is actionable; timeouts and unsupported resolver errors may return unavailable. Three-second bounded operations. Fixed destination prevents arbitrary network probing. |
| `tls` | Platform CA and hostname validation, expiry timestamp and days remaining | Trust failure is actionable; offline connection returns unavailable. Five-second handshake. Fixed public destination, no private key collection. |
| `kubernetes` | Pod readiness, phase, restart count, waiting reason; node readiness and pressure; desired/available deployment replicas | Requires trusted KUBECONFIG and kubectl read access. Eight-second command timeout, 256 KiB output. Large clusters exceeding the cap return unavailable. Pod specs and environment are excluded from evidence. |
| `pipeline` | Last ten GitHub run conclusions; jobs and steps for the first failed run | Requires `GH_TOKEN` with Actions read permission and `GH_REPO=owner/repo`. No repository checkout or CI execution. Raw production job logs are not downloaded. Fixture excerpts also classify test, permission, timeout, and disk signatures. |
| `logs` | Last 100 error-priority journal entries, case-insensitive signature counts | Requires journal read permission. 32 KiB output, no arbitrary files. Pattern matches are triage signals, not causal attribution. Evidence is sanitized before persistence. |
| `cloud` | Up to 20 instance statuses, volumes, and security groups; encryption and unrestricted IPv4/IPv6 ingress | Requires AWS CLI, explicit environment credentials and region, and EC2 Describe permissions. No changes. Broader IAM, cross-account, network-path, and resource inventory analysis are outside scope. Partial or failed configuration collection returns unavailable. |
| `security` | Literal SSH root-login/password directives and shadow mode; lab temporary config and mode | Conservative file-level validation, not effective sshd policy evaluation. Includes, Match blocks, and duplicate directives trigger an unresolved-policy finding. Distro overrides, ACLs, ownership, and SELinux are not resolved. Local host changes are unsupported. Lab repair writes fixed safe directives and mode 0600 only to the lab-owned file. |

All subprocess arguments are fixed, except a strictly validated positive integer GitHub run ID obtained from the provider. Processes use no shell, a bounded capture buffer, a timeout, and process-group cleanup. A twelve-second overall collection limit bounds combined calls. Provider credentials are inherited only from an explicit environment allowlist and are not API inputs.

## Approval contract

`POST /api/runs/{id}/approval` requires diagnose permission and ownership of a supported lab finding. `POST /api/approvals/{id}/decision` requires approve permission, a different actor, a decision of approve or reject, and a reason of 8 to 300 characters. `POST /api/approvals/{id}/execute` requires execute permission, a current approval, and an actor different from the approver. Approval expires after 600 seconds and is invalidated by process restart or a new lab generation.

Completed execution replays the recorded result. Rejected, expired, interrupted, failed, or stale approvals never trigger an automatic retry. A new diagnosis and independent review are required. State and audit mutations occur transactionally; an executing record is not silently reissued after a crash.

## Repeated monitoring

The CLI can be invoked by an existing trusted scheduler to repeat fixed-target TLS, filesystem, or service checks. Set the operator credential in that scheduler's protected environment, use a read-only identity, and preserve the API run records. OpsPilot does not yet provide an internal distributed scheduler or alert delivery service. An unavailable provider is reported as an operational failure rather than a healthy system.

CLI diagnoses exit 0 for healthy or finding outcomes and exit 2 for unavailable or failed outcomes. Structured JSON evidence is printed in both cases. HTTP authorization and transport errors also return a nonzero process status.
