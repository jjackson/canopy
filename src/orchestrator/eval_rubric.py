"""Generic rubric scorer — the math behind ACE's verdict-schema, decoupled from
ACE. Given per-dimension scores (produced by an LLM judge elsewhere) + weights,
compute a weighted overall and a tier. Feeds AgentClient.record_verdict.
"""
from __future__ import annotations


def score_rubric(
    dimensions: "list[dict]", *, pass_at: float = 70.0, warn_at: float = 50.0
) -> dict:
    """Weighted-average the dimensions and assign a tier.

    `dimensions`: ``[{"name": str, "score": float, "weight"?: float=1}, ...]``.
    Returns ``{"overall_score", "verdict": pass|warn|fail, "dimensions"}``.
    Raises ``ValueError`` for an empty rubric or non-positive total weight.
    """
    if not dimensions:
        raise ValueError("score_rubric requires at least one dimension")
    total_w = sum(d.get("weight", 1) for d in dimensions)
    if total_w <= 0:
        raise ValueError("total dimension weight must be > 0")
    overall = sum(d["score"] * d.get("weight", 1) for d in dimensions) / total_w
    tier = "pass" if overall >= pass_at else "warn" if overall >= warn_at else "fail"
    return {
        "overall_score": round(overall, 2),
        "verdict": tier,
        "dimensions": list(dimensions),
    }
