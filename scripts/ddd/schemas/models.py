"""Canonical Pydantic v2 schemas for demo-driven-development v2 (ddd-v2).

All models are defined here.  Import them from this module or from
``scripts.ddd.schemas`` (re-exported via ``__init__.py``).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# SP0.1 — WhyBrief schema
# ---------------------------------------------------------------------------


class Evidence(BaseModel):
    kind: Literal["documented", "implemented", "assumed"]
    ref: str


class SpineItem(BaseModel):
    id: str
    claim: str
    rationale: str
    evidence: list[Evidence] = []
    status: Literal["grounded", "gap"] = "gap"


class Gap(BaseModel):
    id: str
    type: Literal["RESEARCH", "CAPABILITY", "DECISION"]
    claim_ref: str
    detail: str
    proposed_action: str


class WhyBrief(BaseModel):
    schema_version: int = 1
    feature: str
    problem: str
    spine: list[SpineItem]
    gaps: list[Gap]


# ---------------------------------------------------------------------------
# SP0.2 — Remaining models
# ---------------------------------------------------------------------------


class Persona(BaseModel):
    name: str
    role: str
    color: str
    intro: str


class Scene(BaseModel):
    persona: str
    title: str
    show: str
    concept_claim: str
    provenance: str
    design_intent: str | None = None
    impressive_because: str | None = None


class UnifiedSpec(BaseModel):
    name: str
    narrative: str
    base_url: str
    auth: dict | None = None
    why_brief: str | None = None
    personas: dict[str, Persona]
    scenes: list[Scene]


class Dimension(BaseModel):
    score: float
    weight: float


class Verdict(BaseModel):
    schema_version: int = 1
    dimensions: dict[str, Dimension]
    overall_score: float
    verdict: Literal["pass", "warn", "fail", "blocked"]
    blocking_reason: str | None = None
    fix_recommendation: str | None = None


class Decision(BaseModel):
    model_config = {"populate_by_name": True}

    id: str
    prompt: str
    options: list[str]
    recommended: str
    class_: str = Field(alias="class")


class ReviewRequest(BaseModel):
    schema_version: int = 1
    run_id: str
    gate: str
    video: dict
    decisions: list[Decision]
    narration: list[dict]
    autonomous_audit: list[str] = []


class RunState(BaseModel):
    schema_version: int = 1
    run_id: str
    feature: str
    phase: Literal[
        "phase0", "spec", "render", "judged", "converged", "promoted"
    ] = "phase0"
    iteration: int = 0
    why_brief: str | None = None
    verdicts: dict[str, str] = {}
    findings: list[dict] = []
    pending_review: str | None = None
    last_actor: str | None = None
    last_actor_at: str | None = None
