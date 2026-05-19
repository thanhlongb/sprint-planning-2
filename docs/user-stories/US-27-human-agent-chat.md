# US-27: Human Participant Chat with Agents

**Phase:** 4 — Experience Polish
**Reference:** [design-doc.md §10](../design-doc.md#10-human-participation), [US-26](./US-26-agent-communication-ui.md), [US-07](./US-07-react-ui-proxy.md)

## Story
As a **human participant**, I want to send freeform messages to the AI agents (PO and Dev agents) during a sprint planning session, so that I can ask questions, seek clarification, or contribute context that influences agent reasoning.

## Acceptance Criteria
- AC1: The Communication Feed panel (US-26) includes a message composer — a text input and "Send" button — visible to human participants during active planning phases.
- AC2: A human message is submitted to the platform backend via the existing A2A proxy (US-07 AC5) as a task of type `human_message`, carrying `{ sender_id, content, timestamp, target: "all" | agent_id }`.
- AC3: The human can optionally address a specific agent (e.g., "@PO", "@Dev-1") via a mention selector or `@` autocomplete; unaddressed messages are broadcast to all agents in the session.
- AC4: Each LLM-backed agent (US-24, US-25) handles the `human_message` task type: it incorporates the message into its next LLM prompt context so that subsequent decisions and streamed thoughts reflect the human's input.
- AC5: The human's message appears in the Communication Feed immediately after sending (optimistic insert), with a visual distinction (e.g., a "You" label and contrasting bubble colour) that sets it apart from agent messages.
- AC6: Agents acknowledge receipt of a human message with a brief response or updated thought stream within the normal phase timeout window; if no agent responds within 10 seconds a "Agents are processing…" indicator is shown.
- AC7: The message composer is disabled outside of active planning phases (lobby, summary, and post-session screens) with a tooltip explaining why input is unavailable.
- AC8: All human messages are included in the session audit log (US-14) alongside A2A task events so researchers have a complete interaction record.

## Out of Scope
- Human messages overriding or directly modifying agent votes, assignments, or backlog items (agents may consider the message but retain autonomous decision-making).
- Private/direct messaging between human participants (human-to-human chat).
- Rich-media attachments (images, files) in messages.
- Moderation or profanity filtering in Phase 4 (deferred to a future hardening story).
- Persistent chat history across sessions.
