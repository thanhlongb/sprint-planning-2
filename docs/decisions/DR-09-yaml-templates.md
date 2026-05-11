# DR-09: YAML-Based Process Templates

**Status**: Accepted
**Date**: 2026-05-12

## Context
As defined in US-09, the platform needs a way to decouple the process logic (phases, transitions, required roles) from the orchestrator source code. This allows for multi-org custom planning processes without changing the orchestration core.

## Decision
We have decided to:
1. Define a Pydantic schema for Process Templates that fully encapsulates phase definitions and turn orders.
2. Use PyYAML to load YAML configuration files and map Pydantic validation errors back to line numbers.
3. Store the validated templates as JSON inside PostgreSQL in a new `templates` table so the `session_service` and `phase_orchestrator` can retrieve them easily at runtime.
4. Completely refactor the `phase_orchestrator.py` to be a generic state-machine loop evaluating actions in sequence according to the template loaded from DB, instead of having four hard-coded methods.

## Consequences
- The orchestrator becomes completely template-agnostic.
- Any future action types will require changes in `phase_orchestrator`'s generic execution engine to handle new `action.type` strings.
- Pydantic models ensure templates are completely valid before they are committed to DB on startup, preventing runtime orchestrator crashes.
