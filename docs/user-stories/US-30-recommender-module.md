# US-30: Goal-Driven Recommender Module

**Phase:** 2b — New Workflow (Post-May 25 Pivot)
**Reference:** [new-workflow-implementation.md](../plans/new-workflow-implementation.md), benchmark work (F1=0.2483 on TAWOS)

## Story
As the **platform**, I want an algorithmic recommender that produces a goal-aligned task group from the backlog so that the recommendation phase has a data-driven starting point for discussion.

## Acceptance Criteria
- [ ] AC1: Module lives at `src/platform/app/recommender.py`, separate from the phase orchestrator.
- [ ] AC2: Public interface: `recommend(backlog_items: list[dict], sprint_goal: str, total_capacity: int) -> list[dict]`. Returns ranked items with scores.
- [ ] AC3: Algorithm: TF-IDF cosine similarity between sprint goal text and each item's `title + description`.
- [ ] AC4: Composite score = `α · similarity + β · priority_score` where priority_score is HIGH=3, MEDIUM=2, LOW=1.
- [ ] AC5: Greedy selection under total capacity: add highest-scoring item, deduct story points, repeat until no item fits.
- [ ] AC6: Configurable via environment variables: `RECOMMENDER_STRATEGY` (default `tfidf`), `RECOMMENDER_ALPHA` (default `0.7`), `RECOMMENDER_BETA` (default `0.3`).
- [ ] AC7: Items without `story_points` are treated as story_points=1 (never excluded).
- [ ] AC8: Empty backlog or zero total_capacity returns empty list gracefully (no crash).
- [ ] AC9: All dependencies are in `pyproject.toml` (scikit-learn for TF-IDF).

## Out of Scope
- Embedding-based or hybrid strategies (env var reserved for future).
- Re-running recommendation on partial backlog changes (handled by discussion phase orchestrator).
- Real-time LLM-based recommendation.
