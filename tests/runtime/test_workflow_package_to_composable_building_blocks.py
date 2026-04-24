from __future__ import annotations

import importlib
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from autoloop_v3.core.compiler import compile_workflow
from autoloop_v3.core.context import Context
from autoloop_v3.core.providers.fake import ScriptedLLMProvider
from autoloop_v3.core.stores import InMemorySessionStore
from autoloop_v3.runtime.loader import (
    WorkflowParameterError,
    coerce_workflow_parameter_mapping,
    discover_workflow_packages,
    resolve_workflow_reference,
)
from autoloop_v3.runtime.runner import RunnerOptions, run_workflow_package
from workflow.primitives import Outcome


REPO_ROOT = Path(__file__).resolve().parents[2]
TASK_ID = "workflow-decomposition-task"
PARENT_PROMPT_RELATIVE_PATH = "workflows/release_candidate_to_go_no_go/prompts/evidence_producer.md"
PARENT_DOC_RELATIVE_PATH = "docs/workflows/release_candidate_to_go_no_go.md"
PARENT_TEST_RELATIVE_PATH = "tests/runtime/test_release_candidate_to_go_no_go.py"
BUILDING_BLOCK_NAME = "release_decision_evidence_pack"
BUILDING_BLOCK_ROOT = f"workflows/{BUILDING_BLOCK_NAME}"
BUILDING_BLOCK_INIT_RELATIVE_PATH = f"{BUILDING_BLOCK_ROOT}/__init__.py"
BUILDING_BLOCK_WORKFLOW_RELATIVE_PATH = f"{BUILDING_BLOCK_ROOT}/workflow.py"
BUILDING_BLOCK_MANIFEST_RELATIVE_PATH = f"{BUILDING_BLOCK_ROOT}/workflow.toml"
BUILDING_BLOCK_PROMPT_README_RELATIVE_PATH = f"{BUILDING_BLOCK_ROOT}/prompts/README.md"
BUILDING_BLOCK_ASSET_RELATIVE_PATH = f"{BUILDING_BLOCK_ROOT}/assets/{BUILDING_BLOCK_NAME}_checklist.md"
BUILDING_BLOCK_DOC_RELATIVE_PATH = f"docs/workflows/{BUILDING_BLOCK_NAME}.md"
BUILDING_BLOCK_TEST_RELATIVE_PATH = f"tests/runtime/test_{BUILDING_BLOCK_NAME}.py"
ADDED_RELATIVE_PATHS = sorted(
    [
        BUILDING_BLOCK_ASSET_RELATIVE_PATH,
        BUILDING_BLOCK_DOC_RELATIVE_PATH,
        BUILDING_BLOCK_INIT_RELATIVE_PATH,
        BUILDING_BLOCK_MANIFEST_RELATIVE_PATH,
        BUILDING_BLOCK_PROMPT_README_RELATIVE_PATH,
        BUILDING_BLOCK_TEST_RELATIVE_PATH,
        BUILDING_BLOCK_WORKFLOW_RELATIVE_PATH,
    ]
)
CHANGED_RELATIVE_PATHS = sorted([PARENT_DOC_RELATIVE_PATH, PARENT_PROMPT_RELATIVE_PATH, *ADDED_RELATIVE_PATHS])
TARGET_TEST_COMMAND = (
    "pytest -q "
    "tests/runtime/test_release_candidate_to_go_no_go.py "
    f"tests/runtime/test_{BUILDING_BLOCK_NAME}.py"
)


def _clear_workflow_modules() -> None:
    for name in list(sys.modules):
        if name == "workflows" or name.startswith("workflows."):
            sys.modules.pop(name, None)


@pytest.fixture(autouse=True)
def _isolate_workflow_modules():
    _clear_workflow_modules()
    yield
    _clear_workflow_modules()


def test_repo_workflows_namespace_discovers_workflow_package_to_composable_building_blocks() -> None:
    discovered = {package.workflow_name: package for package in discover_workflow_packages(REPO_ROOT)}

    assert "workflow_package_to_composable_building_blocks" in discovered
    package = discovered["workflow_package_to_composable_building_blocks"]
    assert package.package_name == "workflow_package_to_composable_building_blocks"
    assert "workflow-package-to-building-blocks" in package.aliases
    assert package.manifest_path == (
        REPO_ROOT
        / "workflows"
        / "workflow_package_to_composable_building_blocks"
        / "workflow.toml"
    )


def test_workflow_package_to_composable_building_blocks_aliases_resolve_to_same_package(
    monkeypatch,
) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    canonical = resolve_workflow_reference(REPO_ROOT, "workflow_package_to_composable_building_blocks")
    hyphenated = resolve_workflow_reference(REPO_ROOT, "workflow-package-to-building-blocks")
    decomposition = resolve_workflow_reference(REPO_ROOT, "workflow-decomposition-package")

    assert canonical.package.package_name == "workflow_package_to_composable_building_blocks"
    assert hyphenated.package.package_name == canonical.package.package_name
    assert decomposition.package.package_name == canonical.package.package_name
    assert canonical.package.workflow_name == "workflow_package_to_composable_building_blocks"
    assert hyphenated.package.workflow_name == canonical.package.workflow_name
    assert decomposition.package.workflow_name == canonical.package.workflow_name


