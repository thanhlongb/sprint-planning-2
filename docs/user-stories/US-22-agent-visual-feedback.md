# US-22: Agent Action Visualization & Animations

**Phase:** 4 — Experience Polish
**Reference:** [design-doc.md §10](../design-doc.md#10-human-participation)

## Story
As a **human participant**, I want to see visual animations and feedback when AI agents take actions (such as volunteering for a story), so that I have a clear sense of the "presence" and "activity" of AI agents in the session.

## Acceptance Criteria
- [x] AC1: Agent avatars/cards feature dynamic state indicators (Idle, Thinking, Ready, Done).
- [x] AC2: When an agent "volunteers" or is assigned a task, a smooth motion animation (e.g., card sliding or a connecting line) visually links the agent to the specific backlog item.
- [x] AC3: Agents currently processing a task display a "thinking" pulse or glow effect to signify active reasoning.
- [x] AC4: When results are revealed (e.g., after voting), the UI uses staggered entry animations for agent responses rather than a single static update.
- [x] AC5: Human task arrivals (SSE events) are accompanied by subtle entry animations to distinguish them from background agent activity.
- [x] AC6: Use `framer-motion` (or similar) to ensure 60fps animations for state transitions.

## Out of Scope
- Full 3D avatars or complex character animations.
- Sound effects (SFX) for agent actions.
- Real-time video/audio streaming of agent "thoughts".
- Multi-user cursor tracking (focusing only on task-level actions).
