from __future__ import annotations

from types import SimpleNamespace

from botlane.core.branch_groups.manifest import BranchManifest, build_branch_manifest, render_branch_group_context
from botlane.core.branch_groups.outcomes import select_branch_group_outcome
from botlane.core.branch_groups.results import BranchArtifactObservation, BranchResult


def test_branch_result_to_manifest_dict_matches_current_completed_shape() -> None:
    result = BranchResult(
        name="security",
        index=0,
        input={"area": "security"},
        step_name="security_review",
        status="completed",
        route="done",
        destination="publish",
        runtime_control=None,
        reason=None,
        question=None,
        artifacts=(
            BranchArtifactObservation(
                name="report",
                path="_branch_groups/reviews/branches/security/report.md",
                kind="md",
                exists=True,
                validation="ok",
                validation_errors=(),
            ),
        ),
        raw_output_path="_branch_groups/reviews/branches/security/producer.txt",
        raw_output_paths={"producer": "_branch_groups/reviews/branches/security/producer.txt"},
        provider_session="session-security",
        provider_sessions={"producer": "session-security"},
        error=None,
        started_at="2026-05-09T08:00:00+00:00",
        finished_at="2026-05-09T08:00:01+00:00",
        duration_ms=1000,
        usage={"input_tokens": 12, "output_tokens": 5},
    )

    assert result.to_manifest_dict() == {
        "name": "security",
        "index": 0,
        "input": {"area": "security"},
        "step_name": "security_review",
        "status": "completed",
        "route": "done",
        "destination": "publish",
        "runtime_control": None,
        "reason": None,
        "question": None,
        "artifacts": [
            {
                "name": "report",
                "path": "_branch_groups/reviews/branches/security/report.md",
                "kind": "md",
                "exists": True,
                "validation": "ok",
                "validation_errors": [],
            }
        ],
        "raw_output_path": "_branch_groups/reviews/branches/security/producer.txt",
        "raw_output_paths": {"producer": "_branch_groups/reviews/branches/security/producer.txt"},
        "provider_session": "session-security",
        "provider_sessions": {"producer": "session-security"},
        "error": None,
        "started_at": "2026-05-09T08:00:00+00:00",
        "finished_at": "2026-05-09T08:00:01+00:00",
        "duration_ms": 1000,
        "usage": {"input_tokens": 12, "output_tokens": 5},
    }


def test_branch_result_to_manifest_dict_matches_current_skipped_shape() -> None:
    result = BranchResult(
        name="cost",
        index=1,
        input={"area": "cost"},
        step_name="cost_review",
        status="skipped",
        route=None,
        destination=None,
        runtime_control=None,
        reason="Branch was not scheduled because fail_fast stopped new branch launches.",
        question=None,
        artifacts=(),
        raw_output_path=None,
        raw_output_paths={},
        provider_session=None,
        provider_sessions={},
        error=None,
        started_at="2026-05-09T08:00:02+00:00",
        finished_at="2026-05-09T08:00:02+00:00",
        duration_ms=0,
        usage={},
        cancellation_requested=False,
        cancellation_completed=False,
        cancellation_supported=True,
    )

    assert result.to_manifest_dict() == {
        "name": "cost",
        "index": 1,
        "input": {"area": "cost"},
        "step_name": "cost_review",
        "status": "skipped",
        "route": None,
        "destination": None,
        "runtime_control": None,
        "reason": "Branch was not scheduled because fail_fast stopped new branch launches.",
        "question": None,
        "artifacts": [],
        "raw_output_path": None,
        "raw_output_paths": {},
        "provider_session": None,
        "provider_sessions": {},
        "error": None,
        "started_at": "2026-05-09T08:00:02+00:00",
        "finished_at": "2026-05-09T08:00:02+00:00",
        "duration_ms": 0,
        "usage": {},
        "cancellation_requested": False,
        "cancellation_completed": False,
        "cancellation_supported": True,
    }


