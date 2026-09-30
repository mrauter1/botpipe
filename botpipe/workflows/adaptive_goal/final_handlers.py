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

def _prepare_final_audit(ctx):
    mission = _load_mission(ctx)
    blackboard = _load_blackboard(ctx)

    # Recheck freshness at the completion boundary. Reconcile normally does
    # this after every action, but finalization must not depend on timing.
    invalidated = _invalidate_changed_subjects(ctx, mission, blackboard)
    invalidated.extend(
        item for item in _expire_ttl_criteria(mission, blackboard)
        if item not in invalidated
    )
    if invalidated or not required_criteria_pass(mission, blackboard):
        _write_blackboard(ctx, blackboard)
        return "stale"

    _prepare_completion_packet(ctx)
    return "ready"


def _final_gate(ctx):
    mission = _load_mission(ctx)
    blackboard = _load_blackboard(ctx)
    decision = GlobalAuditDecision.model_validate(
        ctx.artifacts.global_audit.read_json()
    )

    if decision.status == "complete":
        invalidated = _invalidate_changed_subjects(ctx, mission, blackboard)
        invalidated.extend(
            item for item in _expire_ttl_criteria(mission, blackboard)
            if item not in invalidated
        )
        if invalidated or not required_criteria_pass(mission, blackboard):
            ctx.state.status = "active"
            ctx.state.last_reason = (
                "Verification freshness changed during finalization: "
                + ", ".join(sorted(set(invalidated)))
            )
            _write_blackboard(ctx, blackboard)
            return "reopen"
        return "complete"

    if decision.status == "reopen":
        known = mission.criterion_map()
        unknown = [item for item in decision.reopen_criteria if item not in known]
        if unknown:
            reason = f"global auditor attempted to reopen unknown criteria: {unknown}"
            blackboard.terminal_reason = reason
            ctx.state.status = "blocked"
            ctx.state.last_reason = reason
            _write_blackboard(ctx, blackboard)
            return "blocked"
        for criterion_id in decision.reopen_criteria:
            state = blackboard.criteria[criterion_id]
            state.status = "stale"
            state.reason = (
                decision.reason
                or decision.summary
                or "Global audit invalidated the prior local verification."
            )
        ctx.state.status = "active"
        ctx.state.last_reason = decision.reason or decision.summary
        _write_blackboard(ctx, blackboard)
        return "reopen"

    reason = decision.reason or decision.summary or "Global audit was blocked."
    blackboard.terminal_reason = reason
    ctx.state.status = "blocked"
    ctx.state.last_reason = reason
    _write_blackboard(ctx, blackboard)
    return "blocked"


def _finish_complete(ctx):
    mission = _load_mission(ctx)
    blackboard = _load_blackboard(ctx)
    audit = GlobalAuditDecision.model_validate(ctx.artifacts.global_audit.read_json())
    blackboard.terminal_reason = audit.summary
    ctx.state.status = "complete"
    ctx.state.last_reason = audit.summary
    _write_blackboard(ctx, blackboard)
    ctx.artifacts.final_report.write_text(
        _final_report_text(
            mission=mission,
            blackboard=blackboard,
            status="complete",
            reason=audit.summary,
        )
    )
    return "done"


def _finish_unsatisfied(ctx):
    mission = _load_mission(ctx)
    blackboard = _load_blackboard(ctx)
    reason = blackboard.terminal_reason or "A terminal mission criterion failed."
    ctx.state.status = "unsatisfied"
    ctx.state.last_reason = reason
    _write_blackboard(ctx, blackboard)
    ctx.artifacts.final_report.write_text(
        _final_report_text(
            mission=mission,
            blackboard=blackboard,
            status="unsatisfied",
            reason=reason,
        )
    )
    return "done"


def _finish_blocked(ctx):
    mission = _load_mission(ctx)
    blackboard = _load_blackboard(ctx)
    reason = blackboard.terminal_reason or ctx.state.last_reason or "Adaptive goal is blocked."
    ctx.state.status = "blocked"
    ctx.state.last_reason = reason
    _write_blackboard(ctx, blackboard)
    ctx.artifacts.final_report.write_text(
        _final_report_text(
            mission=mission,
            blackboard=blackboard,
            status="blocked",
            reason=reason,
        )
    )
    return "done"
