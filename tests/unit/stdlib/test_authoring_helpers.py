from __future__ import annotations

import ast

from pydantic import Field

from tests.unit._stdlib_and_extensions_shared import _ExampleModel, _build_lifecycle_context
from tests.unit._stdlib_and_extensions_shared import *

def test_stdlib_modules_remain_pure_authoring_helpers() -> None:
    runtime_import_patterns = (
        re.compile(r"\bfrom\s+runtime(?:\.|\s+import\b)"),
        re.compile(r"\bimport\s+runtime(?:\.|\b)"),
    )
    workflow_import_patterns = (
        re.compile(r"\bfrom\s+workflows(?:\.|\s+import\b)"),
        re.compile(r"\bimport\s+workflows(?:\.|\b)"),
    )
    for relative_path in (
        "autoloop/stdlib/composition.py",
        "autoloop/stdlib/control.py",
        "autoloop/stdlib/json_artifacts.py",
        "autoloop/stdlib/lifecycle.py",
        "autoloop/stdlib/parameters.py",
        "autoloop/stdlib/prompts.py",
        "autoloop/stdlib/state/cursor.py",
        "autoloop/stdlib/validation.py",
    ):
        text = (PACKAGE_ROOT / relative_path).read_text(encoding="utf-8")
        assert not any(pattern.search(text) for pattern in runtime_import_patterns)
        assert not any(pattern.search(text) for pattern in workflow_import_patterns)
    assert not (PACKAGE_ROOT / "autoloop" / "stdlib" / "contracts.py").exists()
    assert not (PACKAGE_ROOT / "autoloop" / "stdlib" / "steps.py").exists()
    for relative_path in (
        "autoloop/stdlib/_selected_workflow.py",
        "autoloop/stdlib/adaptation.py",
        "autoloop/stdlib/candidate_surfaces.py",
        "autoloop/stdlib/company.py",
        "autoloop/stdlib/decomposition.py",
        "autoloop/stdlib/diagnostics.py",
        "autoloop/stdlib/evaluation.py",
        "autoloop/stdlib/portfolio.py",
        "autoloop/stdlib/refinement.py",
        "autoloop/stdlib/route_" + "infos.py",
    ):
        assert not (PACKAGE_ROOT / relative_path).exists()
def test_active_consumer_runtime_fixtures_avoid_legacy_authoring_tokens() -> None:
    for relative_path in ACTIVE_CONSUMER_RUNTIME_FILES:
        text = (PACKAGE_ROOT / relative_path).read_text(encoding="utf-8")
        for token in BANNED_CONSUMER_TOKENS:
            assert token not in text, f"{relative_path} unexpectedly reintroduced legacy token {token!r}"
