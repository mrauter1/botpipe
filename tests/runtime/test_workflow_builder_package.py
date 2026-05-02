from __future__ import annotations

import importlib
import json
import shutil
import sys
from pathlib import Path

import pytest

from autoloop.core.compiler import compile_workflow
from autoloop.core.context import Context
from autoloop.core.providers.fake import ScriptedLLMProvider
from autoloop.core.stores import InMemorySessionStore
from autoloop.runtime.config import GitTrackingRuntimeConfig, RuntimeConfig
from autoloop.runtime.loader import (
    WorkflowParameterError,
    coerce_workflow_parameter_mapping,
    discover_workflow_packages,
    resolve_workflow_reference,
)
from autoloop.runtime.runner import RunnerOptions, run_workflow_package
from autoloop.core.primitives import Outcome


REPO_ROOT = Path(__file__).resolve().parents[2]
COMMON_PROMPT_CONTRACT_MARKERS = (
    "## Step Contract",
    "## Artifact Contract",
    "| Artifact | Direction | Notes |",
    "## Output Requirements",
    "## Routes",
    "## Forbidden",
)
LEGACY_PROMPT_SCAFFOLDING_MARKERS = ("Read these artifacts", "Write these artifacts")


def _assert_compact_prompt_contract(
    prompt_name: str,
    text: str,
    required_markers: tuple[str, ...],
) -> None:
    for marker in COMMON_PROMPT_CONTRACT_MARKERS:
        assert marker in text, f"{prompt_name} is missing required contract marker: {marker}"

    for marker in required_markers:
        assert marker in text, f"{prompt_name} is missing required contract marker: {marker}"

    for marker in LEGACY_PROMPT_SCAFFOLDING_MARKERS:
        assert marker not in text, f"{prompt_name} still contains legacy scaffolding marker: {marker}"


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
    assert list(compiled.route("frame_candidate", "candidate_selected").required_writes) == [
        "frame_candidate.candidate_comparison",
        "frame_candidate.selected_workflow_brief",
    ]
    assert compiled.route("frame_candidate", "candidate_selected").handoff == (
        "Locks the selected addition and its classification for downstream design."
    )
    assert frame_step.expected_output_schema is not None

    build_step = compiled.steps["build_package"]
    assert "package_built" in build_step.available_routes
    assert "needs_replan" in compiled.routes["build_package"]
    assert build_step.expected_output_schema is not None

    evaluate_step = compiled.steps["evaluate_package"]
    assert list(compiled.route("evaluate_package", "evaluation_passed").required_writes) == [
        "evaluate_package.verification_report",
        "evaluate_package.promotion_record",
        "evaluate_package.rollback_plan",
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


def test_workflow_builder_package_prompt_readme_uses_shared_contract_sections() -> None:
    text = (REPO_ROOT / "workflows" / "workflow_idea_to_workflow_package" / "prompts" / "README.md").read_text(
        encoding="utf-8"
    )

    for required in (
        "## Shared README Boundary",
        "## Keep In Each Prompt",
        "## Step Surface",
        "## Route Surface",
        "## Verifier Payloads",
        "Reserved routes:",
        "`question`",
        "`blocked`",
        "`failed`",
        "Application routes:",
        "`candidate_selected`",
        "`design_accepted`",
        "`package_built`",
        "`evaluation_passed`",
        "`needs_rework`",
        "`needs_replan`",
        "`frame_producer.md` / `frame_verifier.md`",
        "WorkflowEvaluationPayload",
        "compact human-readable step contract",
        "Provider raw output is runtime telemetry",
    ):
        assert required in text


@pytest.mark.parametrize(
    ("prompt_name", "required_markers"),
    (
        (
            "frame_producer.md",
            (
                "`candidate_comparison`",
                "`selected_workflow_brief`",
                "`candidate_selected`",
                "`needs_rework`",
                "`needs_replan`",
            ),
        ),
        (
            "frame_verifier.md",
            (
                "Required outcome structure",
                "`candidate_selected`",
                "`needs_rework`",
                "`needs_replan`",
                "at least three credible candidates were compared",
            ),
        ),
        (
            "design_producer.md",
            (
                "`workflow_package_spec`",
                "`step_contracts`",
                "`prompt_contract_matrix`",
                "`verification_plan`",
                "`design_accepted`",
            ),
        ),
        (
            "design_verifier.md",
            (
                "Required outcome structure",
                "`design_accepted`",
                "`needs_rework`",
                "`needs_replan`",
                "provider-facing packet abstraction",
            ),
        ),
        (
            "build_producer.md",
            (
                "`generated_layout`",
                "`build_report`",
                "`package_built`",
                "`needs_rework`",
                "`needs_replan`",
            ),
        ),
        (
            "build_verifier.md",
            (
                "Required outcome structure",
                "`package_built`",
                "`needs_rework`",
                "`needs_replan`",
                "`build_report` accounts for the output set",
            ),
        ),
        (
            "evaluate_producer.md",
            (
                "`verification_report`",
                "`promotion_record`",
                "`rollback_plan`",
                "`evaluation_passed`",
                "`needs_rework`",
            ),
        ),
        (
            "evaluate_verifier.md",
            (
                "Required outcome structure",
                "`evaluation_passed`",
                "`needs_rework`",
                "`needs_replan`",
                "Do not accept missing rollback evidence.",
            ),
        ),
    ),
)
def test_workflow_builder_package_prompts_keep_step_local_contracts_explicit(
    prompt_name: str,
    required_markers: tuple[str, ...],
) -> None:
    text = (
        REPO_ROOT / "workflows" / "workflow_idea_to_workflow_package" / "prompts" / prompt_name
    ).read_text(encoding="utf-8")

    _assert_compact_prompt_contract(prompt_name, text, required_markers)


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


def test_workflow_builder_package_accepts_cli_style_flow_specs_parameter(tmp_path: Path) -> None:
    _install_repo_workflow_builder_package(tmp_path)
    parameters_cls = resolve_workflow_reference(tmp_path, "workflow_idea_to_workflow_package").parameters_cls

    parameters = coerce_workflow_parameter_mapping(
        parameters_cls,
        {
            "package_name": "release_candidate_to_go_no_go",
            "workflow_kind": "end_to_end",
            "authoring_shape": "flow-specs",
        },
    )

    assert parameters["authoring_shape"] == "flow_specs"


def test_workflow_builder_package_normalizes_optional_title_aliases_and_target_command(tmp_path: Path) -> None:
    _install_repo_workflow_builder_package(tmp_path)
    parameters_cls = resolve_workflow_reference(tmp_path, "workflow_idea_to_workflow_package").parameters_cls

    parameters = coerce_workflow_parameter_mapping(
        parameters_cls,
        {
            "package_name": "release_candidate_to_go_no_go",
            "package_title": " Release Candidate To Go / No-Go ",
            "workflow_kind": "end_to_end",
            "aliases": [" release-go-no-go ", "", "release-go-no-go", "release-decision"],
            "target_test_command": " pytest -q tests/runtime/test_release_candidate_to_go_no_go.py ",
        },
    )

    assert parameters == {
        "aliases": ["release-go-no-go", "release-decision"],
        "authoring_shape": "flow_specs",
        "package_name": "release_candidate_to_go_no_go",
        "package_title": "Release Candidate To Go / No-Go",
        "target_test_command": "pytest -q tests/runtime/test_release_candidate_to_go_no_go.py",
        "workflow_kind": "end_to_end",
    }


def test_workflow_builder_package_bootstrap_reads_typed_ctx_params(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.workflow_idea_to_workflow_package")
    parameters_cls = resolve_workflow_reference(REPO_ROOT, "workflow_idea_to_workflow_package").parameters_cls
    assert parameters_cls is not None
    typed_params = parameters_cls.model_validate(
        coerce_workflow_parameter_mapping(
            parameters_cls,
            {
                "package_name": " release_candidate_to_go_no_go ",
                "package_title": " Release Candidate To Go / No-Go ",
                "workflow_kind": "end_to_end",
                "authoring_shape": "flow-specs",
                "aliases": [" release-go-no-go ", "", "release-go-no-go", "release-decision"],
                "target_test_command": " pytest -q tests/runtime/test_release_candidate_to_go_no_go.py ",
            },
        )
    )

    task_folder = tmp_path / ".autoloop" / "tasks" / "typed-bootstrap-task"
    workflow_folder = task_folder / "wf_workflow_idea_to_workflow_package"
    run_folder = workflow_folder / "runs" / "run-1"
    run_folder.mkdir(parents=True, exist_ok=True)
    (run_folder / "request.md").write_text("Typed bootstrap request.\n", encoding="utf-8")

    ctx = Context(
        task_id="typed-bootstrap-task",
        run_id="run-1",
        workflow_name="workflow_idea_to_workflow_package",
        task_folder=task_folder,
        workflow_folder=workflow_folder,
        run_folder=run_folder,
        package_folder=REPO_ROOT / "workflows" / "workflow_idea_to_workflow_package",
        state=workflow_pkg.WorkflowIdeaToWorkflowPackage.State(),
        session_store=InMemorySessionStore(),
        params=typed_params,
        workflow_params={
            "package_name": "wrong_package",
            "package_title": "Wrong Title",
            "workflow_kind": "building_block",
            "authoring_shape": "single",
            "aliases": ["wrong-alias"],
            "target_test_command": "pytest wrong_test.py",
        },
    )

    next_state, event = workflow_pkg.WorkflowIdeaToWorkflowPackage.on_bootstrap(
        workflow_pkg.WorkflowIdeaToWorkflowPackage.State(),
        ctx,
    )

    assert event.tag == "inputs_prepared"
    assert next_state.package_name == "release_candidate_to_go_no_go"
    assert next_state.package_title == "Release Candidate To Go / No-Go"
    assert next_state.workflow_kind == "end_to_end"
    assert next_state.authoring_shape == "flow_specs"
    assert next_state.aliases == ["release-go-no-go", "release-decision"]
    assert next_state.target_test_command == "pytest -q tests/runtime/test_release_candidate_to_go_no_go.py"
    assert ctx.get_session("frame_session") is not None
    assert ctx.get_session("design_session") is not None
    assert ctx.get_session("build_session") is not None
    assert ctx.get_session("evaluate_session") is not None

    invocation_contract = json.loads((workflow_folder / "invocation_contract.json").read_text(encoding="utf-8"))
    assert invocation_contract["package_name"] == "release_candidate_to_go_no_go"
    assert invocation_contract["package_title"] == "Release Candidate To Go / No-Go"
    assert invocation_contract["workflow_kind"] == "end_to_end"
    assert invocation_contract["authoring_shape"] == "flow_specs"
    assert invocation_contract["aliases"] == next_state.aliases
    assert invocation_contract["target_test_command"] == "pytest -q tests/runtime/test_release_candidate_to_go_no_go.py"


@pytest.mark.parametrize(
    ("authoring_shape", "expected_source"),
    [
        ("single", "workflows/release_candidate_to_go_no_go.py"),
        ("flow_specs", "workflows/release_candidate_to_go_no_go/flow.py"),
        ("package", "workflows/release_candidate_to_go_no_go/flow.py"),
    ],
)
def test_workflow_builder_package_runs_and_generates_a_compilable_package(
    tmp_path: Path,
    authoring_shape: str,
    expected_source: str,
) -> None:
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
                            f"Authoring shape: {authoring_shape}.",
                            "Control flow: bootstrap -> review -> verify -> publish.",
                            "Runtime control contract: only expected_output_schema, available_routes, routes, and route_required_writes.",
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
                            f"- authoring shape: `{authoring_shape}`",
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
            lambda request: _write_generated_workflow(request, generated_name, authoring_shape),
            lambda request: (
                request.artifacts.verification_report.write_text(
                    "\n".join(
                        (
                            "# Verification Report",
                            "",
                            "- Verified workflow discovery and compilation.",
                            f"- Verified the generated `{authoring_shape}` workflow surface exists.",
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
                            f"Promote `{generated_name}` because the selected `{authoring_shape}` workflow surface compiles.",
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
                            f"- Remove `{expected_source}`.",
                            "- Revert any optional support files recorded in `generated_layout.json`.",
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
                    "prompt_files": [],
                    "next_action": "build_package",
                },
            ),
            Outcome(
                raw_output="package built\n",
                tag="package_built",
                payload={
                    "summary": "Generated the requested workflow shape and build evidence.",
                    "changed_paths": [
                        expected_source,
                        f".autoloop/tasks/workflow-builder-task/wf_workflow_idea_to_workflow_package/generated_layout.json",
                    ],
                    "evidence_artifacts": [
                        "generated_layout",
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
                "authoring_shape": authoring_shape,
                "aliases": ["release-go-no-go"],
                "target_test_command": "pytest -q",
            },
            runtime_config=RuntimeConfig(git_tracking=GitTrackingRuntimeConfig(enabled=False)),
        ),
    )

    workflow_dir = tmp_path / ".autoloop" / "tasks" / "workflow-builder-task" / "wf_workflow_idea_to_workflow_package"
    run_dir = next((workflow_dir / "runs").iterdir())
    invocation_contract = json.loads((workflow_dir / "invocation_contract.json").read_text(encoding="utf-8"))
    publish_receipt = json.loads((workflow_dir / "publish_receipt.json").read_text(encoding="utf-8"))

    assert result.terminal == "FINISH"
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
        "authoring_shape": authoring_shape,
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

    assert (workflow_dir / "generated_layout.json").exists()
    generated_layout = json.loads((workflow_dir / "generated_layout.json").read_text(encoding="utf-8"))
    assert generated_layout["authoring_shape"] == authoring_shape
    assert expected_source in generated_layout["created_paths"]

    if authoring_shape == "single":
        assert (tmp_path / "workflows" / f"{generated_name}.py").exists()
        assert not (tmp_path / "workflows" / generated_name).exists()
    else:
        generated_pkg_dir = tmp_path / "workflows" / generated_name
        assert generated_pkg_dir.is_dir()
        assert (generated_pkg_dir / "flow.py").exists()
        assert (generated_pkg_dir / "specs.py").exists()
        if authoring_shape == "package":
            assert (generated_pkg_dir / "__init__.py").exists()
            assert (generated_pkg_dir / "workflow.toml").exists()
            assert (generated_pkg_dir / "prompts" / "README.md").exists()
            assert (generated_pkg_dir / "assets" / ".gitkeep").exists()
        else:
            assert not (generated_pkg_dir / "__init__.py").exists()
            assert not (generated_pkg_dir / "workflow.toml").exists()
            assert not (generated_pkg_dir / "prompts").exists()
            assert not (generated_pkg_dir / "assets").exists()

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
    assert list(provider.calls[5].route_required_writes["package_built"]) == [
        "build_package.generated_layout",
        "build_package.build_report",
    ]
    assert provider.calls[5].routes["package_built"].handoff == (
        "Promotes the generated workflow surface to evaluation."
    )
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


def _write_generated_workflow(request, package_name: str, authoring_shape: str) -> str:
    class_name = _workflow_class_name(package_name)
    created_paths: list[str] = []

    def _record(path: Path) -> None:
        created_paths.append(str(path.resolve().relative_to(request.context.root.resolve())))

    if authoring_shape == "single":
        request.artifacts.generated_single_file.write_text(
            "\n".join(
                (
                    "from __future__ import annotations",
                    "",
                    "from pydantic import BaseModel",
                    "",
                    "from autoloop import Event, FINISH, Workflow, python_step",
                    "",
                    "",
                    f"class {class_name}(Workflow):",
                    f'    name = "{package_name}"',
                    "",
                    "    class State(BaseModel):",
                    "        ready: bool = False",
                    "",
                    '    @python_step(name="bootstrap", routes={"ready": FINISH})',
                    "    def bootstrap(state: State, ctx):",
                    '        ctx.state = state.model_copy(update={"ready": True})',
                    '        return Event("ready")',
                )
            )
            + "\n"
        )
        _record(request.artifacts.generated_single_file.path)
    else:
        request.artifacts.generated_package_root.path.mkdir(parents=True, exist_ok=True)
        request.artifacts.generated_flow.write_text(
            "\n".join(
                (
                    "from __future__ import annotations",
                    "",
                    "from autoloop import Event, FINISH, Workflow, python_step",
                    "",
                    "from .specs import State",
                    "",
                    "",
                    f"class {class_name}(Workflow):",
                    f'    name = "{package_name}"',
                    "    State = State",
                    "",
                    '    @python_step(name="bootstrap", routes={"ready": FINISH})',
                    "    def bootstrap(state: State, ctx):",
                    '        ctx.state = state.model_copy(update={"ready": True})',
                    '        return Event("ready")',
                )
            )
            + "\n"
        )
        request.artifacts.generated_specs.write_text(
            "\n".join(
                (
                    "from __future__ import annotations",
                    "",
                    "from pydantic import BaseModel",
                    "",
                    "",
                    "class State(BaseModel):",
                    "    ready: bool = False",
                )
            )
            + "\n"
        )
        _record(request.artifacts.generated_flow.path)
        _record(request.artifacts.generated_specs.path)

        if authoring_shape == "package":
            request.artifacts.generated_prompts_dir.path.mkdir(parents=True, exist_ok=True)
            request.artifacts.generated_assets_dir.path.mkdir(parents=True, exist_ok=True)
            request.artifacts.generated_init.write_text(
                f'from .flow import {class_name}\n\n__all__ = ["{class_name}"]\n'
            )
            request.artifacts.generated_manifest.write_text(
                "\n".join(
                    (
                        f'name = "{package_name}"',
                        f'title = "{package_name.replace("_", " ").title()}"',
                        'description = "Generated release-readiness workflow."',
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
                        "- Add prompt files here when the workflow design needs them.",
                        "",
                    )
                )
                + "\n"
            )
            (request.artifacts.generated_assets_dir.path / ".gitkeep").write_text("", encoding="utf-8")
            _record(request.artifacts.generated_init.path)
            _record(request.artifacts.generated_manifest.path)
            _record(request.artifacts.generated_prompt_index.path)
            _record(request.artifacts.generated_assets_dir.path / ".gitkeep")

    request.artifacts.generated_layout.write_text(
        json.dumps(
            {
                "authoring_shape": authoring_shape,
                "created_paths": sorted(created_paths),
            },
            indent=2,
        )
        + "\n"
    )
    request.artifacts.build_report.write_text(
        "\n".join(
            (
                "# Build Report",
                "",
                f"- Generated `{authoring_shape}` workflow surface for `{package_name}`.",
                *[f"- Created `{path}`." for path in sorted(created_paths)],
                f"- Wrote `{request.artifacts.generated_layout.path.relative_to(request.context.root)}`.",
                )
        )
        + "\n"
    )
    return "built package\n"


def _workflow_class_name(package_name: str) -> str:
    return "".join(part.capitalize() for part in package_name.split("_"))
