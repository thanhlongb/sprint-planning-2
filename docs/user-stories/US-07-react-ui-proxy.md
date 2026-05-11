# US-07: React UI Human Proxy

**Phase:** 1 — A2A Baseline  
**Reference:** [design-doc.md §10](../design-doc.md#10-human-participation)

## Story
As a **human participant**, I want to join a session via a browser and interact through a UI that fulfils the A2A contract on my behalf, so that I participate symmetrically with AI agents.

## Acceptance Criteria
- [x] AC1: The React UI hosts an A2A-compliant proxy endpoint per active human session.
- [x] AC2: Visiting `join_url` shows the session lobby with sprint goal, declared participants, and current waiting status.
- [x] AC3: Human selects their declared role on join; the proxy submits `POST /session/{session_id}/join` with `{ name, role }`.
- [x] AC4: UI renders the appropriate component per inbound task type per [§10.3](../design-doc.md#103-ui-task-mapping):
  - `session_invite` → lobby
  - `session_ready` → start screen
  - `present_backlog` → read-only list (PO only)
  - `vote` → draggable dot voting interface
  - `assign_opportunity` → accept/decline card
  - `acknowledge_assignment` → toast notification
  - `confirm` → summary with confirm/reject
- [x] AC5: UI translates each interaction into a valid A2A task response and submits it to the platform.
- [x] AC6: Late or missed human responses fall back to the orchestrator's phase timeout — no special-casing for humans.
- [x] AC7: Proxy holds the SSE / connection open while the human's tab is active; closing the tab does not crash the session.

## Out of Scope
- Mobile-native client.
- Offline / reconnection recovery for humans who close their browser.
- Authentication (no login system in Phase 1 — anyone with the `join_url` can join).
- Push notifications / email alerts when a task arrives.
- Internationalisation / accessibility audit beyond default React component behaviour.
