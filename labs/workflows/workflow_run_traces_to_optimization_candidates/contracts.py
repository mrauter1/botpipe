"""Typed optimizer-v2 workflow result."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from botpipe_optimizer.evidence import EvidenceSnapshot
from botpipe_optimizer.records import CandidateReview, CandidateSet, PublicationReceipt


class OptimizationWorkflowResult(BaseModel):
    workflow_name: Literal["workflow_run_traces_to_optimization_candidates"] = (
        "workflow_run_traces_to_optimization_candidates"
    )
    outcome: Literal["completed"] = "completed"
    summary: str
    evidence_snapshot: EvidenceSnapshot
    candidate_set: CandidateSet
    review: CandidateReview | None = None
    receipt: PublicationReceipt
    provider_budget: dict[str, object]


__all__ = ["OptimizationWorkflowResult"]
