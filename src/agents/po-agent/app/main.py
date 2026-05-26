"""Reference PRODUCT_OWNER A2A Remote Agent (US-05).

Hosts a compliant A2A HTTP server backed by a static backlog fixture.
All task handling is stateless — session state comes in via session_ctx only (AC8).
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

AGENT_NAME = os.environ.get("AGENT_NAME", "po-agent")
AGENT_PUBLIC_URL = os.environ.get("AGENT_PUBLIC_URL", "http://localhost:8001")

# Declared auth scheme — validated on every inbound task call (AC7).
_AUTH_SCHEME = "none"

app = FastAPI(title=f"{AGENT_NAME} (A2A Remote Agent)")

# ── Static backlog fixture (AC4: ≥5 items, no metadata field) ─────────────────

STATIC_BACKLOG: list[dict[str, Any]] = [
    # ── HIGH priority (~30 items) ──────────────────────────────────────────────
    {
        "item_id": "T-001",
        "title": "Add rate limiting to login endpoint",
        "description": "Implement token-bucket rate limiting (5 req/s per IP) on POST /auth/login to prevent brute-force attacks.",
        "priority": "HIGH",
        "story_points": 3,
        "labels": ["auth", "security"],
        "dependencies": [],
    },
    {
        "item_id": "T-002",
        "title": "Implement OAuth 2.0 social login",
        "description": "Add Google and GitHub OAuth 2.0 sign-in with account linking for existing email users.",
        "priority": "HIGH",
        "story_points": 8,
        "labels": ["auth", "security", "api"],
        "dependencies": [],
    },
    {
        "item_id": "T-003",
        "title": "Add CSRF protection to all state-changing endpoints",
        "description": "Generate and validate CSRF tokens on POST/PUT/DELETE requests using the double-submit cookie pattern.",
        "priority": "HIGH",
        "story_points": 3,
        "labels": ["security", "api"],
        "dependencies": [],
    },
    {
        "item_id": "T-004",
        "title": "Build user registration with email verification",
        "description": "Create sign-up form, send verification email with expiring token, and activate account on confirmation.",
        "priority": "HIGH",
        "story_points": 5,
        "labels": ["auth", "ui", "api"],
        "dependencies": [],
    },
    {
        "item_id": "T-005",
        "title": "Implement password reset flow",
        "description": "Self-service password reset via email with time-limited reset tokens and account lockout notification.",
        "priority": "HIGH",
        "story_points": 5,
        "labels": ["auth", "security", "api"],
        "dependencies": ["T-004"],
    },
    {
        "item_id": "T-006",
        "title": "Create project dashboard with real-time metrics",
        "description": "Landing page showing active projects, team velocity, sprint burndown, and recent activity feed.",
        "priority": "HIGH",
        "story_points": 8,
        "labels": ["ui", "frontend"],
        "dependencies": [],
    },
    {
        "item_id": "T-007",
        "title": "Add WebSocket support for live updates",
        "description": "Set up WebSocket endpoints for real-time task status updates, notifications, and collaborative editing presence.",
        "priority": "HIGH",
        "story_points": 5,
        "labels": ["api", "performance"],
        "dependencies": [],
    },
    {
        "item_id": "T-008",
        "title": "Implement role-based access control (RBAC)",
        "description": "Add admin, manager, and member roles with middleware to enforce permission checks on all endpoints.",
        "priority": "HIGH",
        "story_points": 8,
        "labels": ["auth", "security"],
        "dependencies": ["T-004"],
    },
    {
        "item_id": "T-009",
        "title": "Set up CI/CD pipeline with automated tests",
        "description": "Configure GitHub Actions to run unit, integration, and E2E tests on PRs with deployment to staging.",
        "priority": "HIGH",
        "story_points": 5,
        "labels": ["infra", "testing"],
        "dependencies": [],
    },
    {
        "item_id": "T-010",
        "title": "Add input sanitization across all API endpoints",
        "description": "Apply HTML entity encoding and SQL injection guards on every user-input field in request bodies and query params.",
        "priority": "HIGH",
        "story_points": 5,
        "labels": ["security", "api"],
        "dependencies": [],
    },
    {
        "item_id": "T-011",
        "title": "Implement JWT token refresh mechanism",
        "description": "Short-lived access tokens (15min) with refresh token rotation and automatic renewal on 401 responses.",
        "priority": "HIGH",
        "story_points": 5,
        "labels": ["auth", "security", "api"],
        "dependencies": ["T-002"],
    },
    {
        "item_id": "T-012",
        "title": "Add pagination to all list endpoints",
        "description": "Cursor-based pagination with configurable page size and total-count header on GET /api/*/list endpoints.",
        "priority": "HIGH",
        "story_points": 5,
        "labels": ["api", "performance"],
        "dependencies": [],
    },
    {
        "item_id": "T-013",
        "title": "Build task CRUD API with validation",
        "description": "Full REST API for tasks: create, read, update, delete with JSON Schema validation on request bodies.",
        "priority": "HIGH",
        "story_points": 5,
        "labels": ["api", "backend"],
        "dependencies": [],
    },
    {
        "item_id": "T-014",
        "title": "Implement database migration framework",
        "description": "Set up Alembic with auto-generation from SQLAlchemy models, rollback support, and seed data scripts.",
        "priority": "HIGH",
        "story_points": 3,
        "labels": ["infra"],
        "dependencies": [],
    },
    {
        "item_id": "T-015",
        "title": "Add request logging and structured error responses",
        "description": "Middleware to log every request with correlation IDs, and return consistent JSON error bodies with trace IDs.",
        "priority": "HIGH",
        "story_points": 3,
        "labels": ["api", "backend"],
        "dependencies": [],
    },
    {
        "item_id": "T-016",
        "title": "Create user profile page with avatar upload",
        "description": "Profile page with editable display name, bio, avatar image upload with cropping, and notification preferences.",
        "priority": "HIGH",
        "story_points": 5,
        "labels": ["ui", "frontend"],
        "dependencies": ["T-004"],
    },
    {
        "item_id": "T-017",
        "title": "Add session management (logout all devices)",
        "description": "Track active sessions per user, allow viewing and revoking specific sessions or logging out everywhere.",
        "priority": "HIGH",
        "story_points": 3,
        "labels": ["auth", "security"],
        "dependencies": ["T-011"],
    },
    {
        "item_id": "T-018",
        "title": "Build notification center UI",
        "description": "Bell icon with unread badge, dropdown showing recent notifications, mark-as-read, and notification preferences page.",
        "priority": "HIGH",
        "story_points": 5,
        "labels": ["ui", "frontend"],
        "dependencies": [],
    },
    {
        "item_id": "T-019",
        "title": "Implement file upload with virus scanning",
        "description": "S3-backed file upload endpoint with ClamAV virus scanning, file type validation, and size limits (max 25MB).",
        "priority": "HIGH",
        "story_points": 5,
        "labels": ["api", "security", "infra"],
        "dependencies": [],
    },
    {
        "item_id": "T-020",
        "title": "Add two-factor authentication (TOTP)",
        "description": "TOTP-based 2FA with QR code setup, backup recovery codes, and remember-device option for 30 days.",
        "priority": "HIGH",
        "story_points": 5,
        "labels": ["auth", "security"],
        "dependencies": ["T-004"],
    },
    {
        "item_id": "T-021",
        "title": "Set up application monitoring and alerting",
        "description": "Integrate Prometheus metrics, Grafana dashboards, and PagerDuty alerts for error rate, latency, and resource usage.",
        "priority": "HIGH",
        "story_points": 5,
        "labels": ["infra", "performance"],
        "dependencies": [],
    },
    {
        "item_id": "T-022",
        "title": "Fix race condition in concurrent task assignment",
        "description": "Two users assigning the same task simultaneously can create duplicate assignments; add optimistic locking.",
        "priority": "HIGH",
        "story_points": 3,
        "labels": ["bug", "backend"],
        "dependencies": [],
    },
    {
        "item_id": "T-023",
        "title": "Add API versioning strategy",
        "description": "URL-prefix versioning (/api/v1/) with deprecation headers and sunset policy documented in OpenAPI spec.",
        "priority": "HIGH",
        "story_points": 3,
        "labels": ["api", "docs"],
        "dependencies": [],
    },
    {
        "item_id": "T-024",
        "title": "Implement search functionality with Elasticsearch",
        "description": "Full-text search across tasks, projects, and documents with typo tolerance, filters, and relevance scoring.",
        "priority": "HIGH",
        "story_points": 8,
        "labels": ["api", "performance"],
        "dependencies": [],
    },
    {
        "item_id": "T-025",
        "title": "Add audit logging for all admin actions",
        "description": "Log every admin action (user CRUD, role changes, config edits) to a tamper-evident audit table with actor and timestamp.",
        "priority": "HIGH",
        "story_points": 3,
        "labels": ["security", "backend"],
        "dependencies": [],
    },
    {
        "item_id": "T-026",
        "title": "Build onboarding wizard for new users",
        "description": "Multi-step onboarding flow: create first project, invite teammates, set up profile, tour key features.",
        "priority": "HIGH",
        "story_points": 5,
        "labels": ["ui", "frontend"],
        "dependencies": ["T-004", "T-016"],
    },
    {
        "item_id": "T-027",
        "title": "Add database connection pooling and query timeout",
        "description": "Configure connection pool size limits, statement timeout (30s), and connection health checks to prevent pool exhaustion.",
        "priority": "HIGH",
        "story_points": 2,
        "labels": ["infra", "performance"],
        "dependencies": [],
    },
    {
        "item_id": "T-028",
        "title": "Implement email notification service",
        "description": "Transactional email via SendGrid with retry logic, template rendering, and bounce/complaint webhook handling.",
        "priority": "HIGH",
        "story_points": 5,
        "labels": ["api", "backend"],
        "dependencies": [],
    },
    {
        "item_id": "T-029",
        "title": "Fix XSS vulnerability in comment rendering",
        "description": "User-submitted comments are rendered without sanitization; apply DOMPurify and Content-Security-Policy headers.",
        "priority": "HIGH",
        "story_points": 2,
        "labels": ["bug", "security"],
        "dependencies": [],
    },
    {
        "item_id": "T-030",
        "title": "Add API key management for service accounts",
        "description": "Generate, rotate, and revoke API keys for machine-to-machine auth with scoped permissions and usage tracking.",
        "priority": "HIGH",
        "story_points": 5,
        "labels": ["auth", "api", "security"],
        "dependencies": ["T-008"],
    },
    # ── MEDIUM priority (~40 items) ────────────────────────────────────────────
    {
        "item_id": "T-031",
        "title": "Create dark mode theme toggle",
        "description": "System-preference-aware dark mode with manual toggle, persisted in localStorage, and CSS custom properties for theming.",
        "priority": "MEDIUM",
        "story_points": 3,
        "labels": ["ui", "frontend"],
        "dependencies": [],
    },
    {
        "item_id": "T-032",
        "title": "Add drag-and-drop file upload component",
        "description": "Reusable React component with drag-and-drop zone, multi-file selection, progress bars, and preview thumbnails.",
        "priority": "MEDIUM",
        "story_points": 3,
        "labels": ["ui", "frontend"],
        "dependencies": [],
    },
    {
        "item_id": "T-033",
        "title": "Implement project member invitation system",
        "description": "Invite users by email to a project, with accept/decline flow, pending invite management, and role assignment.",
        "priority": "MEDIUM",
        "story_points": 5,
        "labels": ["api", "backend", "ui"],
        "dependencies": ["T-004", "T-028"],
    },
    {
        "item_id": "T-034",
        "title": "Build comment thread component",
        "description": "Nested comment threads on tasks with @mentions, markdown support, edit/delete, and real-time updates via WebSocket.",
        "priority": "MEDIUM",
        "story_points": 8,
        "labels": ["ui", "frontend", "api"],
        "dependencies": ["T-007", "T-013"],
    },
    {
        "item_id": "T-035",
        "title": "Add task labels and color coding",
        "description": "Create, edit, and assign colored labels to tasks with filtering by label on the task board and backlog views.",
        "priority": "MEDIUM",
        "story_points": 3,
        "labels": ["ui", "frontend", "api"],
        "dependencies": ["T-013"],
    },
    {
        "item_id": "T-036",
        "title": "Implement Kanban board view",
        "description": "Drag-and-drop Kanban board with swimlanes by status, WIP limits, and inline task creation per column.",
        "priority": "MEDIUM",
        "story_points": 8,
        "labels": ["ui", "frontend"],
        "dependencies": ["T-013", "T-007"],
    },
    {
        "item_id": "T-037",
        "title": "Add CSV import/export for tasks",
        "description": "Import tasks from CSV with column mapping and validation; export filtered task lists to CSV with all fields.",
        "priority": "MEDIUM",
        "story_points": 3,
        "labels": ["api", "backend"],
        "dependencies": ["T-013"],
    },
    {
        "item_id": "T-038",
        "title": "Create activity feed on project home",
        "description": "Chronological feed of task creations, status changes, comments, and assignments with infinite scroll.",
        "priority": "MEDIUM",
        "story_points": 3,
        "labels": ["ui", "frontend", "api"],
        "dependencies": [],
    },
    {
        "item_id": "T-039",
        "title": "Add due date reminders and calendar sync",
        "description": "Set task due dates, get email/push reminders 24h before, and sync to Google Calendar / Outlook via iCal feed.",
        "priority": "MEDIUM",
        "story_points": 5,
        "labels": ["api", "backend"],
        "dependencies": ["T-013", "T-028"],
    },
    {
        "item_id": "T-040",
        "title": "Write API integration tests with pytest",
        "description": "Comprehensive integration tests for all /api/v1 endpoints covering happy path, auth errors, validation, and edge cases.",
        "priority": "MEDIUM",
        "story_points": 5,
        "labels": ["testing", "api"],
        "dependencies": ["T-013"],
    },
    {
        "item_id": "T-041",
        "title": "Set up end-to-end testing with Playwright",
        "description": "Configure Playwright for cross-browser E2E tests on critical user flows: signup, login, create task, board navigation.",
        "priority": "MEDIUM",
        "story_points": 5,
        "labels": ["testing", "ui"],
        "dependencies": ["T-004", "T-006"],
    },
    {
        "item_id": "T-042",
        "title": "Add performance benchmarks and load testing",
        "description": "Set up k6 load-testing scripts for key endpoints, establish baseline metrics, and integrate into CI pipeline.",
        "priority": "MEDIUM",
        "story_points": 3,
        "labels": ["testing", "performance"],
        "dependencies": ["T-009"],
    },
    {
        "item_id": "T-043",
        "title": "Create OpenAPI 3.1 specification document",
        "description": "Full OpenAPI spec for all endpoints with request/response schemas, auth schemes, and example payloads using Swagger UI.",
        "priority": "MEDIUM",
        "story_points": 5,
        "labels": ["docs", "api"],
        "dependencies": [],
    },
    {
        "item_id": "T-044",
        "title": "Write developer onboarding guide",
        "description": "README updates, local setup instructions, architecture diagrams, coding conventions, and contribution workflow docs.",
        "priority": "MEDIUM",
        "story_points": 3,
        "labels": ["docs"],
        "dependencies": [],
    },
    {
        "item_id": "T-045",
        "title": "Add user-facing help documentation",
        "description": "In-app help articles with search, step-by-step guides for common workflows, and contextual help tooltips.",
        "priority": "MEDIUM",
        "story_points": 5,
        "labels": ["docs", "ui"],
        "dependencies": [],
    },
    {
        "item_id": "T-046",
        "title": "Implement caching layer with Redis",
        "description": "Cache frequently-accessed data (user sessions, project metadata, task lists) with TTL-based invalidation patterns.",
        "priority": "MEDIUM",
        "story_points": 3,
        "labels": ["infra", "performance"],
        "dependencies": [],
    },
    {
        "item_id": "T-047",
        "title": "Add database query optimization",
        "description": "Analyze slow queries with EXPLAIN, add missing indexes, denormalize hot-path data, and add N+1 query detection.",
        "priority": "MEDIUM",
        "story_points": 5,
        "labels": ["performance", "backend", "tech-debt"],
        "dependencies": [],
    },
    {
        "item_id": "T-048",
        "title": "Refactor monolithic API router into modules",
        "description": "Split the single router file into domain-specific modules (auth, tasks, projects, users) with shared middleware.",
        "priority": "MEDIUM",
        "story_points": 5,
        "labels": ["tech-debt", "backend"],
        "dependencies": [],
    },
    {
        "item_id": "T-049",
        "title": "Introduce dependency injection container",
        "description": "Replace global singletons with a DI container for services, repositories, and configuration to improve testability.",
        "priority": "MEDIUM",
        "story_points": 5,
        "labels": ["tech-debt", "backend"],
        "dependencies": [],
    },
    {
        "item_id": "T-050",
        "title": "Add TypeScript strict mode to frontend",
        "description": "Enable strict null checks, noImplicitAny, and strict function types; fix all resulting type errors across the codebase.",
        "priority": "MEDIUM",
        "story_points": 5,
        "labels": ["tech-debt", "frontend"],
        "dependencies": [],
    },
    {
        "item_id": "T-051",
        "title": "Fix mobile responsive layout on task board",
        "description": "Task board columns stack vertically on screens < 768px, cards overflow; implement horizontal scroll with sticky headers.",
        "priority": "MEDIUM",
        "story_points": 3,
        "labels": ["bug", "ui", "frontend"],
        "dependencies": [],
    },
    {
        "item_id": "T-052",
        "title": "Resolve timezone inconsistencies in due dates",
        "description": "All due dates stored as UTC but displayed in user local time inconsistently; add user timezone setting and conversion.",
        "priority": "MEDIUM",
        "story_points": 2,
        "labels": ["bug", "backend"],
        "dependencies": [],
    },
    {
        "item_id": "T-053",
        "title": "Add skeleton loading states to all views",
        "description": "Replace spinners with content-shaped skeleton screens on dashboard, task list, board, and profile pages.",
        "priority": "MEDIUM",
        "story_points": 3,
        "labels": ["ui", "frontend"],
        "dependencies": [],
    },
    {
        "item_id": "T-054",
        "title": "Implement infinite scroll for task lists",
        "description": "Replace pagination buttons with intersection-observer-based infinite scroll, prefetching next page when near bottom.",
        "priority": "MEDIUM",
        "story_points": 2,
        "labels": ["ui", "frontend", "performance"],
        "dependencies": ["T-012"],
    },
    {
        "item_id": "T-055",
        "title": "Add keyboard shortcuts for power users",
        "description": "Global hotkey system: 'n' for new task, '/' for search focus, 'j/k' for list navigation, '?' for shortcut overlay.",
        "priority": "MEDIUM",
        "story_points": 2,
        "labels": ["ui", "frontend"],
        "dependencies": [],
    },
    {
        "item_id": "T-056",
        "title": "Create reusable form components library",
        "description": "Build form primitives (TextInput, Select, DatePicker, Combobox) with validation, error states, and accessibility labels.",
        "priority": "MEDIUM",
        "story_points": 5,
        "labels": ["ui", "frontend", "tech-debt"],
        "dependencies": [],
    },
    {
        "item_id": "T-057",
        "title": "Add webhook integration support",
        "description": "Allow projects to register webhook URLs for events (task.created, task.completed) with retry and delivery logs.",
        "priority": "MEDIUM",
        "story_points": 5,
        "labels": ["api", "backend"],
        "dependencies": [],
    },
    {
        "item_id": "T-058",
        "title": "Implement data export (GDPR compliance)",
        "description": "Allow users to request full account data export as JSON archive; admins can trigger per-user exports for compliance.",
        "priority": "MEDIUM",
        "story_points": 3,
        "labels": ["api", "backend", "security"],
        "dependencies": [],
    },
    {
        "item_id": "T-059",
        "title": "Add rate limit headers and retry-after guidance",
        "description": "Include X-RateLimit-Remaining, X-RateLimit-Reset headers on all responses; document retry strategy in API docs.",
        "priority": "MEDIUM",
        "story_points": 2,
        "labels": ["api", "docs"],
        "dependencies": ["T-001"],
    },
    {
        "item_id": "T-060",
        "title": "Build team velocity analytics dashboard",
        "description": "Charts showing sprint-over-sprint velocity, completed vs committed ratio, and individual contribution breakdowns.",
        "priority": "MEDIUM",
        "story_points": 5,
        "labels": ["ui", "frontend", "api"],
        "dependencies": [],
    },
    {
        "item_id": "T-061",
        "title": "Add multi-language i18n support",
        "description": "Set up react-i18next with English and Spanish translations, locale detection, and a language switcher component.",
        "priority": "MEDIUM",
        "story_points": 5,
        "labels": ["ui", "frontend", "docs"],
        "dependencies": [],
    },
    {
        "item_id": "T-062",
        "title": "Implement undo/redo for task edits",
        "description": "Command-pattern-based undo history for task title, description, status, and assignee changes with Ctrl+Z/Ctrl+Y.",
        "priority": "MEDIUM",
        "story_points": 5,
        "labels": ["ui", "frontend"],
        "dependencies": ["T-013"],
    },
    {
        "item_id": "T-063",
        "title": "Add Docker Compose production configuration",
        "description": "Production-grade compose file with health checks, resource limits, restart policies, and secrets management.",
        "priority": "MEDIUM",
        "story_points": 2,
        "labels": ["infra"],
        "dependencies": [],
    },
    {
        "item_id": "T-064",
        "title": "Set up automated database backups",
        "description": "Daily pg_dump with S3 upload, 30-day retention, backup verification by restore-test, and failure alerts.",
        "priority": "MEDIUM",
        "story_points": 3,
        "labels": ["infra"],
        "dependencies": [],
    },
    {
        "item_id": "T-065",
        "title": "Add feature flag system",
        "description": "LaunchDarkly-style feature flags with percentage rollouts, user targeting, and runtime toggle without redeploy.",
        "priority": "MEDIUM",
        "story_points": 3,
        "labels": ["backend", "infra"],
        "dependencies": [],
    },
    {
        "item_id": "T-066",
        "title": "Implement user mention notifications",
        "description": "When @username appears in a comment, send an in-app and email notification to the mentioned user.",
        "priority": "MEDIUM",
        "story_points": 3,
        "labels": ["api", "backend"],
        "dependencies": ["T-034", "T-028"],
    },
    {
        "item_id": "T-067",
        "title": "Add breadcrumb navigation across all pages",
        "description": "Auto-generated breadcrumb trail showing hierarchy: Home > Project > Board with clickable segments.",
        "priority": "MEDIUM",
        "story_points": 1,
        "labels": ["ui", "frontend"],
        "dependencies": [],
    },
    {
        "item_id": "T-068",
        "title": "Create error boundary and fallback UI",
        "description": "React error boundaries at route and feature levels with retry button, error report submission, and graceful degradation.",
        "priority": "MEDIUM",
        "story_points": 2,
        "labels": ["ui", "frontend"],
        "dependencies": [],
    },
    {
        "item_id": "T-069",
        "title": "Fix accessibility violations (WCAG 2.1 AA)",
        "description": "Audit with axe-core, fix color contrast, add ARIA labels, ensure keyboard navigation, and add skip-to-content link.",
        "priority": "MEDIUM",
        "story_points": 3,
        "labels": ["ui", "frontend", "bug"],
        "dependencies": [],
    },
    {
        "item_id": "T-070",
        "title": "Add branch deployment previews per PR",
        "description": "Auto-deploy each PR to a unique subdomain for manual QA; comment PR with preview URL and tear down on merge.",
        "priority": "MEDIUM",
        "story_points": 3,
        "labels": ["infra"],
        "dependencies": ["T-009"],
    },
    # ── LOW priority (~30 items) ───────────────────────────────────────────────
    {
        "item_id": "T-071",
        "title": "Add dark mode to email templates",
        "description": "Update all transactional email templates to support prefers-color-scheme: dark with appropriate color inversion.",
        "priority": "LOW",
        "story_points": 2,
        "labels": ["ui", "frontend"],
        "dependencies": ["T-031", "T-028"],
    },
    {
        "item_id": "T-072",
        "title": "Create animated logo and favicon set",
        "description": "Design SVG logo with animation, generate favicon in all required sizes (16px–512px), and add PWA manifest icons.",
        "priority": "LOW",
        "story_points": 2,
        "labels": ["ui", "frontend"],
        "dependencies": [],
    },
    {
        "item_id": "T-073",
        "title": "Add confetti animation on task completion",
        "description": "Subtle confetti burst animation when marking a task as done, with a user preference toggle to disable.",
        "priority": "LOW",
        "story_points": 1,
        "labels": ["ui", "frontend"],
        "dependencies": [],
    },
    {
        "item_id": "T-074",
        "title": "Build custom emoji picker component",
        "description": "Emoji picker with recent, search, and category tabs for use in comments, task titles, and reactions.",
        "priority": "LOW",
        "story_points": 3,
        "labels": ["ui", "frontend"],
        "dependencies": [],
    },
    {
        "item_id": "T-075",
        "title": "Add task templates for common workflows",
        "description": "Predefined task templates (bug report, feature request, onboarding task) with default fields and checklists.",
        "priority": "LOW",
        "story_points": 2,
        "labels": ["feature"],
        "dependencies": ["T-013"],
    },
    {
        "item_id": "T-076",
        "title": "Implement project archiving and restore",
        "description": "Allow project owners to archive completed projects (read-only, hidden from default views) and restore them later.",
        "priority": "LOW",
        "story_points": 2,
        "labels": ["api", "backend"],
        "dependencies": [],
    },
    {
        "item_id": "T-077",
        "title": "Add weekly digest email of team activity",
        "description": "Automated email every Monday summarizing completed tasks, new assignments, and upcoming deadlines per project.",
        "priority": "LOW",
        "story_points": 3,
        "labels": ["api", "backend"],
        "dependencies": ["T-028", "T-013"],
    },
    {
        "item_id": "T-078",
        "title": "Create public project roadmap view",
        "description": "Optional public-facing roadmap page showing planned features with progress indicators and subscribe-for-updates.",
        "priority": "LOW",
        "story_points": 3,
        "labels": ["ui", "frontend", "api"],
        "dependencies": [],
    },
    {
        "item_id": "T-079",
        "title": "Add time tracking on tasks",
        "description": "Start/stop timer per task, manual time entry, daily/weekly time summaries, and optional billing rate configuration.",
        "priority": "LOW",
        "story_points": 5,
        "labels": ["feature", "api", "ui"],
        "dependencies": ["T-013"],
    },
    {
        "item_id": "T-080",
        "title": "Build Slack integration for notifications",
        "description": "Slack app with OAuth install, channel selection for notifications (task created, completed, mentioned), and slash commands.",
        "priority": "LOW",
        "story_points": 5,
        "labels": ["api", "backend"],
        "dependencies": ["T-057"],
    },
    {
        "item_id": "T-081",
        "title": "Create Microsoft Teams integration",
        "description": "Teams app manifest with bot notifications, tab with project overview, and messaging extension for task search.",
        "priority": "LOW",
        "story_points": 5,
        "labels": ["api", "backend"],
        "dependencies": ["T-057"],
    },
    {
        "item_id": "T-082",
        "title": "Add GitHub sync for task references",
        "description": "Auto-link GitHub commits/PRs that mention task IDs (#T-123) and update task status on PR merge.",
        "priority": "LOW",
        "story_points": 5,
        "labels": ["api", "backend"],
        "dependencies": [],
    },
    {
        "item_id": "T-083",
        "title": "Implement project templates (clone structure)",
        "description": "Allow creating projects from templates with predefined task lists, labels, and workflow stages.",
        "priority": "LOW",
        "story_points": 3,
        "labels": ["feature", "api", "ui"],
        "dependencies": ["T-013"],
    },
    {
        "item_id": "T-084",
        "title": "Add custom task statuses per project",
        "description": "Let project admins define custom workflow statuses beyond the defaults (todo/in-progress/done) with color and order.",
        "priority": "LOW",
        "story_points": 3,
        "labels": ["feature", "api", "ui"],
        "dependencies": ["T-013"],
    },
    {
        "item_id": "T-085",
        "title": "Build Gantt chart view for project timeline",
        "description": "Interactive Gantt chart showing task dependencies, milestones, and critical path with drag-to-reschedule.",
        "priority": "LOW",
        "story_points": 8,
        "labels": ["ui", "frontend"],
        "dependencies": ["T-036"],
    },
    {
        "item_id": "T-086",
        "title": "Write unit tests for utility functions",
        "description": "Achieve >90% coverage on shared utility modules: date formatting, validation helpers, string utils, and math functions.",
        "priority": "LOW",
        "story_points": 3,
        "labels": ["testing"],
        "dependencies": [],
    },
    {
        "item_id": "T-087",
        "title": "Add snapshot tests for UI components",
        "description": "Configure Jest snapshot testing for all presentational components to catch unintended visual regressions.",
        "priority": "LOW",
        "story_points": 3,
        "labels": ["testing", "frontend"],
        "dependencies": [],
    },
    {
        "item_id": "T-088",
        "title": "Create API client SDK (TypeScript)",
        "description": "Auto-generated TypeScript client from OpenAPI spec with typed methods, error handling, and pagination support.",
        "priority": "LOW",
        "story_points": 3,
        "labels": ["docs", "api"],
        "dependencies": ["T-043"],
    },
    {
        "item_id": "T-089",
        "title": "Write ADRs for major architecture decisions",
        "description": "Document 5-8 Architecture Decision Records covering database choice, auth strategy, caching approach, and API design.",
        "priority": "LOW",
        "story_points": 2,
        "labels": ["docs"],
        "dependencies": [],
    },
    {
        "item_id": "T-090",
        "title": "Add changelog and release notes automation",
        "description": "Generate changelog from conventional commits, publish release notes on GitHub, and notify subscribed users.",
        "priority": "LOW",
        "story_points": 2,
        "labels": ["docs", "infra"],
        "dependencies": ["T-009"],
    },
    {
        "item_id": "T-091",
        "title": "Create interactive API playground (Swagger UI)",
        "description": "Host Swagger UI at /api/docs with try-it-out enabled, auth token injection, and environment selector.",
        "priority": "LOW",
        "story_points": 2,
        "labels": ["docs", "api"],
        "dependencies": ["T-043"],
    },
    {
        "item_id": "T-092",
        "title": "Fix inconsistent button styling across pages",
        "description": "Audit all button variants (primary, secondary, danger, ghost) for consistent padding, font, and hover states.",
        "priority": "LOW",
        "story_points": 1,
        "labels": ["bug", "ui", "frontend"],
        "dependencies": [],
    },
    {
        "item_id": "T-093",
        "title": "Add image lazy loading optimization",
        "description": "Implement native lazy loading and blur-up placeholder technique for all user-uploaded images and avatars.",
        "priority": "LOW",
        "story_points": 1,
        "labels": ["performance", "frontend"],
        "dependencies": [],
    },
    {
        "item_id": "T-094",
        "title": "Set up Umami analytics (privacy-focused)",
        "description": "Self-hosted Umami for page views, event tracking, and referral sources with no cookies and GDPR compliance.",
        "priority": "LOW",
        "story_points": 2,
        "labels": ["infra"],
        "dependencies": [],
    },
    {
        "item_id": "T-095",
        "title": "Add PWA support with offline mode",
        "description": "Service worker for offline caching, install prompt, and background sync of queued actions when connectivity returns.",
        "priority": "LOW",
        "story_points": 5,
        "labels": ["ui", "frontend", "infra"],
        "dependencies": [],
    },
    {
        "item_id": "T-096",
        "title": "Create status page for service health",
        "description": "Public status page showing component uptime, incident history, and subscribe-to-alerts using statuspage-like UI.",
        "priority": "LOW",
        "story_points": 3,
        "labels": ["infra", "ui"],
        "dependencies": ["T-021"],
    },
    {
        "item_id": "T-097",
        "title": "Refactor CSS to use design tokens",
        "description": "Extract all hardcoded colors, spacing, and typography values into CSS custom properties with a token naming system.",
        "priority": "LOW",
        "story_points": 3,
        "labels": ["tech-debt", "frontend"],
        "dependencies": [],
    },
    {
        "item_id": "T-098",
        "title": "Add client-side search debouncing",
        "description": "Debounce search input by 300ms to reduce API calls; add AbortController to cancel in-flight requests on new input.",
        "priority": "LOW",
        "story_points": 1,
        "labels": ["performance", "frontend"],
        "dependencies": [],
    },
    {
        "item_id": "T-099",
        "title": "Fix broken pagination on filtered views",
        "description": "Applying a filter then paginating resets the filter; preserve query params across page navigation in the URL.",
        "priority": "LOW",
        "story_points": 2,
        "labels": ["bug", "backend"],
        "dependencies": [],
    },
    {
        "item_id": "T-100",
        "title": "Add system health check endpoint",
        "description": "GET /health returns JSON with database connectivity, Redis ping, disk space, and memory usage for orchestration.",
        "priority": "LOW",
        "story_points": 1,
        "labels": ["infra", "api"],
        "dependencies": [],
    },
]

# Priority ordering used for deterministic voting (AC5).
_PRIORITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}

# Task types that use async SSE streaming.
_ASYNC_TASKS = {"present_backlog"}

# In-flight SSE queues keyed by task_id (stateless between separate task calls — AC8).
_streams: dict[str, asyncio.Queue[dict[str, Any]]] = {}

# ── Pydantic models ───────────────────────────────────────────────────────────


class Task(BaseModel):
    task_id: str
    task_type: str
    session_ctx: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)


# ── Agent Card (AC1, AC2) ──────────────────────────────────────────────────────


@app.get("/.well-known/agent.json")
async def agent_card() -> dict:
    return {
        "name": AGENT_NAME,
        "description": "Reference Product Owner agent backed by a static backlog.",
        "role": "PRODUCT_OWNER",
        "capabilities": {
            "can_provide_backlog": True,
            "can_vote": True,
            "can_volunteer": False,
        },
        "endpoint": f"{AGENT_PUBLIC_URL}/a2a",
        "auth": {"scheme": _AUTH_SCHEME},
    }


# ── Auth guard (AC7) ──────────────────────────────────────────────────────────


def _check_auth(request: Request) -> None:
    """Reject calls whose auth scheme does not match the Agent Card declaration."""
    has_bearer = request.headers.get("authorization", "").lower().startswith("bearer ")
    if _AUTH_SCHEME == "none" and has_bearer:
        raise HTTPException(
            status_code=401,
            detail="Agent Card declares auth scheme 'none'; Bearer token not accepted.",
        )
    if _AUTH_SCHEME == "bearer" and not has_bearer:
        raise HTTPException(
            status_code=401,
            detail="Agent Card declares auth scheme 'bearer'; Authorization header required.",
        )


def _own_participant_id(session_ctx: dict[str, Any]) -> str | None:
    """Resolve this agent's participant_id by matching AGENT_NAME in participants list."""
    for p in (session_ctx.get("participants") or []):
        if p.get("name") == AGENT_NAME:
            return p.get("participant_id")
    return None


