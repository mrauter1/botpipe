from __future__ import annotations

from types import SimpleNamespace

from run_cleanup import _print_result_summary, _result_error, _result_route


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
