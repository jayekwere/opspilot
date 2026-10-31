# Contributing

Use Python 3.14 and Node 24 or later. Run `make install`, then `make check test build demo benchmark`, `npm run test:e2e`, and `make container`. Browser tests require `npx playwright install chromium`. They use loopback port 18091 by default; set `OPSPILOT_TEST_PORT` to another free port if needed. Docker and loopback sockets must be available for integration checks.

New runbooks need a strict input contract, a bounded read-only collector, an analyzer, recommendations, healthy/failing/unavailable fixtures, and tests for malformed or malicious input. Keep provider APIs mockable. Do not add arbitrary shell commands, user-controlled network destinations, or host remediation without a separately designed trust boundary.

Use clear commits and describe behavior, validation, and limitations in pull requests. Never commit credentials, SQLite state, actual provider evidence, or generated dependency directories. Lab reports and screenshots may be committed only when inputs are synthetic. Changes to workflow permissions or remediation semantics require explicit reviewer attention.
