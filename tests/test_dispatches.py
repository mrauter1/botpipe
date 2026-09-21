from __future__ import annotations

import json
import sys

from botpipe import Botpipe, Policy, Session, provider_budget, workflow
from botpipe.providers import (
    CodexProvider,
    FakeProvider,
    ProviderError,
    ProviderResponse,
)


def attempts(client, run_id):
    return [
        dispatch
        for operation in client.inspect(run_id)["operations"]
        for dispatch in operation.get("dispatches", ())
    ]


def test_nested_budgets_share_one_dispatch_identity_and_replay_emits_none(tmp_path):
    @workflow
    def work():
        with provider_budget(max_turns=2):
            with provider_budget(max_turns=2):
                return (
                    Session()
                    .run("work", policy=Policy(model="example", effort="high"))
                    .value
                )

    provider = FakeProvider(
        [ProviderResponse("ok", usage={"input_tokens": 3, "output_tokens": 2})]
    )
    with Botpipe(tmp_path, provider=provider) as client:
        result = client.run(work)
        assert result.status == "completed"
        records = attempts(client, result.run_id)
        assert len(records) == 1
        dispatch = records[0]
        assert dispatch["provider"] == "fake"
        assert dispatch["model"] == "example"
        assert dispatch["effort"] == "high"
        assert dispatch["usage_availability"] == "known_total"
        assert dispatch["total_tokens"] == 5
        assert dispatch["elapsed_seconds"] >= 0
        assert dispatch["started_at"] <= dispatch["finished_at"]
        assert len(dispatch["budgets"]) == 2
        before = [
            event
            for event in client.journal.events(result.run_id)
            if event["event"].startswith("provider_dispatch_")
        ]
        assert len(before) == 3
        assert client.resume(result.run_id, workflow=work).status == "completed"
        assert [
            event
            for event in client.journal.events(result.run_id)
            if event["event"].startswith("provider_dispatch_")
        ] == before


def test_retry_retains_unknown_failed_attempt_instead_of_overwriting_it(tmp_path):
    @workflow
    def work():
        return Session().run("work").value

    provider = FakeProvider(
        [
            ProviderError("lost transport"),
            ProviderResponse("ok", usage={"total_tokens": 7}),
        ]
    )
    with Botpipe(tmp_path, provider=provider) as client:
        result = client.run(work)
        original = attempts(client, result.run_id)[0]
        client.resolve(result.run_id, original["operation_id"], retry=True)
        assert client.resume(result.run_id, workflow=work).status == "completed"
        records = attempts(client, result.run_id)
        assert len(records) == 2
        assert records[0]["dispatch_id"] != records[1]["dispatch_id"]
        assert [d["attempt"] for d in records] == [1, 2]
        assert [d["usage_availability"] for d in records] == ["unknown", "known_total"]
        assert [d["outcome"] for d in records] == ["failed", "completed"]
        operation = next(
            o
            for o in client.inspect(result.run_id)["operations"]
            if o["kind"] == "provider"
        )
        assert operation["usage_availability"] == "partial"
        assert operation["usage"] == {"total_tokens": 7}


def test_schema_repairs_are_separate_physical_dispatches(tmp_path):
    @workflow
    def work():
        return Session().run("number", returns=int).value

    with Botpipe(
        tmp_path,
        provider=FakeProvider(
            [
                ProviderResponse("bad", usage={"total_tokens": 5}),
                ProviderResponse("42", usage={"total_tokens": 7}),
            ]
        ),
    ) as client:
        result = client.run(work)
        records = attempts(client, result.run_id)
        assert result.value == 42
        assert len({d["dispatch_id"] for d in records}) == 2
        assert len({d["operation_id"] for d in records}) == 2
        assert [d["outcome"] for d in records] == ["completed", "completed"]
        assert result.usage == {"total_tokens": 12}


def test_native_failure_preserves_partial_usage_and_timeout_fact(tmp_path):
    script = tmp_path / "native.py"
    script.write_text(
        "import json,time\nprint(json.dumps({'usage':{'input_tokens':3}}),flush=True)\ntime.sleep(5)\n"
    )

    @workflow
    def work():
        return Session().run("work").value

    with Botpipe(
        tmp_path, provider=CodexProvider((sys.executable, str(script))), timeout=0.1
    ) as client:
        result = client.run(work)
        assert result.status == "interrupted"
        record = attempts(client, result.run_id)[0]
        assert record["outcome"] == "timed_out"
        assert record["usage_availability"] == "partial"
        assert record["input_tokens"] == 3
        assert record["timeout_seconds"] == 0.1
        receipt = next((result.folder / "receipts").glob("*.json"))
        assert json.loads(receipt.read_text())["dispatch_id"] == record["dispatch_id"]


def test_interrupt_is_recorded_without_inventing_usage(tmp_path):
    @workflow
    def work():
        return Session().run("work").value

    with Botpipe(tmp_path, provider=FakeProvider([KeyboardInterrupt()])) as client:
        result = client.run(work)
        record = attempts(client, result.run_id)[0]
        assert result.status == "interrupted"
        assert record["outcome"] == "interrupted"
        assert record["usage_availability"] == "unknown"
        assert record["error_type"] == "KeyboardInterrupt"
