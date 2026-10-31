# Release 0.1.0

Source: [jayekwere/opspilot](https://github.com/jayekwere/opspilot). Local checks and hosted verification have passed. See [verification evidence](verification.md) for the recorded commit, workflow result, exact test counts, and scope. Release availability is shown on the [GitHub releases page](https://github.com/jayekwere/opspilot/releases).

## Included

Ten operational diagnostic analyzers and collectors; strict schemas; authenticated API and CLI; React operations console; durable run history; bounded evidence collection; role-based permissions; independent expiring approvals; disposable service and security recovery; verification and safe replay; audit events; toil measurements with explicit baselines; reproducible fixtures; Docker environments; Kubernetes lab validator; tests and CI configuration.

## Release procedure

1. Run `make check test build demo benchmark`, `npm run test:e2e`, and `make container` in a clean checkout with the pinned dependency locks.
2. Run dependency audits and Bandit. Review any findings, scope exceptions, or skipped tests. Refresh schemas when contracts change.
3. Review screenshots, demo outcomes, benchmark limitations, Kubernetes evidence, and SECURITY.md. Confirm that evidence contains only lab inputs.
4. Commit the source and evidence. Publish to `jayekwere/opspilot` once GitHub authentication is available. Push the main branch and require the Verify OpsPilot check before merging future changes.
5. Wait for hosted verification to pass. Review the actual run before claiming verified CI.
6. Tag `v0.1.0` only after release review. The tag workflow repeats verification before publishing the runtime image to GHCR. GitHub organization or account package policy may require additional configuration; no published image is claimed yet.

## Known limits

One process, one workspace, one worker. Fixed diagnostic destinations and bounded inventories. Provider integrations require separately installed trusted tools and read-only credentials. Security configuration analysis is conservative file-level analysis. Remediation is limited to disposable lab objects. Evidence redaction is pattern-based. SQLite audit chains are not protected from a host administrator. Remote production deployment needs stronger identity, TLS, audit export, durable workers, and additional operational review.

The Starlette test client currently emits an upstream deprecation warning for its HTTPX integration. Tests pass, but the warning is retained in the evidence rather than suppressed. There is no human productivity benchmark or demonstrated execution speedup in the committed lab comparison.
