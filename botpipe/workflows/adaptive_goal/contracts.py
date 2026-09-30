"""Contracts and verification helpers for the adaptive goal runtime.

The adaptive runtime separates:
- immutable mission criteria and descriptive rubrics;
- trusted capability metadata;
- mutable runtime blackboard state;
- agent-selected actions;
- designated-verifier judgments/observations; and
- runtime-owned authority, coherence, freshness, and completion decisions.

For subjective criteria, the designated verifier owns the qualitative judgment.
The parent runtime does not manufacture truth by thresholding an LLM-invented
score. Optional ordinal ratings are diagnostic only. Deterministic rules remain
available for properties that are genuinely mechanical, and hybrid criteria can
combine qualitative judgment with true hard checks.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


SCHEMA_MISSION = "botpipe.adaptive-goal.mission/v2"
SCHEMA_REGISTRY = "botpipe.adaptive-goal.capabilities/v2"
SCHEMA_BLACKBOARD = "botpipe.adaptive-goal.blackboard/v2"
SCHEMA_ACTION_RESULT = "botpipe.adaptive-goal.action-result/v2"
SCHEMA_VERIFIER_RESULT = "botpipe.adaptive-goal.verifier-result/v2"
SCHEMA_RECEIPTS = "botpipe.adaptive-goal.verification-ledger/v2"


CriterionStatus = Literal["unknown", "pass", "fail", "stale", "blocked"]
FailurePolicy = Literal["repairable", "terminal_unsatisfied"]
CapabilityKind = Literal["action", "verifier"]
ActionKind = Literal["capability", "verifier", "ad_hoc", "blocked"]
SideEffectClass = Literal[
    "none",
    "workspace",
    "external_reversible",
    "external_irreversible",
]
VerificationMode = Literal["judgment", "deterministic", "hybrid"]
RubricImportance = Literal["gate", "major", "minor"]
FindingStatus = Literal[
    "satisfied",
    "partially_satisfied",
    "not_satisfied",
    "unknown",
]
JudgmentVerdict = Literal["satisfied", "not_satisfied", "insufficient_evidence"]
ConfidenceLevel = Literal["low", "medium", "high"]
RuleOperator = Literal[
    "eq",
    "ne",
    "gt",
    "ge",
    "lt",
    "le",
    "in",
    "not_in",
    "truthy",
    "falsy",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class DeterministicRule(StrictModel):
    """A hard rule for a genuinely mechanical verifier observation."""

    metric: str = "value"
    operator: RuleOperator = "truthy"
    value: Any = None

    @model_validator(mode="after")
    def validate_rule(self) -> "DeterministicRule":
        if not self.metric.strip():
            raise ValueError("deterministic metric must be non-empty")
        if self.operator in {"in", "not_in"} and not isinstance(
            self.value, (list, tuple, set, frozenset)
        ):
            raise ValueError(f"operator {self.operator!r} requires a sequence value")
        return self


class RubricItem(StrictModel):
    """One descriptive aspect the verifier must explicitly assess."""

    id: str
    description: str
    importance: RubricImportance = "major"
    guidance: str | None = None

    @model_validator(mode="after")
    def validate_item(self) -> "RubricItem":
        if not self.id.strip():
            raise ValueError("rubric item id must be non-empty")
        if not self.description.strip():
            raise ValueError(f"rubric item {self.id!r} description must be non-empty")
        if self.guidance is not None and not self.guidance.strip():
            raise ValueError(f"rubric item {self.id!r} guidance must be non-empty when provided")
        return self


class MissionCriterion(StrictModel):
    id: str
    description: str
    required: bool = True
    verifier: str
    verification_mode: VerificationMode = "judgment"
    rubric: list[RubricItem] = Field(default_factory=list)
    deterministic_rules: list[DeterministicRule] = Field(default_factory=list)
    failure_policy: FailurePolicy = "repairable"
    observed_paths: list[str] = Field(default_factory=list)
    ttl_seconds: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_criterion(self) -> "MissionCriterion":
        if not self.id.strip():
            raise ValueError("criterion id must be non-empty")
        if not self.description.strip():
            raise ValueError(f"criterion {self.id!r} description must be non-empty")
        if not self.verifier.strip():
            raise ValueError(f"criterion {self.id!r} verifier must be non-empty")

        rubric_ids = [item.id for item in self.rubric]
        if len(rubric_ids) != len(set(rubric_ids)):
            raise ValueError(f"criterion {self.id!r} rubric item ids must be unique")

        if self.verification_mode in {"judgment", "hybrid"} and not self.rubric:
            raise ValueError(
                f"criterion {self.id!r} mode {self.verification_mode!r} requires a descriptive rubric"
            )
        if self.verification_mode in {"deterministic", "hybrid"} and not self.deterministic_rules:
            raise ValueError(
                f"criterion {self.id!r} mode {self.verification_mode!r} requires deterministic_rules"
            )
        if self.verification_mode == "judgment" and self.deterministic_rules:
            raise ValueError(
                f"criterion {self.id!r} is judgment-only; use hybrid mode for hard rules"
            )
        if self.verification_mode == "deterministic" and self.rubric:
            raise ValueError(
                f"criterion {self.id!r} is deterministic-only; use hybrid mode for a rubric"
            )

        _validate_relative_patterns(
            self.observed_paths,
            field_name=f"criterion {self.id!r} observed_paths",
        )
        return self


class MissionSpec(StrictModel):
    schema: Literal["botpipe.adaptive-goal.mission/v2"] = SCHEMA_MISSION
    id: str
    objective: str
    constraints: list[str] = Field(default_factory=list)
    criteria: list[MissionCriterion]

    @model_validator(mode="after")
    def validate_mission(self) -> "MissionSpec":
        if not self.id.strip():
            raise ValueError("mission id must be non-empty")
        if not self.objective.strip():
            raise ValueError("mission objective must be non-empty")
        if not self.criteria:
            raise ValueError("mission requires at least one criterion")
        ids = [item.id for item in self.criteria]
        if len(ids) != len(set(ids)):
            raise ValueError("mission criterion ids must be unique")
        if not any(item.required for item in self.criteria):
            raise ValueError("mission requires at least one required criterion")
        return self

    def criterion_map(self) -> dict[str, MissionCriterion]:
        return {item.id: item for item in self.criteria}


class CapabilitySpec(StrictModel):
    id: str
    kind: CapabilityKind
    workflow: str
    description: str
    helps: list[str] = Field(default_factory=list)
    verifies: list[str] = Field(default_factory=list)
    observed_paths: list[str] = Field(default_factory=list)
    may_invalidate: list[str] = Field(default_factory=list)
    side_effect: SideEffectClass = "none"
    preapproval_required: bool = False
    result_artifact: str | None = None
    cost_class: Literal["low", "medium", "high"] = "medium"

    @model_validator(mode="after")
    def validate_capability(self) -> "CapabilitySpec":
        if not self.id.strip():
            raise ValueError("capability id must be non-empty")
        if not self.workflow.strip():
            raise ValueError(f"capability {self.id!r} workflow must be non-empty")
        if not self.description.strip():
            raise ValueError(f"capability {self.id!r} description must be non-empty")
        if self.kind == "verifier" and not self.verifies:
            raise ValueError(f"verifier capability {self.id!r} must declare verifies")
        _validate_relative_patterns(
            self.observed_paths,
            field_name=f"capability {self.id!r} observed_paths",
        )
        artifact = self.result_artifact or (
            "verification_result.json" if self.kind == "verifier" else "capability_result.json"
        )
        path = Path(artifact)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(
                f"capability {self.id!r} result_artifact must stay inside child workflow folder"
            )
        self.result_artifact = artifact
        return self


class CapabilityRegistry(StrictModel):
    schema: Literal["botpipe.adaptive-goal.capabilities/v2"] = SCHEMA_REGISTRY
    capabilities: list[CapabilitySpec]

    @model_validator(mode="after")
    def validate_registry(self) -> "CapabilityRegistry":
        ids = [item.id for item in self.capabilities]
        if len(ids) != len(set(ids)):
            raise ValueError("capability ids must be unique")
        return self

    def capability_map(self) -> dict[str, CapabilitySpec]:
        return {item.id: item for item in self.capabilities}


class AdaptiveGoalInput(StrictModel):
    mission: MissionSpec
    registry: CapabilityRegistry
    preapproved_capabilities: list[str] = Field(default_factory=list)
    ad_hoc_enabled: bool = True
    ad_hoc_workflow: str = "ad_hoc_executor"
    max_actions: int = Field(default=60, ge=1)
    max_consecutive_no_progress: int = Field(default=8, ge=1)
    max_same_action_repeats: int = Field(default=4, ge=1)

    @model_validator(mode="after")
    def validate_input(self) -> "AdaptiveGoalInput":
        validate_registry_against_mission(self.mission, self.registry)
        known = set(self.registry.capability_map())
        unknown = [item for item in self.preapproved_capabilities if item not in known]
        if unknown:
            raise ValueError(f"preapproved_capabilities contains unknown ids: {unknown}")
        if not self.ad_hoc_workflow.strip():
            raise ValueError("ad_hoc_workflow must be non-empty")
        return self


class RubricFinding(StrictModel):
    rubric_item_id: str
    status: FindingStatus
    reasoning: str
    evidence: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_finding(self) -> "RubricFinding":
        if not self.rubric_item_id.strip():
            raise ValueError("rubric_item_id must be non-empty")
        if not self.reasoning.strip():
            raise ValueError("rubric finding reasoning must be non-empty")
        return self


class CriterionJudgment(StrictModel):
    """The designated LLM verifier's substantive judgment for one criterion.

    `rating` is deliberately diagnostic only. Runtime PASS/FAIL does not come
    from thresholding it. `reasoning`, findings, and evidence are first-class.
    """

    verdict: JudgmentVerdict
    summary: str
    reasoning: str
    findings: list[RubricFinding]
    rating: int | None = Field(default=None, ge=1, le=5)
    confidence: ConfidenceLevel | None = None
    recommended_actions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_judgment(self) -> "CriterionJudgment":
        if not self.summary.strip():
            raise ValueError("criterion judgment summary must be non-empty")
        if not self.reasoning.strip():
            raise ValueError("criterion judgment reasoning must be non-empty")
        ids = [item.rubric_item_id for item in self.findings]
        if len(ids) != len(set(ids)):
            raise ValueError("criterion judgment rubric findings must be unique")
        return self


class CriterionState(StrictModel):
    status: CriterionStatus = "unknown"
    judgment: CriterionJudgment | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)
    reason: str | None = None
    verifier_id: str | None = None
    verification_id: str | None = None
    verified_at: str | None = None
    observed_paths: list[str] = Field(default_factory=list)
    subject_fingerprint: str | None = None


class ActionRequest(StrictModel):
    kind: ActionKind
    capability_id: str | None = None
    objective: str
    target_criteria: list[str] = Field(default_factory=list)
    rationale: str
    expected_evidence: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_action(self) -> "ActionRequest":
        if not self.objective.strip():
            raise ValueError("action objective must be non-empty")
        if not self.rationale.strip():
            raise ValueError("action rationale must be non-empty")
        if self.kind in {"capability", "verifier"} and not self.capability_id:
            raise ValueError(f"action kind {self.kind!r} requires capability_id")
        if self.kind in {"ad_hoc", "blocked"} and self.capability_id is not None:
            raise ValueError(f"action kind {self.kind!r} must not specify capability_id")
        if len(self.target_criteria) != len(set(self.target_criteria)):
            raise ValueError("target_criteria must be unique")
        return self

    def fingerprint(self) -> str:
        payload = {
            "kind": self.kind,
            "capability_id": self.capability_id,
            "objective": " ".join(self.objective.lower().split()),
            "target_criteria": sorted(self.target_criteria),
        }
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


class ActionCapabilityResult(StrictModel):
    schema: Literal["botpipe.adaptive-goal.action-result/v2"] = SCHEMA_ACTION_RESULT
    status: Literal["completed", "blocked", "failed"]
    summary: str
    evidence: list[str] = Field(default_factory=list)
    changed_paths: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class VerifierCapabilityResult(StrictModel):
    schema: Literal["botpipe.adaptive-goal.verifier-result/v2"] = SCHEMA_VERIFIER_RESULT
    status: Literal["evaluated", "blocked", "failed"]
    verifier_id: str
    summary: str
    judgments: dict[str, CriterionJudgment] = Field(default_factory=dict)
    observations: dict[str, dict[str, Any]] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)
    observed_paths: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_paths(self) -> "VerifierCapabilityResult":
        for criterion_id, patterns in self.observed_paths.items():
            _validate_relative_patterns(
                patterns,
                field_name=f"verifier observed_paths[{criterion_id!r}]",
            )
        return self


class DispatchResult(StrictModel):
    action: ActionRequest
    child_workflow: str | None = None
    child_run_id: str | None = None
    child_status: str | None = None
    child_terminal: str | None = None
    child_result_path: str | None = None
    capability_result: ActionCapabilityResult | None = None
    verifier_result: VerifierCapabilityResult | None = None
    dispatch_error: str | None = None


class VerificationReceipt(StrictModel):
    verification_id: str
    criterion_id: str
    verifier_id: str
    verdict: Literal["pass", "fail", "blocked"]
    judgment: CriterionJudgment | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)
    reason: str | None = None
    observed_paths: list[str] = Field(default_factory=list)
    subject_fingerprint: str | None = None
    verified_at: str


class VerificationLedger(StrictModel):
    schema: Literal["botpipe.adaptive-goal.verification-ledger/v2"] = SCHEMA_RECEIPTS
    receipts: list[VerificationReceipt] = Field(default_factory=list)


class ActionRecord(StrictModel):
    index: int
    action: ActionRequest
    child_workflow: str | None = None
    child_run_id: str | None = None
    outcome: str
    summary: str
    invalidated_criteria: list[str] = Field(default_factory=list)
    verified_criteria: list[str] = Field(default_factory=list)
    progress: bool = False
    at: str


class Blackboard(StrictModel):
    schema: Literal["botpipe.adaptive-goal.blackboard/v2"] = SCHEMA_BLACKBOARD
    mission_id: str
    criteria: dict[str, CriterionState]
    action_count: int = 0
    consecutive_no_progress: int = 0
    last_action_fingerprint: str | None = None
    same_action_repeats: int = 0
    recent_actions: list[ActionRecord] = Field(default_factory=list)
    terminal_reason: str | None = None
    started_at: str
    updated_at: str


class GlobalAuditDecision(StrictModel):
    status: Literal["complete", "reopen", "blocked"]
    summary: str
    reopen_criteria: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    reason: str | None = None

    @model_validator(mode="after")
    def validate_decision(self) -> "GlobalAuditDecision":
        if self.status == "reopen" and not self.reopen_criteria:
            raise ValueError("reopen audit decisions require reopen_criteria")
        if self.status != "reopen" and self.reopen_criteria:
            raise ValueError("reopen_criteria are only valid for reopen decisions")
        return self


class AdaptiveGoalState(StrictModel):
    status: Literal[
        "initializing",
        "active",
        "complete",
        "unsatisfied",
        "blocked",
    ] = "initializing"
    mission_id: str | None = None
    last_reason: str | None = None


class AdaptiveGoalOutput(StrictModel):
    status: Literal["complete", "unsatisfied", "blocked"]
    mission_id: str
    action_count: int
    blackboard_path: str
    verification_ledger_path: str
    final_report_path: str


def validate_registry_against_mission(
    mission: MissionSpec,
    registry: CapabilityRegistry,
) -> None:
    criteria = mission.criterion_map()
    capabilities = registry.capability_map()

    for criterion in mission.criteria:
        cap = capabilities.get(criterion.verifier)
        if cap is None:
            raise ValueError(
                f"criterion {criterion.id!r} references unknown verifier {criterion.verifier!r}"
            )
        if cap.kind != "verifier":
            raise ValueError(
                f"criterion {criterion.id!r} verifier {criterion.verifier!r} is not a verifier capability"
            )
        if criterion.id not in cap.verifies:
            raise ValueError(
                f"verifier {cap.id!r} does not declare criterion {criterion.id!r} in verifies"
            )

    for cap in registry.capabilities:
        for field_name, values in (
            ("helps", cap.helps),
            ("verifies", cap.verifies),
            ("may_invalidate", cap.may_invalidate),
        ):
            unknown = [value for value in values if value not in criteria]
            if unknown:
                raise ValueError(
                    f"capability {cap.id!r} {field_name} references unknown criteria: {unknown}"
                )


def _lookup_metric(metrics: dict[str, Any], dotted: str) -> tuple[bool, Any]:
    current: Any = metrics
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def evaluate_deterministic_rules(
    criterion: MissionCriterion,
    metrics: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Apply only operator-authored hard rules to objective observations."""

    failures: list[str] = []
    for rule in criterion.deterministic_rules:
        found, observed = _lookup_metric(metrics, rule.metric)
        if not found:
            failures.append(f"missing metric {rule.metric!r}")
            continue

        try:
            if rule.operator == "eq":
                ok = observed == rule.value
            elif rule.operator == "ne":
                ok = observed != rule.value
            elif rule.operator == "gt":
                ok = observed > rule.value
            elif rule.operator == "ge":
                ok = observed >= rule.value
            elif rule.operator == "lt":
                ok = observed < rule.value
            elif rule.operator == "le":
                ok = observed <= rule.value
            elif rule.operator == "in":
                ok = observed in rule.value
            elif rule.operator == "not_in":
                ok = observed not in rule.value
            elif rule.operator == "truthy":
                ok = bool(observed)
            elif rule.operator == "falsy":
                ok = not bool(observed)
            else:  # pragma: no cover - Literal protects this
                ok = False
        except (TypeError, ValueError) as exc:
            failures.append(f"metric {rule.metric!r} could not be compared: {exc}")
            continue

        if not ok:
            expected = (
                rule.operator
                if rule.operator in {"truthy", "falsy"}
                else f"{rule.operator} {rule.value!r}"
            )
            failures.append(
                f"metric {rule.metric!r} was {observed!r}, expected {expected}"
            )

    return not failures, failures


