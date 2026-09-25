"""Verification, freshness, and completion helpers for adaptive goals."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .contracts import (
    ActionRequest,
    Blackboard,
    CapabilitySpec,
    MissionCriterion,
    MissionSpec,
    VerificationLedger,
    VerificationReceipt,
    VerifierCapabilityResult,
    evaluate_verification,
    fingerprint_paths,
    utc_now,
)
from .state import _criterion_by_id, _load_blackboard, _load_ledger, _load_mission


def _criterion_observed_paths(
    *,
    criterion: MissionCriterion,
    capability: CapabilitySpec,
    verifier_result: VerifierCapabilityResult,
) -> list[str]:
    # A verifier may broaden the subject it observed, but it may not narrow an
    # operator-authored freshness contract. Criterion paths take precedence over
    # capability defaults and provider-returned paths are unioned on top.
    baseline = list(criterion.observed_paths or capability.observed_paths)
    explicit = list(verifier_result.observed_paths.get(criterion.id) or [])
    result: list[str] = []
    for pattern in [*baseline, *explicit]:
        if pattern not in result:
            result.append(pattern)
    return result


def _expire_ttl_criteria(mission: MissionSpec, blackboard: Blackboard) -> list[str]:
    now = datetime.now(timezone.utc)
    invalidated: list[str] = []
    for criterion in mission.criteria:
        state = blackboard.criteria[criterion.id]
        if state.status != "pass" or criterion.ttl_seconds is None or state.verified_at is None:
            continue
        try:
            verified = datetime.fromisoformat(state.verified_at)
            if verified.tzinfo is None:
                verified = verified.replace(tzinfo=timezone.utc)
        except ValueError:
            state.status = "stale"
            state.reason = "Verifier timestamp could not be parsed."
            invalidated.append(criterion.id)
            continue
        if (now - verified).total_seconds() >= criterion.ttl_seconds:
            state.status = "stale"
            state.reason = f"Verification TTL expired after {criterion.ttl_seconds} seconds."
            invalidated.append(criterion.id)
    return invalidated


def _invalidate_changed_subjects(ctx, mission: MissionSpec, blackboard: Blackboard) -> list[str]:
    invalidated: list[str] = []
    root = Path(ctx.root)
    for criterion in mission.criteria:
        state = blackboard.criteria[criterion.id]
        if state.status != "pass":
            continue
        if not state.observed_paths or not state.subject_fingerprint:
            continue
        current = fingerprint_paths(root, state.observed_paths)
        if current != state.subject_fingerprint:
            state.status = "stale"
            state.reason = "Files observed by the last passing verifier changed."
            invalidated.append(criterion.id)
    return invalidated


def _explicit_invalidation(
    blackboard: Blackboard,
    capability: CapabilitySpec | None,
) -> list[str]:
    if capability is None or capability.kind != "action":
        return []
    invalidated: list[str] = []
    for criterion_id in capability.may_invalidate:
        state = blackboard.criteria[criterion_id]
        if state.status == "pass":
            state.status = "stale"
            state.reason = f"Action capability {capability.id!r} invalidates this verification."
            invalidated.append(criterion_id)
    return invalidated


def _apply_verifier_result(
    *,
    ctx,
    mission: MissionSpec,
    capability: CapabilitySpec,
    action: ActionRequest,
    result: VerifierCapabilityResult,
    blackboard: Blackboard,
    ledger: VerificationLedger,
) -> list[str]:
    if result.verifier_id != capability.id:
        raise ValueError(
            f"verifier result id {result.verifier_id!r} does not match dispatched "
            f"capability {capability.id!r}"
        )

    touched: list[str] = []
    root = Path(ctx.root)
    for criterion_id in action.target_criteria:
        criterion = _criterion_by_id(mission, criterion_id)
        state = blackboard.criteria[criterion_id]
        verification_id = f"v-{uuid4().hex[:16]}"
        observed_paths = _criterion_observed_paths(
            criterion=criterion,
            capability=capability,
            verifier_result=result,
        )
        fingerprint = fingerprint_paths(root, observed_paths)

        judgment = result.judgments.get(criterion_id)
        metrics = dict(result.observations.get(criterion_id, {}))

        if result.status == "blocked":
            verdict = "blocked"
            reason = result.summary or "Verifier was blocked."
        elif result.status == "failed":
            verdict = "blocked"
            reason = result.summary or "Verifier execution failed."
        else:
            verdict, reason = evaluate_verification(
                criterion,
                judgment=judgment,
                metrics=metrics,
            )

        criterion_evidence = list(result.evidence)
        if judgment is not None:
            for finding in judgment.findings:
                for item in finding.evidence:
                    if item not in criterion_evidence:
                        criterion_evidence.append(item)

        receipt = VerificationReceipt(
            verification_id=verification_id,
            criterion_id=criterion_id,
            verifier_id=capability.id,
            verdict=verdict,
            judgment=judgment,
            metrics=metrics,
            evidence=criterion_evidence,
            reason=reason,
            observed_paths=observed_paths,
            subject_fingerprint=fingerprint,
            verified_at=utc_now(),
        )
        ledger.receipts.append(receipt)

        state.status = verdict
        state.judgment = judgment
        state.metrics = metrics
        state.evidence = criterion_evidence
        state.reason = reason
        state.verifier_id = capability.id
        state.verification_id = verification_id
        state.verified_at = receipt.verified_at
        state.observed_paths = observed_paths
        state.subject_fingerprint = fingerprint
        touched.append(criterion_id)

    return touched


def _prepare_completion_packet(ctx) -> None:
    mission = _load_mission(ctx)
    blackboard = _load_blackboard(ctx)
    ledger = _load_ledger(ctx)
    lines = [
        "# Adaptive Goal Completion Packet",
        "",
        f"Mission: `{mission.id}`",
        "",
        "## Objective",
        "",
        mission.objective,
        "",
        "## Constraints",
        "",
    ]
    if mission.constraints:
        lines.extend(f"- {item}" for item in mission.constraints)
    else:
        lines.append("- none")
    lines.extend(["", "## Required Criteria", ""])
    for criterion in mission.criteria:
        state = blackboard.criteria[criterion.id]
        lines.extend(
            [
                f"### {criterion.id}",
                "",
                f"- Required: {criterion.required}",
                f"- Description: {criterion.description}",
                f"- Verification mode: {criterion.verification_mode}",
                f"- Status: {state.status}",
                f"- Verifier: {state.verifier_id or criterion.verifier}",
                f"- Verification id: {state.verification_id or 'none'}",
            ]
        )
        if state.judgment is not None:
            lines.extend(
                [
                    f"- Judgment: {state.judgment.verdict}",
                    f"- Judgment summary: {state.judgment.summary}",
                    f"- Reasoning: {state.judgment.reasoning}",
                    f"- Optional rating: {state.judgment.rating or 'none'}",
                    f"- Confidence: {state.judgment.confidence or 'none'}",
                ]
            )
            if state.judgment.findings:
                lines.append("- Rubric findings:")
                for finding in state.judgment.findings:
                    lines.append(
                        f"  - `{finding.rubric_item_id}` [{finding.status}]: {finding.reasoning}"
                    )
            if state.judgment.recommended_actions:
                lines.append("- Recommended actions:")
                lines.extend(f"  - {item}" for item in state.judgment.recommended_actions)
        if state.metrics:
            lines.append(
                f"- Objective observations: `{json.dumps(state.metrics, ensure_ascii=False, sort_keys=True)}`"
            )
        lines.extend(
            [
                f"- Evidence: {', '.join(state.evidence) if state.evidence else 'none'}",
                "",
            ]
        )
    lines.extend(
        [
            "## Verification Ledger",
            "",
            f"- Receipts: {len(ledger.receipts)}",
            f"- Ledger: `{ctx.artifacts.verification_ledger.path}`",
            "",
            "## Runtime",
            "",
            f"- Actions completed: {blackboard.action_count}",
            f"- Blackboard: `{ctx.artifacts.blackboard.path}`",
            "",
        ]
    )
    ctx.artifacts.completion_packet.write_text("\n".join(lines))


def _final_report_text(
    *,
    mission: MissionSpec,
    blackboard: Blackboard,
    status: str,
    reason: str,
) -> str:
    lines = [
        f"# Adaptive Goal {status.replace('_', ' ').title()}",
        "",
        f"Mission: `{mission.id}`",
        "",
        "## Objective",
        "",
        mission.objective,
        "",
        "## Result",
        "",
        reason,
        "",
        "## Criteria",
        "",
    ]
    for criterion in mission.criteria:
        state = blackboard.criteria[criterion.id]
        lines.append(
            f"- `{criterion.id}` [{state.status.upper()}] {criterion.description}"
        )
        if state.judgment is not None:
            lines.append(
                f"  - judgment: {state.judgment.verdict}; {state.judgment.summary}"
            )
            lines.append(f"  - reasoning: {state.judgment.reasoning}")
        if state.reason and (state.judgment is None or state.reason != state.judgment.reasoning):
            lines.append(f"  - runtime reason: {state.reason}")
    lines.extend(
        [
            "",
            "## Execution",
            "",
            f"- Actions: {blackboard.action_count}",
            f"- Consecutive no-progress actions: {blackboard.consecutive_no_progress}",
            f"- Same-action repeats: {blackboard.same_action_repeats}",
            "",
        ]
    )
    return "\n".join(lines)
