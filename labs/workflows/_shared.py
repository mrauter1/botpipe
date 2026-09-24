"""Small authoring helpers shared by explicit labs durable functions."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from botpipe import (
    Artifact,
    ArtifactHandle,
    Prompt,
    Provider,
    activity,
    ask_human,
    current_run,
)


class _LabPhaseResult(BaseModel):
    summary: str = Field(min_length=1)
    authoritative_artifacts: list[str] = Field(default_factory=list)
    candidate_ids: list[str] = Field(default_factory=list)
    validation_findings: list[str] = Field(default_factory=list)

    @field_validator("authoritative_artifacts", "candidate_ids")
    @classmethod
    def unique_values(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("reported identifiers must be unique")
        return normalized


class LabPhaseOutcome(_LabPhaseResult):
    """Base for a phase-specific producer result accepted by the workflow."""

    outcome: Literal["accepted"]


class LabPhaseControl(_LabPhaseResult):
    """A nonacceptance decision never requires facts that are still unavailable."""

    outcome: Literal["needs_rework", "needs_replan", "question", "blocked", "failed"]
    question: str | None = None
    replan_reason: str | None = None


class LabPhaseReview(_LabPhaseResult):
    """Independent judgment without reconstructing the producer's domain facts."""

    outcome: Literal["accepted"]


class PhaseEvidence(BaseModel):
    name: str
    outcome: Literal[
        "accepted",
        "needs_rework",
        "needs_replan",
        "question",
        "blocked",
        "failed",
    ]
    summary: str
    artifact_names: list[str]
    candidate_ids: list[str] = Field(default_factory=list)
    producer_operation_id: str
    review_operation_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class LabWorkflowResult(BaseModel):
    workflow_name: str
    outcome: Literal["completed"] = "completed"
    summary: str
    phases: list[PhaseEvidence]
    artifact_names: list[str]
    artifacts: dict[str, ArtifactHandle] = Field(default_factory=dict)
    artifact_paths: dict[str, str] = Field(default_factory=dict)
    candidate_ids: list[str] = Field(default_factory=list)

    @field_validator("artifacts", mode="before")
    @classmethod
    def restore_artifact_handles(cls, value: Any) -> dict[str, ArtifactHandle]:
        if not isinstance(value, Mapping):
            raise TypeError("artifacts must be a mapping")
        return {
            str(name): handle
            if isinstance(handle, ArtifactHandle)
            else ArtifactHandle.from_record(handle)
            for name, handle in value.items()
        }


class LabPhaseRejected(RuntimeError):
    def __init__(self, phase: str, outcome: LabPhaseOutcome | LabPhaseControl):
        self.phase = phase
        self.outcome = outcome
        super().__init__(
            f"{phase} verification returned {outcome.outcome}: {outcome.summary}"
        )


class ReplanRequired(RuntimeError):
    def __init__(self, target: str, phase: PhaseRun):
        self.target = target
        self.phase = phase
        self.evidence = phase.evidence
        self.handles = phase.handles
        super().__init__(f"{phase.evidence.name} requested replanning from {target}")


@dataclass(frozen=True, slots=True)
class PhaseRun:
    evidence: PhaseEvidence
    handles: tuple[Any, ...]
    value: LabPhaseOutcome | LabPhaseControl


def artifact(path: str, *, required: bool = True) -> Artifact:
    if path.endswith(".json"):
        return Artifact.json(path, required=required)
    if path.endswith(".md"):
        return Artifact.md(path, required=required)
    return Artifact.text(path, required=required)


@activity(retry_safe=True, name="read publication JSON")
def read_publication_json(
    handles: Sequence[ArtifactHandle], names: Sequence[str]
) -> dict[str, dict[str, Any]]:
    """Read immutable captured JSON handles for a deterministic publication gate."""

    by_name = {str(handle.name): handle for handle in handles}
    result: dict[str, dict[str, Any]] = {}
    for name in names:
        handle = by_name.get(name)
        if handle is None:
            raise FileNotFoundError(f"missing required publication artifact {name}")
        try:
            value = json.loads(handle.read_bytes())
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"{name} must contain a JSON object") from exc
        if not isinstance(value, dict):
            raise TypeError(f"{name} must contain a JSON object")
        result[name] = value
    return result


def observe_workflow(reference: str) -> dict[str, Any]:
    """Journal the callable/source contract used by a selected-workflow lab."""
    from botpipe.inspection import inspect_workflow

    context = current_run()
    return context.operation(
        "labs.inspect_workflow",
        {"reference": reference},
        lambda: inspect_workflow(reference, context.workspace),
        retry_safe=True,
        name="inspect selected workflow",
    )


