# US-31: Expertise-Based Assignment Algorithm

**Phase:** 2b — New Workflow (Post-May 25 Pivot)
**Reference:** [new-workflow-implementation.md](../plans/new-workflow-implementation.md), May 25 meeting (optimization objective #3: expertise-based task assignment)

## Story
As the **platform**, I want to algorithmically propose task assignments matching items to participants by expertise and capacity so that the assignment discussion starts from a reasonable proposal.

## Acceptance Criteria
- [ ] AC1: Handler lives in `phase_orchestrator.py` as `_handle_generate_assignment()`.
- [ ] AC2: Input: selected items (from recommendation phase), participant list with `capacity.story_points` and `capacity.specialties`.
- [ ] AC3: For each item, filter to participants with remaining capacity ≥ item story_points.
- [ ] AC4: Score each candidate: expertise match (Jaccard of item `labels` ∩ participant `specialties`) + workload balance bonus (prefer participants with more remaining capacity).
- [ ] AC5: Assign each item to highest-scoring candidate. Items with zero eligible candidates are left unassigned.
- [ ] AC6: Output: assignment map `{item_id: participant_id}` broadcast as an `assignment_proposal` comm message.
- [ ] AC7: Remaining capacity tracked per participant across items to prevent overallocation.
- [ ] AC8: Deterministic — same inputs always produce same assignments (no randomness).

## Out of Scope
- Multi-objective optimization beyond expertise + capacity (business value, goal alignment weights).
- Negotiation of contested assignments (handled by the discussion phase).
- Human-specific capacity (hours, seniority) — uses story_points uniformly.