def test_workflow_package_to_composable_building_blocks_compiles_with_explicit_control_contracts(
    monkeypatch,
) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT))
    importlib.invalidate_caches()
    _clear_workflow_modules()

    workflow_pkg = importlib.import_module("workflows.workflow_package_to_composable_building_blocks")
    resolved = resolve_workflow_reference(
        REPO_ROOT,
        workflow_pkg.WorkflowPackageToComposableBuildingBlocks,
    )
    compiled = compile_workflow(resolved.workflow_cls)

    assert resolved.parameters_cls is not None
    assert compiled.entry_step_name == "bootstrap"
    assert tuple(compiled.steps) == (
        "bootstrap",
        "capture_decomposition_context",
        "frame_decomposition_request",
        "design_decomposition_plan",
        "implement_candidate_decomposition",
        "evaluate_candidate_decomposition",
        "publish_candidate_decomposition",
    )

    frame_step = compiled.steps["frame_decomposition_request"]
    assert frame_step.available_routes == (
        "decomposition_request_framed",
        "needs_rework",
        "needs_replan",
        "question",
        "blocked",
        "failed",
    )
    assert frame_step.route_contracts["decomposition_request_framed"]["required_artifacts"] == [
        "decomposition_request_brief",
        "decomposition_acceptance_criteria",
    ]
    assert frame_step.expected_output_schema is not None

    design_step = compiled.steps["design_decomposition_plan"]
    assert design_step.route_contracts["decomposition_plan_designed"]["required_artifacts"] == [
        "extraction_strategy",
        "building_block_interface_contracts",
        "parent_rewrite_plan",
        "regression_guardrails",
    ]
    assert design_step.expected_output_schema is not None

    implement_step = compiled.steps["implement_candidate_decomposition"]
    assert implement_step.route_contracts["candidate_decomposition_built"]["required_artifacts"] == [
        "candidate_decomposition_surface",
        "candidate_building_block_index",
        "decomposition_build_report",
        "candidate_diff_summary",
    ]
    assert implement_step.expected_output_schema is not None
    assert set(implement_step.expected_output_schema["required"]) >= {
        "summary",
        "selected_workflow_name",
        "candidate_file_count",
        "changed_relative_paths",
        "building_block_names",
    }

    evaluate_step = compiled.steps["evaluate_candidate_decomposition"]
    assert evaluate_step.route_contracts["candidate_decomposition_evaluated"]["required_artifacts"] == [
        "decomposition_verification_report",
        "composition_migration_guide",
        "promotion_record",
        "rollback_plan",
    ]
    assert evaluate_step.expected_output_schema is not None
    assert set(evaluate_step.expected_output_schema["required"]) >= {
        "summary",
        "selected_workflow_name",
        "candidate_file_count",
        "validated_overlay_command",
        "authoritative_artifacts",
        "building_block_names",
        "next_action",
        "ready_for_publication",
    }

    publish_step = compiled.steps["publish_candidate_decomposition"]
    assert publish_step.requires == (
        "selected_workflow_decomposition_surface",
        "baseline_parent_manifest",
        "decomposition_evidence_manifest",
        "candidate_decomposition_manifest",
        "candidate_building_block_index",
        "decomposition_verification_report",
        "composition_migration_guide",
        "promotion_record",
        "rollback_plan",
    )


def test_workflow_package_to_composable_building_blocks_docs_capture_decision_records() -> None:
    text = (
        REPO_ROOT / "docs" / "workflows" / "workflow_package_to_composable_building_blocks.md"
    ).read_text(encoding="utf-8")

    for required in (
        "Candidate additions considered",
        "Framework improvement candidates considered",
        "Meaningful design decisions",
        "Implementation candidates considered",
        "Route grammar",
        "Runtime-injected control contract",
        "tests/runtime/test_workflow_package_to_composable_building_blocks.py",
    ):
        assert required in text


def test_workflow_package_to_composable_building_blocks_prompt_readme_lists_route_grammar_and_runtime_boundary() -> None:
    text = (
        REPO_ROOT
        / "workflows"
        / "workflow_package_to_composable_building_blocks"
        / "prompts"
        / "README.md"
    ).read_text(encoding="utf-8")

    for required in (
        "Reserved routes:",
        "- `question`",
        "- `blocked`",
        "- `failed`",
        "Application routes:",
        "- `decomposition_request_framed`",
        "- `decomposition_plan_designed`",
        "- `candidate_decomposition_built`",
        "- `candidate_decomposition_evaluated`",
        "The runtime injects only `expected_output_schema`, `available_routes`, and `route_contracts`.",
    ):
        assert required in text


@pytest.mark.parametrize(
    ("prompt_name", "required_markers"),
    (
        (
            "frame_producer.md",
            (
                "Read these artifacts",
                "Write these artifacts",
                "Evidence requirements",
                "Route guidance for the verifier",
                "Forbidden",
                "`decomposition_request_brief`",
                "`decomposition_acceptance_criteria`",
                "`decomposition_request_framed`",
                "`needs_rework`",
                "`needs_replan`",
                "Reserved routes are only",
            ),
        ),
        (
            "frame_verifier.md",
            (
                "Read these artifacts",
                "Write these artifacts",
                "Artifact checks",
                "Evidence requirements",
                "Route guidance",
                "Payload requirements",
                "Forbidden",
                "Do not overwrite `decomposition_request_brief` or `decomposition_acceptance_criteria` during verification.",
                "Return verifier control metadata only through the step payload and selected route.",
                "`decomposition_request_framed`",
                "`needs_rework`",
                "`needs_replan`",
                "Use reserved routes only",
            ),
        ),
        (
            "design_producer.md",
            (
                "Read these artifacts",
                "Write these artifacts",
                "Evidence requirements",
                "Route guidance for the verifier",
                "Forbidden",
                "`extraction_strategy`",
                "`building_block_interface_contracts`",
                "`parent_rewrite_plan`",
                "`regression_guardrails`",
                "`decomposition_plan_designed`",
                "`needs_rework`",
                "`needs_replan`",
                "Reserved routes are only",
            ),
        ),
        (
            "design_verifier.md",
            (
                "Read these artifacts",
                "Write these artifacts",
                "Artifact checks",
                "Evidence requirements",
                "Route guidance",
                "Payload requirements",
                "Forbidden",
                "Do not overwrite `extraction_strategy`, `building_block_interface_contracts`, `parent_rewrite_plan`, or `regression_guardrails` during verification.",
                "Return verifier control metadata only through the step payload and selected route.",
                "`decomposition_plan_designed`",
                "`needs_rework`",
                "`needs_replan`",
                "Use reserved routes only",
            ),
        ),
        (
            "implement_producer.md",
            (
                "Read these artifacts",
                "Write these artifacts",
                "Evidence requirements",
                "Route guidance for the verifier",
                "Forbidden",
                "`candidate_decomposition_surface`",
                "`candidate_building_block_index.json`",
                "`candidate_decomposition_manifest.json`",
                "`decomposition_build_report`",
                "`candidate_diff_summary`",
                "`candidate_decomposition_built`",
                "`needs_rework`",
                "`needs_replan`",
                "Reserved routes are only",
            ),
        ),
        (
            "implement_verifier.md",
            (
                "Read these artifacts",
                "Write these artifacts",
                "Artifact checks",
                "Evidence requirements",
                "Route guidance",
                "Payload requirements",
                "Forbidden",
                "Do not overwrite `candidate_decomposition_surface`, `candidate_building_block_index`, `decomposition_build_report`, or `candidate_diff_summary` during verification.",
                "Do not hand-write `candidate_decomposition_manifest.json` during verification.",
                "Return verifier control metadata only through the step payload and selected route.",
                "`candidate_decomposition_built`",
                "`needs_rework`",
                "`needs_replan`",
                "Use reserved routes only",
            ),
        ),
        (
            "evaluate_producer.md",
            (
                "Read these artifacts",
                "Write these artifacts",
                "Evidence requirements",
                "Route guidance for the verifier",
                "Forbidden",
                "`decomposition_verification_report`",
                "`composition_migration_guide`",
                "`promotion_record`",
                "`rollback_plan`",
                "`candidate_decomposition_evaluated`",
                "`needs_rework`",
                "`needs_replan`",
                "`workflow_decomposition_receipt.json`",
                "Reserved routes are only",
            ),
        ),
        (
            "evaluate_verifier.md",
            (
                "Read these artifacts",
                "Write these artifacts",
                "Artifact checks",
                "Evidence requirements",
                "Route guidance",
                "Payload requirements",
                "Forbidden",
                "Do not overwrite `decomposition_verification_report`, `composition_migration_guide`, `promotion_record`, or `rollback_plan` during verification.",
                "Do not create `workflow_decomposition_receipt.json` in this step.",
                "Return verifier control metadata only through the step payload and selected route.",
                "`candidate_decomposition_evaluated`",
                "`needs_rework`",
                "`needs_replan`",
                "Use reserved routes only",
            ),
        ),
    ),
)
def test_workflow_package_to_composable_building_blocks_prompts_keep_step_local_contracts_explicit(
    prompt_name: str,
    required_markers: tuple[str, ...],
) -> None:
    text = (
        REPO_ROOT
        / "workflows"
        / "workflow_package_to_composable_building_blocks"
        / "prompts"
        / prompt_name
    ).read_text(encoding="utf-8")

    for marker in required_markers:
        assert marker in text, f"{prompt_name} is missing required contract marker: {marker}"


