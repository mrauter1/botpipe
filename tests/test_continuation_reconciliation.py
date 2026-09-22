"""Reconciliation must advance the same continuation as normal execution."""

import pytest

from botpipe import Botpipe, Provider, Session, workflow
from botpipe.providers import FakeProvider, ProviderContinuation, ProviderResponse
from botpipe.recovery import Completed, Stopped


@workflow
def continued_conversation():
    return Provider(session=Session.task("conversation")).run("continue").value


@pytest.mark.parametrize("recovered", [False, True])
@pytest.mark.parametrize("existing_continuation", [False, True])
def test_reconciliation_retains_continuation_for_the_next_run(
    tmp_path, recovered, existing_continuation
):
    continuation = ProviderContinuation(
        "native-thread", "fake", {"authority": {"tools": ["read"]}}
    )
    response = ProviderResponse("accepted", "native-thread", continuation=continuation)
    if existing_continuation:
        with Botpipe(tmp_path, provider=FakeProvider([response])) as client:
            assert client.run(continued_conversation, task_id="shared-task").ok
        response = ProviderResponse("accepted", "native-thread")
    expected_revision = 2 if existing_continuation else 1

    class InterruptedProvider(FakeProvider):
        def run(self, request):
            self.calls.append(request)
            raise KeyboardInterrupt()

        def recover(self, request):
            return Completed(response) if recovered else Stopped("verified stopped")

    first = InterruptedProvider([])
    with Botpipe(tmp_path, provider=first) as client:
        run = client.run(continued_conversation, task_id="shared-task")
        assert run.status == "interrupted"
        operation = next(
            item for item in client.journal.operations(run.run_id)
            if item["kind"] == "provider"
        )
        arguments = {"retry": True} if recovered else {"response": response}
        client.resolve(run.run_id, operation["id"], **arguments)
        saved = client.journal.get(operation["id"])
        session = client.journal.session(saved["session_id"])
        assert session["continuation"] == continuation
        assert session["revision"] == expected_revision
        assert client.resume(run.run_id, workflow=continued_conversation).value == "accepted"
        assert client.journal.session(saved["session_id"])["revision"] == expected_revision
        assert len(first.calls) == 1

    following = FakeProvider(["next"])
    with Botpipe(tmp_path, provider=following) as client:
        run = client.run(continued_conversation, task_id="shared-task")
        assert run.ok, run.error
        assert following.calls[0].session_id == "native-thread"
        assert following.calls[0].continuation == continuation
