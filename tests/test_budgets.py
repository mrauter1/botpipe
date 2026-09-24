from __future__ import annotations

import threading

from botpipe import (
    Botpipe,
    Provider,
    ask_human,
    parallel,
    provider_budget,
    workflow,
)
from botpipe.providers import FakeProvider, ProviderError


def states(client):
    return [
        client.journal.budget(operation["id"])
        for run in client.journal.runs()
        for operation in client.journal.operations(run["run_id"])
        if operation["kind"] == "provider_budget"
    ]


def test_schema_repairs_consume_turns_and_exhaustion_replays_without_dispatch(tmp_path):
    @workflow
    def work():
        with provider_budget(max_turns=2):
            return Provider().run("number", returns=int).value

    provider = FakeProvider(["bad", "still bad", "42"])
    with Botpipe(tmp_path, provider=provider) as client:
        result = client.run(work)
        assert result.status == "budget_exceeded"
        assert len(provider.calls) == 2
        assert states(client)[0]["used_turns"] == 2
        resumed = client.resume(result.run_id, workflow=work)
        assert resumed.status == "budget_exceeded", resumed.error
        assert len(provider.calls) == 2

        @workflow
        def next_run():
            return Provider().run("done").value

        # A denied dispatch has no unresolved effects that block another run.
        assert client.run(next_run).status == "completed"


def test_child_parallel_calls_share_one_atomic_limit(tmp_path):
    concurrent_turns = threading.Barrier(2)

    def respond(request):
        # Both permitted calls must reach the provider together.
        concurrent_turns.wait(timeout=30)
        return "done"

    @workflow
    def child():
        return Provider().query("read").value

    @workflow
    def work():
        with provider_budget(max_turns=2):
            return parallel(lambda: child(), lambda: child(), lambda: child())

    provider = FakeProvider([respond, respond, respond])
    with Botpipe(tmp_path, provider=provider) as client:
        result = client.run(work)
        assert result.status == "budget_exceeded", result.error
        assert len(provider.calls) == 2
        assert states(client)[0]["used_turns"] == 2


def test_resume_keeps_absolute_deadline_and_counts_suspended_time(
    tmp_path, monkeypatch
):
    import botpipe.budgets as budgets

    clock = [budgets.time.time()]
    monkeypatch.setattr(budgets.time, "time", lambda: clock[0])

    class TimedProvider(FakeProvider):
        supports_timeout = True

    @workflow
    def work():
        with provider_budget(max_turns=3, max_seconds=10):
            ask_human("continue?")
            return Provider().run("read").value

    provider = TimedProvider(["done"])
    with Botpipe(tmp_path, provider=provider) as client:
        result = client.run(work)
        deadline = states(client)[0]["deadline"]
        assert result.status == "awaiting_input"
        clock[0] += 11
        assert (
            client.resume(result.run_id, workflow=work, answer="yes").status
            == "budget_exceeded"
        )
        assert states(client)[0]["deadline"] == deadline
        assert not provider.calls


def test_timed_budget_requires_provider_support_and_limits_request_timeout(tmp_path):
    @workflow
    def work():
        with provider_budget(max_turns=3, max_seconds=10, turn_timeout_seconds=2):
            return Provider().run("read", timeout=1).value

    unsupported = FakeProvider(["done"])
    with Botpipe(tmp_path, provider=unsupported) as client:
        result = client.run(work)
        assert result.status == "failed"
        assert "supports_timeout" in result.error
        assert not unsupported.calls
        assert states(client)[0]["used_turns"] == 0

    class TimedProvider(FakeProvider):
        supports_timeout = True

    provider = TimedProvider(["done"])
    with Botpipe(tmp_path, provider=provider) as client:
        assert client.run(work).status == "completed"
        assert provider.calls[0].timeout == 1


def test_explicit_retry_consumes_another_reservation(tmp_path):
    @workflow
    def work():
        with provider_budget(max_turns=1):
            return Provider().run("work").value

    provider = FakeProvider([ProviderError("transport lost"), "done"])
    with Botpipe(tmp_path, provider=provider) as client:
        result = client.run(work)
        assert result.status == "interrupted"
        operation = next(
            row
            for row in client.journal.operations(result.run_id)
            if row["kind"] == "provider"
        )
        client.resolve(result.run_id, operation["id"], retry=True)
        resumed = client.resume(result.run_id, workflow=work)
        assert resumed.status == "budget_exceeded", resumed.error
        assert len(provider.calls) == 1
        assert states(client)[0]["used_turns"] == 1


def test_nested_limit_failure_does_not_partially_charge_outer_limit(tmp_path):
    @workflow
    def work():
        with provider_budget(max_turns=5):
            with provider_budget(max_turns=1):
                Provider().run("one")
                Provider().run("two")

    with Botpipe(tmp_path, provider=FakeProvider(["one", "two"])) as client:
        assert client.run(work).status == "budget_exceeded"
        assert [state["used_turns"] for state in states(client)] == [1, 1]
