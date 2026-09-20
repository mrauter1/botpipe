from __future__ import annotations

import json
import sys
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from botpipe_optimizer.paired_evaluation import (
    EvaluationSpec,
    compare_evaluation_aggregates,
    run_paired_evaluation,
)


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _spec(tmp_path: Path, *, stochastic: bool = False) -> Path:
    evaluator = tmp_path / "evaluator.py"
    evaluator.write_text("# frozen evaluator\n", encoding="utf-8")
    cases = tmp_path / "cases.json"
    cases.write_text("{}\n", encoding="utf-8")
    spec = tmp_path / "spec.json"
    spec.write_text(
        json.dumps(
            {
                "schema": "botpipe.optimizer.evaluation_spec/v1",
                "evaluator_argv": ["python", "{evaluator_path}"],
                "evaluator_path": "evaluator.py",
                "evaluator_content_id": _digest(evaluator),
                "case_input_path": "cases.json",
                "case_input_content_id": _digest(cases),
                "case_ids": ["c1", "c2"],
                "repetitions": 2,
                "metrics": [
                    {
                        "name": "quality",
                        "unit": "score",
                        "direction": "higher_is_better",
                        "aggregation": "mean",
                        "minimum_improvement": 0.25,
                        "maximum_regression": 0.0,
                    },
                    {
                        "name": "latency",
                        "unit": "seconds",
                        "direction": "lower_is_better",
                        "aggregation": "sum",
                        "maximum_regression": 0.5,
                    },
                ],
                "primary_metric": "quality",
                "guardrail_metrics": ["latency"],
                "stochastic": stochastic,
            }
        ),
        encoding="utf-8",
    )
    return spec


def _arms(tmp_path: Path):
    baseline_root = tmp_path / "baseline-arm"
    candidate_root = tmp_path / "candidate-arm"
    baseline_root.mkdir()
    candidate_root.mkdir()
    baseline = SimpleNamespace(
        root=baseline_root,
        execution_tree_id="tree-baseline",
        surface_id="surface-baseline",
    )
    candidate = SimpleNamespace(
        root=candidate_root,
        execution_tree_id="tree-candidate",
        surface_id="surface-candidate",
    )
    return baseline, candidate


def _snapshot(arm):
    return {"execution_tree_id": arm.execution_tree_id}


def _unchanged(expected, root, *, phase):
    assert expected["execution_tree_id"].startswith("tree-")
    assert root.is_dir()


def _runner_factory(
    *,
    candidate_quality=2.0,
    candidate_latency=1.0,
    baseline_quality=1.0,
    baseline_latency=1.0,
    malformed=None,
):
    calls = []

    def runner(argv, **kwargs):
        calls.append((list(argv), kwargs["cwd"]))
        request = json.loads(Path(kwargs["env"]["BOTPIPE_EVAL_REQUEST"]).read_text())
        is_candidate = request["surface_id"] == "surface-candidate"
        quality = candidate_quality if is_candidate else baseline_quality
        latency = candidate_latency if is_candidate else baseline_latency
        cases = [
            {
                "case_id": case,
                "repetition": repetition,
                "outcome": "scored",
                "metrics": {"quality": quality, "latency": latency},
                "evidence_paths": [],
                "usage_availability": "not_attempted",
                "elapsed_seconds": 0.01,
            }
            for case in request["case_ids"]
            for repetition in range(1, request["repetitions"] + 1)
        ]
        if malformed == "duplicate":
            cases[-1] = dict(cases[0])
        if malformed == "nan":
            cases[0]["metrics"]["quality"] = float("nan")
        if malformed == "unknown_case":
            cases[0]["case_id"] = "unplanned-case"
        if malformed == "missing_case":
            cases.pop()
        if malformed == "missing_metric":
            cases[0]["metrics"].pop("quality")
        if malformed == "declared_failure" and is_candidate:
            for case in cases:
                case["outcome"] = "failed"
                case["metrics"]["quality"] = 0.0
        if malformed == "escaping_evidence":
            outside = Path(kwargs["cwd"]).parent / "outside.txt"
            outside.write_text("outside the allowed output directory")
            cases[0]["evidence_paths"] = [str(outside)]
        payload = {
            "schema": "botpipe.optimizer.eval_result/v1",
            "execution_id": request["execution_id"],
            "surface_id": request["surface_id"],
            "spec_id": request["spec_id"],
            "cases": cases,
        }
        result_path = Path(kwargs["env"]["BOTPIPE_EVAL_RESULT"])
        if malformed == "stale_result":
            payload["execution_id"] = "a-different-execution"
        if malformed == "different_environment" and is_candidate:
            payload["environment_id"] = "a-different-environment"
        if malformed != "missing_result":
            result_path.write_text(json.dumps(payload))
        if malformed == "oversized_output":
            (result_path.parent / "oversized.bin").write_bytes(b"x" * 4097)
        code = 9 if malformed == "crash" else 0
        return SimpleNamespace(
            argv=tuple(argv),
            exit_code=code,
            timed_out=False,
            cancelled=False,
            elapsed_seconds=0.01,
            stdout="",
            stderr="boom" if code else "",
            stdout_truncated=False,
            stderr_truncated=False,
        )

    return runner, calls


