from __future__ import annotations

from botlane.core.outcome_contract import NATIVE_SCHEMA_HAS_OPEN_OBJECT, ProviderOutcomeContract

from tests.unit._stdlib_and_extensions_shared import (
    _assert_mapping_contains,
    _build_lifecycle_context,
    _write_catalog_workflow,
    _write_run_history_record,
    _write_runtime_valid_catalog_workflow,
    _write_single_file_runtime_workflow,
)
from tests.unit._stdlib_and_extensions_shared import *

def test_adaptation_helpers_snapshot_one_selected_workflow_without_importing_unrelated_packages(tmp_path: Path) -> None:
    ctx = _build_lifecycle_context(tmp_path, workflow_name="candidate_workflow_to_adapted_execution_plan")
    _write_runtime_valid_catalog_workflow(
        tmp_path,
        "release_candidate_to_go_no_go",
        aliases=("release_decision",),
        export_parameters=True,
        write_doc=True,
    )
    broken_package = _write_catalog_workflow(
        tmp_path,
        "broken_workflow",
        aliases=("broken",),
        export_parameters=True,
        write_doc=True,
    )
    (broken_package / "workflow.py").write_text(
        'raise RuntimeError("selected adaptation helper imported an unrelated workflow")\n',
        encoding="utf-8",
    )

    snapshot_path = write_selected_workflow_capability_snapshot(
        ctx,
        "release_decision",
        "selected/selected_workflow_capability.json",
    )

    assert snapshot_path == ctx.workflow_folder / "selected" / "selected_workflow_capability.json"
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert payload["repo_root"] == str(tmp_path.resolve())
    assert payload["run_id"] == "run-1"
    assert payload["selected_workflow_name"] == "release_candidate_to_go_no_go"
    assert payload["task_id"] == "task-1"
    assert payload["workflow_name"] == "candidate_workflow_to_adapted_execution_plan"
    capability = payload["selected_workflow_capability"]
    _assert_mapping_contains(
        capability,
        {
            "aliases": ["release_decision"],
            "authoring_shape": "manifest_package",
            "description": "Workflow description.",
            "doc_path": str(tmp_path / "docs" / "workflows" / "release_candidate_to_go_no_go.md"),
            "entry_step_name": "assess",
            "manifest_path": str(tmp_path / "workflows" / "release_candidate_to_go_no_go" / "workflow.toml"),
            "package_dir": str(tmp_path / "workflows" / "release_candidate_to_go_no_go"),
            "package_name": "release_candidate_to_go_no_go",
            "parameters_model": "workflows.release_candidate_to_go_no_go.params.Params",
            "parameters_supported": True,
            "params_path": str(tmp_path / "workflows" / "release_candidate_to_go_no_go" / "params.py"),
            "source_path": str(tmp_path / "workflows" / "release_candidate_to_go_no_go" / "workflow.py"),
            "state_model": "workflows.release_candidate_to_go_no_go.workflow.ReleaseCandidateToGoNoGo.State",
            "title": "Release Candidate To Go No Go",
            "workflow_class": "ReleaseCandidateToGoNoGo",
            "workflow_name": "release_candidate_to_go_no_go",
            "workflow_path": str(tmp_path / "workflows" / "release_candidate_to_go_no_go" / "workflow.py"),
        },
    )
    assert capability["parameters"] == [
        {
            "default": "strict",
            "name": "mode",
            "repeated": False,
            "required": False,
            "type": "str",
        },
        {
            "default": "<factory>",
            "name": "reviewers",
            "repeated": True,
            "required": False,
            "type": "list[str]",
        },
    ]
    assert capability["prompt_paths"] == [
        str(tmp_path / "workflows" / "release_candidate_to_go_no_go" / "prompts" / "assess_producer.md"),
        str(tmp_path / "workflows" / "release_candidate_to_go_no_go" / "prompts" / "assess_verifier.md"),
    ]
    assert capability["global_routes"] == {}
    assert capability["routes"] == {
        "global": {},
        "steps": {
            "assess": {
                "assessment_complete": "FINISH",
                "needs_rework": "assess",
                "question": "AWAIT_INPUT",
            }
        },
    }
    assert len(capability["steps"]) == 1
    _assert_mapping_contains(
        capability["steps"][0],
        {
            "available_routes": [
                "assessment_complete",
                "needs_rework",
                "question",
            ],
            "authored_routes": ["assessment_complete", "needs_rework"],
            "has_expected_output_schema": True,
            "typed_output_schema": {
                "properties": {
                    "summary": {
                        "minLength": 1,
                        "title": "Summary",
                        "type": "string",
                    }
                },
                "required": ["summary"],
                "title": "AssessmentPayload",
                "type": "object",
            },
            "kind": "produce_verify",
            "log_artifacts": [],
            "name": "assess",
            "provider_visible_routes_full_auto": [
                "assessment_complete",
                "needs_rework",
            ],
            "provider_visible_routes_interactive": [
                "assessment_complete",
                "needs_rework",
                "question",
            ],
            "producer_prompt": "prompts/assess_producer.md",
            "reads": [],
            "requires": [],
            "runtime_control_routes": ["question"],
            "routes": {
                "assessment_complete": {
                    "handoff": None,
                    "is_runtime_control": False,
                    "on_taken": None,
                    "provider_visible": True,
                    "provider_visible_full_auto": True,
                    "provider_visible_interactive": True,
                    "required_writes": ["assess.assessment_note"],
                    "summary": "The workflow assessment package is complete.",
                    "target": "FINISH",
                },
                "needs_rework": {
                    "handoff": None,
                    "is_runtime_control": False,
                    "on_taken": None,
                    "provider_visible": True,
                    "provider_visible_full_auto": True,
                    "provider_visible_interactive": True,
                    "required_writes": ["assess.assessment_note"],
                    "summary": "The same workflow assessment needs local repair.",
                    "target": "assess",
                },
                "question": {
                    "handoff": None,
                    "is_runtime_control": True,
                    "on_taken": None,
                    "provider_visible": True,
                    "provider_visible_full_auto": False,
                    "provider_visible_interactive": True,
                    "required_writes": [],
                    "summary": "Clarification or user-input request.",
                    "target": "AWAIT_INPUT",
                },
            },
            "session_name": None,
            "verifier_prompt": "prompts/assess_verifier.md",
            "writes": ["assess.assessment_note"],
        },
    )

    with pytest.raises(ValueError, match="ctx.workflow_folder"):
        write_selected_workflow_capability_snapshot(ctx, "release_decision", "../escape.json")
    with pytest.raises(ValueError, match="\\.json"):
        write_selected_workflow_capability_snapshot(ctx, "release_decision", "selected.md")
def test_shared_selected_workflow_helper_reuses_one_capture_and_envelope_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _build_lifecycle_context(tmp_path, workflow_name="workflow_to_eval_suite")
    _write_runtime_valid_catalog_workflow(
        tmp_path,
        "release_candidate_to_go_no_go",
        aliases=("release_decision",),
        export_parameters=True,
        write_doc=True,
    )
    resolve_calls: list[tuple[Path, str | type[object]]] = []
    inspect_calls: list[tuple[Path, str | type[object]]] = []
    original_resolve = selected_workflow_helpers.resolve_workflow_reference
    original_inspect = selected_workflow_helpers.inspect_workflow_reference

    def _record_resolve(root, workflow):
        resolve_calls.append((Path(root), workflow))
        return original_resolve(root, workflow)

    def _record_inspect(root, workflow):
        inspect_calls.append((Path(root), workflow))
        return original_inspect(root, workflow)

    monkeypatch.setattr(selected_workflow_helpers, "resolve_workflow_reference", _record_resolve)
    monkeypatch.setattr(selected_workflow_helpers, "inspect_workflow_reference", _record_inspect)

    inspection = selected_workflow_helpers.inspect_selected_workflow(ctx, "release_decision")
    artifact = selected_workflow_helpers.write_selected_workflow_artifact(
        ctx,
        capture=inspection.capture,
        relative_path="shared/selected_workflow_capability.json",
        artifact_name="selected_workflow_capability",
        artifact_payload=selected_workflow_capability_payload(inspection.capability),
    )

    assert resolve_calls == [(tmp_path.resolve(), "release_decision")]
    workflow_cls = resolve_workflow_reference(tmp_path, "release_decision").workflow_cls
    assert inspect_calls == [(tmp_path.resolve(), workflow_cls)]
    assert inspection.capture.selected_workflow_name == "release_candidate_to_go_no_go"
    assert artifact.capture == inspection.capture
    assert artifact.path == ctx.workflow_folder / "shared" / "selected_workflow_capability.json"
    assert json.loads(artifact.path.read_text(encoding="utf-8")) == {
        "repo_root": str(tmp_path.resolve()),
        "run_id": "run-1",
        "selected_workflow_capability": selected_workflow_capability_payload(inspection.capability),
        "selected_workflow_name": "release_candidate_to_go_no_go",
        "task_id": "task-1",
        "workflow_name": "workflow_to_eval_suite",
    }
