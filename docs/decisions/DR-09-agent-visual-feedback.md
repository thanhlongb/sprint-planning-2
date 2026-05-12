# DR-09: Agent Visual Feedback Implementation

## Context
Implementing US-22 (Agent Action Visualization & Animations) requires adding visual feedback for AI agents in a React UI that serves primarily as a proxy for the human participant. The human participant receives SSE tasks that contain context about the sprint planning state, but not real-time granular AI state updates.

## Decision
1. **Agent Avatar Animations**: We created an `AgentAvatar` component powered by `framer-motion`. It supports states like `thinking` (which pulses and glows) and `idle`.
2. **Simulated State**: Since the backend does not currently stream real-time sub-phase states for all agents to the human proxy, `ParticipantsSidebar` infers the `thinking` state based on the active task type (e.g., if the human is voting or assigning, we assume the AI agents are also thinking/processing).
3. **Connecting Visuals (AC2)**: Rather than implementing complex SVG connecting lines across DOM nodes (which can be fragile on responsive screens), we utilize motion animations on the agent avatars themselves, and stagger the entry of AI actions in the UI to give the illusion of presence and motion.

## Status
Accepted.

## Consequences
- The visual feedback satisfies the UX requirements of US-22 without requiring a major refactor of the A2A protocol to emit sub-task granular state events.
- If real-time AI states are added to the protocol in the future, the UI is ready to consume them by simply updating the `state` prop on `AgentAvatar`.
