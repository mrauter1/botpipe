from __future__ import annotations
import asyncio, json, shutil
from pathlib import Path
import pytest
from botpipe import Outcome
from botpipe.core.providers.fake import ScriptedLLMProvider
from botpipe.runtime.config import GitTrackingRuntimeConfig, RuntimeConfig
from botpipe.runtime.runner import RunnerOptions, run_workflow_package
from botpipe_optimizer.recommendations import (
    finalize_candidate_review_payload,
    finalize_candidate_set_payload,
)

_LAB = (
    Path(__file__).parents[2]
    / "labs/workflows/workflow_run_traces_to_optimization_candidates"
)


def _config():
    return RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False))


def _project(root: Path):
    (root / "examples/prompts").mkdir(parents=True)
    (root / "examples/prompts/work.md").write_text("Do reliable work.\n")
    (root / "examples/target.py").write_text(
        'from botpipe import FINISH,SELF,Workflow,Prompt,step\nclass Target(Workflow):\n name="target"\n work=step(prompt=Prompt.file("prompts/work.md"),retry=1,routes={"needs_rework":SELF,"done":FINISH})\n'
    )
    shutil.copytree(
        _LAB, root / "labs/workflows/workflow_run_traces_to_optimization_candidates"
    )


def _record_rework(root: Path):
    result = run_workflow_package(
        "examples/target.py",
        provider=ScriptedLLMProvider(
            llm_turns=[
                Outcome(raw_output="bad", tag="needs_rework"),
                Outcome(raw_output="ok", tag="done"),
            ]
        ),
        options=RunnerOptions(
            root=root,
            task_id="source",
            message="Exercise target",
            runtime_config=_config(),
        ),
    )
    assert result.terminal == "FINISH"


def _turns():
    def producer(request):
        evidence = json.loads(
            request.artifacts.workflow_optimization_evidence.read_text()
        )
        manifest = json.loads(request.artifacts.baseline_surface_manifest.read_text())
        target = next(
            path for path in manifest["relative_paths"] if path.endswith("work.md")
        )
        observation = evidence["observations"][0]["observation_id"]
        candidate_set = finalize_candidate_set_payload(
            {
                "schema": "botpipe.workflow_optimization.candidate_set/v2",
                "selected_workflow": "target",
                "evidence_snapshot_id": evidence["snapshot_id"],
                "baseline_surface_manifest_id": manifest["surface_id"],
                "candidates": [
                    {
                        "kind": "producer_prompt",
                        "title": "Clarify reliable work",
                        "targets": [target],
                        "cited_observation_ids": [observation],
                        "proposed_change": "Add an explicit completion check.",
                        "expected_effect": "Reduce observed rework.",
                        "risks": ["May be overly strict."],
                        "validation_plan": {
                            "description": "Compile and replay frozen cases.",
                            "checks": ["compile", "replay"],
                            "falsification": "Rework does not decrease.",
                        },
                        "payload": {
                            "prompt_paths": [target],
                            "replacement_strategy": "Add a completion checklist.",
                        },
                    }
                ],
                "next_action": "implement_candidate",
                "no_candidate_reason": None,
            }
        )
        request.artifacts.workflow_optimization_candidates.write_text(
            json.dumps(candidate_set.model_dump(mode="json", by_alias=True))
        )
        return "candidate written"

    def verifier(request):
        candidate_set = json.loads(
            request.artifacts.workflow_optimization_candidates.read_text()
        )
        review = finalize_candidate_review_payload(
            {
                "schema": "botpipe.workflow_optimization.candidate_review/v2",
                "candidate_set_id": candidate_set["candidate_set_id"],
                "evidence_snapshot_id": candidate_set["evidence_snapshot_id"],
                "baseline_surface_manifest_id": candidate_set[
                    "baseline_surface_manifest_id"
                ],
                "accepted": True,
                "reviewed_candidate_ids": [
                    item["candidate_id"] for item in candidate_set["candidates"]
                ],
                "findings": [],
            }
        )
        request.artifacts.workflow_optimization_candidate_review.write_text(
            json.dumps(review.model_dump(mode="json", by_alias=True))
        )
        return Outcome(
            raw_output="accepted",
            tag="recommendations_reviewed",
            payload={
                "selected_workflow": "target",
                "candidate_set_id": candidate_set["candidate_set_id"],
                "review_id": review.review_id,
                "summary": "Evidence-bound candidate accepted.",
            },
        )

    return producer, verifier


