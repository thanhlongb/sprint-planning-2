# US-19: Human-AI User Study

**Phase:** 4 — Evaluation & Paper
**Reference:** [design-doc.md §14 Phase 4](../design-doc.md#phase-4-evaluation--paper-weeks-78), [§15](../design-doc.md#15-evaluation-metrics)

## Story
As a **researcher**, I want to run a structured user study with 15–16 participants so that I can collect empirical data on human-AI interaction quality in mixed planning sessions.

## Acceptance Criteria
- AC1: A study protocol is written and ethics-approved (or covered by an existing approval), including consent form, task script, and debrief.
- AC2: 15–16 participants are recruited; demographic and experience data are recorded.
- AC3: Each participant runs at least one full planning session as a `DEVELOPER` or `SCRUM_MASTER` alongside reference AI agents.
- AC4: Sessions cover at least two different templates (e.g. `sprint_planning_v1` and `delegation_only`).
- AC5: Each session ends with a post-session Likert-scale survey on: perceived usefulness, trust, fairness of assignment, clarity of process.
- AC6: A short semi-structured interview (~10 min) is conducted with a subset of participants and recorded with consent.
- AC7: All raw data is anonymised and stored alongside the corresponding session audit log ID for cross-reference.

## Out of Scope
- Cross-cultural comparison studies.
- Longitudinal study across multiple sprints per participant.
- Compensation / IRB negotiation specifics (handled outside this story).
- Comparison against a non-platform baseline (e.g. plain Zoom planning) — single-arm study only.
- Statistical power analysis for `N > 16`.
