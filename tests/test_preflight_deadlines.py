from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from botpipe import Botpipe, Provider, provider_budget, workflow
from botpipe.capabilities import CapabilityError, CapabilityStatus, CodexCapabilities
from botpipe.codex_appserver import CodexAppServerAdapter
from botpipe.errors import UncertainOperation
from botpipe.policy import NetworkMode, Policy, SandboxMode
from botpipe.providers import (
    CodexProvider,
    ProviderRequest,
    ProviderResponse,
    ProviderTimeoutError,
)
from botpipe.recovery import Unknown


FIXTURE = Path(__file__).parent / "fixtures" / "codex_appserver.py"


def capabilities() -> CodexCapabilities:
    return CodexCapabilities(
        executable=sys.executable,
        version="fixture-version",
        identity="fixture-probe",
        methods=frozenset(
            {
                "initialize",
                "thread/start",
                "thread/resume",
                "turn/start",
                "turn/interrupt",
            }
        ),
        features=({"name": "shell_tool", "enabled": True},),
        supports_turn_sandbox=True,
        supports_interrupt=True,
        supports_tool_config=True,
        supports_mcp_config=True,
        supports_strict_workspace_roots=True,
        presets={name: CapabilityStatus(True) for name in ("run", "query", "generate")},
        item_types=frozenset({"agentMessage", "commandExecution"}),
    )


def budget_state(runtime, run_id):
    operation = next(
        row
        for row in runtime.journal.operations(run_id)
        if row["kind"] == "provider_budget"
    )
    return runtime.journal.budget(operation["id"])


class ExpiredProbeAdapter:
    def __init__(self, expected_ceiling: float) -> None:
        self.expected_ceiling = expected_ceiling
        self.starts = 0

    def probe(self, *, deadline=None):
        assert deadline is not None
        remaining = deadline - time.monotonic()
        assert 0 < remaining <= self.expected_ceiling
        raise TimeoutError("cold probe expired")

    def start_turn(self, request, on_event=None):
        self.starts += 1
        raise AssertionError("timed-out preflight must not dispatch")

    def close(self):
        pass


def dispatch_reservations(runtime: Botpipe) -> list[dict]:
    return [
        event
        for run in runtime.journal.runs()
        for event in runtime.journal.events(run["run_id"])
        if event["event"] == "provider_dispatch_reserved"
    ]


def test_request_timeout_bounds_cold_probe_before_dispatch(tmp_path: Path) -> None:
    adapter = ExpiredProbeAdapter(0.5)
    with Botpipe(
        tmp_path,
        provider=CodexProvider(adapter=adapter),
        state_dir=tmp_path / "state",
    ) as runtime:
        with pytest.raises(ProviderTimeoutError, match="capability probe timed out"):
            Provider(runtime=runtime).generate("answer", timeout=0.5, session=None)

    assert adapter.starts == 0
    assert dispatch_reservations(runtime) == []


def test_supplemental_validator_still_runs_capability_probe(tmp_path: Path) -> None:
    class RejectingCapabilities:
        def require(self, preset):
            raise CapabilityError(f"missing {preset}")

    class ProviderBackend:
        name = "fixture"

        def __init__(self):
            self.validations = 0
            self.probes = 0
            self.runs = 0

        def validate_request(self, request):
            self.validations += 1

        def probe(self):
            self.probes += 1
            return RejectingCapabilities()

        def run(self, request):
            self.runs += 1
            raise AssertionError("rejected capability must not dispatch")

        def recover(self, request):
            return Unknown("preflight rejected before dispatch")

    backend = ProviderBackend()
    with Botpipe(tmp_path, provider=backend, state_dir=tmp_path / "state") as runtime:
        with pytest.raises(CapabilityError, match="missing query"):
            Provider(runtime=runtime).query("answer", session=None)

    assert (backend.validations, backend.probes, backend.runs) == (1, 1, 0)


@pytest.mark.parametrize(
    "budget_options",
    [{"max_seconds": 5}, {"turn_timeout_seconds": 5}],
    ids=["total", "per-turn"],
)
def test_active_budget_bounds_probe_without_charging_a_turn(
    tmp_path: Path, budget_options
) -> None:
    adapter = ExpiredProbeAdapter(5)

    @workflow
    def work():
        with provider_budget(max_turns=1, **budget_options):
            return Provider().generate("answer", timeout=10).value

    with Botpipe(
        tmp_path,
        provider=CodexProvider(adapter=adapter),
        state_dir=tmp_path / "state",
    ) as runtime:
        result = runtime.run(work)
        state = budget_state(runtime, result.run_id)

    assert result.status == "failed"
    assert "capability probe timed out" in result.error
    assert state["used_turns"] == 0
    assert adapter.starts == 0
    assert dispatch_reservations(runtime) == []