def _run_optimizer(root, provider, task="optimizer", **params):
    values = {
        "selected_workflow": "examples/target.py",
        "task_title": "Review target",
        **params,
    }
    return run_workflow_package(
        "labs/workflows/workflow_run_traces_to_optimization_candidates",
        provider=provider,
        options=RunnerOptions(
            root=root,
            task_id=task,
            message="Diagnose target",
            workflow_params=values,
            runtime_config=_config(),
        ),
    )


def _workflow_folder(root, task):
    return (
        root
        / ".botpipe/tasks"
        / task
        / "wf_workflow_run_traces_to_optimization_candidates"
    )


def test_default_recommendation_uses_exactly_one_producer_and_verifier(tmp_path: Path):
    _project(tmp_path)
    _record_rework(tmp_path)
    producer, verifier = _turns()
    provider = ScriptedLLMProvider(producer_turns=[producer], verifier_turns=[verifier])
    result = _run_optimizer(tmp_path, provider)
    assert result.terminal == "FINISH"
    assert [(call.kind, call.step_name) for call in provider.calls] == [
        ("producer", "recommend"),
        ("verifier", "recommend"),
    ]
    receipt = json.loads(
        (
            _workflow_folder(tmp_path, "optimizer")
            / "optimization_publication_receipt.json"
        ).read_text()
    )
    assert (
        receipt["status"] == "accepted"
        and receipt["improvement"] == "not_evaluated"
        and len(receipt["reviewed_candidate_ids"]) == 1
    )


def test_no_evidence_uses_zero_provider_calls(tmp_path: Path):
    _project(tmp_path)
    provider = ScriptedLLMProvider()
    result = _run_optimizer(tmp_path, provider, task="empty")
    assert result.terminal == "FINISH" and provider.calls == []
    folder = _workflow_folder(tmp_path, "empty")
    receipt = json.loads((folder / "optimization_publication_receipt.json").read_text())
    candidates = json.loads(
        (folder / "workflow_optimization_candidates.json").read_text()
    )
    assert (
        receipt["status"] == "accepted"
        and candidates["candidates"] == []
        and candidates["next_action"] in {"collect_evidence", "no_change"}
    )


def test_budget_exhaustion_before_verifier_writes_precise_incomplete_receipt(
    tmp_path: Path,
):
    _project(tmp_path)
    _record_rework(tmp_path)
    producer, _ = _turns()
    provider = ScriptedLLMProvider(producer_turns=[producer])
    with pytest.raises(Exception, match="budget exhausted"):
        _run_optimizer(tmp_path, provider, task="limited", max_provider_turns=1)
    receipt = json.loads(
        (
            _workflow_folder(tmp_path, "limited")
            / "optimization_publication_receipt.json"
        ).read_text()
    )
    assert (
        receipt["status"] == "incomplete"
        and "budget" in receipt["stop_reason"]
        and receipt["stop_reason"] != "analysis_in_progress"
    )


def test_invalid_explicit_run_replaces_stale_success_receipt(tmp_path: Path):
    _project(tmp_path)
    folder = _workflow_folder(tmp_path, "invalid-input")
    folder.mkdir(parents=True)
    (folder / "optimization_publication_receipt.json").write_text(
        json.dumps({"status": "accepted", "selected_workflow": "target"})
    )
    provider = ScriptedLLMProvider()
    with pytest.raises(Exception, match="does not resolve"):
        _run_optimizer(
            tmp_path,
            provider,
            task="invalid-input",
            run_refs=["missing/missing"],
        )
    receipt = json.loads((folder / "optimization_publication_receipt.json").read_text())
    assert receipt["status"] == "incomplete"
    assert "does not resolve" in receipt["stop_reason"]
    assert provider.calls == []


def test_provider_timeout_writes_precise_incomplete_receipt(tmp_path: Path):
    _project(tmp_path)
    _record_rework(tmp_path)

    async def slow_producer(_request):
        await asyncio.sleep(2)
        return "too late"

    provider = ScriptedLLMProvider(producer_turns=[slow_producer])
    with pytest.raises(Exception, match="exceeded"):
        _run_optimizer(
            tmp_path,
            provider,
            task="timed-out",
            provider_turn_timeout_seconds=1,
        )
    receipt = json.loads(
        (
            _workflow_folder(tmp_path, "timed-out")
            / "optimization_publication_receipt.json"
        ).read_text()
    )
    assert receipt["status"] == "incomplete"
    assert "provider_dispatch_timeout" in receipt["stop_reason"]
