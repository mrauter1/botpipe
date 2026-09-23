"""One evidence-bound proposal, isolated implementation, and measured outcome."""

from __future__ import annotations

from pathlib import Path

from botpipe import Prompt, Provider, current_run, provider_budget, workflow
from botpipe_optimizer.candidate_validation import ValidationResult
from labs.workflows._shared import observe_workflow, prepare_selected_candidate_surface
from labs.workflows.optimizer_integration import (
    freeze_candidate_baseline,
    freeze_improvement_evaluation,
    load_optimizer_candidate_handoff,
    revalidate_candidate_comparison,
    staged_workflow_reference,
    validate_candidate_and_compare,
    validate_materialized_handoff,
)

from .models import (
    CandidateResult,
    ChangeReview,
    ImproveWorkflowParams,
    ImproveWorkflowResult,
)
from .proposals import propose_improvement


@workflow(name="improve_workflow", version="1")
def improve_workflow(
    params: ImproveWorkflowParams, request: str = ""
) -> ImproveWorkflowResult:
    """Improve one observed workflow without modifying its authoritative source."""
    run = current_run()
    with provider_budget(
        max_turns=params.max_provider_turns,
        max_seconds=params.max_provider_seconds,
        turn_timeout_seconds=params.provider_timeout,
    ) as budget:
        recommendation = propose_improvement(params, request)

        def result(outcome, summary, candidate=None):
            return ImproveWorkflowResult(
                selected_workflow=params.selected_workflow,
                outcome=outcome,
                summary=summary,
                recommendation=recommendation,
                candidate=candidate,
                provider_budget=budget.snapshot(),
            )

        proposals = recommendation.candidate_set
        if recommendation.review is not None and not recommendation.review.accepted:
            return result(
                "rejected", "The proposed change did not pass independent review."
            )
        if not proposals.candidates:
            return result(proposals.next_action, proposals.no_candidate_reason)

        proposal = proposals.candidates[0]
        contract = observe_workflow(params.selected_workflow)
        source_path = contract["source"]["path"]
        if not source_path:
            raise ValueError("selected workflow must expose an inspectable source file")
        handoff = load_optimizer_candidate_handoff(
            workspace=str(run.workspace),
            optimization_receipt_path=str(
                run.folder / "optimization_publication_receipt.json"
            ),
            candidate_id=proposal.candidate_id,
            expected_selected_workflow=contract["name"],
            selected_workflow_reference=params.selected_workflow,
            selected_workflow_source_path=source_path,
            allowed_kinds=("workflow",),
            max_evidence_bytes=params.max_evidence_bytes,
            max_snapshot_bytes=params.max_snapshot_bytes,
        )
        evaluation_spec = None
        if params.evaluation_spec_path is not None:
            frozen_evaluation = freeze_improvement_evaluation(
                workspace=str(run.workspace),
                evaluation_spec_path=params.evaluation_spec_path,
                staging_parent=str(run.folder / "evaluation-plan"),
                invocation_id=run.run_id,
            )
            evaluation_spec = frozen_evaluation["evaluation_spec_path"]

        feedback = None
        for revision in range(params.max_revisions + 1):
            folder = run.folder / "candidates" / str(revision + 1)
            candidate = prepare_selected_candidate_surface(
                source_path,
                str(folder / "workspace"),
                str(run.workspace),
                handoff["candidate_paths"],
            )
            validate_materialized_handoff(handoff, candidate.authoritative_hashes)
            relative_source = (
                Path(source_path).resolve().relative_to(candidate.repo_root).as_posix()
            )
            reference = staged_workflow_reference(
                params.selected_workflow,
                relative_source=relative_source,
                function=contract.get("function"),
            )
            frozen = freeze_candidate_baseline(
                candidate_workspace=candidate,
                selected_workflow=params.selected_workflow,
                staging_parent=str(folder / "frozen"),
                workspace=str(run.workspace),
            )
            builder = Provider(workspace=candidate.candidate_root)
            builder.run(
                Prompt.file("prompts/implement.md"),
                input={
                    "request": request,
                    "proposal": proposal.model_dump(mode="json"),
                    "baseline_root": str(candidate.baseline_root),
                    "allowed_paths": list(candidate.allowed_paths),
                    "feedback": feedback,
                },
            )
            measured = validate_candidate_and_compare(
                candidate_workspace=candidate,
                frozen_candidate=frozen,
                selected_workflow=reference,
                staging_parent=str(folder / "evaluation"),
                target_test_argv=params.target_test_argv,
                validation_timeout=params.validation_timeout,
                evaluation_spec_path=evaluation_spec,
                workspace=str(run.workspace),
                invocation_id=f"{run.run_id}:{revision + 1}",
            )
            validation = ValidationResult.model_validate(measured["validation"])
            changed = measured["candidate_manifest"]["changed_paths"]
            review = None
            if validation.success and changed:
                review = (
                    builder.with_config(session=None)
                    .query(
                        Prompt.file("prompts/review_change.md"),
                        input={
                            "request": request,
                            "proposal": proposal.model_dump(mode="json"),
                            "baseline_root": str(candidate.baseline_root),
                            "changed_paths": changed,
                            "validation": validation.model_dump(mode="json"),
                        },
                        returns=ChangeReview,
                    )
                    .value
                )
                measured = revalidate_candidate_comparison(
                    measured,
                    candidate_workspace=candidate,
                    frozen_candidate=frozen,
                    evaluation_spec_path=evaluation_spec,
                    workspace=str(run.workspace),
                    staging_parent=str(folder / "evaluation"),
                    invocation_id=f"{run.run_id}:{revision + 1}",
                )
            outcome = CandidateResult(
                root=str(candidate.candidate_root),
                changed_paths=changed,
                validation=validation,
                review=review,
                evaluation=measured["paired_evaluation"],
            )
            if not changed:
                return result(
                    "no_change", "The candidate did not change the workflow.", outcome
                )
            if validation.success and review is not None and review.accepted:
                comparison = outcome.evaluation["comparison"]["state"]
                if comparison == "not_evaluated":
                    return result(
                        "candidate_ready",
                        "The candidate passed checks and review; improvement has not been measured.",
                        outcome,
                    )
                return result(
                    comparison, f"The measured comparison is {comparison}.", outcome
                )
            feedback = {
                "validation": validation.model_dump(mode="json"),
                "review": None if review is None else review.model_dump(mode="json"),
            }
        return result(
            "rejected",
            "The candidate did not pass checks and review within the revision limit.",
            outcome,
        )
