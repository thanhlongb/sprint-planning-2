"""Goal-Driven Recommender Module (US-30).

TF-IDF cosine similarity between sprint goal and backlog item title+description,
combined with priority score, followed by greedy capacity-constrained selection.
"""

from __future__ import annotations

import logging
import os

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

log = logging.getLogger(__name__)

# Priority numeric mapping (AC4)
_PRIORITY_SCORE: dict[str, int] = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}

# Configurable weights via environment variables (AC6)
_ALPHA: float = float(os.getenv("RECOMMENDER_ALPHA", "0.7"))
_BETA: float = float(os.getenv("RECOMMENDER_BETA", "0.3"))


def recommend(
    backlog_items: list[dict],
    sprint_goal: str,
    total_capacity: int,
) -> list[dict]:
    """Rank backlog items by goal alignment and select under capacity (AC2, AC5, AC8).

    Args:
        backlog_items: List of dicts with at least 'title', 'description',
            'priority', and optionally 'story_points'.
        sprint_goal: Free-text sprint goal to match against.
        total_capacity: Total story-point capacity for the sprint.

    Returns:
        Selected items (with added 'score' and 'similarity' fields), ordered
        by descending score.  Items that did not fit under capacity are omitted.
    """
    # AC8: Empty backlog or zero capacity → empty list
    if not backlog_items or total_capacity <= 0:
        return []

    # ── Build text corpus ──
    item_texts: list[str] = [
        f"{item.get('title', '')} {item.get('description', '')}"
        for item in backlog_items
    ]
    corpus: list[str] = [sprint_goal] + item_texts  # sprint_goal at index 0

    # ── TF-IDF & cosine similarity (AC3) ──
    vectorizer = TfidfVectorizer(stop_words="english")
    tfidf_matrix = vectorizer.fit_transform(corpus)

    # Cosine similarity of sprint_goal (row 0) vs each item (rows 1..N)
    sims = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:]).flatten()

    # ── Score = α·similarity + β·priority_score (AC4) ──
    scored_items: list[dict] = []
    for idx, item in enumerate(backlog_items):
        similarity = float(sims[idx])
        priority_str = str(item.get("priority", "LOW")).upper()
        priority_score = float(_PRIORITY_SCORE.get(priority_str, 1))
        composite = _ALPHA * similarity + _BETA * priority_score

        scored_items.append({
            **item,
            "similarity": round(similarity, 4),
            "score": round(composite, 4),
        })

    # Sort by descending score
    scored_items.sort(key=lambda it: it["score"], reverse=True)

    # ── Greedy capacity-constrained selection (AC5, AC7) ──
    selected: list[dict] = []
    used_capacity: int = 0

    for item in scored_items:
        sp = item.get("story_points")
        sp = sp if isinstance(sp, int) and sp is not None else 1  # AC7: missing → 1
        if used_capacity + sp <= total_capacity:
            selected.append(item)
            used_capacity += sp

    log.info(
        "recommender selected=%d/%d capacity=%d/%d",
        len(selected), len(scored_items), used_capacity, total_capacity,
    )
    return selected
