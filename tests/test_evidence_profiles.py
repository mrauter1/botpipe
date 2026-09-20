from __future__ import annotations

import pytest

from botpipe_optimizer import capture_evidence_snapshot, capture_source_manifest


def _manifest():
    def example():
        return None

    return capture_source_manifest(example)


def _dispatch(
    dispatch_id: str,
    *,
    tokens: int | None = None,
    elapsed: float | None = 1.0,
    provider: str | None = "fake",
    model: str | None = "model-a",
    effort: str | None = None,
    effort_present: bool = True,
    policy_fingerprint: str = "policy-a",
    outcome: str = "completed",
):
    item = {
        "dispatch_id": dispatch_id,
        "attempt": 1,
        "generation": 0,
        "outcome": outcome,
        "usage_availability": "unknown" if tokens is None else "known_total",
        "usage": {} if tokens is None else {"total_tokens": tokens},
        "elapsed_seconds": elapsed,
        "provider": provider,
        "model": model,
        "policy_fingerprint": policy_fingerprint,
    }
    if effort_present:
        item["effort"] = effort
    return item


def _operation(
    operation_id: str,
    *,
    name: str,
    dispatches=(),
    kind: str = "provider",
    status: str = "completed",
    duration_seconds: float = 1.0,
):
    return {
        "id": operation_id,
        "scope": "root",
        "ordinal": 1,
        "kind": kind,
        "name": name,
        "status": status,
        "started_at": "2026-01-01T00:00:00+00:00",
        "finished_at": f"2026-01-01T00:00:{duration_seconds:05.2f}+00:00",
        "usage": {},
        "inputs": {},
        "result": {"value": {"outcome": "accepted"}},
        "dispatches": list(dispatches),
    }


def _run(*operations, run_id="run-1"):
    provenance = {
        "verified": True,
        "workflow_identity": "workflow-example",
        "surface_id": "surface-current",
        "orchestration_id": "orchestration-current",
    }
    return {
        "run": {
            "run_id": run_id,
            "task_id": "task",
            "workflow": "example",
            "status": "completed",
            "provenance_start": provenance,
            "provenance_end": provenance,
        },
        "operations": list(operations),
        "events": [],
        "artifacts": {},
    }


def _snapshot(*runs, objective="token_usage", top_k_steps=3):
    return capture_evidence_snapshot(
        "example",
        runs,
        source_manifest=_manifest(),
        objective=objective,
        top_k_steps=top_k_steps,
        current_workflow_identity="workflow-example",
        current_surface_id="surface-current",
        current_orchestration_id="orchestration-current",
    )


def test_mixed_profile_retry_keeps_strata_and_ranks_literal_step_total():
    mixed = _operation(
        "mixed",
        name="mixed",
        dispatches=(
            _dispatch("a", tokens=100, model="model-a"),
            _dispatch("b", tokens=100, model="model-b"),
        ),
    )
    single = _operation(
        "single",
        name="single",
        dispatches=(_dispatch("c", tokens=150, model="model-c"),),
    )

    snapshot = _snapshot(_run(mixed, single), top_k_steps=1)
    metric = next(item for item in snapshot.step_metrics if item.step_id == "mixed")

    assert snapshot.selection_basis == "sum_of_reported_token_counts"
    assert snapshot.profile_comparison == "none"
    assert snapshot.shortlist[0].step_id == "mixed"
    assert snapshot.shortlist[0].known_total_tokens == 200
    assert metric.heterogeneous_profiles is True
    assert [item.known_total_tokens for item in metric.profile_breakdowns] == [100, 100]


def test_unknown_profile_with_complete_usage_ranks_but_unknown_usage_measures_first():
    complete = _operation(
        "complete",
        name="complete unknown identity",
        dispatches=(_dispatch("known-fact", tokens=50, provider=None, model=None),),
    )
    incomplete = _operation(
        "incomplete",
        name="unknown usage",
        dispatches=(_dispatch("unknown-fact", tokens=None),),
    )

    snapshot = _snapshot(_run(complete, incomplete))
    metrics = {item.step_id: item for item in snapshot.step_metrics}

    assert snapshot.shortlist[0].step_id == "complete unknown identity"
    assert snapshot.shortlist[0].incomplete_profile_identity is True
    assert (
        metrics["complete unknown identity"].profile_breakdowns[0].profile_comparable
        is False
    )
    assert metrics["unknown usage"].metric_id in snapshot.measure_first


def test_latency_uses_physical_dispatch_seconds_not_generic_activity_duration():
    activity = _operation(
        "activity",
        name="long activity",
        kind="activity",
        duration_seconds=9.0,
    )
    provider = _operation(
        "provider",
        name="provider",
        dispatches=(_dispatch("provider-dispatch", tokens=1, elapsed=1.0),),
        duration_seconds=8.0,
    )

    snapshot = _snapshot(_run(activity, provider), objective="latency")
    metrics = {item.step_id: item for item in snapshot.step_metrics}

    assert snapshot.selection_basis == "sum_of_provider_dispatch_seconds"
    assert snapshot.shortlist[0].step_id == "provider"
    assert snapshot.shortlist[0].total_elapsed_seconds == 1.0
    assert metrics["long activity"].total_elapsed_seconds is None
    assert metrics["long activity"].metric_id in snapshot.measure_first