def test_shared_selected_workflow_capture_can_drive_multiple_writes_without_re_resolving(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _build_lifecycle_context(tmp_path, workflow_name="workflow_to_eval_suite")
    _write_runtime_valid_catalog_workflow(
        tmp_path,
        "release_candidate_to_go_no_go",
        aliases=("release_decision",),
        export_parameters=True,
    )
    resolve_calls: list[tuple[Path, str | type[object]]] = []
    original_resolve = selected_workflow_helpers.resolve_workflow_reference

    def _record_resolve(root, workflow):
        resolve_calls.append((Path(root), workflow))
        return original_resolve(root, workflow)

    monkeypatch.setattr(selected_workflow_helpers, "resolve_workflow_reference", _record_resolve)

    capture = selected_workflow_helpers.capture_selected_workflow(ctx, "release_decision")
    capability_artifact = selected_workflow_helpers.write_selected_workflow_artifact(
        ctx,
        capture=capture,
        relative_path="shared/selected_workflow_capability.json",
        artifact_name="selected_workflow_capability",
        artifact_payload={"workflow_name": capture.selected_workflow_name},
    )
    parameter_artifact = selected_workflow_helpers.write_selected_workflow_artifact(
        ctx,
        capture=capture,
        relative_path="shared/validated_workflow_parameters.json",
        artifact_name="validated_parameters",
        artifact_payload={"mode": "review"},
    )

    assert resolve_calls == [(tmp_path.resolve(), "release_decision")]
    assert capability_artifact.capture == capture
    assert parameter_artifact.capture == capture
    assert json.loads(capability_artifact.path.read_text(encoding="utf-8")) == {
        "repo_root": str(tmp_path.resolve()),
        "run_id": "run-1",
        "selected_workflow_capability": {"workflow_name": "release_candidate_to_go_no_go"},
        "selected_workflow_name": "release_candidate_to_go_no_go",
        "task_id": "task-1",
        "workflow_name": "workflow_to_eval_suite",
    }
    assert json.loads(parameter_artifact.path.read_text(encoding="utf-8")) == {
        "repo_root": str(tmp_path.resolve()),
        "run_id": "run-1",
        "selected_workflow_name": "release_candidate_to_go_no_go",
        "task_id": "task-1",
        "validated_parameters": {"mode": "review"},
        "workflow_name": "workflow_to_eval_suite",
    }
def test_adaptation_helpers_delegate_parameter_validation_to_shared_loader_coercion_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _build_lifecycle_context(tmp_path, workflow_name="candidate_workflow_to_adapted_execution_plan")
    _write_runtime_valid_catalog_workflow(
        tmp_path,
        "release_candidate_to_go_no_go",
        aliases=("release_decision",),
        export_parameters=True,
    )
    calls: list[tuple[type[object] | None, dict[str, object]]] = []
    original = adaptation_helpers.coerce_workflow_parameter_mapping

    def _record(parameters_cls, raw_values):
        payload = dict(raw_values or {})
        calls.append((parameters_cls, payload))
        return original(parameters_cls, raw_values)

    monkeypatch.setattr(adaptation_helpers, "coerce_workflow_parameter_mapping", _record)

    validated_path = write_validated_workflow_parameters(
        ctx,
        "release_decision",
        {"mode": "review", "reviewers": ["ops", "qa"]},
        "selected/validated_workflow_parameters.json",
    )

    assert len(calls) == 1
    assert calls[0][0] is not None
    assert calls[0][1] == {"mode": "review", "reviewers": ["ops", "qa"]}
    assert validated_path == ctx.workflow_folder / "selected" / "validated_workflow_parameters.json"
    assert json.loads(validated_path.read_text(encoding="utf-8")) == {
        "repo_root": str(tmp_path.resolve()),
        "run_id": "run-1",
        "selected_workflow_name": "release_candidate_to_go_no_go",
        "task_id": "task-1",
        "validated_parameters": {
            "mode": "review",
            "reviewers": ["ops", "qa"],
        },
        "workflow_name": "candidate_workflow_to_adapted_execution_plan",
    }

    with pytest.raises(ValueError, match="ctx.workflow_folder"):
        write_validated_workflow_parameters(ctx, "release_decision", {"mode": "review"}, "../escape.json")
    with pytest.raises(ValueError, match="\\.json"):
        write_validated_workflow_parameters(ctx, "release_decision", {"mode": "review"}, "selected.md")
def test_adaptation_helpers_preserve_shared_loader_failure_for_unknown_workflow_parameters(tmp_path: Path) -> None:
    ctx = _build_lifecycle_context(tmp_path, workflow_name="candidate_workflow_to_adapted_execution_plan")
    _write_runtime_valid_catalog_workflow(
        tmp_path,
        "release_candidate_to_go_no_go",
        aliases=("release_decision",),
        export_parameters=True,
    )

    with pytest.raises(WorkflowParameterError, match=r"unknown workflow parameter 'unexpected'"):
        write_validated_workflow_parameters(
            ctx,
            "release_decision",
            {"unexpected": "value"},
            "selected/validated_workflow_parameters.json",
        )
def test_adaptation_helpers_accept_single_file_workflow_references(tmp_path: Path) -> None:
    ctx = _build_lifecycle_context(tmp_path, workflow_name="candidate_workflow_to_adapted_execution_plan")
    examples_dir = tmp_path / "examples"
    examples_dir.mkdir(parents=True, exist_ok=True)
    (examples_dir / "prompts").mkdir()
    (examples_dir / "prompts" / "ask.md").write_text("Ask for the release summary.\n", encoding="utf-8")
    workflow_path = examples_dir / "single_file_review.py"
    workflow_path.write_text(
        """
from __future__ import annotations

from pydantic import BaseModel

from botlane import Json, Prompt, Workflow, step


class ReviewPayload(BaseModel):
    summary: str


class SingleFileReview(Workflow):
    Params = None

    class State(BaseModel):
        summary: str = ""

    ask = step(
        prompt=Prompt.file("prompts/ask.md"),
        writes=[Json("review_note", ReviewPayload, path="{workflow_folder}/review_note.md")],
        control_schema=ReviewPayload,
    )
""".strip()
        + "\n",
        encoding="utf-8",
    )

    snapshot_path = write_selected_workflow_capability_snapshot(
        ctx,
        str(workflow_path),
        "selected/single_file_workflow_capability.json",
    )

    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    capability = payload["selected_workflow_capability"]

    assert payload["selected_workflow_name"] == "single_file_review"
    assert capability["authoring_shape"] == "single_file"
    assert capability["source_path"] == str(workflow_path)
    assert capability["manifest_path"] is None
    assert capability["package_dir"] == str(examples_dir)
    assert capability["package_init_path"] is None
    assert capability["prompt_paths"] == [str(examples_dir / "prompts" / "ask.md")]
    assert capability["parameters_supported"] is False
    assert capability["state_model"].endswith("SingleFileReview.State")
    assert capability["artifacts"] == [
        {
            "name": "ask.review_note",
            "producer_steps": ["ask"],
            "template": "{workflow_folder}/review_note.md",
            "workflow_level": False,
        }
    ]
def test_core_selected_workflow_payload_builders_preserve_authoring_and_decomposition_contract_shapes(
    tmp_path: Path,
) -> None:
    package_dir = _write_runtime_valid_catalog_workflow(
        tmp_path,
        "release_candidate_to_go_no_go",
        aliases=("release_decision",),
        export_parameters=True,
        write_doc=True,
    )
    (package_dir / "contracts.py").write_text("# workflow contracts\n", encoding="utf-8")
    (package_dir / "prompts" / "repair").mkdir(parents=True, exist_ok=True)
    (package_dir / "prompts" / "repair" / "strategy.md").write_text("Repair the workflow.\n", encoding="utf-8")
    (package_dir / "assets" / "templates").mkdir(parents=True, exist_ok=True)
    (package_dir / "assets" / "checklist.md").write_text("Checklist.\n", encoding="utf-8")
    (package_dir / "assets" / "templates" / "rollback.txt").write_text("Rollback.\n", encoding="utf-8")
    runtime_test = tmp_path / "tests" / "runtime" / "test_release_candidate_to_go_no_go.py"
    runtime_test.parent.mkdir(parents=True, exist_ok=True)
    runtime_test.write_text("def test_placeholder():\n    assert True\n", encoding="utf-8")

    capability = inspect_workflow_reference(tmp_path, "release_decision")
    capability_payload = selected_workflow_capability_payload(capability)
    authoring_surface = selected_workflow_authoring_surface_payload(capability)
    decomposition_surface = selected_workflow_decomposition_surface_payload(capability, repo_root=tmp_path)
    decomposition_authoring_surface = decomposition_surface["selected_workflow_authoring_surface"]

    assert capability_payload["workflow_name"] == "release_candidate_to_go_no_go"
    assert capability_payload["package_name"] == "release_candidate_to_go_no_go"
    assert REMOVED_CONTRACTS_PATH not in capability_payload
    assert capability_payload["workflow_py_path"] == str(package_dir / "workflow.py")
    assert REMOVED_WORKFLOW_PY_FIELD not in capability_payload
    assert capability_payload["prompt_paths"] == [
        str(package_dir / "prompts" / "assess_producer.md"),
        str(package_dir / "prompts" / "assess_verifier.md"),
        str(package_dir / "prompts" / "repair" / "strategy.md"),
    ]
    assert capability_payload["spec_paths"] == [str(package_dir / "contracts.py")]
    assert capability_payload["steps"][0]["reads"] == []
    assert capability_payload["steps"][0]["requires"] == []
    assert capability_payload["steps"][0]["writes"] == ["assess.assessment_note"]
    assert capability_payload["steps"][0]["log_artifacts"] == []

    assert authoring_surface["workflow_name"] == "release_candidate_to_go_no_go"
    assert authoring_surface["package_name"] == "release_candidate_to_go_no_go"
    assert authoring_surface["runtime_test_path"] == str(runtime_test)
    assert authoring_surface["workflow_py_path"] == str(package_dir / "workflow.py")
    assert REMOVED_CONTRACTS_PATH not in authoring_surface
    assert REMOVED_WORKFLOW_PY_FIELD not in authoring_surface
    assert authoring_surface["spec_paths"] == [str(package_dir / "contracts.py")]
    assert authoring_surface["editable_paths"] == sorted(
        [
            str(package_dir / "__init__.py"),
            str(package_dir / "workflow.toml"),
            str(package_dir / "workflow.py"),
            str(package_dir / "params.py"),
            str(package_dir / "contracts.py"),
            str(package_dir / "prompts" / "assess_producer.md"),
            str(package_dir / "prompts" / "assess_verifier.md"),
            str(package_dir / "prompts" / "repair" / "strategy.md"),
            str(package_dir / "assets" / "checklist.md"),
            str(package_dir / "assets" / "templates" / "rollback.txt"),
            str(tmp_path / "docs" / "workflows" / "release_candidate_to_go_no_go.md"),
            str(runtime_test),
        ]
    )

    assert "workflow_name" not in decomposition_authoring_surface
    assert "package_name" not in decomposition_authoring_surface
    assert REMOVED_CONTRACTS_PATH not in decomposition_authoring_surface
    assert REMOVED_CONTRACTS_PATH_REPO_RELATIVE not in decomposition_authoring_surface
    assert decomposition_authoring_surface["workflow_py_path"] == str(package_dir / "workflow.py")
    assert (
        decomposition_authoring_surface["workflow_py_path_repo_relative"]
        == "botlane/workflows/release_candidate_to_go_no_go/workflow.py"
    )
    assert REMOVED_WORKFLOW_PY_FIELD not in decomposition_authoring_surface
    assert (
        decomposition_authoring_surface["workflow_path_repo_relative"]
        == "botlane/workflows/release_candidate_to_go_no_go/workflow.py"
    )
    assert decomposition_authoring_surface["runtime_test_path_repo_relative"] == (
        "tests/runtime/test_release_candidate_to_go_no_go.py"
    )
    assert decomposition_surface["selected_workflow_identity"] == {
        "aliases": ["release_decision"],
        "description": "Workflow description.",
        "package_name": "release_candidate_to_go_no_go",
        "title": "Release Candidate To Go No Go",
        "workflow_class": "ReleaseCandidateToGoNoGo",
        "workflow_name": "release_candidate_to_go_no_go",
    }
    assert decomposition_surface["selected_workflow_compiled_surface"]["parameters"] == [
        {
            "default": "strict",
            "name": "mode",
            "repeated": False,
            "required": False,
            "type": "str",
        },
        {
            "default": "<factory>",
            "name": "reviewers",
            "repeated": True,
            "required": False,
            "type": "list[str]",
        },
    ]
    assess_capability = next(step for step in capability_payload["steps"] if step["name"] == "assess")
    compiled_assess = decomposition_surface["selected_workflow_compiled_surface"]["steps"][0]

    assert capability_payload["compiled_global_routes"] == {}
    assert "question" in assess_capability["compiled_route_tags"]
    assert assess_capability["suppressed_route_tags"] == []
    assert assess_capability["provider_response_contracts"]["interactive"]["schema_delivery_mode"] == "prompt_only"
    assert assess_capability["provider_response_contracts"]["interactive"]["native_skip_reason"] == NATIVE_SCHEMA_HAS_OPEN_OBJECT
    assert assess_capability["provider_response_contracts"]["full_auto"]["schema_delivery_mode"] == "prompt_only"
    assert assess_capability["compiled_routes"]["question"]["payload_contract"]["mode"] == "inherit"
    assert assess_capability["compiled_routes"]["question"]["payload_contract"]["source"] == "step_expected_output"
    assert assess_capability["compiled_routes"]["question"]["route_fields_contract"]["source"] == "route"
    assert assess_capability["compiled_routes"]["question"]["preset_kind"] == "question"
    assert assess_capability["compiled_routes"]["question"]["inheritance_source"] == "framework_default"
    assert assess_capability["compiled_routes"]["question"]["available"] is True
    assert decomposition_surface["selected_workflow_compiled_surface"]["compiled_global_routes"] == {}
    assert "question" in compiled_assess["compiled_route_tags"]
    assert compiled_assess["provider_response_contracts"]["interactive"]["schema_delivery_mode"] == "prompt_only"
    assert compiled_assess["compiled_routes"]["question"]["payload_contract"]["mode"] == "inherit"
    assert compiled_assess["compiled_routes"]["question"]["payload_contract"]["source"] == "step_expected_output"
    assert compiled_assess["compiled_routes"]["question"]["route_fields_contract"]["source"] == "route"
    assert compiled_assess["compiled_routes"]["question"]["inheritance_source"] == "framework_default"
def test_selected_workflow_inspection_payloads_surface_prompt_only_provider_schema_delivery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_runtime_valid_catalog_workflow(
        tmp_path,
        "release_candidate_to_go_no_go",
        aliases=("release_decision",),
        export_parameters=True,
        write_doc=True,
    )

    fallback_schema = {
        "type": "object",
        "properties": {
            "outcome": {
                "type": "object",
                "properties": {
                    "tag": {"type": "string"},
                    "payload": {"type": "object", "additionalProperties": True},
                    "route_fields": {"type": "object", "additionalProperties": True},
                },
                "required": ["tag", "payload", "route_fields"],
                "additionalProperties": False,
            }
        },
        "required": ["outcome"],
        "additionalProperties": False,
    }

    def _force_prompt_only_contract(*, routes, expected_output_schema, max_chars=12_000):
        return ProviderOutcomeContract(
            prompt_schema=fallback_schema,
            native_schema=None,
            native_skip_reason=NATIVE_SCHEMA_HAS_OPEN_OBJECT,
        )

    monkeypatch.setattr(route_reporting_helpers, "build_provider_outcome_contract", _force_prompt_only_contract)

    capability = inspect_workflow_reference(tmp_path, "release_decision")
    capability_payload = selected_workflow_capability_payload(capability)
    decomposition_surface = selected_workflow_decomposition_surface_payload(capability, repo_root=tmp_path)

    assess_capability = next(step for step in capability_payload["steps"] if step["name"] == "assess")
    compiled_assess = decomposition_surface["selected_workflow_compiled_surface"]["steps"][0]

    assert assess_capability["provider_response_contracts"]["interactive"]["schema_delivery_mode"] == "prompt_only"
    assert assess_capability["provider_response_contracts"]["interactive"]["native_skip_reason"] == NATIVE_SCHEMA_HAS_OPEN_OBJECT
    assert assess_capability["provider_response_contracts"]["interactive"]["schema_fingerprint"] is not None
    assert assess_capability["provider_response_contracts"]["interactive"]["schema_chars"] > 0
    assert assess_capability["provider_response_contracts"]["full_auto"]["schema_delivery_mode"] == "prompt_only"
    assert compiled_assess["provider_response_contracts"]["interactive"]["schema_delivery_mode"] == "prompt_only"
    assert compiled_assess["provider_response_contracts"]["interactive"]["schema_fingerprint"] is not None
    assert compiled_assess["provider_response_contracts"]["interactive"]["schema_chars"] > 0
    assert compiled_assess["provider_response_contracts"]["full_auto"]["schema_delivery_mode"] == "prompt_only"
def test_refinement_helper_snapshots_selected_workflow_authoring_surface_via_shared_resolution_and_catalog_seams(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _build_lifecycle_context(tmp_path, workflow_name="workflow_and_eval_to_refined_workflow_package")
    package_dir = _write_runtime_valid_catalog_workflow(
        tmp_path,
        "release_candidate_to_go_no_go",
        aliases=("release_decision",),
        export_parameters=True,
        write_doc=True,
    )
    (package_dir / "contracts.py").write_text("# workflow contracts\n", encoding="utf-8")
    (package_dir / "prompts" / "repair").mkdir(parents=True, exist_ok=True)
    (package_dir / "prompts" / "repair" / "strategy.md").write_text("Repair the workflow.\n", encoding="utf-8")
    (package_dir / "assets" / "templates").mkdir(parents=True, exist_ok=True)
    (package_dir / "assets" / "checklist.md").write_text("Checklist.\n", encoding="utf-8")
    (package_dir / "assets" / "templates" / "rollback.txt").write_text("Rollback.\n", encoding="utf-8")
    runtime_test = tmp_path / "tests" / "runtime" / "test_release_candidate_to_go_no_go.py"
    runtime_test.parent.mkdir(parents=True, exist_ok=True)
    runtime_test.write_text("def test_placeholder():\n    assert True\n", encoding="utf-8")
    selected_workflow_folder = tmp_path / ".botlane" / "tasks" / "task-1" / "wf_release_candidate_to_go_no_go"
    before_surface_files = {
        str(path.relative_to(tmp_path)): path.read_text(encoding="utf-8")
        for path in (
            package_dir / "__init__.py",
            package_dir / "workflow.toml",
            package_dir / "workflow.py",
            package_dir / "params.py",
            package_dir / "contracts.py",
            package_dir / "prompts" / "assess_producer.md",
            package_dir / "prompts" / "assess_verifier.md",
            package_dir / "prompts" / "repair" / "strategy.md",
            package_dir / "assets" / "checklist.md",
            package_dir / "assets" / "templates" / "rollback.txt",
            tmp_path / "docs" / "workflows" / "release_candidate_to_go_no_go.md",
            runtime_test,
        )
    }
    resolve_calls: list[tuple[Path, str | type[object]]] = []
    inspect_calls: list[tuple[Path, str | type[object]]] = []
    original_resolve = selected_workflow_helpers.resolve_workflow_reference
    original_inspect = selected_workflow_helpers.inspect_workflow_reference

    def _record_resolve(root, workflow):
        resolve_calls.append((Path(root), workflow))
        return original_resolve(root, workflow)

    def _record_inspect(root, workflow):
        inspect_calls.append((Path(root), workflow))
        return original_inspect(root, workflow)

    monkeypatch.setattr(selected_workflow_helpers, "resolve_workflow_reference", _record_resolve)
    monkeypatch.setattr(selected_workflow_helpers, "inspect_workflow_reference", _record_inspect)

    snapshot_path = write_selected_workflow_authoring_surface(
        ctx,
        "release_decision",
        "refinement/selected_workflow_authoring_surface.json",
    )

    assert resolve_calls == [(tmp_path.resolve(), "release_decision")]
    workflow_cls = resolve_workflow_reference(tmp_path, "release_decision").workflow_cls
    assert inspect_calls == [(tmp_path.resolve(), workflow_cls)]
    assert snapshot_path == ctx.workflow_folder / "refinement" / "selected_workflow_authoring_surface.json"
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert payload["repo_root"] == str(tmp_path.resolve())
    assert payload["run_id"] == "run-1"
    assert payload["selected_workflow_name"] == "release_candidate_to_go_no_go"
    assert payload["task_id"] == "task-1"
    assert payload["workflow_name"] == "workflow_and_eval_to_refined_workflow_package"
    _assert_mapping_contains(
        payload["selected_workflow_authoring_surface"],
        {
            "asset_paths": [
                str(package_dir / "assets" / "checklist.md"),
                str(package_dir / "assets" / "templates" / "rollback.txt"),
            ],
            "doc_path": str(tmp_path / "docs" / "workflows" / "release_candidate_to_go_no_go.md"),
            "editable_paths": sorted(
                [
                    str(package_dir / "__init__.py"),
                    str(package_dir / "workflow.toml"),
                    str(package_dir / "workflow.py"),
                    str(package_dir / "params.py"),
                    str(package_dir / "contracts.py"),
                    str(package_dir / "prompts" / "assess_producer.md"),
                    str(package_dir / "prompts" / "assess_verifier.md"),
                    str(package_dir / "prompts" / "repair" / "strategy.md"),
                    str(package_dir / "assets" / "checklist.md"),
                    str(package_dir / "assets" / "templates" / "rollback.txt"),
                    str(tmp_path / "docs" / "workflows" / "release_candidate_to_go_no_go.md"),
                    str(runtime_test),
                ]
            ),
            "manifest_path": str(package_dir / "workflow.toml"),
            "package_dir": str(package_dir),
            "package_init_path": str(package_dir / "__init__.py"),
            "package_name": "release_candidate_to_go_no_go",
            "params_path": str(package_dir / "params.py"),
            "prompt_paths": [
                str(package_dir / "prompts" / "assess_producer.md"),
                str(package_dir / "prompts" / "assess_verifier.md"),
                str(package_dir / "prompts" / "repair" / "strategy.md"),
            ],
            "runtime_test_path": str(runtime_test),
            "spec_paths": [str(package_dir / "contracts.py")],
            "test_paths": [str(runtime_test)],
            "workflow_name": "release_candidate_to_go_no_go",
            "workflow_py_path": str(package_dir / "workflow.py"),
            "workflow_path": str(package_dir / "workflow.py"),
            "asset_paths_repo_relative": [
                "botlane/workflows/release_candidate_to_go_no_go/assets/checklist.md",
                "botlane/workflows/release_candidate_to_go_no_go/assets/templates/rollback.txt",
            ],
            "doc_path_repo_relative": "docs/workflows/release_candidate_to_go_no_go.md",
            "manifest_path_repo_relative": "botlane/workflows/release_candidate_to_go_no_go/workflow.toml",
            "package_dir_repo_relative": "botlane/workflows/release_candidate_to_go_no_go",
            "package_init_path_repo_relative": "botlane/workflows/release_candidate_to_go_no_go/__init__.py",
            "params_path_repo_relative": "botlane/workflows/release_candidate_to_go_no_go/params.py",
            "prompt_paths_repo_relative": [
                "botlane/workflows/release_candidate_to_go_no_go/prompts/assess_producer.md",
                "botlane/workflows/release_candidate_to_go_no_go/prompts/assess_verifier.md",
                "botlane/workflows/release_candidate_to_go_no_go/prompts/repair/strategy.md",
            ],
            "runtime_test_path_repo_relative": "tests/runtime/test_release_candidate_to_go_no_go.py",
            "spec_paths_repo_relative": ["botlane/workflows/release_candidate_to_go_no_go/contracts.py"],
            "test_paths_repo_relative": ["tests/runtime/test_release_candidate_to_go_no_go.py"],
            "workflow_py_path_repo_relative": "botlane/workflows/release_candidate_to_go_no_go/workflow.py",
            "workflow_path_repo_relative": "botlane/workflows/release_candidate_to_go_no_go/workflow.py",
        },
    )
    assert set(payload["selected_workflow_authoring_surface"]["editable_paths_repo_relative"]) == {
        "botlane/workflows/release_candidate_to_go_no_go/__init__.py",
        "botlane/workflows/release_candidate_to_go_no_go/workflow.toml",
        "botlane/workflows/release_candidate_to_go_no_go/workflow.py",
        "botlane/workflows/release_candidate_to_go_no_go/params.py",
        "botlane/workflows/release_candidate_to_go_no_go/contracts.py",
        "botlane/workflows/release_candidate_to_go_no_go/prompts/assess_producer.md",
        "botlane/workflows/release_candidate_to_go_no_go/prompts/assess_verifier.md",
        "botlane/workflows/release_candidate_to_go_no_go/prompts/repair/strategy.md",
        "botlane/workflows/release_candidate_to_go_no_go/assets/checklist.md",
        "botlane/workflows/release_candidate_to_go_no_go/assets/templates/rollback.txt",
        "docs/workflows/release_candidate_to_go_no_go.md",
        "tests/runtime/test_release_candidate_to_go_no_go.py",
    }
    assert not selected_workflow_folder.exists()
    assert {
        str(path.relative_to(tmp_path)): path.read_text(encoding="utf-8")
        for path in (
            package_dir / "__init__.py",
            package_dir / "workflow.toml",
            package_dir / "workflow.py",
            package_dir / "params.py",
            package_dir / "contracts.py",
            package_dir / "prompts" / "assess_producer.md",
            package_dir / "prompts" / "assess_verifier.md",
            package_dir / "prompts" / "repair" / "strategy.md",
            package_dir / "assets" / "checklist.md",
            package_dir / "assets" / "templates" / "rollback.txt",
            tmp_path / "docs" / "workflows" / "release_candidate_to_go_no_go.md",
            runtime_test,
        )
    } == before_surface_files

    with pytest.raises(ValueError, match="ctx.workflow_folder"):
        write_selected_workflow_authoring_surface(ctx, "release_decision", "../escape.json")
    with pytest.raises(ValueError, match="\\.json"):
        write_selected_workflow_authoring_surface(ctx, "release_decision", "surface.md")
def test_refinement_helper_keeps_optional_authoring_surface_paths_nullable_when_absent(tmp_path: Path) -> None:
    ctx = _build_lifecycle_context(tmp_path, workflow_name="workflow_and_eval_to_refined_workflow_package")
    package_dir = _write_runtime_valid_catalog_workflow(
        tmp_path,
        "release_candidate_to_go_no_go",
        aliases=("release_decision",),
    )

    snapshot_path = write_selected_workflow_authoring_surface(ctx, "release_decision")
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))

    assert payload["selected_workflow_authoring_surface"] == {
        "asset_paths": [],
        "asset_paths_repo_relative": [],
        "doc_path": None,
        "doc_path_repo_relative": None,
        "editable_paths": sorted(
            [
                str(package_dir / "__init__.py"),
                str(package_dir / "workflow.toml"),
                str(package_dir / "workflow.py"),
                str(package_dir / "prompts" / "assess_producer.md"),
                str(package_dir / "prompts" / "assess_verifier.md"),
            ]
        ),
        "editable_paths_repo_relative": sorted(
            [
                "workflows/release_candidate_to_go_no_go/__init__.py",
                "workflows/release_candidate_to_go_no_go/workflow.toml",
                "workflows/release_candidate_to_go_no_go/workflow.py",
                "workflows/release_candidate_to_go_no_go/prompts/assess_producer.md",
                "workflows/release_candidate_to_go_no_go/prompts/assess_verifier.md",
            ]
        ),
        "manifest_path": str(package_dir / "workflow.toml"),
        "manifest_path_repo_relative": "workflows/release_candidate_to_go_no_go/workflow.toml",
        "package_dir": str(package_dir),
        "package_dir_repo_relative": "workflows/release_candidate_to_go_no_go",
        "package_init_path": str(package_dir / "__init__.py"),
        "package_init_path_repo_relative": "workflows/release_candidate_to_go_no_go/__init__.py",
        "package_name": "release_candidate_to_go_no_go",
        "params_path": None,
        "params_path_repo_relative": None,
        "prompt_paths": [
            str(package_dir / "prompts" / "assess_producer.md"),
            str(package_dir / "prompts" / "assess_verifier.md"),
        ],
        "prompt_paths_repo_relative": [
            "workflows/release_candidate_to_go_no_go/prompts/assess_producer.md",
            "workflows/release_candidate_to_go_no_go/prompts/assess_verifier.md",
        ],
        "runtime_test_path": None,
        "runtime_test_path_repo_relative": None,
        "spec_paths": [],
        "spec_paths_repo_relative": [],
        "test_paths": [],
        "test_paths_repo_relative": [],
        "workflow_name": "release_candidate_to_go_no_go",
        "workflow_py_path": str(package_dir / "workflow.py"),
        "workflow_py_path_repo_relative": "workflows/release_candidate_to_go_no_go/workflow.py",
        "workflow_path": str(package_dir / "workflow.py"),
        "workflow_path_repo_relative": "workflows/release_candidate_to_go_no_go/workflow.py",
    }
