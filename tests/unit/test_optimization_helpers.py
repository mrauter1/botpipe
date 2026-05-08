from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from botlane_optimizer.optimization import (
    OptimizationArtifactSpec,
    build_step_trace_metrics,
    collect_optimization_publication_surface,
    extract_failure_scenario_seeds,
    finalize_optional_optimization_artifact,
    list_selected_workflow_runs,
    load_run_observability_bundle,
    normalize_trace_corpus,
    parse_run_ref,
    rank_optimization_targets,
    validate_optimization_scorecard_publication,
    validate_observability_bundle,
    validate_selected_workflow_source_unchanged,
    write_optimization_refinement_evidence,
    write_selected_workflow_source_manifest,
)
from botlane.core.schema_registry import RUN_METADATA_SCHEMA


def test_parse_run_ref_accepts_task_slash_run() -> None:
    assert parse_run_ref("task-123/run-456") == ("task-123", "run-456")


@pytest.mark.parametrize("raw", ("", "task-only", "task/run/extra", "/run", "task/"))
def test_parse_run_ref_rejects_invalid_shapes(raw: str) -> None:
    with pytest.raises(ValueError):
        parse_run_ref(raw)


def test_list_selected_workflow_runs_filters_by_workflow_and_status(tmp_path: Path) -> None:
    _write_minimal_run_metadata(tmp_path, "task-1", "release_candidate_to_go_no_go", "run-failed", "failed")
    _write_minimal_run_metadata(tmp_path, "task-2", "release_candidate_to_go_no_go", "run-success", "success")
    _write_minimal_run_metadata(tmp_path, "task-3", "incident_to_hardening_program", "run-other", "failed")

    runs = list_selected_workflow_runs(
        tmp_path,
        "release_candidate_to_go_no_go",
        run_refs=[],
        run_statuses=["failed", "awaiting_input"],
        history_limit=10,
    )

    assert runs == [
        tmp_path
        / ".botlane"
        / "tasks"
        / "task-1"
        / "wf_release_candidate_to_go_no_go"
        / "runs"
        / "run-failed"
    ]


def test_explicit_run_refs_select_exact_runs(tmp_path: Path) -> None:
    run_one = _write_minimal_run_metadata(
        tmp_path,
        "task-1",
        "release_candidate_to_go_no_go",
        "run-one",
        "failed",
    )
    _write_minimal_run_metadata(tmp_path, "task-2", "release_candidate_to_go_no_go", "run-two", "failed")

    runs = list_selected_workflow_runs(
        tmp_path,
        "release_candidate_to_go_no_go",
        run_refs=["task-1/run-one"],
        run_statuses=["failed"],
        history_limit=10,
    )

    assert runs == [run_one]


def test_load_run_observability_bundle_requires_run_json_trace_static_graph_git_tracking_and_raw(tmp_path: Path) -> None:
    run_dir = _write_observable_run(tmp_path, "task-1", "release_candidate_to_go_no_go", "run-good")

    bundle = load_run_observability_bundle(run_dir)

    assert validate_observability_bundle(bundle) == (True, None)
    assert bundle.run_json is not None
    assert bundle.trace_records is not None
    assert bundle.git_tracking_records is not None
    assert bundle.static_step_graph is not None


def test_missing_plan1_files_exclude_run_with_reason(tmp_path: Path) -> None:
    run_dir = _write_minimal_run_metadata(
        tmp_path,
        "task-1",
        "release_candidate_to_go_no_go",
        "run-old",
        "failed",
    )
    (run_dir / "git_tracking.jsonl").write_text("", encoding="utf-8")
    (run_dir / "static_step_graph.json").write_text("{}", encoding="utf-8")
    (run_dir / "raw").mkdir(parents=True, exist_ok=True)

    bundle = load_run_observability_bundle(run_dir)

    assert validate_observability_bundle(bundle) == (False, "missing_trace_jsonl")


