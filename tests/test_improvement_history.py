from __future__ import annotations

import pytest

from botpipe import Botpipe, workflow
from labs.workflows.improve_workflow import ImproveWorkflowParams, improve_workflow
from labs.workflows.improve_workflow.proposals import _capture_history
from tests.improvement_support import ACCEPT, FixtureProvider, assess, observed_workflow


@workflow
def capture_subject_history(run_refs: tuple[str, ...] = ()):
    return _capture_history("subject", run_refs, history_limit=1)


@pytest.mark.parametrize("status", ["created", "running"])
def test_active_runs_do_not_displace_history_but_can_be_explicitly_selected(
    tmp_path, monkeypatch, status
):
    observed_workflow(tmp_path)
    with Botpipe(tmp_path, provider=FixtureProvider([])) as client:
        newer = dict(client.journal.run("observed"), run_id="newer", status=status)
        client.journal.create_run(newer)
        original_runs = client.runs

        def stale_listing():
            # The run resumed after listing, before its inspection snapshot.
            return [
                dict(record, status="completed")
                if record["run_id"] == "newer"
                else record
                for record in original_runs()
            ]

        monkeypatch.setattr(client, "runs", stale_listing)
        implicit = client.run(capture_subject_history)
        assert implicit.ok, implicit.error
        assert [item["run"]["run_id"] for item in implicit.value] == ["observed"]
        assert implicit.value[0]["run"]["status"] == "failed"

        explicit = client.run(capture_subject_history, ("newer",))
        assert explicit.ok, explicit.error
        assert [item["run"]["run_id"] for item in explicit.value] == ["newer"]
        assert explicit.value[0]["run"]["status"] == status


@pytest.mark.parametrize(
    "status", ["failed", "interrupted", "budget_exceeded", "awaiting_input"]
)
def test_stopped_runs_remain_eligible_history(tmp_path, status):
    observed_workflow(tmp_path)
    with Botpipe(tmp_path, provider=FixtureProvider([])) as client:
        client.journal.update_run("observed", status=status)
        result = client.run(capture_subject_history)
        assert result.ok, result.error
        assert [item["run"]["run_id"] for item in result.value] == ["observed"]


def test_self_improvement_selects_historical_failure_not_itself(tmp_path):
    provider = FixtureProvider(
        [
            assess,
            {
                "candidate": None,
                "next_action": "no_change",
                "reason": "The invalid workflow reference is an input issue, not a source defect.",
            },
            ACCEPT,
        ]
    )
    with Botpipe(tmp_path, provider=provider) as client:
        failed = client.run(
            improve_workflow,
            ImproveWorkflowParams(selected_workflow="nonexistent_workflow"),
            run_id="historical-failure",
        )
        assert failed.status == "failed"
        result = client.run(
            improve_workflow,
            ImproveWorkflowParams(
                selected_workflow="improve_workflow", history_limit=1
            ),
        )
        assert result.ok, result.error
        snapshot = result.value.recommendation.evidence_snapshot
        assert [run.run_id for run in snapshot.runs] == [failed.run_id]
        assert snapshot.observations
        assert snapshot.shortlist
        assert len(provider.calls) == 3