def test_refinement_helper_accepts_main_workflow_class_references(tmp_path: Path) -> None:
    ctx = _build_lifecycle_context(tmp_path, workflow_name="workflow_and_eval_to_refined_workflow_package")
    package_dir = _write_runtime_valid_catalog_workflow(
        tmp_path,
        "release_candidate_to_go_no_go",
        aliases=("release_decision",),
        write_doc=True,
    )
    workflow_cls = resolve_workflow_reference(tmp_path, "release_decision").workflow_cls

    snapshot_path = write_selected_workflow_authoring_surface(
        ctx,
        workflow_cls,
        "refinement/selected_workflow_authoring_surface.json",
    )
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))

    assert snapshot_path == ctx.workflow_folder / "refinement" / "selected_workflow_authoring_surface.json"
    assert payload["selected_workflow_name"] == "release_candidate_to_go_no_go"
    _assert_mapping_contains(
        payload["selected_workflow_authoring_surface"],
        {
            "asset_paths": [],
            "asset_paths_repo_relative": [],
            "doc_path": str(tmp_path / "docs" / "workflows" / "release_candidate_to_go_no_go.md"),
            "doc_path_repo_relative": "docs/workflows/release_candidate_to_go_no_go.md",
            "editable_paths": sorted(
                [
                    str(package_dir / "__init__.py"),
                    str(package_dir / "workflow.toml"),
                    str(package_dir / "workflow.py"),
                    str(package_dir / "prompts" / "assess_producer.md"),
                    str(package_dir / "prompts" / "assess_verifier.md"),
                    str(tmp_path / "docs" / "workflows" / "release_candidate_to_go_no_go.md"),
                ]
            ),
            "manifest_path": str(package_dir / "workflow.toml"),
            "manifest_path_repo_relative": "botlane/workflows/release_candidate_to_go_no_go/workflow.toml",
            "package_dir": str(package_dir),
            "package_dir_repo_relative": "botlane/workflows/release_candidate_to_go_no_go",
            "package_init_path": str(package_dir / "__init__.py"),
            "package_init_path_repo_relative": "botlane/workflows/release_candidate_to_go_no_go/__init__.py",
            "package_name": "release_candidate_to_go_no_go",
            "params_path": None,
            "params_path_repo_relative": None,
            "prompt_paths": [
                str(package_dir / "prompts" / "assess_producer.md"),
                str(package_dir / "prompts" / "assess_verifier.md"),
            ],
            "prompt_paths_repo_relative": [
                "botlane/workflows/release_candidate_to_go_no_go/prompts/assess_producer.md",
                "botlane/workflows/release_candidate_to_go_no_go/prompts/assess_verifier.md",
            ],
            "runtime_test_path": None,
            "runtime_test_path_repo_relative": None,
            "spec_paths": [],
            "spec_paths_repo_relative": [],
            "test_paths": [],
            "test_paths_repo_relative": [],
            "workflow_name": "release_candidate_to_go_no_go",
            "workflow_py_path": str(package_dir / "workflow.py"),
            "workflow_py_path_repo_relative": "botlane/workflows/release_candidate_to_go_no_go/workflow.py",
            "workflow_path": str(package_dir / "workflow.py"),
            "workflow_path_repo_relative": "botlane/workflows/release_candidate_to_go_no_go/workflow.py",
        },
    )
    assert set(payload["selected_workflow_authoring_surface"]["editable_paths_repo_relative"]) == {
        "botlane/workflows/release_candidate_to_go_no_go/__init__.py",
        "botlane/workflows/release_candidate_to_go_no_go/workflow.toml",
        "botlane/workflows/release_candidate_to_go_no_go/workflow.py",
        "botlane/workflows/release_candidate_to_go_no_go/prompts/assess_producer.md",
        "botlane/workflows/release_candidate_to_go_no_go/prompts/assess_verifier.md",
        "docs/workflows/release_candidate_to_go_no_go.md",
    }
