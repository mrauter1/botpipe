"""Adaptive verifier-driven goal runtime.

Static control graph:
    initialize -> orchestrate -> validate_action -> dispatch -> reconcile
        -> orchestrate | prepare_final_audit | finish_*
    prepare_final_audit -> final_audit -> final_gate
        -> finish_complete | orchestrate | finish_blocked

The semantic action graph is generated incrementally by the orchestrator. Child
workflows are pre-authored trusted capabilities; unforeseen local work is routed
through the pre-authored `ad_hoc_executor` workflow rather than generating and
importing new Botpipe Python at runtime.
"""

from __future__ import annotations

from botpipe import (
    FINISH,
    NetworkMode,
    PermissionMode,
    Policy,
    Prompt,
    Route,
    SandboxMode,
    Session,
    Workflow,
    python_step,
    step,
)
from botpipe.core import Artifact

from .contracts import (
    ActionRequest,
    AdaptiveGoalInput,
    AdaptiveGoalOutput,
    AdaptiveGoalState,
    Blackboard,
    CapabilityRegistry,
    DispatchResult,
    GlobalAuditDecision,
    MissionSpec,
    VerificationLedger,
)

from .action_handlers import (
    _dispatch,
    _initialize,
    _reconcile,
    _validate_action,
)
from .final_handlers import (
    _final_gate,
    _finish_blocked,
    _finish_complete,
    _finish_unsatisfied,
    _prepare_final_audit,
)
from .state import (
    _load_blackboard,
    _persist_final_audit_payload,
    _persist_orchestrator_payload,
)


_ORCHESTRATOR_POLICY = Policy(
    permission_mode=PermissionMode.FULL_AUTO_SANDBOXED,
    sandbox_mode=SandboxMode.READ_ONLY,
    network=NetworkMode.NONE,
)

_FINAL_AUDITOR_POLICY = Policy(
    permission_mode=PermissionMode.FULL_AUTO_SANDBOXED,
    sandbox_mode=SandboxMode.READ_ONLY,
    network=NetworkMode.NONE,
)


