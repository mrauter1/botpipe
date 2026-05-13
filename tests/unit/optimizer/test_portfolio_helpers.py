from __future__ import annotations

from tests.unit._stdlib_and_extensions_shared import (
    _assert_mapping_contains,
    _build_lifecycle_context,
    _write_catalog_workflow,
    _write_run_history_record,
    _write_runtime_valid_catalog_workflow,
    _write_single_file_runtime_workflow,
    _write_task_operation_record,
)
from tests.unit._stdlib_and_extensions_shared import *

def test_portfolio_helper_writes_workflow_local_catalog_snapshot(tmp_path: Path) -> None:
    ctx = _build_lifecycle_context(tmp_path)
    release_package = _write_catalog_workflow(
        tmp_path,
        "release_candidate_to_go_no_go",
        aliases=("release_decision",),
        export_parameters=True,
        write_doc=True,
    )
    incident_package = _write_catalog_workflow(
        tmp_path,
        "incident_to_hardening_program",
        aliases=("incident_hardening",),
    )

    snapshot_path = write_workflow_portfolio_snapshot(ctx, "catalog/workflow_portfolio_snapshot.json")

    assert snapshot_path == ctx.workflow_folder / "catalog" / "workflow_portfolio_snapshot.json"
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert payload["repo_root"] == str(tmp_path.resolve())
    assert payload["run_id"] == "run-1"
    assert payload["task_id"] == "task-1"
    assert payload["workflow_count"] == 2
    assert payload["workflow_name"] == "release_candidate_to_go_no_go"
    incident_entry = next(entry for entry in payload["workflows"] if entry["workflow_name"] == "incident_to_hardening_program")
    release_entry = next(entry for entry in payload["workflows"] if entry["workflow_name"] == "release_candidate_to_go_no_go")
    _assert_mapping_contains(
        incident_entry,
        {
            "aliases": ["incident_hardening"],
            "authoring_shape": "manifest_package",
            "description": "Workflow description.",
            "doc_path": None,
            "manifest_path": str(incident_package / "workflow.toml"),
            "package_dir": str(incident_package),
            "package_name": "incident_to_hardening_program",
            "params_path": None,
            "source_path": str(incident_package / "workflow.py"),
            "title": "Incident To Hardening Program",
            "workflow_path": str(incident_package / "workflow.py"),
        },
    )
    _assert_mapping_contains(
        release_entry,
        {
            "aliases": ["release_decision"],
            "authoring_shape": "manifest_package",
            "description": "Workflow description.",
            "doc_path": str(release_package / "README.md"),
            "manifest_path": str(release_package / "workflow.toml"),
            "package_dir": str(release_package),
            "package_name": "release_candidate_to_go_no_go",
            "params_path": str(release_package / "params.py"),
            "source_path": str(release_package / "workflow.py"),
            "title": "Release Candidate To Go No Go",
            "workflow_path": str(release_package / "workflow.py"),
        },
    )

    with pytest.raises(ValueError, match="ctx.workflow_folder"):
        write_workflow_portfolio_snapshot(ctx, "../escape.json")
    with pytest.raises(ValueError, match="\\.json"):
        write_workflow_portfolio_snapshot(ctx, "portfolio.md")