@activity(retry_safe=True, name="prepare candidate surface")
def prepare_selected_candidate_surface(
    source_path: str,
    destination: str,
    preferred_root: str,
    candidate_paths: Sequence[str] = (),
):
    """Create an immutable baseline and editable allowlisted copy for one source file."""
    from botpipe_optimizer import prepare_candidate_workspace, repository_root_for

    repo_root = repository_root_for(source_path, preferred_root)
    source = Path(source_path).resolve()
    if candidate_paths:
        paths = list(candidate_paths)
    elif (source.parent / "__init__.py").is_file():
        paths = [source.parent.relative_to(repo_root).as_posix()]
    else:
        paths = [source.relative_to(repo_root).as_posix()]
    return prepare_candidate_workspace(repo_root, paths, destination)


@activity(retry_safe=True, name="validate workflow parameters")
def validate_selected_workflow_parameters(
    reference: str,
    workspace: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate a proposed invocation against the selected callable signature."""
    from botpipe.discovery import resolve_workflow
    from botpipe_optimizer import validate_workflow_parameters

    return validate_workflow_parameters(resolve_workflow(reference, workspace), payload)


@activity(retry_safe=True, name="validate evaluation cases")
def validate_selected_eval_manifest(
    reference: str,
    workspace: str,
    manifest: Mapping[str, Any],
):
    """Validate eval cases and their flat Params payloads against a selected callable."""
    from botpipe.discovery import resolve_workflow
    from botpipe_optimizer import validate_eval_case_manifest

    return validate_eval_case_manifest(resolve_workflow(reference, workspace), manifest)


def observe_catalog() -> list[dict[str, Any]]:
    """Journal the effective callable catalog used for portfolio decisions."""
    from botpipe.discovery import discover_workflows

    context = current_run()
    return context.operation(
        "labs.discover_workflows",
        {"include_labs": True},
        lambda: [
            entry.to_dict()
            for entry in discover_workflows(context.workspace, include_labs=True)
        ],
        retry_safe=True,
        name="inspect workflow catalog",
    )


def observe_run_history(
    workflow_name: str | None = None,
    *,
    statuses: Sequence[str] = (),
    limit: int = 25,
    task_ids: Sequence[str] = (),
) -> list[dict[str, Any]]:
    """Journal bounded run inspection data; absent runs remain an explicit empty list."""
    context = current_run()

    def collect():
        selected = []
        allowed_statuses = set(statuses)
        allowed_tasks = set(task_ids)
        for summary in context.client.runs():
            record = summary if isinstance(summary, dict) else vars(summary)
            if (
                workflow_name
                and (record.get("workflow_name") or record.get("workflow"))
                != workflow_name
            ):
                continue
            if allowed_statuses and record.get("status") not in allowed_statuses:
                continue
            if allowed_tasks and record.get("task_id") not in allowed_tasks:
                continue
            selected.append(context.client.inspect(str(record["run_id"])))
            if len(selected) >= limit:
                break
        return selected

    return context.operation(
        "labs.observe_run_history",
        {
            "workflow_name": workflow_name,
            "statuses": list(statuses),
            "limit": limit,
            "task_ids": list(task_ids),
        },
        collect,
        retry_safe=True,
        name="inspect durable run history",
    )


def run_phase(
    *,
    phase: str,
    producer: Provider,
    producer_prompt: str,
    input: Mapping[str, Any],
    writes: Sequence[Artifact],
    reads: Sequence[Any] = (),
    provider_workspace: str | Path | None = None,
    returns: type[LabPhaseOutcome] = LabPhaseOutcome,
    reviewer: Provider | None = None,
    reviewer_prompt: str | None = None,
    replan_target: str | None = None,
) -> PhaseRun:
    """Produce a typed phase handoff, with independent review only when useful."""

    response_type = returns | LabPhaseControl
    expected = [str(item.name) for item in writes]
    producer_config: dict[str, Any] = {
        "name": f"{phase}.produce",
        "output_retries": 2,
    }
    if provider_workspace is not None:
        producer_config["workspace"] = provider_workspace
    phase_producer = producer.with_config(**producer_config)
    if (reviewer is None) != (reviewer_prompt is None):
        raise ValueError("reviewer and reviewer_prompt must be supplied together")
    phase_reviewer = (
        reviewer.with_config(name=f"{phase}.review", output_retries=2)
        if reviewer is not None
        else None
    )
    feedback: dict[str, Any] | None = None
    previous_handles: tuple[Any, ...] = ()
    while True:
        phase_input = {**dict(input), "phase": phase, "required_artifacts": expected}
        if feedback is not None:
            phase_input["rework_feedback"] = feedback
        producer_result = phase_producer.run(
            Prompt.file(producer_prompt),
            input=phase_input,
            reads=tuple(reads) + previous_handles,
            writes=tuple(writes),
            returns=response_type,
        )
        handles = tuple(producer_result.artifacts.values())
        captured = sorted(producer_result.artifacts.keys())
        missing = sorted(set(expected) - set(captured))
        if missing:
            raise ValueError(
                f"{phase} did not capture required artifacts: {', '.join(missing)}"
            )
        outcome = producer_result.value
        review_operation_id: str | None = None
        review_details: dict[str, Any] | None = None
        if outcome.outcome == "accepted" and phase_reviewer is not None:
            review = phase_reviewer.query(
                Prompt.file(str(reviewer_prompt)),
                input={
                    **dict(input),
                    "phase": phase,
                    "producer_result": outcome.model_dump(mode="json"),
                    "required_artifacts": expected,
                },
                reads=handles,
                returns=LabPhaseReview | LabPhaseControl,
            )
            outcome = review.value
            review_operation_id = review.operation_id
            review_details = outcome.model_dump(mode="json")
        unknown = sorted(set(outcome.authoritative_artifacts) - set(captured))
        if unknown:
            raise ValueError(
                f"{phase} review cited uncaptured artifacts: {', '.join(unknown)}"
            )
        evidence = PhaseEvidence(
            name=phase,
            outcome=outcome.outcome,
            summary=outcome.summary,
            artifact_names=outcome.authoritative_artifacts or captured,
            candidate_ids=producer_result.value.candidate_ids,
            producer_operation_id=producer_result.operation_id,
            review_operation_id=review_operation_id,
            details={
                **producer_result.value.model_dump(mode="json"),
                **(review_details or {}),
            },
        )
        phase_run = PhaseRun(
            evidence=evidence,
            handles=handles,
            value=producer_result.value,
        )
        if outcome.outcome == "accepted":
            return phase_run
        if outcome.outcome == "needs_rework":
            feedback = outcome.model_dump(mode="json")
            previous_handles = handles
            continue
        if outcome.outcome == "needs_replan":
            if not replan_target:
                raise ValueError(
                    f"{phase} returned needs_replan without a replan_target"
                )
            raise ReplanRequired(replan_target, phase_run)
        if outcome.outcome in {"question", "blocked"}:
            answer = ask_human(
                f"{phase}: {outcome.summary}\n"
                + (
                    outcome.question
                    or "Provide the missing prerequisite or instructions to continue."
                ),
            )
            feedback = {
                **outcome.model_dump(mode="json"),
                "input_answer": answer,
            }
            previous_handles = handles
            continue
        raise LabPhaseRejected(phase, outcome)


def finish(
    workflow_name: str,
    phases: Sequence[PhaseRun],
    *,
    additional_artifacts: Sequence[str] = (),
) -> LabWorkflowResult:
    artifacts: list[str] = []
    artifact_handles: dict[str, ArtifactHandle] = {}
    artifact_paths: dict[str, str] = {}
    candidates: list[str] = []
    evidences = [phase.evidence for phase in phases]
    for evidence in evidences:
        for candidate in evidence.candidate_ids:
            if candidate not in candidates:
                candidates.append(candidate)
    for phase in phases:
        for handle in phase.handles:
            name = str(handle.name)
            if name not in artifacts:
                artifacts.append(name)
            artifact_handles[name] = handle
            artifact_paths[name] = str(handle.path)
    for name in additional_artifacts:
        if name not in artifacts:
            artifacts.append(name)
    return LabWorkflowResult(
        workflow_name=workflow_name,
        summary=evidences[-1].summary,
        phases=evidences,
        artifact_names=artifacts,
        artifacts=artifact_handles,
        artifact_paths=artifact_paths,
        candidate_ids=candidates,
    )


__all__ = [
    "LabPhaseControl",
    "LabPhaseOutcome",
    "LabPhaseReview",
    "LabPhaseRejected",
    "LabWorkflowResult",
    "PhaseEvidence",
    "PhaseRun",
    "ReplanRequired",
    "artifact",
    "finish",
    "observe_catalog",
    "observe_run_history",
    "observe_workflow",
    "prepare_selected_candidate_surface",
    "read_publication_json",
    "run_phase",
    "validate_selected_eval_manifest",
    "validate_selected_workflow_parameters",
]
