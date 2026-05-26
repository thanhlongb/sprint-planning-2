# US-32: Discussion Phase Handler

**Phase:** 2b — New Workflow (Post-May 25 Pivot)
**Reference:** [new-workflow-implementation.md](../plans/new-workflow-implementation.md), existing `comm_bus.py` infrastructure

## Story
As the **platform**, I want a shared discussion handler used by both recommendation and assignment phases so that participants can refine task lists and negotiate assignments through structured messages.

## Acceptance Criteria
- [ ] AC1: Handler lives in `phase_orchestrator.py` as `_handle_discussion(session, slots, context, allowed_actions, timeout)`.
- [ ] AC2: On entry, broadcasts current state via comm bus: recommendation list (with scores) or assignment map.
- [ ] AC3: Subscribes to the session comm channel and enters a message-processing loop.
- [ ] AC4: Validates incoming messages against `allowed_actions` for the current `context` — rejects unknown action types.
- [ ] AC5: **Recommendation context:** `add_item` appends to working list (recalculates capacity), `remove_item` removes, `modify_item` updates fields.
- [ ] AC6: **Assignment context:** `volunteer` claims an item for a participant, `object` contests an existing assignment with reason, `reassign` proposes moving an item between participants.
- [ ] AC7: After each accepted message, platform recalculates (recommendation: re-sort; assignment: re-match) and broadcasts an update.
- [ ] AC8: Loop exits on: (a) timeout with no activity, (b) all items assigned with no objections (assignment context only), or (c) PO signals advance.
- [ ] AC9: Round count tracked in `session.context` (`recommendation_rounds` or `assignment_rounds`), incremented per state change.
- [ ] AC10: Final state returned to the orchestrator for persistence.

## Out of Scope
- Free-form natural language message parsing.
- Conflict resolution beyond simple last-write-wins.
- Real-time UI updates (existing comm bus handles broadcast).
