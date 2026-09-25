"""Child-capability dispatch protocol helpers for adaptive goals."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import (
    ActionCapabilityResult,
    ActionRequest,
    Blackboard,
    CapabilitySpec,
    MissionSpec,
    VerifierCapabilityResult,
)


def _dispatch_message(
    *,
    ctx,
    action: ActionRequest,
    mission: MissionSpec,
    blackboard: Blackboard,
    capability: CapabilitySpec | None,
) -> str:
    target_contracts = []
    criteria = mission.criterion_map()
    for criterion_id in action.target_criteria:
        criterion = criteria[criterion_id]
        state = blackboard.criteria[criterion_id]
        target_contract = {
            "id": criterion.id,
            "description": criterion.description,
            "required": criterion.required,
            "current_status": state.status,
            "verifier": criterion.verifier,
            "verification_mode": criterion.verification_mode,
            "rubric": [item.model_dump(mode="json") for item in criterion.rubric],
            "deterministic_rules": [
                rule.model_dump(mode="json")
                for rule in criterion.deterministic_rules
            ],
            "failure_policy": criterion.failure_policy,
        }

        # Repair/action workers benefit from exact prior verifier findings. A
        # verifier should instead judge the current subject independently so a
        # re-verification is not anchored by its own previous conclusion.
        if action.kind != "verifier":
            target_contract["previous_judgment"] = (
                state.judgment.model_dump(mode="json")
                if state.judgment is not None
                else None
            )
            target_contract["previous_runtime_reason"] = state.reason
            target_contract["previous_evidence"] = state.evidence

        target_contracts.append(target_contract)

    payload = {
        "mission_id": mission.id,
        "mission_objective": mission.objective,
        "mission_constraints": mission.constraints,
        "action": action.model_dump(mode="json"),
        "target_criteria": target_contracts,
        # Child workflows receive the minimum semantic contract they need.
        # Parent governance artifact locations are intentionally not disclosed.
        "capability": capability.model_dump(mode="json") if capability is not None else None,
    }
    return (
        "Execute the following bounded adaptive-goal action. Treat the JSON below "
        "as the action contract. Do not change the parent mission, criteria, "
        "rubrics, hard checks, or verification ledger. Complete only the requested "
        "action within your own workflow contract. For subjective verification, "
        "reason directly against every rubric item and ground findings in observable "
        "evidence; optional ratings are diagnostic only.\n\n"
        + json.dumps(payload, indent=2, ensure_ascii=False)
    )


def _child_result_summary(child_result: Any) -> tuple[str | None, str | None, str | None, str | None]:
    workflow_name = getattr(child_result, "workflow_name", None)
    run_id = getattr(child_result, "run_id", None)
    status = getattr(child_result, "status", None)
    terminal = getattr(child_result, "terminal", None)
    return (
        str(workflow_name) if workflow_name is not None else None,
        str(run_id) if run_id is not None else None,
        str(status) if status is not None else None,
        str(terminal) if terminal is not None else None,
    )


def _read_child_protocol_result(
    *,
    child_result: Any,
    capability: CapabilitySpec | None,
    action: ActionRequest,
) -> tuple[ActionCapabilityResult | None, VerifierCapabilityResult | None, str | None, str | None]:
    child_folder_raw = getattr(child_result, "workflow_folder", None)
    if child_folder_raw is None:
        return None, None, None, "child workflow result did not expose workflow_folder"

    child_folder = Path(child_folder_raw)
    if action.kind == "ad_hoc":
        artifact_name = "capability_result.json"
        expected_kind = "action"
    else:
        assert capability is not None
        artifact_name = capability.result_artifact or (
            "verification_result.json" if capability.kind == "verifier" else "capability_result.json"
        )
        expected_kind = capability.kind

    result_path = child_folder / artifact_name
    if not result_path.exists():
        return None, None, str(result_path), (
            f"child capability protocol artifact is missing: {result_path}"
        )

    try:
        if expected_kind == "verifier":
            result = VerifierCapabilityResult.model_validate_json(
                result_path.read_text(encoding="utf-8")
            )
            return None, result, str(result_path), None
        result = ActionCapabilityResult.model_validate_json(
            result_path.read_text(encoding="utf-8")
        )
        return result, None, str(result_path), None
    except Exception as exc:  # schema failures are parent-runtime failures, not model claims
        return None, None, str(result_path), (
            f"invalid child capability protocol artifact {result_path}: {exc}"
        )
