from __future__ import annotations

import json
import shutil
import sys
from hashlib import sha256
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

_REPO_ROOT = Path(__file__).parents[2]
_OPTIMIZER_LAB = (
    _REPO_ROOT / "labs/workflows/workflow_run_traces_to_optimization_candidates"
)
_REFINEMENT_LAB = (
    _REPO_ROOT / "labs/workflows/workflow_and_eval_to_refined_workflow_package"
)


def _config() -> RuntimeConfig:
    return RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False))


def _write_project(root: Path) -> None:
    (root / "docs").mkdir()
    for name in ("architecture.md", "authoring.md", "workflow_authoring_guidelines.md"):
        (root / "docs" / name).write_text(f"# {name}\n", encoding="utf-8")
    (root / "examples/target/prompts").mkdir(parents=True)
    (root / "examples/target/workflow.toml").write_text(
        'name = "target"\ntitle = "Target"\ndescription = "Refinement test target"\n',
        encoding="utf-8",
    )
    (root / "examples/target/prompts/work.md").write_text(
        "Do reliable work.\n", encoding="utf-8"
    )
    (root / "examples/target/workflow.py").write_text(
        """from botpipe import FINISH, SELF, Prompt, Workflow, step


class Target(Workflow):
    name = "target"
    work = step(
        prompt=Prompt.file("prompts/work.md"),
        retry=1,
        routes={"needs_rework": SELF, "done": FINISH},
    )
""",
        encoding="utf-8",
    )
    (root / "tests").mkdir()
    (root / "tests/test_target.py").write_text(
        "def test_target():\n    assert True\n", encoding="utf-8"
    )
    shutil.copytree(
        _OPTIMIZER_LAB,
        root / "labs/workflows/workflow_run_traces_to_optimization_candidates",
    )


def _record_rework(root: Path) -> None:
    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="bad", tag="needs_rework"),
            Outcome(raw_output="ok", tag="done"),
        ]
    )
    result = run_workflow_package(
        "examples/target",
        provider=provider,
        options=RunnerOptions(
            root=root,
            task_id="source",
            message="Exercise target",
            runtime_config=_config(),
        ),
    )
    assert result.terminal == "FINISH"


def _optimizer_inputs(root: Path) -> tuple[Path, str]:
    _record_rework(root)

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

    result = run_workflow_package(
        "labs/workflows/workflow_run_traces_to_optimization_candidates",
        provider=ScriptedLLMProvider(
            producer_turns=[producer], verifier_turns=[verifier]
        ),
        options=RunnerOptions(
            root=root,
            task_id="optimizer",
            message="Diagnose target",
            workflow_params={
                "selected_workflow": "examples/target",
                "task_title": "Review target",
            },
            runtime_config=_config(),
        ),
    )
    assert result.terminal == "FINISH"
    folder = (
        root
        / ".botpipe/tasks/optimizer/wf_workflow_run_traces_to_optimization_candidates"
    )
    receipt = json.loads((folder / "optimization_publication_receipt.json").read_text())
    return (
        folder / "optimization_publication_receipt.json",
        receipt["reviewed_candidate_ids"][0],
    )