def test_retained_stdlib_authoring_test_stays_free_of_repo_owned_workflow_package_params() -> None:
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    forbidden_modules = {
        "autoloop.workflows.workflow_and_eval_to_refined_workflow_package.params",
        "autoloop.workflows.workflow_package_to_composable_building_blocks.params",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module not in forbidden_modules
def test_control_helpers_merge_routes_and_build_outcome_passthrough() -> None:
    step = object()
    transitions = merge_transitions(
        global_routes(await_input_on_outcome_tags("question", "blocked"), failed=FAIL),
        {step: {"done": FINISH}},
    )
    handler = event_on_outcome_tags("question", "blocked", "failed")

    class Ctx:
        def __init__(self, outcome: Outcome) -> None:
            self.outcome = outcome

    assert transitions[GLOBAL] == {"question": AWAIT_INPUT, "blocked": AWAIT_INPUT, "failed": FAIL}
    assert transitions[step] == {"done": FINISH}
    assert handler(Ctx(Outcome(raw_output="need help", tag="question", question="Clarify?"))) == Event(
        "question",
        question="Clarify?",
    )
    assert handler(Ctx(Outcome(raw_output="done", tag="done"))) is None
def test_control_helper_event_on_outcome_tags_exposes_single_ctx_hook_signature() -> None:
    handler = event_on_outcome_tags("question")

    assert tuple(inspect.signature(handler).parameters) == ("ctx",)
def test_prompt_bundle_pairs_prompts_without_reexporting_legacy_pair_step_helper() -> None:
    prompts = PromptBundle("prompts/plan").pair("producer.md", "verifier.md")

    assert prompts.producer.path == "prompts/plan/producer.md"
    assert prompts.verifier.path == "prompts/plan/verifier.md"
def test_validation_helpers_normalize_strings_lists_and_duplicates() -> None:
    assert require_non_empty_string("  ready  ", field_name="status") == "ready"
    assert require_string_list([" a ", "b"], field_name="items") == ["a", "b"]
    assert require_unique_values(["alpha", "beta"], field_name="items") == ["alpha", "beta"]
    assert require_non_empty_string(7, error_message="custom status message", coerce=True) == "7"
    assert require_string_list(
        " b ",
        field_name="items",
        error_message="custom list message",
        allow_scalar=True,
        dedupe=True,
        coerce=True,
    ) == ["b"]
    assert require_string_list(
        [" b ", "a", "b"],
        field_name="items",
        dedupe=True,
        sort_output=True,
    ) == ["a", "b"]

    with pytest.raises(ValueError, match="status must be a non-empty string"):
        require_non_empty_string("   ", field_name="status")
    with pytest.raises(ValueError, match="items must contain at least 1 item"):
        require_string_list([], field_name="items")
    with pytest.raises(ValueError, match="items must not repeat values"):
        require_unique_values(["dup", "dup"], field_name="items")
    with pytest.raises(ValueError, match="custom duplicate message"):
        require_unique_values(["dup", "dup"], error_message="custom duplicate message")
    with pytest.raises(ValueError, match="custom list message"):
        require_string_list([], field_name="items", error_message="custom list message")
def test_validation_helpers_cover_shared_workflow_local_shapes(tmp_path: Path) -> None:
    payload_path = tmp_path / "summary.json"
    payload_path.write_text('{"status": "ready", "count": 2}\n', encoding="utf-8")

    assert normalize_optional_string("  status  ") == "status"
    assert normalize_unique_strings(" one ", field_name="items", allow_scalar=True) == ["one"]
    assert require_non_negative_int(0, field_name="count") == 0
    assert require_positive_int(3, field_name="count") == 3
    assert require_mapping({"count": 2}, field_name="payload") == {"count": 2}
    assert require_mapping_list([{"count": 2}], field_name="payloads") == [{"count": 2}]
    assert read_json_object(payload_path) == {"status": "ready", "count": 2}

    with pytest.raises(ValueError, match="items must be a string or null"):
        normalize_optional_string(object(), field_name="items", coerce=False)
    with pytest.raises(ValueError, match="count must be a non-negative integer"):
        require_non_negative_int(-1, field_name="count")
    with pytest.raises(ValueError, match="count must be a positive integer"):
        require_positive_int(False, field_name="count")
    with pytest.raises(ValueError, match="payload must be a JSON object"):
        require_mapping([], field_name="payload")

    assert validation_helpers.normalize_optional_string is normalize_optional_string
    assert validation_helpers.normalize_unique_strings is normalize_unique_strings
    assert validation_helpers.read_json_object is read_json_object
    assert validation_helpers.require_mapping is require_mapping
    assert validation_helpers.require_mapping_list is require_mapping_list
    assert validation_helpers.require_non_negative_int is require_non_negative_int
    assert validation_helpers.require_positive_int is require_positive_int
    assert validation_helpers.required_text_fields is required_text_fields
    assert validation_helpers.optional_text_fields is optional_text_fields
    assert validation_helpers.deduped_string_list_fields is deduped_string_list_fields
    assert validation_helpers.positive_int_fields is positive_int_fields
    assert validation_helpers.validate_selected_workflow_capability_snapshot is (
        validate_selected_workflow_capability_snapshot
    )
    assert validation_helpers.validate_selected_workflow_authoring_surface_snapshot is (
        validate_selected_workflow_authoring_surface_snapshot
    )
    assert validation_helpers.validate_selected_workflow_artifact_alignment is (
        validate_selected_workflow_artifact_alignment
    )
    assert validation_helpers.validate_selected_workflow_capability_and_authoring_snapshots is (
        validate_selected_workflow_capability_and_authoring_snapshots
    )
    assert validation_helpers.validate_selected_workflow_decomposition_surface_snapshot is (
        validate_selected_workflow_decomposition_surface_snapshot
    )
    assert validation_helpers.validate_selected_workflow_name_alignment is validate_selected_workflow_name_alignment
def test_parameter_model_bundles_preserve_shared_task_and_selected_workflow_normalization() -> None:
    class _WindowedTaskParameters(TaskFramingParameters):
        max_iterations: int = 3

        _validate_max_iterations = positive_int_fields(
            "max_iterations",
            error_message="must be a positive integer",
        )

    task_params = TaskFramingWithEvidenceParameters.model_validate(
        {
            "task_title": " Workflow portfolio review ",
            "sponsor_role": " Architecture ",
            "desired_outcome": " Reduce boilerplate ",
            "constraints": [" reuse ", "reuse", " ", "keep CLI stable"],
            "evidence_expectations": [" tests ", "tests", " docs "],
        }
    )
    selected_params = SelectedWorkflowTaskFramingWithEvidenceParameters.model_validate(
        {
            "selected_workflow": " release_candidate_to_go_no_go ",
            "task_title": " Release quality review ",
            "constraints": [" evidence ", "evidence"],
            "evidence_expectations": [" receipt ", "receipt", "summary"],
        }
    )
    portfolio_params = PortfolioReviewParameters.model_validate(
        {
            "task_title": " Company recursive-improvement review ",
            "decision_drivers": [" clarity ", "clarity", "coverage"],
            "constraints": [" keep CLI stable ", "keep CLI stable"],
        }
    )
    windowed_params = _WindowedTaskParameters.model_validate(
        {
            "task_title": " Governance review ",
            "constraints": [" bounded ", "bounded", "explicit"],
            "max_iterations": 4,
        }
    )

    assert task_params.task_title == "Workflow portfolio review"
    assert task_params.sponsor_role == "Architecture"
    assert task_params.desired_outcome == "Reduce boilerplate"
    assert task_params.constraints == ["reuse", "keep CLI stable"]
    assert task_params.evidence_expectations == ["tests", "docs"]

    assert selected_params.selected_workflow == "release_candidate_to_go_no_go"
    assert selected_params.task_title == "Release quality review"
    assert selected_params.constraints == ["evidence"]
    assert selected_params.evidence_expectations == ["receipt", "summary"]

    assert portfolio_params.task_title == "Company recursive-improvement review"
    assert portfolio_params.decision_drivers == ["clarity", "coverage"]
    assert portfolio_params.constraints == ["keep CLI stable"]

    assert windowed_params.max_iterations == 4
    assert windowed_params.constraints == ["bounded", "explicit"]

    assert parameter_helpers.TaskFramingParameters is TaskFramingParameters
    assert parameter_helpers.TaskFramingWithEvidenceParameters is TaskFramingWithEvidenceParameters
    assert parameter_helpers.SelectedWorkflowTaskFramingParameters is SelectedWorkflowTaskFramingParameters
    assert (
        parameter_helpers.SelectedWorkflowTaskFramingWithEvidenceParameters
        is SelectedWorkflowTaskFramingWithEvidenceParameters
    )
    assert parameter_helpers.PortfolioReviewParameters is PortfolioReviewParameters

    with pytest.raises(ValueError, match="task_title"):
        TaskFramingParameters.model_validate({"task_title": "   "})

    with pytest.raises(ValueError, match="value must be non-empty"):
        SelectedWorkflowTaskFramingParameters.model_validate(
            {
                "selected_workflow": "   ",
                "task_title": "Valid title",
            }
        )

    with pytest.raises(ValueError, match="must be a positive integer"):
        _WindowedTaskParameters.model_validate({"task_title": "Governance review", "max_iterations": 0})
def test_workflow_specific_parameter_models_keep_inherited_selected_workflow_validation() -> None:
    class RefinementParameters(SelectedWorkflowTaskFramingParameters):
        evaluation_summary_path: str
        evaluation_findings_path: str
        failure_modes_path: str | None = None
        target_test_command: str | None = None

        _normalize_required_text = required_text_fields(
            "evaluation_summary_path",
            "evaluation_findings_path",
            error_message="value must be non-empty",
        )
        _normalize_optional_text = optional_text_fields("failure_modes_path", "target_test_command")

    class DecompositionParameters(SelectedWorkflowTaskFramingParameters):
        evidence_paths: list[str] = Field(default_factory=list)
        target_test_command: str

        _normalize_evidence_paths = deduped_string_list_fields("evidence_paths")
        _normalize_target_test_command = required_text_fields(
            "target_test_command",
            error_message="value must be non-empty",
        )

    refinement_params = RefinementParameters.model_validate(
        {
            "selected_workflow": " release_candidate_to_go_no_go ",
            "task_title": " Release workflow refinement ",
            "evaluation_summary_path": " .autoloop/evals/summary.json ",
            "evaluation_findings_path": " .autoloop/evals/findings.md ",
            "failure_modes_path": " ",
            "target_test_command": " pytest -q ",
            "constraints": [" keep candidate publication explicit ", "keep candidate publication explicit"],
        }
    )
    decomposition_params = DecompositionParameters.model_validate(
        {
            "selected_workflow": " release_candidate_to_go_no_go ",
            "task_title": " Release workflow decomposition ",
            "evidence_paths": [
                " .autoloop/signals/release_decomposition_pressure.md ",
                ".autoloop/signals/release_decomposition_pressure.md",
            ],
            "target_test_command": " pytest -q ",
            "constraints": [" keep runtime control narrow ", "keep runtime control narrow"],
        }
    )

    assert refinement_params.selected_workflow == "release_candidate_to_go_no_go"
    assert refinement_params.task_title == "Release workflow refinement"
    assert refinement_params.evaluation_summary_path == ".autoloop/evals/summary.json"
    assert refinement_params.evaluation_findings_path == ".autoloop/evals/findings.md"
    assert refinement_params.failure_modes_path is None
    assert refinement_params.target_test_command == "pytest -q"
    assert refinement_params.constraints == ["keep candidate publication explicit"]

    assert decomposition_params.selected_workflow == "release_candidate_to_go_no_go"
    assert decomposition_params.task_title == "Release workflow decomposition"
    assert decomposition_params.evidence_paths == [".autoloop/signals/release_decomposition_pressure.md"]
    assert decomposition_params.target_test_command == "pytest -q"
    assert decomposition_params.constraints == ["keep runtime control narrow"]

    with pytest.raises(ValueError, match="value must be non-empty"):
        RefinementParameters.model_validate(
            {
                "selected_workflow": "   ",
                "task_title": "Release workflow refinement",
                "evaluation_summary_path": ".autoloop/evals/summary.json",
                "evaluation_findings_path": ".autoloop/evals/findings.md",
            }
        )

    with pytest.raises(ValueError, match="value must be non-empty"):
        DecompositionParameters.model_validate(
            {
                "selected_workflow": "release_candidate_to_go_no_go",
                "task_title": "   ",
                "target_test_command": "pytest -q",
            }
        )
def test_validation_helpers_cover_opt_in_bool_and_mapping_list_item_failures() -> None:
    assert require_positive_int(True, field_name="count", allow_bool=True) is True

    with pytest.raises(ValueError, match="payloads must be JSON objects"):
        require_mapping_list(
            [{"count": 1}, []],
            field_name="payloads",
            error_message="payloads must be JSON objects",
        )
def test_selected_workflow_validation_helpers_cover_shared_snapshot_identity_rules() -> None:
    capability_name, capability = validate_selected_workflow_capability_snapshot(
        {
            "selected_workflow_name": "release_candidate_to_go_no_go",
            "selected_workflow_capability": {"workflow_name": "release_candidate_to_go_no_go"},
        }
    )
    authoring_name, authoring_surface = validate_selected_workflow_authoring_surface_snapshot(
        {
            "selected_workflow_name": "release_candidate_to_go_no_go",
            "selected_workflow_authoring_surface": {"workflow_name": "release_candidate_to_go_no_go"},
        }
    )
    decomposition_name, decomposition_surface, identity, compiled_surface = (
        validate_selected_workflow_decomposition_surface_snapshot(
            {
                "selected_workflow_name": "release_candidate_to_go_no_go",
                "selected_workflow_decomposition_surface": {
                    "selected_workflow_identity": {"workflow_name": "release_candidate_to_go_no_go"},
                    "selected_workflow_compiled_surface": {"step_count": 1},
                },
            }
        )
    )

    assert capability_name == "release_candidate_to_go_no_go"
    assert capability["workflow_name"] == capability_name
    assert authoring_name == capability_name
    assert authoring_surface["workflow_name"] == authoring_name
    paired_name, paired_capability, paired_authoring_surface = (
        validate_selected_workflow_capability_and_authoring_snapshots(
            {
                "selected_workflow_name": "release_candidate_to_go_no_go",
                "selected_workflow_capability": {"workflow_name": "release_candidate_to_go_no_go"},
            },
            {
                "selected_workflow_name": "release_candidate_to_go_no_go",
                "selected_workflow_authoring_surface": {"workflow_name": "release_candidate_to_go_no_go"},
            },
        )
    )
    assert decomposition_name == capability_name
    assert decomposition_surface["selected_workflow_identity"] == identity
    assert compiled_surface["step_count"] == 1
    assert paired_name == capability_name
    assert paired_capability["workflow_name"] == capability_name
    assert paired_authoring_surface["workflow_name"] == capability_name
    assert (
        validate_selected_workflow_name_alignment(
            "release_candidate_to_go_no_go",
            capability_name,
            artifact_name="selected_workflow_run_history.json",
            expected_artifact_name="selected_workflow_capability.json",
        )
        == capability_name
    )
    assert (
        validate_selected_workflow_artifact_alignment(
            {"selected_workflow_name": "release_candidate_to_go_no_go"},
            artifact_name="validated_eval_case_manifest.json",
            expected_selected_workflow_name=capability_name,
            expected_artifact_name="selected_workflow_capability.json",
        )
        == capability_name
    )

    with pytest.raises(
        ValueError,
        match="selected_workflow_authoring_surface.json selected_workflow_name must match selected_workflow_capability.json",
    ):
        validate_selected_workflow_name_alignment(
            "incident_to_hardening_program",
            capability_name,
            artifact_name="selected_workflow_authoring_surface.json",
            expected_artifact_name="selected_workflow_capability.json",
        )

    with pytest.raises(
        ValueError,
        match="validated_eval_case_manifest.json selected_workflow_name must match selected_workflow_capability.json",
    ):
        validate_selected_workflow_artifact_alignment(
            {"selected_workflow_name": "incident_to_hardening_program"},
            artifact_name="validated_eval_case_manifest.json",
            expected_selected_workflow_name=capability_name,
            expected_artifact_name="selected_workflow_capability.json",
        )

    with pytest.raises(
        ValueError,
        match="selected_workflow_authoring_surface.json selected_workflow_name must match selected_workflow_capability.json",
    ):
        validate_selected_workflow_capability_and_authoring_snapshots(
            {
                "selected_workflow_name": "release_candidate_to_go_no_go",
                "selected_workflow_capability": {"workflow_name": "release_candidate_to_go_no_go"},
            },
            {
                "selected_workflow_name": "incident_to_hardening_program",
                "selected_workflow_authoring_surface": {"workflow_name": "incident_to_hardening_program"},
            },
        )
def test_validation_model_file_helpers_round_trip_and_report_readable_errors(tmp_path: Path) -> None:
    ctx = _build_lifecycle_context(tmp_path)
    model = _ExampleModel(status="ready", count=2)

    written_path = write_model_file(ctx, "reports/result.json", model)
    assert written_path == ctx.workflow_folder / "reports" / "result.json"
    assert read_model_file(written_path, _ExampleModel) == model

    valid_report = validate_model_file(written_path, _ExampleModel)
    assert valid_report == ValidationReport(path=written_path, model_name="_ExampleModel", issues=())
    assert valid_report.ok is True

    invalid_json_path = ctx.workflow_folder / "reports" / "invalid.json"
    invalid_json_path.write_text("{bad", encoding="utf-8")
    invalid_json_report = validate_model_file(invalid_json_path, _ExampleModel)
    assert invalid_json_report.ok is False
    assert invalid_json_report.issues == (
        ValidationIssue(location=("json",), message="invalid JSON: Expecting property name enclosed in double quotes"),
    )

    non_object_json_path = ctx.workflow_folder / "reports" / "wrong_shape.json"
    non_object_json_path.write_text("[]\n", encoding="utf-8")
    non_object_report = validate_model_file(non_object_json_path, _ExampleModel)
    assert non_object_report.ok is False
    assert non_object_report.issues == (
        ValidationIssue(location=("json",), message="wrong_shape.json must contain a JSON object"),
    )

    invalid_model_path = ctx.workflow_folder / "reports" / "schema_invalid.json"
    invalid_model_path.write_text('{"status": "ready", "count": "wrong"}\n', encoding="utf-8")
    invalid_model_report = validate_model_file(invalid_model_path, _ExampleModel)
    assert invalid_model_report.ok is False
    assert invalid_model_report.issues[0].location == ("count",)
    assert "valid integer" in invalid_model_report.issues[0].message

    with pytest.raises(ValueError, match="ctx.workflow_folder"):
        write_model_file(ctx, "../escape.json", model)
def test_json_artifact_spec_wraps_shared_model_file_helpers(tmp_path: Path) -> None:
    ctx = _build_lifecycle_context(tmp_path)
    spec = JsonArtifactSpec("_typed/result.json", _ExampleModel)
    model = _ExampleModel(status="published", count=1)

    written_path = spec.write(ctx, model)

    assert written_path == ctx.workflow_folder / "_typed" / "result.json"
    assert spec.read(written_path) == model
    assert spec.validate(written_path).ok is True
def test_workflow_local_json_artifact_specs_cover_summary_and_manifest_contracts(tmp_path: Path) -> None:
    strategy_summary_path = tmp_path / "strategy_summary.json"
    strategy_summary_path.write_text(
        json.dumps(
            {
                "summary": "Keep the front door at strategy publication.",
                "selected_strategy": "adapt",
                "recommended_workflows": ["security_finding_to_verified_remediation"],
                "comparison_candidates": [
                    "security_finding_to_verified_remediation",
                    "incident_to_hardening_program",
                    "workflow_idea_to_workflow_package",
                ],
                "builder_baseline_workflow": "workflow_idea_to_workflow_package",
                "builder_considered": True,
                "create_new_required": False,
                "authoritative_artifacts": [
                    "workflow_strategy_package",
                    "strategy_summary",
                    "strategy_next_action",
                ],
                "next_action": "Run candidate_workflow_to_adapted_execution_plan for security_finding_to_verified_remediation.",
                "ready_for_handoff": True,
                "rejected_routes": ["create_new"],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    strategy_summary = STRATEGY_SUMMARY_ARTIFACT.read(strategy_summary_path)
    assert strategy_summary.selected_strategy == "adapt"
    assert strategy_summary.recommended_workflows == ["security_finding_to_verified_remediation"]
    assert STRATEGY_SUMMARY_ARTIFACT.validate(strategy_summary_path).ok is True

    validated_manifest_path = tmp_path / "validated_eval_case_manifest.json"
    validated_manifest_path.write_text(
        json.dumps(
            {
                "repo_root": "/repo",
                "run_id": "run-123",
                "selected_workflow_name": "release_candidate_to_go_no_go",
                "task_id": "task-123",
                "workflow_name": "workflow_to_eval_suite",
                "case_count": 1,
                "case_ids": ["baseline_release_gate"],
                "case_kinds": ["benchmark"],
                "validated_cases": [
                    {
                        "case_id": "baseline_release_gate",
                        "case_kind": "benchmark",
                        "expected_artifacts": ["decision_summary", "release_decision_package"],
                        "prompt": "Assess a routine release candidate and publish the package.",
                        "workflow_parameters": {},
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    validated_manifest = VALIDATED_EVAL_CASE_MANIFEST_ARTIFACT.read(validated_manifest_path)
    assert validated_manifest.case_ids == ["baseline_release_gate"]
    assert validated_manifest.validated_cases[0].expected_artifacts == [
        "decision_summary",
        "release_decision_package",
    ]
    assert VALIDATED_EVAL_CASE_MANIFEST_ARTIFACT.validate(validated_manifest_path).ok is True

    invalid_strategy_summary_path = tmp_path / "invalid_strategy_summary.json"
    invalid_strategy_summary_path.write_text(
        json.dumps({"selected_strategy": "adapt"}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    invalid_report = STRATEGY_SUMMARY_ARTIFACT.validate(invalid_strategy_summary_path)
    assert invalid_report.ok is False
    assert {issue.location for issue in invalid_report.issues} >= {
        ("recommended_workflows",),
        ("comparison_candidates",),
    }
@pytest.mark.parametrize(
    ("artifact_spec", "filename", "payload", "expected_field", "expected_value"),
    (
        (
            PORTFOLIO_OPERATING_SUMMARY_ARTIFACT,
            "portfolio_operating_summary.json",
            {
                "focus_workflows": [
                    "task_to_workflow_strategy",
                    "workflow_run_history_to_failure_modes",
                ],
                "analyzed_workflows": [
                    "task_to_workflow_strategy",
                    "workflow_run_history_to_failure_modes",
                ],
                "lifecycle_recommendations": [
                    {
                        "workflow_name": "task_to_workflow_strategy",
                        "lifecycle_posture": "refine",
                        "priority": "P1",
                    },
                    {
                        "workflow_name": "workflow_run_history_to_failure_modes",
                        "lifecycle_posture": "keep",
                        "priority": "P2",
                    },
                ],
                "governance_posture_counts": {
                    "keep": 1,
                    "refine": 1,
                },
                "change_candidate_ids": [
                    "refine_strategy_front_door",
                    "stabilize_failure_diagnostics",
                ],
                "priority_workflows": ["task_to_workflow_strategy"],
                "authoritative_artifacts": [
                    "workflow_portfolio_operating_system",
                    "portfolio_operating_summary",
                    "portfolio_next_actions",
                    "workflow_lifecycle_matrix",
                    "portfolio_gap_analysis",
                    "portfolio_change_candidates",
                ],
                "next_action": "Keep governance publication explicit and hand the package to operators.",
                "publication_boundary": "operating_system_publication_only",
                "ready_for_publication": True,
            },
            "priority_workflows",
            ["task_to_workflow_strategy"],
        ),
        (
            RECURSIVE_IMPROVEMENT_SUMMARY_ARTIFACT,
            "recursive_improvement_summary.json",
            {
                "workflow_name": "company_operation_to_recursive_improvement_cycle",
                "focus_task_ids": ["recursive-alpha", "recursive-beta"],
                "focus_workflows": [
                    "workflow_portfolio_to_operating_system",
                    "workflow_and_eval_to_refined_workflow_package",
                ],
                "candidate_ids": [
                    "stabilize_portfolio_governance_handoff",
                    "refine_company_cycle_package_contract",
                ],
                "priority_item_ids": [
                    "stabilize_portfolio_governance_handoff",
                    "refine_company_cycle_package_contract",
                ],
                "priority_categories": [
                    "workflow_portfolio",
                    "workflow_package",
                ],
                "priority_category_counts": {
                    "workflow_portfolio": 1,
                    "workflow_package": 1,
                },
                "authoritative_artifacts": [
                    "recursive_improvement_cycle",
                    "recursive_improvement_summary",
                    "recursive_improvement_next_actions",
                    "company_pressure_map",
                    "recursive_improvement_priority_matrix",
                    "recursive_improvement_candidates",
                ],
                "next_action": "Keep recursive improvement publication explicit and operator-routed.",
                "publication_boundary": "recursive_improvement_publication_only",
                "ready_for_publication": True,
            },
            "workflow_name",
            "company_operation_to_recursive_improvement_cycle",
        ),
        (
            CANDIDATE_WORKFLOW_SET_SUMMARY_ARTIFACT,
            "candidate_workflow_set_summary.json",
            {
                "comparison_candidates": [
                    "security_finding_to_verified_remediation",
                    "investigation_request_to_evidence_pack",
                    "workflow_idea_to_workflow_package",
                ],
                "ranked_candidates": [
                    "security_finding_to_verified_remediation",
                    "investigation_request_to_evidence_pack",
                    "workflow_idea_to_workflow_package",
                ],
                "recommended_candidate_workflows": ["security_finding_to_verified_remediation"],
                "builder_baseline_workflow": "workflow_idea_to_workflow_package",
                "builder_considered": True,
                "portfolio_posture": "direct_fit",
                "authoritative_artifacts": [
                    "candidate_workflow_set",
                    "candidate_workflow_set_summary",
                    "candidate_next_action",
                ],
                "next_action": "Pass this candidate package to task_to_workflow_strategy.",
                "ready_for_strategy_selection": True,
            },
            "portfolio_posture",
            "direct_fit",
        ),
        (
            ADAPTED_EXECUTION_SUMMARY_ARTIFACT,
            "adapted_execution_summary.json",
            {
                "selected_workflow_name": "security_finding_to_verified_remediation",
                "selected_workflow_entry_step": "bootstrap",
                "selected_workflow_parameters_supported": True,
                "proposed_parameter_keys": ["finding_title", "finding_source"],
                "expected_downstream_artifacts": [
                    "selected_remediation_plan",
                    "remediation_summary",
                    "security_remediation_package",
                ],
                "authoritative_artifacts": [
                    "adapted_execution_plan",
                    "adapted_execution_summary",
                    "adapted_execution_next_action",
                    "validated_workflow_parameters",
                ],
                "next_action": "Run the selected workflow with the validated parameters.",
                "ready_for_execution": True,
            },
            "selected_workflow_entry_step",
            "bootstrap",
        ),
        (
            FAILURE_MODE_MANIFEST_ARTIFACT,
            "failure_mode_manifest.json",
            {
                "selected_workflow_name": "release_candidate_to_go_no_go",
                "evidence_run_ids": ["run-1", "run-2"],
                "failure_mode_ids": ["clarification_loops"],
                "failure_modes": [
                    {
                        "failure_mode_id": "clarification_loops",
                        "title": "Clarification loops stall decision publication",
                        "severity": "high",
                        "evidence_run_ids": ["run-1", "run-2"],
                        "symptom_pattern": "Ownership clarifications keep blocking publication.",
                        "likely_causes": ["The request contract leaves ownership vague."],
                        "supporting_signals": ["Blocked runs cluster on the same clarification thread."],
                    }
                ],
                "recurring_weak_point_ids": ["request_contract_drift"],
                "workflow_name": "workflow_run_history_to_failure_modes",
            },
            "workflow_name",
            "workflow_run_history_to_failure_modes",
        ),
        (
            IMPROVEMENT_OPPORTUNITIES_SUMMARY_ARTIFACT,
            "improvement_opportunities.json",
            {
                "selected_workflow_name": "release_candidate_to_go_no_go",
                "evidence_run_ids": ["run-1", "run-2"],
                "failure_mode_ids": ["clarification_loops"],
                "ranked_opportunity_ids": ["tighten_request_contract"],
                "opportunities": [
                    {
                        "opportunity_id": "tighten_request_contract",
                        "title": "Tighten the request contract before evidence assembly starts",
                        "priority": "P1",
                        "linked_failure_mode_ids": ["clarification_loops"],
                        "recommended_next_step": "workflow_and_eval_to_refined_workflow_package",
                        "why_now": "Repeated blocked runs show the same ambiguity cost.",
                        "expected_impact": "Reduces clarification stalls before publication.",
                    }
                ],
                "authoritative_artifacts": [
                    "improvement_opportunities",
                    "improvement_opportunities_summary",
                    "diagnostic_next_actions",
                    "failure_mode_map",
                    "failure_mode_manifest",
                    "recurring_weak_points",
                ],
                "next_action": "Recommend a refinement pass and rerun diagnostics later.",
                "publication_boundary": "diagnostic_publication_only",
                "ready_for_publication": True,
                "workflow_name": "workflow_run_history_to_failure_modes",
            },
            "workflow_name",
            "workflow_run_history_to_failure_modes",
        ),
        (
            WORKFLOW_EVAL_SUITE_SUMMARY_ARTIFACT,
            "workflow_eval_suite_summary.json",
            {
                "selected_workflow_name": "release_candidate_to_go_no_go",
                "selected_workflow_entry_step": "bootstrap",
                "selected_workflow_parameters_supported": True,
                "case_count": 3,
                "case_ids": [
                    "baseline_release_gate",
                    "edge_missing_owner",
                    "adversarial_rollback_gap",
                ],
                "case_kinds": ["benchmark", "edge", "adversarial"],
                "covered_expected_artifacts": [
                    "blocking_issues",
                    "decision_summary",
                    "release_decision_package",
                ],
                "authoritative_artifacts": [
                    "workflow_eval_suite",
                    "workflow_eval_suite_summary",
                    "workflow_eval_next_action",
                    "validated_eval_case_manifest",
                    "eval_rubric",
                ],
                "next_action": "Run the evaluation harness with the validated manifest and rubric.",
                "ready_for_publication": True,
            },
            "case_count",
            3,
        ),
    ),
)
def test_split_summary_artifact_specs_match_on_disk_json_shapes(
    tmp_path: Path,
    artifact_spec: JsonArtifactSpec,
    filename: str,
    payload: dict[str, object],
    expected_field: str,
    expected_value: object,
) -> None:
    path = tmp_path / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    artifact = artifact_spec.read(path)

    assert getattr(artifact, expected_field) == expected_value
    assert artifact_spec.validate(path).ok is True
@pytest.mark.parametrize(
    ("artifact_spec", "filename", "payload", "expected_issue_locations"),
    (
        (
            PORTFOLIO_OPERATING_SUMMARY_ARTIFACT,
            "portfolio_operating_summary.json",
            {
                "focus_workflows": ["task_to_workflow_strategy"],
                "analyzed_workflows": ["task_to_workflow_strategy"],
                "lifecycle_recommendations": [
                    {
                        "workflow_name": "task_to_workflow_strategy",
                        "lifecycle_posture": "refine",
                        "priority": "P1",
                    }
                ],
                "governance_posture_counts": {"refine": 1},
                "change_candidate_ids": ["refine_strategy_front_door"],
                "priority_workflows": ["task_to_workflow_strategy"],
                "authoritative_artifacts": [
                    "workflow_portfolio_operating_system",
                    "portfolio_operating_summary",
                    "portfolio_next_actions",
                    "workflow_lifecycle_matrix",
                    "portfolio_gap_analysis",
                    "portfolio_change_candidates",
                ],
                "next_action": "Keep governance publication explicit and operator-routed.",
                "ready_for_publication": True,
            },
            {("publication_boundary",)},
        ),
        (
            RECURSIVE_IMPROVEMENT_SUMMARY_ARTIFACT,
            "recursive_improvement_summary.json",
            {
                "workflow_name": "company_operation_to_recursive_improvement_cycle",
                "focus_task_ids": ["recursive-alpha"],
                "focus_workflows": ["workflow_portfolio_to_operating_system"],
                "candidate_ids": ["stabilize_portfolio_governance_handoff"],
                "priority_item_ids": ["stabilize_portfolio_governance_handoff"],
                "priority_categories": ["workflow_portfolio"],
                "authoritative_artifacts": [
                    "recursive_improvement_cycle",
                    "recursive_improvement_summary",
                    "recursive_improvement_next_actions",
                    "company_pressure_map",
                    "recursive_improvement_priority_matrix",
                    "recursive_improvement_candidates",
                ],
                "next_action": "Keep recursive improvement publication explicit and operator-routed.",
                "publication_boundary": "recursive_improvement_publication_only",
                "ready_for_publication": True,
            },
            {("priority_category_counts",)},
        ),
        (
            FAILURE_MODE_MANIFEST_ARTIFACT,
            "failure_mode_manifest.json",
            {
                "selected_workflow_name": "release_candidate_to_go_no_go",
                "evidence_run_ids": ["run-1"],
                "failure_mode_ids": ["clarification_loops"],
                "recurring_weak_point_ids": ["request_contract_drift"],
                "workflow_name": "workflow_run_history_to_failure_modes",
            },
            {("failure_modes",)},
        ),
        (
            IMPROVEMENT_OPPORTUNITIES_SUMMARY_ARTIFACT,
            "improvement_opportunities.json",
            {
                "selected_workflow_name": "release_candidate_to_go_no_go",
                "evidence_run_ids": ["run-1"],
                "failure_mode_ids": ["clarification_loops"],
                "ranked_opportunity_ids": ["tighten_request_contract"],
                "opportunities": [
                    {
                        "opportunity_id": "tighten_request_contract",
                        "title": "Tighten the request contract before evidence assembly starts",
                        "priority": "P1",
                        "linked_failure_mode_ids": ["clarification_loops"],
                        "recommended_next_step": "workflow_and_eval_to_refined_workflow_package",
                        "why_now": "Repeated blocked runs show the same ambiguity cost.",
                        "expected_impact": "Reduces clarification stalls before publication.",
                    }
                ],
                "authoritative_artifacts": [
                    "improvement_opportunities",
                    "improvement_opportunities_summary",
                    "diagnostic_next_actions",
                    "failure_mode_map",
                    "failure_mode_manifest",
                    "recurring_weak_points",
                ],
                "next_action": "Recommend a refinement pass and rerun diagnostics later.",
                "publication_boundary": "diagnostic_publication_only",
                "workflow_name": "workflow_run_history_to_failure_modes",
            },
            {("ready_for_publication",)},
        ),
    ),
)
def test_typed_publication_artifact_specs_report_missing_required_fields(
    tmp_path: Path,
    artifact_spec: JsonArtifactSpec,
    filename: str,
    payload: dict[str, object],
    expected_issue_locations: set[tuple[str, ...]],
) -> None:
    path = tmp_path / filename
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = artifact_spec.validate(path)

    assert report.ok is False
    assert {issue.location for issue in report.issues} >= expected_issue_locations
def test_route_helpers_return_explicit_normalized_bundles() -> None:
    review_routes = {
        "approved": Route.to("publish", summary="The review boundary is complete.", required_writes=["review_report"]),
        "needs_revision": Route.to(
            SELF,
            summary="The review boundary needs local repair.",
            required_writes=["review_report"],
        ),
    }
    publish_routes = {
        "published": Route.finish(required_writes=["publish_receipt"]),
    }

    assert tuple(review_routes) == ("approved", "needs_revision")
    assert isinstance(review_routes["approved"], Route)
    assert review_routes["approved"].required_writes == ("review_report",)
    assert "review boundary" in (review_routes["needs_revision"].summary or "")
    assert tuple(publish_routes) == ("published",)
    assert publish_routes["published"].required_writes == ("publish_receipt",)

    assert json_artifact_helpers.JsonArtifactSpec is JsonArtifactSpec
def test_sequence_cursor_advances_without_hidden_state() -> None:
    cursor = SequenceCursor.from_items(["phase-a", "phase-b"])

    assert cursor.current is None
    assert cursor.peek() == "phase-a"

    cursor = cursor.advance()
    assert cursor.current == "phase-a"
    assert cursor.peek() == "phase-b"

    cursor = cursor.advance()
    assert cursor.current == "phase-b"
    assert cursor.peek() is None
    assert cursor.advance() == cursor
    assert cursor.reset().current is None
def test_lifecycle_helpers_open_declared_sessions_and_write_workflow_local_json(tmp_path: Path) -> None:
    ctx = _build_lifecycle_context(tmp_path)

    open_workflow_sessions(ctx, "frame_session", "verify_session")
    target_path = write_workflow_json(ctx, "nested/summary.json", {"published": True, "count": 2})

    assert ctx.get_session("frame_session") is not None
    assert ctx.get_session("verify_session") is not None
    assert target_path == ctx.workflow_folder / "nested" / "summary.json"
    assert json.loads(target_path.read_text(encoding="utf-8")) == {"count": 2, "published": True}

    with pytest.raises(ValueError, match="ctx.workflow_folder"):
        write_workflow_json(ctx, "../escape.json", {"bad": True})
    with pytest.raises(ValueError, match="\\.json"):
        write_publication_receipt(ctx, "receipt.md", {"published": True})
def test_lifecycle_helpers_write_canonical_invocation_contract_and_publication_receipt(tmp_path: Path) -> None:
    ctx = _build_lifecycle_context(tmp_path)

    invocation_path = write_invocation_contract(
        ctx,
        {
            "release_name": "2026.04",
            "deployment_environment": "production",
            "evidence_paths": ["docs/releases/2026.04.md"],
        },
    )
    receipt_path = write_publication_receipt(
        ctx,
        "decision_receipt.json",
        {
            "workflow_name": ctx.workflow_name,
            "release_name": "2026.04",
            "published": True,
        },
    )

    assert invocation_path == ctx.workflow_folder / "invocation_contract.json"
    assert json.loads(invocation_path.read_text(encoding="utf-8")) == {
        "deployment_environment": "production",
        "evidence_paths": ["docs/releases/2026.04.md"],
        "message": "Ship release 2026.04.\n",
        "release_name": "2026.04",
        "request_file": str(ctx.run_folder / "request.md"),
        "run_id": "run-1",
        "task_id": "task-1",
        "workflow_name": "release_candidate_to_go_no_go",
    }
    assert receipt_path == ctx.workflow_folder / "decision_receipt.json"
    assert json.loads(receipt_path.read_text(encoding="utf-8")) == {
        "published": True,
        "release_name": "2026.04",
        "workflow_name": "release_candidate_to_go_no_go",
    }
def test_lifecycle_helper_invocation_contract_keeps_ctx_owned_identity_fields_authoritative(tmp_path: Path) -> None:
    ctx = _build_lifecycle_context(tmp_path)

    invocation_path = write_invocation_contract(
        ctx,
        {
            "workflow_name": "wrong_workflow",
            "task_id": "wrong-task",
            "run_id": "wrong-run",
            "request_file": "/tmp/wrong-request.md",
            "message": "wrong message",
            "release_name": "2026.04",
        },
    )

    assert json.loads(invocation_path.read_text(encoding="utf-8")) == {
        "message": "Ship release 2026.04.\n",
        "release_name": "2026.04",
        "request_file": str(ctx.run_folder / "request.md"),
        "run_id": "run-1",
        "task_id": "task-1",
        "workflow_name": "release_candidate_to_go_no_go",
    }
