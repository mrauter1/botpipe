"""Small authoring helpers shared by explicit labs durable functions."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from botpipe import (
    Artifact,
    ArtifactHandle,
    Prompt,
    Session,
    activity,
    ask,
    current_run,
)


class LabPhaseDraft(BaseModel):
    """Structured producer result retained in the operation journal."""

    summary: str = Field(min_length=1)
    evidence_notes: list[str] = Field(default_factory=list)
    candidate_ids: list[str] = Field(default_factory=list)

    @field_validator("candidate_ids")
    @classmethod
    def unique_candidates(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("candidate_ids must be unique")
        return normalized


class LabPhaseOutcome(BaseModel):
    """Typed verifier decision used as the durable control-flow outcome."""

    outcome: Literal["accepted"]
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


class LabPhaseControl(LabPhaseOutcome):
    """A nonacceptance decision never requires facts that are still unavailable."""

    model_config = ConfigDict(extra="allow")
    outcome: Literal["needs_rework", "needs_replan", "question", "blocked", "failed"]
    question: str | None = None
    replan_reason: str | None = None


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
    verifier_operation_id: str
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
    def __init__(self, phase: str, outcome: LabPhaseOutcome):
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
        paths = [str(source.parent.relative_to(repo_root))]
    else:
        paths = [str(source.relative_to(repo_root))]
    return prepare_candidate_workspace(repo_root, paths, destination)


@activity(name="execute candidate validation")
def execute_candidate_validation(workspace, argv: Sequence[str], timeout: float):
    """Run configured argv against an isolated candidate overlay."""
    from botpipe_optimizer import evaluate_candidate_workspace

    return evaluate_candidate_workspace(workspace, argv, timeout=timeout)


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
    producer: Session,
    verifier: Session,
    producer_prompt: str,
    verifier_prompt: str,
    input: Mapping[str, Any],
    writes: Sequence[Artifact],
    reads: Sequence[Any] = (),
    provider_workspace: str | Path | None = None,
    returns: type[LabPhaseOutcome] = LabPhaseOutcome,
    replan_target: str | None = None,
) -> PhaseRun:
    """Run a journaled producer/validator pair and accept only evidenced output."""

    response_type = returns | LabPhaseControl
    expected = [str(item.name) for item in writes]
    feedback: dict[str, Any] | None = None
    previous_handles: tuple[Any, ...] = ()
    while True:
        phase_input = {**dict(input), "phase": phase, "required_artifacts": expected}
        if feedback is not None:
            phase_input["rework_feedback"] = feedback
        producer_result = producer.run(
            Prompt.file(producer_prompt),
            input=phase_input,
            reads=tuple(reads) + previous_handles,
            writes=tuple(writes),
            returns=LabPhaseDraft,
            name=f"{phase}.produce",
            retries=2,
            workspace=provider_workspace,
        )
        handles = tuple(producer_result.artifacts.values())
        captured = sorted(producer_result.artifacts.keys())
        missing = sorted(set(expected) - set(captured))
        if missing:
            raise ValueError(
                f"{phase} did not capture required artifacts: {', '.join(missing)}"
            )
        verification = verifier.run(
            Prompt.file(verifier_prompt),
            input={
                **dict(input),
                "phase": phase,
                "producer_result": producer_result.value.model_dump(mode="json"),
                "required_artifacts": expected,
                "rework_feedback": feedback,
            },
            reads=handles,
            returns=response_type,
            name=f"{phase}.verify",
            retries=2,
        )
        outcome = verification.value
        unknown = sorted(set(outcome.authoritative_artifacts) - set(captured))
        if unknown:
            raise ValueError(
                f"{phase} verifier cited uncaptured artifacts: {', '.join(unknown)}"
            )
        evidence = PhaseEvidence(
            name=phase,
            outcome=outcome.outcome,
            summary=outcome.summary,
            artifact_names=outcome.authoritative_artifacts or captured,
            candidate_ids=outcome.candidate_ids or producer_result.value.candidate_ids,
            producer_operation_id=producer_result.operation_id,
            verifier_operation_id=verification.operation_id,
            details=outcome.model_dump(mode="json"),
        )
        phase_run = PhaseRun(evidence=evidence, handles=handles)
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
            answer = ask(
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
    for phase in evidences:
        for candidate in phase.candidate_ids:
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
    "LabPhaseDraft",
    "LabPhaseOutcome",
    "LabPhaseRejected",
    "LabWorkflowResult",
    "PhaseEvidence",
    "PhaseRun",
    "ReplanRequired",
    "artifact",
    "execute_candidate_validation",
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