def _refinement_provider(
    *, invalid_candidate: bool = False, forge_baseline: bool = False
) -> ScriptedLLMProvider:
    def frame(request):
        request.artifacts.refinement_request_brief.write_text(
            "Refine the target workflow.\n"
        )
        request.artifacts.refinement_acceptance_criteria.write_text(
            "Candidate compiles and tests pass.\n"
        )
        return "framed"

    def frame_verify(_request):
        return Outcome(
            raw_output="framed",
            tag="refinement_request_framed",
            payload={
                "summary": "Boundary and evidence are explicit.",
                "authoritative_artifacts": ["baseline_workflow_manifest"],
                "selected_workflow_name": "target",
                "decision_axes": ["reliability"],
            },
        )

    def design(request):
        request.artifacts.refinement_strategy.write_text(
            "Add an explicit completion marker.\n"
        )
        request.artifacts.workflow_change_plan.write_text(
            "Update the workflow source.\n"
        )
        request.artifacts.regression_guardrails.write_text(
            "Keep the workflow importable.\n"
        )
        return "planned"

    def design_verify(_request):
        return Outcome(
            raw_output="planned",
            tag="refinement_plan_designed",
            payload={
                "summary": "A bounded source change is planned.",
                "selected_workflow_name": "target",
                "planned_change_paths": ["examples/target/workflow.py"],
                "verification_focus": ["compile", "tests"],
            },
        )

    def implement(request):
        baseline = request.artifacts.baseline_workflow_surface.path
        candidate = request.artifacts.candidate_workflow_surface.path
        shutil.copytree(baseline, candidate, dirs_exist_ok=True)
        manifest = json.loads(request.artifacts.baseline_workflow_manifest.read_text())
        workflow_path = candidate / next(
            path for path in manifest["relative_paths"] if path.endswith("workflow.py")
        )
        workflow_path.write_text(
            (
                "invalid python !!!\n"
                if invalid_candidate
                else workflow_path.read_text() + "\n# refined\n"
            ),
            encoding="utf-8",
        )
        request.artifacts.candidate_workflow_manifest.write_text("{}\n")
        request.artifacts.refinement_build_report.write_text("Candidate built.\n")
        request.artifacts.candidate_diff_summary.write_text(
            "Added a completion marker.\n"
        )
        return "implemented"

    def implement_verify(request):
        manifest = json.loads(request.artifacts.baseline_workflow_manifest.read_text())
        changed = next(
            path for path in manifest["relative_paths"] if path.endswith("workflow.py")
        )
        return Outcome(
            raw_output="implemented",
            tag="workflow_refinement_applied",
            payload={
                "summary": "Candidate source was refined.",
                "selected_workflow_name": "target",
                "candidate_file_count": manifest["file_count"],
                "changed_relative_paths": [changed],
            },
        )

    def evaluate(request):
        if forge_baseline:
            from botpipe_optimizer.candidate_surfaces import derive_surface_manifest

            baseline = json.loads(
                request.artifacts.baseline_workflow_manifest.read_text()
            )
            root = Path(baseline["surface_root"])
            changed = root / next(
                path
                for path in baseline["relative_paths"]
                if path.endswith("workflow.py")
            )
            changed.write_text(changed.read_text() + "\n# forged baseline\n")
            replacement = derive_surface_manifest(
                root,
                expected_root=root,
                boundary=baseline["boundary"],
                surface_kind="baseline",
                authoritative_sources={
                    entry["relative_path"]: Path(entry["source_path"])
                    for entry in baseline["files"]
                },
            )
            request.artifacts.baseline_workflow_manifest.write_text(
                json.dumps({**baseline, **replacement})
            )
        request.artifacts.refinement_verification_report.write_text(
            "Compile and target test passed.\n"
        )
        request.artifacts.evaluation_delta_report.write_text(
            "Candidate is ready for paired evaluation.\n"
        )
        request.artifacts.promotion_record.write_text("No automatic promotion.\n")
        request.artifacts.rollback_plan.write_text("Retain the baseline surface.\n")
        return "evaluated"

    def evaluate_verify(request):
        manifest = json.loads(request.artifacts.candidate_workflow_manifest.read_text())
        return Outcome(
            raw_output="evaluated",
            tag="workflow_refinement_evaluated",
            payload={
                "summary": "Candidate artifacts are complete.",
                "selected_workflow_name": "target",
                "candidate_file_count": manifest["file_count"],
                "validated_overlay_command": f"{sys.executable} -c pass",
                "authoritative_artifacts": [
                    "refinement_verification_report",
                    "evaluation_delta_report",
                    "promotion_record",
                    "rollback_plan",
                ],
                "next_action": "review_candidate",
                "ready_for_publication": True,
            },
        )

    return ScriptedLLMProvider(
        producer_turns=[frame, design, implement, evaluate],
        verifier_turns=[frame_verify, design_verify, implement_verify, evaluate_verify],
    )


