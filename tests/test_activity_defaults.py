from __future__ import annotations

import pytest

from botpipe import Botpipe, activity, workflow
from botpipe.providers import FakeProvider


@pytest.mark.parametrize("is_async", [False, True])
@pytest.mark.parametrize("factory", [False, True])
def test_default_activity_recovers_lost_result_after_restart(
    tmp_path, monkeypatch, is_async, factory
):
    calls = []

    @activity
    def completed():
        calls.append("completed")
        return "saved"

    def execute():
        calls.append("unfinished")
        return calls.count("unfinished")

    async def async_execute():
        return execute()

    function = async_execute if is_async else execute
    unfinished = activity()(function) if factory else activity(function)

    @workflow
    async def job():
        before = completed()
        after = await unfinished() if is_async else unfinished()
        return before, after

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        finish = client.journal.finish

        def lose_result(operation_id, value):
            if client.journal.get(operation_id)["name"] == function.__qualname__:
                raise SystemExit("lost before saving result")
            return finish(operation_id, value)

        monkeypatch.setattr(client.journal, "finish", lose_result)
        with pytest.raises(SystemExit, match="lost before saving result"):
            client.run(job, run_id="default-recovery")

    with Botpipe(tmp_path, provider=FakeProvider([])) as restarted:
        resumed = restarted.resume("default-recovery", workflow=job)
        assert resumed.ok, resumed.error
        assert resumed.value == ("saved", 2)
        assert calls == ["completed", "unfinished", "unfinished"]
        assert restarted.resume("default-recovery", workflow=job).value == ("saved", 2)
        assert calls == ["completed", "unfinished", "unfinished"]


def test_default_activity_does_not_retry_recorded_exceptions(tmp_path):
    calls = []

    @activity
    def fail():
        calls.append("failed")
        raise ValueError("rejected")

    @workflow
    def job():
        return fail()

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        result = client.run(job)
        assert result.status == "failed"
        assert "rejected" in result.error
        resumed = client.resume(result.run_id, workflow=job)
        assert resumed.status == "failed"
        assert "rejected" in resumed.error
        assert calls == ["failed"]


def test_exception_retries_can_use_default_retry_safety(tmp_path):
    calls = []

    @activity(retries=1)
    def recover():
        calls.append("attempt")
        if len(calls) == 1:
            raise ValueError("temporary failure")
        return "recovered"

    @workflow
    def job():
        return recover()

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        result = client.run(job)
        assert result.ok, result.error
        assert result.value == "recovered"
        assert calls == ["attempt", "attempt"]


def test_explicit_unsafe_activity_still_rejects_exception_retries():
    with pytest.raises(ValueError, match="retries require retry_safe=True"):
        activity(retry_safe=False, retries=1)
