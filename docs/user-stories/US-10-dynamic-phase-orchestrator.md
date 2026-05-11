# US-10: Dynamic Phase Orchestrator

**Phase:** 2 — Template Engine
**Reference:** [design-doc.md §8](../design-doc.md#8-phase-orchestration)

## Story
As the **platform**, I want the Phase Orchestrator to execute any valid Process Template dynamically so that planning behaviour is determined by configuration rather than hard-coded logic.

## Acceptance Criteria
- AC1: Orchestrator iterates phases declared in the template — not a hard-coded list.
- AC2: All four turn-order modes are supported: `ROLE_FIRST`, `ALL_PARALLEL`, `ROUND_ROBIN`, `FACILITATOR_LED`.
- AC3: All three transition modes are supported: `AUTO` (all required responses received), `TIMED` (duration elapsed), `MANUAL` (SCRUM_MASTER advance).
- AC4: Action types `PRESENT_ITEMS`, `VOTE`, `SELECT`, `ASSIGN`, `CONFIRM` are dispatched to dedicated action handlers via a registry pattern.
- AC5: Assignment action honours its `strategy`, `fallback`, `conflict_resolution`, and `timeout_ms` parameters from the template.
- AC6: Confirmation action honours `requires_unanimous` and `quorum` parameters.
- AC7: An unrecognised `action.type` causes the session to `ABORT` with a clear error reason, not silently skip.
- AC8: Running the baseline `sprint_planning_v1` template via the dynamic orchestrator produces identical outputs to the hard-coded baseline from [US-04](US-04-phase-orchestrator-baseline.md).

## Out of Scope
- New action types beyond those listed in §7.1.
- Branching / conditional phase flows.
- Parallel phase execution (phases remain strictly sequential).
- Mid-session template swap.
- Custom user-defined action handler plugins.
