"""Frozen, bounded two-arm evaluation for concrete workflow candidates."""

from __future__ import annotations

import json
import math
import os
import platform
import shutil
import stat
import sys
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

EVALUATION_SPEC_SCHEMA = "botpipe.optimizer.evaluation_spec/v1"
EVALUATION_REQUEST_SCHEMA = "botpipe.optimizer.eval_request/v1"
EVALUATION_RESULT_SCHEMA = "botpipe.optimizer.eval_result/v1"
PAIRED_EVALUATION_SCHEMA = "botpipe.optimizer.paired_evaluation/v1"
DEFAULT_MAX_EVALUATION_OUTPUT_BYTES = 50 * 1024 * 1024
DEFAULT_MAX_EVALUATION_OUTPUT_FILES = 10_000


class BudgetExhausted(ValueError):
    pass


class MetricDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    direction: Literal["higher_is_better", "lower_is_better"]
    aggregation: Literal["mean", "sum"] = "mean"
    minimum_improvement: float | None = None
    maximum_regression: float = Field(default=0.0, ge=0.0)

    @field_validator("minimum_improvement", "maximum_regression")
    @classmethod
    def finite(cls, value):
        if value is not None and (isinstance(value, bool) or not math.isfinite(value)):
            raise ValueError("metric thresholds must be finite numbers")
        return value


class EvaluationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[EVALUATION_SPEC_SCHEMA] = Field(alias="schema")
    evaluator_argv: list[str] = Field(min_length=1)
    evaluator_path: str
    evaluator_content_id: str
    case_input_path: str
    case_input_content_id: str
    case_ids: list[str] = Field(min_length=1)
    repetitions: int = Field(default=1, ge=1)
    effective_settings: dict[str, Any] = Field(default_factory=dict)
    environment_id: str | None = None
    metrics: list[MetricDefinition] = Field(min_length=1)
    primary_metric: str
    guardrail_metrics: list[str] = Field(default_factory=list)
    claim_scope: Literal["development_cases", "evaluation_cases"] = "development_cases"
    stochastic: bool = False
    evaluator_kind: Literal["external", "botpipe"] = "external"
    max_elapsed_seconds: float = Field(default=1200.0, gt=0)
    per_arm_timeout_seconds: float = Field(default=600.0, gt=0)
    max_provider_turns_per_arm: int | None = Field(default=None, ge=1)
    max_evaluation_output_bytes: int = Field(
        default=DEFAULT_MAX_EVALUATION_OUTPUT_BYTES, ge=1
    )
    max_evaluation_output_files: int = Field(
        default=DEFAULT_MAX_EVALUATION_OUTPUT_FILES, ge=1
    )

    @field_validator("case_ids", "guardrail_metrics")
    @classmethod
    def unique_strings(cls, values):
        if any(not isinstance(x, str) or not x or x != x.strip() for x in values):
            raise ValueError(
                "entries must be non-empty strings without surrounding whitespace"
            )
        if len(values) != len(set(values)):
            raise ValueError("entries must be unique")
        return values

    @field_validator("evaluator_argv")
    @classmethod
    def argv_strings(cls, values):
        if any(not isinstance(value, str) or not value for value in values):
            raise ValueError("evaluator_argv entries must be non-empty strings")
        return values

    @field_validator(
        "evaluator_path",
        "case_input_path",
        "evaluator_content_id",
        "case_input_content_id",
    )
    @classmethod
    def text(cls, value):
        if not value or value != value.strip():
            raise ValueError("value must be non-empty")
        return value

    @field_validator("max_elapsed_seconds", "per_arm_timeout_seconds")
    @classmethod
    def finite_time(cls, value):
        if not math.isfinite(value):
            raise ValueError("time limits must be finite")
        return value

    @model_validator(mode="after")
    def validate_plan(self):
        names = [m.name for m in self.metrics]
        if len(names) != len(set(names)):
            raise ValueError("metric names must be unique")
        metrics = {m.name: m for m in self.metrics}
        if self.primary_metric not in metrics:
            raise ValueError("primary_metric must name a declared metric")
        threshold = metrics[self.primary_metric].minimum_improvement
        if threshold is None or threshold <= 0:
            raise ValueError("primary metric requires positive minimum_improvement")
        if self.primary_metric in self.guardrail_metrics:
            raise ValueError("primary metric cannot also be a guardrail")
        if unknown := sorted(set(self.guardrail_metrics) - set(metrics)):
            raise ValueError(f"unknown guardrail metrics: {unknown}")
        if any(
            m.name != self.primary_metric and m.minimum_improvement is not None
            for m in self.metrics
        ):
            raise ValueError("only primary metric may define minimum_improvement")
        if self.evaluator_kind == "botpipe" and self.max_provider_turns_per_arm is None:
            raise ValueError("botpipe evaluator requires max_provider_turns_per_arm")
        if (
            self.evaluator_kind == "external"
            and self.max_provider_turns_per_arm is not None
        ):
            raise ValueError(
                "external evaluator cannot claim provider-turn enforcement"
            )
        if (
            "{evaluator_path}" not in self.evaluator_argv
            and self.evaluator_path not in self.evaluator_argv
        ):
            raise ValueError(
                "evaluator_argv must reference evaluator_path or {evaluator_path}"
            )
        return self


class CaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    case_id: str = Field(min_length=1)
    repetition: int = Field(ge=1)
    outcome: str = Field(min_length=1)
    metrics: dict[str, float]
    evidence_paths: list[str] = Field(default_factory=list)
    usage_availability: Literal["known_total", "partial", "unknown", "not_attempted"]
    elapsed_seconds: float = Field(ge=0)

    @field_validator("elapsed_seconds")
    @classmethod
    def finite_elapsed(cls, value):
        if isinstance(value, bool) or not math.isfinite(value):
            raise ValueError("elapsed_seconds must be finite")
        return value

    @field_validator("metrics")
    @classmethod
    def finite_metrics(cls, values):
        if any(
            not k
            or isinstance(v, bool)
            or not isinstance(v, (int, float))
            or not math.isfinite(v)
            for k, v in values.items()
        ):
            raise ValueError("metric values must be finite numbers")
        return {k: float(v) for k, v in values.items()}


class EvaluatorResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[EVALUATION_RESULT_SCHEMA] = Field(alias="schema")
    execution_id: str
    surface_id: str
    spec_id: str
    cases: list[CaseResult]
    environment_id: str | None = None
    provider_budget: dict[str, Any] | None = None


def load_evaluation_spec(path: str | Path) -> tuple[EvaluationSpec, str]:
    path = _regular(Path(path), "evaluation specification")
    payload = _read_json(
        path, DEFAULT_MAX_EVALUATION_OUTPUT_BYTES, "evaluation specification"
    )
    try:
        spec = EvaluationSpec.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"invalid evaluation specification: {exc}") from exc
    return spec, _canonical_id(spec.model_dump(mode="json", by_alias=True))


def compare_evaluation_aggregates(
    spec: EvaluationSpec | Mapping[str, Any],
    baseline: Mapping[str, float],
    candidate: Mapping[str, float],
    *,
    comparable: bool = True,
) -> dict[str, Any]:
    spec = (
        spec
        if isinstance(spec, EvaluationSpec)
        else EvaluationSpec.model_validate(spec)
    )
    names = {m.name for m in spec.metrics}
    if set(baseline) != names or set(candidate) != names:
        raise ValueError("aggregates must contain exactly declared metrics")
    deltas, regressions = {}, []
    relevant = {spec.primary_metric, *spec.guardrail_metrics}
    for metric in spec.metrics:
        before, after = _finite(baseline[metric.name]), _finite(candidate[metric.name])
        delta = (
            after - before if metric.direction == "higher_is_better" else before - after
        )
        deltas[metric.name] = delta
        if metric.name in relevant and delta < -metric.maximum_regression:
            regressions.append(metric.name)
    primary = next(m for m in spec.metrics if m.name == spec.primary_metric)
    state = (
        "inconclusive"
        if not comparable
        else (
            "regressed"
            if regressions
            else (
                "improved"
                if deltas[primary.name] >= float(primary.minimum_improvement)
                else "no_material_change"
            )
        )
    )
    return {
        "state": state,
        "primary_metric": spec.primary_metric,
        "deltas": deltas,
        "regressed_metrics": regressions,
        "claim_scope": spec.claim_scope,
        "limitations": _limitations(spec),
    }


