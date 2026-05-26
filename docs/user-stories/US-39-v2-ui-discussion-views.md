# US-39: v2 Workflow UI — Discussion-Driven Views

**Phase:** 2b — New Workflow (Post-May 25 Pivot)
**Reference:** [new-workflow-implementation.md](../plans/new-workflow-implementation.md), existing `SessionPage.tsx`, `CommunicationFeed.tsx`

## Story
As a **human participant**, I want the UI to support the v2 discussion-driven workflow so that I can see algorithmic recommendations, discuss and refine task lists, negotiate assignments, and confirm the sprint plan.

## Acceptance Criteria
- [ ] AC1: **RecommendationView** (new component) replaces BacklogView + VoteView for v2 sessions. Shows: platform-recommended item list with scores, round counter, add/remove/modify discussion panel.
- [ ] AC2: RecommendationView has an "Add Item" input (title + story points), "Remove" button per item, and inline "Modify" for story points or priority.
- [ ] AC3: RecommendationView sends structured messages (`add_item`, `remove_item`, `modify_item`) via the existing comm bus when the human acts.
- [ ] AC4: RecommendationView listens to `recommendation` and `recommendation_update` comm events and refreshes the displayed list.
- [ ] AC5: **AssignView** (modified) detects v2 context. Shows: algorithmic assignment proposal from `assignment_proposal` event, round counter, volunteer/object/reassign discussion panel.
- [ ] AC6: AssignView sends `volunteer`, `object`, `reassign` structured messages via comm bus.
- [ ] AC7: AssignView listens to `assignment_proposal` and `assignment_update` comm events.
- [ ] AC8: **ConfirmView** (modified) detects v2 context. Shows: final sprint backlog with assignments and convergence metrics. Single "Accept Plan" button. Sends `accept_plan` message. Removes quorum bar.
- [ ] AC9: **SessionPage** detects template version (`sprint_planning_v2`) and routes to the correct view set: LobbyView → RecommendationView → AssignView → ConfirmView.
- [ ] AC10: **CommunicationFeed** already displays discussion messages from the comm bus — verify it renders v2 message types correctly alongside human actions.
- [ ] AC11: **SprintBacklogView** (modified) displays convergence metrics (`recommendation_rounds`, `assignment_rounds`, `retention_pct`) alongside the final backlog.
- [ ] AC12: V1 sessions continue to use the existing views unchanged. Version detection is at the template level in SessionPage.

## Out of Scope
- Real-time collaborative editing (multi-cursor).
- Visual diff of recommendation changes between rounds.
- Participant-specific views (everyone sees the same UI).
