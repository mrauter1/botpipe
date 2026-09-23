from __future__ import annotations

from copy import deepcopy

import pytest

from botpipe import Botpipe, Provider, workflow
from botpipe.providers import FakeProvider, ProviderRequest, ProviderResponse
from botpipe.recovery import Stopped


def _provider_operation(client: Botpipe, run_id: str) -> dict:
    return next(
        row for row in client.journal.operations(run_id) if row["kind"] == "provider"
    )


@pytest.mark.parametrize(
    "response",
    [
        ProviderResponse(123),  # type: ignore[arg-type]
        ProviderResponse("ok", session_id=123),  # type: ignore[arg-type]
        ProviderResponse("ok", usage=[]),  # type: ignore[arg-type]
        ProviderResponse("ok", usage={"tokens": (1, 2)}),
        ProviderResponse("ok", metadata={1: "value"}),  # type: ignore[dict-item]
    ],
)
def test_malformed_provider_response_remains_uncertain(tmp_path, response):
    @workflow
    def work():
        return Provider().run("effectful work").value

    provider = FakeProvider([response])
    with Botpipe(tmp_path, provider=provider) as client:
        result = client.run(work, run_id="invalid-response")
        operation = _provider_operation(client, result.run_id)

    assert result.status == "interrupted"
    assert operation["status"] == "response"
    assert "text" not in (operation["response"] or {})
    assert len(provider.calls) == 1


def test_manual_provider_response_is_validated_before_checkpoint(tmp_path):
    class StoppedProvider(FakeProvider):
        def recover(self, request: ProviderRequest):
            return Stopped("the provider is quiescent")

    @workflow
    def work():
        return Provider().run("effectful work").value

    provider = StoppedProvider([SystemExit("provider response was not checkpointed")])
    with Botpipe(tmp_path, provider=provider) as client:
        with pytest.raises(SystemExit):
            client.run(work, run_id="invalid-manual")
        operation = _provider_operation(client, "invalid-manual")
        before = deepcopy(operation["response"])

        with pytest.raises(TypeError, match="text"):
            client.resolve(
                "invalid-manual",
                operation["id"],
                response={"text": 123},
            )

        assert client.journal.get(operation["id"])["response"] == before


def test_arbitrary_provider_exception_after_dispatch_is_uncertain(tmp_path):
    def fail_after_effects(request: ProviderRequest):
        raise RuntimeError("provider adapter crashed after dispatch")

    @workflow
    def work():
        return Provider().run("effectful work").value

    provider = FakeProvider([fail_after_effects])
    with Botpipe(tmp_path, provider=provider) as client:
        result = client.run(work, run_id="generic-provider-failure")
        operation = _provider_operation(client, result.run_id)

    assert result.status == "interrupted"
    assert operation["status"] == "response"
    assert len(provider.calls) == 1