def test_decomposition_helper_writes_selected_workflow_identity_authoring_surface_and_compiled_routes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _build_lifecycle_context(tmp_path, workflow_name="workflow_package_to_composable_building_blocks")
    package_dir = _write_runtime_valid_catalog_workflow(
        tmp_path,
        "release_candidate_to_go_no_go",
        aliases=("release_decision",),
        export_parameters=True,
        write_doc=True,
    )
    (package_dir / "contracts.py").write_text("# workflow contracts\n", encoding="utf-8")
    (package_dir / "prompts" / "repair").mkdir(parents=True, exist_ok=True)
    (package_dir / "prompts" / "repair" / "strategy.md").write_text("Repair the workflow.\n", encoding="utf-8")
    (package_dir / "assets" / "templates").mkdir(parents=True, exist_ok=True)
    (package_dir / "assets" / "checklist.md").write_text("Checklist.\n", encoding="utf-8")
    (package_dir / "assets" / "templates" / "rollback.txt").write_text("Rollback.\n", encoding="utf-8")
    runtime_test = tmp_path / "tests" / "runtime" / "test_release_candidate_to_go_no_go.py"
    runtime_test.parent.mkdir(parents=True, exist_ok=True)
    runtime_test.write_text("def test_placeholder():\n    assert True\n", encoding="utf-8")
    before_surface_files = {
        str(path.relative_to(tmp_path)): path.read_text(encoding="utf-8")
        for path in (
            package_dir / "__init__.py",
            package_dir / "workflow.toml",
            package_dir / "workflow.py",
            package_dir / "params.py",
            package_dir / "contracts.py",
            package_dir / "prompts" / "assess_producer.md",
            package_dir / "prompts" / "assess_verifier.md",
            package_dir / "prompts" / "repair" / "strategy.md",
            package_dir / "assets" / "checklist.md",
            package_dir / "assets" / "templates" / "rollback.txt",
            tmp_path / "docs" / "workflows" / "release_candidate_to_go_no_go.md",
            runtime_test,
        )
    }
    resolve_calls: list[tuple[Path, str | type[object]]] = []
    inspect_calls: list[tuple[Path, str | type[object]]] = []
    original_resolve = selected_workflow_helpers.resolve_workflow_reference
    original_inspect = selected_workflow_helpers.inspect_workflow_reference

    def _record_resolve(root, workflow):
        resolve_calls.append((Path(root), workflow))
        return original_resolve(root, workflow)

    def _record_inspect(root, workflow):
        inspect_calls.append((Path(root), workflow))
        return original_inspect(root, workflow)

    monkeypatch.setattr(selected_workflow_helpers, "resolve_workflow_reference", _record_resolve)
    monkeypatch.setattr(selected_workflow_helpers, "inspect_workflow_reference", _record_inspect)

    snapshot_path = write_selected_workflow_decomposition_surface(
        ctx,
        "release_decision",
        "decomposition/selected_workflow_decomposition_surface.json",
    )

    workflow_cls = resolve_workflow_reference(tmp_path, "release_decision").workflow_cls
    assert resolve_calls == [(tmp_path.resolve(), "release_decision")]
    assert inspect_calls == [(tmp_path.resolve(), workflow_cls)]
    assert snapshot_path == ctx.workflow_folder / "decomposition" / "selected_workflow_decomposition_surface.json"
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert payload["repo_root"] == str(tmp_path.resolve())
    assert payload["run_id"] == "run-1"
    assert payload["selected_workflow_name"] == "release_candidate_to_go_no_go"
    assert payload["task_id"] == "task-1"
    assert payload["workflow_name"] == "workflow_package_to_composable_building_blocks"
    decomposition_surface = payload["selected_workflow_decomposition_surface"]
    _assert_mapping_contains(
        decomposition_surface["selected_workflow_authoring_surface"],
        {
            "asset_paths": [
                str(package_dir / "assets" / "checklist.md"),
                str(package_dir / "assets" / "templates" / "rollback.txt"),
            ],
            "asset_paths_repo_relative": [
                "botlane/workflows/release_candidate_to_go_no_go/assets/checklist.md",
                "botlane/workflows/release_candidate_to_go_no_go/assets/templates/rollback.txt",
            ],
            "doc_path": str(tmp_path / "docs" / "workflows" / "release_candidate_to_go_no_go.md"),
            "doc_path_repo_relative": "docs/workflows/release_candidate_to_go_no_go.md",
            "editable_paths": sorted(
                [
                    str(package_dir / "__init__.py"),
                    str(package_dir / "workflow.toml"),
                    str(package_dir / "workflow.py"),
                    str(package_dir / "params.py"),
                    str(package_dir / "contracts.py"),
                    str(package_dir / "prompts" / "assess_producer.md"),
                    str(package_dir / "prompts" / "assess_verifier.md"),
                    str(package_dir / "prompts" / "repair" / "strategy.md"),
                    str(package_dir / "assets" / "checklist.md"),
                    str(package_dir / "assets" / "templates" / "rollback.txt"),
                    str(tmp_path / "docs" / "workflows" / "release_candidate_to_go_no_go.md"),
                    str(runtime_test),
                ]
            ),
            "manifest_path": str(package_dir / "workflow.toml"),
            "manifest_path_repo_relative": "botlane/workflows/release_candidate_to_go_no_go/workflow.toml",
            "package_dir": str(package_dir),
            "package_dir_repo_relative": "botlane/workflows/release_candidate_to_go_no_go",
            "package_init_path": str(package_dir / "__init__.py"),
            "package_init_path_repo_relative": "botlane/workflows/release_candidate_to_go_no_go/__init__.py",
            "params_path": str(package_dir / "params.py"),
            "params_path_repo_relative": "botlane/workflows/release_candidate_to_go_no_go/params.py",
            "prompt_paths": [
                str(package_dir / "prompts" / "assess_producer.md"),
                str(package_dir / "prompts" / "assess_verifier.md"),
                str(package_dir / "prompts" / "repair" / "strategy.md"),
            ],
            "prompt_paths_repo_relative": [
                "botlane/workflows/release_candidate_to_go_no_go/prompts/assess_producer.md",
                "botlane/workflows/release_candidate_to_go_no_go/prompts/assess_verifier.md",
                "botlane/workflows/release_candidate_to_go_no_go/prompts/repair/strategy.md",
            ],
            "runtime_test_path": str(runtime_test),
            "runtime_test_path_repo_relative": "tests/runtime/test_release_candidate_to_go_no_go.py",
            "spec_paths": [str(package_dir / "contracts.py")],
            "spec_paths_repo_relative": ["botlane/workflows/release_candidate_to_go_no_go/contracts.py"],
            "test_paths": [str(runtime_test)],
            "test_paths_repo_relative": ["tests/runtime/test_release_candidate_to_go_no_go.py"],
            "workflow_py_path": str(package_dir / "workflow.py"),
            "workflow_py_path_repo_relative": "botlane/workflows/release_candidate_to_go_no_go/workflow.py",
            "workflow_path": str(package_dir / "workflow.py"),
            "workflow_path_repo_relative": "botlane/workflows/release_candidate_to_go_no_go/workflow.py",
        },
    )
    assert set(decomposition_surface["selected_workflow_authoring_surface"]["editable_paths_repo_relative"]) == {
        "botlane/workflows/release_candidate_to_go_no_go/__init__.py",
        "botlane/workflows/release_candidate_to_go_no_go/workflow.toml",
        "botlane/workflows/release_candidate_to_go_no_go/workflow.py",
        "botlane/workflows/release_candidate_to_go_no_go/params.py",
        "botlane/workflows/release_candidate_to_go_no_go/contracts.py",
        "botlane/workflows/release_candidate_to_go_no_go/prompts/assess_producer.md",
        "botlane/workflows/release_candidate_to_go_no_go/prompts/assess_verifier.md",
        "botlane/workflows/release_candidate_to_go_no_go/prompts/repair/strategy.md",
        "botlane/workflows/release_candidate_to_go_no_go/assets/checklist.md",
        "botlane/workflows/release_candidate_to_go_no_go/assets/templates/rollback.txt",
        "docs/workflows/release_candidate_to_go_no_go.md",
        "tests/runtime/test_release_candidate_to_go_no_go.py",
    }
    assert decomposition_surface["selected_workflow_identity"] == {
        "aliases": ["release_decision"],
        "description": "Workflow description.",
        "package_name": "release_candidate_to_go_no_go",
        "title": "Release Candidate To Go No Go",
        "workflow_class": "ReleaseCandidateToGoNoGo",
        "workflow_name": "release_candidate_to_go_no_go",
    }
    compiled_surface = decomposition_surface["selected_workflow_compiled_surface"]
    assert compiled_surface["artifacts"] == [
        {
            "name": "assess.assessment_note",
            "producer_steps": ["assess"],
            "template": "{workflow_folder}/assessment_note.md",
            "workflow_level": False,
        }
    ]
    assert compiled_surface["entry_step_name"] == "assess"
    assert compiled_surface["global_routes"] == {}
    assert compiled_surface["parameters"] == [
        {
            "default": "strict",
            "name": "mode",
            "repeated": False,
            "required": False,
            "type": "str",
        },
        {
            "default": "<factory>",
            "name": "reviewers",
            "repeated": True,
            "required": False,
            "type": "list[str]",
        },
    ]
    assert compiled_surface["parameters_supported"] is True
    assert compiled_surface["sessions"] == []
    assert compiled_surface["state_model"] == (
        "workflows.release_candidate_to_go_no_go.workflow.ReleaseCandidateToGoNoGo.State"
    )
    assert compiled_surface["step_count"] == 1
    _assert_mapping_contains(
        compiled_surface["steps"][0],
        {
            "available_routes": [
                "assessment_complete",
                "needs_rework",
                "question",
            ],
            "authored_routes": ["assessment_complete", "needs_rework"],
            "expected_output_schema": {
                "properties": {
                    "summary": {
                        "minLength": 1,
                        "title": "Summary",
                        "type": "string",
                    }
                },
                "required": ["summary"],
                "title": "AssessmentPayload",
                "type": "object",
            },
            "kind": "produce_verify",
            "log_artifacts": [],
            "name": "assess",
            "provider_visible_routes_full_auto": [
                "assessment_complete",
                "needs_rework",
            ],
            "provider_visible_routes_interactive": [
                "assessment_complete",
                "needs_rework",
                "question",
            ],
            "producer_prompt": "prompts/assess_producer.md",
            "producer_prompt_repo_relative": "workflows/release_candidate_to_go_no_go/prompts/assess_producer.md",
            "writes": ["assess.assessment_note"],
            "reads": [],
            "requires": [],
            "runtime_control_routes": ["question"],
            "routes": {
                "assessment_complete": {
                    "handoff": None,
                    "is_runtime_control": False,
                    "on_taken": None,
                    "provider_visible": True,
                    "provider_visible_full_auto": True,
                    "provider_visible_interactive": True,
                    "required_writes": ["assess.assessment_note"],
                    "summary": "The workflow assessment package is complete.",
                    "target": "FINISH",
                },
                "needs_rework": {
                    "handoff": None,
                    "is_runtime_control": False,
                    "on_taken": None,
                    "provider_visible": True,
                    "provider_visible_full_auto": True,
                    "provider_visible_interactive": True,
                    "required_writes": ["assess.assessment_note"],
                    "summary": "The same workflow assessment needs local repair.",
                    "target": "assess",
                },
                "question": {
                    "handoff": None,
                    "is_runtime_control": True,
                    "on_taken": None,
                    "provider_visible": True,
                    "provider_visible_full_auto": False,
                    "provider_visible_interactive": True,
                    "required_writes": [],
                    "summary": "Clarification or user-input request.",
                    "target": "AWAIT_INPUT",
                },
            },
            "route_targets": {
                "assessment_complete": "FINISH",
                "needs_rework": "assess",
                "question": "AWAIT_INPUT",
            },
            "session_name": None,
            "verifier_prompt": "prompts/assess_verifier.md",
            "verifier_prompt_repo_relative": "workflows/release_candidate_to_go_no_go/prompts/assess_verifier.md",
        },
    )
    assert {
        str(path.relative_to(tmp_path)): path.read_text(encoding="utf-8")
        for path in (
            package_dir / "__init__.py",
            package_dir / "workflow.toml",
            package_dir / "workflow.py",
            package_dir / "params.py",
            package_dir / "contracts.py",
            package_dir / "prompts" / "assess_producer.md",
            package_dir / "prompts" / "assess_verifier.md",
            package_dir / "prompts" / "repair" / "strategy.md",
            package_dir / "assets" / "checklist.md",
            package_dir / "assets" / "templates" / "rollback.txt",
            tmp_path / "docs" / "workflows" / "release_candidate_to_go_no_go.md",
            runtime_test,
        )
    } == before_surface_files

    with pytest.raises(ValueError, match="ctx.workflow_folder"):
        write_selected_workflow_decomposition_surface(ctx, "release_decision", "../escape.json")
    with pytest.raises(ValueError, match="\\.json"):
        write_selected_workflow_decomposition_surface(ctx, "release_decision", "surface.md")