def run_paired_evaluation(
    *,
    evaluation_spec_path: str | Path,
    baseline_arm: Any,
    candidate_arm: Any,
    output_root: str | Path,
    process_runner: Callable[..., Any] | None = None,
    snapshot_arm: Callable[[Any], Mapping[str, Any]] | None = None,
    assert_arm_unchanged: Callable[..., None] | None = None,
) -> dict[str, Any]:
    """Launch exactly one evaluator process for each exact, disjoint execution arm."""
    spec_path = _regular(Path(evaluation_spec_path), "evaluation specification")
    spec, spec_id = load_evaluation_spec(spec_path)
    base_root, base_tree, base_surface = _arm_fields(baseline_arm, "baseline")
    cand_root, cand_tree, cand_surface = _arm_fields(candidate_arm, "candidate")
    if (
        base_root == cand_root
        or base_root.is_relative_to(cand_root)
        or cand_root.is_relative_to(base_root)
    ):
        raise ValueError("baseline and candidate execution arms must be disjoint")
    destination = Path(output_root).resolve()
    if destination.exists():
        raise ValueError("paired evaluation output_root must be newly allocated")
    destination.mkdir(parents=True)
    sources = [
        spec_path,
        _resolve(spec_path, spec.evaluator_path, "evaluator"),
        _resolve(spec_path, spec.case_input_path, "case input"),
    ]
    if any(p.is_relative_to(base_root) or p.is_relative_to(cand_root) for p in sources):
        raise ValueError(
            "spec, evaluator, and cases must live outside editable execution arms"
        )
    if destination.is_relative_to(base_root) or destination.is_relative_to(cand_root):
        raise ValueError("evaluation output must live outside editable execution arms")
    frozen = _freeze(spec, spec_path, destination / "frozen")
    request_root = destination / "requests"
    request_root.mkdir()
    process_runner = process_runner or _default_runner()
    if snapshot_arm is None or assert_arm_unchanged is None:
        from .execution_trees import (
            snapshot_execution_arm,
            assert_execution_arm_unchanged,
        )

        snapshot_arm = snapshot_arm or snapshot_execution_arm
        assert_arm_unchanged = assert_arm_unchanged or assert_execution_arm_unchanged
    env_id = _environment_id(spec, frozen)
    deadline = time.monotonic() + spec.max_elapsed_seconds
    arms: dict[str, dict[str, Any]] = {}
    for name, arm, root, tree, surface in (
        ("baseline", baseline_arm, base_root, base_tree, base_surface),
        ("candidate", candidate_arm, cand_root, cand_tree, cand_surface),
    ):
        expected = snapshot_arm(arm)
        if expected.get("execution_tree_id") != tree:
            raise ValueError(f"{name} arm changed before evaluation")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            arms[name] = _failed(
                name,
                surface,
                tree,
                "budget_exhausted",
                "overall elapsed budget exhausted before launch",
            )
            continue
        arms[name] = _run_arm(
            name=name,
            root=root,
            tree=tree,
            surface=surface,
            spec=spec,
            spec_id=spec_id,
            frozen=frozen,
            request_root=request_root,
            output_root=destination / name,
            timeout=min(spec.per_arm_timeout_seconds, remaining),
            runner=process_runner,
            environment_id=env_id,
        )
        assert_arm_unchanged(expected, root, phase=f"paired evaluation {name}")
        _assert_frozen(frozen)
        if time.monotonic() > deadline and arms[name]["execution_state"] == "complete":
            arms[name] = _failed(
                name,
                surface,
                tree,
                "budget_exhausted",
                "overall elapsed budget exhausted during result validation",
                arms[name].get("diagnostics"),
            )
    complete = all(x["execution_state"] == "complete" for x in arms.values())
    comparable = (
        complete
        and all(x.get("environment_compatible") is True for x in arms.values())
        and arms["baseline"]["environment_id"] == arms["candidate"]["environment_id"]
    )
    if complete:
        comparison = compare_evaluation_aggregates(
            spec,
            arms["baseline"]["aggregates"],
            arms["candidate"]["aggregates"],
            comparable=comparable,
        )
        if not comparable:
            comparison["limitations"].append(
                "evaluator environments were not comparable"
            )
    else:
        comparison = {
            "state": "inconclusive",
            "primary_metric": spec.primary_metric,
            "deltas": {},
            "regressed_metrics": [],
            "claim_scope": spec.claim_scope,
            "limitations": [
                "one or both evaluator executions were incomplete",
                *_limitations(spec),
            ],
        }
    record = {
        "schema": PAIRED_EVALUATION_SCHEMA,
        "spec_id": spec_id,
        "execution_output_root": str(destination),
        "frozen_inputs": {
            k: v
            for k, v in frozen.items()
            if k.endswith("_id") or k == "evaluator_executable"
        },
        "plan": {
            "case_ids": spec.case_ids,
            "repetitions": spec.repetitions,
            "effective_settings": spec.effective_settings,
            "stochastic": spec.stochastic,
            "max_elapsed_seconds": spec.max_elapsed_seconds,
            "per_arm_timeout_seconds": spec.per_arm_timeout_seconds,
            "max_provider_turns_per_arm": spec.max_provider_turns_per_arm,
        },
        "arms": arms,
        "comparison": comparison,
        "automatic_promotion": False,
    }
    return finalize_paired_evaluation_record(record)


