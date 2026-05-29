from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from botpipe import Outcome
from botpipe.core.compiler import compile_workflow
from botpipe.core.providers.fake import ScriptedLLMProvider
from botpipe.runtime.config import GitTrackingRuntimeConfig, RuntimeConfig
from botpipe.runtime.runner import RunnerOptions, run_workflow_package
from botpipe.workflows.code_to_workflow import CodeToWorkflow, Params
from botpipe.workflows.code_to_workflow.specs import (
    capture_source_manifest,
    collect_trace_corpus,
    derive_generated_workflow_name,
    validate_coverage_map,
)


def _runner_options(root: Path, **kwargs: object) -> RunnerOptions:
    kwargs.setdefault(
        "runtime_config",
        RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
    )
    return RunnerOptions(root=root, **kwargs)


def _write_repo_docs(root: Path) -> None:
    docs = root / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "architecture.md").write_text("# Architecture\n", encoding="utf-8")
    (docs / "authoring.md").write_text("# Authoring\n", encoding="utf-8")
    (docs / "workflow_authoring_guidelines.md").write_text("# Guidelines\n", encoding="utf-8")


def test_params_expose_only_optional_generated_workflow_name() -> None:
    assert Params().generated_workflow_name is None
    assert Params(generated_workflow_name="converted_app").generated_workflow_name == "converted_app"
    assert Params(generated_workflow_name="  converted_app  ").generated_workflow_name == "converted_app"
    assert Params(generated_workflow_name="   ").generated_workflow_name is None

    with pytest.raises(ValidationError, match="generated_workflow_name"):
        Params(generated_workflow_name="converted-app")


def test_derive_generated_workflow_name_sanitizes_repo_name_when_param_omitted(tmp_path: Path) -> None:
    root = tmp_path / "123 Example Repo"
    root.mkdir()

    assert derive_generated_workflow_name(root, None) == "workflow_123_example_repo"
    assert derive_generated_workflow_name(root, "explicit_name") == "explicit_name"


def test_source_manifest_excludes_runtime_generated_and_cache_paths(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / ".botpipe" / "workflows" / "converted" / "flow.py").parent.mkdir(parents=True)
    (tmp_path / ".botpipe" / "workflows" / "converted" / "flow.py").write_text("# generated\n", encoding="utf-8")
    (tmp_path / ".autoloop" / "tasks" / "task-1" / "runs" / "run-1").mkdir(parents=True)
    (tmp_path / ".autoloop" / "tasks" / "task-1" / "runs" / "run-1" / "events.jsonl").write_text(
        "{}\n",
        encoding="utf-8",
    )
    (tmp_path / ".venv" / "ignored.py").parent.mkdir()
    (tmp_path / ".venv" / "ignored.py").write_text("# ignored\n", encoding="utf-8")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "ignored.py").write_text("# ignored\n", encoding="utf-8")

    manifest = capture_source_manifest(tmp_path, generated_workflow_name="converted")

    paths = {entry["path"] for entry in manifest["files"]}
    assert paths == {"app.py"}
    assert manifest["file_count"] == 1
    assert manifest["skipped"]["excluded_path"] >= 2


