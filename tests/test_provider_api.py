"""Behavioral acceptance for the configured public provider boundary."""
import asyncio
import gc
import weakref
from pathlib import Path

import pytest
from pydantic import BaseModel

from botpipe import Botpipe, Provider, Result, Session, ask_human, workflow
from botpipe.providers import FakeProvider, ProviderResponse


def test_direct_continuity_derivation_and_independent_override(tmp_path):
    native = FakeProvider([ProviderResponse("first", "one"), "second", "independent", "third", "other"])
    with Botpipe(tmp_path, provider=native) as runtime:
        base = Provider(runtime=runtime)
        planner = base.with_config(instructions="Plan")
        builder = base.with_config(instructions="Build")
        first = planner.generate("start")
        assert builder.generate("continue").value == "second"
        assert planner.session is builder.session is base.session
        builder.generate("independent", session=None)
        builder.generate("continue again")
        Provider(runtime=runtime).generate("different conversation")
        assert [r.session_id for r in native.calls] == [None, "one", None, "one", None]
        assert [r.instructions for r in native.calls[:2]] == ["Plan", "Build"]
        assert first.run_id and first.operation_id
        assert runtime.inspect(first.run_id)["run"]["status"] == "completed"
        assert runtime.resume(first.run_id).value.value == "first"
        assert len(native.calls) == 5


def test_configuration_is_immutable_and_variant_does_not_mutate_original():
    settings = {"vendor": {"limit": [1, 2]}}
    base = Provider(settings=settings)
    settings["vendor"]["limit"].append(3)
    assert base.config["settings"]["vendor"]["limit"] == (1, 2)
    with pytest.raises(TypeError):
        base.config["instructions"] = "changed"
    variant = base.with_config(instructions="Review")
    assert "instructions" not in base.config
    assert variant.config["instructions"] == "Review"


