"""Generic bounded workspace action for the adaptive goal runtime.

This workflow is intentionally pre-authored. The adaptive orchestrator may use
it for unforeseen local work, but it may not generate/import new Botpipe Python
workflows during an active mission.

Security posture:
- workspace-write sandbox;
- no network;
- no external side effects;
- independent verifier;
- standard capability_result.json protocol.
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
    produce_verify_step,
)

from botpipe.core import Artifact
from botpipe.workflows.adaptive_goal.contracts import ActionCapabilityResult


_AD_HOC_POLICY = Policy(
    permission_mode=PermissionMode.FULL_AUTO_SANDBOXED,
    sandbox_mode=SandboxMode.WORKSPACE_WRITE,
    network=NetworkMode.NONE,
)


class AdHocExecutorWorkflow(Workflow):
    name = "ad_hoc_executor"

    producer_session = Session.fresh()
    verifier_session = Session.fresh()

    capability_result = Artifact.json(
        "{{ workflow.folder }}/capability_result.json",
        schema=ActionCapabilityResult,
        name="capability_result",
        required=True,
    )
    review = Artifact.md(
        "{{ workflow.folder }}/review.md",
        name="review",
        required=True,
    )

    execute = produce_verify_step(
        name="execute",
        producer_prompt=Prompt.inline(
            """
            ROLE
            You are a bounded ad-hoc execution worker inside the adaptive-goal
            runtime.

            REQUEST
            {{ message }}

            OBJECTIVE
            Complete the requested bounded workspace action using the tools
            available in the provider sandbox. Inspect the current workspace,
            write/edit files, run commands, or create temporary utilities when
            useful.

            HARD BOUNDARIES
            - Do not send email/messages.
            - Do not spend money or initiate purchases.
            - Do not change DNS, domains, production infrastructure, external
              accounts, permissions, credentials, or remote state.
            - Network access is disabled by policy.
            - Do not modify the parent adaptive-goal mission, capability
              registry, blackboard, or verification ledger.
            - Do not generate/import a new Botpipe workflow as a shortcut.
            - Keep work narrowly scoped to the requested action.

            RESULT PROTOCOL
            Write {{ workflow.folder }}/capability_result.json as
            ActionCapabilityResult:
            {
              "schema": "botpipe.adaptive-goal.action-result/v2",
              "status": "completed",
              "summary": "...",
              "evidence": ["..."],
              "changed_paths": ["relative/path", "..."],
              "metrics": {}
            }

            `changed_paths` is informative evidence only; the parent runtime
            independently invalidates existing verifier receipts using subject
            fingerprints.

            Perform useful local validation before returning.
            """.strip()
        ),
        verifier_prompt=Prompt.inline(
            """
            ROLE
            Independently verify the bounded ad-hoc action.

            READ
            - the original request in {{ message }}
            - {{ workflow.folder }}/capability_result.json
            - current workspace files and command/test output as needed

            ACCEPT only when:
            - the bounded requested action was actually completed;
            - the result artifact accurately describes the work/evidence;
            - no forbidden external side effect was attempted;
            - no parent adaptive-goal mission/registry/blackboard/ledger was
              modified;
            - the work is locally correct enough to be useful to the parent
              mission.

            If the work is incomplete or incorrect, choose needs_rework and write
            exact actionable feedback to {{ workflow.folder }}/review.md.

            Write {{ workflow.folder }}/review.md in all cases.
            """.strip()
        ),
        producer_writes=[capability_result],
        verifier_writes=[review],
        session=producer_session,
        verifier_session=verifier_session,
        policy=_AD_HOC_POLICY,
        routes={
            "accepted": Route.to(
                FINISH,
                required_writes=["capability_result", "review"],
                summary="The bounded ad-hoc action is complete and independently verified.",
            ),
            "needs_rework": Route.to(
                "execute",
                required_writes=["review"],
                summary="The bounded ad-hoc action requires local rework.",
            ),
        },
    )

    entry = execute
