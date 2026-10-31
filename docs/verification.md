# Verification evidence

Verified locally on October 31, 2026. Host: macOS ARM64, Python 3.14.6, Node 26.3.0, Docker 29.5.3. Linux validation runs in the digest-pinned Python 3.14 container. These are local results, not hosted GitHub Actions results.

| Check | Result | Evidence |
| --- | --- | --- |
| Python unit, integration, adversarial, and workflow tests | 97 passed; 1 Linux-only test skipped on macOS; 87.23% branch-aware coverage | [Local verification](local-verification.txt) |
| Python lint, formatting, and typechecking | Passed | [Local verification](local-verification.txt) |
| TypeScript lint, formatting, and typechecking | Passed | [Local verification](local-verification.txt) |
| Production React build | Passed | [Local verification](local-verification.txt) |
| Browser end-to-end scenarios | 3 passed: console/evidence/mobile, independent approval/recovery, rejected authentication | [Browser results](browser-tests.txt) |
| Linux Docker suite | 98 passed, including real Linux `/proc` integration | [Container verification](container-verification.txt) |
| Restricted runtime smoke | Authentication, unapproved execution denial, approved recovery, dashboard serving | [Structured smoke report](container-smoke.json) |
| Service troubleshooting demo | Detection, evidence, recommendation, approval, recovery, verification, safe replay, stale-generation failure | [Demo](demo-result.json) |
| Security remediation | Temporary configuration and permission repair, followed by healthy recollection | Python integration test `test_security_recovery` |
| Actual TLS validation | Trusted short-lived local certificate accepted; untrusted certificate rejected | Python integration tests in `tests/test_tls.py` |
| Kubernetes lab | Restarting pod and unavailable deployment detected; healthy deployment validated; node conditions collected | [Structured Kubernetes evidence](kubernetes-validation.json), [output](kubernetes-tests.txt) |
| Kubernetes cleanup | Disposable cluster removed | [Cleanup](kubernetes-cleanup.txt) |
| Static security analysis | No medium or high severity Bandit findings | [Bandit JSON](bandit.json) |
| Python runtime dependency audit | No known vulnerabilities at check time | [Audit JSON](pip-audit.json) |
| JavaScript dependency audit | No known vulnerabilities at check time | [Audit JSON](npm-audit.json) |
| Dependency integrity | Exact npm lock and Python locks with distribution SHA-256 hashes; hash-verified installation succeeded | `package-lock.json`, `requirements.lock`, `requirements-dev.lock` |
| CI configuration | YAML parsed; action commit pins, permissions, tag trigger, and release dependency checked locally | `.github/workflows/verify.yml` |

The Python suite exercises every runbook in healthy, supported-failure, and unavailable modes. It also covers malformed schemas, shell-like input, arbitrary target rejection, read-only authorization, missing executables, command timeouts, capture limits, provider command parsing, provider failure, secret redaction, Kubernetes secret exclusion, idempotency conflicts, independent approval, approval expiry, rejection, stale generation, process restart invalidation, private storage permissions, and audit hash consistency.

The test client emits an upstream Starlette/HTTPX deprecation warning. It is recorded, not suppressed. The Linux-only integration is intentionally skipped on macOS and executed in Docker. Provider-specific AWS and GitHub failure analysis is verified through controlled responses and unavailable paths; authenticated production AWS or GitHub API calls were not made. Network and TLS use fixed live destinations; real TLS behavior is verified locally without reliance on an external service.

Screenshots are captured from the real console with synthetic fixture records. They are not production operational data. The benchmark reports scripted comparator and automated wall times, leaving human manual time and human effort avoided null. It establishes no team productivity improvement or execution speedup.

Local checks are complete. Repository publication and hosted workflow verification are in progress. No hosted CI result, public release, GHCR image publication, or branch protection change is claimed until the corresponding operation has been verified.