def test_branch_result_to_manifest_dict_matches_current_cancelled_shape() -> None:
    result = BranchResult(
        name="perf",
        index=2,
        input={"area": "performance"},
        step_name="perf_review",
        status="cancelled",
        route=None,
        destination=None,
        runtime_control=None,
        reason="Cancellation requested after fail_fast.",
        question=None,
        artifacts=(),
        raw_output_path=None,
        raw_output_paths={},
        provider_session=None,
        provider_sessions={},
        error={
            "type": "Cancelled",
            "message": "Branch execution was cancelled before completion.",
            "failure_context": None,
            "retry_kind": None,
            "retry_exhausted": False,
        },
        started_at="2026-05-09T08:00:03+00:00",
        finished_at="2026-05-09T08:00:03+00:00",
        duration_ms=0,
        usage={},
        cancellation_requested=True,
        cancellation_completed=True,
        cancellation_supported=True,
    )

    assert result.to_manifest_dict() == {
        "name": "perf",
        "index": 2,
        "input": {"area": "performance"},
        "step_name": "perf_review",
        "status": "cancelled",
        "route": None,
        "destination": None,
        "runtime_control": None,
        "reason": "Cancellation requested after fail_fast.",
        "question": None,
        "artifacts": [],
        "raw_output_path": None,
        "raw_output_paths": {},
        "provider_session": None,
        "provider_sessions": {},
        "error": {
            "type": "Cancelled",
            "message": "Branch execution was cancelled before completion.",
            "failure_context": None,
            "retry_kind": None,
            "retry_exhausted": False,
        },
        "started_at": "2026-05-09T08:00:03+00:00",
        "finished_at": "2026-05-09T08:00:03+00:00",
        "duration_ms": 0,
        "usage": {},
        "cancellation_requested": True,
        "cancellation_completed": True,
        "cancellation_supported": True,
    }


def test_branch_manifest_schema_context_and_outcome_remain_stable() -> None:
    completed = BranchResult(
        name="security",
        index=0,
        input={"area": "security"},
        step_name="security_review",
        status="completed",
        route="done",
        destination="publish",
        runtime_control=None,
        reason=None,
        question=None,
        artifacts=(),
        raw_output_path=None,
        raw_output_paths={},
        provider_session=None,
        provider_sessions={},
        error=None,
        started_at="2026-05-09T08:00:00+00:00",
        finished_at="2026-05-09T08:00:01+00:00",
        duration_ms=1000,
        usage={},
    )
    needs_input = BranchResult(
        name="cost",
        index=1,
        input={"area": "cost"},
        step_name="cost_review",
        status="needs_input",
        route=None,
        destination="cost_review",
        runtime_control="request_input",
        reason="Awaiting reviewer input.",
        question="Approve cost review?",
        artifacts=(),
        raw_output_path=None,
        raw_output_paths={},
        provider_session=None,
        provider_sessions={},
        error=None,
        started_at="2026-05-09T08:00:00+00:00",
        finished_at="2026-05-09T08:00:01+00:00",
        duration_ms=1000,
        usage={},
    )
    spec = SimpleNamespace(
        kind="parallel",
        name="reviews",
        concurrency=2,
        settle="wait_all",
        success_routes=("done",),
        outcome="all_settled",
    )

    manifest = build_branch_manifest(
        spec=spec,
        started_at="2026-05-09T08:00:00+00:00",
        finished_at="2026-05-09T08:00:01+00:00",
        duration_ms=1000,
        branches=[completed.to_manifest_dict(), needs_input],
    )
    context_text = render_branch_group_context(manifest)
    event = select_branch_group_outcome(spec, manifest.to_dict(), context=None)

    assert isinstance(manifest, BranchManifest)
    assert manifest.schema == "botlane.branch_results/v1"
    assert [branch.name for branch in manifest.branches] == ["security", "cost"]
    assert "## Needs Input Details" in context_text
    assert "- cost: Approve cost review?" in context_text
    assert event.tag == "question"
    assert event.question == "cost: Approve cost review?"
    assert event.reason == "One or more branches need input."


def test_render_branch_group_context_preserves_empty_section_fallbacks() -> None:
    manifest = {
        "schema": "botlane.branch_results/v1",
        "kind": "parallel",
        "name": "reviews",
        "started_at": "2026-05-09T08:00:00+00:00",
        "finished_at": "2026-05-09T08:00:01+00:00",
        "duration_ms": 1000,
        "concurrency": 2,
        "settle": "wait_all",
        "success_routes": (),
        "branches": [
            {
                "name": "security",
                "index": 0,
                "input": {"area": "security"},
                "step_name": "security_review",
                "status": "completed",
                "route": None,
                "destination": "publish",
                "runtime_control": None,
                "reason": None,
                "question": None,
                "artifacts": [],
                "raw_output_path": None,
                "raw_output_paths": {},
                "provider_session": None,
                "provider_sessions": {},
                "error": None,
                "started_at": "2026-05-09T08:00:00+00:00",
                "finished_at": "2026-05-09T08:00:01+00:00",
                "duration_ms": 1000,
                "usage": {},
            }
        ],
    }

    context_text = render_branch_group_context(manifest)

    assert "- Success routes: (none)" in context_text
    assert "## Route Summary" in context_text
    assert "- No branch route events were produced." in context_text
    assert "## Failure Summary" in context_text
    assert "## Needs Input Details" in context_text
    assert "## Cancellation Details" in context_text
    assert context_text.count("- None.") == 3
    assert "- Artifacts: (none)" in context_text
    assert "- Error summary: (none)" in context_text
