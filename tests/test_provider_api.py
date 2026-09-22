"""Behavioral acceptance for the configured public provider boundary."""
import asyncio
import gc
import weakref
from pathlib import Path

import pytest
from pydantic import BaseModel

from botpipe import (
    Botpipe,
    BudgetExceeded,
    Codex,
    Provider,
    Result,
    Session,
    UncertainOperation,
    ask_human,
    workflow,
)
from botpipe.providers import FakeProvider, ProviderError, ProviderResponse


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


@pytest.mark.parametrize("asynchronous", [False, True])
def test_direct_provider_preserves_uncertain_error_type_and_ids(
    tmp_path, asynchronous
):
    with Botpipe(
        tmp_path, provider=FakeProvider([ProviderError("transport lost")])
    ) as runtime:
        provider = Provider(runtime=runtime, session=None)
        with pytest.raises(UncertainOperation, match="transport lost") as raised:
            if asynchronous:
                asyncio.run(provider.arun("effect"))
            else:
                provider.run("effect")

    assert raised.value.run_id
    assert raised.value.operation_id.startswith(raised.value.run_id + ":")


@pytest.mark.parametrize("asynchronous", [False, True])
def test_direct_provider_preserves_budget_error_type_and_ids(tmp_path, asynchronous):
    with Botpipe(
        tmp_path, provider=FakeProvider(["must not dispatch"]), max_operations=1
    ) as runtime:
        provider = Provider(runtime=runtime)
        with pytest.raises(BudgetExceeded) as raised:
            if asynchronous:
                asyncio.run(provider.arun("effect"))
            else:
                provider.run("effect")

    assert raised.value.run_id
    assert raised.value.operation_id.startswith(raised.value.run_id + ":")


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
        with pytest.raises(UncertainOperation):
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


@pytest.mark.parametrize("with_default", [False, True])
def test_explicit_backend_uses_its_catalog_settings_without_becoming_default(
    tmp_path, monkeypatch, with_default
):
    default = 'default_provider = "claude"\n' if with_default else ""
    (tmp_path / "botpipe.toml").write_text(
        default
        + '''[providers.claude.options]
unavailable = true
[providers.codex]
model = "codex-model"
[providers.codex.options]
marker = "codex-options"
''',
        encoding="utf-8",
    )
    native = FakeProvider(["done"])
    resolutions = []

    def resolve(name, config):
        resolutions.append((name, config))
        if name == "claude":
            raise AssertionError("unrelated default was instantiated")
        return native

    monkeypatch.setattr("botpipe.providers.get_provider", resolve)
    with Botpipe(tmp_path) as runtime:
        result = Codex(runtime=runtime, session=None).generate("work")
    assert result.value == "done"
    assert resolutions == [("codex", {"marker": "codex-options"})]
    assert native.calls[0].policy.model == "codex-model"


def test_explicit_backend_without_catalog_entry_uses_empty_settings(
    tmp_path, monkeypatch
):
    native = FakeProvider(["done"])
    seen = []

    def resolve(name, config):
        seen.append((name, config))
        return native

    monkeypatch.setattr("botpipe.providers.get_provider", resolve)
    with Botpipe(tmp_path, provider=None) as runtime:
        assert Codex(runtime=runtime, session=None).generate("work").value == "done"
    assert seen == [("codex", {})]


def test_run_catalog_survives_config_change_before_first_backend_use(
    tmp_path, monkeypatch
):
    config = tmp_path / "botpipe.toml"
    config.write_text(
        'default_provider = "claude"\n[providers.codex.options]\nmarker = "old"\n',
        encoding="utf-8",
    )

    @workflow
    def approval():
        ask_human("continue?")
        return Codex(session=None).generate("work").value

    first = Botpipe(tmp_path)
    paused = first.run(approval, run_id="catalog-snapshot")
    assert paused.status == "awaiting_input"
    first.close()
    config.write_text(
        'default_provider = "claude"\n[providers.codex.options]\nmarker = "new"\n',
        encoding="utf-8",
    )
    seen = []

    def resolve(name, config):
        seen.append((name, config))
        return FakeProvider(["resumed" if config["marker"] == "old" else "new"])

    monkeypatch.setattr("botpipe.providers.get_provider", resolve)
    with Botpipe(tmp_path) as resumed:
        result = resumed.answer(
            paused.run_id,
            paused.pending_input["operation_id"],
            "yes",
            workflow=approval,
        )
        assert result.value == "resumed"

    @workflow
    def fresh():
        return Codex(session=None).generate("work").value

    with Botpipe(tmp_path) as current:
        assert current.run(fresh).value == "new"
    assert seen == [
        ("codex", {"marker": "old"}),
        ("codex", {"marker": "new"}),
    ]


def test_programmatic_runtime_does_not_read_ambient_provider_config(
    tmp_path, monkeypatch
):
    (tmp_path / "botpipe.toml").write_text("unknown = true\n", encoding="utf-8")
    native = FakeProvider(["done"])
    seen = []

    def resolve(name, config):
        seen.append((name, config))
        return native

    monkeypatch.setattr("botpipe.providers.get_provider", resolve)
    with Botpipe(
        tmp_path,
        provider=" CoDeX ",
        provider_config={"marker": "programmatic"},
        provider_defaults={"model": "explicit-model"},
    ) as runtime:
        assert Provider(runtime=runtime, session=None).generate("work").value == "done"
    assert seen == [("codex", {"marker": "programmatic"})]
    assert native.calls[0].policy.model == "explicit-model"