def test_portfolio_helpers_keep_catalog_snapshot_lightweight_and_capability_snapshot_rich(tmp_path: Path) -> None:
    ctx = _build_lifecycle_context(tmp_path)
    _write_runtime_valid_catalog_workflow(
        tmp_path,
        "release_candidate_to_go_no_go",
        aliases=("release_decision",),
        export_parameters=True,
        write_doc=True,
    )
    _write_runtime_valid_catalog_workflow(
        tmp_path,
        "incident_to_hardening_program",
        aliases=("incident_hardening",),
    )

    portfolio_path = write_workflow_portfolio_snapshot(ctx, "catalog/workflow_portfolio_snapshot.json")
    capability_path = write_workflow_capability_snapshot(ctx, "capabilities/workflow_capability_snapshot.json")
    portfolio = json.loads(portfolio_path.read_text(encoding="utf-8"))
    capability = json.loads(capability_path.read_text(encoding="utf-8"))

    portfolio_entry = next(
        entry for entry in portfolio["workflows"] if entry["workflow_name"] == "release_candidate_to_go_no_go"
    )
    capability_entry = next(
        entry for entry in capability["workflows"] if entry["workflow_name"] == "release_candidate_to_go_no_go"
    )

    assert "parameters" not in portfolio_entry
    assert "steps" not in portfolio_entry
    assert portfolio_entry["authoring_shape"] == "manifest_package"
    assert portfolio_entry["source_path"].endswith("/workflows/release_candidate_to_go_no_go/workflow.py")
    assert capability["workflow_count"] == 2
    assert capability_entry["workflow_class"] == "ReleaseCandidateToGoNoGo"
    assert capability_entry["authoring_shape"] == "manifest_package"
    assert capability_entry["parameters_model"].endswith("Params")
    assert capability_entry["state_model"].endswith("ReleaseCandidateToGoNoGo.State")
    assert capability_entry["parameters_supported"] is True
    assert capability_entry["parameters"] == [
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
    assert capability_entry["entry_step_name"] == "assess"
    assert capability_entry["prompt_paths"] == [
        str(tmp_path / "workflows" / "release_candidate_to_go_no_go" / "prompts" / "assess_producer.md"),
        str(tmp_path / "workflows" / "release_candidate_to_go_no_go" / "prompts" / "assess_verifier.md"),
    ]
    assert capability_entry["global_routes"] == {}
    assert capability_entry["routes"] == {
        "global": {},
        "steps": {
            "assess": {
                "assessment_complete": "FINISH",
                "needs_rework": "assess",
                "question": "AWAIT_INPUT",
            }
        },
    }
    assert len(capability_entry["steps"]) == 1
    _assert_mapping_contains(
        capability_entry["steps"][0],
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
        write_workflow_capability_snapshot(ctx, "../escape.json")
    with pytest.raises(ValueError, match="\\.json"):
        write_workflow_capability_snapshot(ctx, "capabilities.md")
def test_capability_snapshot_imports_workflows_while_lightweight_portfolio_snapshot_stays_non_importing(
    tmp_path: Path,
) -> None:
    ctx = _build_lifecycle_context(tmp_path)
    broken_package = _write_catalog_workflow(
        tmp_path,
        "broken_workflow",
        aliases=("broken",),
        export_parameters=True,
        write_doc=True,
    )
    (broken_package / "workflow.py").write_text(
        'raise RuntimeError("capability inspection imports workflow modules")\n',
        encoding="utf-8",
    )

    portfolio_path = write_workflow_portfolio_snapshot(ctx, "catalog/workflow_portfolio_snapshot.json")
    portfolio = json.loads(portfolio_path.read_text(encoding="utf-8"))

    assert portfolio["workflow_count"] == 1
    _assert_mapping_contains(
        portfolio["workflows"][0],
        {
            "aliases": ["broken"],
            "authoring_shape": "manifest_package",
            "description": "Workflow description.",
            "doc_path": str(broken_package / "README.md"),
            "manifest_path": str(broken_package / "workflow.toml"),
            "package_dir": str(broken_package),
            "package_name": "broken_workflow",
            "params_path": str(broken_package / "params.py"),
            "source_path": str(broken_package / "workflow.py"),
            "title": "Broken Workflow",
            "workflow_path": str(broken_package / "workflow.py"),
        },
    )

    with pytest.raises(RuntimeError, match="capability inspection imports workflow modules"):
        write_workflow_capability_snapshot(ctx, "capabilities/workflow_capability_snapshot.json")
def test_portfolio_health_helper_writes_grouped_workflow_run_health_via_shared_resolution_and_run_summaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _build_lifecycle_context(tmp_path, workflow_name="workflow_portfolio_to_operating_system")
    release_package = _write_runtime_valid_catalog_workflow(
        tmp_path,
        "release_candidate_to_go_no_go",
        aliases=("release_decision",),
    )
    incident_package = _write_runtime_valid_catalog_workflow(
        tmp_path,
        "incident_to_hardening_program",
        aliases=("incident_hardening",),
    )
    builder_package = _write_runtime_valid_catalog_workflow(
        tmp_path,
        "workflow_idea_to_workflow_package",
        aliases=("workflow_builder",),
    )
    broken_package = _write_catalog_workflow(
        tmp_path,
        "broken_workflow",
        aliases=("broken",),
        export_parameters=True,
        write_doc=True,
    )
    (broken_package / "workflow.py").write_text(
        'raise RuntimeError("portfolio health helper imported an unrelated workflow")\n',
        encoding="utf-8",
    )

    release_paused_dir = _write_run_history_record(
        tmp_path,
        task_id="task-1",
        workflow_name="release_candidate_to_go_no_go",
        run_id="run-paused",
        status="paused",
        created_at="2026-04-24T06:00:00+00:00",
        updated_at="2026-04-24T06:03:00+00:00",
        request_text="  Investigate the paused release.\nNeed the go/no-go owner.\n",
        pending_question="Who approves the release?",
    )
    release_failed_dir = _write_run_history_record(
        tmp_path,
        task_id="task-2",
        workflow_name="release_candidate_to_go_no_go",
        run_id="run-failed",
        status="failed",
        created_at="2026-04-24T06:00:00+00:00",
        updated_at="2026-04-24T06:02:00+00:00",
        request_text="Investigate the failed release.\n",
        terminal="FAIL",
        error="verification mismatch",
    )
    _write_run_history_record(
        tmp_path,
        task_id="task-3",
        workflow_name="release_candidate_to_go_no_go",
        run_id="run-success",
        status="success",
        created_at="2026-04-24T06:00:00+00:00",
        updated_at="2026-04-24T06:01:00+00:00",
        request_text="Routine release follow-up.\n",
    )
    incident_failed_dir = _write_run_history_record(
        tmp_path,
        task_id="task-4",
        workflow_name="incident_to_hardening_program",
        run_id="run-incident-failed",
        status="failed",
        created_at="2026-04-24T06:00:00+00:00",
        updated_at="2026-04-24T06:04:00+00:00",
        request_text="Investigate the failed incident hardening plan.\n",
        terminal="FAIL",
        error="missing owner",
    )
    _write_run_history_record(
        tmp_path,
        task_id="task-5",
        workflow_name="broken_workflow",
        run_id="run-broken",
        status="failed",
        created_at="2026-04-24T06:00:00+00:00",
        updated_at="2026-04-24T06:05:00+00:00",
        request_text="Ignore the broken workflow.\n",
    )

    before_files = {
        str(path.relative_to(tmp_path)): path.read_text(encoding="utf-8")
        for path in (
            release_package / "__init__.py",
            release_package / "workflow.toml",
            release_package / "workflow.py",
            incident_package / "__init__.py",
            incident_package / "workflow.toml",
            incident_package / "workflow.py",
            builder_package / "__init__.py",
            builder_package / "workflow.toml",
            builder_package / "workflow.py",
            release_paused_dir / "run.json",
            release_paused_dir / "request.md",
            release_failed_dir / "run.json",
            incident_failed_dir / "run.json",
        )
    }
    resolve_calls: list[tuple[Path, str | type[object]]] = []
    summary_calls: list[tuple[Path, tuple[str, ...] | None, object, int | None]] = []
    original_resolve = portfolio_helpers.resolve_workflow_reference
    original_summaries = portfolio_helpers.list_workflow_run_summaries

    def _record_resolve(root, workflow):
        resolve_calls.append((Path(root), workflow))
        return original_resolve(root, workflow)

    def _record_summaries(root, *, workflow_names=None, statuses=None, max_runs_per_workflow=None):
        normalized_names = None if workflow_names is None else tuple(workflow_names)
        summary_calls.append((Path(root), normalized_names, statuses, max_runs_per_workflow))
        return original_summaries(
            root,
            workflow_names=workflow_names,
            statuses=statuses,
            max_runs_per_workflow=max_runs_per_workflow,
        )

    monkeypatch.setattr(portfolio_helpers, "resolve_workflow_reference", _record_resolve)
    monkeypatch.setattr(portfolio_helpers, "list_workflow_run_summaries", _record_summaries)

    snapshot_path = write_workflow_portfolio_health_snapshot(
        ctx,
        workflows=["release_decision", "workflow_builder", "incident_hardening"],
        statuses=(status for status in ["failed", "paused", "failed"]),
        max_runs_per_workflow=1,
        relative_path="health/workflow_portfolio_health_snapshot.json",
    )

    assert resolve_calls == [
        (tmp_path.resolve(), "release_decision"),
        (tmp_path.resolve(), "workflow_builder"),
        (tmp_path.resolve(), "incident_hardening"),
    ]
    assert summary_calls == [
        (
            tmp_path.resolve(),
            (
                "incident_to_hardening_program",
                "release_candidate_to_go_no_go",
                "workflow_idea_to_workflow_package",
            ),
            ["awaiting_input", "failed"],
            1,
        )
    ]
    assert snapshot_path == ctx.workflow_folder / "health" / "workflow_portfolio_health_snapshot.json"
    assert json.loads(snapshot_path.read_text(encoding="utf-8")) == {
        "repo_root": str(tmp_path.resolve()),
        "run_id": "run-1",
        "task_id": "task-1",
        "workflow_name": "workflow_portfolio_to_operating_system",
        "workflow_portfolio_health": {
            "max_runs_per_workflow": 1,
            "selected_workflow_names": [
                "incident_to_hardening_program",
                "release_candidate_to_go_no_go",
                "workflow_idea_to_workflow_package",
            ],
            "statuses": ["awaiting_input", "failed"],
            "workflow_count": 3,
            "workflows": [
                {
                    "aliases": ["incident_hardening"],
                    "description": "Workflow description.",
                    "latest_run_id": "run-incident-failed",
                    "latest_updated_at": "2026-04-24T06:04:00+00:00",
                    "recent_runs": [
                        {
                            "created_at": "2026-04-24T06:00:00+00:00",
                            "error": "missing owner",
                            "finalization": None,
                            "pending_input": None,
                            "request_excerpt": "Investigate the failed incident hardening plan.",
                            "request_file": str(incident_failed_dir / "request.md"),
                            "run_folder": str(incident_failed_dir),
                            "run_id": "run-incident-failed",
                            "status": "failed",
                            "task_id": "task-4",
                            "terminal": "FAIL",
                            "updated_at": "2026-04-24T06:04:00+00:00",
                        }
                    ],
                    "run_count": 1,
                    "status_counts": {"failed": 1},
                    "title": "Incident To Hardening Program",
                    "workflow_name": "incident_to_hardening_program",
                },
                {
                    "aliases": ["release_decision"],
                    "description": "Workflow description.",
                    "latest_run_id": "run-paused",
                    "latest_updated_at": "2026-04-24T06:03:00+00:00",
                    "recent_runs": [
                        {
                            "created_at": "2026-04-24T06:00:00+00:00",
                            "error": None,
                            "finalization": None,
                            "pending_input": {"question": "Who approves the release?"},
                            "request_excerpt": "Investigate the paused release. Need the go/no-go owner.",
                            "request_file": str(release_paused_dir / "request.md"),
                            "run_folder": str(release_paused_dir),
                            "run_id": "run-paused",
                            "status": "awaiting_input",
                            "task_id": "task-1",
                            "terminal": None,
                            "updated_at": "2026-04-24T06:03:00+00:00",
                        }
                    ],
                    "run_count": 2,
                    "status_counts": {"awaiting_input": 1, "failed": 1},
                    "title": "Release Candidate To Go No Go",
                    "workflow_name": "release_candidate_to_go_no_go",
                },
                {
                    "aliases": ["workflow_builder"],
                    "description": "Workflow description.",
                    "latest_run_id": None,
                    "latest_updated_at": None,
                    "recent_runs": [],
                    "run_count": 0,
                    "status_counts": {},
                    "title": "Workflow Idea To Workflow Package",
                    "workflow_name": "workflow_idea_to_workflow_package",
                },
            ],
        },
    }
    assert {
        str(path.relative_to(tmp_path)): path.read_text(encoding="utf-8")
        for path in (
            release_package / "__init__.py",
            release_package / "workflow.toml",
            release_package / "workflow.py",
            incident_package / "__init__.py",
            incident_package / "workflow.toml",
            incident_package / "workflow.py",
            builder_package / "__init__.py",
            builder_package / "workflow.toml",
            builder_package / "workflow.py",
            release_paused_dir / "run.json",
            release_paused_dir / "request.md",
            release_failed_dir / "run.json",
            incident_failed_dir / "run.json",
        )
    } == before_files

    with pytest.raises(ValueError, match="ctx.workflow_folder"):
        write_workflow_portfolio_health_snapshot(ctx, relative_path="../escape.json")
    with pytest.raises(ValueError, match="\\.json"):
        write_workflow_portfolio_health_snapshot(ctx, relative_path="health.md")
    with pytest.raises(ValueError, match="positive integer"):
        write_workflow_portfolio_health_snapshot(ctx, max_runs_per_workflow=0)
    with pytest.raises(ValueError, match="statuses entries must be non-empty strings"):
        write_workflow_portfolio_health_snapshot(ctx, statuses=["failed", "  "])
    with pytest.raises(ValueError, match="at least one workflow reference"):
        write_workflow_portfolio_health_snapshot(ctx, workflows=[])
def test_company_helpers_write_bounded_company_operation_snapshot_without_mutating_current_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _build_lifecycle_context(tmp_path, workflow_name="company_operation_to_recursive_improvement_cycle")
    release_package = _write_runtime_valid_catalog_workflow(
        tmp_path,
        "release_candidate_to_go_no_go",
        aliases=("release_decision",),
    )
    incident_package = _write_runtime_valid_catalog_workflow(
        tmp_path,
        "incident_to_hardening_program",
        aliases=("incident_hardening",),
    )
    task_one_dir = _write_task_operation_record(
        tmp_path,
        task_id="task-1",
        created_at="2026-04-24T06:00:00+00:00",
        updated_at="2026-04-24T06:04:00+00:00",
        request_text="Investigate the paused release gate.\n",
        messages=[
            (
                "2026-04-24T06:01:00+00:00",
                "Customer escalation: reporting exports still disagree with the dashboard totals for the enterprise rollout and the release gate is blocked until that discrepancy is explained to operations.",
            ),
            (
                "2026-04-24T06:02:00+00:00",
                "Need the go/no-go owner before the release package can close.",
            ),
        ],
    )
    task_two_dir = _write_task_operation_record(
        tmp_path,
        task_id="task-2",
        created_at="2026-04-24T06:00:00+00:00",
        updated_at="2026-04-24T06:05:00+00:00",
        request_text="Recover the failed incident hardening package.\n",
        messages=[
            (
                "2026-04-24T06:03:00+00:00",
                "Need rollback owner before we can republish the failed package.",
            ),
        ],
    )
    release_paused_dir = _write_run_history_record(
        tmp_path,
        task_id="task-1",
        workflow_name="release_candidate_to_go_no_go",
        run_id="run-paused",
        status="paused",
        created_at="2026-04-24T06:00:00+00:00",
        updated_at="2026-04-24T06:04:00+00:00",
        request_text="Investigate the paused release gate.\n",
        pending_question="Who owns the release gate?",
    )
    incident_failed_dir = _write_run_history_record(
        tmp_path,
        task_id="task-2",
        workflow_name="incident_to_hardening_program",
        run_id="run-failed",
        status="failed",
        created_at="2026-04-24T06:00:00+00:00",
        updated_at="2026-04-24T06:05:00+00:00",
        request_text="Recover the failed incident hardening package.\n",
        terminal="FAIL",
        error="missing rollback owner",
    )

    before_files = {
        str(path.relative_to(tmp_path)): path.read_text(encoding="utf-8")
        for path in (
            release_package / "__init__.py",
            release_package / "workflow.toml",
            release_package / "workflow.py",
            incident_package / "__init__.py",
            incident_package / "workflow.toml",
            incident_package / "workflow.py",
            task_one_dir / "task.json",
            task_one_dir / "request.md",
            task_one_dir / "messages.jsonl",
            task_two_dir / "task.json",
            task_two_dir / "request.md",
            task_two_dir / "messages.jsonl",
            release_paused_dir / "run.json",
            release_paused_dir / "request.md",
            incident_failed_dir / "run.json",
            incident_failed_dir / "request.md",
        )
    }
    resolve_calls: list[tuple[Path, str | type[object]]] = []
    summary_calls: list[
        tuple[Path, tuple[str, ...] | None, tuple[str, ...] | None, object, int | None, int | None, int | None]
    ] = []
    original_resolve = company_helpers.resolve_workflow_reference
    original_summaries = company_helpers.list_task_operation_summaries

    def _record_resolve(root, workflow):
        resolve_calls.append((Path(root), workflow))
        return original_resolve(root, workflow)

    def _record_summaries(
        root,
        *,
        task_ids=None,
        workflow_names=None,
        statuses=None,
        max_tasks=None,
        max_runs_per_workflow=None,
        max_messages_per_task=None,
    ):
        normalized_task_ids = None if task_ids is None else tuple(task_ids)
        normalized_workflow_names = None if workflow_names is None else tuple(workflow_names)
        summary_calls.append(
            (
                Path(root),
                normalized_task_ids,
                normalized_workflow_names,
                statuses,
                max_tasks,
                max_runs_per_workflow,
                max_messages_per_task,
            )
        )
        return original_summaries(
            root,
            task_ids=task_ids,
            workflow_names=workflow_names,
            statuses=statuses,
            max_tasks=max_tasks,
            max_runs_per_workflow=max_runs_per_workflow,
            max_messages_per_task=max_messages_per_task,
        )

    monkeypatch.setattr(company_helpers, "resolve_workflow_reference", _record_resolve)
    monkeypatch.setattr(company_helpers, "list_task_operation_summaries", _record_summaries)

    snapshot_path = write_company_operation_snapshot(
        ctx,
        task_ids=["task-2", " task-1 ", "task-2"],
        workflows=["release_decision", "incident_hardening"],
        statuses=(status for status in ["failed", "paused", "failed"]),
        max_tasks=2,
        max_runs_per_workflow=1,
        max_messages_per_task=2,
        relative_path="company/company_operation_snapshot.json",
    )

    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))

    assert resolve_calls == [
        (tmp_path.resolve(), "release_decision"),
        (tmp_path.resolve(), "incident_hardening"),
    ]
    assert summary_calls == [
        (
            tmp_path.resolve(),
            ("task-1", "task-2"),
            ("incident_to_hardening_program", "release_candidate_to_go_no_go"),
            ["awaiting_input", "failed"],
            2,
            1,
            2,
        )
    ]
    assert snapshot_path == ctx.workflow_folder / "company" / "company_operation_snapshot.json"
    assert payload["repo_root"] == str(tmp_path.resolve())
    assert payload["run_id"] == "run-1"
    assert payload["task_id"] == "task-1"
    assert payload["workflow_name"] == "company_operation_to_recursive_improvement_cycle"
    assert payload["company_operation"]["max_messages_per_task"] == 2
    assert payload["company_operation"]["max_runs_per_workflow"] == 1
    assert payload["company_operation"]["max_tasks"] == 2
    assert payload["company_operation"]["selected_task_ids"] == ["task-1", "task-2"]
    assert payload["company_operation"]["selected_workflow_names"] == [
        "incident_to_hardening_program",
        "release_candidate_to_go_no_go",
    ]
    assert payload["company_operation"]["statuses"] == ["awaiting_input", "failed"]
    assert payload["company_operation"]["task_count"] == 2
    assert [entry["task_id"] for entry in payload["company_operation"]["tasks"]] == ["task-2", "task-1"]
    assert payload["company_operation"]["tasks"][0]["recent_messages"] == [
        {
            "message_excerpt": "Need rollback owner before we can republish the failed package.",
            "ts": "2026-04-24T06:03:00+00:00",
        }
    ]
    assert payload["company_operation"]["tasks"][0]["workflow_run_summaries"][0]["run_count"] == 1
    assert payload["company_operation"]["tasks"][0]["workflow_run_summaries"][1]["run_count"] == 0
    assert payload["company_operation"]["tasks"][1]["recent_messages"][0] == {
        "message_excerpt": "Need the go/no-go owner before the release package can close.",
        "ts": "2026-04-24T06:02:00+00:00",
    }
    assert payload["company_operation"]["tasks"][1]["recent_messages"][1]["ts"] == "2026-04-24T06:01:00+00:00"
    assert payload["company_operation"]["tasks"][1]["recent_messages"][1]["message_excerpt"].startswith(
        "Customer escalation: reporting exports still disagree"
    )
    assert payload["company_operation"]["tasks"][1]["recent_messages"][1]["message_excerpt"].endswith("...")
    assert payload["company_operation"]["tasks"][1]["workflow_run_summaries"][0]["run_count"] == 0
    assert payload["company_operation"]["tasks"][1]["workflow_run_summaries"][1]["run_count"] == 1
    assert len(payload["company_operation"]["tasks"][1]["recent_messages"][1]["message_excerpt"]) == 160
    assert {
        str(path.relative_to(tmp_path)): path.read_text(encoding="utf-8")
        for path in (
            release_package / "__init__.py",
            release_package / "workflow.toml",
            release_package / "workflow.py",
            incident_package / "__init__.py",
            incident_package / "workflow.toml",
            incident_package / "workflow.py",
            task_one_dir / "task.json",
            task_one_dir / "request.md",
            task_one_dir / "messages.jsonl",
            task_two_dir / "task.json",
            task_two_dir / "request.md",
            task_two_dir / "messages.jsonl",
            release_paused_dir / "run.json",
            release_paused_dir / "request.md",
            incident_failed_dir / "run.json",
            incident_failed_dir / "request.md",
        )
    } == before_files

    with pytest.raises(ValueError, match="ctx.workflow_folder"):
        write_company_operation_snapshot(ctx, relative_path="../escape.json")
    with pytest.raises(ValueError, match="\\.json"):
        write_company_operation_snapshot(ctx, relative_path="company.md")
    with pytest.raises(ValueError, match="positive integer"):
        write_company_operation_snapshot(ctx, max_tasks=0)
    with pytest.raises(ValueError, match="task_ids entries must be non-empty strings"):
        write_company_operation_snapshot(ctx, task_ids=["task-1", "  "])
    with pytest.raises(ValueError, match="statuses entries must be non-empty strings"):
        write_company_operation_snapshot(ctx, statuses=["failed", "  "])
    with pytest.raises(ValueError, match="at least one workflow reference"):
        write_company_operation_snapshot(ctx, workflows=[])