def test_workflow_package_to_composable_building_blocks_rejects_blank_selected_workflow(
    tmp_path: Path,
) -> None:
    _install_repo_workflow_package_to_composable_building_blocks(tmp_path)
    parameters_cls = resolve_workflow_reference(
        tmp_path,
        "workflow_package_to_composable_building_blocks",
    ).parameters_cls

    with pytest.raises(WorkflowParameterError, match="value must be non-empty"):
        coerce_workflow_parameter_mapping(
            parameters_cls,
            {
                "selected_workflow": "   ",
                "task_title": "Release workflow decomposition",
            },
        )


def test_workflow_package_to_composable_building_blocks_normalizes_repeatable_inputs(
    tmp_path: Path,
) -> None:
    _install_repo_workflow_package_to_composable_building_blocks(tmp_path)
    parameters_cls = resolve_workflow_reference(
        tmp_path,
        "workflow_package_to_composable_building_blocks",
    ).parameters_cls

    normalized = coerce_workflow_parameter_mapping(
        parameters_cls,
        {
            "selected_workflow": " release_candidate_to_go_no_go ",
            "task_title": " Release workflow decomposition ",
            "evidence_paths": [
                " .autoloop/signals/release_decomposition_pressure.md ",
                "",
                ".autoloop/signals/release_decomposition_pressure.md",
            ],
            "sponsor_role": " Engineering Productivity ",
            "desired_outcome": " ",
            "constraints": [
                " keep runtime control narrow ",
                "",
                "keep runtime control narrow",
                "Stop before promotion.",
            ],
            "target_test_command": f" {TARGET_TEST_COMMAND} ",
            "max_candidate_building_blocks": 2,
        },
    )

    assert normalized == {
        "constraints": ["keep runtime control narrow", "Stop before promotion."],
        "desired_outcome": None,
        "evidence_paths": [".autoloop/signals/release_decomposition_pressure.md"],
        "max_candidate_building_blocks": 2,
        "selected_workflow": "release_candidate_to_go_no_go",
        "sponsor_role": "Engineering Productivity",
        "target_test_command": TARGET_TEST_COMMAND,
        "task_title": "Release workflow decomposition",
    }