def test_load_run_observability_bundle_accepts_legacy_runtime_observability_payloads_without_schema(tmp_path: Path) -> None:
    run_dir = _write_observable_run(tmp_path, "task-1", "release_candidate_to_go_no_go", "run-legacy-schema-less")
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    run_payload.pop("schema", None)
    (run_dir / "run.json").write_text(json.dumps(run_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    trace_records = [
        json.loads(line)
        for line in (run_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for record in trace_records:
        record.pop("schema", None)
    (run_dir / "trace.jsonl").write_text(
        "\n".join(json.dumps(record, sort_keys=True) for record in trace_records) + "\n",
        encoding="utf-8",
    )

    git_records = [
        json.loads(line)
        for line in (run_dir / "git_tracking.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for record in git_records:
        record.pop("schema", None)
    (run_dir / "git_tracking.jsonl").write_text(
        "\n".join(json.dumps(record, sort_keys=True) for record in git_records) + "\n",
        encoding="utf-8",
    )

    static_graph_payload = json.loads((run_dir / "static_step_graph.json").read_text(encoding="utf-8"))
    static_graph_payload.pop("schema", None)
    (run_dir / "static_step_graph.json").write_text(
        json.dumps(static_graph_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    bundle = load_run_observability_bundle(run_dir)

    assert validate_observability_bundle(bundle) == (True, None)
    assert bundle.load_error is None


def test_load_run_observability_bundle_rejects_explicit_unsupported_runtime_schema_ids(tmp_path: Path) -> None:
    run_dir = _write_observable_run(tmp_path, "task-1", "release_candidate_to_go_no_go", "run-unknown-schema")
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    run_payload["schema"] = RUN_METADATA_SCHEMA.replace("/v1", "/v2")
    (run_dir / "run.json").write_text(json.dumps(run_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    bundle = load_run_observability_bundle(run_dir)

    assert bundle.load_error is not None
    assert "unsupported schema" in bundle.load_error
    assert validate_observability_bundle(bundle) == (False, "unreadable_observability_files")


def test_normalize_trace_corpus_preserves_raw_refs_and_git_commits(tmp_path: Path) -> None:
    run_dir = _write_observable_run(tmp_path, "task-1", "release_candidate_to_go_no_go", "run-good")

    corpus = normalize_trace_corpus(
        selected_workflow="release_candidate_to_go_no_go",
        run_dirs=[run_dir],
        route_tags=["needs_rework", "failed"],
    )

    assert corpus["candidate_run_count"] == 1
    assert corpus["eligible_run_count"] == 1
    assert corpus["excluded_run_count"] == 0
    assert corpus["step_observation_count"] == 1
    assert corpus["runs"][0]["commit_before_run"] == "commit-before-run"
    assert corpus["runs"][0]["commit_after_run"] == "commit-after-run"
    assert corpus["step_observations"][0]["raw_output_refs"] == {
        "producer": "raw/000003_assessment_producer.txt",
        "verifier": "raw/000003_assessment_verifier.txt",
    }
    assert corpus["step_observations"][0]["commit_before_step"] == "commit-before-step"
    assert corpus["step_observations"][0]["commit_after_step"] == "commit-after-step"


def test_normalize_trace_corpus_separates_run_statuses_from_route_tags(tmp_path: Path) -> None:
    run_dir = _write_observable_run(tmp_path, "task-1", "release_candidate_to_go_no_go", "run-mixed")
    with (run_dir / "trace.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "schema": "botlane.runtime_trace/v1",
                    "event_type": "step_finished",
                    "sequence": 4,
                    "step_name": "assessment",
                    "step_kind": "pair",
                    "event": {"tag": "blocked"},
                    "outcome": {"tag": "blocked"},
                    "provider_usage": {
                        "producer": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15, "source": "provider"},
                    },
                    "raw_output_refs": {},
                }
            )
            + "\n"
        )
    with (run_dir / "git_tracking.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "schema": "botlane.git_tracking/v1",
                    "event_type": "step_committed",
                    "sequence": 4,
                    "step_name": "assessment",
                    "commit_before_step": "commit-before-step-2",
                    "commit_after_step": "commit-after-step-2",
                }
            )
            + "\n"
        )

    corpus = normalize_trace_corpus(
        selected_workflow="release_candidate_to_go_no_go",
        run_dirs=[run_dir],
        route_tags=["blocked"],
    )

    assert corpus["candidate_run_count"] == 1
    assert corpus["eligible_run_count"] == 1
    assert corpus["step_observation_count"] == 1
    assert [entry["route"] for entry in corpus["step_observations"]] == ["blocked"]
    assert corpus["step_observations"][0]["sequence"] == 4


def test_normalize_trace_corpus_keeps_eligible_runs_when_route_filter_matches_no_steps(tmp_path: Path) -> None:
    run_dir = _write_observable_run(tmp_path, "task-1", "release_candidate_to_go_no_go", "run-no-match")

    corpus = normalize_trace_corpus(
        selected_workflow="release_candidate_to_go_no_go",
        run_dirs=[run_dir],
        route_tags=["blocked"],
    )

    assert corpus["candidate_run_count"] == 1
    assert corpus["eligible_run_count"] == 1
    assert corpus["excluded_run_count"] == 0
    assert corpus["runs"][0]["run_ref"] == "task-1/run-no-match"
    assert corpus["step_observation_count"] == 0
    assert corpus["step_observations"] == []


def test_normalize_trace_corpus_preserves_direct_runtime_control_metadata(tmp_path: Path) -> None:
    run_dir = _write_observable_run(tmp_path, "task-1", "release_candidate_to_go_no_go", "run-awaiting")
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    run_payload["status"] = "awaiting_input"
    run_payload["terminal"] = "AWAIT_INPUT"
    (run_dir / "run.json").write_text(json.dumps(run_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (run_dir / "trace.jsonl").write_text(
        json.dumps(
            {
                "schema": "botlane.runtime_trace/v1",
                "event_type": "step_finished",
                "sequence": 1,
                "step_name": "assessment",
                "step_kind": "pair",
                "candidate_route": None,
                "final_route": None,
                "runtime_control": "request_input",
                "pending_input_id": "pending-assessment-1",
                "terminal": "AWAIT_INPUT",
                "provider_attempted": False,
                "producer_attempted": False,
                "verifier_attempted": False,
                "source_hook": "before",
                "source_phase": "before",
                "raw_output_refs": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    corpus = normalize_trace_corpus(
        selected_workflow="release_candidate_to_go_no_go",
        run_dirs=[run_dir],
        route_tags=["runtime_control:request_input"],
    )

    observation = corpus["all_step_observations"][0]
    assert observation["route"] == "runtime_control:request_input"
    assert observation["runtime_control"] == "request_input"
    assert observation["terminal"] == "AWAIT_INPUT"
    assert observation["pending_input_id"] == "pending-assessment-1"
    assert observation["provider_attempted"] is False
    assert observation["producer_attempted"] is False
    assert observation["verifier_attempted"] is False
    assert observation["source_hook"] == "before"
    assert observation["source_phase"] == "before"
    assert observation["local_outcome"] == "awaiting_input"
    assert observation["downstream_outcome"] == "awaiting_input_terminal_after_local_pass"


def test_normalize_trace_corpus_keeps_question_route_distinct_from_awaiting_input_terminal(tmp_path: Path) -> None:
    run_dir = _write_observable_run(tmp_path, "task-1", "release_candidate_to_go_no_go", "run-question")
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    run_payload["status"] = "awaiting_input"
    run_payload["terminal"] = "AWAIT_INPUT"
    (run_dir / "run.json").write_text(json.dumps(run_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (run_dir / "trace.jsonl").write_text(
        json.dumps(
            {
                "schema": "botlane.runtime_trace/v1",
                "event_type": "step_finished",
                "sequence": 1,
                "step_name": "assessment",
                "step_kind": "llm",
                "event": {"tag": "question", "question": "Need more evidence?"},
                "outcome": {"tag": "question", "question": "Need more evidence?"},
                "candidate_route": "question",
                "final_route": "question",
                "pending_input_id": "pending-assessment-1",
                "terminal": "AWAIT_INPUT",
                "provider_attempted": True,
                "raw_output_refs": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    corpus = normalize_trace_corpus(
        selected_workflow="release_candidate_to_go_no_go",
        run_dirs=[run_dir],
        route_tags=["question"],
    )

    observation = corpus["all_step_observations"][0]
    assert observation["route"] == "question"
    assert observation["final_route"] == "question"
    assert observation["runtime_control"] is None
    assert observation["terminal"] == "AWAIT_INPUT"
    assert observation["pending_input_id"] == "pending-assessment-1"
    assert observation["provider_attempted"] is True
    assert observation["local_outcome"] == "awaiting_input"
    assert observation["downstream_outcome"] == "awaiting_input_terminal_after_local_pass"


def test_filtered_published_observations_still_allow_upstream_ranking_from_internal_trace_context(tmp_path: Path) -> None:
    run_dir = _write_upstream_pass_downstream_fail_run(
        tmp_path,
        "task-1",
        "release_candidate_to_go_no_go",
        "run-upstream",
    )

    corpus = normalize_trace_corpus(
        selected_workflow="release_candidate_to_go_no_go",
        run_dirs=[run_dir],
        route_tags=["failed"],
    )
    metrics = build_step_trace_metrics(corpus, corpus["static_step_graphs"])
    priority = rank_optimization_targets(step_metrics=metrics, static_centrality={}, top_k=1)

    assert [entry["step_name"] for entry in corpus["step_observations"]] == ["package"]
    assert {entry["step_name"] for entry in corpus["all_step_observations"]} == {"assessment", "package"}
    assert {entry["step_name"] for entry in metrics["steps"]} == {"assessment", "package"}
    assert priority["ranked_steps"][0]["step_name"] == "assessment"


def test_build_step_trace_metrics_counts_routes_and_tokens() -> None:
    trace_corpus = {
        "selected_workflow": "release_candidate_to_go_no_go",
        "step_observations": [
            {
                "step_name": "assessment",
                "step_kind": "pair",
                "route": "needs_rework",
                "local_outcome": "rejected_by_verifier",
                "downstream_outcome": "next_step_failed",
                "usage": {"total_tokens": 200},
            },
            {
                "step_name": "assessment",
                "step_kind": "pair",
                "route": "assessment_complete",
                "local_outcome": "locally_accepted",
                "downstream_outcome": "terminal_failure_after_local_pass",
                "usage": {"total_tokens": 300},
            },
            {
                "step_name": "package",
                "step_kind": "pair",
                "route": "failed",
                "local_outcome": "failed",
                "downstream_outcome": "unknown",
                "usage": {"total_tokens": 100},
            },
        ],
    }
    static_graphs = [
        {
            "steps": [{"name": "assessment"}, {"name": "package"}],
            "transitions": {
                "steps": {
                    "assessment": {"assessment_complete": "package", "needs_rework": "assessment"},
                    "package": {"failed": "FAIL"},
                }
            },
        }
    ]

    payload = build_step_trace_metrics(trace_corpus, static_graphs)

    assessment = next(step for step in payload["steps"] if step["step_name"] == "assessment")
    package = next(step for step in payload["steps"] if step["step_name"] == "package")
    assert assessment["observed_count"] == 2
    assert assessment["route_counts"]["needs_rework"] == 1
    assert assessment["estimated_token_total"] == 500
    assert assessment["token_share"] == pytest.approx(0.8333, abs=1e-4)
    assert assessment["downstream_failure_after_pass_count"] == 1
    assert assessment["artifact_centrality"] >= package["artifact_centrality"]


def test_rank_targets_prefers_high_leverage_upstream_step_over_downstream_symptom() -> None:
    step_metrics = {
        "selected_workflow": "release_candidate_to_go_no_go",
        "steps": [
            {
                "step_name": "assessment",
                "step_kind": "pair",
                "observed_count": 5,
                "route_counts": {"assessment_complete": 2, "needs_rework": 3},
                "producer_failed_verifier_count": 3,
                "blocked_count": 0,
                "failed_count": 0,
                "needs_rework_count": 3,
                "needs_replan_count": 0,
                "estimated_token_total": 2200,
                "token_share": 0.55,
                "downstream_failure_after_pass_count": 2,
                "artifact_centrality": 1.0,
                "route_criticality": 0.59,
            },
            {
                "step_name": "package",
                "step_kind": "pair",
                "observed_count": 5,
                "route_counts": {"failed": 3, "package_complete": 2},
                "producer_failed_verifier_count": 0,
                "blocked_count": 0,
                "failed_count": 3,
                "needs_rework_count": 0,
                "needs_replan_count": 0,
                "estimated_token_total": 350,
                "token_share": 0.08,
                "downstream_failure_after_pass_count": 0,
                "artifact_centrality": 0.3,
                "route_criticality": 0.6,
            },
        ],
    }

    payload = rank_optimization_targets(step_metrics=step_metrics, static_centrality={}, top_k=1)

    assert payload["ranked_steps"][0]["step_name"] == "assessment"
    assert payload["not_selected"][0]["step_name"] == "package"
    assert "downstream symptom" in payload["not_selected"][0]["reason"]


def test_extract_failure_scenario_seeds_limits_to_max_scenarios() -> None:
    trace_corpus = {
        "selected_workflow": "release_candidate_to_go_no_go",
        "step_observations": [
            {
                "observation_id": "task/run:000001:assessment",
                "step_name": "assessment",
                "route": "needs_rework",
                "usage": {"total_tokens": 2000},
                "raw_output_refs": {},
                "local_outcome": "rejected_by_verifier",
                "downstream_outcome": "unknown",
            },
            {
                "observation_id": "task/run:000002:assessment",
                "step_name": "assessment",
                "route": "needs_rework",
                "usage": {"total_tokens": 1800},
                "raw_output_refs": {"producer": "raw/1.txt"},
                "local_outcome": "rejected_by_verifier",
                "downstream_outcome": "unknown",
            },
            {
                "observation_id": "task/run:000003:package",
                "step_name": "package",
                "route": "failed",
                "usage": {},
                "raw_output_refs": {"producer": "raw/2.txt"},
                "local_outcome": "failed",
                "downstream_outcome": "unknown",
            },
        ],
    }
    priority_report = {
        "ranked_steps": [{"step_name": "assessment"}, {"step_name": "package"}],
    }

    payload = extract_failure_scenario_seeds(
        trace_corpus=trace_corpus,
        priority_report=priority_report,
        max_scenarios=2,
    )

    assert payload["schema"] == "botlane.workflow_optimization.failure_scenario_seeds/v1"
    assert len(payload["seeds"]) == 2
    assert any(
        "repeated_same_step_needs_rework_loop" in seed["seed_reasons"]
        for seed in payload["seeds"]
    )
    assert all(isinstance(seed["suggested_failure_kind"], str) and seed["suggested_failure_kind"] for seed in payload["seeds"])


def test_write_selected_workflow_source_manifest_records_hashes(tmp_path: Path) -> None:
    _install_selected_workflow(tmp_path)
    workflow_folder = tmp_path / ".botlane" / "tasks" / "task-1" / "wf_optimizer"
    workflow_folder.mkdir(parents=True, exist_ok=True)
    ctx = SimpleNamespace(root=tmp_path, workflow_folder=workflow_folder)

    manifest_path = write_selected_workflow_source_manifest(
        ctx=ctx,
        selected_workflow="release_candidate_to_go_no_go",
        relative_path="selected_workflow_source_manifest.json",
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert payload["selected_workflow"] == "release_candidate_to_go_no_go"
    first_entry = payload["files"][0]
    absolute_path = _manifest_entry_source_path(
        tmp_path,
        first_entry["path"],
        workflow_name="release_candidate_to_go_no_go",
    )
    content = absolute_path.read_bytes()
    assert first_entry["sha256"] == hashlib.sha256(content).hexdigest()
    assert first_entry["bytes"] == len(content)


def test_write_selected_workflow_source_manifest_does_not_materialize_canonical_repo_tree(tmp_path: Path) -> None:
    _install_selected_workflow(tmp_path)
    workflow_folder = tmp_path / ".botlane" / "tasks" / "task-1" / "wf_optimizer"
    workflow_folder.mkdir(parents=True, exist_ok=True)
    ctx = SimpleNamespace(root=tmp_path, workflow_folder=workflow_folder)
    canonical_dir = tmp_path / "botlane" / "workflows" / "release_candidate_to_go_no_go"

    assert canonical_dir.exists() is False

    write_selected_workflow_source_manifest(
        ctx=ctx,
        selected_workflow="release_candidate_to_go_no_go",
        relative_path="selected_workflow_source_manifest.json",
    )

    assert canonical_dir.exists() is False


def test_write_selected_workflow_source_manifest_uses_repo_local_bytes_under_canonical_first_party_labels(
    tmp_path: Path,
) -> None:
    _install_selected_workflow(tmp_path)
    workflow_folder = tmp_path / ".botlane" / "tasks" / "task-1" / "wf_optimizer"
    workflow_folder.mkdir(parents=True, exist_ok=True)
    ctx = SimpleNamespace(root=tmp_path, workflow_folder=workflow_folder)
    workflow_toml = tmp_path / "workflows" / "release_candidate_to_go_no_go" / "workflow.toml"
    workflow_toml.write_text(workflow_toml.read_text(encoding="utf-8") + "\n# repo-local drift\n", encoding="utf-8")

    manifest_path = write_selected_workflow_source_manifest(
        ctx=ctx,
        selected_workflow="release_candidate_to_go_no_go",
        relative_path="selected_workflow_source_manifest.json",
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = next(
        item
        for item in payload["files"]
        if item["path"] == "botlane/workflows/release_candidate_to_go_no_go/workflow.toml"
    )

    assert payload["package_dir"] == "botlane/workflows/release_candidate_to_go_no_go"
    assert entry["sha256"] == hashlib.sha256(workflow_toml.read_bytes()).hexdigest()


def test_write_selected_workflow_source_manifest_normalizes_alias_to_canonical_workflow_name(tmp_path: Path) -> None:
    _install_selected_workflow(tmp_path)
    workflow_folder = tmp_path / ".botlane" / "tasks" / "task-1" / "wf_optimizer"
    workflow_folder.mkdir(parents=True, exist_ok=True)
    ctx = SimpleNamespace(root=tmp_path, workflow_folder=workflow_folder)

    manifest_path = write_selected_workflow_source_manifest(
        ctx=ctx,
        selected_workflow="release-readiness",
        relative_path="selected_workflow_source_manifest.json",
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert payload["selected_workflow"] == "release_candidate_to_go_no_go"
    assert payload["package_dir"] == "botlane/workflows/release_candidate_to_go_no_go"
    assert payload["files"]


def test_validate_selected_workflow_source_unchanged_detects_mutation(tmp_path: Path) -> None:
    _install_selected_workflow(tmp_path)
    workflow_folder = tmp_path / ".botlane" / "tasks" / "task-1" / "wf_optimizer"
    workflow_folder.mkdir(parents=True, exist_ok=True)
    ctx = SimpleNamespace(root=tmp_path, workflow_folder=workflow_folder)

    manifest_path = write_selected_workflow_source_manifest(
        ctx=ctx,
        selected_workflow="release_candidate_to_go_no_go",
        relative_path="selected_workflow_source_manifest.json",
    )
    target_file = tmp_path / "workflows" / "release_candidate_to_go_no_go" / "workflow.toml"
    target_file.write_text(target_file.read_text(encoding="utf-8") + "# drift\n", encoding="utf-8")

    ok, details = validate_selected_workflow_source_unchanged(
        ctx=ctx,
        selected_workflow="release_candidate_to_go_no_go",
        manifest_path=manifest_path,
    )

    assert ok is False
    assert "changed during optimization publication" in details


def test_write_optimization_refinement_evidence_uses_expected_schema(tmp_path: Path) -> None:
    workflow_folder = tmp_path / ".botlane" / "tasks" / "task-1" / "wf_optimizer"
    workflow_folder.mkdir(parents=True, exist_ok=True)
    ctx = SimpleNamespace(root=tmp_path, workflow_folder=workflow_folder)

    path = write_optimization_refinement_evidence(
        ctx=ctx,
        selected_workflow="release_candidate_to_go_no_go",
        evidence_entries=[
            {
                "kind": "workflow_optimization_scorecard",
                "path": "workflow_optimization_scorecard.json",
                "summary": "No-op packet because no eligible traces were present.",
                "handling": "Candidate-only boundary.",
            }
        ],
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema"] == "botlane.workflow_refinement_evidence/v1"
    assert payload["target_workflow_id"] == "release_candidate_to_go_no_go"
    assert payload["evidence_entries"][0]["kind"] == "workflow_optimization_scorecard"


def test_finalize_optional_optimization_artifact_writes_empty_payload_for_missing_skipped_route(tmp_path: Path) -> None:
    artifact_path = tmp_path / "token_optimization_candidates.json"
    spec = OptimizationArtifactSpec(
        filename=artifact_path.name,
        artifact_name=artifact_path.name,
        expected_schema="botlane.workflow_optimization.token_candidates/v1",
        list_field="candidates",
        reader=_namespace_reader,
        empty_payload_factory=lambda *, selected_workflow: {
            "schema": "botlane.workflow_optimization.token_candidates/v1",
            "selected_workflow": selected_workflow,
            "candidates": [],
        },
    )

    finalize_optional_optimization_artifact(
        route="token_pass_not_applicable",
        path=artifact_path,
        selected_workflow_name="release_candidate_to_go_no_go",
        spec=spec,
    )

    assert json.loads(artifact_path.read_text(encoding="utf-8")) == {
        "schema": "botlane.workflow_optimization.token_candidates/v1",
        "selected_workflow": "release_candidate_to_go_no_go",
        "candidates": [],
    }


def test_collect_and_validate_optimization_publication_surface_aggregates_counts_ids_and_ablation(tmp_path: Path) -> None:
    producer_path = tmp_path / "producer_prompt_optimization_candidates.json"
    producer_path.write_text(
        json.dumps(
            {
                "schema": "botlane.workflow_optimization.producer_candidates/v1",
                "selected_workflow": "release_candidate_to_go_no_go",
                "candidates": [
                    {"candidate_id": "producer-001", "requires_ablation": False},
                    {"candidate_id": "producer-002", "requires_ablation": True},
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    adversarial_path = tmp_path / "adversarial_case_candidates.json"
    adversarial_path.write_text(
        json.dumps(
            {
                "schema": "botlane.workflow_optimization.adversarial_case_candidates/v1",
                "selected_workflow": "release_candidate_to_go_no_go",
                "cases": [
                    {"case_id": "case-001"},
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    specs = (
        OptimizationArtifactSpec(
            filename=producer_path.name,
            artifact_name=producer_path.name,
            expected_schema="botlane.workflow_optimization.producer_candidates/v1",
            list_field="candidates",
            reader=_namespace_reader,
            empty_payload_factory=lambda *, selected_workflow: {
                "schema": "botlane.workflow_optimization.producer_candidates/v1",
                "selected_workflow": selected_workflow,
                "candidates": [],
            },
            count_key="producer",
            id_field="candidate_id",
            requires_ablation_field="requires_ablation",
        ),
        OptimizationArtifactSpec(
            filename=adversarial_path.name,
            artifact_name=adversarial_path.name,
            expected_schema="botlane.workflow_optimization.adversarial_case_candidates/v1",
            list_field="cases",
            reader=_namespace_reader,
            empty_payload_factory=lambda *, selected_workflow: {
                "schema": "botlane.workflow_optimization.adversarial_case_candidates/v1",
                "selected_workflow": selected_workflow,
                "cases": [],
            },
            count_key="adversarial_cases",
            id_field="case_id",
        ),
    )

    surface = collect_optimization_publication_surface(
        tmp_path,
        selected_workflow_name="release_candidate_to_go_no_go",
        artifact_specs=specs,
    )

    assert surface.counts == {"producer": 2, "adversarial_cases": 1}
    assert surface.candidate_ids == {"producer-001", "producer-002", "case-001"}
    assert surface.requires_ablation is True

    validate_optimization_scorecard_publication(
        {
            "candidate_counts": {"producer": 2, "adversarial_cases": 1},
            "highest_priority_candidate_ids": ["producer-002", "case-001"],
            "requires_ablation_before_promotion": True,
        },
        publication_surface=surface,
    )


def test_validate_optimization_scorecard_publication_rejects_unknown_high_priority_candidate_ids() -> None:
    with pytest.raises(
        ValueError,
        match="workflow_optimization_scorecard.json highest_priority_candidate_ids must refer to validated candidate artifacts",
    ):
        validate_optimization_scorecard_publication(
            {
                "candidate_counts": {"producer": 1},
                "highest_priority_candidate_ids": ["producer-001", "missing-999"],
                "requires_ablation_before_promotion": False,
            },
            publication_surface=SimpleNamespace(
                counts={"producer": 1},
                candidate_ids={"producer-001"},
                requires_ablation=False,
            ),
        )


def test_validate_optimization_scorecard_publication_rejects_ablation_flag_mismatch() -> None:
    with pytest.raises(
        ValueError,
        match="workflow_optimization_scorecard.json requires_ablation_before_promotion must match validated candidate ablation requirements",
    ):
        validate_optimization_scorecard_publication(
            {
                "candidate_counts": {"producer": 1},
                "highest_priority_candidate_ids": ["producer-001"],
                "requires_ablation_before_promotion": False,
            },
            publication_surface=SimpleNamespace(
                counts={"producer": 1},
                candidate_ids={"producer-001"},
                requires_ablation=True,
            ),
        )


def _write_minimal_run_metadata(root: Path, task_id: str, workflow_name: str, run_id: str, status: str) -> Path:
    run_dir = root / ".botlane" / "tasks" / task_id / f"wf_{workflow_name}" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "created_at": "2026-04-24T06:00:00+00:00",
        "package_folder": str(Path("workflows") / workflow_name),
        "run_folder": str(Path(".botlane") / "tasks" / task_id / f"wf_{workflow_name}" / "runs" / run_id),
        "run_id": run_id,
        "status": status,
        "task_folder": str(Path(".botlane") / "tasks" / task_id),
        "task_id": task_id,
        "updated_at": "2026-04-24T06:05:00+00:00",
        "workflow_folder": str(Path(".botlane") / "tasks" / task_id / f"wf_{workflow_name}"),
        "workflow_name": workflow_name,
        "workflow_params": {},
    }
    (run_dir / "run.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return run_dir


def _namespace_reader(path: Path) -> SimpleNamespace:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _to_namespace(payload)


def _to_namespace(value):
    if isinstance(value, dict):
        return SimpleNamespace(**{key: _to_namespace(item) for key, item in value.items()})
    if isinstance(value, list):
        return [_to_namespace(item) for item in value]
    return value


def _manifest_entry_source_path(root: Path, entry_path: str, *, workflow_name: str) -> Path:
    relative_path = Path(entry_path)
    canonical_root = Path("botlane") / "workflows" / workflow_name
    if relative_path.parts[: len(canonical_root.parts)] == canonical_root.parts:
        suffix = relative_path.relative_to(canonical_root)
        return root / "workflows" / workflow_name / suffix
    return root / relative_path


def _write_observable_run(root: Path, task_id: str, workflow_name: str, run_id: str) -> Path:
    run_dir = _write_minimal_run_metadata(root, task_id, workflow_name, run_id, "failed")
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    run_payload["terminal"] = "FAIL"
    run_payload["git_tracking"] = {
        "commit_before_run": "commit-before-run",
        "commit_after_run": "commit-after-run",
    }
    (run_dir / "run.json").write_text(json.dumps(run_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    producer_text = "producer output\n"
    verifier_text = "verifier output\n"
    raw_dir = run_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "000003_assessment_producer.txt").write_text(producer_text, encoding="utf-8")
    (raw_dir / "000003_assessment_verifier.txt").write_text(verifier_text, encoding="utf-8")
    (run_dir / "trace.jsonl").write_text(
        json.dumps(
            {
                "schema": "botlane.runtime_trace/v1",
                "event_type": "step_finished",
                "sequence": 3,
                "step_name": "assessment",
                "step_kind": "pair",
                "event": {"tag": "needs_rework"},
                "outcome": {"tag": "needs_rework"},
                "git": {"commit_before_step": "commit-before-step"},
                "provider_usage": {
                    "producer": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120, "source": "provider"},
                    "verifier": {"input_tokens": 80, "output_tokens": 10, "total_tokens": 90, "source": "provider"},
                },
                "raw_output_refs": {
                    "producer": {
                        "path": "raw/000003_assessment_producer.txt",
                        "sha256": hashlib.sha256(producer_text.encode("utf-8")).hexdigest(),
                        "bytes": len(producer_text.encode("utf-8")),
                    },
                    "verifier": {
                        "path": "raw/000003_assessment_verifier.txt",
                        "sha256": hashlib.sha256(verifier_text.encode("utf-8")).hexdigest(),
                        "bytes": len(verifier_text.encode("utf-8")),
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "git_tracking.jsonl").write_text(
        json.dumps(
            {
                "schema": "botlane.git_tracking/v1",
                "event_type": "step_committed",
                "sequence": 3,
                "step_name": "assessment",
                "commit_before_step": "commit-before-step",
                "commit_after_step": "commit-after-step",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "static_step_graph.json").write_text(
        json.dumps(
            {
                "schema": "botlane.workflow_static_step_graph/v1",
                "workflow_name": workflow_name,
                "steps": [{"name": "assessment", "kind": "pair"}],
                "transitions": {"steps": {"assessment": {"needs_rework": "assessment"}}, "global": {}},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return run_dir


def _write_upstream_pass_downstream_fail_run(root: Path, task_id: str, workflow_name: str, run_id: str) -> Path:
    run_dir = _write_minimal_run_metadata(root, task_id, workflow_name, run_id, "failed")
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    run_payload["terminal"] = "FAIL"
    run_payload["git_tracking"] = {
        "commit_before_run": "commit-before-run",
        "commit_after_run": "commit-after-run",
    }
    (run_dir / "run.json").write_text(json.dumps(run_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    raw_dir = run_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "000001_assessment_producer.txt").write_text("assessment producer\n", encoding="utf-8")
    (raw_dir / "000002_package_producer.txt").write_text("package producer\n", encoding="utf-8")
    (run_dir / "trace.jsonl").write_text(
        "\n".join(
            (
                json.dumps(
                    {
                        "schema": "botlane.runtime_trace/v1",
                        "event_type": "step_finished",
                        "sequence": 1,
                        "step_name": "assessment",
                        "step_kind": "pair",
                        "event": {"tag": "assessment_complete"},
                        "outcome": {"tag": "assessment_complete"},
                        "provider_usage": {
                            "producer": {
                                "input_tokens": 200,
                                "output_tokens": 40,
                                "total_tokens": 240,
                                "source": "provider",
                            }
                        },
                        "raw_output_refs": {
                            "producer": {
                                "path": "raw/000001_assessment_producer.txt",
                                "sha256": "unused",
                                "bytes": 18,
                            }
                        },
                    }
                ),
                json.dumps(
                    {
                        "schema": "botlane.runtime_trace/v1",
                        "event_type": "step_finished",
                        "sequence": 2,
                        "step_name": "package",
                        "step_kind": "pair",
                        "event": {"tag": "failed"},
                        "outcome": {"tag": "failed"},
                        "provider_usage": {
                            "producer": {
                                "input_tokens": 40,
                                "output_tokens": 10,
                                "total_tokens": 50,
                                "source": "provider",
                            }
                        },
                        "raw_output_refs": {
                            "producer": {
                                "path": "raw/000002_package_producer.txt",
                                "sha256": "unused",
                                "bytes": 16,
                            }
                        },
                    }
                ),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "git_tracking.jsonl").write_text(
        "\n".join(
            (
                json.dumps(
                    {
                        "schema": "botlane.git_tracking/v1",
                        "event_type": "step_committed",
                        "sequence": 1,
                        "step_name": "assessment",
                        "commit_before_step": "commit-before-assessment",
                        "commit_after_step": "commit-after-assessment",
                    }
                ),
                json.dumps(
                    {
                        "schema": "botlane.git_tracking/v1",
                        "event_type": "step_committed",
                        "sequence": 2,
                        "step_name": "package",
                        "commit_before_step": "commit-before-package",
                        "commit_after_step": "commit-after-package",
                    }
                ),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "static_step_graph.json").write_text(
        json.dumps(
            {
                "schema": "botlane.workflow_static_step_graph/v1",
                "workflow_name": workflow_name,
                "steps": [
                    {"name": "assessment", "kind": "pair"},
                    {"name": "package", "kind": "pair"},
                ],
                "transitions": {
                    "steps": {
                        "assessment": {"assessment_complete": "package"},
                        "package": {"failed": "FAIL"},
                    },
                    "global": {},
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return run_dir


def _install_selected_workflow(root: Path) -> None:
    workflows_root = root / "workflows"
    workflows_root.mkdir(parents=True, exist_ok=True)
    (workflows_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    package_dir = workflows_root / "release_candidate_to_go_no_go"
    (package_dir / "assets").mkdir(parents=True, exist_ok=True)
    (package_dir / "prompts").mkdir(parents=True, exist_ok=True)
    (package_dir / "__init__.py").write_text(
        "from .workflow import ReleaseCandidateToGoNoGo\n"
        "__all__ = ['ReleaseCandidateToGoNoGo']\n",
        encoding="utf-8",
    )
    (package_dir / "workflow.toml").write_text(
        "\n".join(
            (
                'name = "release_candidate_to_go_no_go"',
                'title = "Release Candidate To Go No Go"',
                'description = "Synthetic workflow fixture for optimizer tests."',
                'aliases = ["release-readiness"]',
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (package_dir / "workflow.py").write_text(
        "\n".join(
            (
                "from __future__ import annotations",
                "",
                "from pydantic import BaseModel",
                "",
                "from botlane import Event, FINISH, Workflow, python_step",
                "",
                "",
                "class ReleaseCandidateToGoNoGo(Workflow):",
                '    name = "release_candidate_to_go_no_go"',
                "",
                "    class State(BaseModel):",
                "        published: bool = False",
                "",
                '    @python_step(name="bootstrap", routes={"published": FINISH})',
                "    def bootstrap(ctx):",
                '        ctx.state = ctx.state.model_copy(update={"published": True})',
                '        return Event("published")',
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (package_dir / "prompts" / "README.md").write_text("# Synthetic prompts\n", encoding="utf-8")
    (package_dir / "assets" / "release_decision_package_checklist.md").write_text(
        "# Checklist\n- verify evidence\n",
        encoding="utf-8",
    )
