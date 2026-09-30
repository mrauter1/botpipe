"""Python step handlers for the adaptive goal workflow."""

from __future__ import annotations

from .contracts import (
    ActionRecord,
    ActionRequest,
    AdaptiveGoalState,
    Blackboard,
    CapabilitySpec,
    CriterionState,
    DispatchResult,
    GlobalAuditDecision,
    VerificationLedger,
    required_criteria_pass,
    terminal_unsatisfied_criteria,
    utc_now,
    validate_registry_against_mission,
)
from .dispatch import (
    _child_result_summary,
    _dispatch_message,
    _read_child_protocol_result,
)
from .state import (
    _action_targets_are_legal,
    _capability_by_id,
    _load_blackboard,
    _load_ledger,
    _load_mission,
    _load_registry,
    _needs_preapproval,
    _reject_selected_action,
    _write_blackboard,
    _write_ledger,
    _write_status,
)
from .verification import (
    _apply_verifier_result,
    _explicit_invalidation,
    _expire_ttl_criteria,
    _final_report_text,
    _invalidate_changed_subjects,
    _prepare_completion_packet,
)


def _initialize(ctx):
    options = ctx.input
    assert options is not None
    validate_registry_against_mission(options.mission, options.registry)

    ctx.artifacts.mission.write_model(options.mission)
    ctx.artifacts.registry.write_model(options.registry)

    now = utc_now()
    blackboard = Blackboard(
        mission_id=options.mission.id,
        criteria={
            criterion.id: CriterionState()
            for criterion in options.mission.criteria
        },
        started_at=now,
        updated_at=now,
    )
    ctx.artifacts.blackboard.write_model(blackboard)
    ctx.artifacts.verification_ledger.write_model(VerificationLedger())
    ctx.state.status = "active"
    ctx.state.mission_id = options.mission.id
    _write_status(ctx, blackboard)
    ctx.open_session("orchestrator_session")
    return "ready"


def _validate_action(ctx):
    mission = _load_mission(ctx)
    registry = _load_registry(ctx)
    blackboard = _load_blackboard(ctx)
    action = ActionRequest.model_validate(ctx.artifacts.action_request.read_json())

    if action.kind == "blocked":
        reason = f"orchestrator reported blocked: {action.rationale}"
        if _reject_selected_action(ctx, blackboard, action, reason):
            return "reselect"
        return "blocked"

    capability = None
    rejection: str | None = None

    if action.kind in {"capability", "verifier"}:
        assert action.capability_id is not None
        try:
            capability = _capability_by_id(registry, action.capability_id)
        except ValueError as exc:
            rejection = str(exc)

        if capability is not None:
            expected_kind = "action" if action.kind == "capability" else "verifier"
            if capability.kind != expected_kind:
                rejection = (
                    f"action requested {action.kind!r} but registry capability "
                    f"{capability.id!r} has kind {capability.kind!r}"
                )

            if (
                rejection is None
                and _needs_preapproval(capability)
                and capability.id not in set(ctx.input.preapproved_capabilities)
            ):
                rejection = (
                    f"capability {capability.id!r} requires explicit preapproval "
                    f"because side_effect={capability.side_effect!r}"
                )

    if action.kind == "ad_hoc" and not ctx.input.ad_hoc_enabled:
        rejection = "orchestrator requested ad_hoc but ad_hoc_enabled is false"

    if rejection is None:
        rejection = _action_targets_are_legal(
            action=action,
            mission=mission,
            capability=capability,
        )

    if rejection is not None:
        if _reject_selected_action(ctx, blackboard, action, rejection):
            return "reselect"
        return "blocked"

    return "valid"


def _dispatch(ctx):
    mission = _load_mission(ctx)
    registry = _load_registry(ctx)
    blackboard = _load_blackboard(ctx)
    action = ActionRequest.model_validate(ctx.artifacts.action_request.read_json())

    capability: CapabilitySpec | None = None
    if action.kind in {"capability", "verifier"}:
        assert action.capability_id is not None
        capability = _capability_by_id(registry, action.capability_id)
        workflow_ref = capability.workflow
    elif action.kind == "ad_hoc":
        workflow_ref = ctx.input.ad_hoc_workflow
    else:  # validate_action handles blocked
        raise RuntimeError(f"dispatch received non-dispatchable action {action.kind!r}")

    message = _dispatch_message(
        ctx=ctx,
        action=action,
        mission=mission,
        blackboard=blackboard,
        capability=capability,
    )

    try:
        child = ctx.invoke_workflow(workflow_ref, message=message)
        child_workflow, child_run_id, child_status, child_terminal = _child_result_summary(child)
        action_result, verifier_result, result_path, protocol_error = _read_child_protocol_result(
            child_result=child,
            capability=capability,
            action=action,
        )
        dispatch_error = protocol_error
        if child_status != "success":
            dispatch_error = (
                f"child workflow ended with status={child_status!r}, "
                f"terminal={child_terminal!r}"
            )
        result = DispatchResult(
            action=action,
            child_workflow=child_workflow or workflow_ref,
            child_run_id=child_run_id,
            child_status=child_status,
            child_terminal=child_terminal,
            child_result_path=result_path,
            capability_result=action_result,
            verifier_result=verifier_result,
            dispatch_error=dispatch_error,
        )
    except Exception as exc:
        result = DispatchResult(
            action=action,
            child_workflow=workflow_ref,
            dispatch_error=f"child workflow invocation failed: {type(exc).__name__}: {exc}",
        )

    ctx.artifacts.dispatch_result.write_model(result)
    return "dispatched"