def test_decomposition_helper_keeps_optional_authoring_paths_nullable_when_absent(tmp_path: Path) -> None:
    ctx = _build_lifecycle_context(tmp_path, workflow_name="workflow_package_to_composable_building_blocks")
    package_dir = _write_runtime_valid_catalog_workflow(
        tmp_path,
        "release_candidate_to_go_no_go",
        aliases=("release_decision",),
    )

    snapshot_path = write_selected_workflow_decomposition_surface(ctx, "release_decision")
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))

    assert payload["selected_workflow_decomposition_surface"]["selected_workflow_authoring_surface"] == {
        "asset_paths": [],
        "asset_paths_repo_relative": [],
        "doc_path": None,
        "doc_path_repo_relative": None,
        "editable_paths": sorted(
            [
                str(package_dir / "__init__.py"),
                str(package_dir / "workflow.toml"),
                str(package_dir / "workflow.py"),
                str(package_dir / "prompts" / "assess_producer.md"),
                str(package_dir / "prompts" / "assess_verifier.md"),
            ]
        ),
        "editable_paths_repo_relative": sorted(
            [
                "workflows/release_candidate_to_go_no_go/__init__.py",
                "workflows/release_candidate_to_go_no_go/workflow.toml",
                "workflows/release_candidate_to_go_no_go/workflow.py",
                "workflows/release_candidate_to_go_no_go/prompts/assess_producer.md",
                "workflows/release_candidate_to_go_no_go/prompts/assess_verifier.md",
            ]
        ),
        "manifest_path": str(package_dir / "workflow.toml"),
        "manifest_path_repo_relative": "workflows/release_candidate_to_go_no_go/workflow.toml",
        "package_dir": str(package_dir),
        "package_dir_repo_relative": "workflows/release_candidate_to_go_no_go",
        "package_init_path": str(package_dir / "__init__.py"),
        "package_init_path_repo_relative": "workflows/release_candidate_to_go_no_go/__init__.py",
        "params_path": None,
        "params_path_repo_relative": None,
        "prompt_paths": [
            str(package_dir / "prompts" / "assess_producer.md"),
            str(package_dir / "prompts" / "assess_verifier.md"),
        ],
        "prompt_paths_repo_relative": [
            "workflows/release_candidate_to_go_no_go/prompts/assess_producer.md",
            "workflows/release_candidate_to_go_no_go/prompts/assess_verifier.md",
        ],
        "runtime_test_path": None,
        "runtime_test_path_repo_relative": None,
        "spec_paths": [],
        "spec_paths_repo_relative": [],
        "test_paths": [],
        "test_paths_repo_relative": [],
        "workflow_py_path": str(package_dir / "workflow.py"),
        "workflow_py_path_repo_relative": "workflows/release_candidate_to_go_no_go/workflow.py",
        "workflow_path": str(package_dir / "workflow.py"),
        "workflow_path_repo_relative": "workflows/release_candidate_to_go_no_go/workflow.py",
    }