def test_probe_and_start_share_one_absolute_deadline(tmp_path: Path, monkeypatch) -> None:
    import botpipe.dispatches as dispatches
    import botpipe.operations as operations

    clock = [100.0]
    monkeypatch.setattr(operations.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(dispatches.time, "monotonic", lambda: clock[0])

    class Adapter:
        def __init__(self):
            self.probe_deadline = None
            self.start_deadline = None

        def probe(self, *, deadline=None):
            self.probe_deadline = deadline
            clock[0] += 3
            return capabilities()

        def start_turn(self, request, on_event=None):
            self.start_deadline = request.deadline
            clock[0] += 3
            if request.deadline is not None and clock[0] >= request.deadline:
                raise ProviderTimeoutError("startup exhausted the shared deadline")
            return ProviderResponse("unexpected")

        def close(self):
            pass

    adapter = Adapter()
    with Botpipe(
        tmp_path,
        provider=CodexProvider(adapter=adapter),
        state_dir=tmp_path / "state",
    ) as runtime:
        with pytest.raises(UncertainOperation, match="shared deadline"):
            Provider(runtime=runtime).generate("answer", timeout=5, session=None)

    assert adapter.probe_deadline == 105
    assert adapter.start_deadline == adapter.probe_deadline


def test_appserver_start_uses_existing_deadline(tmp_path: Path, monkeypatch) -> None:
    import botpipe.codex_appserver as appserver

    clock = [300.0]
    monkeypatch.setattr(appserver.time, "monotonic", lambda: clock[0])
    adapter = CodexAppServerAdapter("unused", capabilities=capabilities())

    def start(*, deadline=None):
        assert deadline == 301
        clock[0] = 302

    monkeypatch.setattr(adapter, "_start", start)
    request = ProviderRequest(
        operation_id="deadline",
        prompt="answer",
        workspace=tmp_path,
        session_id=None,
        output_schema=None,
        policy=Policy(sandbox_mode=SandboxMode.READ_ONLY, network=NetworkMode.NONE),
        artifacts={},
        timeout=10,
        preset="generate",
        tools=(),
        deadline=301,
    )

    with pytest.raises(ProviderTimeoutError, match="dispatch budget: 10 seconds"):
        adapter.start_turn(request)


def test_cached_capability_probe_is_not_repeated_for_start(
    tmp_path: Path, monkeypatch
) -> None:
    import botpipe.codex_appserver as appserver

    calls = []

    def probe(*args, **kwargs):
        calls.append(kwargs["deadline"])
        return capabilities()

    monkeypatch.setattr(appserver, "probe_codex", probe)
    adapter = CodexAppServerAdapter(
        (sys.executable, str(FIXTURE)),
        env={
            "BOTPIPE_FAKE_SCENARIO": "complete",
            "BOTPIPE_FAKE_TRANSCRIPT": str(tmp_path / "transcript.jsonl"),
        },
    )
    with Botpipe(
        tmp_path,
        provider=CodexProvider(adapter=adapter),
        state_dir=tmp_path / "state",
    ) as runtime:
        assert (
            Provider(runtime=runtime).generate("answer", session=None).value
            == "fixture answer"
        )
    assert len(calls) == 1
    assert calls[0] is not None


def test_thread_setup_failure_is_uncharged_and_resume_dispatches_once(
    tmp_path: Path, monkeypatch
) -> None:
    transcript = tmp_path / "transcript.jsonl"
    adapter = CodexAppServerAdapter(
        (sys.executable, str(FIXTURE)),
        env={
            "BOTPIPE_FAKE_SCENARIO": "complete",
            "BOTPIPE_FAKE_TRANSCRIPT": str(transcript),
        },
        capabilities=capabilities(),
    )
    original_rpc = adapter._rpc
    fail_thread_start = True

    def rpc(method, params, timeout, cancel_event=None, *, deadline=None, process=None):
        nonlocal fail_thread_start
        if method == "thread/start" and fail_thread_start:
            fail_thread_start = False
            raise TimeoutError("controlled thread/start failure")
        return original_rpc(
            method,
            params,
            timeout,
            cancel_event,
            deadline=deadline,
            process=process,
        )

    monkeypatch.setattr(adapter, "_rpc", rpc)

    @workflow
    def work():
        with provider_budget(max_turns=1):
            return Provider().generate("answer", session=None).value

    with Botpipe(
        tmp_path,
        provider=CodexProvider(adapter=adapter),
        state_dir=tmp_path / "state",
    ) as runtime:
        first = runtime.run(work, run_id="thread-setup-retry")
        assert first.status == "interrupted"
        assert budget_state(runtime, first.run_id)["used_turns"] == 0
        assert dispatch_reservations(runtime) == []
        operation = next(
            row
            for row in runtime.journal.operations(first.run_id)
            if row["kind"] == "provider"
        )
        attempt = runtime.journal.attempt(operation["id"], 1)
        assert attempt["status"] == "configured"
        assert "dispatch_authorized" not in attempt
        assert "turn/start" not in transcript.read_text()

        resumed = runtime.resume(first.run_id, workflow=work)

        assert resumed.ok, resumed.error
        assert resumed.value == "fixture answer"
        assert budget_state(runtime, first.run_id)["used_turns"] == 1
        assert len(dispatch_reservations(runtime)) == 1


def test_repairs_get_fresh_deadlines_and_one_charge_each(
    tmp_path: Path, monkeypatch
) -> None:
    import botpipe.dispatches as dispatches
    import botpipe.operations as operations

    clock = [200.0]
    monkeypatch.setattr(operations.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(dispatches.time, "monotonic", lambda: clock[0])

    class Adapter:
        def __init__(self):
            self.probe_deadlines = []
            self.start_deadlines = []
            self.responses = iter(["bad", "42"])

        def probe(self, *, deadline=None):
            self.probe_deadlines.append(deadline)
            clock[0] += 1
            return capabilities()

        def start_turn(self, request, on_event=None):
            self.start_deadlines.append(request.deadline)
            clock[0] += 1
            request.on_checkpoint({"status": "turn_intent"})
            return ProviderResponse(next(self.responses))

        def close(self):
            pass

    adapter = Adapter()

    @workflow
    def work():
        with provider_budget(max_turns=2, turn_timeout_seconds=5):
            return Provider().generate("number", returns=int, output_retries=1).value

    with Botpipe(
        tmp_path,
        provider=CodexProvider(adapter=adapter),
        state_dir=tmp_path / "state",
    ) as runtime:
        result = runtime.run(work)
        state = budget_state(runtime, result.run_id)

    assert result.value == 42
    assert adapter.probe_deadlines == [205, 207]
    assert adapter.start_deadlines == adapter.probe_deadlines
    assert state["used_turns"] == 2