def finalize_paired_evaluation_record(record: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(record)
    value.pop("paired_evaluation_id", None)
    value["paired_evaluation_id"] = _canonical_id(value)
    return value


def validate_paired_evaluation_record(
    record: Mapping[str, Any],
    *,
    evaluation_spec_path: str | Path,
    baseline_surface_id: str,
    candidate_surface_id: str,
    baseline_execution_tree_id: str,
    candidate_execution_tree_id: str,
    allowed_output_parent: str | Path,
    expected_invocation_id: str | None = None,
) -> dict[str, Any]:
    """Revalidate a committed paired result before resume publication without rerunning it."""
    value = dict(record)
    declared = value.pop("paired_evaluation_id", None)
    if not isinstance(declared, str) or declared != _canonical_id(value):
        raise ValueError("paired_evaluation_id does not match record content")
    if value.get("schema") != PAIRED_EVALUATION_SCHEMA:
        raise ValueError("paired evaluation schema mismatch")
    if (
        expected_invocation_id is not None
        and value.get("invocation_id") != expected_invocation_id
    ):
        raise ValueError("paired evaluation invocation identity is stale")
    spec, spec_id = load_evaluation_spec(evaluation_spec_path)
    if value.get("spec_id") != spec_id:
        raise ValueError("paired evaluation spec identity is stale")
    plan = value.get("plan")
    if (
        not isinstance(plan, Mapping)
        or plan.get("case_ids") != spec.case_ids
        or plan.get("repetitions") != spec.repetitions
        or plan.get("effective_settings") != spec.effective_settings
        or plan.get("stochastic") is not spec.stochastic
    ):
        raise ValueError("paired evaluation plan does not match frozen spec")
    root = Path(str(value.get("execution_output_root"))).resolve()
    parent = Path(allowed_output_parent).resolve()
    if not root.is_relative_to(parent) or not root.is_dir():
        raise ValueError(
            "paired evaluation output root is unavailable or outside workflow output"
        )
    _validate_cached_frozen_inputs(
        spec, spec_id, root / "frozen", value.get("frozen_inputs")
    )
    arms = value.get("arms")
    if not isinstance(arms, Mapping) or set(arms) != {"baseline", "candidate"}:
        raise ValueError("paired evaluation must define both arms")
    aggregate_pairs = {}
    for name, surface, tree in (
        ("baseline", baseline_surface_id, baseline_execution_tree_id),
        ("candidate", candidate_surface_id, candidate_execution_tree_id),
    ):
        arm = arms[name]
        if (
            not isinstance(arm, Mapping)
            or arm.get("surface_id") != surface
            or arm.get("execution_tree_id") != tree
        ):
            raise ValueError(f"cached {name} arm identity is stale")
        cases = arm.get("cases")
        if arm.get("execution_state") == "complete":
            request = _read_json(
                _regular(
                    root / "requests" / f"{name}.json", "cached evaluation request"
                ),
                spec.max_evaluation_output_bytes,
                "cached evaluation request",
            )
            if (
                request.get("execution_id") != arm.get("execution_id")
                or request.get("surface_id") != surface
                or request.get("execution_tree_id") != tree
                or request.get("spec_id") != spec_id
            ):
                raise ValueError(f"cached {name} request identity is stale")
            raw_result = EvaluatorResult.model_validate(
                _read_json(
                    _regular(root / name / "result.json", "cached evaluator result"),
                    spec.max_evaluation_output_bytes,
                    "cached evaluator result",
                )
            )
            if (raw_result.execution_id, raw_result.surface_id, raw_result.spec_id) != (
                arm.get("execution_id"),
                surface,
                spec_id,
            ):
                raise ValueError(f"cached {name} evaluator result identity is stale")
            _validate_budget(raw_result, spec)
            if not isinstance(cases, list) or [
                (c.get("case_id"), c.get("repetition"))
                for c in cases
                if isinstance(c, Mapping)
            ] != [
                (case, repetition)
                for case in spec.case_ids
                for repetition in range(1, spec.repetitions + 1)
            ]:
                raise ValueError(f"cached {name} cases do not match plan")
            parsed = [CaseResult.model_validate(case) for case in cases]
            if [case.model_dump(mode="json") for case in raw_result.cases] != [
                case.model_dump(mode="json") for case in parsed
            ]:
                raise ValueError(f"cached {name} cases differ from evaluator result")
            aggregates = _aggregate(spec, parsed)
            if aggregates != arm.get("aggregates"):
                raise ValueError(f"cached {name} aggregates do not match cases")
            aggregate_pairs[name] = aggregates
            for evidence in arm.get("evidence", []):
                if not isinstance(evidence, Mapping):
                    raise ValueError("cached evidence record invalid")
                path = _regular(
                    root / name / str(evidence.get("path")),
                    "cached evaluation evidence",
                )
                if _sha256(path) != evidence.get(
                    "sha256"
                ) or path.stat().st_size != evidence.get("size_bytes"):
                    raise ValueError("cached evaluation evidence changed")
    comparison = value.get("comparison")
    if set(aggregate_pairs) == {"baseline", "candidate"}:
        comparable = all(
            arms[name].get("environment_compatible") is True
            for name in ("baseline", "candidate")
        ) and arms["baseline"].get("environment_id") == arms["candidate"].get(
            "environment_id"
        )
        expected = compare_evaluation_aggregates(
            spec,
            aggregate_pairs["baseline"],
            aggregate_pairs["candidate"],
            comparable=comparable,
        )
        if not comparable:
            expected["limitations"].append("evaluator environments were not comparable")
        if comparison != expected:
            raise ValueError("cached comparison does not match arm results")
    value["paired_evaluation_id"] = declared
    return value


def _run_arm(
    *,
    name,
    root,
    tree,
    surface,
    spec,
    spec_id,
    frozen,
    request_root,
    output_root,
    timeout,
    runner,
    environment_id,
):
    output_root.mkdir()
    result_path = output_root / "result.json"
    request_path = request_root / f"{name}.json"
    execution_id = uuid.uuid4().hex
    request = {
        "schema": EVALUATION_REQUEST_SCHEMA,
        "execution_id": execution_id,
        "surface_id": surface,
        "execution_tree_id": tree,
        "spec_id": spec_id,
        "workspace_path": str(root),
        "case_input_path": str(frozen["case_input_path"]),
        "case_ids": spec.case_ids,
        "repetitions": spec.repetitions,
        "effective_settings": spec.effective_settings,
        "environment_id": environment_id,
        "allowed_output_directory": str(output_root),
        "remaining_limits": {
            "elapsed_seconds": timeout,
            "max_provider_turns": spec.max_provider_turns_per_arm,
            "max_output_bytes": spec.max_evaluation_output_bytes,
            "max_output_files": spec.max_evaluation_output_files,
        },
    }
    _atomic_json(request_path, request)
    exceeded = False

    def cancel():
        nonlocal exceeded
        try:
            _inventory(
                output_root,
                spec.max_evaluation_output_bytes,
                spec.max_evaluation_output_files,
            )
        except ValueError:
            exceeded = True
        except OSError:
            return False
        return exceeded

    env = dict(os.environ)
    env.update(
        BOTPIPE_EVAL_REQUEST=str(request_path), BOTPIPE_EVAL_RESULT=str(result_path)
    )
    argv = _argv(spec, frozen, root)
    try:
        proc = runner(
            argv,
            cwd=root,
            timeout_seconds=timeout,
            max_stream_bytes=1024 * 1024,
            termination_grace_seconds=5,
            env=env,
            cancel_requested=cancel,
        )
    except Exception as exc:
        return _failed(name, surface, tree, "failed", f"evaluator launch failed: {exc}")
    diag = _diagnostics(proc, argv)
    if diag["timed_out"]:
        return _failed(name, surface, tree, "timed_out", "evaluator timed out", diag)
    if diag["cancelled"]:
        return _failed(
            name,
            surface,
            tree,
            "cancelled",
            "evaluation output limit exceeded" if exceeded else "evaluator cancelled",
            diag,
        )
    if diag["exit_code"] != 0:
        return _failed(name, surface, tree, "failed", "evaluator exited nonzero", diag)
    try:
        inventory = _inventory(
            output_root,
            spec.max_evaluation_output_bytes,
            spec.max_evaluation_output_files,
        )
        if result_path.resolve() not in inventory["paths"]:
            raise ValueError("fresh result missing")
        result = EvaluatorResult.model_validate(
            _read_json(
                result_path, spec.max_evaluation_output_bytes, "evaluation result"
            )
        )
        if (result.execution_id, result.surface_id, result.spec_id) != (
            execution_id,
            surface,
            spec_id,
        ):
            raise ValueError("result identity does not echo request")
        cases, evidence = _validate_cases(result, spec, output_root)
        _validate_budget(result, spec)
        aggregates = _aggregate(spec, cases)
    except BudgetExhausted as exc:
        return _failed(name, surface, tree, "budget_exhausted", str(exc), diag)
    except (OSError, ValueError, ValidationError) as exc:
        return _failed(
            name, surface, tree, "failed", f"invalid evaluator result: {exc}", diag
        )
    compatible = result.environment_id in (None, environment_id)
    return {
        "arm": name,
        "execution_state": "complete",
        "execution_id": execution_id,
        "surface_id": surface,
        "execution_tree_id": tree,
        "environment_id": environment_id,
        "reported_environment_id": result.environment_id,
        "environment_compatible": compatible,
        "aggregates": aggregates,
        "cases": [c.model_dump(mode="json") for c in cases],
        "evidence": evidence,
        "provider_budget": result.provider_budget,
        "output_file_count": inventory["file_count"],
        "output_bytes": inventory["total_bytes"],
        "diagnostics": diag,
    }


def _validate_cases(result, spec, root):
    expected = [(c, r) for c in spec.case_ids for r in range(1, spec.repetitions + 1)]
    if [(c.case_id, c.repetition) for c in result.cases] != expected:
        raise ValueError("cases must exactly match frozen case/repetition order")
    metrics = {m.name for m in spec.metrics}
    evidence = []
    seen = set()
    for case in result.cases:
        if set(case.metrics) != metrics:
            raise ValueError("case must contain exactly required metrics")
        for raw in case.evidence_paths:
            p = Path(raw)
            p = p if p.is_absolute() else root / p
            p = _regular(p, "evaluation evidence")
            try:
                rel = p.relative_to(root.resolve()).as_posix()
            except ValueError as exc:
                raise ValueError("evidence path escapes output directory") from exc
            if rel not in seen:
                seen.add(rel)
                evidence.append(
                    {"path": rel, "sha256": _sha256(p), "size_bytes": p.stat().st_size}
                )
    return result.cases, evidence


def _validate_budget(result, spec):
    if spec.evaluator_kind != "botpipe":
        return
    b = result.provider_budget
    if not isinstance(b, Mapping):
        raise ValueError("botpipe result requires provider_budget")
    maximum, used = b.get("max_turns"), b.get("used_turns")
    if (
        isinstance(maximum, bool)
        or not isinstance(maximum, int)
        or maximum != spec.max_provider_turns_per_arm
    ):
        raise ValueError("provider budget cap mismatch")
    if isinstance(used, bool) or not isinstance(used, int) or not 0 <= used <= maximum:
        raise ValueError("invalid provider budget usage")
    if b.get("exhausted") is True:
        raise BudgetExhausted("provider budget exhausted")


def _aggregate(spec, cases):
    return {
        m.name: (
            sum(c.metrics[m.name] for c in cases)
            if m.aggregation == "sum"
            else sum(c.metrics[m.name] for c in cases) / len(cases)
        )
        for m in spec.metrics
    }


def _freeze(spec, spec_path, root):
    root.mkdir()
    evaluator = _resolve(spec_path, spec.evaluator_path, "evaluator")
    cases = _resolve(spec_path, spec.case_input_path, "case input")
    eid, cid = _sha256(evaluator), _sha256(cases)
    _check_id(spec.evaluator_content_id, eid, "evaluator")
    _check_id(spec.case_input_content_id, cid, "case input")
    targets = _frozen_paths(spec, root)
    shutil.copy2(spec_path, targets["spec_path"])
    shutil.copy2(evaluator, targets["evaluator_path"])
    shutil.copy2(cases, targets["case_input_path"])
    return {
        **targets,
        "spec_file_id": _sha256(targets["spec_path"]),
        "evaluator_id": eid,
        "case_input_id": cid,
        "evaluator_executable": bool(evaluator.stat().st_mode & stat.S_IXUSR),
    }


def _frozen_paths(spec, root):
    return {
        "spec_path": root / "evaluation-spec.json",
        "evaluator_path": root / f"evaluator-{Path(spec.evaluator_path).name}",
        "case_input_path": root / f"cases-{Path(spec.case_input_path).name}",
    }


def _validate_cached_frozen_inputs(spec, spec_id, root, identities):
    if root.is_symlink() or not root.is_dir():
        raise ValueError("cached frozen input directory is unavailable")
    if (
        not isinstance(identities, Mapping)
        or any(
            not isinstance(identities.get(key), str) or not identities[key]
            for key in ("spec_file_id", "evaluator_id", "case_input_id")
        )
        or not isinstance(identities.get("evaluator_executable"), bool)
    ):
        raise ValueError(
            "cached frozen input identities are missing; start a new evaluation"
        )
    frozen = {**identities, **_frozen_paths(spec, root)}
    _assert_frozen(frozen)
    _check_id(spec.evaluator_content_id, identities["evaluator_id"], "evaluator")
    _check_id(spec.case_input_content_id, identities["case_input_id"], "case input")
    _, frozen_spec_id = load_evaluation_spec(frozen["spec_path"])
    if frozen_spec_id != spec_id:
        raise ValueError("cached frozen specification differs from evaluation plan")


def _assert_frozen(frozen):
    for stem in ("evaluator", "case_input"):
        p = _regular(frozen[f"{stem}_path"], f"frozen {stem}")
        if _sha256(p) != frozen[f"{stem}_id"]:
            raise ValueError(f"frozen {stem} changed")
    if _sha256(_regular(frozen["spec_path"], "frozen spec")) != frozen["spec_file_id"]:
        raise ValueError("frozen spec changed")
    if (
        bool(Path(frozen["evaluator_path"]).stat().st_mode & stat.S_IXUSR)
        != frozen["evaluator_executable"]
    ):
        raise ValueError("frozen evaluator mode changed")


def _inventory(root, max_bytes, max_files):
    paths = []
    total = 0
    for p in sorted(root.rglob("*")):
        if p.is_symlink():
            raise ValueError("output symlink forbidden")
        if p.is_dir():
            continue
        if not p.is_file():
            raise ValueError("output special file forbidden")
        paths.append(p.resolve())
        total += p.stat().st_size
        if len(paths) > max_files:
            raise ValueError("output file limit exceeded")
        if total > max_bytes:
            raise ValueError("output byte limit exceeded")
    return {"paths": paths, "file_count": len(paths), "total_bytes": total}


def _arm_fields(arm, label):
    for attr in ("root", "execution_tree_id", "surface_id"):
        if not hasattr(arm, attr):
            raise ValueError(f"{label} must be a bound ExecutionArm")
    root = Path(arm.root).resolve()
    tree = arm.execution_tree_id
    surface = arm.surface_id
    if (
        not root.is_dir()
        or not isinstance(tree, str)
        or not tree
        or not isinstance(surface, str)
        or not surface
    ):
        raise ValueError(f"{label} arm lacks root/tree/surface identity")
    return root, tree, surface


def _failed(name, surface, tree, state, reason, diag=None):
    return {
        "arm": name,
        "execution_state": state,
        "surface_id": surface,
        "execution_tree_id": tree,
        "reason": reason,
        "diagnostics": dict(diag or {}),
    }


def _diagnostics(p, argv):
    get = lambda n, d=None: p.get(n, d) if isinstance(p, Mapping) else getattr(p, n, d)
    code = get("exit_code", get("returncode"))
    code = code if isinstance(code, int) and not isinstance(code, bool) else -1
    return {
        "argv": list(get("argv", argv)),
        "exit_code": code,
        "timed_out": bool(get("timed_out", False)),
        "cancelled": bool(get("cancelled", False)),
        "elapsed_seconds": float(get("elapsed_seconds", 0)),
        "stdout": str(get("stdout", "")),
        "stderr": str(get("stderr", "")),
        "stdout_truncated": bool(get("stdout_truncated", False)),
        "stderr_truncated": bool(get("stderr_truncated", False)),
    }


def _argv(spec, frozen, workspace):
    replacements = {
        "{evaluator_path}": str(frozen["evaluator_path"]),
        "{case_input_path}": str(frozen["case_input_path"]),
        "{workspace_path}": str(workspace),
        spec.evaluator_path: str(frozen["evaluator_path"]),
    }
    return [replacements.get(x, x) for x in spec.evaluator_argv]


def _environment_id(spec, frozen):
    resolved_executable = shutil.which(spec.evaluator_argv[0])
    exe = (
        Path(resolved_executable)
        if resolved_executable is not None
        else Path(spec.evaluator_argv[0])
    )
    record = {"argv0": spec.evaluator_argv[0]}
    if exe.is_file() and not exe.is_symlink():
        record |= {"path": str(exe.resolve()), "sha256": _sha256(exe)}
    return _canonical_id(
        {
            "declared": spec.environment_id,
            "evaluator_id": frozen["evaluator_id"],
            "cases_id": frozen["case_input_id"],
            "argv": spec.evaluator_argv,
            "settings": spec.effective_settings,
            "executable": record,
            "platform": platform.platform(),
            "python": list(sys.version_info[:3]),
        }
    )


def _limitations(spec):
    result = []
    if spec.stochastic:
        result.append(
            "stochastic evaluator seeds are not controlled by the paired harness"
        )
        if spec.repetitions == 1:
            result.append(
                "one stochastic repetition supports only an observed difference"
            )
    if spec.claim_scope == "development_cases":
        result.append("results apply to development cases exposed during refinement")
    return result


def _resolve(spec_path, raw, label):
    return _regular(
        Path(raw) if Path(raw).is_absolute() else spec_path.parent / raw, label
    )


def _regular(path, label):
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink")
    p = path.resolve()
    if not p.is_file():
        raise FileNotFoundError(f"{label} must be a regular file: {path}")
    return p


def _read_json(path, limit, label):
    if path.stat().st_size > limit:
        raise ValueError(f"{label} exceeds byte limit")
    data = path.read_bytes()
    if len(data) > limit:
        raise ValueError(f"{label} exceeds byte limit")
    try:
        return json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must be valid UTF-8 JSON") from exc


def _atomic_json(path, payload):
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    tmp.replace(path)


def _sha256(path):
    digest = sha256()
    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_id(payload):
    return (
        "sha256:"
        + sha256(
            json.dumps(
                payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode()
        ).hexdigest()
    )


def _check_id(declared, actual, label):
    if declared.removeprefix("sha256:") != actual:
        raise ValueError(f"{label}_content_id mismatch")


def _finite(value):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError("aggregate must be finite")
    return float(value)


def _default_runner():
    from .processes import run_bounded_process

    return run_bounded_process


__all__ = [
    "EVALUATION_SPEC_SCHEMA",
    "EVALUATION_REQUEST_SCHEMA",
    "EVALUATION_RESULT_SCHEMA",
    "PAIRED_EVALUATION_SCHEMA",
    "EvaluationSpec",
    "MetricDefinition",
    "compare_evaluation_aggregates",
    "finalize_paired_evaluation_record",
    "load_evaluation_spec",
    "run_paired_evaluation",
    "validate_paired_evaluation_record",
]