def test_paired_runner_runs_one_process_per_bound_disjoint_arm(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    baseline, candidate = _arms(tmp_path)
    runner, calls = _runner_factory(candidate_quality=1.5)
    result = run_paired_evaluation(
        evaluation_spec_path=spec,
        baseline_arm=baseline,
        candidate_arm=candidate,
        output_root=tmp_path / "out",
        process_runner=runner,
        snapshot_arm=_snapshot,
        assert_arm_unchanged=_unchanged,
    )
    assert len(calls) == 2
    assert result["comparison"]["state"] == "improved"
    assert result["comparison"]["claim_scope"] == "development_cases"
    assert result["automatic_promotion"] is False
    assert [item["execution_state"] for item in result["arms"].values()] == [
        "complete",
        "complete",
    ]


@pytest.mark.parametrize(
    "malformed",
    [
        "duplicate",
        "nan",
        "crash",
        "unknown_case",
        "missing_case",
        "missing_metric",
        "escaping_evidence",
        "stale_result",
        "missing_result",
        "oversized_output",
    ],
)
def test_protocol_failure_cannot_produce_improvement(
    tmp_path: Path, malformed: str
) -> None:
    spec = _spec(tmp_path)
    if malformed == "oversized_output":
        payload = json.loads(spec.read_text())
        payload["max_evaluation_output_bytes"] = 4096
        spec.write_text(json.dumps(payload))
    baseline, candidate = _arms(tmp_path)
    runner, calls = _runner_factory(candidate_quality=100.0, malformed=malformed)
    result = run_paired_evaluation(
        evaluation_spec_path=spec,
        baseline_arm=baseline,
        candidate_arm=candidate,
        output_root=tmp_path / "out",
        process_runner=runner,
        snapshot_arm=_snapshot,
        assert_arm_unchanged=_unchanged,
    )
    assert len(calls) == 2
    assert result["comparison"]["state"] == "inconclusive"
    assert all(item["execution_state"] == "failed" for item in result["arms"].values())


def test_candidate_cannot_change_frozen_evaluator(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    payload = json.loads(spec.read_text())
    (tmp_path / "evaluator.py").write_text("# weakened\n")
    baseline, candidate = _arms(tmp_path)
    runner, calls = _runner_factory()
    with pytest.raises(ValueError, match="evaluator_content_id mismatch"):
        run_paired_evaluation(
            evaluation_spec_path=spec,
            baseline_arm=baseline,
            candidate_arm=candidate,
            output_root=tmp_path / "out",
            process_runner=runner,
            snapshot_arm=_snapshot,
            assert_arm_unchanged=_unchanged,
        )
    assert calls == []
    assert payload["evaluator_content_id"] != _digest(tmp_path / "evaluator.py")


def test_same_or_unbound_arms_are_rejected(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    baseline, _ = _arms(tmp_path)
    with pytest.raises(ValueError, match="disjoint"):
        run_paired_evaluation(
            evaluation_spec_path=spec,
            baseline_arm=baseline,
            candidate_arm=baseline,
            output_root=tmp_path / "out",
            process_runner=lambda *a, **k: None,
            snapshot_arm=_snapshot,
            assert_arm_unchanged=_unchanged,
        )
    baseline.surface_id = None
    with pytest.raises(ValueError, match="lacks root/tree/surface identity"):
        run_paired_evaluation(
            evaluation_spec_path=spec,
            baseline_arm=baseline,
            candidate_arm=SimpleNamespace(
                root=tmp_path / "candidate-arm",
                execution_tree_id="tree",
                surface_id="surface",
            ),
            output_root=tmp_path / "out2",
            process_runner=lambda *a, **k: None,
            snapshot_arm=_snapshot,
            assert_arm_unchanged=_unchanged,
        )


def test_comparison_regression_tie_guardrail_and_stochastic_scope(
    tmp_path: Path,
) -> None:
    spec = EvaluationSpec.model_validate(
        json.loads(_spec(tmp_path, stochastic=True).read_text())
    )
    assert (
        compare_evaluation_aggregates(
            spec, {"quality": 1.0, "latency": 4.0}, {"quality": 1.25, "latency": 4.0}
        )["state"]
        == "improved"
    )
    assert (
        compare_evaluation_aggregates(
            spec, {"quality": 1.0, "latency": 4.0}, {"quality": 1.1, "latency": 4.0}
        )["state"]
        == "no_material_change"
    )
    assert (
        compare_evaluation_aggregates(
            spec, {"quality": 1.0, "latency": 4.0}, {"quality": 1.5, "latency": 5.0}
        )["state"]
        == "regressed"
    )
    inconclusive = compare_evaluation_aggregates(
        spec,
        {"quality": 1.0, "latency": 4.0},
        {"quality": 2.0, "latency": 4.0},
        comparable=False,
    )
    assert inconclusive["state"] == "inconclusive"
    assert inconclusive["claim_scope"] == "development_cases"


def test_single_stochastic_repetition_discloses_its_limit(tmp_path: Path) -> None:
    payload = json.loads(_spec(tmp_path, stochastic=True).read_text())
    payload["repetitions"] = 1
    result = compare_evaluation_aggregates(
        payload, {"quality": 1.0, "latency": 4.0}, {"quality": 2.0, "latency": 4.0}
    )
    assert result["state"] == "improved"
    assert any(
        "one stochastic repetition" in limitation
        for limitation in result["limitations"]
    )


@pytest.mark.parametrize(
    ("mode", "expected"),
    [("declared_failure", "regressed"), ("different_environment", "inconclusive")],
)
def test_complete_failed_cases_and_noncomparable_environments_remain_distinct(
    tmp_path: Path, mode: str, expected: str
) -> None:
    spec = _spec(tmp_path)
    baseline, candidate = _arms(tmp_path)
    runner, calls = _runner_factory(malformed=mode)
    result = run_paired_evaluation(
        evaluation_spec_path=spec,
        baseline_arm=baseline,
        candidate_arm=candidate,
        output_root=tmp_path / "out",
        process_runner=runner,
        snapshot_arm=_snapshot,
        assert_arm_unchanged=_unchanged,
    )
    assert len(calls) == 2
    assert all(arm["execution_state"] == "complete" for arm in result["arms"].values())
    assert result["comparison"]["state"] == expected


def test_evaluation_spec_allows_repeated_argv_entries(tmp_path: Path) -> None:
    spec_path = _spec(tmp_path)
    payload = json.loads(spec_path.read_text())
    payload["evaluator_argv"] = [sys.executable, "{evaluator_path}", "--flag", "--flag"]
    spec_path.write_text(json.dumps(payload))
    spec = EvaluationSpec.model_validate(payload)
    assert spec.evaluator_argv[-2:] == ["--flag", "--flag"]


@pytest.mark.parametrize(
    "target", ["baseline", "candidate", "evaluator", "cases", "spec", "frozen"]
)
def test_evaluator_cannot_mutate_other_arm_or_frozen_sources(tmp_path, target):
    spec = _spec(tmp_path)
    baseline, candidate = _arms(tmp_path)
    for arm in (baseline, candidate):
        (arm.root / "source.py").write_text("VALUE = 1\n")

    def snapshot(arm):
        return {
            "execution_tree_id": arm.execution_tree_id,
            "digest": _digest(arm.root / "source.py"),
        }

    def unchanged(expected, root, *, phase):
        if _digest(root / "source.py") != expected["digest"]:
            raise ValueError("execution arm changed")

    delegate, calls = _runner_factory()

    def runner(argv, **kwargs):
        result = delegate(argv, **kwargs)
        # Modify baseline only from candidate: its own post-run check already passed.
        if len(calls) == 2:
            path = {
                "baseline": baseline.root / "source.py",
                "candidate": candidate.root / "source.py",
                "evaluator": tmp_path / "evaluator.py",
                "cases": tmp_path / "cases.json",
                "spec": spec,
                "frozen": Path(argv[1]),
            }[target]
            path.write_text("mutated\n")
        return result

    with pytest.raises(ValueError, match="changed"):
        run_paired_evaluation(
            evaluation_spec_path=spec,
            baseline_arm=baseline,
            candidate_arm=candidate,
            output_root=tmp_path / "out",
            process_runner=runner,
            snapshot_arm=snapshot,
            assert_arm_unchanged=unchanged,
        )
    assert len(calls) == 2


@pytest.mark.parametrize(
    "mutation", ["boolean_metric", "infinite_aggregate", "symlink", "file_count"]
)
def test_additional_invalid_results_are_inconclusive(tmp_path, mutation):
    spec = _spec(tmp_path)
    payload = json.loads(spec.read_text())
    if mutation == "file_count":
        payload["max_evaluation_output_files"] = 1
        spec.write_text(json.dumps(payload))
    baseline, candidate = _arms(tmp_path)
    delegate, calls = _runner_factory()

    def runner(argv, **kwargs):
        result = delegate(argv, **kwargs)
        path = Path(kwargs["env"]["BOTPIPE_EVAL_RESULT"])
        payload = json.loads(path.read_text())
        if mutation == "boolean_metric":
            payload["cases"][0]["metrics"]["quality"] = True
        elif mutation == "infinite_aggregate":
            for case in payload["cases"]:
                case["metrics"]["quality"] = 1e308
        elif mutation == "symlink":
            (path.parent / "linked").symlink_to(spec)
        else:
            (path.parent / "extra").write_text("extra")
        path.write_text(json.dumps(payload))
        return result

    record = run_paired_evaluation(
        evaluation_spec_path=spec,
        baseline_arm=baseline,
        candidate_arm=candidate,
        output_root=tmp_path / "out",
        process_runner=runner,
        snapshot_arm=_snapshot,
        assert_arm_unchanged=_unchanged,
    )
    assert record["comparison"]["state"] == "inconclusive"
    assert len(calls) == 2


def test_real_subprocess_runs_frozen_evaluator_once_per_arm(tmp_path):
    spec = _spec(tmp_path)
    evaluator = tmp_path / "evaluator.py"
    evaluator.write_text("""import json, os
from pathlib import Path
request = json.loads(Path(os.environ["BOTPIPE_EVAL_REQUEST"]).read_text())
quality = 2.0 if request["surface_id"] == "surface-candidate" else 1.0
cases = [dict(case_id=case, repetition=repetition, outcome="scored",
              metrics=dict(quality=quality, latency=1.0), evidence_paths=["evidence.txt"],
              usage_availability="not_attempted", elapsed_seconds=0.01)
         for case in request["case_ids"] for repetition in range(1, request["repetitions"] + 1)]
result = {"schema": "botpipe.optimizer.eval_result/v1",
          **{key: request[key] for key in ("execution_id", "surface_id", "spec_id")}, "cases": cases}
output = Path(os.environ["BOTPIPE_EVAL_RESULT"])
(output.parent / "evidence.txt").write_text("scored frozen cases")
temporary = output.with_suffix(".tmp")
temporary.write_text(json.dumps(result))
temporary.replace(output)
""")
    payload = json.loads(spec.read_text())
    payload["evaluator_argv"] = [sys.executable, "{evaluator_path}"]
    payload["evaluator_content_id"] = _digest(evaluator)
    spec.write_text(json.dumps(payload))
    baseline, candidate = _arms(tmp_path)
    record = run_paired_evaluation(
        evaluation_spec_path=spec,
        baseline_arm=baseline,
        candidate_arm=candidate,
        output_root=tmp_path / "out",
        snapshot_arm=_snapshot,
        assert_arm_unchanged=_unchanged,
    )
    assert record["comparison"]["state"] == "improved", record
    assert all(arm["diagnostics"]["exit_code"] == 0 for arm in record["arms"].values())
    assert all(
        arm["evidence"][0]["path"] == "evidence.txt" for arm in record["arms"].values()
    )
    from botpipe_optimizer.paired_evaluation import validate_paired_evaluation_record

    assert (
        validate_paired_evaluation_record(
            record,
            evaluation_spec_path=spec,
            baseline_surface_id=baseline.surface_id,
            candidate_surface_id=candidate.surface_id,
            baseline_execution_tree_id=baseline.execution_tree_id,
            candidate_execution_tree_id=candidate.execution_tree_id,
            allowed_output_parent=tmp_path,
        )
        == record
    )


@pytest.mark.parametrize(
    "budget",
    [
        None,
        {"max_turns": 4, "used_turns": 1},
        {"max_turns": 3, "used_turns": True},
        {"max_turns": 3, "used_turns": 4},
        {"max_turns": 3, "used_turns": 3, "exhausted": True},
        {"max_turns": 3, "used_turns": 2, "exhausted": False},
    ],
)
def test_botpipe_provider_budget_is_per_arm_and_required(tmp_path, budget):
    spec = _spec(tmp_path)
    payload = json.loads(spec.read_text())
    payload.update(evaluator_kind="botpipe", max_provider_turns_per_arm=3)
    spec.write_text(json.dumps(payload))
    baseline, candidate = _arms(tmp_path)
    delegate, calls = _runner_factory()
    requests = []

    def runner(argv, **kwargs):
        result = delegate(argv, **kwargs)
        requests.append(
            json.loads(Path(kwargs["env"]["BOTPIPE_EVAL_REQUEST"]).read_text())
        )
        path = Path(kwargs["env"]["BOTPIPE_EVAL_RESULT"])
        payload = json.loads(path.read_text())
        payload["provider_budget"] = budget
        path.write_text(json.dumps(payload))
        return result

    record = run_paired_evaluation(
        evaluation_spec_path=spec,
        baseline_arm=baseline,
        candidate_arm=candidate,
        output_root=tmp_path / "out",
        process_runner=runner,
        snapshot_arm=_snapshot,
        assert_arm_unchanged=_unchanged,
    )
    assert len(calls) == 2
    assert all(r["remaining_limits"]["max_provider_turns"] == 3 for r in requests)
    expected = (
        "improved" if budget and budget.get("used_turns") == 2 else "inconclusive"
    )
    assert record["comparison"]["state"] == expected
    if budget and budget.get("exhausted"):
        assert all(
            arm["execution_state"] == "budget_exhausted"
            for arm in record["arms"].values()
        )