def test_selected_model_and_effort_overrides_reach_provider_request(
    tmp_path, monkeypatch
):
    from botpipe.config import load_config

    (tmp_path / "botpipe.toml").write_text(
        'default_provider = "codex"\n[providers.codex]\nmodel = "base"\n',
        encoding="utf-8",
    )
    configured = load_config(tmp_path, model="cli-model", effort="high")
    native = FakeProvider(["done"])
    monkeypatch.setattr(
        "botpipe.providers.get_provider", lambda name, config: native
    )
    with Botpipe(**configured.client_kwargs()) as runtime:
        Provider(runtime=runtime, session=None).generate("work")
        assert runtime.policy.model is None
        assert runtime.policy.effort is None
    assert native.calls[0].policy.model == "cli-model"
    assert native.calls[0].policy.effort.value == "high"


def test_close_attempts_all_owned_adapters_and_retries_only_failures(
    tmp_path, monkeypatch
):
    events = []

    class ClosingAdapter(FakeProvider):
        def __init__(self, name, failures=0):
            super().__init__([])
            self.name = name
            self.failures = failures
            self.close_calls = 0

        def close(self):
            self.close_calls += 1
            events.append(self.name)
            if self.close_calls <= self.failures:
                raise RuntimeError(f"{self.name} close failed")

    adapters = {
        "codex": ClosingAdapter("codex", failures=1),
        "claude": ClosingAdapter("claude", failures=1),
        "pi": ClosingAdapter("pi"),
    }
    monkeypatch.setattr(
        "botpipe.providers.get_provider", lambda name, config: adapters[name]
    )
    runtime = Botpipe(tmp_path, provider=None)
    close_journal = runtime.journal.close

    def journal_close():
        events.append("journal")
        close_journal()

    runtime.journal.close = journal_close
    for name in adapters:
        runtime.resolve_adapter(name)
    # The same identity under another cache key must still close once.
    runtime._adapter_cache[("duplicate", "{}")]=adapters["pi"]
    with pytest.raises(ExceptionGroup) as raised:
        runtime.close()
    assert len(raised.value.exceptions) == 2
    assert {str(error) for error in raised.value.exceptions} == {
        "codex close failed",
        "claude close failed",
    }
    assert [adapter.close_calls for adapter in adapters.values()] == [1, 1, 1]
    assert events == ["codex", "claude", "pi", "journal"]
    with pytest.raises(Exception, match="closed"):
        runtime.resolve_adapter("pi")
    runtime.close()
    assert [adapter.close_calls for adapter in adapters.values()] == [2, 2, 1]
    runtime.close()
    assert [adapter.close_calls for adapter in adapters.values()] == [2, 2, 1]


def test_close_preserves_one_original_failure(tmp_path, monkeypatch):
    failure = RuntimeError("original close failure")

    class Failing(FakeProvider):
        def close(self):
            raise failure

    native = Failing([])
    monkeypatch.setattr(
        "botpipe.providers.get_provider", lambda name, config: native
    )
    runtime = Botpipe(tmp_path, provider=None)
    runtime.resolve_adapter("codex")
    with pytest.raises(RuntimeError) as raised:
        runtime.close()
    assert raised.value is failure


def test_close_never_closes_caller_owned_adapter(tmp_path):
    class CallerOwned(FakeProvider):
        def __init__(self):
            super().__init__([])
            self.close_calls = 0

        def close(self):
            self.close_calls += 1

    native = CallerOwned()
    runtime = Botpipe(tmp_path, provider=native)
    runtime.close()
    runtime.close()
    assert native.close_calls == 0


def test_injected_mixed_case_name_suspends_and_resumes_with_one_catalog_key(
    tmp_path,
):
    class Mixed(FakeProvider):
        name = "MiXeD"

    @workflow
    def job():
        ask_human("continue?")
        return Provider(session=None).generate("work").value

    native = Mixed(["done"])
    with Botpipe(tmp_path, provider=native) as runtime:
        paused = runtime.run(job, run_id="mixed-name")
        assert paused.status == "awaiting_input"
        recorded = runtime.journal.run(paused.run_id)
        assert recorded["provider"] == "mixed"
        assert set(recorded["provider_catalog"]) == {"mixed"}
        result = runtime.answer(
            paused.run_id,
            paused.pending_input["operation_id"],
            "yes",
            workflow=job,
        )
    assert result.value == "done"


@pytest.mark.parametrize(
    "field,value",
    [
        ("config", {"nested": {"api_key": "TOPSECRET"}}),
        ("defaults", {"nested": {"access_token": "TOPSECRET"}}),
    ],
)
def test_nondefault_public_catalog_rejects_nested_secrets(
    tmp_path, field, value
):
    from botpipe import ConfigurationError

    selection = {"name": "codex", "config": {}, "defaults": {}}
    selection[field] = value
    with pytest.raises(ConfigurationError, match="environment credential"):
        Botpipe(
            tmp_path,
            provider=None,
            provider_catalog={"codex": selection},
        )
    assert not (tmp_path / ".botpipe-v2" / "state.sqlite3").exists()


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_public_catalog_rejects_nonfinite_durable_values(tmp_path, value):
    with pytest.raises(ValueError, match="finite JSON"):
        Botpipe(
            tmp_path,
            provider=None,
            provider_catalog={
                "codex": {
                    "name": "codex",
                    "config": {"temperature": value},
                    "defaults": {},
                }
            },
        )
