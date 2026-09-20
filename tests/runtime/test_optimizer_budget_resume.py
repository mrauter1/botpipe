from __future__ import annotations

import json
from pathlib import Path

import pytest

from botpipe.core.providers.fake import ScriptedLLMProvider
from botpipe.runtime.runner import RunnerOptions, run_workflow_package
from tests.runtime.test_optimizer_v2_workflow import (
    _config,
    _project,
    _record_rework,
    _turns,
    _workflow_folder,
)

_OPTIMIZER = "labs/workflows/workflow_run_traces_to_optimization_candidates"


def _start_interrupted_optimizer(
    root: Path, *, task_id: str, max_provider_turns: int = 2
) -> tuple[Path, Path]:
    _project(root)
    _record_rework(root)
    producer, _ = _turns()

    def interrupt_after_reserved_producer(request):
        producer(request)
        raise RuntimeError("simulated optimizer interruption")

    provider = ScriptedLLMProvider(producer_turns=[interrupt_after_reserved_producer])
    with pytest.raises(RuntimeError, match="simulated optimizer interruption"):
        run_workflow_package(
            _OPTIMIZER,
            provider=provider,
            options=RunnerOptions(
                root=root,
                task_id=task_id,
                message="Diagnose target",
                workflow_params={
                    "selected_workflow": "examples/target.py",
                    "task_title": "Review target",
                    "max_provider_turns": max_provider_turns,
                },
                runtime_config=_config(),
            ),
        )

    workflow_folder = _workflow_folder(root, task_id)
    run_dirs = list((workflow_folder / "runs").iterdir())
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]
    metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert metadata["provider_dispatch_budget"]["used_turns"] == 1
    return workflow_folder, run_dir


def _resume(root: Path, *, task_id: str, run_id: str, provider: ScriptedLLMProvider):
    return run_workflow_package(
        _OPTIMIZER,
        provider=provider,
        options=RunnerOptions(
            root=root,
            task_id=task_id,
            run_id=run_id,
            resume=True,
            message="Resume optimizer",
            runtime_config=_config(),
        ),
    )


def test_interrupted_optimizer_resume_preserves_consumed_dispatches(
    tmp_path: Path,
) -> None:
    task_id = "optimizer-budget-resume"
    workflow_folder, run_dir = _start_interrupted_optimizer(tmp_path, task_id=task_id)
    producer, verifier = _turns()
    resumed_provider = ScriptedLLMProvider(
        producer_turns=[producer], verifier_turns=[verifier]
    )

    with pytest.raises(Exception, match="budget exhausted"):
        _resume(
            tmp_path,
            task_id=task_id,
            run_id=run_dir.name,
            provider=resumed_provider,
        )

    metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    receipt = json.loads(
        (workflow_folder / "optimization_publication_receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert metadata["provider_dispatch_budget"]["used_turns"] == 2
    assert [(call.kind, call.step_name) for call in resumed_provider.calls] == [
        ("producer", "recommend")
    ]
    assert receipt["status"] == "incomplete"
    assert "budget" in receipt["stop_reason"]


@pytest.mark.parametrize("mutation", ["missing", "incompatible"])
def test_optimizer_resume_rejects_missing_or_incompatible_budget_checkpoint(
    tmp_path: Path,
    mutation: str,
) -> None:
    task_id = f"optimizer-budget-{mutation}"
    _, run_dir = _start_interrupted_optimizer(tmp_path, task_id=task_id)
    metadata_path = run_dir / "run.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if mutation == "missing":
        metadata.pop("provider_dispatch_budget")
        expected = "budget is missing"
    else:
        metadata["provider_dispatch_budget"]["max_turns"] = 3
        expected = "budget resume rejected"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    provider = ScriptedLLMProvider()

    with pytest.raises(Exception, match=expected):
        _resume(
            tmp_path,
            task_id=task_id,
            run_id=run_dir.name,
            provider=provider,
        )

    assert provider.calls == []


def test_optimizer_resume_rejects_corrupted_frozen_baseline(tmp_path: Path) -> None:
    task_id = "optimizer-corrupt-baseline"
    workflow_folder, run_dir = _start_interrupted_optimizer(
        tmp_path,
        task_id=task_id,
        max_provider_turns=3,
    )
    manifest = json.loads(
        (workflow_folder / "baseline_surface_manifest.json").read_text(encoding="utf-8")
    )
    frozen_file = Path(manifest["files"][0]["surface_path"])
    frozen_file.write_bytes(frozen_file.read_bytes() + b"\n# corrupted after capture\n")
    producer, verifier = _turns()
    provider = ScriptedLLMProvider(producer_turns=[producer], verifier_turns=[verifier])

    with pytest.raises(
        Exception, match="manifest surface_id must match derived surface"
    ):
        _resume(
            tmp_path,
            task_id=task_id,
            run_id=run_dir.name,
            provider=provider,
        )

    receipt = json.loads(
        (workflow_folder / "optimization_publication_receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert receipt["status"] == "incomplete"
    assert "manifest surface_id must match derived surface" in receipt["stop_reason"]