# ── Task endpoint (AC3) ────────────────────────────────────────────────────────


@app.post("/a2a/tasks")
async def receive_task(task: Task, request: Request, response: Response) -> dict:
    _check_auth(request)

    # Async: present_backlog streams progress via SSE before returning the items.
    if task.task_type in _ASYNC_TASKS:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        _streams[task.task_id] = queue
        asyncio.create_task(_run_present_backlog(task, queue))
        response.status_code = 202
        return {"task_id": task.task_id, "status": "working"}

    if task.task_type == "session_invite":
        import httpx
        async def auto_join():
            own_id = _own_participant_id(task.session_ctx)
            if own_id:
                session_id = task.session_ctx.get("session_id")
                platform_url = os.environ.get("PLATFORM_URL", "http://platform:8000")
                async with httpx.AsyncClient() as client:
                    try:
                        await client.post(
                            f"{platform_url}/sessions/{session_id}/join",
                            json={"participant_id": own_id}
                        )
                    except Exception as e:
                        print(f"Failed to auto-join: {e}")
        asyncio.create_task(auto_join())
        return {
            "task_id": task.task_id,
            "status": "completed",
            "artifact": {"ack": True},
        }

    # Simple acknowledgement messages — no session state required.
    if task.task_type in ("session_ready", "session_aborted", "acknowledge_assignment", "sprint_backlog"):
        return {
            "task_id": task.task_id,
            "status": "completed",
            "artifact": {"ack": True},
        }

    if task.task_type == "vote":
        return _handle_vote(task)

    if task.task_type == "confirm":
        return _handle_confirm(task)

    if task.task_type == "accept_plan":
        return _handle_accept_plan(task)

    raise HTTPException(400, f"Unsupported task type: {task.task_type}")