def test_decomposition_helper_reports_empty_parameter_metadata_when_selected_workflow_has_no_params_model(
    tmp_path: Path,
) -> None:
    ctx = _build_lifecycle_context(tmp_path, workflow_name="workflow_package_to_composable_building_blocks")
    _write_runtime_valid_catalog_workflow(
        tmp_path,
        "release_candidate_to_go_no_go",
        aliases=("release_decision",),
    )

    snapshot_path = write_selected_workflow_decomposition_surface(ctx, "release_decision")
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    compiled_surface = payload["selected_workflow_decomposition_surface"]["selected_workflow_compiled_surface"]

    assert compiled_surface["parameters_supported"] is False
    assert compiled_surface["parameters"] == []
    assert compiled_surface["artifacts"] == [
        {
            "name": "assess.assessment_note",
            "producer_steps": ["assess"],
            "template": "{workflow_folder}/assessment_note.md",
            "workflow_level": False,
        }
    ]
    assert compiled_surface["sessions"] == []
    assert compiled_surface["state_model"].endswith("ReleaseCandidateToGoNoGo.State")
    assert compiled_surface["step_count"] == 1
def test_decomposition_helper_accepts_main_workflow_class_references(tmp_path: Path) -> None:
    ctx = _build_lifecycle_context(tmp_path, workflow_name="workflow_package_to_composable_building_blocks")
    _write_runtime_valid_catalog_workflow(
        tmp_path,
        "release_candidate_to_go_no_go",
        aliases=("release_decision",),
        write_doc=True,
    )
    workflow_cls = resolve_workflow_reference(tmp_path, "release_decision").workflow_cls

    snapshot_path = write_selected_workflow_decomposition_surface(
        ctx,
        workflow_cls,
        "decomposition/selected_workflow_decomposition_surface.json",
    )
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    step = payload["selected_workflow_decomposition_surface"]["selected_workflow_compiled_surface"]["steps"][0]

    assert snapshot_path == ctx.workflow_folder / "decomposition" / "selected_workflow_decomposition_surface.json"
    assert payload["selected_workflow_name"] == "release_candidate_to_go_no_go"
    assert payload["selected_workflow_decomposition_surface"]["selected_workflow_identity"] == {
        "aliases": ["release_decision"],
        "description": "Workflow description.",
        "package_name": "release_candidate_to_go_no_go",
        "title": "Release Candidate To Go No Go",
        "workflow_class": "ReleaseCandidateToGoNoGo",
        "workflow_name": "release_candidate_to_go_no_go",
    }
    assert step["producer_prompt"] == "prompts/assess_producer.md"
    assert step["producer_prompt_repo_relative"] == "workflows/release_candidate_to_go_no_go/prompts/assess_producer.md"
    assert step["verifier_prompt"] == "prompts/assess_verifier.md"
    assert step["verifier_prompt_repo_relative"] == "workflows/release_candidate_to_go_no_go/prompts/assess_verifier.md"
