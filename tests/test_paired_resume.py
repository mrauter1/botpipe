"""Saved paired results remain verifiable without executing another process."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from test_paired_evaluation import _arms, _runner_factory, _snapshot, _spec, _unchanged

from botpipe_optimizer.paired_evaluation import (
    finalize_paired_evaluation_record,
    run_paired_evaluation,
    validate_paired_evaluation_record,
)


@pytest.fixture
def saved_pair(tmp_path):
    spec = _spec(tmp_path)
    baseline, candidate = _arms(tmp_path)
    runner, calls = _runner_factory()
    record = run_paired_evaluation(
        evaluation_spec_path=spec,
        baseline_arm=baseline,
        candidate_arm=candidate,
        output_root=tmp_path / "out",
        process_runner=runner,
        snapshot_arm=_snapshot,
        assert_arm_unchanged=_unchanged,
    )
    record = finalize_paired_evaluation_record({**record, "invocation_id": "run-1"})
    kwargs = {
        "evaluation_spec_path": spec,
        "baseline_surface_id": baseline.surface_id,
        "candidate_surface_id": candidate.surface_id,
        "baseline_execution_tree_id": baseline.execution_tree_id,
        "candidate_execution_tree_id": candidate.execution_tree_id,
        "allowed_output_parent": tmp_path,
        "expected_invocation_id": "run-1",
    }
    return record, kwargs, calls


def test_saved_pair_validation_never_relaunches(saved_pair):
    record, kwargs, calls = saved_pair
    assert validate_paired_evaluation_record(record, **kwargs) == record
    assert validate_paired_evaluation_record(record, **kwargs) == record
    assert len(calls) == 2


@pytest.mark.parametrize(
    "name", ["evaluation-spec.json", "evaluator-evaluator.py", "cases-cases.json"]
)
@pytest.mark.parametrize("mutation", ["delete", "change"])
def test_cache_rejects_frozen_input_changes(saved_pair, name, mutation):
    record, kwargs, calls = saved_pair
    path = Path(record["execution_output_root"]) / "frozen" / name
    if mutation == "delete":
        path.unlink()
    else:
        path.write_text("changed\n")
    with pytest.raises((ValueError, OSError)):
        validate_paired_evaluation_record(record, **kwargs)
    assert len(calls) == 2


@pytest.mark.parametrize("field", ["invocation", "spec", "tree", "surface", "root"])
def test_cache_rejects_identity_drift(saved_pair, field):
    record, kwargs, calls = saved_pair
    if field == "spec":
        path = kwargs["evaluation_spec_path"]
        payload = json.loads(path.read_text())
        payload["effective_settings"] = {"changed": True}
        path.write_text(json.dumps(payload))
    else:
        key = {
            "invocation": "expected_invocation_id",
            "tree": "baseline_execution_tree_id",
            "surface": "candidate_surface_id",
            "root": "allowed_output_parent",
        }[field]
        kwargs[key] = "different"
    with pytest.raises(ValueError):
        validate_paired_evaluation_record(record, **kwargs)
    assert len(calls) == 2


@pytest.mark.parametrize(
    "field",
    [
        "aggregate",
        "evidence",
        "environment",
        "comparison",
        "promotion",
        "plan",
        "state",
    ],
)
def test_cache_recomputes_claims_even_with_rehashed_receipt(saved_pair, field):
    record, kwargs, calls = saved_pair
    record = copy.deepcopy(record)
    arm = record["arms"]["candidate"]
    if field == "aggregate":
        arm["aggregates"]["quality"] = 999.0
    elif field == "evidence":
        arm["evidence"] = [
            {"path": "../../spec.json", "sha256": "bogus", "size_bytes": 1}
        ]
    elif field == "environment":
        arm["reported_environment_id"] = "fabricated"
    elif field == "comparison":
        record["comparison"]["state"] = "regressed"
    elif field == "promotion":
        record["automatic_promotion"] = True
    elif field == "plan":
        record["plan"]["per_arm_timeout_seconds"] = 100000
    elif field == "state":
        arm["execution_state"] = "failed"
    record = finalize_paired_evaluation_record(record)
    with pytest.raises(ValueError):
        validate_paired_evaluation_record(record, **kwargs)
    assert len(calls) == 2


@pytest.mark.parametrize("mutation", ["result", "request", "extra_output", "symlink"])
def test_cache_revalidates_saved_outputs_and_request(saved_pair, mutation, tmp_path):
    record, kwargs, calls = saved_pair
    root = Path(record["execution_output_root"])
    if mutation == "result":
        path = root / "candidate/result.json"
        payload = json.loads(path.read_text())
        payload["cases"][0]["metrics"]["quality"] = 100.0
        path.write_text(json.dumps(payload))
    elif mutation == "request":
        path = root / "requests/candidate.json"
        payload = json.loads(path.read_text())
        payload["case_ids"] = ["unplanned"]
        path.write_text(json.dumps(payload))
    elif mutation == "extra_output":
        (root / "candidate/extra.bin").write_bytes(b"new output")
    else:
        path = root / "candidate"
        moved = tmp_path / "moved"
        path.rename(moved)
        path.symlink_to(moved, target_is_directory=True)
    with pytest.raises(ValueError):
        validate_paired_evaluation_record(record, **kwargs)
    assert len(calls) == 2
