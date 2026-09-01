"""State, legality, and orchestrator-output helpers for adaptive goals."""

from __future__ import annotations

from .contracts import (
    ActionRecord,
    ActionRequest,
    Blackboard,
    CapabilityRegistry,
    CapabilitySpec,
    GlobalAuditDecision,
    MissionCriterion,
    MissionSpec,
    VerificationLedger,
    utc_now,
)


def _load_mission(ctx) -> MissionSpec:
    return MissionSpec.model_validate(ctx.artifacts.mission.read_json())


def _load_registry(ctx) -> CapabilityRegistry:
    return CapabilityRegistry.model_validate(ctx.artifacts.registry.read_json())


def _load_blackboard(ctx) -> Blackboard:
    return Blackboard.model_validate(ctx.artifacts.blackboard.read_json())


def _write_blackboard(ctx, blackboard: Blackboard) -> None:
    blackboard.updated_at = utc_now()
    ctx.artifacts.blackboard.write_model(blackboard)
    _write_status(ctx, blackboard)


def _load_ledger(ctx) -> VerificationLedger:
    if not ctx.artifacts.verification_ledger.exists():
        return VerificationLedger()
    return VerificationLedger.model_validate(ctx.artifacts.verification_ledger.read_json())


def _write_ledger(ctx, ledger: VerificationLedger) -> None:
    ctx.artifacts.verification_ledger.write_model(ledger)


def _capability_by_id(registry: CapabilityRegistry, capability_id: str) -> CapabilitySpec:
    capability = registry.capability_map().get(capability_id)
    if capability is None:
        raise ValueError(f"unknown capability {capability_id!r}")
    return capability


def _criterion_by_id(mission: MissionSpec, criterion_id: str) -> MissionCriterion:
    criterion = mission.criterion_map().get(criterion_id)
    if criterion is None:
        raise ValueError(f"unknown criterion {criterion_id!r}")
    return criterion


def _write_status(ctx, blackboard: Blackboard) -> None:
    mission = _load_mission(ctx)
    lines = [
        "# Adaptive Goal Status",
        "",
        f"Mission: `{mission.id}`",
        "",
        mission.objective,
        "",
        "## Criteria",
        "",
    ]
    for criterion in mission.criteria:
        state = blackboard.criteria[criterion.id]
        required = "required" if criterion.required else "optional"
        lines.append(
            f"- `{criterion.id}` [{state.status.upper()}] {required}; "
            f"mode={criterion.verification_mode}: {criterion.description}"
        )
        if state.judgment is not None:
            rating = f"; rating={state.judgment.rating}/5" if state.judgment.rating else ""
            confidence = (
                f"; confidence={state.judgment.confidence}"
                if state.judgment.confidence
                else ""
            )
            lines.append(
                f"  - judgment: {state.judgment.verdict}{rating}{confidence}: "
                f"{state.judgment.summary}"
            )
            lines.append(f"  - reasoning: {state.judgment.reasoning}")
            for finding in state.judgment.findings:
                lines.append(
                    f"  - rubric `{finding.rubric_item_id}` [{finding.status}]: "
                    f"{finding.reasoning}"
                )
            if state.judgment.recommended_actions:
                lines.append("  - recommended next actions:")
                lines.extend(
                    f"    - {item}" for item in state.judgment.recommended_actions
                )
        if state.metrics:
            score_bits = []
            for key, value in sorted(state.metrics.items()):
                if isinstance(value, (str, int, float, bool)) or value is None:
                    score_bits.append(f"{key}={value!r}")
            if score_bits:
                lines.append(
                    f"  - objective observations: {', '.join(score_bits)}"
                )
        if state.reason and (
            state.judgment is None or state.reason != state.judgment.reasoning
        ):
            lines.append(f"  - runtime reason: {state.reason}")
        if state.verification_id:
            lines.append(f"  - verification: `{state.verification_id}`")
    lines.extend(
        [
            "",
            "## Runtime",
            "",
            f"- Actions: {blackboard.action_count}",
            f"- Consecutive no-progress actions: {blackboard.consecutive_no_progress}",
            f"- Same-action repeats: {blackboard.same_action_repeats}",
        ]
    )
    if blackboard.terminal_reason:
        lines.append(f"- Terminal reason: {blackboard.terminal_reason}")
    if blackboard.recent_actions:
        lines.extend(["", "## Recent Actions", ""])
        for item in blackboard.recent_actions[-15:]:
            lines.append(
                f"- #{item.index} `{item.action.kind}` "
                f"`{item.action.capability_id or 'ad-hoc'}` "
                f"-> {item.outcome}; progress={item.progress}: {item.summary}"
            )
    ctx.artifacts.status_report.write_text("\n".join(lines) + "\n")


