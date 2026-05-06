from __future__ import annotations

import asyncio
import gc
import warnings
from pathlib import Path

from pydantic import BaseModel

import autoloop.simple as simple
from autoloop.core.engine import Engine
from autoloop.core.primitives import Event, Outcome, RequestInput
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

    async def run_producer(self, request: ProducerRequest) -> ProducerResponse:
        raise AssertionError("sync producer path should not be used")

    async def run_verifier(self, request: VerifierRequest) -> OutcomeResponse:
        raise AssertionError("sync verifier path should not be used")

    async def run_llm(self, request: LLMRequest) -> OutcomeResponse:
        self.async_calls.append(request.step_name)
        return OutcomeResponse(outcome=Outcome(raw_output="ok", tag="done"))

    def run_operation(self, request: object) -> object:  # pragma: no cover - defensive
        raise AssertionError("operation path should not be used")


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


def test_engine_rejects_sync_only_provider_during_construction() -> None:
    class SyncProviderWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        review = simple.step("Review the artifact.", name="review", routes={"done": simple.FINISH})

    with pytest.raises(TypeError, match="must be async coroutine functions"):
        Engine(
            SyncProviderWorkflow,
            provider=_SyncOnlyLLMProvider(),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        )


def test_engine_resume_async_uses_async_core_after_pending_input(tmp_path: Path) -> None:
    class ResumeWorkflow(simple.Workflow):
        class State(BaseModel):
            answer: str | None = None

        @staticmethod
        def _ask(ctx):
            if ctx.input_response is None:
                return RequestInput("Approve the review?")
            ctx.state = ctx.state.model_copy(update={"answer": str(ctx.input_response)})
            return Event("done")

        ask = simple.python_step(_ask, name="ask", routes={"done": simple.Route.to("review")})
        review = simple.step("Review the artifact.", name="review", routes={"done": simple.FINISH})

    task_folder, run_folder = _workspace(tmp_path)
    provider = _AsyncOnlyLLMProvider()
    engine = Engine(
        ResumeWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    first = engine.run(
        task_id="task-resume-async",
        run_id="run-resume-async",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )
    resumed = asyncio.run(
        engine.resume_async(
            task_id="task-resume-async",
            run_id="run-resume-async",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
            answer="yes",
        )
    )

    assert first.terminal == simple.AWAIT_INPUT
    assert resumed.terminal == simple.FINISH
    assert resumed.state.answer == "yes"
    assert provider.async_calls == ["review"]


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
