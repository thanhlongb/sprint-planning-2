# Shared Protocol Contracts

This folder holds the cross-service protocol contracts described in the design doc:

- A2A task envelope shapes
- Agent Card JSON Schema
- Backlog item exchange format
- Process Template YAML schema

Today these are documented inline in `../../docs/design-doc.md`. When concrete
schemas are extracted (e.g. JSON Schema, OpenAPI fragments, Pydantic models
shared across Python services), they live here as the single source of truth
that every service in the monorepo depends on.