def test_construction_performs_no_config_or_filesystem_io(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("constructor performed I/O")
    monkeypatch.setattr(Path, "resolve", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(Path, "mkdir", forbidden)
    base = Provider()
    base.with_config(instructions="Role", session=Session())
    Session.load("existing-session", state_dir="deferred-state")
    Provider(session=None)


def test_operation_permissions_and_grants_do_not_leak_between_calls(tmp_path):
    native = FakeProvider(["a", "b", "c", "d"])
    with Botpipe(tmp_path, provider=native) as runtime:
        p = Provider(runtime=runtime, allow_commands=(("git", "status", "--short"),))
        p.generate("status")
        p.generate("context only", allow_commands=())
        p.query("inspect")
        p.run("edit")
    assert [r.operation.value for r in native.calls] == ["generate", "generate", "query", "run"]
    assert native.calls[0].allow_commands == (("git", "status", "--short"),)
    assert all(not r.allow_commands for r in native.calls[1:])
    assert all(not r.artifacts for r in native.calls)
    assert native.calls[0].policy.read_only is True


def test_invalid_operation_arguments_never_dispatch(tmp_path):
    native = FakeProvider([])
    with Botpipe(tmp_path, provider=native) as runtime:
        p = Provider(runtime=runtime)
        with pytest.raises(TypeError):
            p.query("write", writes=())
        with pytest.raises(TypeError):
            p.generate("write", writes=())
        with pytest.raises(TypeError):
            p.run("commands", allow_commands=())
        with pytest.raises(ValueError):
            p.generate("bad grant", allow_commands=("git status",))
    assert native.calls == []


def test_workflow_results_keep_returned_wrapper_and_scoped_defaults(tmp_path):
    native = FakeProvider(["one", "two"])
    @workflow
    def wrapped():
        assert Provider() is not Provider()
        assert current_provider() is current_provider()
        return current_provider().generate("one")
    @workflow
    def plain():
        return Provider().generate("two").value
    def current_provider():
        from botpipe import current_run
        return current_run().provider
    with Botpipe(tmp_path, provider=native) as runtime:
        first = runtime.run(wrapped)
        second = runtime.run(plain)
    assert first.ok, first.error
    assert isinstance(first.value, Result)
    assert first.value.value == "one"
    assert second.value == "two"


def test_ephemeral_provider_families_keep_distinct_replay_bindings(tmp_path):
    @workflow
    def ephemeral_calls():
        from botpipe import current_run

        first = Provider(session=None)
        first_family = weakref.ref(first._family)
        first.generate("one")
        del first
        gc.collect()
        assert first_family() is not None

        second = Provider(session=None)
        second.generate("two")
        assert len(current_run()._provider_family_bindings) == 2
        return ask_human("continue?")

    with Botpipe(tmp_path, provider=FakeProvider(["one", "two"])) as runtime:
        paused = runtime.run(ephemeral_calls, run_id="ephemeral-families")
        assert paused.status == "awaiting_input", paused.error
        bindings = [
            row
            for row in runtime.journal.operations(paused.run_id)
            if row["kind"] == "provider_binding"
        ]
        assert len(bindings) == 2
        completed = runtime.answer(
            paused.run_id,
            paused.pending_input["operation_id"],
            "done",
            workflow=ephemeral_calls,
        )
        assert completed.value == "done"


def test_async_direct_call_uses_same_typed_validation(tmp_path):
    class Answer(BaseModel):
        count: int
    native = FakeProvider(['{"count":3,"additional":"allowed by default"}'])
    with Botpipe(tmp_path, provider=native) as runtime:
        p = Provider(runtime=runtime)
        answer = asyncio.run(p.agenerate("count", returns=Answer))
        assert answer.value.count == 3
        assert answer.run_id and answer.operation_id


def test_independent_calls_do_not_create_reusable_native_binding(tmp_path):
    native = FakeProvider([ProviderResponse("one", "ignored-one"), ProviderResponse("two", "ignored-two")])
    with Botpipe(tmp_path, provider=native) as runtime:
        p = Provider(runtime=runtime, session=None)
        p.run("one")
        p.run("two")
        assert p.session is None
        assert [r.session_id for r in native.calls] == [None, None]


def test_native_decision_contract_uses_no_session_and_replays_typed_answers(tmp_path):
    from botpipe.decisions import Noul
    from botpipe.jev import JevAdapter
    requests = []
    def transport(payload, timeout):
        requests.append(payload)
        return {"model": "jev-test", "answers": {"ready": {"type": "noul", "noul": 0.87}}}
    with Botpipe(tmp_path, provider=JevAdapter(transport=transport)) as runtime:
        provider = Provider(runtime=runtime)
        response = provider.decide(state={"evidence": "passed"}, questions={"ready": Noul("Ready?")})
        assert response.value["ready"].noul == 0.87
        assert provider.session is None
        replay = runtime.resume(response.run_id)
        assert replay.value.value["ready"].noul == 0.87
        assert len(requests) == 1
        assert not any(op["kind"] == "session_alias" for op in runtime.journal.operations(response.run_id))
        with pytest.raises(Exception, match="session"):
            provider.decide(state={}, questions={"ready": Noul("Ready?")}, session=None)


def test_interrupted_decision_accepts_typed_stopped_reconciliation(tmp_path):
    from botpipe.decisions import Noul
    from botpipe.jev import JevAdapter
    from botpipe.recovery import Stopped

    class InterruptedDecision(JevAdapter):
        def decide(self, request):
            raise KeyboardInterrupt("response acknowledgement lost")

        def recover(self, request):
            return Stopped("decision transport is quiescent")

    with Botpipe(tmp_path, provider=InterruptedDecision(api_key="unused")) as runtime:
        with pytest.raises(Exception):
            Provider(runtime=runtime).decide(
                state={"evidence": "passed"},
                questions={"ready": Noul("Ready?")},
            )
        run_id = runtime.runs()[0]["run_id"]
        operation = next(
            row
            for row in runtime.journal.operations(run_id)
            if row["kind"] == "decision"
        )
        runtime.resolve(
            run_id,
            operation["id"],
            response={
                "model": "operator-observed",
                "answers": {"ready": {"type": "noul", "noul": 0.9}},
            },
        )
        recovered = runtime.resume(run_id)
        assert recovered.ok, recovered.error
        assert recovered.value.value["ready"].noul == 0.9


def test_pinned_family_resolves_live_adapter_from_each_runtime(tmp_path):
    provider = Provider(session=None)
    first_native = FakeProvider(["first"])
    second_native = FakeProvider(["second"])
    (tmp_path / "first").mkdir()
    (tmp_path / "second").mkdir()

    @workflow
    def job():
        return provider.generate("same operation").value

    with Botpipe(tmp_path / "first", provider=first_native, provider_defaults={"model": "pinned-model"}) as first:
        assert first.run(job).value == "first"
    with Botpipe(tmp_path / "second", provider=second_native, provider_defaults={"model": "new-default"}) as second:
        result = second.run(job)
        assert result.ok, result.error
        assert result.value == "second"
    assert len(first_native.calls) == len(second_native.calls) == 1
    assert first_native.calls[0].policy.model == second_native.calls[0].policy.model == "pinned-model"


def test_explicit_runtime_cannot_be_silently_replaced(tmp_path):
    native = FakeProvider([])
    with Botpipe(tmp_path, provider=native) as attached:
        provider = Provider(runtime=attached)

        @workflow
        def job():
            return provider.generate("attached")

        with Botpipe(tmp_path, provider=FakeProvider([])) as active:
            result = active.run(job)
            assert result.status == "failed"
            assert "another runtime" in result.error
    assert native.calls == []


def test_unsupported_decision_does_not_materialize_conversation(tmp_path):
    from botpipe import CapabilityError
    from botpipe.decisions import Noul

    with Botpipe(tmp_path, provider=FakeProvider([])) as runtime:
        provider = Provider(runtime=runtime)
        with pytest.raises(CapabilityError, match="typed decisions"):
            provider.decide(state={}, questions={"ready": Noul("Ready?")})
        assert provider.session is None


def test_provider_settings_reject_reusable_credentials_before_binding():
    from botpipe import ConfigurationError

    with pytest.raises(ConfigurationError, match="credential"):
        Provider(settings={"api_key": "do-not-record"})
    base = Provider()
    with pytest.raises(ConfigurationError, match="credential"):
        base.with_config(settings={"env": {"VENDOR_API_KEY": "do-not-record"}})
    from botpipe import Policy
    with pytest.raises(ConfigurationError, match="credential"):
        base.with_config(policy=Policy(base_url="https://user:password@example.org"))
    assert base.backend is None


def test_interrupted_direct_call_recovers_without_application_workflow(tmp_path):
    from botpipe.recovery import Completed

    crashed = FakeProvider([SystemExit("lost caller")])
    with Botpipe(tmp_path, provider=crashed) as runtime:
        with pytest.raises(SystemExit, match="lost caller"):
            Provider(runtime=runtime).run("compute", returns=int)
        runs = runtime.runs()
        assert len(runs) == 1
        run_id = runs[0]["run_id"]
        operation = next(
            item for item in runtime.inspect(run_id)["operations"]
            if item["kind"] == "provider"
        )
        assert operation["response"]

    class Recovered(FakeProvider):
        def recover(self, request):
            assert request.operation_id == operation["id"]
            return Completed(ProviderResponse("7", "native-completed"))

    recovered = Recovered([])
    with Botpipe(tmp_path, provider=recovered) as runtime:
        result = runtime.resume(run_id)
        assert result.ok, result.error
        assert result.value.value == 7
        assert result.value.run_id == run_id
        assert result.value.operation_id == operation["id"]
        assert recovered.calls == []


def test_shared_session_rejects_profile_affinity_change_before_dispatch(tmp_path):
    from botpipe import SessionAffinityError

    native = FakeProvider([ProviderResponse("first", "native-one")])
    with Botpipe(tmp_path, provider=native, provider_defaults={"profile": "original"}) as runtime:
        first = Provider(runtime=runtime)
        first.generate("start")
        runtime.provider_defaults = {"profile": "different-account-profile"}
        second = Provider(runtime=runtime, session=first.session)
        with pytest.raises(SessionAffinityError, match="affinity"):
            second.generate("continue")
    assert len(native.calls) == 1
