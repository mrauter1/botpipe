"""Current authority gates future effects without rewriting committed history."""

import pytest

from botpipe import Botpipe, Policy, Provider, ask_human, workflow
from botpipe.providers import FakeProvider


@pytest.mark.parametrize(
    "saved,current,expected",
    [
        (
            {"sandbox_mode": "workspace_write"},
            {"sandbox_mode": "read_only"},
            {"sandbox_mode": "read_only"},
        ),
        (
            {"sandbox_mode": "read_only"},
            {"sandbox_mode": "workspace_write"},
            {"sandbox_mode": "read_only"},
        ),
        (
            {"network": "full"},
            {"network": "limited", "network_domains": ["example.org"]},
            {"network": "limited", "network_domains": ["example.org"]},
        ),
        (
            {"allow_read": ["src", "docs"]},
            {"allow_read": ["docs", "tests"]},
            {"allow_read": ["docs"]},
        ),
    ],
)
def test_changed_ceiling_preserves_replay_and_constrains_next_turn(
    tmp_path, saved, current, expected
):
    @workflow
    def job():
        provider = Provider(session=None)
        first = provider.run("first").value
        ask_human("Continue?")
        return first, provider.run("second").value

    original = FakeProvider(["committed"])
    with Botpipe(tmp_path, provider=original, policy=Policy(**saved)) as runtime:
        paused = runtime.run(job)
        assert paused.status == "awaiting_input", paused.error
        pending_id = paused.pending_input["operation_id"]

    resumed_native = FakeProvider(["future"])
    with Botpipe(tmp_path, provider=resumed_native, policy=Policy(**current)) as runtime:
        completed = runtime.resume(
            paused.run_id, workflow=job, answers={pending_id: "yes"}
        )
        assert completed.ok, completed.error
        assert completed.value == ("committed", "future")
        assert len(resumed_native.calls) == 1
        policy = resumed_native.calls[0].policy.to_dict()
        for field, value in expected.items():
            assert policy[field] == value
    assert len(original.calls) == 1
