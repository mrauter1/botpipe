from __future__ import annotations

import threading

import pytest

from botpipe import Botpipe, Provider, aparallel, parallel, workflow
from botpipe.providers import FakeProvider


@pytest.mark.parametrize("async_parallel", [False, True], ids=["parallel", "aparallel"])
def test_parallel_writers_overlap_in_default_workspace(tmp_path, async_parallel):
    barrier = threading.Barrier(2)
    overlapped = threading.Event()

    def hold_turn(request):
        position = barrier.wait(timeout=30)
        if position == 0:
            overlapped.set()
        assert overlapped.wait(30)
        (request.workspace / f"{request.prompt}.txt").write_text(request.prompt)
        return request.prompt

    provider = FakeProvider([hold_turn, hold_turn])

    if async_parallel:

        @workflow
        async def work():
            return await aparallel(
                lambda: Provider().run("first").value,
                lambda: Provider().run("second").value,
            )

    else:

        @workflow
        def work():
            return parallel(
                lambda: Provider().run("first").value,
                lambda: Provider().run("second").value,
            )

    with Botpipe(tmp_path, provider=provider) as client:
        result = client.run(work)
        assert result.ok, result.error
        replay = client.resume(result.run_id, workflow=work)
        assert replay.ok, replay.error
        assert replay.value == result.value

    assert result.ok, result.error
    assert sorted(result.value) == ["first", "second"]
    assert overlapped.is_set()
    assert {call.workspace for call in provider.calls} == {tmp_path.resolve()}
    assert len(provider.calls) == 2
    assert (tmp_path / "first.txt").read_text() == "first"
    assert (tmp_path / "second.txt").read_text() == "second"
