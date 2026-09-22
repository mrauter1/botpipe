"""Static consumer acceptance, checked against the installed wheel in CI."""

from typing import assert_type

from pydantic import BaseModel

from botpipe import Codex, Jev, Provider, Result, Session, Stream, current_run
from botpipe.decisions import Choice, DecisionAnswer


class Answer(BaseModel):
    text: str


def check_sync(provider: Provider, codex: Codex, jev: Jev) -> None:
    assert_type(provider.generate("Explain"), Result[str])
    assert_type(provider.generate("Explain", returns=Answer).value, Answer)
    assert_type(provider.query("Inspect", returns=Answer), Result[Answer])
    assert_type(provider.run("Build", returns=Answer), Result[Answer])
    assert_type(provider.with_config(instructions="Review"), Provider)
    assert_type(codex.with_config(instructions="Review"), Codex)
    assert_type(provider.with_config(instructions="Review").query("Inspect", returns=Answer), Result[Answer])
    assert_type(provider.session, Session | None)
    assert_type(current_run().provider.generate("Explain", returns=Answer), Result[Answer])
    assert_type(jev.decide(state={}, questions={"next": Choice("Choose", {"go": "Proceed", "stop": "Stop"})}), Result[dict[str, DecisionAnswer]])
    assert_type(provider.stream("Inspect", operation="query"), Stream[str])
    with provider.stream("Inspect", operation="query", returns=Answer) as stream:
        assert_type(stream, Stream[Answer])
        assert_type(stream.result(), Result[Answer])
    with codex.with_config(instructions="Review") as configured:
        assert_type(configured, Codex)


async def check_async(provider: Provider, jev: Jev) -> None:
    assert_type(await provider.agenerate("Explain"), Result[str])
    assert_type(await provider.agenerate("Explain", returns=Answer), Result[Answer])
    assert_type(await provider.aquery("Inspect", returns=Answer), Result[Answer])
    assert_type(await provider.arun("Build", returns=Answer), Result[Answer])
    assert_type(await jev.adecide(state={}, questions={"next": Choice("Choose", {"go": "Proceed", "stop": "Stop"})}), Result[dict[str, DecisionAnswer]])
    async with provider.astream("Inspect", operation="query", returns=Answer) as stream:
        assert_type(stream, Stream[Answer])
        assert_type(await stream.aresult(), Result[Answer])
