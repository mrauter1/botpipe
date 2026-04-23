from __future__ import annotations

import importlib
import json
import shutil
import sys
from pathlib import Path

import pytest

from autoloop_v3.core.compiler import compile_workflow
from autoloop_v3.core.providers.fake import ScriptedLLMProvider
from autoloop_v3.runtime.loader import (
    WorkflowParameterError,
    coerce_workflow_parameter_mapping,
    discover_workflow_packages,
    resolve_workflow_reference,
)
from autoloop_v3.runtime.runner import RunnerOptions, run_workflow_package
from workflow.primitives import Outcome


REPO_ROOT = Path(__file__).resolve().parents[2]


def _clear_workflow_modules() -> None:
    for name in list(sys.modules):
        if name == "workflows" or name.startswith("workflows."):
            sys.modules.pop(name, None)


@pytest.fixture(autouse=True)
def _isolate_workflow_modules():
    _clear_workflow_modules()
    yield
    _clear_workflow_modules()


def test_repo_workflows_namespace_discovers_workflow_builder_package() -> None:
    discovered = {package.workflow_name: package for package in discover_workflow_packages(REPO_ROOT)}

    assert "workflow_idea_to_workflow_package" in discovered
    package = discovered["workflow_idea_to_workflow_package"]
    assert package.package_name == "workflow_idea_to_workflow_package"
    assert "workflow-builder" in package.aliases
    assert package.manifest_path == (
        REPO_ROOT / "workflows" / "workflow_idea_to_workflow_package" / "workflow.toml"
    )