def _reconcile(ctx):
    mission = _load_mission(ctx)
    registry = _load_registry(ctx)
    blackboard = _load_blackboard(ctx)
    ledger = _load_ledger(ctx)
    dispatch_result = DispatchResult.model_validate(
        ctx.artifacts.dispatch_result.read_json()
    )
    action = dispatch_result.action

    before = {
        criterion_id: state.status
        for criterion_id, state in blackboard.criteria.items()
    }

    invalidated: list[str] = []
    for criterion_id in _invalidate_changed_subjects(ctx, mission, blackboard):
        if criterion_id not in invalidated:
            invalidated.append(criterion_id)
    for criterion_id in _expire_ttl_criteria(mission, blackboard):
        if criterion_id not in invalidated:
            invalidated.append(criterion_id)

    capability: CapabilitySpec | None = None
    if action.kind in {"capability", "verifier"} and action.capability_id:
        capability = _capability_by_id(registry, action.capability_id)

    if action.kind in {"capability", "ad_hoc"}:
        for criterion_id in _explicit_invalidation(blackboard, capability):
            if criterion_id not in invalidated:
                invalidated.append(criterion_id)

    verified: list[str] = []
    summary = dispatch_result.dispatch_error or "Child capability completed."
    outcome = "error" if dispatch_result.dispatch_error else "completed"

    if (
        action.kind == "verifier"
        and capability is not None
        and dispatch_result.verifier_result is not None
        and dispatch_result.dispatch_error is None
    ):
        try:
            verified = _apply_verifier_result(
                ctx=ctx,
                mission=mission,
                capability=capability,
                action=action,
                result=dispatch_result.verifier_result,
                blackboard=blackboard,
                ledger=ledger,
            )
            summary = dispatch_result.verifier_result.summary
            outcome = dispatch_result.verifier_result.status
        except Exception as exc:
            summary = f"verifier result reconciliation failed: {type(exc).__name__}: {exc}"
            outcome = "error"

    elif (
        action.kind in {"capability", "ad_hoc"}
        and dispatch_result.capability_result is not None
        and dispatch_result.dispatch_error is None
    ):
        summary = dispatch_result.capability_result.summary
        outcome = dispatch_result.capability_result.status

    after = {
        criterion_id: state.status
        for criterion_id, state in blackboard.criteria.items()
    }
    state_changed = before != after
    result_signal = False
    if dispatch_result.verifier_result is not None:
        result_signal = bool(
            dispatch_result.verifier_result.observations
            or dispatch_result.verifier_result.evidence
        )
    if dispatch_result.capability_result is not None:
        result_signal = result_signal or bool(
            dispatch_result.capability_result.evidence
            or dispatch_result.capability_result.changed_paths
        )
    progress = state_changed or result_signal

    blackboard.action_count += 1
    action_fingerprint = action.fingerprint()
    if action_fingerprint == blackboard.last_action_fingerprint:
        blackboard.same_action_repeats += 1
    else:
        blackboard.same_action_repeats = 1
        blackboard.last_action_fingerprint = action_fingerprint

    if progress:
        blackboard.consecutive_no_progress = 0
    else:
        blackboard.consecutive_no_progress += 1

    blackboard.recent_actions.append(
        ActionRecord(
            index=blackboard.action_count,
            action=action,
            child_workflow=dispatch_result.child_workflow,
            child_run_id=dispatch_result.child_run_id,
            outcome=outcome,
            summary=summary,
            invalidated_criteria=invalidated,
            verified_criteria=verified,
            progress=progress,
            at=utc_now(),
        )
    )
    if len(blackboard.recent_actions) > 100:
        blackboard.recent_actions = blackboard.recent_actions[-100:]

    _write_ledger(ctx, ledger)

    terminal_failures = terminal_unsatisfied_criteria(mission, blackboard)
    if terminal_failures:
        reason = (
            "Terminal mission criteria failed: "
            + ", ".join(sorted(terminal_failures))
        )
        blackboard.terminal_reason = reason
        ctx.state.status = "unsatisfied"
        ctx.state.last_reason = reason
        _write_blackboard(ctx, blackboard)
        return "unsatisfied"

    if required_criteria_pass(mission, blackboard):
        _write_blackboard(ctx, blackboard)
        return "candidate_complete"

    if blackboard.action_count >= ctx.input.max_actions:
        reason = f"Maximum adaptive actions reached: {ctx.input.max_actions}."
        blackboard.terminal_reason = reason
        ctx.state.status = "blocked"
        ctx.state.last_reason = reason
        _write_blackboard(ctx, blackboard)
        return "blocked"

    if blackboard.consecutive_no_progress >= ctx.input.max_consecutive_no_progress:
        reason = (
            "No mission progress for "
            f"{blackboard.consecutive_no_progress} consecutive actions."
        )
        blackboard.terminal_reason = reason
        ctx.state.status = "blocked"
        ctx.state.last_reason = reason
        _write_blackboard(ctx, blackboard)
        return "blocked"

    if blackboard.same_action_repeats >= ctx.input.max_same_action_repeats and not progress:
        reason = (
            f"The same action repeated {blackboard.same_action_repeats} times "
            "without progress."
        )
        blackboard.terminal_reason = reason
        ctx.state.status = "blocked"
        ctx.state.last_reason = reason
        _write_blackboard(ctx, blackboard)
        return "blocked"

    _write_blackboard(ctx, blackboard)
    return "continue"
