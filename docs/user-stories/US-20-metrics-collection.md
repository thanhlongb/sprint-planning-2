# US-20: Evaluation Metrics Collection

**Phase:** 4 — Evaluation & Paper
**Reference:** [design-doc.md §15](../design-doc.md#15-evaluation-metrics)

## Story
As a **researcher**, I want each of the five evaluation metrics measured and reported so that the platform's claimed contributions are testable.

## Acceptance Criteria
- AC1: **Openness** — count of distinct agent harnesses (e.g. Claude, LangChain, AutoGen) successfully integrated; record time-to-first-session for each.
- AC2: **Scalability** — latency / throughput / success-rate results from [US-17](US-17-scalability-testing.md) are summarised.
- AC3: **Process Flexibility** — count of distinct templates executed in real sessions; user satisfaction with customisation captured via a short survey to template authors.
- AC4: **Human-AI Interaction Quality** — task completion rate, Likert means / medians, and qualitative themes from [US-19](US-19-human-ai-study.md) interviews.
- AC5: **Cross-Organisation Support** — a multi-tenant scenario test runs to completion with ≥ 3 organisations and is included in the report.
- AC6: All metrics are written up in `docs/eval/metrics-report.md` with method, results, and limitations sections.
- AC7: Raw data and analysis scripts are version-controlled alongside the report for reproducibility.

## Out of Scope
- Live metrics dashboard.
- Continuous evaluation after the paper deadline.
- Pre-registered hypothesis testing (exploratory study).
- Cost-per-session metric.
