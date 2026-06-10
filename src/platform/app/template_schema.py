from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field


class ActionBase(BaseModel):
    pass


class PresentItemsAction(ActionBase):
    type: Literal["PRESENT_ITEMS"]
    source: str | None = None
    min_items: int | None = None
    max_items: int | None = None


class VoteAction(ActionBase):
    type: Literal["VOTE"]
    method: str | None = None


class SelectAction(ActionBase):
    type: Literal["SELECT"]
    constraint: str | None = None


class AssignAction(ActionBase):
    type: Literal["ASSIGN"]
    strategy: str | None = None
    fallback: str | None = None
    conflict_resolution: str | None = None
    timeout_ms: int | None = None


class ConfirmAction(ActionBase):
    type: Literal["CONFIRM"]
    requires_unanimous: bool | None = None
    quorum: float | None = None
    acceptor: str | None = None


class GenerateRecommendationAction(ActionBase):
    type: Literal["GENERATE_RECOMMENDATION"]
    strategy: str | None = None


class GenerateAssignmentAction(ActionBase):
    type: Literal["GENERATE_ASSIGNMENT"]
    strategy: str | None = None


class OpenDiscussionAction(ActionBase):
    type: Literal["OPEN_DISCUSSION"]
    context: Literal["recommendation", "assignment"] | None = None
    allowed_actions: list[str] | None = None
    timeout_seconds: int | None = None
    strategy: str | None = None
    fallback: str | None = None
    # ── Round-robin config (used when phase turn_order == ROUND_ROBIN) ──
    turn_timeout_seconds: int | None = None   # per-participant turn timeout (default 30)
    max_rounds: int | None = None             # max discussion rounds (default 5)
    synthesize_proposals: bool | None = None  # platform proposes new items after each round


Action = (
    PresentItemsAction
    | VoteAction
    | SelectAction
    | AssignAction
    | ConfirmAction
    | GenerateRecommendationAction
    | GenerateAssignmentAction
    | OpenDiscussionAction
)


class Phase(BaseModel):
    phase_id: str
    name: str
    description: str
    required_roles: list[str] | Literal["ALL"]
    actions: list[Action]
    turn_order: Literal["ROLE_FIRST", "ALL_PARALLEL", "ROUND_ROBIN", "FACILITATOR_LED"]
    duration_limit: int | None = None
    transition: Literal["AUTO", "TIMED", "MANUAL"] = "AUTO"


class ProcessTemplate(BaseModel):
    template_id: str
    name: str
    description: str
    phases: list[Phase]
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)


class TemplateValidationError(Exception):
    pass


def load_yaml_template(file_path: str) -> ProcessTemplate:
    """Load a YAML file, validate it against ProcessTemplate schema, and return it.
    
    AC7: Schema and validation errors are reported with the YAML file path and line number where possible.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            # We use SafeLoader.
            # To get line numbers, we'd ideally use a custom loader, but standard YAML parse errors have them.
            # For Pydantic validation errors, we map them as best as possible.
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = mark.line + 1 if mark else "unknown"
        raise TemplateValidationError(f"YAML parsing error in {file_path} at line {line}: {exc}") from exc

    try:
        if "ProcessTemplate" in data:
            data = data["ProcessTemplate"]
        return ProcessTemplate.model_validate(data)
    except Exception as exc:
        # Pydantic validation error
        raise TemplateValidationError(f"Validation error in {file_path}: {exc}") from exc