def _evaluation_spec(root: Path) -> Path:
    evaluator = root / "evaluation/evaluator.py"
    evaluator.parent.mkdir()
    evaluator.write_text(
        """import json, os
from pathlib import Path

request = json.loads(Path(os.environ["BOTPIPE_EVAL_REQUEST"]).read_text())
refined = "# refined" in (Path(request["workspace_path"]) / "examples/target/workflow.py").read_text()
cases = []
for case_id in request["case_ids"]:
    for repetition in range(1, request["repetitions"] + 1):
        cases.append({"case_id": case_id, "repetition": repetition, "outcome": "ok", "metrics": {"quality": 2.0 if refined else 1.0}, "evidence_paths": [], "usage_availability": "known_total", "elapsed_seconds": 0.01})
Path(os.environ["BOTPIPE_EVAL_RESULT"]).write_text(json.dumps({"schema": "botpipe.optimizer.eval_result/v1", "execution_id": request["execution_id"], "surface_id": request["surface_id"], "spec_id": request["spec_id"], "cases": cases, "environment_id": request["environment_id"], "provider_budget": None}))
""",
        encoding="utf-8",
    )
    cases = root / "evaluation/cases.json"
    cases.write_text(
        json.dumps({"cases": [{"case_id": "development-case"}]}), encoding="utf-8"
    )
    digest = lambda path: sha256(path.read_bytes()).hexdigest()
    spec = root / "evaluation/spec.json"
    spec.write_text(
        json.dumps(
            {
                "schema": "botpipe.optimizer.evaluation_spec/v1",
                "evaluator_argv": [sys.executable, "{evaluator_path}"],
                "evaluator_path": str(evaluator),
                "evaluator_content_id": digest(evaluator),
                "case_input_path": str(cases),
                "case_input_content_id": digest(cases),
                "case_ids": ["development-case"],
                "repetitions": 1,
                "effective_settings": {"mode": "fixed"},
                "metrics": [
                    {
                        "name": "quality",
                        "unit": "score",
                        "direction": "higher_is_better",
                        "aggregation": "mean",
                        "minimum_improvement": 0.5,
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
            }
        ),
        encoding="utf-8",
    )
    return spec


@pytest.mark.parametrize(
    "input_kind,evaluate", [("legacy", False), ("optimizer", True)]
)
def test_refinement_publication_supports_both_primary_inputs_and_optional_paired_evaluation(
    tmp_path: Path, input_kind: str, evaluate: bool
) -> None:
    _write_project(tmp_path)
    params = {
        "selected_workflow": "examples/target",
        "task_title": "Refine target",
    }
    if input_kind == "legacy":
        summary = tmp_path / "evaluation-summary.json"
        summary.write_text(
            json.dumps(
                {"selected_workflow_name": "target", "summary": "Observed rework."}
            )
        )
        findings = tmp_path / "evaluation-findings.md"
        findings.write_text("# Finding\nThe target retried once.\n")
        params.update(
            evaluation_summary_path=str(summary), evaluation_findings_path=str(findings)
        )
    else:
        receipt_path, candidate_id = _optimizer_inputs(tmp_path)
        params.update(
            optimization_receipt_path=str(receipt_path), candidate_id=candidate_id
        )
    if evaluate:
        params["evaluation_spec_path"] = str(_evaluation_spec(tmp_path))

    task_id = f"refinement-{input_kind}"
    provider = _refinement_provider()
    result = run_workflow_package(
        str(_REFINEMENT_LAB),
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id=task_id,
            message="Refine the selected workflow",
            workflow_params=params,
            runtime_config=_config(),
        ),
    )

    assert result.terminal == "FINISH"
    assert len(provider.calls) == 8
    folder = (
        tmp_path
        / ".botpipe/tasks"
        / task_id
        / "wf_workflow_and_eval_to_refined_workflow_package"
    )
    receipt = json.loads((folder / "workflow_refinement_receipt.json").read_text())
    paired = json.loads((folder / "paired_evaluation_result.json").read_text())
    assert receipt["published"] is True
    assert receipt["validation_result"]["success"] is True
    assert (
        receipt["validation_result"]["baseline_surface_id"]
        == json.loads((folder / "baseline_workflow_manifest.json").read_text())[
            "surface_id"
        ]
    )
    assert (
        receipt["validation_result"]["candidate_surface_id"]
        == json.loads((folder / "candidate_workflow_manifest.json").read_text())[
            "surface_id"
        ]
    )
    if evaluate:
        assert paired["comparison"]["state"] == "improved"
        assert [
            paired["arms"][name]["execution_state"]
            for name in ("baseline", "candidate")
        ] == [
            "complete",
            "complete",
        ]
        assert (
            receipt["validation_result"]["evaluation_comparison"]
            == paired["comparison"]
        )
    else:
        assert paired["evaluation"] == "not_evaluated"
        assert paired["comparison"]["state"] == "not_evaluated"
        assert receipt["validation_result"].get("evaluation_comparison") is None


@pytest.mark.parametrize(
    "fault", ["invalid_candidate", "mutation_after_validation", "forged_baseline"]
)
def test_refinement_failure_cannot_retain_an_accepted_receipt(
    tmp_path: Path, fault: str
) -> None:
    _write_project(tmp_path)
    source = tmp_path / "examples/target/workflow.py"
    original = source.read_bytes()
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({"selected_workflow_name": "target"}))
    findings = tmp_path / "findings.md"
    findings.write_text("Observed rework")
    folder = (
        tmp_path
        / ".botpipe/tasks/failing/wf_workflow_and_eval_to_refined_workflow_package"
    )
    folder.mkdir(parents=True)
    receipt_path = folder / "workflow_refinement_receipt.json"
    receipt_path.write_text(
        json.dumps({"published": True, "status": "accepted", "run_id": "previous"})
    )
    params = {
        "selected_workflow": "examples/target",
        "task_title": "Fail closed",
        "evaluation_summary_path": str(summary),
        "evaluation_findings_path": str(findings),
        "target_test_argv": [sys.executable, "-c", "raise SystemExit(0)"],
    }
    if fault == "mutation_after_validation":
        spec_path = _evaluation_spec(tmp_path)
        spec = json.loads(spec_path.read_text())
        evaluator = Path(spec["evaluator_path"])
        candidate_path = (
            folder / "candidate_workflow_surface/examples/target/workflow.py"
        )
        evaluator.write_text(
            evaluator.read_text()
            + f"\nPath({str(candidate_path)!r}).write_text('changed after validation\\n')\n"
        )
        spec["evaluator_content_id"] = sha256(evaluator.read_bytes()).hexdigest()
        spec_path.write_text(json.dumps(spec))
        params["evaluation_spec_path"] = str(spec_path)
    with pytest.raises(
        Exception,
        match="candidate validation failed|surface_sha256|surface_id|surface changed",
    ):
        run_workflow_package(
            str(_REFINEMENT_LAB),
            provider=_refinement_provider(
                invalid_candidate=fault == "invalid_candidate",
                forge_baseline=fault == "forged_baseline",
            ),
            options=RunnerOptions(
                root=tmp_path,
                task_id="failing",
                message="Validate failure handling",
                workflow_params=params,
                runtime_config=_config(),
            ),
        )
    receipt = json.loads(receipt_path.read_text())
    assert receipt["published"] is False and receipt["status"] == "incomplete"
    assert receipt["run_id"] != "previous"
    assert source.read_bytes() == original