def test_diagnostics_helper_snapshots_selected_workflow_run_history_via_shared_resolution_and_run_discovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _build_lifecycle_context(tmp_path, workflow_name="workflow_run_history_to_failure_modes")
    package_dir = _write_runtime_valid_catalog_workflow(
        tmp_path,
        "release_candidate_to_go_no_go",
        aliases=("release_decision",),
    )
    broken_package = _write_catalog_workflow(
        tmp_path,
        "broken_workflow",
        aliases=("broken",),
        export_parameters=True,
        write_doc=True,
    )
    (broken_package / "workflow.py").write_text(
        'raise RuntimeError("diagnostics helper imported an unrelated workflow")\n',
        encoding="utf-8",
    )
    paused_run_dir = _write_run_history_record(
        tmp_path,
        task_id="task-1",
        workflow_name="release_candidate_to_go_no_go",
        run_id="run-paused",
        status="paused",
        created_at="2026-04-24T06:00:00+00:00",
        updated_at="2026-04-24T06:03:00+00:00",
        request_text="Investigate the paused release.\n",
        workflow_params={"mode": "strict"},
        pending_question="Clarify the release gate owner.",
        events=[
            {"tag": "question", "question": "Who owns the release gate?", "reason": ""},
            {"tag": "blocked", "question": None, "reason": "Waiting on evidence."},
        ],
        children=[
            {
                "workflow_name": "release_candidate_to_go_no_go",
                "run_id": "child-run-1",
                "status": "success",
            }
        ],
        parent_record={
            "task_id": "task-1",
            "workflow_name": "task_to_workflow_strategy",
            "run_id": "parent-run-1",
        },
    )
    failed_run_dir = _write_run_history_record(
        tmp_path,
        task_id="task-2",
        workflow_name="release_candidate_to_go_no_go",
        run_id="run-failed",
        status="failed",
        created_at="2026-04-24T06:00:00+00:00",
        updated_at="2026-04-24T06:02:00+00:00",
        request_text="Investigate the failed release.\n",
        workflow_params={"mode": "review"},
        terminal="FAIL",
        error="verification mismatch",
        events=[{"tag": "failed", "question": None, "reason": "verification mismatch"}],
    )
    _write_run_history_record(
        tmp_path,
        task_id="task-3",
        workflow_name="release_candidate_to_go_no_go",
        run_id="run-success",
        status="success",
        created_at="2026-04-24T06:00:00+00:00",
        updated_at="2026-04-24T06:01:00+00:00",
        request_text="Ignore the successful release.\n",
        events=[{"tag": "assessment_complete", "question": None, "reason": ""}],
    )
    _write_run_history_record(
        tmp_path,
        task_id="task-4",
        workflow_name="incident_to_hardening_program",
        run_id="run-unrelated",
        status="failed",
        created_at="2026-04-24T06:00:00+00:00",
        updated_at="2026-04-24T06:04:00+00:00",
        request_text="Unrelated workflow history.\n",
        events=[{"tag": "failed", "question": None, "reason": "not selected"}],
    )

    before_files = {
        str(path.relative_to(tmp_path)): path.read_text(encoding="utf-8")
        for path in (
            package_dir / "__init__.py",
            package_dir / "workflow.toml",
            package_dir / "workflow.py",
            package_dir / "prompts" / "assess_producer.md",
            package_dir / "prompts" / "assess_verifier.md",
            paused_run_dir / "run.json",
            paused_run_dir / "request.md",
            paused_run_dir / "events.jsonl",
            paused_run_dir / "children.jsonl",
            paused_run_dir / "parent.json",
            failed_run_dir / "run.json",
            failed_run_dir / "request.md",
            failed_run_dir / "events.jsonl",
            failed_run_dir / "children.jsonl",
        )
    }
    resolve_calls: list[tuple[Path, str | type[object]]] = []
    discovery_calls: list[tuple[Path, str | None, str | None, str | None]] = []
    original_resolve = selected_workflow_helpers.resolve_workflow_reference
    original_list = diagnostics_helpers.list_run_records

    def _record_resolve(root, workflow):
        resolve_calls.append((Path(root), workflow))
        return original_resolve(root, workflow)

    def _record_list(root, *, workflow_name=None, task_id=None, status=None):
        discovery_calls.append((Path(root), workflow_name, task_id, status))
        return original_list(root, workflow_name=workflow_name, task_id=task_id, status=status)

    monkeypatch.setattr(selected_workflow_helpers, "resolve_workflow_reference", _record_resolve)
    monkeypatch.setattr(diagnostics_helpers, "list_run_records", _record_list)

    snapshot_path = write_selected_workflow_run_history_snapshot(
        ctx,
        "release_decision",
        statuses=["paused", "failed", "failed"],
        max_runs=2,
        relative_path="diagnostics/selected_workflow_run_history.json",
    )

    assert resolve_calls == [(tmp_path.resolve(), "release_decision")]
    assert discovery_calls == [(tmp_path.resolve(), "release_candidate_to_go_no_go", None, None)]
    assert snapshot_path == ctx.workflow_folder / "diagnostics" / "selected_workflow_run_history.json"
    assert json.loads(snapshot_path.read_text(encoding="utf-8")) == {
        "repo_root": str(tmp_path.resolve()),
        "run_id": "run-1",
        "selected_workflow_name": "release_candidate_to_go_no_go",
        "selected_workflow_run_history": {
            "max_runs": 2,
            "run_count": 2,
            "runs": [
                {
                    "children": [
                        {
                            "run_id": "child-run-1",
                            "status": "success",
                            "workflow_name": "release_candidate_to_go_no_go",
                        }
                    ],
                    "events": [
                        {
                            "question": "Who owns the release gate?",
                            "reason": "",
                            "tag": "question",
                        },
                        {
                            "question": None,
                            "reason": "Waiting on evidence.",
                            "tag": "blocked",
                        },
                    ],
                    "parent_record": {
                        "run_id": "parent-run-1",
                        "task_id": "task-1",
                        "workflow_name": "task_to_workflow_strategy",
                    },
                    "request_text": "Investigate the paused release.\n",
                    "run_metadata": {
                        "created_at": "2026-04-24T06:00:00+00:00",
                        "error": None,
                            "package_folder": "workflows/release_candidate_to_go_no_go",
                        "pending_question": "Clarify the release gate owner.",
                        "run_id": "run-paused",
                        "status": "awaiting_input",
                        "task_id": "task-1",
                        "terminal": None,
                        "updated_at": "2026-04-24T06:03:00+00:00",
                        "workflow_name": "release_candidate_to_go_no_go",
                        "workflow_params": {"mode": "strict"},
                    },
                    "source_paths": {
                        "checkpoint_file": str(paused_run_dir / "checkpoint.json"),
                        "children_file": str(paused_run_dir / "children.jsonl"),
                        "events_file": str(paused_run_dir / "events.jsonl"),
                        "parent_file": str(paused_run_dir / "parent.json"),
                        "raw_dir": str(paused_run_dir / "raw"),
                        "request_file": str(paused_run_dir / "request.md"),
                        "run_dir": str(paused_run_dir),
                        "run_meta_file": str(paused_run_dir / "run.json"),
                            "task_dir": str(tmp_path / ".botlane" / "tasks" / "task-1"),
                        "trace_file": str(paused_run_dir / "trace.jsonl"),
                            "workflow_dir": str(tmp_path / ".botlane" / "tasks" / "task-1" / "wf_release_candidate_to_go_no_go"),
                    },
                },
                {
                    "children": [],
                    "events": [
                        {
                            "question": None,
                            "reason": "verification mismatch",
                            "tag": "failed",
                        }
                    ],
                    "parent_record": None,
                    "request_text": "Investigate the failed release.\n",
                    "run_metadata": {
                        "created_at": "2026-04-24T06:00:00+00:00",
                        "error": "verification mismatch",
                            "package_folder": "workflows/release_candidate_to_go_no_go",
                        "pending_question": None,
                        "run_id": "run-failed",
                        "status": "failed",
                        "task_id": "task-2",
                        "terminal": "FAIL",
                        "updated_at": "2026-04-24T06:02:00+00:00",
                        "workflow_name": "release_candidate_to_go_no_go",
                        "workflow_params": {"mode": "review"},
                    },
                    "source_paths": {
                        "checkpoint_file": str(failed_run_dir / "checkpoint.json"),
                        "children_file": str(failed_run_dir / "children.jsonl"),
                        "events_file": str(failed_run_dir / "events.jsonl"),
                        "parent_file": str(failed_run_dir / "parent.json"),
                        "raw_dir": str(failed_run_dir / "raw"),
                        "request_file": str(failed_run_dir / "request.md"),
                        "run_dir": str(failed_run_dir),
                        "run_meta_file": str(failed_run_dir / "run.json"),
                            "task_dir": str(tmp_path / ".botlane" / "tasks" / "task-2"),
                        "trace_file": str(failed_run_dir / "trace.jsonl"),
                            "workflow_dir": str(tmp_path / ".botlane" / "tasks" / "task-2" / "wf_release_candidate_to_go_no_go"),
                    },
                },
            ],
            "statuses": ["awaiting_input", "failed"],
        },
        "task_id": "task-1",
        "workflow_name": "workflow_run_history_to_failure_modes",
    }
    assert {
        str(path.relative_to(tmp_path)): path.read_text(encoding="utf-8")
        for path in (
            package_dir / "__init__.py",
            package_dir / "workflow.toml",
            package_dir / "workflow.py",
            package_dir / "prompts" / "assess_producer.md",
            package_dir / "prompts" / "assess_verifier.md",
            paused_run_dir / "run.json",
            paused_run_dir / "request.md",
            paused_run_dir / "events.jsonl",
            paused_run_dir / "children.jsonl",
            paused_run_dir / "parent.json",
            failed_run_dir / "run.json",
            failed_run_dir / "request.md",
            failed_run_dir / "events.jsonl",
            failed_run_dir / "children.jsonl",
        )
    } == before_files

    with pytest.raises(ValueError, match="ctx.workflow_folder"):
        write_selected_workflow_run_history_snapshot(ctx, "release_decision", relative_path="../escape.json")
    with pytest.raises(ValueError, match="\\.json"):
        write_selected_workflow_run_history_snapshot(ctx, "release_decision", relative_path="diagnostics.md")
    with pytest.raises(ValueError, match="positive integer"):
        write_selected_workflow_run_history_snapshot(ctx, "release_decision", max_runs=0)
    with pytest.raises(ValueError, match="statuses entries must be non-empty strings"):
        write_selected_workflow_run_history_snapshot(ctx, "release_decision", statuses=["ok", "  "])
def test_diagnostics_helper_accepts_main_workflow_class_references_and_allows_empty_filtered_histories(
    tmp_path: Path,
) -> None:
    ctx = _build_lifecycle_context(tmp_path, workflow_name="workflow_run_history_to_failure_modes")
    _write_runtime_valid_catalog_workflow(
        tmp_path,
        "release_candidate_to_go_no_go",
        aliases=("release_decision",),
    )
    _write_run_history_record(
        tmp_path,
        task_id="task-1",
        workflow_name="release_candidate_to_go_no_go",
        run_id="run-success",
        status="success",
        created_at="2026-04-24T06:00:00+00:00",
        updated_at="2026-04-24T06:01:00+00:00",
        request_text="Routine release history.\n",
        events=[{"tag": "assessment_complete", "question": None, "reason": ""}],
    )
    workflow_cls = resolve_workflow_reference(tmp_path, "release_decision").workflow_cls

    snapshot_path = write_selected_workflow_run_history_snapshot(
        ctx,
        workflow_cls,
        statuses=["failed"],
        relative_path="diagnostics/selected_workflow_run_history.json",
    )

    assert snapshot_path == ctx.workflow_folder / "diagnostics" / "selected_workflow_run_history.json"
    assert json.loads(snapshot_path.read_text(encoding="utf-8")) == {
        "repo_root": str(tmp_path.resolve()),
        "run_id": "run-1",
        "selected_workflow_name": "release_candidate_to_go_no_go",
        "selected_workflow_run_history": {
            "max_runs": None,
            "run_count": 0,
            "runs": [],
            "statuses": ["failed"],
        },
        "task_id": "task-1",
        "workflow_name": "workflow_run_history_to_failure_modes",
    }
def test_diagnostics_helper_accepts_single_file_workflow_references(tmp_path: Path) -> None:
    ctx = _build_lifecycle_context(tmp_path, workflow_name="workflow_run_history_to_failure_modes")
    workflow_path = _write_single_file_runtime_workflow(tmp_path)
    _write_run_history_record(
        tmp_path,
        task_id="task-1",
        workflow_name="single_file_review",
        run_id="run-paused",
        status="paused",
        created_at="2026-04-24T06:00:00+00:00",
        updated_at="2026-04-24T06:01:00+00:00",
        request_text="Investigate the paused single-file review.\n",
        events=[{"tag": "question", "question": "Who owns the review?", "reason": ""}],
    )

    snapshot_path = write_selected_workflow_run_history_snapshot(
        ctx,
        str(workflow_path),
        statuses=["paused"],
        relative_path="diagnostics/single_file_workflow_run_history.json",
    )

    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))

    assert snapshot_path == ctx.workflow_folder / "diagnostics" / "single_file_workflow_run_history.json"
    assert payload["selected_workflow_name"] == "single_file_review"
    assert payload["selected_workflow_run_history"]["run_count"] == 1
    assert payload["selected_workflow_run_history"]["statuses"] == ["awaiting_input"]
    assert payload["selected_workflow_run_history"]["runs"][0]["run_metadata"]["status"] == "awaiting_input"
    assert payload["selected_workflow_run_history"]["runs"][0]["run_metadata"]["workflow_name"] == "single_file_review"