class AdaptiveGoalWorkflow(Workflow):
    """Goal-constrained, path-free orchestration on top of Botpipe."""

    name = "adaptive_goal"
    Input = AdaptiveGoalInput
    State = AdaptiveGoalState
    Output = AdaptiveGoalOutput

    orchestrator_session = Session.task()
    final_auditor_session = Session.fresh()

    mission = Artifact.json(
        "{{ workflow.folder }}/mission.json",
        schema=MissionSpec,
        name="mission",
        required=True,
    )
    registry = Artifact.json(
        "{{ workflow.folder }}/capabilities.json",
        schema=CapabilityRegistry,
        name="registry",
        required=True,
    )
    blackboard = Artifact.json(
        "{{ workflow.folder }}/blackboard.json",
        schema=Blackboard,
        name="blackboard",
        required=True,
    )
    verification_ledger = Artifact.json(
        "{{ workflow.folder }}/verification_ledger.json",
        schema=VerificationLedger,
        name="verification_ledger",
        required=True,
    )
    action_request = Artifact.json(
        "{{ workflow.folder }}/action_request.json",
        schema=ActionRequest,
        name="action_request",
        required=False,
    )
    dispatch_result = Artifact.json(
        "{{ workflow.folder }}/dispatch_result.json",
        schema=DispatchResult,
        name="dispatch_result",
        required=False,
    )
    status_report = Artifact.md(
        "{{ workflow.folder }}/status.md",
        name="status_report",
        required=False,
    )
    completion_packet = Artifact.md(
        "{{ workflow.folder }}/completion_packet.md",
        name="completion_packet",
        required=False,
    )
    global_audit = Artifact.json(
        "{{ workflow.folder }}/global_audit.json",
        schema=GlobalAuditDecision,
        name="global_audit",
        required=False,
    )
    final_report = Artifact.md(
        "{{ workflow.folder }}/final_report.md",
        name="final_report",
        required=False,
    )

    initialize = python_step(
        _initialize,
        name="initialize",
        writes=[mission, registry, blackboard, verification_ledger, status_report],
        routes={"ready": "orchestrate"},
    )

    orchestrate = step(
        Prompt.file("prompts/orchestrate.md"),
        name="orchestrate",
        session=orchestrator_session,
        control_schema=ActionRequest,
        writes=[action_request],
        reads=[mission, registry, blackboard, verification_ledger, status_report],
        after=_persist_orchestrator_payload,
        policy=_ORCHESTRATOR_POLICY,
        routes={
            "selected": Route.to(
                "validate_action",
                summary="A single next action has been selected.",
            )
        },
    )

    validate_action = python_step(
        _validate_action,
        name="validate_action",
        requires=[mission, registry, blackboard, action_request],
        writes=[blackboard, status_report],
        routes={
            "valid": "dispatch",
            "reselect": "orchestrate",
            "blocked": "finish_blocked",
        },
    )

    dispatch = python_step(
        _dispatch,
        name="dispatch",
        requires=[mission, registry, blackboard, action_request],
        writes=[dispatch_result],
        routes={"dispatched": "reconcile"},
    )

    reconcile = python_step(
        _reconcile,
        name="reconcile",
        requires=[mission, registry, blackboard, verification_ledger, dispatch_result],
        writes=[blackboard, verification_ledger, status_report],
        routes={
            "continue": "orchestrate",
            "candidate_complete": "prepare_final_audit",
            "unsatisfied": "finish_unsatisfied",
            "blocked": "finish_blocked",
        },
    )

    prepare_final_audit = python_step(
        _prepare_final_audit,
        name="prepare_final_audit",
        requires=[mission, blackboard, verification_ledger],
        writes=[completion_packet, blackboard, status_report],
        routes={"ready": "final_audit", "stale": "orchestrate"},
    )

    final_audit = step(
        Prompt.file("prompts/final_audit.md"),
        name="final_audit",
        session=final_auditor_session,
        control_schema=GlobalAuditDecision,
        reads=[mission, blackboard, verification_ledger, completion_packet],
        writes=[global_audit],
        after=_persist_final_audit_payload,
        policy=_FINAL_AUDITOR_POLICY,
        routes={
            "audited": Route.to(
                "final_gate",
                summary="The global mission audit produced a decision.",
            )
        },
    )

    final_gate = python_step(
        _final_gate,
        name="final_gate",
        requires=[mission, blackboard, global_audit],
        writes=[blackboard, status_report],
        routes={
            "complete": "finish_complete",
            "reopen": "orchestrate",
            "blocked": "finish_blocked",
        },
    )

    finish_complete = python_step(
        _finish_complete,
        name="finish_complete",
        requires=[mission, blackboard, verification_ledger, global_audit],
        writes=[blackboard, final_report, status_report],
        routes={"done": FINISH},
    )

    finish_unsatisfied = python_step(
        _finish_unsatisfied,
        name="finish_unsatisfied",
        requires=[mission, blackboard],
        writes=[blackboard, final_report, status_report],
        routes={"done": FINISH},
    )

    finish_blocked = python_step(
        _finish_blocked,
        name="finish_blocked",
        requires=[mission, blackboard],
        writes=[blackboard, final_report, status_report],
        routes={"done": FINISH},
    )

    entry = initialize

    @staticmethod
    def build_output(state: AdaptiveGoalState, ctx) -> AdaptiveGoalOutput:
        blackboard = Blackboard.model_validate(ctx.artifacts.blackboard.read_json())
        status = state.status
        if status not in {"complete", "unsatisfied", "blocked"}:
            status = "blocked"
        return AdaptiveGoalOutput(
            status=status,
            mission_id=blackboard.mission_id,
            action_count=blackboard.action_count,
            blackboard_path=str(ctx.artifacts.blackboard.path),
            verification_ledger_path=str(ctx.artifacts.verification_ledger.path),
            final_report_path=str(ctx.artifacts.final_report.path),
        )
