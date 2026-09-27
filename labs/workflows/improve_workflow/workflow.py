"""One evidence-bound proposal, isolated implementation, and measured outcome."""

from __future__ import annotations

from pathlib import Path

from botpipe import Prompt, Provider, current_run, provider_budget, workflow
from botpipe_optimizer.candidate_validation import ValidationResult
from labs.workflows._shared import observe_workflow, prepare_selected_candidate_surface
from labs.workflows.optimizer_integration import (
    freeze_candidate_baseline,
    freeze_improvement_evaluation,
    revalidate_candidate_comparison,
    staged_workflow_reference,
    validate_candidate_and_compare,
    validate_materialized_handoff,
)

from .evaluation import evaluate_trial_plan, prepare_trial_arms, verify_trial_plan
from .models import (
    CandidateResult,
    ChangeReview,
    ImproveWorkflowParams,
    ImproveWorkflowResult,
)
from .proposals import propose_improvement


def _prepare_candidate(
    params: ImproveWorkflowParams, request: str = ""
) -> ImproveWorkflowResult:
    """Improve one observed workflow without modifying its authoritative source."""
    run = current_run()
    with provider_budget(
        max_turns=params.max_provider_turns,
        max_seconds=params.max_provider_seconds,
        turn_timeout_seconds=params.provider_timeout,
    ) as budget:
        evaluation_spec = None
        if params.evaluation_spec_path is not None:
            # Freeze executable success criteria before diagnosis or candidate
            # generation so later turns cannot move the measurement goalposts.
            frozen_evaluation = freeze_improvement_evaluation(
                workspace=str(run.workspace),
                evaluation_spec_path=params.evaluation_spec_path,
                staging_parent=str(run.folder / "evaluation-plan"),
                invocation_id=run.run_id,
            )
            evaluation_spec = frozen_evaluation["evaluation_spec_path"]
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
        baseline_files = {
            item["relative_path"]: item["surface_sha256"]
            for item in recommendation.baseline_manifest["files"]
        }
        handoff = {
            "baseline_files": baseline_files,
            "candidate_paths": sorted(baseline_files),
        }
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
                    "assessment": recommendation.assessment.model_dump(mode="json"),
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
                            "assessment": recommendation.assessment.model_dump(
                                mode="json"
                            ),
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
                    plan = recommendation.frozen_trial_plan
                    if params.execute_trials and plan is not None:
                        verify_trial_plan(plan)
                        if any(case["available"] for case in plan["cases"]):
                            arms = prepare_trial_arms(
                                candidate_workspace=candidate,
                                frozen_candidate=frozen,
                                staging_parent=str(folder / "trial-code"),
                            )
                            outcome.evaluation["trial_context"] = {
                                "arms": arms,
                                "reference": reference,
                            }
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


@workflow(name="improve_workflow", version="3")
def improve_workflow(
    params: ImproveWorkflowParams, request: str = ""
) -> ImproveWorkflowResult:
    """Investigate, author, then optionally measure one candidate on frozen cases."""
    result = _prepare_candidate(params, request)
    if not params.execute_trials or result.outcome != "candidate_ready":
        return result
    plan = result.recommendation.frozen_trial_plan
    candidate = result.candidate
    if plan is None or candidate is None:
        return result
    verify_trial_plan(plan)
    context = candidate.evaluation.get("trial_context")
    if context is None:
        reasons = [case["reason"] for case in plan["cases"] if not case["available"]]
        reason = "No trial case is executable. " + (
            "; ".join(reasons) or "No cases were proposed."
        )
        evaluation = {
            "schema": "botpipe.rubric-evaluation/v1",
            "evaluation": "rubric_trials",
            "plan_id": plan["plan_id"],
            "comparison": {"state": "inconclusive", "reason": reason},
            "trials": [],
            "pairs": [],
            "scope": plan["case_scope"],
            "automatic_promotion": False,
        }
        return result.model_copy(
            update={
                "outcome": "inconclusive",
                "summary": "Candidate passed checks and review, but evaluation is inconclusive. "
                + reason,
                "candidate": candidate.model_copy(update={"evaluation": evaluation}),
            }
        )
    evaluation = evaluate_trial_plan(
        plan=plan,
        arms=context["arms"],
        reference=context["reference"],
        max_repairs=params.max_grounding_repairs,
    )
    state = evaluation["comparison"]["state"]
    return result.model_copy(
        update={
            "outcome": state,
            "summary": f"The rubric comparison is {state} on the frozen evaluated cases; untested inputs are not assessed.",
            "candidate": candidate.model_copy(update={"evaluation": evaluation}),
        }
    )