def test_reliability_dedupes_run_and_step_across_profile_observations():
    first = _operation(
        "first",
        name="retrying step",
        status="failed",
        dispatches=(_dispatch("retry-a", model="model-a", outcome="failed"),),
    )
    second = _operation(
        "second",
        name="retrying step",
        status="failed",
        dispatches=(_dispatch("retry-b", model="model-b", outcome="failed"),),
    )

    snapshot = _snapshot(_run(first, second), objective="reliability")
    metric = snapshot.step_metrics[0]

    assert metric.observation_count == 2
    assert metric.direct_failure_count == 1
    assert metric.direct_failure_run_count == 1
    assert len(metric.profile_breakdowns) == 2


def test_failed_retry_dispatch_does_not_promote_completed_operation_to_failure():
    operation = _operation(
        "recovered",
        name="recovered step",
        status="completed",
        dispatches=(
            _dispatch("failed-attempt", outcome="failed"),
            _dispatch("completed-attempt", outcome="completed"),
        ),
    )

    snapshot = _snapshot(_run(operation), objective="reliability")
    metric = snapshot.step_metrics[0]

    assert metric.direct_failure_run_count == 0
    assert metric.profile_breakdowns[0].failed_dispatch_count == 1
    assert snapshot.shortlist == ()
    assert snapshot.next_action == "no_change"


def test_duplicate_physical_dispatch_identity_is_rejected_before_aggregation():
    first = _operation(
        "first-duplicate",
        name="first",
        dispatches=(_dispatch("same", tokens=11),),
    )
    second = _operation(
        "second-duplicate",
        name="second",
        dispatches=(_dispatch("same", tokens=11),),
    )

    with pytest.raises(ValueError, match="duplicate provider dispatch ids"):
        _snapshot(_run(first, second))


def test_full_policy_hash_is_audit_only_for_semantic_profile():
    operation = _operation(
        "same-profile",
        name="same profile",
        dispatches=(
            _dispatch("one", tokens=5, policy_fingerprint="full-policy-one"),
            _dispatch("two", tokens=7, policy_fingerprint="full-policy-two"),
        ),
    )

    snapshot = _snapshot(_run(operation))
    observation = snapshot.observations[0]
    metric = snapshot.step_metrics[0]

    assert len(metric.profile_breakdowns) == 1
    assert metric.profile_breakdowns[0].known_total_tokens == 12
    assert {item.policy_fingerprint for item in observation.dispatches} == {
        "full-policy-one",
        "full-policy-two",
    }


def test_top_k_is_one_global_cap_over_unique_steps_not_profile_strata():
    operations = [
        _operation(
            f"operation-{index}",
            name=f"step-{index}",
            dispatches=(
                _dispatch(f"{index}-a", tokens=tokens, model="model-a"),
                _dispatch(f"{index}-b", tokens=tokens, model="model-b"),
            ),
        )
        for index, tokens in enumerate((100, 80, 60))
    ]

    snapshot = _snapshot(_run(*operations), top_k_steps=2)

    assert len(snapshot.shortlist) == 2
    assert [item.step_id for item in snapshot.shortlist] == ["step-0", "step-1"]
    assert len({item.step_id for item in snapshot.shortlist}) == 2


def test_effort_known_unset_and_absent_do_not_share_a_profile():
    operation = _operation(
        "effort-state",
        name="effort state",
        dispatches=(
            _dispatch("known-unset", tokens=3, effort=None),
            _dispatch("absent", tokens=4, effort_present=False),
        ),
    )

    snapshot = _snapshot(_run(operation))
    profiles = snapshot.step_metrics[0].profile_breakdowns

    assert {item.effort_state for item in profiles} == {"known_unset", "absent"}
    assert {item.profile_comparable for item in profiles} == {True, False}


def test_unknown_profiles_are_distinct_when_dispatch_ids_repeat_across_runs():
    first = _operation(
        "first-operation",
        name="same step",
        dispatches=(
            _dispatch("reused-dispatch-id", tokens=3, provider=None, model=None),
        ),
    )
    second = _operation(
        "second-operation",
        name="same step",
        dispatches=(
            _dispatch("reused-dispatch-id", tokens=4, provider=None, model=None),
        ),
    )

    snapshot = _snapshot(
        _run(first, run_id="run-1"),
        _run(second, run_id="run-2"),
    )
    profiles = snapshot.step_metrics[0].profile_breakdowns

    assert len(profiles) == 2
    assert {item.known_total_tokens for item in profiles} == {3, 4}
    assert all(item.profile_comparable is False for item in profiles)
