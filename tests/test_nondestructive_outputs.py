"""Provider failures and retries preserve the shared workspace's current state."""

import pytest

from botpipe import Artifact, Botpipe, Provider, workflow
from botpipe.providers import FakeProvider, ProviderError
from botpipe.recovery import Stopped


def test_existing_required_output_is_captured_without_being_recreated(tmp_path):
    destination = tmp_path / "result.txt"
    destination.write_text("existing output")

    def observe(request):
        assert request.artifacts["result"].read_text() == "existing output"
        return "already correct"

    @workflow
    def work():
        return Provider().run("check output", writes=(Artifact.text(destination, required=True),))

    provider = FakeProvider([observe])
    with Botpipe(tmp_path, provider=provider) as client:
        result = client.run(work)
        assert result.ok, result.error
        destination.write_text("later change")
        replay = client.resume(result.run_id, workflow=work)
        assert replay.ok, replay.error
        assert replay.value.artifacts.result.read_text() == "existing output"
        assert destination.read_text() == "later change"
        assert len(provider.calls) == 1


@pytest.mark.parametrize("retry_safe", [False, True])
def test_retry_observes_partial_and_subsequent_edits(tmp_path, retry_safe):
    destination = tmp_path / "result.txt"
    destination.write_text("before")
    other = tmp_path / "other.txt"

    def interrupted(request):
        assert destination.read_text() == "before"
        destination.write_text("partial output")
        other.write_text("additional effect")
        raise ProviderError("provider stopped")

    def finish(request):
        assert destination.read_text() == "partial output plus another writer"
        assert other.read_text() == "additional effect"
        destination.write_text("finished")
        return "done"

    @workflow
    def work():
        return Provider().run(
            "write", writes=(Artifact.text(destination, required=True),), retry_safe=retry_safe
        )

    class StoppedProvider(FakeProvider):
        def recover(self, request):
            return Stopped("confirmed stopped")

    provider = StoppedProvider([interrupted, finish])
    with Botpipe(tmp_path, provider=provider) as client:
        first = client.run(work)
        assert first.status == "interrupted"
        assert destination.read_text() == "partial output"
        assert other.read_text() == "additional effect"
        destination.write_text("partial output plus another writer")
        if not retry_safe:
            blocked = client.resume(first.run_id, workflow=work)
            assert blocked.status == "interrupted"
            assert len(provider.calls) == 1
            operation = next(
                row for row in client.journal.operations(first.run_id)
                if row["kind"] == "provider"
            )
            client.resolve(first.run_id, operation["id"], retry=True)
        result = client.resume(first.run_id, workflow=work)
        assert result.ok, result.error
        assert result.value.artifacts.result.read_text() == "finished"
        assert len(provider.calls) == 2


@pytest.mark.parametrize("repair", [False, True])
def test_output_validation_preserves_files_and_repair_uses_current_state(tmp_path, repair):
    destination = tmp_path / "result.json"
    destination.write_text('{"old": true}')

    def invalid(request):
        assert destination.read_text() == '{"old": true}'
        destination.write_text("invalid partial JSON")
        return "done"

    def fix(request):
        assert destination.read_text() == "invalid partial JSON"
        destination.write_text('{"fixed": true}')
        return "fixed"

    @workflow
    def work():
        return Provider().run(
            "write JSON", writes=(Artifact.json(destination, required=True),),
            output_retries=1 if repair else 0,
        )

    provider = FakeProvider([invalid, fix])
    with Botpipe(tmp_path, provider=provider) as client:
        result = client.run(work)
        if repair:
            assert result.ok, result.error
            assert result.value.artifacts.result.read_json() == {"fixed": True}
            assert len(provider.calls) == 2
        else:
            assert result.status == "failed"
            assert destination.read_text() == "invalid partial JSON"
            assert len(provider.calls) == 1
