from __future__ import annotations

import sys
from types import SimpleNamespace

import run_cleanup
from run_cleanup import (
    _combined_notes,
    _print_result_summary,
    _result_error,
    _result_route,
    build_parser,
)
from workflows.botpipe_cleanup_workflow import (
    BotpipeCyclicalCleanupWorkflow,
    CleanupAuditDecision,
    CleanupScope,
    _record_audit_cycle,
)


def _cleanup_hook_context(*, route: str, cycle_count: int, max_cycles: int) -> SimpleNamespace:
    context = SimpleNamespace(
        route=SimpleNamespace(tag=route),
        state=BotpipeCyclicalCleanupWorkflow.State(cycle_count=cycle_count),
        input=CleanupScope(scope="botpipe/core", max_cycles=max_cycles),
    )
    return context


def test_result_route_prefers_last_event_then_last_outcome() -> None:
    result = SimpleNamespace(
        last_event=SimpleNamespace(tag="failed"),
        last_outcome=SimpleNamespace(tag="complete"),
    )

    assert _result_route(result) == "failed"

    result.last_event = None

    assert _result_route(result) == "complete"


def test_result_error_prefers_validation_error_then_route_reason() -> None:
    result = SimpleNamespace(
        ok=False,
        terminal="FAIL",
        output_validation_error="output mismatch",
        last_event=SimpleNamespace(reason="route failed"),
        last_outcome=None,
    )

    assert _result_error(result) == "output mismatch"

    result.output_validation_error = None

    assert _result_error(result) == "route failed"


def test_print_result_summary_uses_workflow_result_debug(capsys, tmp_path) -> None:
    result = SimpleNamespace(
        ok=False,
        status="failed",
        terminal="FAIL",
        output_validation_error=None,
        last_event=SimpleNamespace(tag="failed", reason="cleanup failed"),
        last_outcome=None,
        debug=SimpleNamespace(task_id="sdk-cleanup", run_id="run-1"),
    )

    _print_result_summary(result, workspace=tmp_path)

    assert capsys.readouterr().out.splitlines() == [
        "ok: False",
        "status: failed",
        "terminal: FAIL",
        "route: failed",
        "task_id: sdk-cleanup",
        "run_id: run-1",
        f"workspace: {tmp_path}",
        "error: cleanup failed",
    ]


def test_cleanup_runner_defaults_to_medium_impact_batch() -> None:
    args = build_parser().parse_args([])

    assert args.batch_size == "medium"
    assert args.target_production_loc_delta == 150


def test_cleanup_runner_does_not_pass_cycle_or_max_steps_caps(monkeypatch, tmp_path) -> None:
    calls: dict[str, object] = {}

    class FakeBotpipe:
        def __init__(self, **kwargs) -> None:
            calls["init_kwargs"] = kwargs

        def run(self, workflow, message=None, **kwargs):
            calls["workflow"] = workflow
            calls["message"] = message
            calls["run_kwargs"] = kwargs
            return SimpleNamespace(
                ok=True,
                status="completed",
                terminal="FINISH",
                last_event=SimpleNamespace(tag="complete"),
                last_outcome=None,
                debug=SimpleNamespace(task_id="sdk-cleanup", run_id="run-1"),
            )

    monkeypatch.setattr(run_cleanup, "Botpipe", FakeBotpipe)
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_cleanup.py", "--workspace", str(tmp_path), "--cycles", "1"],
    )

    assert run_cleanup.main() == 0

    run_kwargs = calls["run_kwargs"]
    assert isinstance(run_kwargs, dict)
    assert "max_steps" not in run_kwargs
    assert "max_cycles" not in run_kwargs["input"]


def test_cleanup_audit_decision_tracks_actual_loc_decrease_only() -> None:
    fields = CleanupAuditDecision.model_fields

    assert "production_loc_decreased" in fields
    assert "production_loc_decreased_or_old_representation_removed" not in fields


def test_combined_notes_prefer_bundled_high_impact_cleanup() -> None:
    notes = _combined_notes(
        target_loc_delta=200,
        user_notes="Preserve public behavior.",
    )

    assert "does not impose a cleanup-cycle or max_steps-derived stop condition" in notes
    assert "200+ production LOC reduction as a soft planning target" in notes
    assert "not as an audit gate" in notes
    assert "Audit acceptance only requires an actual net production LOC decrease" in notes
    assert "select the one with the larger expected production LOC decrease" in notes
    assert "Small dead-code and stale-helper cleanup is still welcome" in notes
    assert "batched with the larger coherent seam" in notes
    assert "Do not select isolated helper shaving as the whole batch" in notes
    assert "Preserve public behavior." in notes


def test_cleanup_audit_hook_records_repeat_without_cycle_budget_redirect() -> None:
    context = _cleanup_hook_context(route="repeat", cycle_count=1, max_cycles=3)

    redirect = _record_audit_cycle(context)

    assert redirect is None
    assert context.state.cycle_count == 2
    assert context.state.last_scope == "botpipe/core"
    assert context.state.last_route == "repeat"


def test_cleanup_audit_hook_does_not_finish_final_repeat() -> None:
    context = _cleanup_hook_context(route="repeat", cycle_count=2, max_cycles=3)

    redirect = _record_audit_cycle(context)

    assert redirect is None
    assert context.state.cycle_count == 3
    assert context.state.last_route == "repeat"


def test_cleanup_audit_hook_records_fail_without_cycle_budget_redirect() -> None:
    context = _cleanup_hook_context(route="fail", cycle_count=1, max_cycles=3)

    redirect = _record_audit_cycle(context)

    assert redirect is None
    assert context.state.cycle_count == 2
    assert context.state.last_route == "fail"


def test_cleanup_audit_hook_does_not_terminal_fail_at_cycle_budget() -> None:
    context = _cleanup_hook_context(route="fail", cycle_count=2, max_cycles=3)

    redirect = _record_audit_cycle(context)

    assert redirect is None
    assert context.state.cycle_count == 3
    assert context.state.last_route == "fail"
