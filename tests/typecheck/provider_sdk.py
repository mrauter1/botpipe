"""Strict public typing contract for the Provider-first SDK."""

from __future__ import annotations

from pydantic import BaseModel
from typing_extensions import assert_type

from botpipe import Artifact, Botpipe, Codex, Provider, Result, Session, StreamEvent


class Review(BaseModel):
    accepted: bool


def receive_event(event: StreamEvent) -> None:
    assert_type(event.type, str)


def attached(runtime: Botpipe) -> Provider:
    return Provider(runtime=runtime)


provider = Provider(
    session=Session.task("review"),
    model="example",
    effort="high",
    sandbox="read-only",
    network=False,
    tools=(),
    timeout=30,
    output_retries=1,
    name="review",
    settings={"reasoning": {"summary": "concise"}},
)
configured = provider.with_config(model="next", session=None)
assert_type(configured, Provider)
assert_type(provider.session, Session | None)
assert_type(provider.run("write", writes=(Artifact.text("out.txt"),)), Result[str])
assert_type(provider.run("review", returns=Review, on_event=receive_event), Result[Review])
assert_type(provider.query("inspect", reads=("input.txt",)), Result[str])
assert_type(provider.query("review", returns=Review), Result[Review])
assert_type(provider.generate("draft", allowed_tools=("read_file",)), Result[str])
assert_type(Codex().generate("review", returns=Review), Result[Review])


async def async_contract() -> None:
    assert_type(await provider.arun("write"), Result[str])
    assert_type(await provider.arun("review", returns=Review), Result[Review])
    assert_type(await provider.aquery("inspect"), Result[str])
    assert_type(await provider.aquery("review", returns=Review), Result[Review])
    assert_type(await provider.agenerate("draft"), Result[str])
    assert_type(await provider.agenerate("review", returns=Review), Result[Review])


Provider(runtime="not a runtime")  # type: ignore[arg-type]
Provider(session="not a session")  # type: ignore[arg-type]
provider.run("review", returns=42)  # type: ignore[call-overload]
provider.run("review", policy={})  # type: ignore[call-overload]
provider.run("review", retries=1)  # type: ignore[call-overload]
provider.query("inspect", writes=())  # type: ignore[call-overload]
provider.query("inspect", sandbox="read-only")  # type: ignore[call-overload]
provider.generate("draft", tools=())  # type: ignore[call-overload]