def test_workflow_package_to_composable_building_blocks_runs_and_publishes_candidate_decomposition_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run = _run_successful_decomposition_workflow(tmp_path, monkeypatch, include_evidence_paths=True)

    invocation_contract = json.loads((run.workflow_dir / "invocation_contract.json").read_text(encoding="utf-8"))
    decomposition_surface = json.loads(
        (run.workflow_dir / "selected_workflow_decomposition_surface.json").read_text(encoding="utf-8")
    )
    baseline_manifest = json.loads((run.workflow_dir / "baseline_parent_manifest.json").read_text(encoding="utf-8"))
    evidence_manifest = json.loads((run.workflow_dir / "decomposition_evidence_manifest.json").read_text(encoding="utf-8"))
    candidate_index = json.loads((run.workflow_dir / "candidate_building_block_index.json").read_text(encoding="utf-8"))
    candidate_manifest = json.loads(
        (run.workflow_dir / "candidate_decomposition_manifest.json").read_text(encoding="utf-8")
    )
    receipt = json.loads((run.workflow_dir / "workflow_decomposition_receipt.json").read_text(encoding="utf-8"))

    assert run.result.terminal == "SUCCESS"
    assert (run.workflow_dir / "selected_workflow_decomposition_surface.json").exists()
    assert (run.workflow_dir / "baseline_parent_workflow_surface").exists()
    assert (run.workflow_dir / "baseline_parent_manifest.json").exists()
    assert (run.workflow_dir / "decomposition_evidence_manifest.json").exists()
    assert (run.workflow_dir / "decomposition_request_brief.md").exists()
    assert (run.workflow_dir / "decomposition_acceptance_criteria.md").exists()
    assert (run.workflow_dir / "extraction_strategy.md").exists()
    assert (run.workflow_dir / "building_block_interface_contracts.json").exists()
    assert (run.workflow_dir / "parent_rewrite_plan.md").exists()
    assert (run.workflow_dir / "regression_guardrails.md").exists()
    assert (run.workflow_dir / "candidate_decomposition_surface").exists()
    assert (run.workflow_dir / "candidate_building_block_index.json").exists()
    assert (run.workflow_dir / "candidate_decomposition_manifest.json").exists()
    assert (run.workflow_dir / "decomposition_build_report.md").exists()
    assert (run.workflow_dir / "candidate_diff_summary.md").exists()
    assert (run.workflow_dir / "decomposition_verification_report.md").exists()
    assert (run.workflow_dir / "composition_migration_guide.md").exists()
    assert (run.workflow_dir / "promotion_record.md").exists()
    assert (run.workflow_dir / "rollback_plan.md").exists()
    assert (run.workflow_dir / "workflow_decomposition_receipt.json").exists()
    assert not (run.task_dir / "wf_release_candidate_to_go_no_go").exists()

    assert invocation_contract == {
        "constraints": [
            "Keep runtime control narrow.",
            "Stop before promotion.",
        ],
        "desired_outcome": "Publish a candidate decomposition overlay and receipt for the selected workflow.",
        "evidence_paths": [".autoloop/signals/release_decomposition_pressure.md"],
        "max_candidate_building_blocks": 2,
        "message": "Decompose the release workflow into reusable building blocks.\n",
        "request_file": str(run.run_dir / "request.md"),
        "run_id": run.run_dir.name,
        "selected_workflow_reference": "release_candidate_to_go_no_go",
        "sponsor_role": "engineering productivity",
        "target_test_command": TARGET_TEST_COMMAND,
        "task_id": TASK_ID,
        "task_title": "Release workflow decomposition candidate",
        "workflow_name": "workflow_package_to_composable_building_blocks",
    }
    assert decomposition_surface["selected_workflow_name"] == "release_candidate_to_go_no_go"
    assert baseline_manifest["selected_workflow_name"] == "release_candidate_to_go_no_go"
    assert PARENT_PROMPT_RELATIVE_PATH in baseline_manifest["relative_paths"]
    assert PARENT_DOC_RELATIVE_PATH in baseline_manifest["relative_paths"]
    assert PARENT_TEST_RELATIVE_PATH in baseline_manifest["relative_paths"]
    assert evidence_manifest["capture_status"] == "captured"
    assert evidence_manifest["request_fallback_used"] is False
    assert evidence_manifest["entries"][0]["requested_path"] == ".autoloop/signals/release_decomposition_pressure.md"
    assert candidate_index["publication_mode"] == "candidate_only"
    assert candidate_index["promotion_required"] is True
    assert candidate_index["building_blocks"][0]["workflow_name"] == BUILDING_BLOCK_NAME
    assert candidate_manifest["surface_kind"] == "candidate_decomposition"
    assert candidate_manifest["selected_workflow_name"] == "release_candidate_to_go_no_go"
    assert candidate_manifest["file_count"] == baseline_manifest["file_count"] + len(ADDED_RELATIVE_PATHS)
    assert candidate_manifest["changed_relative_paths"] == CHANGED_RELATIVE_PATHS
    assert candidate_manifest["added_relative_paths"] == ADDED_RELATIVE_PATHS
    assert candidate_manifest["building_block_names"] == [BUILDING_BLOCK_NAME]
    assert candidate_manifest["building_block_package_roots"] == [BUILDING_BLOCK_ROOT]
    assert receipt["selected_workflow_name"] == "release_candidate_to_go_no_go"
    assert receipt["target_test_command"] == TARGET_TEST_COMMAND
    assert receipt["building_block_names"] == [BUILDING_BLOCK_NAME]
    assert receipt["changed_relative_paths"] == CHANGED_RELATIVE_PATHS
    assert receipt["overlay_validation"] == {
        "compiled_workflow_names": ["release_candidate_to_go_no_go", BUILDING_BLOCK_NAME],
        "test_command": TARGET_TEST_COMMAND,
        "test_returncode": 0,
    }
    assert receipt["published"] is True

    assert (run.workflow_dir / "baseline_parent_workflow_surface" / PARENT_PROMPT_RELATIVE_PATH).read_text(
        encoding="utf-8"
    ) == run.source_snapshot[PARENT_PROMPT_RELATIVE_PATH]
    assert (run.workflow_dir / "candidate_decomposition_surface" / PARENT_PROMPT_RELATIVE_PATH).read_text(
        encoding="utf-8"
    ) != run.source_snapshot[PARENT_PROMPT_RELATIVE_PATH]
    assert (run.workflow_dir / "candidate_decomposition_surface" / PARENT_DOC_RELATIVE_PATH).read_text(
        encoding="utf-8"
    ) != run.source_snapshot[PARENT_DOC_RELATIVE_PATH]
    assert (tmp_path / PARENT_PROMPT_RELATIVE_PATH).read_text(encoding="utf-8") == run.source_snapshot[
        PARENT_PROMPT_RELATIVE_PATH
    ]
    assert (tmp_path / PARENT_DOC_RELATIVE_PATH).read_text(encoding="utf-8") == run.source_snapshot[
        PARENT_DOC_RELATIVE_PATH
    ]
    assert (run.workflow_dir / "candidate_decomposition_surface" / BUILDING_BLOCK_DOC_RELATIVE_PATH).exists()
    assert (run.workflow_dir / "candidate_decomposition_surface" / BUILDING_BLOCK_WORKFLOW_RELATIVE_PATH).exists()
    assert (run.workflow_dir / "candidate_decomposition_surface" / BUILDING_BLOCK_TEST_RELATIVE_PATH).exists()

    assert [call.step_name for call in run.provider.calls] == [
        "frame_decomposition_request",
        "frame_decomposition_request",
        "design_decomposition_plan",
        "design_decomposition_plan",
        "implement_candidate_decomposition",
        "implement_candidate_decomposition",
        "evaluate_candidate_decomposition",
        "evaluate_candidate_decomposition",
    ]
    assert run.provider.calls[1].route_contracts["decomposition_request_framed"]["required_artifacts"] == [
        "decomposition_request_brief",
        "decomposition_acceptance_criteria",
    ]
    assert run.provider.calls[5].available_routes == (
        "candidate_decomposition_built",
        "needs_rework",
        "needs_replan",
        "question",
        "blocked",
        "failed",
    )
    assert run.provider.calls[7].route_contracts["candidate_decomposition_evaluated"]["required_artifacts"] == [
        "decomposition_verification_report",
        "composition_migration_guide",
        "promotion_record",
        "rollback_plan",
    ]


def test_workflow_package_to_composable_building_blocks_records_request_fallback_when_evidence_paths_are_omitted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run = _run_successful_decomposition_workflow(tmp_path, monkeypatch, include_evidence_paths=False)
    evidence_manifest = json.loads((run.workflow_dir / "decomposition_evidence_manifest.json").read_text(encoding="utf-8"))

    assert evidence_manifest["capture_status"] == "captured"
    assert evidence_manifest["request_fallback_used"] is True
    assert evidence_manifest["entries"][0]["fallback_request"] is True
    assert evidence_manifest["entries"][0]["source_path"] == str(run.run_dir / "request.md")