def test_evaluation_helper_validates_eval_cases_via_selected_workflow_snapshot_and_loader_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _build_lifecycle_context(tmp_path, workflow_name="workflow_to_eval_suite")
    _write_runtime_valid_catalog_workflow(
        tmp_path,
        "release_candidate_to_go_no_go",
        aliases=("release_decision",),
        export_parameters=True,
        write_doc=True,
    )
    snapshot_calls: list[tuple[str | type[object], str]] = []
    snapshot_read_paths: list[Path] = []
    snapshot_validation_calls: list[tuple[dict[str, object], str]] = []
    parameter_calls: list[tuple[type[object] | None, dict[str, object]]] = []
    original_snapshot = evaluation_helpers.write_selected_workflow_capability_snapshot
    original_read_json = evaluation_helpers.read_json_object
    original_validate_snapshot = evaluation_helpers.validate_selected_workflow_capability_snapshot
    original_coerce = evaluation_helpers.coerce_workflow_parameter_mapping

    def _record_snapshot(ctx, workflow, relative_path="selected_workflow_capability.json"):
        snapshot_calls.append((workflow, str(relative_path)))
        return original_snapshot(ctx, workflow, relative_path)

    def _record_read_json(path):
        snapshot_read_paths.append(Path(path))
        return original_read_json(path)

    def _record_validate_snapshot(payload, **kwargs):
        snapshot_validation_calls.append((dict(payload), str(kwargs.get("expected_label"))))
        return original_validate_snapshot(payload, **kwargs)

    def _record_coerce(parameters_cls, raw_values):
        payload = dict(raw_values or {})
        parameter_calls.append((parameters_cls, payload))
        return original_coerce(parameters_cls, raw_values)

    monkeypatch.setattr(evaluation_helpers, "write_selected_workflow_capability_snapshot", _record_snapshot)
    monkeypatch.setattr(evaluation_helpers, "read_json_object", _record_read_json)
    monkeypatch.setattr(evaluation_helpers, "validate_selected_workflow_capability_snapshot", _record_validate_snapshot)
    monkeypatch.setattr(evaluation_helpers, "coerce_workflow_parameter_mapping", _record_coerce)

    validated_path = write_validated_eval_case_manifest(
        ctx,
        "release_decision",
        {
            "cases": [
                {
                    "case_id": "stress_release",
                    "case_kind": "adversarial",
                    "prompt": "Assess a release candidate with rollback evidence missing.",
                    "expected_artifacts": ["assessment_note"],
                },
                {
                    "case_id": "baseline_release",
                    "case_kind": "benchmark",
                    "prompt": "Assess a routine release candidate with complete evidence.",
                    "expected_artifacts": ["assessment_note"],
                    "workflow_parameters": {"mode": "review", "reviewers": ["ops", "qa"]},
                },
            ]
        },
        "eval/validated_eval_case_manifest.json",
    )

    assert snapshot_calls == [("release_decision", "selected_workflow_capability.json")]
    assert snapshot_read_paths == [ctx.workflow_folder / "selected_workflow_capability.json"]
    assert len(snapshot_validation_calls) == 1
    snapshot_payload, expected_label = snapshot_validation_calls[0]
    assert expected_label == "the resolved workflow"
    assert snapshot_payload["selected_workflow_name"] == "release_candidate_to_go_no_go"
    assert snapshot_payload["workflow_name"] == "workflow_to_eval_suite"
    assert snapshot_payload["selected_workflow_capability"]["workflow_name"] == "release_candidate_to_go_no_go"
    assert len(parameter_calls) == 2
    assert [payload for _, payload in parameter_calls] == [
        {},
        {"mode": "review", "reviewers": ["ops", "qa"]},
    ]
    assert validated_path == ctx.workflow_folder / "eval" / "validated_eval_case_manifest.json"
    assert json.loads(validated_path.read_text(encoding="utf-8")) == {
        "case_count": 2,
        "case_ids": ["baseline_release", "stress_release"],
        "case_kinds": ["benchmark", "adversarial"],
        "repo_root": str(tmp_path.resolve()),
        "run_id": "run-1",
        "selected_workflow_name": "release_candidate_to_go_no_go",
        "task_id": "task-1",
        "validated_cases": [
            {
                "case_id": "baseline_release",
                "case_kind": "benchmark",
                "expected_artifacts": ["assessment_note"],
                "prompt": "Assess a routine release candidate with complete evidence.",
                "workflow_parameters": {
                    "mode": "review",
                    "reviewers": ["ops", "qa"],
                },
            },
            {
                "case_id": "stress_release",
                "case_kind": "adversarial",
                "expected_artifacts": ["assessment_note"],
                "prompt": "Assess a release candidate with rollback evidence missing.",
                "workflow_parameters": {
                    "mode": "strict",
                    "reviewers": [],
                },
            },
        ],
        "workflow_name": "workflow_to_eval_suite",
    }

    assert (ctx.workflow_folder / "selected_workflow_capability.json").is_file()
    with pytest.raises(ValueError, match="ctx.workflow_folder"):
        write_validated_eval_case_manifest(
            ctx,
            "release_decision",
            {
                "cases": [
                    {
                        "case_id": "path_escape",
                        "case_kind": "benchmark",
                        "prompt": "Assess the routine release candidate.",
                        "expected_artifacts": ["assessment_note"],
                    }
                ]
            },
            "../escape.json",
        )
    with pytest.raises(ValueError, match="\\.json"):
        write_validated_eval_case_manifest(
            ctx,
            "release_decision",
            {
                "cases": [
                    {
                        "case_id": "wrong_suffix",
                        "case_kind": "benchmark",
                        "prompt": "Assess the routine release candidate.",
                        "expected_artifacts": ["assessment_note"],
                    }
                ]
            },
            "validated.md",
        )
def test_evaluation_helper_accepts_single_file_workflow_references(tmp_path: Path) -> None:
    ctx = _build_lifecycle_context(tmp_path, workflow_name="workflow_to_eval_suite")
    workflow_path = _write_single_file_runtime_workflow(tmp_path)

    validated_path = write_validated_eval_case_manifest(
        ctx,
        str(workflow_path),
        {
            "cases": [
                {
                    "case_id": "single-file-edge",
                    "case_kind": "edge",
                    "prompt": "Validate the review note flow.",
                    "expected_artifacts": ["review_note"],
                }
            ]
        },
        "evaluation/single_file_validated_eval_case_manifest.json",
    )

    payload = json.loads(validated_path.read_text(encoding="utf-8"))

    assert validated_path == ctx.workflow_folder / "evaluation" / "single_file_validated_eval_case_manifest.json"
    assert payload["selected_workflow_name"] == "single_file_review"
    assert payload["case_count"] == 1
    assert payload["case_ids"] == ["single-file-edge"]
    assert payload["validated_cases"] == [
        {
            "case_id": "single-file-edge",
            "case_kind": "edge",
            "expected_artifacts": ["review_note"],
            "prompt": "Validate the review note flow.",
            "workflow_parameters": {},
        }
    ]
def test_evaluation_helper_rejects_snapshot_mismatch_through_shared_snapshot_validator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _build_lifecycle_context(tmp_path, workflow_name="workflow_to_eval_suite")
    _write_runtime_valid_catalog_workflow(
        tmp_path,
        "release_candidate_to_go_no_go",
        aliases=("release_decision",),
        export_parameters=True,
    )
    original_read_json = evaluation_helpers.read_json_object

    def _mismatched_snapshot(path):
        payload = original_read_json(path)
        payload["selected_workflow_name"] = "incident_to_hardening_program"
        payload["selected_workflow_capability"]["workflow_name"] = "incident_to_hardening_program"
        return payload

    monkeypatch.setattr(evaluation_helpers, "read_json_object", _mismatched_snapshot)

    with pytest.raises(
        ValueError,
        match="selected_workflow_capability.json selected_workflow_name must match the resolved workflow",
    ):
        write_validated_eval_case_manifest(
            ctx,
            "release_decision",
            {
                "cases": [
                    {
                        "case_id": "baseline_release",
                        "case_kind": "benchmark",
                        "prompt": "Assess a routine release candidate with complete evidence.",
                        "expected_artifacts": ["assessment_note"],
                    }
                ]
            },
        )
def test_evaluation_helper_rejects_invalid_case_shapes_and_unknown_expected_artifacts(tmp_path: Path) -> None:
    ctx = _build_lifecycle_context(tmp_path, workflow_name="workflow_to_eval_suite")
    _write_runtime_valid_catalog_workflow(
        tmp_path,
        "release_candidate_to_go_no_go",
        aliases=("release_decision",),
        export_parameters=True,
    )

    with pytest.raises(ValueError, match="unsupported case_kind"):
        write_validated_eval_case_manifest(
            ctx,
            "release_decision",
            {
                "cases": [
                    {
                        "case_id": "bad_kind",
                        "case_kind": "smoke",
                        "prompt": "Assess the release candidate.",
                        "expected_artifacts": ["assessment_note"],
                    }
                ]
            },
        )
    with pytest.raises(ValueError, match="repeats case_id 'duplicate_case'"):
        write_validated_eval_case_manifest(
            ctx,
            "release_decision",
            {
                "cases": [
                    {
                        "case_id": "duplicate_case",
                        "case_kind": "benchmark",
                        "prompt": "Assess the routine release candidate.",
                        "expected_artifacts": ["assessment_note"],
                    },
                    {
                        "case_id": "duplicate_case",
                        "case_kind": "edge",
                        "prompt": "Assess the release candidate with missing notes.",
                        "expected_artifacts": ["assessment_note"],
                    },
                ]
            },
        )
    with pytest.raises(ValueError, match="non-empty prompt"):
        write_validated_eval_case_manifest(
            ctx,
            "release_decision",
            {
                "cases": [
                    {
                        "case_id": "blank_prompt",
                        "case_kind": "benchmark",
                        "prompt": "   ",
                        "expected_artifacts": ["assessment_note"],
                    }
                ]
            },
        )
    with pytest.raises(ValueError, match="non-empty string list"):
        write_validated_eval_case_manifest(
            ctx,
            "release_decision",
            {
                "cases": [
                    {
                        "case_id": "missing_artifacts",
                        "case_kind": "benchmark",
                        "prompt": "Assess the routine release candidate.",
                        "expected_artifacts": [],
                    }
                ]
            },
        )
    with pytest.raises(ValueError, match="unknown artifact 'not_declared'"):
        write_validated_eval_case_manifest(
            ctx,
            "release_decision",
            {
                "cases": [
                    {
                        "case_id": "unknown_artifact",
                        "case_kind": "edge",
                        "prompt": "Assess a release candidate with missing artifacts.",
                        "expected_artifacts": ["not_declared"],
                    }
                ]
            },
        )
def test_evaluation_helper_rejects_missing_case_arrays_and_non_mapping_case_parameters(tmp_path: Path) -> None:
    ctx = _build_lifecycle_context(tmp_path, workflow_name="workflow_to_eval_suite")
    _write_runtime_valid_catalog_workflow(
        tmp_path,
        "release_candidate_to_go_no_go",
        aliases=("release_decision",),
        export_parameters=True,
    )

    with pytest.raises(ValueError, match="must define cases as a JSON array"):
        write_validated_eval_case_manifest(ctx, "release_decision", {})
    with pytest.raises(ValueError, match="must define at least one case"):
        write_validated_eval_case_manifest(ctx, "release_decision", {"cases": []})
    with pytest.raises(ValueError, match="workflow_parameters must be a JSON object"):
        write_validated_eval_case_manifest(
            ctx,
            "release_decision",
            {
                "cases": [
                    {
                        "case_id": "bad_parameter_shape",
                        "case_kind": "benchmark",
                        "prompt": "Assess the routine release candidate.",
                        "expected_artifacts": ["assessment_note"],
                        "workflow_parameters": ["not", "a", "mapping"],
                    }
                ]
            },
        )
def test_evaluation_helper_preserves_shared_loader_failure_for_invalid_case_parameters(tmp_path: Path) -> None:
    ctx = _build_lifecycle_context(tmp_path, workflow_name="workflow_to_eval_suite")
    _write_runtime_valid_catalog_workflow(
        tmp_path,
        "release_candidate_to_go_no_go",
        aliases=("release_decision",),
        export_parameters=True,
    )

    with pytest.raises(WorkflowParameterError, match=r"unknown workflow parameter 'unexpected'"):
        write_validated_eval_case_manifest(
            ctx,
            "release_decision",
            {
                "cases": [
                    {
                        "case_id": "bad_parameters",
                        "case_kind": "benchmark",
                        "prompt": "Assess the routine release candidate.",
                        "expected_artifacts": ["assessment_note"],
                        "workflow_parameters": {"unexpected": "value"},
                    }
                ]
            },
        )