def test_trace_corpus_summarizes_botpipe_legacy_and_nested_codex_traces(tmp_path: Path) -> None:
    run_dir = tmp_path / ".botpipe" / "tasks" / "task-1" / "wf_demo" / "runs" / "run-1"
    raw_dir = run_dir / "raw" / "provider" / "codex" / "sessions" / "2026" / "05" / "25"
    raw_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps({"status": "failed", "terminal": "FAIL"}),
        encoding="utf-8",
    )
    (run_dir / "trace.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"event": "step_started", "step": "build"}),
                json.dumps(
                    {
                        "event": "step_finished",
                        "step": "build",
                        "outcome": {"tag": "failed"},
                        "error": "validation failed",
                        "raw_output_refs": ["raw/provider/output.txt"],
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (raw_dir / "rollout-test.jsonl").write_text(
        json.dumps({"type": "message", "text": "sample"}) + "\n",
        encoding="utf-8",
    )
    legacy_dir = tmp_path / ".autoloop" / "tasks" / "legacy-task" / "runs" / "legacy-run"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "events.jsonl").write_text(
        json.dumps({"event": "phase_failed", "error": "legacy failed"}) + "\n",
        encoding="utf-8",
    )

    corpus = collect_trace_corpus(tmp_path)

    assert corpus["botpipe_runs"][0]["workflow_name"] == "demo"
    assert corpus["botpipe_runs"][0]["event_counts"] == {"step_finished": 1, "step_started": 1}
    assert corpus["botpipe_runs"][0]["errors"] == ["validation failed"]
    assert corpus["legacy_autoloop_runs"][0]["event_counts"] == {"phase_failed": 1}
    assert corpus["codex_rollout_refs"][0]["path"].endswith("rollout-test.jsonl")


def test_code_to_workflow_compiles_with_expected_routes() -> None:
    compiled = compile_workflow(CodeToWorkflow)

    assert compiled.workflow_name == "code_to_workflow"
    assert compiled.parameters_cls is Params
    assert compiled.entry_step_name == "bootstrap_capture"
    assert set(compiled.routes["distill_behavior"]) >= {"behavior_distilled", "needs_rework"}
    assert set(compiled.routes["design_botpipe_recreation"]) >= {"design_accepted", "needs_rework", "needs_replan"}
    assert set(compiled.routes["build_and_validate"]) >= {"build_validated", "needs_rework", "needs_replan"}

    assert "capture_session" not in compiled.sessions
    assert "build_session" not in compiled.sessions

    distill_step = compiled.steps["distill_behavior"]
    assert {artifact.name for artifact in distill_step.producer.io.reads} == {"behavior_review"}
    assert {"request", "invocation_contract", "source_manifest", "trace_corpus"} <= {
        artifact.name for artifact in distill_step.verifier.io.requires
    }

    design_step = compiled.steps["design_botpipe_recreation"]
    assert design_step.producer.session_name == "authoring_session"
    assert design_step.verifier.session_name == "design_verifier_session"
    assert "botpipe_workflow_authoring_skill" in {artifact.name for artifact in design_step.producer.io.reads}
    assert "botpipe_workflow_authoring_skill" in {artifact.name for artifact in design_step.verifier.io.reads}
    assert {
        "request",
        "invocation_contract",
        "source_manifest",
        "behavior_inventory",
        "behavior_inventory_report",
        "trace_pattern_notes",
        "behavior_review",
    } <= {artifact.name for artifact in design_step.verifier.io.requires}

    build_step = compiled.steps["build_and_validate"]
    assert build_step.producer.session_name == "authoring_session"
    assert build_step.verifier.session_name == "build_verifier_session"
    required_source_context = {
        "source_manifest",
        "trace_corpus",
        "behavior_inventory",
        "behavior_inventory_report",
        "trace_pattern_notes",
        "behavior_review",
        "design_review",
    }
    assert required_source_context <= {artifact.name for artifact in build_step.producer.io.requires}
    assert required_source_context <= {artifact.name for artifact in build_step.verifier.io.requires}
    assert "botpipe_workflow_authoring_skill" in {artifact.name for artifact in build_step.producer.io.reads}
    assert "botpipe_workflow_authoring_skill" in {artifact.name for artifact in build_step.verifier.io.reads}


def test_code_to_workflow_packages_botpipe_authoring_skill_copy() -> None:
    skill_path = Path("botpipe/workflows/code_to_workflow/skills/botpipe-workflow-autoring.md")
    text = skill_path.read_text(encoding="utf-8")

    assert "name: botpipe-workflow-authoring" in text
    assert "## Session design" in text


def test_validate_coverage_map_blocks_unhandled_required_behavior() -> None:
    behavior_inventory = {
        "behaviors": [
            {"id": "behavior-1", "required": True},
            {"id": "behavior-2", "required": True},
        ]
    }
    coverage_map = {"coverage": [{"behavior_id": "behavior-1", "status": "implemented"}]}

    with pytest.raises(ValueError, match="behavior-2"):
        validate_coverage_map(behavior_inventory=behavior_inventory, coverage_map=coverage_map)


def test_code_to_workflow_scripted_happy_path_publishes_generated_workflow(tmp_path: Path) -> None:
    _write_repo_docs(tmp_path)
    (tmp_path / "app.py").write_text("def greet(name):\n    return f'hello {name}'\n", encoding="utf-8")

    def distill_producer(request):
        request.artifacts.behavior_inventory.write_text(
            json.dumps(
                {
                    "schema": "botpipe.code_to_workflow.behavior_inventory/v1",
                    "summary": "Greeting library",
                    "behaviors": [
                        {
                            "id": "behavior-1",
                            "summary": "Return a greeting for a supplied name.",
                            "required": True,
                            "evidence": ["app.py"],
                            "inputs": ["name"],
                            "outputs": ["greeting"],
                            "error_modes": [],
                        }
                    ],
                },
                indent=2,
            )
            + "\n"
        )
        request.artifacts.behavior_inventory_report.write_text("# Behavior Inventory\n")
        request.artifacts.trace_pattern_notes.write_text("# Trace Notes\nNo traces.\n")
        return "distilled"

    def distill_verifier(request):
        request.artifacts.behavior_review.write_text("ACCEPTED\n")
        return Outcome(
            raw_output="accepted",
            tag="behavior_distilled",
            payload={
                "summary": "covered",
                "behavior_count": 1,
                "evidence_artifacts": ["behavior_inventory.json"],
                "uncovered_areas": [],
            },
        )

    def design_producer(request):
        request.artifacts.workflow_design.write_text("# Workflow Design\n")
        request.artifacts.step_contracts.write_text(json.dumps({"steps": ["greet"]}) + "\n")
        request.artifacts.prompt_contract_matrix.write_text("# Prompt Matrix\n")
        request.artifacts.equivalence_plan.write_text("# Equivalence Plan\n")
        request.artifacts.coverage_map.write_text(
            json.dumps(
                {
                    "schema": "botpipe.code_to_workflow.coverage_map/v1",
                    "coverage": [
                        {
                            "behavior_id": "behavior-1",
                            "status": "implemented",
                            "target": "generated greet step",
                            "evidence": ["workflow_design.md"],
                        }
                    ],
                },
                indent=2,
            )
            + "\n"
        )
        return "designed"

    def design_verifier(request):
        request.artifacts.design_review.write_text("ACCEPTED\n")
        return Outcome(
            raw_output="accepted",
            tag="design_accepted",
            payload={
                "summary": "design covers behavior",
                "authoritative_artifacts": ["workflow_design.md", "coverage_map.json"],
                "coverage_count": 1,
                "uncovered_required_behaviors": [],
            },
        )

    def build_producer(request):
        request.artifacts.generated_workflow_root.path.mkdir(parents=True, exist_ok=True)
        request.artifacts.generated_flow.write_text(
            "\n".join(
                [
                    "from __future__ import annotations",
                    "from botpipe import FINISH, Workflow, python_step",
                    "",
                    "class ConvertedApp(Workflow):",
                    '    name = "converted_app"',
                    '    @python_step(name="greet", routes={"done": FINISH})',
                    "    def greet(ctx):",
                    '        return "done"',
                ]
            )
            + "\n"
        )
        request.artifacts.generated_manifest.write_text(
            'name = "converted_app"\ntitle = "Converted App"\ndescription = "Generated test workflow."\n',
        )
        request.artifacts.generated_layout.write_text(
            json.dumps(
                {
                    "generated_workflow_name": request.context.state.generated_workflow_name,
                    "files": ["flow.py", "workflow.toml"],
                },
                indent=2,
            )
            + "\n"
        )
        request.artifacts.validation_report.write_text("# Validation\nCompiled by scripted test.\n")
        return "built"

    def build_verifier(request):
        request.artifacts.build_review.write_text("ACCEPTED\n")
        return Outcome(
            raw_output="accepted",
            tag="build_validated",
            payload={
                "summary": "generated workflow exists",
                "changed_paths": [".botpipe/workflows/converted_app/flow.py"],
                "evidence_artifacts": ["validation_report.md"],
                "validation_commands": ["scripted compile check"],
                "coverage_status": "complete",
            },
        )

    provider = ScriptedLLMProvider(
        producer_turns=[distill_producer, design_producer, build_producer],
        verifier_turns=[distill_verifier, design_verifier, build_verifier],
    )

    result = run_workflow_package(
        "code_to_workflow",
        provider=provider,
        options=_runner_options(
            tmp_path,
            task_id="code-to-workflow-task",
            message="Convert this greeting library into a workflow.",
            workflow_params={"generated_workflow_name": "converted_app"},
        ),
    )

    workflow_dir = tmp_path / ".botpipe" / "tasks" / "code-to-workflow-task" / "wf_code_to_workflow"
    run_dir = next((workflow_dir / "runs").iterdir())
    receipt = json.loads((workflow_dir / "publication_receipt.json").read_text(encoding="utf-8"))
    source_manifest = json.loads((workflow_dir / "source_manifest.json").read_text(encoding="utf-8"))

    assert result.terminal == "FINISH"
    assert (tmp_path / ".botpipe" / "workflows" / "converted_app" / "flow.py").exists()
    assert receipt["published"] is True
    assert receipt["generated_workflow_name"] == "converted_app"
    assert source_manifest["generated_output"] == ".botpipe/workflows/converted_app"
    assert {call.step_name for call in provider.calls} >= {
        "distill_behavior",
        "design_botpipe_recreation",
        "build_and_validate",
    }
    assert (run_dir / "run.json").exists()
