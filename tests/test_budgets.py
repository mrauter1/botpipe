from __future__ import annotations

import json
import sys

from botpipe import Botpipe, Policy, Provider, ask_human, parallel, provider_budget, workflow
from botpipe.providers import CodexProvider, FakeProvider, ProviderError


def states(client):
    return [
        json.loads(row[0])
        for row in client.journal.db.execute(
            "SELECT state FROM provider_budgets ORDER BY rowid"
        )
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

        # A denied dispatch has no unresolved effects and does not retain a
        # workspace ownership fence against an unrelated new run.
        assert client.run(next_run).status == "completed"


def test_child_parallel_calls_share_one_atomic_limit(tmp_path):
    @workflow
    def child():
        return Provider().run("read", policy=Policy(sandbox_mode="read_only")).value

    @workflow
    def work():
        with provider_budget(max_turns=2):
            return parallel(lambda: child(), lambda: child(), lambda: child())

    provider = FakeProvider(["one", "two", "three"])
    with Botpipe(tmp_path, provider=provider) as client:
        assert client.run(work).status == "budget_exceeded"
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
            client.resume(result.run_id, workflow=work, answers={client.pending(result.run_id)[0]["operation_id"]: "yes"}).status
            == "budget_exceeded"
        )
        assert states(client)[0]["deadline"] == deadline
        assert not provider.calls


def test_timed_budget_requires_provider_support_and_limits_request_timeout(tmp_path):
    @workflow
    def work():
        with provider_budget(max_turns=3, max_seconds=10, turn_timeout_seconds=2):
            return Provider().run("read", policy=Policy(timeout=1)).value

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


def test_native_receipt_recovery_does_not_consume_another_turn(tmp_path, monkeypatch):
    script = tmp_path / "native.py"
    script.write_text(
        'import json\nprint(json.dumps({"type":"item.completed", "item":'
        '{"type":"agent_message", "text":"done"}}))\n'
        'print(json.dumps({"type":"turn.completed"}))\n'
    )
    provider = CodexProvider((sys.executable, str(script)))

    @workflow
    def work():
        with provider_budget(max_turns=1):
            return Provider().run("work").value

    with Botpipe(tmp_path, provider=provider) as client:
        original = client.journal.response
        interrupted_response = False

        def crash(operation_id, response, **kwargs):
            nonlocal interrupted_response
            if "text" in response:
                interrupted_response = True
                raise KeyboardInterrupt()
            return original(operation_id, response, **kwargs)

        monkeypatch.setattr(client.journal, "response", crash)
        result = client.run(work)
        assert result.status == "interrupted"
        assert interrupted_response, result.error
        monkeypatch.setattr(client.journal, "response", original)
        resumed = client.resume(result.run_id, workflow=work)
        assert resumed.status == "completed", resumed.error
        assert resumed.value == "done"
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