def test_workflow_builder_package_compiles_with_explicit_control_contracts(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.workflow_idea_to_workflow_package")
    resolved = resolve_workflow_reference(REPO_ROOT, workflow_pkg.WorkflowIdeaToWorkflowPackage)
    compiled = compile_workflow(resolved.workflow_cls)

    assert resolved.parameters_cls is not None
    assert compiled.entry_step_name == "bootstrap"
    assert tuple(compiled.steps) == (
        "bootstrap",
        "frame_candidate",
        "design_package",
        "build_package",
        "evaluate_package",
        "publish_package",
    )

    frame_step = compiled.steps["frame_candidate"]
    assert frame_step.available_routes == (
        "candidate_selected",
        "needs_rework",
        "needs_replan",
        "question",
        "blocked",
        "failed",
    )
    assert frame_step.route_contracts["candidate_selected"]["required_artifacts"] == [
        "candidate_comparison",
        "selected_workflow_brief",
    ]
    assert frame_step.expected_output_schema is not None

    build_step = compiled.steps["build_package"]
    assert "package_built" in build_step.available_routes
    assert "needs_replan" in build_step.route_contracts
    assert build_step.expected_output_schema is not None

    evaluate_step = compiled.steps["evaluate_package"]
    assert evaluate_step.route_contracts["evaluation_passed"]["required_artifacts"] == [
        "verification_report",
        "promotion_record",
        "rollback_plan",
    ]


def test_workflow_builder_package_docs_capture_decision_records() -> None:
    text = (REPO_ROOT / "docs" / "workflows" / "workflow_idea_to_workflow_package.md").read_text(
        encoding="utf-8"
    )

    for required in (
        "Candidate additions considered",
        "Framework improvement candidates considered",
        "Meaningful design decisions",
        "Implementation candidates considered",
        "Route grammar",
        "Runtime-injected control contract",
        "tests/runtime/test_workflow_builder_package.py",
    ):
        assert required in text


def test_workflow_builder_package_rejects_invalid_package_name(tmp_path: Path) -> None:
    _install_repo_workflow_builder_package(tmp_path)
    parameters_cls = resolve_workflow_reference(tmp_path, "workflow_idea_to_workflow_package").parameters_cls

    with pytest.raises(WorkflowParameterError, match="package_name"):
        coerce_workflow_parameter_mapping(
            parameters_cls,
            {
                "package_name": "release-candidate-to-go-no-go",
                "workflow_kind": "end_to_end",
            },
        )


def test_workflow_builder_package_runs_and_generates_a_compilable_package(tmp_path: Path) -> None:
    _install_repo_workflow_builder_package(tmp_path)
    generated_name = "release_candidate_to_go_no_go"

    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.candidate_comparison.write_text(
                    "\n".join(
                        (
                            "# Candidate Comparison",
                            "",
                            "- `workflow_idea_to_workflow_package`: chosen because the repo lacks a credible builder.",
                            "- `release_candidate_to_go_no_go`: deferred until the builder exists.",
                            "- `incident_to_hardening_program`: deferred until the builder exists.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.selected_workflow_brief.write_text(
                    "\n".join(
                        (
                            "# Selected Workflow Brief",
                            "",
                            "Chosen addition: `workflow_idea_to_workflow_package`.",
                            "Classification: end-to-end workflow package.",
                            "Terminal outcome: a discoverable workflow package plus evidence artifacts.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "framed candidate\n",
            )[2],
            lambda request: (
                request.artifacts.workflow_package_spec.write_text(
                    "\n".join(
                        (
                            "# Workflow Package Spec",
                            "",
                            "Objective: build a release-readiness workflow package.",
                            "Control flow: bootstrap -> review -> verify -> publish.",
                            "Runtime control contract: only expected_output_schema, available_routes, and route_contracts.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.step_contracts.write_text(
                    '{\n  "steps": ["bootstrap", "review_release", "publish"]\n}\n'
                ),
                request.artifacts.prompt_contract_matrix.write_text(
                    "\n".join(
                        (
                            "# Prompt Contract Matrix",
                            "",
                            "- `prompts/review_release_producer.md`",
                            "- `prompts/review_release_verifier.md`",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.verification_plan.write_text(
                    "\n".join(
                        (
                            "# Verification Plan",
                            "",
                            "- compile workflow package",
                            "- run package-specific tests",
                            "",
                        )
                    )
                    + "\n"
                ),
                "designed package\n",
            )[4],
            lambda request: _write_generated_package(request, generated_name),
            lambda request: (
                request.artifacts.verification_report.write_text(
                    "\n".join(
                        (
                            "# Verification Report",
                            "",
                            "- Verified workflow discovery and compilation.",
                            "- Verified package-specific test file exists.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.promotion_record.write_text(
                    "\n".join(
                        (
                            "# Promotion Record",
                            "",
                            f"Promote `{generated_name}` because the package structure, prompts, docs, and tests exist.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.rollback_plan.write_text(
                    "\n".join(
                        (
                            "# Rollback Plan",
                            "",
                            f"- Remove `workflows/{generated_name}`.",
                            f"- Remove `docs/workflows/{generated_name}.md`.",
                            f"- Remove `tests/runtime/test_{generated_name}.py`.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "evaluated package\n",
            )[3],
        ],
        verifier_turns=[
            Outcome(
                raw_output="candidate selected\n",
                tag="candidate_selected",
                payload={
                    "summary": "Selected the workflow-builder after comparing three candidates.",
                    "evidence_artifacts": ["candidate_comparison", "selected_workflow_brief"],
                    "selected_candidate": "workflow_idea_to_workflow_package",
                    "selected_kind": "end_to_end",
                },
            ),
            Outcome(
                raw_output="design accepted\n",
                tag="design_accepted",
                payload={
                    "summary": "The design artifacts are explicit and implementation-ready.",
                    "authoritative_artifacts": [
                        "workflow_package_spec",
                        "step_contracts",
                        "prompt_contract_matrix",
                        "verification_plan",
                    ],
                    "prompt_files": [
                        "prompts/review_release_producer.md",
                        "prompts/review_release_verifier.md",
                    ],
                    "next_action": "build_package",
                },
            ),
            Outcome(
                raw_output="package built\n",
                tag="package_built",
                payload={
                    "summary": "Generated the target package, docs, tests, and build report.",
                    "changed_paths": [
                        f"workflows/{generated_name}/workflow.py",
                        f"workflows/{generated_name}/workflow.toml",
                        f"docs/workflows/{generated_name}.md",
                        f"tests/runtime/test_{generated_name}.py",
                    ],
                    "evidence_artifacts": [
                        "generated_workflow",
                        "generated_manifest",
                        "generated_doc",
                        "generated_test",
                        "build_report",
                    ],
                },
            ),
            Outcome(
                raw_output="evaluation passed\n",
                tag="evaluation_passed",
                payload={
                    "summary": "Evaluation artifacts justify publication.",
                    "evidence_artifacts": [
                        "verification_report",
                        "promotion_record",
                        "rollback_plan",
                    ],
                    "validation_commands": [
                        f"pytest -q tests/runtime/test_{generated_name}.py",
                    ],
                    "promotion_decision": "promote",
                },
            ),
        ],
    )

    result = run_workflow_package(
        "workflow_idea_to_workflow_package",
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id="workflow-builder-task",
            message="We need a workflow for release readiness reviews.",
            workflow_params={
                "package_name": generated_name,
                "package_title": "Release Candidate To Go No Go",
                "workflow_kind": "end_to_end",
                "aliases": ["release-go-no-go"],
                "target_test_command": "pytest -q",
            },
        ),
    )

    workflow_dir = tmp_path / ".autoloop" / "tasks" / "workflow-builder-task" / "wf_workflow_idea_to_workflow_package"
    run_dir = next((workflow_dir / "runs").iterdir())
    invocation_contract = json.loads((workflow_dir / "invocation_contract.json").read_text(encoding="utf-8"))
    publish_receipt = json.loads((workflow_dir / "publish_receipt.json").read_text(encoding="utf-8"))

    assert result.terminal == "SUCCESS"
    assert (workflow_dir / "invocation_contract.json").exists()
    assert (workflow_dir / "candidate_comparison.md").exists()
    assert (workflow_dir / "workflow_package_spec.md").exists()
    assert (workflow_dir / "build_report.md").exists()
    assert (workflow_dir / "verification_report.md").exists()
    assert (workflow_dir / "promotion_record.md").exists()
    assert (workflow_dir / "rollback_plan.md").exists()
    assert (workflow_dir / "publish_receipt.json").exists()
    assert invocation_contract == {
        "aliases": ["release-go-no-go"],
        "message": "We need a workflow for release readiness reviews.\n",
        "package_name": generated_name,
        "package_title": "Release Candidate To Go No Go",
        "request_file": str(run_dir / "request.md"),
        "run_id": run_dir.name,
        "target_test_command": "pytest -q",
        "task_id": "workflow-builder-task",
        "workflow_kind": "end_to_end",
        "workflow_name": "workflow_idea_to_workflow_package",
    }
    assert publish_receipt == {
        "package_name": generated_name,
        "promotion_record": str(workflow_dir / "promotion_record.md"),
        "published": True,
        "rollback_plan": str(workflow_dir / "rollback_plan.md"),
        "selected_candidate": "workflow_idea_to_workflow_package",
        "workflow_name": "workflow_idea_to_workflow_package",
    }

    generated_pkg_dir = tmp_path / "workflows" / generated_name
    assert generated_pkg_dir.is_dir()
    assert (generated_pkg_dir / "workflow.py").exists()
    assert (generated_pkg_dir / "prompts" / "review_release_producer.md").exists()
    assert (tmp_path / "docs" / "workflows" / f"{generated_name}.md").exists()
    assert (tmp_path / "tests" / "runtime" / f"test_{generated_name}.py").exists()

    compiled_generated = compile_workflow(resolve_workflow_reference(tmp_path, generated_name).workflow_cls)
    assert compiled_generated.workflow_name == generated_name

    assert [call.step_name for call in provider.calls] == [
        "frame_candidate",
        "frame_candidate",
        "design_package",
        "design_package",
        "build_package",
        "build_package",
        "evaluate_package",
        "evaluate_package",
    ]
    assert provider.calls[1].available_routes == (
        "candidate_selected",
        "needs_rework",
        "needs_replan",
        "question",
        "blocked",
        "failed",
    )
    assert provider.calls[5].route_contracts["package_built"]["required_artifacts"] == [
        "generated_package_root",
        "generated_init",
        "generated_workflow",
        "generated_manifest",
        "generated_prompts_dir",
        "generated_assets_dir",
        "build_report",
    ]
    assert (run_dir / "run.json").exists()


def _install_repo_workflow_builder_package(root: Path) -> None:
    workflows_root = root / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    (workflows_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    _clear_workflow_modules()
    importlib.invalidate_caches()

    for package_name in ("workflow_idea_to_workflow_package", "autoloop_v1"):
        shutil.copytree(
            REPO_ROOT / "workflows" / package_name,
            workflows_root / package_name,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )

    shutil.copytree(
        REPO_ROOT / "docs",
        root / "docs",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    (root / "Workflow_Instructions.md").write_text(
        (REPO_ROOT / "Workflow_Instructions.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (root / "core").mkdir(parents=True, exist_ok=True)
    for filename in ("steps.py", "validation.py", "compiler.py", "engine.py"):
        shutil.copy2(REPO_ROOT / "core" / filename, root / "core" / filename)
    (root / "runtime").mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO_ROOT / "runtime" / "cli.py", root / "runtime" / "cli.py")


def _write_generated_package(request, package_name: str) -> str:
    class_name = _workflow_class_name(package_name)
    request.artifacts.generated_package_root.path.mkdir(parents=True, exist_ok=True)
    request.artifacts.generated_prompts_dir.path.mkdir(parents=True, exist_ok=True)
    request.artifacts.generated_assets_dir.path.mkdir(parents=True, exist_ok=True)
    request.artifacts.generated_init.write_text(
        f'from .params import Parameters\nfrom .workflow import {class_name}\n\n__all__ = ["Parameters", "{class_name}"]\n'
    )
    request.artifacts.generated_params.write_text(
        "\n".join(
            (
                "from pydantic import BaseModel",
                "",
                "",
                "class Parameters(BaseModel):",
                '    mode: str = "strict"',
            )
        )
        + "\n"
    )
    request.artifacts.generated_contracts.write_text(
        "\n".join(
            (
                "from pydantic import BaseModel",
                "",
                "",
                "class ReviewPayload(BaseModel):",
                "    summary: str",
            )
        )
        + "\n"
    )
    request.artifacts.generated_workflow.write_text(
        "\n".join(
            (
                "from __future__ import annotations",
                "",
                "from pydantic import BaseModel",
                "",
                "from workflow import GLOBAL, SUCCESS, SystemStep, Workflow",
                "from workflow.primitives import Event",
                "",
                "",
                f"class {class_name}(Workflow):",
                f'    name = "{package_name}"',
                "",
                "    class State(BaseModel):",
                "        ready: bool = False",
                "",
                '    bootstrap = SystemStep(name="bootstrap")',
                "    entry = bootstrap",
                "    transitions = {",
                "        GLOBAL: {},",
                '        bootstrap: {"ready": SUCCESS},',
                "    }",
                "",
                "    @staticmethod",
                "    def on_bootstrap(state: State, ctx):",
                '        return state.model_copy(update={"ready": True}), Event("ready")',
            )
        )
        + "\n"
    )
    request.artifacts.generated_manifest.write_text(
        "\n".join(
            (
                f'name = "{package_name}"',
                f'title = "{package_name.replace("_", " ").title()}"',
                'description = "Generated release-readiness workflow package."',
                'aliases = ["release-go-no-go"]',
            )
        )
        + "\n"
    )
    request.artifacts.generated_prompt_index.write_text(
        "\n".join(
            (
                "# Generated Prompts",
                "",
                "- `review_release_producer.md`",
                "- `review_release_verifier.md`",
                "",
            )
        )
        + "\n"
    )
    (request.artifacts.generated_prompts_dir.path / "review_release_producer.md").write_text(
        "Review the release candidate and draft the evidence package.\n",
        encoding="utf-8",
    )
    (request.artifacts.generated_prompts_dir.path / "review_release_verifier.md").write_text(
        "Verify the release review artifacts and choose the next route.\n",
        encoding="utf-8",
    )
    (request.artifacts.generated_assets_dir.path / ".gitkeep").write_text("", encoding="utf-8")
    request.artifacts.generated_doc.write_text(
        "\n".join(
            (
                f"# `{package_name}`",
                "",
                "Generated by the workflow-builder integration test.",
                "",
            )
        )
        + "\n"
    )
    request.artifacts.generated_test.write_text(
        "\n".join(
            (
                "from __future__ import annotations",
                "",
                "",
                "def test_generated_workflow_package_placeholder() -> None:",
                "    assert True",
            )
        )
        + "\n"
    )
    request.artifacts.build_report.write_text(
        "\n".join(
            (
                "# Build Report",
                "",
                f"- Created `workflows/{package_name}` with scaffold files.",
                f"- Created `docs/workflows/{package_name}.md`.",
                f"- Created `tests/runtime/test_{package_name}.py`.",
                "- Created generated prompt files and a prompt index.",
                "",
            )
        )
        + "\n"
    )
    return "built package\n"


def _workflow_class_name(package_name: str) -> str:
    return "".join(part.capitalize() for part in package_name.split("_"))