# ── Vote handler (AC5) ────────────────────────────────────────────────────────


def _handle_vote(task: Task) -> dict:
    """Deterministically cast dot votes using only session_ctx fields (AC5).

    Strategy: mirror each item's declared priority from session_ctx.backlog_items.
    Items not found in the backlog receive MEDIUM as a safe default.
    Same input always produces the same output — no randomness involved.
    """
    items: list[str] = task.payload.get("items", [])
    backlog_items: list[dict] = task.session_ctx.get("backlog_items") or []

    priority_map: dict[str, str] = {
        item["item_id"]: item.get("priority", "MEDIUM")
        for item in backlog_items
        if "item_id" in item
    }

    votes: dict[str, str] = {
        item_id: priority_map.get(item_id, "MEDIUM")
        for item_id in items
    }
    return {
        "task_id": task.task_id,
        "status": "completed",
        "artifact": {"votes": votes},
    }


# ── Confirm handler (AC6) ─────────────────────────────────────────────────────


def _handle_confirm(task: Task) -> dict:
    """Return confirmed=true only when session_ctx.selected_items is non-empty (AC6)."""
    selected_items = task.session_ctx.get("selected_items")
    confirmed = bool(selected_items)
    return {
        "task_id": task.task_id,
        "status": "completed",
        "artifact": {"confirmed": confirmed},
    }


