from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from botpipe import Botpipe, current_run, workflow
from botpipe.providers import FakeProvider
from labs.workflows import optimizer_integration


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _evaluation_spec(root: Path) -> Path:
    evaluator = root / "evaluator.py"
    evaluator.write_text("# exact evaluator\n", encoding="utf-8")
    cases = root / "cases.json"
    cases.write_text('{"case": 1}\n', encoding="utf-8")
    spec = root / "evaluation.json"
    spec.write_text(
        json.dumps(
            {
                "schema": "botpipe.optimizer.evaluation_spec/v1",
                "evaluator_argv": ["python", "{evaluator_path}"],
                "evaluator_path": "evaluator.py",
                "evaluator_content_id": _digest(evaluator),
                "case_input_path": "cases.json",
                "case_input_content_id": _digest(cases),
                "case_ids": ["case"],
                "metrics": [
                    {
                        "name": "quality",
                        "unit": "score",
                        "direction": "higher_is_better",
                        "minimum_improvement": 0.1,
                    }
                ],
                "primary_metric": "quality",
            }
        ),
        encoding="utf-8",
    )
    return spec


@workflow
def frozen_plan(evaluation_spec_path: str):
    run = current_run()
    frozen = optimizer_integration.freeze_improvement_evaluation(
        workspace=str(run.workspace),
        evaluation_spec_path=evaluation_spec_path,
        staging_parent=str(run.folder / "evaluation-plan"),
        invocation_id=run.run_id,
    )
    if not (run.workspace / "finish").exists():
        raise KeyboardInterrupt("stop after freezing inputs")
    return frozen


@pytest.mark.parametrize("frozen_drift", [False, True])
def test_evaluation_inputs_remain_fixed_across_resume(tmp_path, frozen_drift):
    spec = _evaluation_spec(tmp_path)
    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        run = client.run(frozen_plan, spec.name)
        assert run.status == "interrupted", run.error

        (tmp_path / "evaluator.py").write_text("# source changed\n", encoding="utf-8")
        spec.unlink()
        if frozen_drift:
            evaluator = next(run.folder.rglob("evaluator-evaluator.py"))
            evaluator.write_text("# frozen drift\n", encoding="utf-8")
        (tmp_path / "finish").touch()
        replay = client.resume(run.run_id)
        if frozen_drift:
            assert not replay.ok
            assert "frozen evaluator changed" in replay.error
        else:
            assert replay.ok, replay.error
            assert Path(replay.value["evaluator_path"]).read_text() == "# exact evaluator\n"
