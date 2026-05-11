# US-17: Scalability Testing

**Phase:** 3 — Marketplace Generalisation
**Reference:** [design-doc.md §15 Scalability](../design-doc.md#15-evaluation-metrics)

## Story
As a **researcher**, I want measured evidence that the platform handles growing participant counts so that the scalability claim in the paper is empirically backed.

## Acceptance Criteria
- AC1: A load-test harness can spin up `N` stub A2A Remote Agents that complete a full `sprint_planning_v1` session.
- AC2: Load tests are run at `N ∈ {5, 10, 25, 50}` concurrent participants in a single session.
- AC3: For each `N`, the harness captures end-to-end session duration, P50/P95/P99 task round-trip latency, and platform CPU/memory peak.
- AC4: Sessions complete successfully (status `COMPLETED`) at every tested `N` without dropped tasks.
- AC5: Multi-session concurrency is also tested: 10 simultaneous sessions each with 10 participants — no cross-session state leakage in audit logs.
- AC6: Results are summarised in a markdown report with a latency-vs-N chart, committed under `docs/eval/scalability.md`.

## Out of Scope
- Production-grade autoscaling configuration.
- Sustained multi-day soak testing.
- Network failure / chaos engineering.
- Cost analysis or pricing model.
- Geographic / multi-region deployment.