def _persist_orchestrator_payload(ctx) -> None:
    if ctx.outcome is None:
        return
    action = ActionRequest.model_validate(ctx.outcome.payload)
    ctx.artifacts.action_request.write_model(action)


def _persist_final_audit_payload(ctx) -> None:
    if ctx.outcome is None:
        return
    decision = GlobalAuditDecision.model_validate(ctx.outcome.payload)
    ctx.artifacts.global_audit.write_model(decision)


def _reject_selected_action(ctx, blackboard: Blackboard, action: ActionRequest, reason: str) -> bool:
    """Record an illegal/unavailable orchestrator choice.

    Returns True when retry budgets permit another orchestration turn, False when
    the repeated invalid choices must terminally block the run.
    """

    blackboard.action_count += 1
    blackboard.consecutive_no_progress += 1
    fingerprint = action.fingerprint()
    if fingerprint == blackboard.last_action_fingerprint:
        blackboard.same_action_repeats += 1
    else:
        blackboard.last_action_fingerprint = fingerprint
        blackboard.same_action_repeats = 1

    blackboard.recent_actions.append(
        ActionRecord(
            index=blackboard.action_count,
            action=action,
            outcome="rejected",
            summary=reason,
            progress=False,
            at=utc_now(),
        )
    )
    if len(blackboard.recent_actions) > 100:
        blackboard.recent_actions = blackboard.recent_actions[-100:]

    blackboard.terminal_reason = None
    ctx.state.last_reason = reason

    limits = [
        (
            blackboard.action_count >= ctx.input.max_actions,
            f"Maximum adaptive actions reached: {ctx.input.max_actions}.",
        ),
        (
            blackboard.consecutive_no_progress >= ctx.input.max_consecutive_no_progress,
            "Too many consecutive no-progress/rejected actions: "
            f"{blackboard.consecutive_no_progress}.",
        ),
        (
            blackboard.same_action_repeats >= ctx.input.max_same_action_repeats,
            f"The same rejected action repeated {blackboard.same_action_repeats} times.",
        ),
    ]
    for reached, terminal_reason in limits:
        if reached:
            blackboard.terminal_reason = terminal_reason
            ctx.state.status = "blocked"
            ctx.state.last_reason = terminal_reason
            _write_blackboard(ctx, blackboard)
            return False

    _write_blackboard(ctx, blackboard)
    return True


def _action_targets_are_legal(
    *,
    action: ActionRequest,
    mission: MissionSpec,
    capability: CapabilitySpec | None,
) -> str | None:
    criteria = mission.criterion_map()
    unknown = [item for item in action.target_criteria if item not in criteria]
    if unknown:
        return f"action targets unknown mission criteria: {unknown}"

    if action.kind != "blocked" and not action.target_criteria:
        return f"action kind {action.kind!r} must target at least one criterion"

    if action.kind == "capability":
        if capability is None or capability.kind != "action":
            return "capability action requires a registered action capability"
        undeclared = [item for item in action.target_criteria if item not in capability.helps]
        if undeclared:
            return (
                f"capability {capability.id!r} does not declare that it helps "
                f"criteria: {undeclared}"
            )

    if action.kind == "verifier":
        if capability is None or capability.kind != "verifier":
            return "verifier action requires a registered verifier capability"
        for criterion_id in action.target_criteria:
            criterion = criteria[criterion_id]
            if criterion.verifier != capability.id:
                return (
                    f"criterion {criterion_id!r} is designated for verifier "
                    f"{criterion.verifier!r}, not {capability.id!r}"
                )
            if criterion_id not in capability.verifies:
                return (
                    f"verifier {capability.id!r} does not declare {criterion_id!r} "
                    "in its verifies contract"
                )

    return None


def _needs_preapproval(capability: CapabilitySpec) -> bool:
    return capability.preapproval_required or capability.side_effect in {
        "external_reversible",
        "external_irreversible",
    }