def evaluate_judgment(
    criterion: MissionCriterion,
    judgment: CriterionJudgment | None,
) -> tuple[Literal["pass", "fail", "blocked"], str | None]:
    """Validate designated-verifier rubric coverage and accept its judgment.

    The runtime does not infer subjective quality from a score. It verifies that
    every authored rubric item was actually considered and that an overall
    `satisfied` verdict is not internally inconsistent with an authored gate.
    """

    if judgment is None:
        return "blocked", "designated verifier did not provide a qualitative judgment"

    expected = {item.id: item for item in criterion.rubric}
    actual = {item.rubric_item_id: item for item in judgment.findings}
    missing = sorted(set(expected) - set(actual))
    unknown = sorted(set(actual) - set(expected))
    if missing or unknown:
        parts: list[str] = []
        if missing:
            parts.append(f"missing rubric findings: {missing}")
        if unknown:
            parts.append(f"unknown rubric findings: {unknown}")
        return "blocked", "; ".join(parts)

    if judgment.verdict == "insufficient_evidence":
        return "blocked", judgment.reasoning
    if judgment.verdict == "not_satisfied":
        return "fail", judgment.reasoning

    inconsistent_gates = [
        item.id
        for item in criterion.rubric
        if item.importance == "gate"
        and actual[item.id].status != "satisfied"
    ]
    if inconsistent_gates:
        return (
            "blocked",
            "overall judgment was satisfied but gate findings were not fully satisfied: "
            f"{inconsistent_gates}",
        )

    return "pass", judgment.reasoning


