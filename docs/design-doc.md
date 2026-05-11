# Sprint Planning 2.0 — Full System Design

**Version:** 2.0  
**Status:** Draft  

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Core Architectural Principles](#2-core-architectural-principles)
3. [A2A Protocol](#3-a2a-protocol)
4. [Participant Contract](#4-participant-contract)
5. [Agent Onboarding](#5-agent-onboarding)
6. [Session Lifecycle](#6-session-lifecycle)
7. [Process Template Engine](#7-process-template-engine)
8. [Phase Orchestration](#8-phase-orchestration)
9. [Assignment Strategy](#9-assignment-strategy)
10. [Human Participation](#10-human-participation)
11. [Session Context Schema](#11-session-context-schema)
12. [Component Architecture](#12-component-architecture)
13. [Multi-Organisation Marketplace Model](#13-multi-organisation-marketplace-model)
14. [Implementation Roadmap](#14-implementation-roadmap)
15. [Evaluation Metrics](#15-evaluation-metrics)
16. [Key Design Decisions](#16-key-design-decisions)

---

## 1. System Overview

Sprint Planning 2.0 is a **protocol-based marketplace platform** for AI-augmented sprint planning. It enables human participants and AI agents from different organisations to collaboratively plan a software sprint — regardless of the tools, LLMs, or internal systems each party uses.

The platform acts as a **neutral session orchestrator**. It has zero knowledge of any participant's product backlog, codebase, or internal business logic. It only enforces a structured planning process, routes messages between participants, collects decisions, and produces a sprint backlog as output.

```
┌─────────────────────────────────────────────────────────────────┐
│                     SPRINT PLANNING 2.0                          │
│                    (Marketplace Platform)                        │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │               Protocol & Session Manager                 │   │
│  │  ┌──────────────┐  ┌───────────────┐  ┌─────────────┐  │   │
│  │  │ Template     │  │ Phase         │  │ Contract    │  │   │
│  │  │ Engine       │  │ Orchestrator  │  │ Validator   │  │   │
│  │  └──────────────┘  └───────────────┘  └─────────────┘  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│  ┌──────────────┐  ┌─────────┴───────────┐  ┌───────────────┐  │
│  │ Session      │  │ Message Bus /        │  │ Output        │  │
│  │ Registry     │  │ Event Router         │  │ Aggregator    │  │
│  └──────────────┘  └─────────────────────┘  └───────────────┘  │
│                              │                                   │
│          ┌───────────────────┼───────────────────┐              │
│          │                   │                   │              │
│     ┌────▼────┐        ┌────▼────┐        ┌────▼────┐         │
│     │ Slot 1  │        │ Slot 2  │        │ Slot N  │         │
│     │(Agent / │        │(Agent / │        │(Agent / │         │
│     │ Human)  │        │ Human)  │        │ Human)  │         │
│     └─────────┘        └─────────┘        └─────────┘         │
└─────────────────────────────────────────────────────────────────┘
          │                    │                   │
     ┌────▼────┐         ┌────▼────┐        ┌────▼────┐
     │Company A│         │Company B│        │Company C│
     │ (Jira)  │         │(GitHub) │        │(Custom) │
     └─────────┘         └─────────┘        └─────────┘
```

**Input:** Product backlog (from the PRODUCT_OWNER participant)  
**Output:** Sprint backlog — a prioritised, assigned list of items for the upcoming sprint

---

## 2. Core Architectural Principles

| Principle | Description |
|---|---|
| **Platform Agnosticism** | The platform has zero knowledge of product backlogs, codebases, or internal business logic. It only orchestrates the planning process. |
| **A2A Protocol** | All agent-platform communication follows the Agent-to-Agent (A2A) open protocol. Agents are A2A Remote Agents; the platform is the A2A Client. |
| **Participant Symmetry** | Humans and AI agents are treated identically by the platform. Both occupy a Participant Slot and communicate through the same protocol. Humans use a React UI proxy that fulfils the A2A contract on their behalf. |
| **Template-Driven Flexibility** | The planning process (phases, turn order, required roles, decision rules) is defined via configurable Process Templates, not hard-coded logic. |
| **Stateless Agents** | The platform is the source of truth for all session state. Every task call includes a full `session_ctx` payload. Agents must not rely on locally cached state across task calls. |
| **Zero Internal Visibility** | The platform standardises the shape of data exchange but never inspects participants' internal systems, metadata, or reasoning. What happens inside an agent's container is opaque. |

---

## 3. A2A Protocol

The platform uses the **Agent-to-Agent (A2A) open protocol** for all agent communication. A2A defines a standard for how autonomous AI agents from different vendors and frameworks can discover each other, exchange tasks, and coordinate work without exposing internal implementation details.

### 3.1 Roles

| Role | Description |
|---|---|
| **Platform (A2A Client)** | Orchestrates sessions, sends tasks to agents, subscribes to task result streams |
| **Agent (A2A Remote Agent)** | Hosts a compliant HTTP server, publishes an Agent Card, receives and responds to tasks |
| **Human Proxy (A2A Remote Agent)** | React UI that acts as an A2A Remote Agent on behalf of a human participant |

### 3.2 Agent Card

Every agent publishes an Agent Card at a well-known URL on their own server:

```
GET https://company-b.com/.well-known/agent.json
```

The platform fetches this card once at registration time. The company owns and hosts it — there is no centralised registry.

```json
{
  "name": "Company B Dev Agent",
  "description": "Development agent backed by GitHub Issues",
  "role": "DEVELOPER",
  "capabilities": {
    "can_estimate": true,
    "can_vote": true,
    "can_volunteer": true
  },
  "endpoint": "https://company-b.com/a2a",
  "auth": {
    "scheme": "bearer"
  }
}
```

### 3.3 Task Lifecycle

The platform communicates with agents via A2A tasks. A task has a lifecycle:

| Status | Meaning |
|---|---|
| `working` | Agent has received the task and is processing |
| `completed` | Agent has produced a result artifact |
| `failed` | Agent encountered an error and cannot complete the task |

For short decisions (vote, confirm, acknowledge), agents respond synchronously with `completed`. For decisions that require human input or longer reasoning (e.g. presenting a backlog, human voting), agents respond with `working` and stream progress via SSE until `completed`.

```
Platform                          Agent
   │                                │
   │── POST /tasks ──────────────► │  (task submitted)
   │◄─ 202 { task_id, working } ── │
   │── GET /tasks/{id} (SSE) ────► │
   │◄─ stream: { working, ... } ── │  (optional progress)
   │◄─ stream: { completed, ... }  │  (final result)
```

### 3.4 Connection Model

Agents do not maintain a persistent outbound connection to the platform. Instead:

- **Platform → Agent:** REST task calls (POST /tasks) + SSE subscription per task for long-running decisions
- **Agent → Platform:** REST responses only — agents never push unsolicited messages to the platform

This means agents only need to be reachable HTTP servers. No persistent WebSocket, no polling, no runner process.

---

## 4. Participant Contract

Any participant (human or AI agent) that joins the platform must satisfy the following contract. For AI agents this means their A2A Remote Agent server implements these behaviours. For humans this is fulfilled by the React UI proxy.

### 4.1 Required Capabilities (declared in Agent Card)

```yaml
capabilities:
  can_provide_backlog: boolean   # PRODUCT_OWNER only
  can_vote: boolean
  can_volunteer: boolean         # DEVELOPER, ARCHITECT
```

### 4.2 Required Task Handlers

The platform will send the following task types. Agents must handle all tasks relevant to their role:

| Task Type | Sent To | Phase |
|---|---|---|
| `session_invite` | All | Pre-session |
| `session_ready` | All | Pre-session |
| `present_backlog` | PRODUCT_OWNER | Backlog Presentation |
| `vote` | All | Prioritisation |
| `assign_opportunity` | DEVELOPER, ARCHITECT | Assignment |
| `acknowledge_assignment` | All | Assignment |
| `confirm` | All | Confirmation |
| `session_aborted` | All | Pre-session (on failure) |

### 4.3 Backlog Item Schema (Standardised Exchange Format)

```json
{
  "item_id": "string",
  "title": "string",
  "description": "string",
  "priority": "HIGH | MEDIUM | LOW",
  "story_points": "number | null",
  "labels": ["string"],
  "dependencies": ["item_id"]
}
```

> The `metadata` field used internally by source systems (Jira, GitHub, etc.) is intentionally excluded. The platform never inspects internal metadata. Participants keep it in their own systems and only exchange the standardised schema above.

---

## 5. Agent Onboarding

Onboarding is a one-time process per agent. Once registered, an agent can join any number of sessions using its `participant_id`.

```
Dev Agent (Company B)              Platform
       │                               │
       │── POST /register ────────────►│
       │     { agent_url:              │
       │       "https://company-b.com" }│
       │                               │
       │◄── GET /.well-known/agent.json │
       │──► { name, role,              │
       │      capabilities, endpoint } │
       │                               │
       │       Platform validates      │
       │       capabilities against    │
       │       required contract ✅    │
       │                               │
       │◄── 201 ────────────────────── │
       │     { participant_id: "da-xyz",│
       │       status: REGISTERED }    │
```

**What the platform stores after onboarding:** the agent's `participant_id`, endpoint URL, role, and validated capabilities. The Agent Card is not stored — only the endpoint is bookmarked.

**Auth:** The agent's Agent Card declares its preferred auth scheme (e.g. Bearer token). The platform uses this when calling the agent's task endpoint. No API key is issued by the platform.

---

## 6. Session Lifecycle

### 6.1 Session States

```
PENDING ──► ACTIVE ──► COMPLETED
   │
   └──► ABORTED  (if required roles not satisfied at timeout)
```

### 6.2 Session Creation

Any registered participant can create a session. Participants are declared upfront — a mix of agents (by `agent_url` or `participant_id`) and humans (by name and role).

```
POST /sessions
{
  "template": "sprint_planning_v1",
  "sprint_goal": "Ship OAuth + user profile",
  "participants": [
    { "agent_url": "https://company-a.com", "role": "PRODUCT_OWNER" },
    { "participant_id": "da-xyz",           "role": "DEVELOPER" },
    { "type": "HUMAN", "role": "DEVELOPER", "name": "Alice" },
    { "type": "HUMAN", "role": "SCRUM_MASTER", "name": "Bob" }
  ]
}
```

**Response:**
```json
{
  "session_id": "sess-456",
  "join_url": "https://sprint-planning.io/join/sess-456",
  "timeout_at": "2026-05-11T10:15:00Z",
  "status": "PENDING"
}
```

### 6.3 Participant Joining

All participants — agents and humans — join via the same endpoint. The session is symmetric: the platform does not distinguish between agent and human joins at this layer.

```
POST /session/{session_id}/join
{ "participant_id": "da-xyz" }           ← agent (uses registered ID)

POST /session/{session_id}/join
{ "name": "Alice", "role": "DEVELOPER" } ← human (gets assigned an ID)
```

**Response:**
```json
{
  "participant_id": "hu-001",
  "status": "PENDING",
  "waiting_for": ["Bob"]
}
```

Agents join programmatically upon receiving a `session_invite` task. Humans join proactively by navigating to the `join_url` (shared out-of-band via Slack, email, etc.) and clicking join in the React UI.

### 6.4 Join Timeout

The session is created with a 15-minute join timeout (`timeout_at`). If not all declared participants have joined by then:

- The platform checks whether the missing participants' roles are `required_roles` in the **first phase** of the template.
- If required roles are still covered by present participants → session goes `ACTIVE` with a note about who is missing.
- If a required role is missing → session is `ABORTED` and all present participants are notified with a clear reason.

```
Platform
   │
   ⏱ timeout_at reached
   │
   ├── Missing: Bob (SCRUM_MASTER)
   │   SCRUM_MASTER not required for backlog_presentation ✅
   │   SET status: ACTIVE
   │   Notify all: session_ready (note: "Bob did not join")
   │
   └── Missing: Alice (PRODUCT_OWNER)
       PRODUCT_OWNER required for backlog_presentation ❌
       SET status: ABORTED
       Notify all: session_aborted (reason: "Required role PRODUCT_OWNER did not join")
```

### 6.5 Full Session Sequence

```
Dev Agent (Company B)     Platform          PO Agent (Company A)    Human Dev (Alice)
       │                      │                      │                      │
       │ POST /register        │                      │                      │
       │──────────────────────►│                      │                      │
       │◄── 201 participant_id ┤                      │                      │
       │                       │                      │                      │
       │ POST /sessions        │                      │                      │
       │──────────────────────►│                      │                      │
       │                       │── GET agent.json ───►│                      │
       │                       │◄─ Agent Card ─────── │                      │
       │                       │ Create sess-456       │                      │
       │◄── 201 { join_url } ──┤                      │                      │
       │                       │                      │                      │
       │     [Notify all participants in parallel]     │                      │
       │                       │── session_invite ───►│                      │
       │◄── session_invite ────┤                      │  email: join_url ───►│
       │                       │                      │                      │
       │     [All participants join]                   │                      │
       │ POST /join            │                      │                      │
       │──────────────────────►│                      │                      │
       │                       │◄─ POST /join ─────── │                      │
       │                       │◄───────────────────────── POST /join ───────│
       │                       │ All joined ✅         │                      │
       │                       │ SET status: ACTIVE    │                      │
       │                       │                      │                      │
       │◄── session_ready ─────┼─── session_ready ───►┼── session_ready ────►│
       │                       │                      │                      │
       │         [Phase 1: Backlog Presentation]       │                      │
       │                       │── present_backlog ──►│                      │
       │                       │◄─ { items × 15 } ─── │                      │
       │◄── broadcast items ───┼──────────────────────┼── broadcast items ──►│
       │                       │                      │                      │
       │         [Phase 2: Prioritisation]             │                      │
       │◄── vote { ballot } ───┼── vote { ballot } ──►┼─── vote { ballot } ─►│
       │── { votes } ─────────►│◄─ { votes } ─────── │◄──── { votes } ───── │
       │                       │ Tally → select items  │                      │
       │◄── broadcast selected ┼── broadcast selected ►┼── broadcast selected►│
       │                       │                      │                      │
       │         [Phase 3: Assignment]                 │                      │
       │◄── assign_opportunity ┼──────────────────────┼──── assign_opportunity│
       │── { volunteer: true } ►│                      │                      │
       │                       │ Assign to Dev Agent   │                      │
       │◄── acknowledge ───────┼── acknowledge ───────►┼─── acknowledge ─────►│
       │                       │                      │                      │
       │         [Phase 4: Confirmation]               │                      │
       │◄── confirm ───────────┼── confirm ───────────►┼─── confirm ──────────│
       │── { confirmed: true } ►│◄─ { confirmed: true }│◄── { confirmed: true}│
       │                       │ Quorum: 3/3 ✅        │                      │
       │                       │ SET status: COMPLETED │                      │
       │                       │                      │                      │
       │◄── sprint_backlog ────┼── sprint_backlog ────►┼─── sprint_backlog ──►│
       │ Sync → GitHub         │ Archive + audit log   │ Sync → Jira          │ UI summary
```

---

## 7. Process Template Engine

The platform's core differentiator is its configurable process engine. Planning sessions follow a Process Template that defines phases, turn order, required roles, and decision rules.

### 7.1 Template Schema

```yaml
ProcessTemplate:
  template_id: "sprint_planning_v1"
  name: "Sprint Planning 2.0 — Standard"
  description: "Human-AI collaborative sprint planning session"

  phases:
    - phase_id: "backlog_presentation"
      name: "Backlog Presentation"
      description: "PO presents candidate backlog items"
      required_roles: [PRODUCT_OWNER]
      actions:
        - type: PRESENT_ITEMS
          source: participant.backlog_items
          min_items: 1
          max_items: null
      turn_order: ROLE_FIRST
      duration_limit: null
      transition: AUTO

    - phase_id: "prioritization"
      name: "Selection & Prioritisation"
      description: "Team selects items for the sprint backlog"
      required_roles: [PRODUCT_OWNER, DEVELOPER, SCRUM_MASTER]
      actions:
        - type: VOTE
          method: DOT_VOTING
        - type: SELECT
          constraint: capacity_based
      turn_order: ALL_PARALLEL

    - phase_id: "assignment"
      name: "Task Assignment"
      description: "Selected items are assigned to participants"
      required_roles: [DEVELOPER]
      actions:
        - type: ASSIGN
          strategy: VOLUNTEER_FIRST
          fallback: AUTO_BALANCE
          conflict_resolution: LOWEST_LOAD
          timeout_ms: 5000
      turn_order: FACILITATOR_LED

    - phase_id: "confirmation"
      name: "Sprint Goal & Confirmation"
      description: "Team confirms sprint goal and backlog"
      required_roles: ALL
      actions:
        - type: CONFIRM
          requires_unanimous: false
          quorum: 0.75

  inputs:
    - product_backlog           # From PRODUCT_OWNER participant
    - capacity_constraints      # From all participants

  outputs:
    - sprint_backlog            # Selected items with assignments
    - sprint_goal               # Agreed-upon goal statement
    - capacity_plan             # Who does what, estimated effort
```

### 7.2 Pre-Built Templates

| Template | Phases | Best For |
|---|---|---|
| `sprint_planning_v1` | present → prioritise → assign → confirm | Traditional teams transitioning to AI |
| `continuous_planning` | No fixed sprint; rolling prioritisation | High-velocity AI-heavy teams |
| `delegation_only` | PO presents, platform auto-assigns to agents | Fully autonomous agent teams with human oversight |
| `negotiation_protocol` | Multi-party negotiation (cross-company) | Outsourcing / multi-org collaboration |

### 7.3 Turn Order Modes

| Mode | Behaviour |
|---|---|
| `ROLE_FIRST` | A specific role acts first (e.g. PRODUCT_OWNER presents before others respond) |
| `ALL_PARALLEL` | All participants act simultaneously; platform waits for all responses |
| `ROUND_ROBIN` | Each participant takes a turn in a fixed rotation |
| `FACILITATOR_LED` | SCRUM_MASTER or platform drives the order |

---

## 8. Phase Orchestration

### 8.1 Phase Transition Rules

The Phase Orchestrator advances through phases sequentially. Transition conditions:

| Transition Mode | Condition to advance |
|---|---|
| `AUTO` | All required participants have responded |
| `TIMED` | Duration limit reached (partial responses accepted) |
| `MANUAL` | SCRUM_MASTER explicitly advances |

### 8.2 Prioritisation Phase Detail

The platform sends a `vote` task to all participants in parallel with the same ballot. It waits for all responses (or the `duration_limit`), then:

1. Tallies dot votes across all participants
2. Ranks items by total votes descending
3. Selects items greedily until the team's declared velocity/capacity is filled
4. Broadcasts the selected list

### 8.3 Simultaneous Reveal

For voting, the platform holds all responses privately until either all participants have responded or the time limit is reached. It then broadcasts all votes simultaneously. This prevents anchoring — no participant sees another's votes before submitting their own.

---

## 9. Assignment Strategy

Assignment follows a three-branch decision tree for each selected item:

```
Platform broadcasts assign_opportunity
for item + starts timeout (5000ms)
              │
              ▼
    Volunteers received?
    ┌───────────┬──────────────┬──────────────┐
  None      Exactly one    Multiple
    │            │               │
    ▼            ▼               ▼
AUTO_BALANCE  Assign to     Pick by lowest
Pick by       that           current load
lowest load   participant         │
                            Still tied?
                           ┌─────┴──────┐
                          No           Yes
                           │             │
                           │         Random
                           │         selection
                           └─────┬──────┘
                                 ▼
                         Assign to winner

              ▼ (all branches)
POST /acknowledge_assignment to all participants
{ assignee_id, assignee_name, reason: VOLUNTEERED |
  CONFLICT_RESOLVED | AUTO_BALANCE }
```

**`reason` field:** All participants receive the assignment acknowledgement with a reason. Agents use this to update internal workload tracking. Humans see it as a UI label. The losing volunteer is not given a separate rejection notification — the `assignee_id` in the broadcast is sufficient.

**Load calculation:** Based on the number of items already assigned in `session_ctx.assignments` for the current session. The platform does not query external systems for workload — it only knows what has been assigned in this session.

---

## 10. Human Participation

### 10.1 The Human Proxy

The platform treats all participants symmetrically — humans and AI agents occupy the same Participant Slot and communicate through the same A2A protocol. Humans cannot literally expose A2A endpoints, so a **React UI proxy** fulfils the contract on their behalf.

The proxy:
- Hosts an A2A-compliant HTTP server on behalf of the human
- Receives task calls from the platform (e.g. `vote`, `confirm`)
- Renders the appropriate UI for the human to interact with
- Translates the human's UI interaction into a valid A2A task response
- Submits the response to the platform

The platform has no knowledge of the proxy's existence. From its perspective, the human is just another A2A Remote Agent.

### 10.2 Human Join Flow

Humans do not receive an automated invite. Instead:
1. The session creator receives a `join_url` on session creation
2. The join link is shared out-of-band (Slack, email, calendar invite)
3. The human navigates to the URL in their browser
4. The React UI shows session details (sprint goal, template, participants so far)
5. The human clicks **Join** and selects their declared role
6. The UI proxy registers the human as a participant and holds the A2A connection open

### 10.3 UI Task Mapping

| A2A Task Type | React UI renders |
|---|---|
| `session_invite` | Session lobby — sprint goal, participants, waiting status |
| `session_ready` | Session start screen — phase overview |
| `present_backlog` | Read-only backlog list (PO only — displays submitted items) |
| `vote` | Dot voting interface — draggable dots allocated across items |
| `assign_opportunity` | "Volunteer for this task?" card with Accept / Decline |
| `acknowledge_assignment` | Assignment notification toast |
| `confirm` | Sprint summary — backlog, assignments, sprint goal — with Confirm / Reject |

---

## 11. Session Context Schema

The platform attaches a `session_ctx` object to every A2A task call. Agents must read this on every call — they must not rely on locally cached state.

### 11.1 Schema

```json
{
  "session_id": "string",
  "sprint_goal": "string",
  "template_id": "string",

  "current_phase": {
    "phase_id": "string",
    "name": "string",
    "turn": "number"
  },

  "participants": [
    {
      "participant_id": "string",
      "name": "string",
      "role": "PRODUCT_OWNER | DEVELOPER | SCRUM_MASTER | ARCHITECT | REVIEWER",
      "type": "AI_AGENT | HUMAN"
    }
  ],

  "backlog_items": [
    {
      "item_id": "string",
      "title": "string",
      "description": "string",
      "priority": "HIGH | MEDIUM | LOW",
      "story_points": "number | null",
      "labels": ["string"],
      "dependencies": ["item_id"]
    }
  ],

  "selected_items": ["item_id"],

  "assignments": {
    "item_id": "participant_id"
  },

  "phase_history": [
    {
      "phase_id": "string",
      "completed_at": "ISO8601",
      "outcome": "string"
    }
  ]
}
```

### 11.2 Population Rules

| Field | Available from phase |
|---|---|
| `session_id`, `sprint_goal`, `template_id`, `participants` | Session start |
| `backlog_items` | After `backlog_presentation` |
| `selected_items` | After `prioritization` |
| `assignments` | Populated incrementally during `assignment` |
| `phase_history` | Appended at each phase transition |

### 11.3 Design Constraints

- **`backlog_items` carries standardised fields only.** Internal source-system metadata stays inside the participant's own systems and is never included.
- **`phase_history.outcome` is a platform-generated plain-text summary** (e.g. `"8 items selected, total 34 story points"`). It is informational only and not machine-parseable.
- **Agents must null-check before using late-populated fields.** `backlog_items` is null during `backlog_presentation`. `selected_items` is null during `prioritization`.

---

## 12. Component Architecture

### 12.1 Component Breakdown

```
┌──────────────────────────────────────────────────────────────┐
│                       API Gateway                             │
│               (REST + SSE + Webhook)                          │
└─────────────────────┬────────────────────────────────────────┘
                      │
         ┌────────────┴────────────┐
         │                         │
┌────────▼──────────┐   ┌─────────▼─────────┐
│  Session Manager  │   │ Participant        │
│  ─────────────    │   │ Registry           │
│  • Create session │   │  ─────────────     │
│  • Load template  │   │  • Register agent  │
│  • Manage states  │   │  • Fetch Agent Card│
│  • Join timeout   │   │  • Validate caps   │
│  • Track state    │   │  • Store endpoints │
└────────┬──────────┘   └─────────┬─────────┘
         │                         │
┌────────▼─────────────────────────▼────────┐
│              Phase Orchestrator            │
│  ─────────────────────────────────────    │
│  • Execute template phases sequentially   │
│  • Send A2A tasks to participants         │
│  • Enforce turn order & duration limits   │
│  • Collect and validate responses         │
│  • Apply consensus/decision rules         │
│  • Manage simultaneous reveal buffer      │
│  • Transition between phases              │
└──────────────────────┬────────────────────┘
                       │
┌──────────────────────▼────────────────────┐
│           Message Bus / Event Router       │
│  ─────────────────────────────────────    │
│  • Route A2A tasks to agent endpoints     │
│  • Manage SSE streams per task            │
│  • Broadcast phase transitions            │
│  • Log all interactions (audit trail)     │
└──────────────────────┬────────────────────┘
                       │
┌──────────────────────▼────────────────────┐
│              Output Aggregator             │
│  ─────────────────────────────────────    │
│  • Compile sprint backlog                 │
│  • Generate sprint goal summary           │
│  • Distribute results to all participants │
│  • Deliver via webhook / A2A push         │
│  • Archive session + audit log            │
└───────────────────────────────────────────┘
```

### 12.2 Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| API Gateway | FastAPI (Python) | Async support, SSE native, quick to prototype |
| Message Bus | Redis Pub/Sub | Low-latency event routing between components |
| Session State | PostgreSQL | Session lifecycle, phase state, assignment tracking |
| Template Store | YAML → PostgreSQL | Templates stored as structured config |
| Human UI | React + SSE | Real-time participation UI; acts as A2A proxy |
| Agent Interface | A2A (REST + SSE) | Standard open protocol for agent participation |

---

## 13. Multi-Organisation Marketplace Model

The platform enables cross-company collaboration without proprietary integration. Each company deploys their own A2A Remote Agent — the platform never touches their internal systems.

```
┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
│     Company A        │  │     Company B        │  │     Company C        │
│  (Client / PO)       │  │  (Dev Outsourcer)    │  │  (QA Contractor)     │
│                      │  │                      │  │                      │
│  ┌────────────────┐  │  │  ┌────────────────┐  │  │  ┌────────────────┐  │
│  │   PO Agent     │  │  │  │  Dev Agent     │  │  │  │  QA Agent      │  │
│  │  (Jira-backed) │  │  │  │(GitHub-backed) │  │  │  │ (TestRail)     │  │
│  └───────┬────────┘  │  │  └───────┬────────┘  │  │  └───────┬────────┘  │
│          │           │  │          │           │  │          │           │
│  company-a.com/      │  │  company-b.com/      │  │  company-c.com/      │
│  .well-known/        │  │  .well-known/        │  │  .well-known/        │
│  agent.json          │  │  agent.json          │  │  agent.json          │
└──────────┼───────────┘  └──────────┼───────────┘  └──────────┼───────────┘
           │                          │                          │
           │       A2A Protocol       │       A2A Protocol       │
           │                          │                          │
     ┌─────▼──────────────────────────▼──────────────────────────▼─────┐
     │                  SPRINT PLANNING 2.0 PLATFORM                    │
     │                                                                  │
     │   • No knowledge of Jira, GitHub, or TestRail                   │
     │   • Only knows: roles, protocol phases, session context         │
     │   • Enforces contract, orchestrates process                     │
     │   • Returns results to each participant via their endpoint      │
     └──────────────────────────────────────────────────────────────────┘
```

**What each company needs to do to join:**
1. Deploy an A2A Remote Agent that publishes an Agent Card
2. Implement handlers for the relevant task types (vote, estimate, confirm, etc.)
3. Register their agent URL with the platform once
4. Join sessions using their `participant_id`

The agent skill document (`sprint-planning-agent-skill.md`) provides a complete guide for building a compliant agent on any LLM harness (Claude, LangChain, AutoGen, etc.).

---

## 14. Implementation Roadmap

### Phase 1: A2A Baseline (Weeks 1–2)

- [ ] Implement A2A task sending and SSE subscription in the platform
- [ ] Build Participant Registry with Agent Card fetch and validation
- [ ] Implement Session Manager (create, join, timeout, state transitions)
- [ ] Implement Phase Orchestrator for `sprint_planning_v1` (hard-coded template)
- [ ] Build PO Agent (A2A Remote Agent backed by a static backlog)
- [ ] Build Dev Agent (A2A Remote Agent that votes and volunteers)
- [ ] Build React UI proxy (A2A Remote Agent for human participants)
- [ ] Session produces sprint backlog as output

**Deliverable:** Working end-to-end demo with one PO agent, one Dev agent, one human

### Phase 2: Template Engine (Weeks 3–4)

- [ ] Extract hard-coded process into YAML-based Process Templates
- [ ] Build Phase Orchestrator to execute templates dynamically
- [ ] Support 2–3 distinct templates
- [ ] Add simultaneous reveal buffer to voting phase
- [ ] Add Output Aggregator with webhook delivery
- [ ] Session audit log

**Deliverable:** Configurable planning sessions

### Phase 3: Marketplace Generalisation (Weeks 5–6)

- [ ] Support multi-organisation participant registration
- [ ] Full A2A Agent Card discovery and revalidation
- [ ] Scalability testing with multiple concurrent agents
- [ ] Template authoring UI

**Deliverable:** Open marketplace prototype

### Phase 4: Evaluation & Paper (Weeks 7–8)

- [ ] Run human-AI study (15–16 participants)
- [ ] Collect metrics: openness, scalability, human-AI interaction quality
- [ ] Write evaluation section of research paper

**Deliverable:** Evaluation data + draft paper sections

---

## 15. Evaluation Metrics

| Metric | What It Measures | How to Measure |
|---|---|---|
| **Openness** | Can heterogeneous agents join freely? | Count of distinct agent types successfully integrated; time-to-first-session for a new agent |
| **Scalability** | Does the platform handle growing participant counts? | Load test: 5, 10, 25, 50 concurrent participants; measure latency and throughput |
| **Process Flexibility** | Can different planning processes be configured? | Number of distinct templates executed successfully; user satisfaction with customisation |
| **Human-AI Interaction Quality** | Is the collaboration effective? | User study — task completion rate, perceived usefulness (Likert scale), sprint backlog quality |
| **Cross-Organisation Support** | Can multiple companies collaborate on one session? | Multi-tenant scenario test with isolated agent deployments |

---

## 16. Key Design Decisions

| Decision | Rationale |
|---|---|
| **A2A from Phase 1** | Avoids re-implementing a custom agent protocol later; frameworks already ship A2A server support making it genuinely plug-and-play |
| **Agent Card hosted by the company** | No centralised registry needed; companies own and update their own identity; platform just bookmarks the endpoint |
| **Platform is the A2A Client, agents are Remote Agents** | Agents only need to be reachable HTTP servers — no persistent outbound connection, no polling, no runner process required |
| **Stateless agents, platform carries all state** | Any agent harness (Claude, LangChain, AutoGen, etc.) can participate without maintaining session memory; `session_ctx` is sent with every task |
| **Human as A2A proxy** | Achieves true participant symmetry — the platform has zero special cases for humans vs agents; all protocol handling is uniform |
| **Humans join proactively via join_url** | More natural than a platform-pushed invite; mirrors how humans join meetings (shared link, click to join) |
| **Single `participants` list in POST /sessions** | Agents and humans declared together upfront; the platform knows exactly who to expect; session state is deterministic from creation |
| **15-minute join timeout with role-aware abort** | Session is not held hostage by a missing human; platform checks template `required_roles` before aborting; non-critical absent roles are noted, not fatal |
| **`VOLUNTEER_FIRST → AUTO_BALANCE` assignment** | Preserves agent autonomy where possible; guarantees all items get assigned; lowest-load tiebreaker requires no external workload data |
| **`reason` field on `acknowledge_assignment`** | Agents update their internal workload tracking correctly; humans see clear UI labels; losing volunteers understand why without a separate notification |
| **`metadata` excluded from `session_ctx`** | Enforces the zero-knowledge guarantee; internal source-system data never leaves a participant's own systems |
| **Estimation removed from template** | Reduces session complexity; story points can be pre-populated in the backlog by the PO agent before the session begins |
| **Platform has zero knowledge of backlog content** | Internal data stays internal; the platform only sees the standardised `BacklogItem` schema |
| **Hard-coded baseline first, then generalise** | Avoids over-engineering before the core interaction model is validated; each phase is independently deliverable |
