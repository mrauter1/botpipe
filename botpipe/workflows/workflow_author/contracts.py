"""Small semantic handoffs for the workflow author."""

from pydantic import BaseModel, Field, model_validator

from .validation import Validation


class Brief(BaseModel):
    purpose: str
    definitions: list[str]
    gates: list[str]
    scenarios: list[str]
    questions: list[str] = Field(default_factory=list)


class Build(BaseModel):
    reference: str
    notes: str = ""
    brief: Brief | None = None  # Revise a mistaken assumption, preserving the request.


class Review(BaseModel):
    ship: bool = Field(strict=True)
    findings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_verdict(self):
        if self.ship == bool(self.findings) or any(not f.strip() for f in self.findings):
            raise ValueError("Ship requires no findings; rejection requires concrete findings")
        return self


class WorkflowAuthorResult(BaseModel):
    reference: str | None
    shipped: bool
    rounds: int
    findings: list[str]
    brief: Brief
    candidate_root: str
    validation: Validation | None = None
