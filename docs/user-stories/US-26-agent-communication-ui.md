# US-26: Agent Communication & Chat UI

**Phase:** 4 — Experience Polish
**Reference:** [design-doc.md §10](../design-doc.md#10-human-participation), [US-24](./US-24-llm-po-agent.md), [US-25](./US-25-llm-dev-agent.md)

## Story
As a **human participant or researcher**, I want to see a real-time communication feed showing the messages exchanged between AI agents (PO and Dev agents) during a sprint planning session, so that I can follow the collaborative reasoning and negotiation happening between agents.

## Acceptance Criteria
- AC1: The UI includes a "Communication Feed" panel that displays A2A messages exchanged between the LLM-backed PO agent (US-24) and Dev agents (US-25) in chronological order.
- AC2: Each message entry shows the sender's avatar/identity, timestamp, and message content, distinguishing between task requests, responses, and streamed reasoning ("thoughts").
- AC3: The feed updates in real-time via SSE or WebSocket as agents exchange messages during active planning phases (no manual refresh required).
- AC4: Messages originating from the PO agent are visually differentiated from those of Dev agents (e.g., colour-coded bubbles or avatar labels) so participants can track who said what.
- AC5: Streamed reasoning content (thoughts from US-24 AC2 and US-25 AC3) appears inline within the feed as a distinct "thought" style (e.g., italicised, lower-opacity), consistent with the styling established in US-23 AC5.
- AC6: The feed is filterable by agent identity and message type (task request / response / thought) so researchers can isolate specific interaction patterns.
- AC7: When a new message arrives and the user is not scrolled to the bottom, a "New messages ↓" indicator appears; clicking it scrolls to the latest message.

## Out of Scope
- Allowing human participants to inject messages directly into the agent communication channel.
- Persisting the communication feed across sessions (feed is scoped to the current session only).
- Displaying raw A2A JSON payloads by default (a developer debug toggle may expose this in a future story).
- Cross-session comparison or replay of agent conversations (Phase 5+).
