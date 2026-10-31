# Toil measurement methodology

The engine records diagnostic wall time with a monotonic performance counter. This includes collection, parsing, and finding generation. It excludes the final SQLite persistence commit, operator interpretation, independent approval, and remediation. Remediation has its own elapsed time and verified outcome. The demo also records overall workflow wall time.

A completed diagnosis is successful if it returns healthy or a supported finding. Unavailable and failed are operational failures. Findings, failures, and unavailability mark intervention required; this is a need for review, not a measurement of time spent by an operator. The intervention flag is historical and is not cleared by a later recovery.

Repeatability groups identical full request contracts with at least two independent runs and measures the fraction with identical outcome status. It does not claim equivalent evidence, deterministic provider state, or statistical reliability. Idempotent replays do not add runs. Metrics and the dashboard are scoped to the latest 200 records.

Manual execution time is optional and must include a stated source. Baselines may be measured by an operator or explicitly labeled assumptions. Estimated effort avoided is the non-negative difference between supplied manual seconds and measured diagnostic seconds, only for successful diagnoses with a baseline. It is not a measured productivity gain, and it omits intervention, approval, and recovery effort. API responses retain the source so estimates remain reviewable.

## Controlled benchmark

Run `make benchmark`. Twenty trials compare a scripted manual-procedure sequence with the orchestrated diagnostic against a process-owned service returning HTTP 503. The scripted comparator probes the endpoint, reads the response, classifies the supported condition, and writes a small JSON finding. The automated path uses the same failure and generates the OpsPilot result. There are no artificial sleeps or invented operator timings. Raw timings and medians are in `benchmark.json`.

This comparator is code, not a person. The measured tiny scripted procedure is faster than the automated path in the committed lab result. OpsPilot incurs HTTP client setup and orchestration overhead. There is no demonstrated speedup and no measured human effort reduction. The benchmark establishes repeatable behavior and a transparent measurement path. It does not establish organization-wide capacity recovery or workload reduction.

For a real manual comparison, define the same inputs, evidence completeness, and completion criteria; have an operator perform the documented procedure; record their elapsed and intervention time; repeat across a predeclared sample; and supply that measured baseline with its source. Keep failed runs and report variance. Do not extrapolate this local lab to a team's productivity.