def test_company_helper_accepts_single_file_workflow_references(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = _build_lifecycle_context(tmp_path, workflow_name="company_operation_to_recursive_improvement_cycle")
    workflow_path = _write_single_file_runtime_workflow(tmp_path)
    summary_calls: list[
        tuple[Path, tuple[str, ...] | None, tuple[str, ...] | None, list[str] | None, int | None, int | None, int | None]
    ] = []

    def _record_summaries(
        root,
        *,
        task_ids=None,
        workflow_names=None,
        statuses=None,
        max_tasks=None,
        max_runs_per_workflow=None,
        max_messages_per_task=None,
    ):
        normalized_task_ids = None if task_ids is None else tuple(task_ids)
        normalized_workflow_names = None if workflow_names is None else tuple(workflow_names)
        normalized_statuses = None if statuses is None else list(statuses)
        summary_calls.append(
            (
                Path(root),
                normalized_task_ids,
                normalized_workflow_names,
                normalized_statuses,
                max_tasks,
                max_runs_per_workflow,
                max_messages_per_task,
            )
        )
        return ()

    monkeypatch.setattr(company_helpers, "list_task_operation_summaries", _record_summaries)

    snapshot_path = write_company_operation_snapshot(
        ctx,
        workflows=[str(workflow_path)],
        relative_path="company/single_file_company_operation_snapshot.json",
    )

    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))

    assert summary_calls == [
        (tmp_path.resolve(), None, ("single_file_review",), None, None, None, None)
    ]
    assert snapshot_path == ctx.workflow_folder / "company" / "single_file_company_operation_snapshot.json"
    assert payload["company_operation"]["selected_workflow_names"] == ["single_file_review"]
    assert payload["company_operation"]["task_count"] == 0