# ── Accept-plan handler (US-36 AC1) ──────────────────────────────────────────


def _handle_accept_plan(task: Task) -> dict:
    """Accept the final sprint plan — return accepted=true if backlog non-empty.

    Receives the final sprint backlog in session_ctx (selected_items or
    backlog_items).  Deterministic: same input always produces the same output.
    """
    selected_items = task.session_ctx.get("selected_items")
    backlog_items = task.session_ctx.get("backlog_items")
    non_empty = bool(selected_items or backlog_items)
    return {
        "task_id": task.task_id,
        "status": "completed",
        "artifact": {"accepted": non_empty},
    }


# ── SSE stream endpoint ───────────────────────────────────────────────────────


@app.get("/a2a/tasks/{task_id}")
async def stream_task(task_id: str, request: Request) -> StreamingResponse:
    queue = _streams.get(task_id)
    if queue is None:
        raise HTTPException(404, f"unknown task_id: {task_id}")

    async def gen():
        try:
            while True:
                if await request.is_disconnected():
                    return
                event = await queue.get()
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("status") in ("completed", "failed"):
                    return
        finally:
            _streams.pop(task_id, None)

    return StreamingResponse(gen(), media_type="text/event-stream")


# ── present_backlog background task ──────────────────────────────────────────


async def _run_present_backlog(task: Task, queue: asyncio.Queue[dict[str, Any]]) -> None:
    """Simulate a long-running backlog fetch, then emit the static fixture (AC4)."""
    await queue.put(
        {
            "task_id": task.task_id,
            "status": "working",
            "progress": "loading backlog from source system",
        }
    )
    await asyncio.sleep(0.3)
    await queue.put(
        {
            "task_id": task.task_id,
            "status": "completed",
            "artifact": {"backlog": STATIC_BACKLOG},
        }
    )