def test_workflow_package_to_composable_building_blocks_routes_to_blocked_for_unreadable_evidence_paths(
    tmp_path: Path,
) -> None:
    _install_repo_workflow_package_to_composable_building_blocks(tmp_path)
    provider = ScriptedLLMProvider(producer_turns=[], verifier_turns=[])

    result = run_workflow_package(
        "workflow_package_to_composable_building_blocks",
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id=TASK_ID,
            message="Decompose the release workflow into reusable building blocks.",
            workflow_params={
                "selected_workflow": "release_candidate_to_go_no_go",
                "task_title": "Release workflow decomposition candidate",
                "evidence_paths": [".autoloop/signals/missing_pressure.md"],
                "sponsor_role": "engineering productivity",
                "desired_outcome": "Publish a candidate decomposition overlay and receipt for the selected workflow.",
                "constraints": [
                    "Keep runtime control narrow.",
                    "Stop before promotion.",
                ],
                "target_test_command": TARGET_TEST_COMMAND,
                "max_candidate_building_blocks": 2,
            },
        ),
    )

    task_dir = tmp_path / ".autoloop" / "tasks" / TASK_ID
    workflow_dir = task_dir / "wf_workflow_package_to_composable_building_blocks"
    run_dir = next((workflow_dir / "runs").iterdir())
    evidence_manifest = json.loads((workflow_dir / "decomposition_evidence_manifest.json").read_text(encoding="utf-8"))

    assert result.terminal == "PAUSE"
    assert result.last_event.tag == "blocked"
    assert evidence_manifest["capture_status"] == "blocked"
    assert "evidence_paths does not exist" in evidence_manifest["blocking_reason"]
    assert evidence_manifest["entries"][-1]["status"] == "unreadable"
    assert run_dir.exists()
    assert provider.calls == []


def test_workflow_package_to_composable_building_blocks_publish_rejects_hidden_execution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run = _run_successful_decomposition_workflow(tmp_path, monkeypatch, include_evidence_paths=True)
    index_path = run.workflow_dir / "candidate_building_block_index.json"
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    payload["publication_mode"] = "promote_in_place"
    index_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="candidate_building_block_index.json must keep publication_mode candidate_only to prevent hidden execution",
    ):
        run.workflow_pkg.WorkflowPackageToComposableBuildingBlocks.on_publish_candidate_decomposition(
            run.result.state,
            run.publish_context,
        )


def test_workflow_package_to_composable_building_blocks_publish_rejects_identity_drift(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run = _run_successful_decomposition_workflow(tmp_path, monkeypatch, include_evidence_paths=True)
    surface_path = run.workflow_dir / "selected_workflow_decomposition_surface.json"
    payload = json.loads(surface_path.read_text(encoding="utf-8"))
    payload["selected_workflow_name"] = "incident_to_hardening_program"
    surface_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="selected_workflow_decomposition_surface.json identity must match selected_workflow_name",
    ):
        run.workflow_pkg.WorkflowPackageToComposableBuildingBlocks.on_publish_candidate_decomposition(
            run.result.state,
            run.publish_context,
        )


def test_workflow_package_to_composable_building_blocks_publish_rejects_candidate_files_outside_allowed_boundary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run = _run_successful_decomposition_workflow(tmp_path, monkeypatch, include_evidence_paths=True)
    extra_file = run.workflow_dir / "candidate_decomposition_surface" / "docs" / "workflows" / "unrelated.md"
    extra_file.parent.mkdir(parents=True, exist_ok=True)
    extra_file.write_text("# Unrelated\n", encoding="utf-8")
    baseline_manifest = json.loads((run.workflow_dir / "baseline_parent_manifest.json").read_text(encoding="utf-8"))
    building_block_index = json.loads((run.workflow_dir / "candidate_building_block_index.json").read_text(encoding="utf-8"))
    run.workflow_pkg._write_candidate_decomposition_manifest(
        run.workflow_dir,
        baseline_manifest,
        building_block_index,
        "release_candidate_to_go_no_go",
        2,
    )

    with pytest.raises(
        ValueError,
        match="candidate_decomposition_manifest.json must stay within the allowed repo-relative boundary",
    ):
        run.workflow_pkg.WorkflowPackageToComposableBuildingBlocks.on_publish_candidate_decomposition(
            run.result.state,
            run.publish_context,
        )


