from pydantic import BaseModel, ConfigDict, Field
from botpipe import Route, SELF


class RecommendationControl(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    selected_workflow: str = Field(min_length=1)
    candidate_set_id: str = Field(min_length=1)
    review_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)


RECOMMENDATION_ROUTES = {
    "recommendations_reviewed": Route.to(
        "publish_recommendation",
        summary="Independent verifier accepted the exact CandidateSet.",
        required_writes=(
            "workflow_optimization_candidates",
            "workflow_optimization_candidate_review",
        ),
    ),
    "recommendation_rework": Route.to(
        SELF,
        summary="Independent verifier requested bounded rework.",
        required_writes=(
            "workflow_optimization_candidates",
            "workflow_optimization_candidate_review",
        ),
    ),
}
__all__ = ["RecommendationControl", "RECOMMENDATION_ROUTES"]
