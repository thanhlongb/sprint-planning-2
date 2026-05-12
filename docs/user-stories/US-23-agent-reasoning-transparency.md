# US-23: Agent Reasoning Transparency (Thought Stream)

**Phase:** 4 — Experience Polish
**Reference:** [design-doc.md §10.3](../design-doc.md#103-ui-task-mapping)

## Story
As a **human participant**, I want to be able to view the internal reasoning or "thoughts" of AI agents as they process tasks, so that I can understand the rationale behind their decisions and trust the planning process.

## Acceptance Criteria
- AC1: The UI includes a collapsible "Activity Stream" or "Thought Panel" per agent card.
- AC2: If an A2A task response includes reasoning/metadata, it is displayed in the Thought Panel in real-time.
- AC3: The "Thinking" state of an agent is visually linked to a streaming text component if the agent supports incremental reasoning output.
- AC4: Historical thoughts for the current phase are accessible to allow humans to "catch up" on agent logic.
- AC5: UI uses different typography/styling (e.g., italicized, lower-opacity) for "internal thoughts" vs "public declarations" to prevent confusion.
- AC6: Thoughts are truncated with a "Read More" option if they exceed a specific length to maintain UI cleanliness.

## Out of Scope
- Editing or influencing agent thoughts directly (read-only).
- Cross-agent private communication visibility (unless explicitly shared in task metadata).
- Sentiment analysis or "mood" indicators for agents (Phase 5+).