def evaluate_verification(
    criterion: MissionCriterion,
    *,
    judgment: CriterionJudgment | None,
    metrics: dict[str, Any],
) -> tuple[Literal["pass", "fail", "blocked"], str | None]:
    """Evaluate a verifier result according to the criterion's authored mode."""

    if criterion.verification_mode == "judgment":
        return evaluate_judgment(criterion, judgment)

    if criterion.verification_mode == "deterministic":
        passed, failures = evaluate_deterministic_rules(criterion, metrics)
        return ("pass", None) if passed else ("fail", "; ".join(failures))

    judgment_verdict, judgment_reason = evaluate_judgment(criterion, judgment)
    if judgment_verdict != "pass":
        return judgment_verdict, judgment_reason
    passed, failures = evaluate_deterministic_rules(criterion, metrics)
    if not passed:
        return "fail", "; ".join(failures)
    return "pass", judgment_reason


def _validate_relative_patterns(patterns: list[str], *, field_name: str) -> None:
    for pattern in patterns:
        if not isinstance(pattern, str) or not pattern.strip():
            raise ValueError(f"{field_name} entries must be non-empty strings")
        path = Path(pattern)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(
                f"{field_name} patterns must stay inside the workspace: {pattern!r}"
            )


def fingerprint_paths(root: Path, patterns: list[str]) -> str | None:
    """Hash the exact filesystem subject a verifier claims to observe.

    Missing matches are included in the digest so creating a previously absent
    file changes the fingerprint. `.git` and `.botpipe` are always excluded.
    Symlinks resolving outside `root` are ignored.
    """

    if not patterns:
        return None

    root = root.resolve()
    digest = hashlib.sha256()

    for pattern in sorted(set(patterns)):
        digest.update(b"PATTERN\0")
        digest.update(pattern.encode("utf-8", errors="surrogateescape"))
        matches: list[Path] = []

        def add_candidate(candidate: Path) -> None:
            try:
                resolved = candidate.resolve()
                resolved.relative_to(root)
            except (OSError, ValueError):
                return

            rel = resolved.relative_to(root)
            if not rel.parts or rel.parts[0] in {".git", ".botpipe"}:
                return
            if resolved.is_file():
                matches.append(resolved)

        for candidate in root.glob(pattern):
            add_candidate(candidate)
            try:
                resolved_candidate = candidate.resolve()
                resolved_candidate.relative_to(root)
            except (OSError, ValueError):
                continue
            if resolved_candidate.is_dir():
                for descendant in resolved_candidate.rglob("*"):
                    add_candidate(descendant)

        matches = sorted(
            set(matches), key=lambda path: path.relative_to(root).as_posix()
        )
        if not matches:
            digest.update(b"\0NO_MATCH\0")
            continue

        for path in matches:
            rel = path.relative_to(root).as_posix()
            digest.update(b"\0FILE\0")
            digest.update(rel.encode("utf-8", errors="surrogateescape"))
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)

    return digest.hexdigest()


def required_criteria_pass(mission: MissionSpec, blackboard: Blackboard) -> bool:
    return all(
        blackboard.criteria[item.id].status == "pass"
        for item in mission.criteria
        if item.required
    )


def terminal_unsatisfied_criteria(
    mission: MissionSpec,
    blackboard: Blackboard,
) -> list[str]:
    return [
        item.id
        for item in mission.criteria
        if item.required
        and item.failure_policy == "terminal_unsatisfied"
        and blackboard.criteria[item.id].status == "fail"
    ]
