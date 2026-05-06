from __future__ import annotations

import asyncio
import gc
import warnings
from pathlib import Path

from pydantic import BaseModel

import autoloop.simple as simple
from autoloop.core.engine import Engine
from autoloop.core.primitives import Event, Outcome
from autoloop.core.providers.fake import ScriptedLLMProvider
from autoloop.core.providers.models import LLMRequest, OutcomeResponse, ProducerRequest, ProducerResponse, VerifierRequest
from autoloop.core.stores import InMemoryCheckpointStore, InMemorySessionStore


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    task_folder = tmp_path / "task"
    run_folder = tmp_path / "run"
    task_folder.mkdir()
    run_folder.mkdir()
    return task_folder, run_folder


class _AsyncOnlyLLMProvider:
    def __init__(self) -> None:
        self.async_calls: list[str] = []

    def run_producer(self, request: ProducerRequest) -> ProducerResponse:  # pragma: no cover - defensive
        raise AssertionError("sync producer path should not be used")

    def run_verifier(self, request: VerifierRequest) -> OutcomeResponse:  # pragma: no cover - defensive
        raise AssertionError("sync verifier path should not be used")

    def run_llm(self, request: LLMRequest) -> OutcomeResponse:  # pragma: no cover - defensive
        raise AssertionError("sync llm path should not be used")

    def run_operation(self, request: object) -> object:  # pragma: no cover - defensive
        raise AssertionError("operation path should not be used")

    async def run_producer_async(self, request: ProducerRequest) -> ProducerResponse:
        raise AssertionError("producer path should not be used")

    async def run_verifier_async(self, request: VerifierRequest) -> OutcomeResponse:
        raise AssertionError("verifier path should not be used")

    async def run_llm_async(self, request: LLMRequest) -> OutcomeResponse:
        self.async_calls.append(request.step_name)
        return OutcomeResponse(outcome=Outcome(raw_output="ok", tag="done"))


class _SyncOnlyLLMProvider:
    def __init__(self) -> None:
        self.sync_calls: list[str] = []

    def run_producer(self, request: ProducerRequest) -> ProducerResponse:  # pragma: no cover - defensive
        raise AssertionError("producer path should not be used")

    def run_verifier(self, request: VerifierRequest) -> OutcomeResponse:  # pragma: no cover - defensive
        raise AssertionError("verifier path should not be used")

    def run_llm(self, request: LLMRequest) -> OutcomeResponse:
        self.sync_calls.append(request.step_name)
        return OutcomeResponse(outcome=Outcome(raw_output="ok", tag="done"))

    def run_operation(self, request: object) -> object:  # pragma: no cover - defensive
        raise AssertionError("operation path should not be used")


def test_engine_run_async_is_the_sequential_execution_core(tmp_path: Path) -> None:
    class AsyncWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        review = simple.step("Review the artifact.", name="review", routes={"done": simple.FINISH})

    task_folder, run_folder = _workspace(tmp_path)
    provider = _AsyncOnlyLLMProvider()
    engine = Engine(
        AsyncWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = asyncio.run(
        engine.run_async(
            task_id="task-async-engine",
            run_id="run-async-engine",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )
    )

    assert result.terminal == simple.FINISH
    assert provider.async_calls == ["review"]


def test_engine_sync_wrappers_reject_active_event_loop_without_running_coroutines(tmp_path: Path) -> None:
    class WrapperWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        review = simple.step("Review the artifact.", name="review", routes={"done": simple.FINISH})

    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        WrapperWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    async def run_in_loop() -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            for method in (engine.run, engine.resume):
                try:
                    method(
                        task_id="task-sync-wrapper",
                        run_id="run-sync-wrapper",
                        task_folder=task_folder,
                        run_folder=run_folder,
                        root=tmp_path,
                    )
                except RuntimeError as exc:
                    assert "active event loop" in str(exc)
                else:
                    raise AssertionError("sync engine wrapper should reject active-event-loop execution")
            gc.collect()
        assert not any("never awaited" in str(warning.message) for warning in caught)

    asyncio.run(run_in_loop())


def test_engine_run_async_preserves_sequential_sync_provider_compatibility(tmp_path: Path) -> None:
    class SyncProviderWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        review = simple.step("Review the artifact.", name="review", routes={"done": simple.FINISH})

    task_folder, run_folder = _workspace(tmp_path)
    provider = _SyncOnlyLLMProvider()
    engine = Engine(
        SyncProviderWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = asyncio.run(
        engine.run_async(
            task_id="task-sync-provider",
            run_id="run-sync-provider",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )
    )

    assert result.terminal == simple.FINISH
    assert provider.sync_calls == ["review"]


def test_engine_run_wrapper_executes_async_core_for_sequential_workflows(tmp_path: Path) -> None:
    class SyncShellWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        review = simple.step("Review the artifact.", name="review", routes={"done": simple.Route.to("publish")})
        publish = simple.python_step(lambda ctx: Event("done"), name="publish", routes={"done": simple.FINISH})

    task_folder, run_folder = _workspace(tmp_path)
    provider = _AsyncOnlyLLMProvider()
    engine = Engine(
        SyncShellWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-sync-shell",
        run_id="run-sync-shell",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == simple.FINISH
    assert provider.async_calls == ["review"]
