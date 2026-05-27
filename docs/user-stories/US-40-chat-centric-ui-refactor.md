# US-40: Chat-Centric UI — Discussion as the Core Interaction

**Phase:** 2b — New Workflow (Post-May 25 Pivot)
**Reference:** May 25 meeting (discussion is the central interaction element), existing comm bus infrastructure

## Story
As a **human participant**, I want a chat-centric interface where discussion is the primary interaction mode and task state is always visible, so that every phase of sprint planning (refinement, assignment, review) feels like a conversation with the platform and AI agents.

## Design Principles

1. **Chat is the main area** — all interaction happens through messages, not separate view-switching
2. **Task state is always visible** — current task list or assignment map in a persistent side panel
3. **Platform proposes, team discusses** — same pattern across all 3 phases
4. **Actions are conversational** — add/remove/modify/volunteer can be done via chat or quick-action buttons
5. **Phase progression is clear** — header shows current phase (1/3, 2/3, 3/3) and sprint goal

## Layout

```
┌──────────────────────────────────────────────────────────┐
│  HASP · Phase 1/3 — Task Refinement   Goal: Ship OAuth   │
├──────────────────────────────────────┬───────────────────┤
│  💬 DISCUSSION                       │  TASKS (19 items) │
│                                      │  Capacity: 90 SP  │
│  Platform: Here's the recommended    │  Round: 2         │
│  list for "Ship OAuth..." (19 items) │                   │
│                                      │  ┌─────────────┐  │
│  Platform: ┌─────────────────────┐   │  │ T-001 3 SP  │  │
│            │ T-001 Add rate      │   │  │ Add rate    │  │
│            │ limiting (3 SP)     │   │  │ limiting    │  │
│            │ Priority: HIGH      │   │  │ [✎] [✕]    │  │
│            │ Score: 0.85         │   │  ├─────────────┤  │
│            └─────────────────────┘   │  │ T-002 8 SP  │  │
│                                      │  │ OAuth login │  │
│  Long (you): We need WebSocket       │  │ [✎] [✕]    │  │
│  support for real-time updates.      │  ├─────────────┤  │
│                                      │  │ ...         │  │
│  Platform: ✓ Added T-100             │  └─────────────┘  │
│  "WebSocket support" (5 SP).         │                   │
│  Updated: 20 items, 88/90 SP.        │  [+ Add Task]     │
│                                      │                   │
│  dev-agent: T-005 (8 SP) is too      │  [→ Assignment]   │
│  large for a single sprint. Can      │                   │
│  we split it?                        │  PARTICIPANTS     │
│                                      │  ● Long (you)     │
│  Platform: ✓ Split T-005 into        │  ● po-agent       │
│  T-005a (3 SP) + T-005b (5 SP).      │  ● dev-agent      │
│                                      │                   │
├──────────────────────────────────────┤                   │
│  [Type message...]              [Send]│                   │
│  [+ Add] [Modify] [Remove]           │                   │
│  [Volunteer] [Object] (Phase 2)      │                   │
└──────────────────────────────────────┴───────────────────┘
```

## Acceptance Criteria

### AC1 — Single-Page Layout
- [ ] Two-panel layout: chat (left, ~65%) + task state (right, ~35%)
- [ ] Header bar: project name, phase indicator (1/3, 2/3, 3/3), sprint goal
- [ ] Participants list in the right panel footer
- [ ] No page navigation between phases — phase transitions are seamless

### AC2 — Chat Panel (Left)
- [ ] Scrollable message feed — newest at bottom, auto-scroll
- [ ] Messages from: Platform (system), human participants, AI agents
- [ ] Platform messages include rich cards: task lists, assignment proposals
- [ ] Each message shows: sender name, avatar/icon, timestamp
- [ ] Input bar at bottom: text input + quick-action buttons
- [ ] Quick actions change by phase:
  - Phase 1 (Refinement): [+ Add Task] [Modify] [Remove]
  - Phase 2 (Assignment): [Volunteer] [Object] [Reassign]
  - Phase 3 (Review): no special actions, just chat
- [ ] Send structured messages via comm bus when quick actions are used

### AC3 — Task Panel (Right)
- [ ] Phase 1: shows current recommendation list
  - Each item: ID, title, story points, priority badge, score
  - Inline [Edit] and [Remove] buttons per item
  - [+ Add Task] button at bottom
  - Stats: item count, capacity used/available, round number
  - Updates in real-time when platform broadcasts recommendation_update
- [ ] Phase 2: shows current assignment map
  - Table: Task → Assignee → Status
  - Color-coded by assignment method (volunteered, assigned, unassigned)
  - Round number
  - Updates in real-time on assignment_update
- [ ] Phase 3: shows final sprint backlog (read-only)
  - Table with assignments and story points
  - Convergence metrics: recommendation rounds, assignment rounds, retention %
  - [Accept Plan] button for PO

### AC4 — Phase Transitions
- [ ] Phase indicator in header updates when platform broadcasts phase_started or discussion_update
- [ ] Phase 1 → 2: when recommendation discussion settles (timeout or PO advances)
- [ ] Phase 2 → 3: when all tasks assigned or PO advances
- [ ] Phase 3 → complete: when PO clicks [Accept Plan]
- [ ] "Ready for next phase" / "Advance to Assignment" button visible to PO
- [ ] Non-PO participants see "Waiting for PO to advance..." when appropriate

### AC5 — Message Rendering
- [ ] Platform recommendation: rendered as a compact task card list
- [ ] add_item/remove_item/modify_item: rendered as action notifications ("Long added T-100")
- [ ] volunteer/object/reassign: rendered as assignment change notifications
- [ ] Human chat messages: rendered as normal chat bubbles
- [ ] AI agent messages: rendered with agent avatar and name
- [ ] System/platform messages: rendered with distinct style (gray, left-aligned, no avatar)

### AC6 — Real-Time Updates
- [ ] Subscribe to comm-feed SSE for all discussion events
- [ ] Task panel re-renders when recommendation_update or assignment_update received
- [ ] Chat auto-scrolls when new messages arrive
- [ ] Phase indicator updates on phase_started events

### AC7 — V1 Backward Compatibility
- [ ] Existing SessionPage with separate views remains for v1 sessions
- [ ] New chat-centric view only for sprint_planning_v2 sessions
- [ ] Version detection unchanged (template includes "v2")

### AC8 — Actions via Chat
- [ ] User can type "/add Task title [SP]" to add a task (slash command)
- [ ] User can type "/remove T-001" to remove a task
- [ ] User can type "/volunteer T-001" in Phase 2 to claim a task
- [ ] Slash commands are parsed client-side and sent as structured discussion actions
- [ ] Regular text messages are sent as chat messages

## Out of Scope
- File/image attachments in chat
- Message threading/replies
- Message reactions/emoji
- Message edit/delete
- Typing indicators
- Read receipts
- Mobile responsive layout (desktop-first)
- Voice/video integration
