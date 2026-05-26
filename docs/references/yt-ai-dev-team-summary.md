# Summary: How Abundly Uses AI Agents for Product Development

Source: YouTube video by Henrik at Abundly
File: yt-ai-dev-team.srt

---

## Context

Abundly builds an operating system for AI agents — a platform to create, run, and manage digital colleagues. Despite a small team and a large, complex codebase (hundreds of thousands of lines), they ship a new product version every day. The trick: AI assistance across the entire development workflow, not just coding.

---

## Evolution of AI-Assisted Coding

- Early days: copy-paste between editor and ChatGPT — clunky but faster than manual
- Then: tools like Cursor and Claude Code brought AI into the editor directly
- Now: AI builds whole features end-to-end while developers have tea. Half an hour of discussion, then "build it", and it's done in 5-10 minutes
- Scale shift: large features went from weeks → days, medium from days → hours, small from hours → minutes
- Coding stopped being the bottleneck — constraints moved upstream (what to build, decisions, design) and downstream (getting to production)

---

## The Three Agents

### 1. Backlogger (upstream agent)
- Monitors Slack threads, turns messy discussions into clean, well-structured tickets in Notion/Kanban
- Built using Abundly: told it its job, it asked for integrations (Slack, Notion), wrote its own instructions, was deployed
- Solved user mapping issue by creating its own database to remember Slack → Notion user mappings
- Benefits: reduced context switching for developers, faster triage meetings, clearer tickets benefit both human and AI implementers

### 2. Releaser (downstream agent)
- Ships to production every day — was previously once or twice a week
- Four triggers:
  1. Weekday 1:00 PM — prepares a release PR and docs PR, posts to Slack for approval
  2. 13:37 — if not approved, posts a "funny angry rant" on dev channel (deliberate personality)
  3. On PR approval — merges to production, updates changelog, posts release notes to Slack
  4. Friday 2:02 PM — posts weekly release summary for less frequent readers
- Learned to write custom scripts to interact with GitHub API efficiently (too much data returned otherwise)
- Agents build on each other: Cursor writes clean commit messages knowing Releaser will use them for changelogs
- Benefits: daily releases, less stale code pile-up, fewer merge conflicts, better stakeholder communication

### 3. Grace (end-to-end agent, named after Grace Hopper)
- High-level workflow agent: handles stakeholder requests from Slack all the way to a merged PR
- Has access to Slack, GitHub, Notion, and can spin up Cursor agents via the Cursor Cloud API
- Connected to Backlogger and Releaser — she interviewed them to learn what they can do
- Workflow: reads request → asks clarifying questions → triages complexity → if doable, fires Cursor to build it → makes PR → posts to dev channel
- Three scenarios:
  - Trivial: just builds it and makes a PR
  - Unclear: asks questions, then builds it
  - Complex: escalates to a Notion ticket for a human developer
- Maintains her own state: errands database, dashboard, scripts for recurring tasks, skill documents, context documents
- Most files were created and maintained by Grace herself
- After day 1, ran a retrospective and identified her own weaknesses ("over-asking, under-reading") and updated her own instructions
- Key design insight: high-level agents need clear purpose and context, not step-by-step workflow instructions

---

## Key Lessons

- Agents build on each other's work — compounding effects across the system
- Context management is critical: break out detailed instructions per trigger to avoid weighing down the agent
- GitHub API can be token-inefficient — agents can write their own utility scripts to fix this
- Agents are not scripts — they can handle adjacent use cases beyond their primary job
- You grow agents iteratively, you don't build them in one shot — similar to onboarding a new colleague
- Human developers remain in control: they write instructions, give feedback, approve PRs

---

## Human Role in This System

Humans focus on: what to build and why, architecture, design, UX, key decisions, and complex implementation. AI handles the rest. The team's view: humans and AI agents work side by side as colleagues, with compounding productivity gains over time.
