"""Build an executable workflow package from the user's selected request."""

from __future__ import annotations

from pathlib import Path

from botpipe import Artifact, Provider, current_run, provider_budget, workflow
from labs.workflows._shared import (
    ReplanRequired,
    artifact,
    finish,
    observe_catalog,
    run_phase,
)

from .contracts import (
    RequestFramingPayload,
    WorkflowAuthorResult,
    WorkflowBuildPayload,
    WorkflowDesignPayload,
    WorkflowEvaluationPayload,
)
from .guidance import load_authoring_guidance
from .materialization import (
    WorkflowManifestValidationError,
    _revalidate_generated_workflow_validation,
    freeze_generated_workflow_candidate,
    materialize_generated_workflow_manifest,
    prepare_generated_workflow_candidate,
    validate_generated_workflow_candidate,
)
from .params import Params


def _build_workflow_package(
    params: Params, request: str = "", *, enforce_generated_test: bool = False
) -> WorkflowAuthorResult:
    """Execute the workflow idea to workflow package evidence workflow."""
    _producer = Provider(instructions=load_authoring_guidance())
    _reviewer = _producer.with_config(session=None)
    context = {
        "request": request,
        "parameters": params.model_dump(mode="json"),
        "enforce_generated_test": enforce_generated_test,
    }
    context["workflow_catalog"] = observe_catalog()
    run = current_run()
    completed = []
    prior_handles = ()
    build_cycle = 0
    frame_request_checkpoint = len(completed)
    frame_request_reads = prior_handles
    frame_request_context = dict(context)
    while True:
        try:
            phase_1 = run_phase(
                phase="frame_request",
                returns=RequestFramingPayload,
                replan_target="frame_request",
                producer=_producer,
                producer_prompt="prompts/frame_producer.md",
                input=context,
                reads=prior_handles,
                writes=(artifact("workflow_brief.md"),),
            )
            completed.append(phase_1)
            prior_handles = prior_handles + phase_1.handles
            design_workflow_checkpoint = len(completed)
            design_workflow_reads = prior_handles
            design_workflow_context = dict(context)
            while True:
                try:
                    phase_2 = run_phase(
                        phase="design_workflow",
                        returns=WorkflowDesignPayload,
                        replan_target="frame_request",
                        producer=_producer,
                        reviewer=_reviewer,
                        producer_prompt="prompts/design_producer.md",
                        reviewer_prompt="prompts/design_reviewer.md",
                        input=context,
                        reads=prior_handles,
                        writes=(
                            artifact("workflow_design.md"),
                            artifact("prompt_design.md"),
                        ),
                    )
                    completed.append(phase_2)
                    prior_handles = prior_handles + phase_2.handles
                    build_reads = prior_handles
                    build_validation_feedback = None
                    build_errors: list[str] = []
                    build_cycle += 1
                    for build_attempt in range(1, 4):
                        candidate = prepare_generated_workflow_candidate(
                            str(run.workspace),
                            str(
                                run.folder
                                / "generated-workflow-candidates"
                                / f"cycle-{build_cycle}-attempt-{build_attempt}"
                            ),
                            params.package_name,
                        )
                        frozen_candidate = freeze_generated_workflow_candidate(
                            candidate,
                            str(
                                run.folder
                                / "generated-workflow-execution"
                                / f"cycle-{build_cycle}-attempt-{build_attempt}"
                                / "frozen"
                            ),
                        )
                        build_input = {
                            **context,
                            "build_attempt": build_attempt,
                            "max_build_attempts": 3,
                        }
                        if build_validation_feedback is not None:
                            build_input["runtime_validation_feedback"] = (
                                build_validation_feedback
                            )
                        phase_3 = run_phase(
                            phase="build_package",
                            returns=WorkflowBuildPayload,
                            replan_target="design_workflow",
                            producer=_producer,
                            producer_prompt="prompts/build_producer.md",
                            input=build_input,
                            reads=build_reads,
                            writes=(
                                # Capture bytes first so malformed provider JSON can
                                # participate in the bounded manifest repair loop.
                                Artifact.text("workflow_package_manifest.json"),
                                artifact("implementation_notes.md"),
                            ),
                        )
                        manifest_handle = next(
                            handle
                            for handle in phase_3.handles
                            if str(handle.name) == "workflow_package_manifest"
                        )
                        try:
                            generated_candidate = (
                                materialize_generated_workflow_manifest(
                                    candidate,
                                    manifest_handle,
                                    params.package_name,
                                )
                            )
                        except WorkflowManifestValidationError as error:
                            build_errors = [str(error)]
                            build_validation_feedback = {
                                "summary": (
                                    "The generated workflow manifest could not be "
                                    "materialized."
                                ),
                                "manifest_validation": {
                                    "success": False,
                                    "error_type": type(error).__name__,
                                    "errors": build_errors,
                                },
                            }
                            build_reads = prior_handles + phase_3.handles
                            continue
                        generated_validation = validate_generated_workflow_candidate(
                            candidate,
                            frozen_candidate,
                            generated_candidate["workflow_reference"],
                            str(
                                run.folder
                                / "generated-workflow-execution"
                                / f"cycle-{build_cycle}-attempt-{build_attempt}"
                                / "validation"
                            ),
                            params.target_test_command,
                            manifest_diagnostics=generated_candidate[
                                "reference_errors"
                            ],
                            target_test_argv=params.target_test_argv,
                            enforce_generated_test=enforce_generated_test,
                        )
                        if generated_validation["validation"]["success"]:
                            break
                        build_errors = list(
                            generated_validation["validation"].get("errors", [])
                        )
                        build_validation_feedback = {
                            "summary": (
                                "The isolated generated candidate did not validate."
                            ),
                            "generated_candidate": generated_candidate,
                            "candidate_manifest": generated_validation[
                                "candidate_manifest"
                            ],
                            "candidate_evaluation": generated_validation["validation"],
                        }
                        build_reads = prior_handles + phase_3.handles
                    else:
                        raise ValueError(
                            "generated workflow did not validate after 3 build "
                            "attempts: " + "; ".join(build_errors)
                        )
                    completed.append(phase_3)
                    prior_handles = prior_handles + phase_3.handles
                    context["generated_candidate"] = generated_candidate
                    context["candidate_manifest"] = generated_validation[
                        "candidate_manifest"
                    ]
                    context["candidate_evaluation"] = generated_validation["validation"]
                    phase_4 = run_phase(
                        phase="evaluate_package",
                        returns=WorkflowEvaluationPayload,
                        replan_target="design_workflow",
                        producer=_producer,
                        reviewer=_reviewer,
                        producer_prompt="prompts/evaluate_producer.md",
                        reviewer_prompt="prompts/evaluate_reviewer.md",
                        input=context,
                        reads=prior_handles,
                        writes=(
                            artifact("workflow_evaluation.md"),
                            artifact("workflow_package_summary.json"),
                            artifact("workflow_next_action.md"),
                        ),
                    )
                    completed.append(phase_4)
                    prior_handles = prior_handles + phase_4.handles
                    break
                except ReplanRequired as change:
                    if change.target != "design_workflow":
                        raise
                    del completed[design_workflow_checkpoint:]
                    # Build and evaluation replans must not reduce a concrete
                    # candidate defect to a prose summary. Feed captured defect
                    # reports and exact runtime evidence through redesign, then
                    # rebuild a fresh isolated candidate.
                    prior_handles = design_workflow_reads + change.handles
                    rejected_candidate_evidence = {
                        key: context[key]
                        for key in (
                            "generated_candidate",
                            "candidate_manifest",
                            "candidate_evaluation",
                        )
                        if key in context
                    }
                    context = {
                        **design_workflow_context,
                        "replan_feedback": change.evidence.model_dump(mode="json"),
                        "replan_artifacts": [
                            str(handle.path) for handle in change.handles
                        ],
                    }
                    if rejected_candidate_evidence:
                        context["rejected_candidate_evidence"] = (
                            rejected_candidate_evidence
                        )
            break
        except ReplanRequired as change:
            if change.target != "frame_request":
                raise
            del completed[frame_request_checkpoint:]
            prior_handles = frame_request_reads + change.handles
            context = {
                **frame_request_context,
                "replan_feedback": change.evidence.model_dump(mode="json"),
                "replan_artifacts": [str(handle.path) for handle in change.handles],
            }
    # Final semantic review can pause. Check the actual package bytes again
    # before handing out the runtime's validation evidence.
    _revalidate_generated_workflow_validation(
        generated_validation,
        candidate_workspace=candidate,
        frozen_candidate=frozen_candidate,
    )
    result = finish("workflow_idea_to_workflow_package", completed)
    return WorkflowAuthorResult(
        **result.model_dump(mode="python"),
        package_name=params.package_name,
        candidate_root=generated_candidate["root"],
        package_path=str(
            Path(generated_candidate["root"])
            / ".botpipe"
            / "workflows"
            / params.package_name
        ),
        workflow_reference=generated_candidate["workflow_reference"],
        surface_boundary=frozen_candidate.boundary,
        files=generated_validation["candidate_manifest"]["files"],
        validation=generated_validation["validation"],
    )


@workflow(name="workflow_idea_to_workflow_package", version="4")
def WorkflowIdeaToWorkflowPackage(
    params: Params, request: str = "", *, enforce_generated_test: bool = False
) -> WorkflowAuthorResult:
    """Execute the SOP within one durable provider-turn budget."""
    with provider_budget(max_turns=params.max_provider_turns):
        return _build_workflow_package(
            params, request, enforce_generated_test=enforce_generated_test
        )


workflow_callable = WorkflowIdeaToWorkflowPackage

__all__ = ["WorkflowIdeaToWorkflowPackage", "workflow_callable"]
