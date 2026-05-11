# DR-08: Sprint Backlog Output (US-08)

## Context
When a sprint planning session completes (i.e. transitions to `COMPLETED`), the platform must construct a canonical `sprint_backlog` object containing the session's goal, the selected items, and a summary of assignments ("capacity plan"). This backlog needs to be delivered to every participant (agents via A2A, humans via the React UI Proxy).

## Decision
1. **Canonical Build**: We built a `_build_sprint_backlog` function in the Phase Orchestrator that creates a single, immutable dictionary containing only the standardized BacklogItem schema, stripping all internal metadata.
2. **Assignee Name Resolution**: To prevent participants from needing an extra lookup, we enrich each assigned item with its `assignee_name` using the orchestrator's participant slots map.
3. **Capacity Plan**: We compute the `capacity_plan` directly from the `selected_items`, summarizing `item_count` and `total_story_points` per `assignee_id`.
4. **Broadcast Mechanism**: We use `_broadcast_sprint_backlog` right after the session status atomic commit to `COMPLETED`. Delivery failures are logged but do not roll back the session state, ensuring resilience.
5. **UI Proxy Handling**: In the UI proxy, `sprint_backlog` is treated as an informational task. The proxy pushes it to the React UI via SSE, where a new `SprintBacklogView` component renders the final backlog and capacity plan to the human user.

## Consequences
- Guarantees byte-identical content delivered to all participants.
- Complies strictly with the zero-knowledge principle (no internal metadata leaked).
- Human participants get a clean, read-only summary screen upon session completion.
