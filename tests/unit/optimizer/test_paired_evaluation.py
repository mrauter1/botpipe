from __future__ import annotations

import json
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
    spec.write_text(json.dumps({
        "schema": "botpipe.optimizer.evaluation_spec/v1",
        "evaluator_argv": ["python", "{evaluator_path}"],
        "evaluator_path": "evaluator.py",
        "evaluator_content_id": _digest(evaluator),
        "case_input_path": "cases.json",
        "case_input_content_id": _digest(cases),
        "case_ids": ["c1", "c2"],
        "repetitions": 2,
        "metrics": [
            {"name": "quality", "unit": "score", "direction": "higher_is_better", "aggregation": "mean", "minimum_improvement": 0.25, "maximum_regression": 0.0},
            {"name": "latency", "unit": "seconds", "direction": "lower_is_better", "aggregation": "sum", "maximum_regression": 0.5},
        ],
        "primary_metric": "quality",
        "guardrail_metrics": ["latency"],
        "stochastic": stochastic,
    }), encoding="utf-8")
    return spec


def _arms(tmp_path: Path):
    baseline_root = tmp_path / "baseline-arm"
    candidate_root = tmp_path / "candidate-arm"
    baseline_root.mkdir(); candidate_root.mkdir()
    baseline = SimpleNamespace(root=baseline_root, execution_tree_id="tree-baseline", surface_id="surface-baseline")
    candidate = SimpleNamespace(root=candidate_root, execution_tree_id="tree-candidate", surface_id="surface-candidate")
    return baseline, candidate


def _snapshot(arm):
    return {"execution_tree_id": arm.execution_tree_id}


def _unchanged(expected, root, *, phase):
    assert expected["execution_tree_id"].startswith("tree-")
    assert root.is_dir()


def _runner_factory(*, candidate_quality=2.0, candidate_latency=1.0, baseline_quality=1.0, baseline_latency=1.0, malformed=None):
    calls = []
    def runner(argv, **kwargs):
        calls.append((list(argv), kwargs["cwd"]))
        request = json.loads(Path(kwargs["env"]["BOTPIPE_EVAL_REQUEST"]).read_text())
        is_candidate = request["surface_id"] == "surface-candidate"
        quality = candidate_quality if is_candidate else baseline_quality
        latency = candidate_latency if is_candidate else baseline_latency
        cases = [
            {"case_id": case, "repetition": repetition, "outcome": "scored", "metrics": {"quality": quality, "latency": latency}, "evidence_paths": [], "usage_availability": "not_attempted", "elapsed_seconds": 0.01}
            for case in request["case_ids"] for repetition in range(1, request["repetitions"] + 1)
        ]
        if malformed == "duplicate": cases[-1] = dict(cases[0])
        if malformed == "nan": cases[0]["metrics"]["quality"] = float("nan")
        payload = {"schema": "botpipe.optimizer.eval_result/v1", "execution_id": request["execution_id"], "surface_id": request["surface_id"], "spec_id": request["spec_id"], "cases": cases}
        Path(kwargs["env"]["BOTPIPE_EVAL_RESULT"]).write_text(json.dumps(payload))
        code = 9 if malformed == "crash" else 0
        return SimpleNamespace(argv=tuple(argv), exit_code=code, timed_out=False, cancelled=False, elapsed_seconds=0.01, stdout="", stderr="boom" if code else "", stdout_truncated=False, stderr_truncated=False)
    return runner, calls


def test_paired_runner_runs_one_process_per_bound_disjoint_arm(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    baseline, candidate = _arms(tmp_path)
    runner, calls = _runner_factory(candidate_quality=1.5)
    result = run_paired_evaluation(evaluation_spec_path=spec, baseline_arm=baseline, candidate_arm=candidate, output_root=tmp_path / "out", process_runner=runner, snapshot_arm=_snapshot, assert_arm_unchanged=_unchanged)
    assert len(calls) == 2
    assert result["comparison"]["state"] == "improved"
    assert result["comparison"]["claim_scope"] == "development_cases"
    assert result["automatic_promotion"] is False
    assert [item["execution_state"] for item in result["arms"].values()] == ["complete", "complete"]


@pytest.mark.parametrize("malformed", ["duplicate", "nan", "crash"])
def test_protocol_failure_cannot_produce_improvement(tmp_path: Path, malformed: str) -> None:
    spec = _spec(tmp_path)
    baseline, candidate = _arms(tmp_path)
    runner, calls = _runner_factory(candidate_quality=100.0, malformed=malformed)
    result = run_paired_evaluation(evaluation_spec_path=spec, baseline_arm=baseline, candidate_arm=candidate, output_root=tmp_path / "out", process_runner=runner, snapshot_arm=_snapshot, assert_arm_unchanged=_unchanged)
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
        run_paired_evaluation(evaluation_spec_path=spec, baseline_arm=baseline, candidate_arm=candidate, output_root=tmp_path / "out", process_runner=runner, snapshot_arm=_snapshot, assert_arm_unchanged=_unchanged)
    assert calls == []
    assert payload["evaluator_content_id"] != _digest(tmp_path / "evaluator.py")


def test_same_or_unbound_arms_are_rejected(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    baseline, _ = _arms(tmp_path)
    with pytest.raises(ValueError, match="disjoint"):
        run_paired_evaluation(evaluation_spec_path=spec, baseline_arm=baseline, candidate_arm=baseline, output_root=tmp_path / "out", process_runner=lambda *a, **k: None, snapshot_arm=_snapshot, assert_arm_unchanged=_unchanged)
    baseline.surface_id = None
    _, candidate = _arms(tmp_path / "other") if False else (None, None)
    with pytest.raises(ValueError, match="lacks root/tree/surface identity"):
        run_paired_evaluation(evaluation_spec_path=spec, baseline_arm=baseline, candidate_arm=SimpleNamespace(root=tmp_path / "candidate-arm", execution_tree_id="tree", surface_id="surface"), output_root=tmp_path / "out2", process_runner=lambda *a, **k: None, snapshot_arm=_snapshot, assert_arm_unchanged=_unchanged)


def test_comparison_regression_tie_guardrail_and_stochastic_scope(tmp_path: Path) -> None:
    spec = EvaluationSpec.model_validate(json.loads(_spec(tmp_path, stochastic=True).read_text()))
    assert compare_evaluation_aggregates(spec, {"quality": 1.0, "latency": 4.0}, {"quality": 1.25, "latency": 4.0})["state"] == "improved"
    assert compare_evaluation_aggregates(spec, {"quality": 1.0, "latency": 4.0}, {"quality": 1.1, "latency": 4.0})["state"] == "no_material_change"
    assert compare_evaluation_aggregates(spec, {"quality": 1.0, "latency": 4.0}, {"quality": 1.5, "latency": 5.0})["state"] == "regressed"
    inconclusive = compare_evaluation_aggregates(spec, {"quality": 1.0, "latency": 4.0}, {"quality": 2.0, "latency": 4.0}, comparable=False)
    assert inconclusive["state"] == "inconclusive"
    # This spec has two repetitions; single-repetition warnings are tested by the model contract itself.
    assert inconclusive["claim_scope"] == "development_cases"
