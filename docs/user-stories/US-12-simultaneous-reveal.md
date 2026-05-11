# US-12: Simultaneous Reveal Voting Buffer

**Phase:** 2 — Template Engine
**Reference:** [design-doc.md §8.3](../design-doc.md#83-simultaneous-reveal)

## Story
As a **participant**, I want my vote held privately until all participants have voted (or time runs out) so that I am not anchored by seeing other participants' votes first.

## Acceptance Criteria
- AC1: During a `VOTE` action, the orchestrator buffers incoming responses privately in memory.
- AC2: No vote is included in the next `session_ctx.phase_history.outcome` until the buffer is released.
- AC3: The buffer is released when either:
  - All required participants have responded, **or**
  - The phase's `duration_limit` is reached.
- AC4: On release, all votes are broadcast simultaneously to all participants.
- AC5: Late votes received after release are discarded with a logged warning.
- AC6: Buffered votes survive a brief platform restart within the same phase (best-effort: persisted to PostgreSQL on receipt).

## Out of Scope
- Anonymous voting (votes still carry `participant_id`).
- Weighted votes by role.
- Multi-round voting (single round per phase).
- Cryptographic commitment / reveal scheme.
