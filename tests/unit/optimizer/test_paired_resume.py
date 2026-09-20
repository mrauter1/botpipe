from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from botpipe_optimizer.candidate_surfaces import derive_surface_manifest
from botpipe_optimizer.execution_trees import (
    capture_execution_tree,
    cleanup_owned_directory,
)
from botpipe_optimizer.paired_evaluation import run_paired_evaluation
from labs.workflows.workflow_and_eval_to_refined_workflow_package import (
    workflow as refinement,
)


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _evaluation_spec(root: Path) -> Path:
    evaluation = root / "evaluation"
    evaluation.mkdir()
    evaluator = evaluation / "evaluator.py"
    evaluator.write_text("# injected evaluator\n", encoding="utf-8")
    cases = evaluation / "cases.json"
    cases.write_text('{"cases":["case-1"]}\n', encoding="utf-8")
    spec = evaluation / "spec.json"
    spec.write_text(
        json.dumps(
            {
                "schema": "botpipe.optimizer.evaluation_spec/v1",
                "evaluator_argv": ["python", "{evaluator_path}"],
                "evaluator_path": "evaluator.py",
                "evaluator_content_id": _digest(evaluator),
                "case_input_path": "cases.json",
                "case_input_content_id": _digest(cases),
                "case_ids": ["case-1"],
                "repetitions": 1,
                "effective_settings": {"mode": "fixed"},
                "metrics": [
                    {
                        "name": "quality",
                        "unit": "score",
                        "direction": "higher_is_better",
                        "minimum_improvement": 0.25,
                        "maximum_regression": 0.0,
                    }
                ],
                "primary_metric": "quality",
                "guardrail_metrics": [],
                "claim_scope": "development_cases",
                "stochastic": False,
                "evaluator_kind": "external",
                "max_elapsed_seconds": 30.0,
                "per_arm_timeout_seconds": 10.0,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return spec


def _process_runner(
    calls: list[str],
    candidate_surface_id: str,
    requests: list[dict] | None = None,
):
    def run(argv, **kwargs):
        request = json.loads(Path(kwargs["env"]["BOTPIPE_EVAL_REQUEST"]).read_text())
        calls.append(request["surface_id"])
        if requests is not None:
            requests.append(request)
        quality = 2.0 if request["surface_id"] == candidate_surface_id else 1.0
        result = {
            "schema": "botpipe.optimizer.eval_result/v1",
            "execution_id": request["execution_id"],
            "surface_id": request["surface_id"],
            "spec_id": request["spec_id"],
            "cases": [
                {
                    "case_id": "case-1",
                    "repetition": 1,
                    "outcome": "scored",
                    "metrics": {"quality": quality},
                    "evidence_paths": [],
                    "usage_availability": "not_attempted",
                    "elapsed_seconds": 0.01,
                }
            ],
        }
        Path(kwargs["env"]["BOTPIPE_EVAL_RESULT"]).write_text(json.dumps(result))
        return SimpleNamespace(
            argv=tuple(argv),
            exit_code=0,
            timed_out=False,
            cancelled=False,
            elapsed_seconds=0.01,
            stdout="",
            stderr="",
            stdout_truncated=False,
            stderr_truncated=False,
        )

    return run


@pytest.fixture
def paired_inputs(tmp_path: Path):
    project = tmp_path / "project"
    (project / "pkg").mkdir(parents=True)
    (project / "pkg/app.py").write_text("VALUE = 'baseline'\n", encoding="utf-8")
    frozen_parent = tmp_path / "frozen"
    snapshot = capture_execution_tree(project, frozen_parent)

    candidate_root = tmp_path / "candidate"
    (candidate_root / "pkg").mkdir(parents=True)
    (candidate_root / "pkg/app.py").write_text(
        "VALUE = 'candidate'\n", encoding="utf-8"
    )
    boundary = {"package_root_relative_path": "pkg"}
    candidate_manifest = derive_surface_manifest(
        candidate_root,
        expected_root=candidate_root,
        boundary=boundary,
        surface_kind="candidate",
    )
    spec = _evaluation_spec(tmp_path)
    workflow_folder = tmp_path / "workflow-output"
    workflow_folder.mkdir()
    staging = tmp_path / "staging"
    staging.mkdir()
    ctx = SimpleNamespace(
        root=tmp_path,
        run_id="run-a",
        workflow_folder=workflow_folder,
        state=SimpleNamespace(evaluation_spec_path=str(spec)),
    )
    value = SimpleNamespace(
        ctx=ctx,
        repo_root=tmp_path,
        snapshot=snapshot,
        staging=staging,
        baseline_manifest={"surface_id": "surface-baseline"},
        candidate_manifest=candidate_manifest,
        spec=spec,
        project=project,
    )
    try:
        yield value
    finally:
        if snapshot.root.exists():
            cleanup_owned_directory(
                snapshot.root,
                owned_parent=snapshot.owned_parent,
                ownership_token=snapshot.ownership_token,
            )


def _run(inputs):
    return refinement._run_optional_paired_evaluation(
        inputs.ctx,
        repo_root=inputs.repo_root,
        snapshot=inputs.snapshot,
        staging=inputs.staging,
        baseline_manifest=inputs.baseline_manifest,
        candidate_manifest=inputs.candidate_manifest,
    )


def _install_real_runner(monkeypatch, inputs, calls, requests=None):
    def injected(**kwargs):
        return run_paired_evaluation(
            **kwargs,
            process_runner=_process_runner(
                calls,
                inputs.candidate_manifest["surface_id"],
                requests,
            ),
        )

    monkeypatch.setattr(refinement, "run_paired_evaluation", injected)


def test_same_run_complete_cache_does_not_launch_evaluators_again(
    paired_inputs, monkeypatch
):
    calls: list[str] = []
    _install_real_runner(monkeypatch, paired_inputs, calls)

    first = _run(paired_inputs)
    second = _run(paired_inputs)

    assert first == second
    assert all(arm["execution_state"] == "complete" for arm in first["arms"].values())
    assert len(calls) == 2


def test_t18_both_arms_receive_the_same_frozen_plan_and_limits(
    paired_inputs, monkeypatch
):
    calls: list[str] = []
    requests: list[dict] = []
    _install_real_runner(monkeypatch, paired_inputs, calls, requests)

    _run(paired_inputs)

    assert len(requests) == 2
    identity_fields = {
        "execution_id",
        "surface_id",
        "execution_tree_id",
        "workspace_path",
        "allowed_output_directory",
    }
    plans = [
        {key: value for key, value in request.items() if key not in identity_fields}
        for request in requests
    ]
    assert plans[0] == plans[1]
    assert plans[0]["case_ids"] == ["case-1"]
    assert plans[0]["repetitions"] == 1
    assert plans[0]["effective_settings"] == {"mode": "fixed"}
    assert plans[0]["remaining_limits"] == {
        "elapsed_seconds": 10.0,
        "max_provider_turns": None,
        "max_output_bytes": 50 * 1024 * 1024,
        "max_output_files": 10_000,
    }


def test_matching_interrupted_marker_requires_restart_without_relaunch(
    paired_inputs, monkeypatch
):
    launches = 0

    def interrupted(**_kwargs):
        nonlocal launches
        launches += 1
        raise RuntimeError("simulated interruption")

    monkeypatch.setattr(refinement, "run_paired_evaluation", interrupted)
    with pytest.raises(RuntimeError, match="simulated interruption"):
        _run(paired_inputs)
    assert launches == 1

    result = _run(paired_inputs)
    assert launches == 1
    assert result["execution_state"] == "failed"
    assert result["comparison"]["state"] == "inconclusive"
    assert result["stop_reason"] == "interrupted_paired_evaluation_restart_required"


@pytest.mark.parametrize("marker_state", ["complete", "interrupted"])
@pytest.mark.parametrize("drift", ["spec", "execution_tree"])
def test_same_run_drift_is_rejected_without_new_evaluator_launch(
    paired_inputs, monkeypatch, marker_state: str, drift: str
):
    calls: list[str] = []
    if marker_state == "complete":
        _install_real_runner(monkeypatch, paired_inputs, calls)
        _run(paired_inputs)
        expected_calls = 2
    else:

        def interrupted(**_kwargs):
            raise RuntimeError("simulated interruption")

        monkeypatch.setattr(refinement, "run_paired_evaluation", interrupted)
        with pytest.raises(RuntimeError):
            _run(paired_inputs)
        expected_calls = 0

    if drift == "spec":
        payload = json.loads(paired_inputs.spec.read_text())
        payload["effective_settings"] = {"mode": "changed"}
        paired_inputs.spec.write_text(json.dumps(payload), encoding="utf-8")
    else:
        (paired_inputs.snapshot.root / "pkg/app.py").write_text(
            "VALUE = 'drifted'\n", encoding="utf-8"
        )

    with pytest.raises(ValueError, match="stale|changed"):
        _run(paired_inputs)
    assert len(calls) == expected_calls


def test_new_run_in_same_folder_launches_a_fresh_pair(paired_inputs, monkeypatch):
    calls: list[str] = []
    _install_real_runner(monkeypatch, paired_inputs, calls)
    first = _run(paired_inputs)
    assert len(calls) == 2

    paired_inputs.ctx.run_id = "run-b"
    second = _run(paired_inputs)

    assert len(calls) == 4
    assert first["evaluation_attempt_id"] != second["evaluation_attempt_id"]
    assert first["invocation_id"] == "run-a"
    assert second["invocation_id"] == "run-b"