def test_workflow_package_to_composable_building_blocks_publish_rejects_unlisted_candidate_surface_files(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run = _run_successful_decomposition_workflow(tmp_path, monkeypatch, include_evidence_paths=True)
    extra_file = run.workflow_dir / "candidate_decomposition_surface" / "docs" / "workflows" / "unlisted.md"
    extra_file.parent.mkdir(parents=True, exist_ok=True)
    extra_file.write_text("# Unlisted\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="candidate_decomposition_manifest.json relative_paths must match candidate_decomposition_surface",
    ):
        run.workflow_pkg.WorkflowPackageToComposableBuildingBlocks.on_publish_candidate_decomposition(
            run.result.state,
            run.publish_context,
        )


def test_workflow_package_to_composable_building_blocks_publish_rejects_missing_declared_doc_and_runtime_test(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run = _run_successful_decomposition_workflow(tmp_path, monkeypatch, include_evidence_paths=True)
    for relative_path in (BUILDING_BLOCK_DOC_RELATIVE_PATH, BUILDING_BLOCK_TEST_RELATIVE_PATH):
        (run.workflow_dir / "candidate_decomposition_surface" / relative_path).unlink()

    baseline_manifest = json.loads((run.workflow_dir / "baseline_parent_manifest.json").read_text(encoding="utf-8"))
    building_block_index = json.loads((run.workflow_dir / "candidate_building_block_index.json").read_text(encoding="utf-8"))
    candidate_manifest = run.workflow_pkg._write_candidate_decomposition_manifest(
        run.workflow_dir,
        baseline_manifest,
        building_block_index,
        "release_candidate_to_go_no_go",
        2,
    )
    publish_state = run.result.state.model_copy(
        update={
            "candidate_file_count": candidate_manifest["file_count"],
            "candidate_changed_paths": candidate_manifest["changed_relative_paths"],
            "target_test_command": f"pytest -q {PARENT_TEST_RELATIVE_PATH}",
        }
    )

    with pytest.raises(
        ValueError,
        match="candidate_decomposition_manifest.json must include every declared building-block doc_relative_path and runtime_test_relative_path",
    ):
        run.workflow_pkg.WorkflowPackageToComposableBuildingBlocks.on_publish_candidate_decomposition(
            publish_state,
            run.publish_context,
        )


def _run_successful_decomposition_workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    include_evidence_paths: bool,
) -> SimpleNamespace:
    _install_repo_workflow_package_to_composable_building_blocks(tmp_path)
    evidence_path = _write_decomposition_evidence(tmp_path)
    source_snapshot = {
        PARENT_PROMPT_RELATIVE_PATH: (tmp_path / PARENT_PROMPT_RELATIVE_PATH).read_text(encoding="utf-8"),
        PARENT_DOC_RELATIVE_PATH: (tmp_path / PARENT_DOC_RELATIVE_PATH).read_text(encoding="utf-8"),
    }

    provider = ScriptedLLMProvider(
        producer_turns=[
            lambda request: (
                request.artifacts.decomposition_request_brief.write_text(
                    "\n".join(
                        (
                            "# Decomposition Request Brief",
                            "",
                            "Selected workflow: `release_candidate_to_go_no_go`.",
                            "Sponsor: engineering productivity.",
                            "Trigger: the release workflow still bundles evidence capture with assessment, which makes later reuse awkward.",
                            "Terminal outcome: publish a candidate decomposition overlay and receipt, not an in-place promotion.",
                            "Why the boundary stays fixed: the release go/no-go workflow remains the right parent package; the gap is reusable evidence capture, not workflow identity.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.decomposition_acceptance_criteria.write_text(
                    "\n".join(
                        (
                            "# Decomposition Acceptance Criteria",
                            "",
                            "- Keep `release_candidate_to_go_no_go` as the fixed parent workflow boundary.",
                            f"- Extract `{BUILDING_BLOCK_NAME}` as the first reusable building block candidate.",
                            "- Keep the authoritative selected workflow package unchanged before promotion.",
                            "- Publish explicit migration, promotion, and rollback guidance tied to the baseline and candidate manifests.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "framed decomposition request\n",
            )[2],
            lambda request: (
                request.artifacts.extraction_strategy.write_text(
                    "\n".join(
                        (
                            "# Extraction Strategy",
                            "",
                            f"- Extract `{BUILDING_BLOCK_NAME}` so release evidence capture becomes reusable across later release and delivery workflows.",
                            "- Rewrite the parent prompt and workflow documentation so the parent package points at the extracted reusable evidence stage.",
                            "- Keep runtime behavior unchanged and validate the candidate through the release runtime test plus the new building-block runtime test.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.building_block_interface_contracts.write_text(
                    json.dumps(
                        {
                            "building_blocks": [
                                {
                                    "workflow_name": BUILDING_BLOCK_NAME,
                                    "package_name": BUILDING_BLOCK_NAME,
                                    "objective": "Package release decision evidence into a reusable building-block artifact set.",
                                    "inputs": ["request", "release inputs"],
                                    "outputs": ["release evidence package", "evidence receipt"],
                                    "parent_handoff": "The parent workflow adopts the evidence package before assessment.",
                                    "verifier_expectations": [
                                        "Package is discoverable and compiles.",
                                        "Candidate stays candidate-only until explicit promotion.",
                                    ],
                                }
                            ]
                        },
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                ),
                request.artifacts.parent_rewrite_plan.write_text(
                    "\n".join(
                        (
                            "# Parent Rewrite Plan",
                            "",
                            f"- Update `{PARENT_PROMPT_RELATIVE_PATH}` so the parent evidence stage refers to the extracted building block.",
                            f"- Update `{PARENT_DOC_RELATIVE_PATH}` so the migration path and candidate-only boundary are explicit.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.regression_guardrails.write_text(
                    "\n".join(
                        (
                            "# Regression Guardrails",
                            "",
                            f"- Validate the candidate with `{TARGET_TEST_COMMAND}` against an isolated overlay.",
                            "- Keep every baseline parent file present in the candidate overlay.",
                            "- Reject hidden execution and undeclared building-block roots during publication.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "designed decomposition plan\n",
            )[4],
            lambda request: _write_candidate_decomposition_surface(request),
            lambda request: (
                request.artifacts.decomposition_verification_report.write_text(
                    "\n".join(
                        (
                            "# Decomposition Verification Report",
                            "",
                            f"- Candidate overlay should be validated with `{TARGET_TEST_COMMAND}`.",
                            "- Candidate files stay within the parent workflow boundary plus the declared building-block package, doc, and test paths.",
                            "- Candidate publication remains explicit and candidate-only.",
                            "",
                        )
                    )
                    + "\n"
                ),
                request.artifacts.composition_migration_guide.write_text(
                    "\n".join(
                        (
                            "# Composition Migration Guide",
                            "",
                            "- Promote the candidate only after the parent workflow and extracted building block both pass overlay validation.",
                            f"- Adopt `{BUILDING_BLOCK_NAME}` as the reusable evidence stage before later parent workflow cleanup.",
                            "- Keep the baseline parent manifest as the rollback boundary until explicit promotion completes.",
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
                            "- Promote only after `candidate_decomposition_manifest.json` and `candidate_building_block_index.json` remain aligned.",
                            "- Use the decomposition receipt and migration guide as the publication boundary for later adoption.",
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
                            "- Treat the authoritative selected workflow package as the rollback baseline.",
                            "- If the candidate proves unsafe, discard `candidate_decomposition_surface/` and retain the baseline parent manifest as the source of truth.",
                            "",
                        )
                    )
                    + "\n"
                ),
                "evaluated decomposition candidate\n",
            )[4],
        ],
        verifier_turns=[
            Outcome(
                raw_output="decomposition request framed\n",
                tag="decomposition_request_framed",
                payload={
                    "summary": "The selected workflow, evidence bundle, and candidate-only decomposition boundary are explicit enough for planning.",
                    "authoritative_artifacts": [
                        "decomposition_request_brief",
                        "decomposition_acceptance_criteria",
                    ],
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "extraction_focus": [
                        BUILDING_BLOCK_NAME,
                        "candidate-only publication boundary",
                        "parent workflow immutability before promotion",
                    ],
                },
            ),
            Outcome(
                raw_output="decomposition plan designed\n",
                tag="decomposition_plan_designed",
                payload={
                    "summary": "The extraction strategy and parent rewrite plan are explicit enough for implementation.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "building_block_names": [BUILDING_BLOCK_NAME],
                    "planned_change_paths": CHANGED_RELATIVE_PATHS,
                    "verification_focus": [
                        "candidate stays within the declared repo-relative boundary",
                        "overlay validation stays on the release and building-block runtime tests",
                    ],
                },
            ),
            lambda request: Outcome(
                raw_output="candidate decomposition built\n",
                tag="candidate_decomposition_built",
                payload={
                    "summary": "The candidate decomposition surface and build artifacts are explicit enough for evaluation.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "candidate_file_count": _candidate_file_count(request.artifacts.candidate_decomposition_surface.path),
                    "changed_relative_paths": CHANGED_RELATIVE_PATHS,
                    "building_block_names": [BUILDING_BLOCK_NAME],
                },
            ),
            lambda request: Outcome(
                raw_output="candidate decomposition evaluated\n",
                tag="candidate_decomposition_evaluated",
                payload={
                    "summary": "The verification package is publication-ready and tied to the deterministic candidate boundary.",
                    "selected_workflow_name": "release_candidate_to_go_no_go",
                    "candidate_file_count": _candidate_file_count(request.artifacts.candidate_decomposition_surface.path),
                    "validated_overlay_command": TARGET_TEST_COMMAND,
                    "authoritative_artifacts": [
                        "decomposition_verification_report",
                        "composition_migration_guide",
                        "promotion_record",
                        "rollback_plan",
                    ],
                    "building_block_names": [BUILDING_BLOCK_NAME],
                    "next_action": "Use the published candidate package and receipt to decide whether to promote the parent rewrite and extracted building block into the authoritative repo.",
                    "ready_for_publication": True,
                },
            ),
        ],
    )

    workflow_params = {
        "selected_workflow": "release_candidate_to_go_no_go",
        "task_title": "Release workflow decomposition candidate",
        "sponsor_role": "engineering productivity",
        "desired_outcome": "Publish a candidate decomposition overlay and receipt for the selected workflow.",
        "constraints": [
            "Keep runtime control narrow.",
            "Stop before promotion.",
        ],
        "target_test_command": TARGET_TEST_COMMAND,
        "max_candidate_building_blocks": 2,
    }
    if include_evidence_paths:
        workflow_params["evidence_paths"] = [evidence_path]

    result = run_workflow_package(
        "workflow_package_to_composable_building_blocks",
        provider=provider,
        options=RunnerOptions(
            root=tmp_path,
            task_id=TASK_ID,
            message="Decompose the release workflow into reusable building blocks.",
            workflow_params=workflow_params,
        ),
    )

    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    workflow_pkg = importlib.import_module("workflows.workflow_package_to_composable_building_blocks.workflow")

    task_dir = tmp_path / ".autoloop" / "tasks" / TASK_ID
    workflow_dir = task_dir / "wf_workflow_package_to_composable_building_blocks"
    run_dir = next((workflow_dir / "runs").iterdir())
    publish_context = _build_publish_context(
        root=tmp_path,
        task_dir=task_dir,
        workflow_dir=workflow_dir,
        run_dir=run_dir,
        state=result.state,
    )
    return SimpleNamespace(
        provider=provider,
        result=result,
        workflow_pkg=workflow_pkg,
        task_dir=task_dir,
        workflow_dir=workflow_dir,
        run_dir=run_dir,
        publish_context=publish_context,
        source_snapshot=source_snapshot,
    )


def _install_repo_workflow_package_to_composable_building_blocks(root: Path) -> None:
    workflows_root = root / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    (workflows_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    _clear_workflow_modules()
    importlib.invalidate_caches()

    for package_name in (
        "workflow_package_to_composable_building_blocks",
        "release_candidate_to_go_no_go",
    ):
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
    runtime_tests_root = root / "tests" / "runtime"
    runtime_tests_root.mkdir(parents=True, exist_ok=True)
    (runtime_tests_root / "test_release_candidate_to_go_no_go.py").write_text(
        (REPO_ROOT / "tests" / "runtime" / "test_release_candidate_to_go_no_go.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def _write_decomposition_evidence(root: Path) -> str:
    evidence_root = root / ".autoloop" / "signals"
    evidence_root.mkdir(parents=True, exist_ok=True)
    pressure_path = evidence_root / "release_decomposition_pressure.md"
    pressure_path.write_text(
        "\n".join(
            (
                "# Release Workflow Decomposition Pressure",
                "",
                "- Evidence capture keeps reappearing in release-focused workflows and follow-on planning packages.",
                f"- `{BUILDING_BLOCK_NAME}` is the strongest first extraction because it can publish reusable evidence artifacts before release assessment.",
                "- Keep the parent workflow candidate-only until explicit promotion proof exists.",
                "",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return ".autoloop/signals/release_decomposition_pressure.md"


def _write_candidate_decomposition_surface(request) -> str:
    candidate_root = request.artifacts.candidate_decomposition_surface.path
    baseline_root = request.artifacts.baseline_parent_workflow_surface.path
    shutil.rmtree(candidate_root, ignore_errors=True)
    shutil.copytree(baseline_root, candidate_root)

    candidate_prompt = candidate_root / PARENT_PROMPT_RELATIVE_PATH
    candidate_doc = candidate_root / PARENT_DOC_RELATIVE_PATH
    candidate_prompt.write_text(
        candidate_prompt.read_text(encoding="utf-8").rstrip()
        + f"\n- Candidate decomposition note: reference `{BUILDING_BLOCK_NAME}` as the reusable evidence stage before assessment.\n",
        encoding="utf-8",
    )
    candidate_doc.write_text(
        candidate_doc.read_text(encoding="utf-8").rstrip()
        + f"\n\nCandidate decomposition note: `{BUILDING_BLOCK_NAME}` is the extracted reusable evidence stage for later promotion.\n",
        encoding="utf-8",
    )

    building_block_root = candidate_root / BUILDING_BLOCK_ROOT
    (building_block_root / "prompts").mkdir(parents=True, exist_ok=True)
    (building_block_root / "assets").mkdir(parents=True, exist_ok=True)
    (candidate_root / "docs" / "workflows").mkdir(parents=True, exist_ok=True)
    (candidate_root / "tests" / "runtime").mkdir(parents=True, exist_ok=True)

    (building_block_root / "__init__.py").write_text(
        "from .workflow import ReleaseDecisionEvidencePack\n\n__all__ = [\"ReleaseDecisionEvidencePack\"]\n",
        encoding="utf-8",
    )
    (building_block_root / "workflow.toml").write_text(
        "\n".join(
            (
                f'name = "{BUILDING_BLOCK_NAME}"',
                'title = "Release Decision Evidence Pack"',
                'description = "Package release decision evidence into a reusable building-block workflow."',
                'aliases = ["release-decision-evidence-pack"]',
                "",
            )
        ),
        encoding="utf-8",
    )
    (building_block_root / "workflow.py").write_text(
        "\n".join(
            (
                '"""Candidate release-decision evidence building block."""',
                "",
                "from __future__ import annotations",
                "",
                "from pydantic import BaseModel",
                "",
                "from workflow import Artifact, SUCCESS, SystemStep, Workflow",
                "from workflow.primitives import Event",
                "",
                "",
                "class ReleaseDecisionEvidencePack(Workflow):",
                f'    name = "{BUILDING_BLOCK_NAME}"',
                "",
                "    class State(BaseModel):",
                "        packaged: bool = False",
                "",
                '    request = Artifact("{run_folder}/request.md")',
                '    evidence_package = Artifact("{workflow_folder}/release_evidence_package.md")',
                "",
                "    bootstrap = SystemStep(",
                '        name="bootstrap",',
                "        requires=[request],",
                '        produces={"evidence_package": evidence_package},',
                "    )",
                "",
                "    entry = bootstrap",
                '    transitions = {bootstrap: {"package_ready": SUCCESS}}',
                "",
                "    @staticmethod",
                "    def on_bootstrap(state: State, ctx) -> tuple[State, Event]:",
                '        artifact_path = ctx.workflow_folder / "release_evidence_package.md"',
                '        artifact_path.write_text("# Release Evidence Package\\n\\nCandidate reusable evidence package.\\n", encoding="utf-8")',
                '        return state.model_copy(update={"packaged": True}), Event("package_ready")',
                "",
                "",
                '__all__ = ["ReleaseDecisionEvidencePack"]',
                "",
            )
        ),
        encoding="utf-8",
    )
    (building_block_root / "prompts" / "README.md").write_text(
        "# Release Decision Evidence Pack Prompts\n\nThis candidate building block currently uses a deterministic system step and ships no provider prompts yet.\n",
        encoding="utf-8",
    )
    (building_block_root / "assets" / f"{BUILDING_BLOCK_NAME}_checklist.md").write_text(
        "# Release Decision Evidence Pack Checklist\n\n- Capture release evidence inputs.\n- Publish reusable evidence artifacts.\n",
        encoding="utf-8",
    )
    (candidate_root / BUILDING_BLOCK_DOC_RELATIVE_PATH).write_text(
        "# `release_decision_evidence_pack`\n\nCandidate reusable building block for packaging release decision evidence before release assessment.\n",
        encoding="utf-8",
    )
    (candidate_root / BUILDING_BLOCK_TEST_RELATIVE_PATH).write_text(
        "\n".join(
            (
                "from __future__ import annotations",
                "",
                "import importlib",
                "import sys",
                "from pathlib import Path",
                "",
                "from autoloop_v3.core.compiler import compile_workflow",
                "from autoloop_v3.runtime.loader import discover_workflow_packages, resolve_workflow_reference",
                "",
                "",
                "def _clear_workflow_modules() -> None:",
                "    for name in list(sys.modules):",
                '        if name == "workflows" or name.startswith("workflows."):',
                "            sys.modules.pop(name, None)",
                "",
                "",
                "def test_release_decision_evidence_pack_is_discoverable() -> None:",
                "    root = Path(__file__).resolve().parents[2]",
                '    discovered = {package.workflow_name: package for package in discover_workflow_packages(root)}',
                f'    assert "{BUILDING_BLOCK_NAME}" in discovered',
                "",
                "",
                "def test_release_decision_evidence_pack_compiles() -> None:",
                "    root = Path(__file__).resolve().parents[2]",
                "    _clear_workflow_modules()",
                "    importlib.invalidate_caches()",
                f'    workflow_pkg = importlib.import_module("workflows.{BUILDING_BLOCK_NAME}")',
                f'    resolved = resolve_workflow_reference(root, workflow_pkg.ReleaseDecisionEvidencePack)',
                "    compiled = compile_workflow(resolved.workflow_cls)",
                f'    assert compiled.workflow_name == "{BUILDING_BLOCK_NAME}"',
                '    assert compiled.entry_step_name == "bootstrap"',
                "",
            )
        ),
        encoding="utf-8",
    )

    request.artifacts.candidate_building_block_index.write_text(
        json.dumps(
            {
                "selected_workflow_name": "release_candidate_to_go_no_go",
                "publication_mode": "candidate_only",
                "promotion_required": True,
                "building_blocks": [
                    {
                        "workflow_name": BUILDING_BLOCK_NAME,
                        "package_name": BUILDING_BLOCK_NAME,
                        "package_root_relative_path": BUILDING_BLOCK_ROOT,
                        "doc_relative_path": BUILDING_BLOCK_DOC_RELATIVE_PATH,
                        "runtime_test_relative_path": BUILDING_BLOCK_TEST_RELATIVE_PATH,
                        "objective": "Package release decision evidence into a reusable building-block workflow.",
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    request.artifacts.decomposition_build_report.write_text(
        "\n".join(
            (
                "# Decomposition Build Report",
                "",
                f"- Updated `{PARENT_PROMPT_RELATIVE_PATH}` inside `candidate_decomposition_surface/`.",
                f"- Updated `{PARENT_DOC_RELATIVE_PATH}` inside `candidate_decomposition_surface/`.",
                f"- Added the candidate building block package `{BUILDING_BLOCK_NAME}` with docs and runtime proof.",
                "- Kept the authoritative selected workflow package unchanged.",
                "- Left deterministic manifest derivation and overlay validation to later workflow steps.",
                "",
            )
        )
        + "\n"
    )
    request.artifacts.candidate_diff_summary.write_text(
        "\n".join(
            (
                "# Candidate Diff Summary",
                "",
                f"- `{PARENT_PROMPT_RELATIVE_PATH}`: point the parent evidence stage at `{BUILDING_BLOCK_NAME}`.",
                f"- `{PARENT_DOC_RELATIVE_PATH}`: document the candidate extraction and migration boundary.",
                f"- `{BUILDING_BLOCK_ROOT}`: new reusable evidence-pack building block candidate with docs and runtime proof.",
                "",
            )
        )
        + "\n"
    )
    return "implemented candidate decomposition\n"


def _candidate_file_count(surface_root: Path) -> int:
    return sum(1 for path in surface_root.rglob("*") if path.is_file())


def _build_publish_context(
    *,
    root: Path,
    task_dir: Path,
    workflow_dir: Path,
    run_dir: Path,
    state,
) -> Context:
    return Context(
        task_id=TASK_ID,
        run_id=run_dir.name,
        workflow_name="workflow_package_to_composable_building_blocks",
        task_folder=task_dir,
        workflow_folder=workflow_dir,
        run_folder=run_dir,
        package_folder=root / "workflows" / "workflow_package_to_composable_building_blocks",
        state=state,
        session_store=InMemorySessionStore(),
        workflow_params={},
        workflow_invoker=None,
        answer=None,
    )
