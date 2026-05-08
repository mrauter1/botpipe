from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest
from pydantic import BaseModel

from botlane.core.branch_groups import runtime as branch_group_runtime
from botlane.core.engine import Engine
from botlane.core.errors import WorkflowExecutionError
from botlane.core.primitives import Event, Goto, Outcome, RequestInput
from botlane.core.providers.fake import ScriptedLLMProvider
from botlane.core.providers.models import LLMRequest, OutcomeResponse, ProducerRequest, ProducerResponse, VerifierRequest
from botlane.core.stores import InMemoryCheckpointStore, InMemorySessionStore
from botlane.core.stores.protocols import SessionBinding
import botlane.simple as simple


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    task_folder = tmp_path / "task"
    run_folder = tmp_path / "run"
    task_folder.mkdir()
    run_folder.mkdir()
    return task_folder, run_folder


def _workflow_folder(task_folder: Path, workflow_cls: type[object]) -> Path:
    workflow_name = re.sub(r"(?<!^)(?=[A-Z])", "_", workflow_cls.__name__).lower()
    workflow_name = re.sub(r"[^a-z0-9_]+", "_", workflow_name).strip("_") or workflow_cls.__name__.lower()
    return task_folder / f"wf_{workflow_name}"


def _branch_group_dir(task_folder: Path, workflow_cls: type[object], group_name: str) -> Path:
    return _workflow_folder(task_folder, workflow_cls) / "_branch_groups" / group_name


def _prompt_routed_outcome(request: object) -> Outcome:
    prompt_text = request.prompt.text
    if prompt_text == "Approved.":
        return Outcome(raw_output="approved", tag="approved")
    return Outcome(raw_output="done", tag="done")


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
    def run_producer(self, request: ProducerRequest) -> ProducerResponse:
        return ProducerResponse(raw_output="draft")

    def run_verifier(self, request: VerifierRequest) -> OutcomeResponse:
        return OutcomeResponse(outcome=Outcome(raw_output="ok", tag="done"))

    def run_llm(self, request: LLMRequest) -> OutcomeResponse:
        return OutcomeResponse(outcome=Outcome(raw_output="ok", tag="done"))

    def run_operation(self, request: object) -> object:  # pragma: no cover - defensive
        raise AssertionError("operation path should not be used")


class _ConcurrentAsyncLLMProvider:
    def __init__(
        self,
        *,
        delays: dict[str, float] | None = None,
        fail_steps: set[str] | None = None,
    ) -> None:
        self.delays = delays or {}
        self.fail_steps = fail_steps or set()
        self.started: list[str] = []
        self.completed: list[str] = []
        self.cancelled: list[str] = []
        self.prompts: list[str] = []
        self.active = 0
        self.max_active = 0

    async def run_producer(self, request: ProducerRequest) -> ProducerResponse:
        raise AssertionError("sync producer path should not be used")

    async def run_verifier(self, request: VerifierRequest) -> OutcomeResponse:
        raise AssertionError("sync verifier path should not be used")

    async def run_llm(self, request: LLMRequest) -> OutcomeResponse:
        step_name = request.step_name
        self.started.append(step_name)
        self.prompts.append(request.prompt.text)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(self.delays.get(step_name, 0.01))
            if step_name in self.fail_steps:
                raise RuntimeError(f"{step_name} failed")
            self.completed.append(step_name)
            return OutcomeResponse(outcome=Outcome(raw_output=f"{step_name} ok", tag="done"))
        except asyncio.CancelledError:
            self.cancelled.append(step_name)
            raise
        finally:
            self.active -= 1

    def run_operation(self, request: object) -> object:  # pragma: no cover - defensive
        raise AssertionError("operation path should not be used")


def test_parallel_branch_group_without_fan_in_routes_question_and_writes_evidence(tmp_path: Path) -> None:
    class ReviewWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        reviews = simple.parallel(
            branches={
                "security": simple.python_step(lambda ctx: RequestInput("Approve security review?"), name="security_review"),
                "cost": simple.python_step(lambda ctx: Event("done"), name="cost_review"),
            }
        )
        publish = simple.python_step(lambda ctx: Event("done"))

    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        ReviewWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-branch-question",
        run_id="run-branch-question",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == simple.AWAIT_INPUT
    assert result.checkpoint is not None
    assert result.checkpoint.stage == "reviews"
    results_path = _branch_group_dir(task_folder, ReviewWorkflow, "reviews") / "results.json"
    context_path = _branch_group_dir(task_folder, ReviewWorkflow, "reviews") / "context.md"
    manifest = json.loads(results_path.read_text(encoding="utf-8"))
    context_text = context_path.read_text(encoding="utf-8")
    assert manifest["schema"] == "botlane.branch_results/v1"
    assert [branch["name"] for branch in manifest["branches"]] == ["security", "cost"]
    assert manifest["branches"][0]["status"] == "needs_input"
    assert manifest["branches"][0]["question"] == "Approve security review?"
    assert manifest["branches"][1]["status"] == "completed"
    assert "Approve security review?" in context_text
    assert "## Needs Input Details" in context_text
    assert "- security: Approve security review?" in context_text


def test_parallel_branch_group_with_fan_in_routes_through_fan_in_and_exposes_helpers(tmp_path: Path) -> None:
    seen: dict[str, object] = {}

    class FanInWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        reviews = simple.parallel(
            branches={
                "security": simple.step("Review {branch.name}.", name="security_review", session=simple.Session.fresh()),
                "cost": simple.step("Review {branch.name}.", name="cost_review", session=simple.Session.fresh()),
            },
            fan_in=simple.step(
                "Summarize {fan_in.branch_count} branches.\n{fan_in.context_text}",
                name="combine_reviews",
                reads=[simple.FanIn.results(), simple.FanIn.context()],
                routes={"approved": simple.FINISH},
            ),
        )

    provider = ScriptedLLMProvider(
        llm_turns=[
            Outcome(raw_output="security ok", tag="done"),
            Outcome(raw_output="cost ok", tag="done"),
            lambda request: (
                seen.update(
                    {
                        "branch_count": request.context.fan_in.branch_count,
                        "results_path": request.context.fan_in.results_path,
                        "context_path": request.context.fan_in.context_path,
                        "context_text": request.context.fan_in.context_text,
                        "readable_paths": tuple(ref.path for ref in request.readable_artifacts),
                    }
                )
                or Outcome(raw_output="approved", tag="approved")
            ),
        ]
    )
    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        FanInWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-fan-in",
        run_id="run-fan-in",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == simple.FINISH
    assert result.last_event is not None
    assert result.last_event.tag == "approved"
    assert seen["branch_count"] == 2
    expected_results_path = _branch_group_dir(task_folder, FanInWorkflow, "reviews") / "results.json"
    expected_context_path = _branch_group_dir(task_folder, FanInWorkflow, "reviews") / "context.md"
    assert seen["results_path"] == expected_results_path
    assert seen["context_path"] == expected_context_path
    assert "Branch Group: reviews" in str(seen["context_text"])
    assert str(expected_results_path) in seen["readable_paths"]
    assert str(expected_context_path) in seen["readable_paths"]


def test_parallel_branch_group_exposes_workflow_scoped_evidence_to_downstream_reads(tmp_path: Path) -> None:
    class DownstreamReadWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        reviews = simple.parallel(
            branches={
                "security": simple.python_step(lambda ctx: Event("done"), name="security_review"),
                "cost": simple.python_step(lambda ctx: Event("done"), name="cost_review"),
            }
        )
        publish = simple.step(
            "Summarize branch evidence.",
            name="publish",
            reads=["_branch_groups/reviews/results.json", "_branch_groups/reviews/context.md"],
            routes={"done": simple.FINISH},
        )

    provider = ScriptedLLMProvider(llm_turns=[Outcome(raw_output="published", tag="done")])
    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        DownstreamReadWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-downstream-reads",
        run_id="run-downstream-reads",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == simple.FINISH
    assert len(provider.calls) == 1
    readable_refs = provider.calls[0].readable_artifacts
    expected_results_path = _branch_group_dir(task_folder, DownstreamReadWorkflow, "reviews") / "results.json"
    expected_context_path = _branch_group_dir(task_folder, DownstreamReadWorkflow, "reviews") / "context.md"

    assert tuple(ref.name for ref in readable_refs) == (
        "_branch_groups/reviews/results.json",
        "_branch_groups/reviews/context.md",
    )
    assert tuple(ref.path for ref in readable_refs) == (
        str(expected_results_path),
        str(expected_context_path),
    )
    assert all(ref.exists for ref in readable_refs)
    assert all(ref.declared_artifact is False for ref in readable_refs)


def test_parallel_branch_group_uses_async_provider_path_for_branch_steps(tmp_path: Path) -> None:
    class AsyncProviderWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        reviews = simple.parallel(
            branches={
                "security": simple.step("Review security.", name="security_review", session=simple.Session.fresh()),
                "cost": simple.step("Review cost.", name="cost_review", session=simple.Session.fresh()),
            }
        )
        publish = simple.python_step(lambda ctx: Event("done"))

    provider = _AsyncOnlyLLMProvider()
    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        AsyncProviderWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-async-provider",
        run_id="run-async-provider",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == simple.FINISH
    assert provider.async_calls == ["security_review", "cost_review"]


def test_parallel_branch_group_supports_provider_backed_concurrency_one(tmp_path: Path) -> None:
    class SequentialAsyncProviderWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        reviews = simple.parallel(
            concurrency=1,
            branches={
                "security": simple.step("Review security.", name="security_review", session=simple.Session.fresh()),
                "cost": simple.step("Review cost.", name="cost_review", session=simple.Session.fresh()),
            },
        )
        publish = simple.python_step(lambda ctx: Event("done"))

    provider = _ConcurrentAsyncLLMProvider(
        delays={"security_review": 0.01, "cost_review": 0.01},
    )
    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        SequentialAsyncProviderWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-sequential-async-provider",
        run_id="run-sequential-async-provider",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == simple.FINISH
    assert provider.max_active == 1
    assert provider.started == ["security_review", "cost_review"]
    assert provider.completed == ["security_review", "cost_review"]


def test_parallel_branch_group_runs_provider_backed_branches_concurrently(tmp_path: Path) -> None:
    class ConcurrentParallelWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        reviews = simple.parallel(
            concurrency=2,
            branches={
                "security": simple.step("Review security.", name="security_review", session=simple.Session.fresh()),
                "cost": simple.step("Review cost.", name="cost_review", session=simple.Session.fresh()),
            },
        )
        publish = simple.python_step(lambda ctx: Event("done"))

    provider = _ConcurrentAsyncLLMProvider(
        delays={"security_review": 0.05, "cost_review": 0.05},
    )
    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        ConcurrentParallelWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-concurrent-parallel",
        run_id="run-concurrent-parallel",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == simple.FINISH
    assert provider.max_active == 2
    assert set(provider.completed) == {"security_review", "cost_review"}


def test_fan_out_branch_group_runs_provider_backed_branches_concurrently(tmp_path: Path) -> None:
    class ConcurrentFanOutWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        assess = simple.fan_out(
            concurrency=2,
            step=simple.step(
                "Assess area {branch.input.area}.",
                name="assess_one",
                session=simple.Session.fresh(),
            ),
            branches={
                "security": {"area": "security"},
                "performance": {"area": "performance"},
            },
        )
        publish = simple.python_step(lambda ctx: Event("done"))

    provider = _ConcurrentAsyncLLMProvider(delays={"assess_one": 0.05})
    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        ConcurrentFanOutWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-concurrent-fan-out",
        run_id="run-concurrent-fan-out",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == simple.FINISH
    assert provider.max_active == 2
    assert set(provider.prompts) == {"Assess area security.", "Assess area performance."}


def test_parallel_branch_group_rejects_sync_only_provider_for_provider_backed_steps(tmp_path: Path) -> None:
    class SyncOnlyWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        reviews = simple.parallel(
            branches={"security": simple.step("Review security.", name="security_review", session=simple.Session.fresh())}
        )
        publish = simple.python_step(lambda ctx: Event("done"))

    with pytest.raises(TypeError, match="must be async coroutine functions"):
        Engine(
            SyncOnlyWorkflow,
            provider=_SyncOnlyLLMProvider(),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        )


def test_fan_out_renders_branch_input_roots_artifacts_and_keeps_branch_sessions_local(tmp_path: Path) -> None:
    prompts: list[str] = []
    sessions: list[str | None] = []
    session_keys_by_branch: dict[str, str] = {}
    returned_sessions: list[str] = []

    class FanOutWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        assess = simple.fan_out(
            step=simple.step(
                "Assess area {branch.input.area}.",
                name="assess_one",
                session=simple.Session.fresh(),
                writes=[simple.Md("report", path="reports/{branch.name}.md")],
                after=lambda ctx: (ctx.write(ctx.artifacts.report, f"{ctx.branch.input.area}\n") or None),
            ),
            branches={
                "security": {"area": "security"},
                "performance": {"area": "performance"},
            },
        )
        publish = simple.python_step(lambda ctx: Event("done"))

    provider = ScriptedLLMProvider(
        llm_turns=[
            lambda request: (
                prompts.append(request.prompt.text),
                sessions.append(None if request.session is None else request.session.session_id),
                session_keys_by_branch.__setitem__(request.context.branch.name, request.session.key.value),
                returned_sessions.append(f"provider-session-{request.context.branch.name}"),
                OutcomeResponse(
                    outcome=Outcome(raw_output="ok", tag="done"),
                    session=SessionBinding(
                        key=request.session.key,
                        session_id=f"provider-session-{request.context.branch.name}",
                    ),
                ),
            )[-1],
            lambda request: (
                prompts.append(request.prompt.text),
                sessions.append(None if request.session is None else request.session.session_id),
                session_keys_by_branch.__setitem__(request.context.branch.name, request.session.key.value),
                returned_sessions.append(f"provider-session-{request.context.branch.name}"),
                OutcomeResponse(
                    outcome=Outcome(raw_output="ok", tag="done"),
                    session=SessionBinding(
                        key=request.session.key,
                        session_id=f"provider-session-{request.context.branch.name}",
                    ),
                ),
            )[-1],
        ]
    )
    session_store = InMemorySessionStore()
    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        FanOutWorkflow,
        provider=provider,
        session_store=session_store,
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-fan-out",
        run_id="run-fan-out",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == simple.FINISH
    assert len(prompts) == 2
    assert set(prompts) == {"Assess area security.", "Assess area performance."}
    assert sessions == [None, None]
    assert session_keys_by_branch["security"].startswith("assess:security:0:")
    assert session_keys_by_branch["performance"].startswith("assess:performance:1:")
    assert session_keys_by_branch["security"] != session_keys_by_branch["performance"]
    parent_snapshot = session_store.snapshot()
    assert all(binding.session_id not in returned_sessions for binding in parent_snapshot.bindings)
    security_report = task_folder / "wf_fan_out_workflow" / "assess_one" / "reports" / "security.md"
    performance_report = task_folder / "wf_fan_out_workflow" / "assess_one" / "reports" / "performance.md"
    assert security_report.read_text(encoding="utf-8").strip() == "security"
    assert performance_report.read_text(encoding="utf-8").strip() == "performance"
    manifest = json.loads((_branch_group_dir(task_folder, FanOutWorkflow, "assess") / "results.json").read_text(encoding="utf-8"))
    assert manifest["branches"][0]["artifacts"][0]["path"].endswith("wf_fan_out_workflow/assess_one/reports/security.md")
    assert manifest["branches"][1]["artifacts"][0]["path"].endswith("wf_fan_out_workflow/assess_one/reports/performance.md")
    assert [branch["provider_session"] for branch in manifest["branches"]] == [
        "provider-session-security",
        "provider-session-performance",
    ]
    assert manifest["branches"][0]["provider_sessions"] == {"producer": "provider-session-security"}
    assert manifest["branches"][1]["provider_sessions"] == {"producer": "provider-session-performance"}
    assert manifest["branches"][0]["raw_output_path"] == str(
        (_branch_group_dir(task_folder, FanOutWorkflow, "assess") / "branches" / "security" / "producer.txt").relative_to(tmp_path)
    )
    assert manifest["branches"][1]["raw_output_path"] == str(
        (_branch_group_dir(task_folder, FanOutWorkflow, "assess") / "branches" / "performance" / "producer.txt").relative_to(tmp_path)
    )


def test_parallel_branch_group_leaves_manifest_provider_session_empty_without_provider_returned_id(tmp_path: Path) -> None:
    seen_sessions: list[str | None] = []

    class NoReturnedSessionWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        reviews = simple.parallel(
            branches={
                "security": simple.step(
                    "Review security.",
                    name="security_review",
                    session=simple.Session.fresh(),
                )
            },
            routes={"done": simple.FINISH},
        )

    provider = ScriptedLLMProvider(
        llm_turns=[
            lambda request: (
                seen_sessions.append(None if request.session is None else request.session.session_id),
                Outcome(raw_output="ok", tag="done"),
            )[-1]
        ]
    )
    session_store = InMemorySessionStore()
    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        NoReturnedSessionWorkflow,
        provider=provider,
        session_store=session_store,
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-no-returned-session",
        run_id="run-no-returned-session",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == simple.FINISH
    assert seen_sessions == [None]
    manifest = json.loads(
        (_branch_group_dir(task_folder, NoReturnedSessionWorkflow, "reviews") / "results.json").read_text(encoding="utf-8")
    )
    branch = manifest["branches"][0]
    assert branch["provider_session"] is None
    assert branch["provider_sessions"] == {}
    assert all(binding.session_id is not None for binding in session_store.snapshot().bindings)


def test_parallel_branch_group_does_not_leak_parent_active_provider_session_into_fresh_branch_sessions(
    tmp_path: Path,
) -> None:
    seen_sessions: list[str | None] = []

    class SessionIsolationWorkflow(simple.Workflow):
        class State(BaseModel):
            parent_session_after_setup: str | None = None
            parent_session_after_reviews: str | None = None

        main = simple.Session.fresh()
        prepare = simple.python_step(
            lambda ctx: (
                ctx._session_store.upsert(
                    SessionBinding(
                        key=ctx.open_session("main").key,
                        session_id="parent-provider-session",
                        metadata={"provider": "codex"},
                    )
                ),
                setattr(
                    ctx,
                    "state",
                    ctx.state.model_copy(update={"parent_session_after_setup": ctx.get_session("main").session_id}),
                ),
                Event("done"),
            )[-1]
        )
        reviews = simple.parallel(
            branches={
                "security": simple.step(
                    "Review security.",
                    name="security_review",
                    session=main,
                )
            }
        )
        publish = simple.python_step(
            lambda ctx: (
                setattr(
                    ctx,
                    "state",
                    ctx.state.model_copy(update={"parent_session_after_reviews": ctx.get_session("main").session_id}),
                ),
                Event("done"),
            )[-1],
            routes={"done": simple.FINISH},
        )

    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        SessionIsolationWorkflow,
        provider=ScriptedLLMProvider(
            llm_turns=[
                lambda request: (
                    seen_sessions.append(None if request.session is None else request.session.session_id),
                    Outcome(raw_output="ok", tag="done"),
                )[-1]
            ]
        ),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-parent-session-isolation",
        run_id="run-parent-session-isolation",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == simple.FINISH
    assert result.history == ("prepare", "reviews", "publish")
    assert seen_sessions == [None]
    assert result.state.parent_session_after_setup == "parent-provider-session"
    assert result.state.parent_session_after_reviews == "parent-provider-session"
    manifest = json.loads(
        (_branch_group_dir(task_folder, SessionIsolationWorkflow, "reviews") / "results.json").read_text(encoding="utf-8")
    )
    branch = manifest["branches"][0]
    assert branch["provider_session"] is None
    assert branch["provider_sessions"] == {}


def test_parallel_branch_group_captures_goto_without_following_branch_destination(tmp_path: Path) -> None:
    class GotoWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        reviews = simple.parallel(
            outcome="any_done",
            branches={
                "reroute": simple.python_step(lambda ctx: Goto("repair"), name="reroute_branch"),
                "complete": simple.python_step(lambda ctx: Event("done"), name="complete_branch"),
            },
        )
        publish = simple.python_step(lambda ctx: Event("done"))
        repair = simple.python_step(lambda ctx: Event("done"))

    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        GotoWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-branch-goto",
        run_id="run-branch-goto",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == simple.FINISH
    assert result.history[:2] == ("reviews", "publish")
    manifest = json.loads((_branch_group_dir(task_folder, GotoWorkflow, "reviews") / "results.json").read_text(encoding="utf-8"))
    reroute_branch = next(branch for branch in manifest["branches"] if branch["name"] == "reroute")
    assert reroute_branch["status"] == "completed"
    assert reroute_branch["runtime_control"] == "goto"
    assert reroute_branch["destination"] == "repair"


def test_parallel_branch_group_captures_fail_runtime_control_as_failed(tmp_path: Path) -> None:
    class FailWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        reviews = simple.parallel(
            outcome="all_settled",
            branches={
                "stop": simple.python_step(lambda ctx: simple.Fail("stop branch"), name="stop_branch"),
                "complete": simple.python_step(lambda ctx: Event("done"), name="complete_branch"),
            },
            routes={"partial": simple.FINISH, "done": simple.FINISH},
        )
        publish = simple.python_step(lambda ctx: Event("done"))

    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        FailWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-branch-fail",
        run_id="run-branch-fail",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == simple.FINISH
    assert result.last_event is not None
    assert result.last_event.tag == "partial"
    manifest = json.loads((_branch_group_dir(task_folder, FailWorkflow, "reviews") / "results.json").read_text(encoding="utf-8"))
    failed_branch = next(branch for branch in manifest["branches"] if branch["name"] == "stop")
    assert failed_branch["status"] == "failed"
    assert failed_branch["runtime_control"] == "fail"
    assert failed_branch["route"] is None
    assert failed_branch["destination"] == "FAIL"
    assert failed_branch["error"] == {
        "type": "Fail",
        "message": "Branch returned Fail control.",
        "failure_context": None,
        "retry_kind": None,
        "retry_exhausted": False,
    }


def test_parallel_branch_group_capture_mode_skips_branch_route_on_taken_hooks(tmp_path: Path) -> None:
    on_taken_calls: list[str] = []

    def on_taken(ctx: object) -> None:
        on_taken_calls.append("done")

    class CaptureWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        reviews = simple.parallel(
            outcome="all_done",
            branches={
                "security": simple.python_step(
                    lambda ctx: Event("done"),
                    name="security_review",
                    routes={"done": simple.Route.to("repair", on_taken=on_taken)},
                )
            },
            routes={"done": "publish"},
        )
        publish = simple.python_step(lambda ctx: Event("done"))
        repair = simple.python_step(lambda ctx: Event("done"))

    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        CaptureWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-capture-on-taken",
        run_id="run-capture-on-taken",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == simple.FINISH
    assert result.history[:2] == ("reviews", "publish")
    assert on_taken_calls == []
    manifest = json.loads((_branch_group_dir(task_folder, CaptureWorkflow, "reviews") / "results.json").read_text(encoding="utf-8"))
    assert manifest["branches"][0]["route"] == "done"
    assert manifest["branches"][0]["destination"] == "repair"


def test_parallel_branch_group_fail_fast_stops_new_branch_launches_and_persists_skipped_results(tmp_path: Path) -> None:
    executed: list[str] = []

    def fail_now(ctx: object) -> Event:
        executed.append("explode")
        raise RuntimeError("boom")

    def finish(name: str) -> object:
        def _finish(ctx: object) -> Event:
            executed.append(name)
            return Event("done")

        return _finish

    class FailFastWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        reviews = simple.parallel(
            name="reviews",
            settle="fail_fast",
            concurrency=1,
            outcome="all_settled",
            branches={
                "explode": simple.python_step(fail_now, name="explode_branch"),
                "later_a": simple.python_step(finish("later_a"), name="later_a_branch"),
                "later_b": simple.python_step(finish("later_b"), name="later_b_branch"),
            },
            routes={"partial": simple.FINISH, "done": simple.FINISH},
        )

    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        FailFastWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-fail-fast",
        run_id="run-fail-fast",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == simple.FINISH
    assert result.last_event is not None
    assert result.last_event.tag == "partial"
    assert executed == ["explode"]

    manifest = json.loads((_branch_group_dir(task_folder, FailFastWorkflow, "reviews") / "results.json").read_text(encoding="utf-8"))
    assert manifest["settle"] == "fail_fast"
    assert [branch["name"] for branch in manifest["branches"]] == ["explode", "later_a", "later_b"]
    assert [branch["status"] for branch in manifest["branches"]] == ["failed", "skipped", "skipped"]
    assert manifest["branches"][1]["reason"] == "Branch was not scheduled because fail_fast stopped new branch launches."
    assert manifest["branches"][2]["reason"] == "Branch was not scheduled because fail_fast stopped new branch launches."


def test_parallel_branch_group_fail_fast_cancels_in_flight_async_branches_and_keeps_manifest_order(
    tmp_path: Path,
) -> None:
    class AsyncFailFastWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        reviews = simple.parallel(
            name="reviews",
            settle="fail_fast",
            concurrency=3,
            outcome="all_settled",
            branches={
                "explode": simple.step("Explode.", name="explode_branch", session=simple.Session.fresh()),
                "slow_a": simple.step("Slow A.", name="slow_a_branch", session=simple.Session.fresh()),
                "slow_b": simple.step("Slow B.", name="slow_b_branch", session=simple.Session.fresh()),
                "later": simple.step("Later.", name="later_branch", session=simple.Session.fresh()),
            },
            routes={"partial": simple.FINISH, "done": simple.FINISH},
        )

    provider = _ConcurrentAsyncLLMProvider(
        delays={
            "explode_branch": 0.01,
            "slow_a_branch": 0.2,
            "slow_b_branch": 0.2,
            "later_branch": 0.2,
        },
        fail_steps={"explode_branch"},
    )
    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        AsyncFailFastWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-fail-fast-cancel",
        run_id="run-fail-fast-cancel",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == simple.FINISH
    assert result.last_event is not None
    assert result.last_event.tag == "partial"
    assert sorted(provider.cancelled) == ["slow_a_branch", "slow_b_branch"]

    manifest = json.loads((_branch_group_dir(task_folder, AsyncFailFastWorkflow, "reviews") / "results.json").read_text(encoding="utf-8"))
    context_text = (_branch_group_dir(task_folder, AsyncFailFastWorkflow, "reviews") / "context.md").read_text(
        encoding="utf-8"
    )
    assert [branch["name"] for branch in manifest["branches"]] == ["explode", "slow_a", "slow_b", "later"]
    assert [branch["status"] for branch in manifest["branches"]] == ["failed", "cancelled", "cancelled", "skipped"]
    assert manifest["branches"][1]["cancellation_requested"] is True
    assert manifest["branches"][2]["cancellation_completed"] is True
    assert manifest["branches"][3]["reason"] == "Branch was not scheduled because fail_fast stopped new branch launches."
    assert "## Failure Summary" in context_text
    failure_detail = "- explode: WorkflowExecutionError: explode_branch failed"
    assert failure_detail in context_text
    assert context_text.index("## Failure Summary") < context_text.index(failure_detail) < context_text.index(
        "## Needs Input Summary"
    )
    assert "## Cancellation Details" in context_text
    assert "- slow_a: Cancellation requested after fail_fast." in context_text
    assert "- slow_b: Cancellation requested after fail_fast." in context_text
    assert "- later: Branch was not scheduled because fail_fast stopped new branch launches." in context_text


def test_parallel_branch_group_runtime_preserves_shared_state_values_and_overlapping_writes(tmp_path: Path) -> None:
    overlap_path = Path("shared/review.md")

    class SharedEffectsWorkflow(simple.Workflow):
        class State(BaseModel):
            branch_state: str | None = None
            publish_saw_state: str | None = None
            publish_saw_value: str | None = None

        reviews = simple.parallel(
            name="reviews",
            concurrency=1,
            outcome="all_done",
            branches={
                "state": simple.python_step(
                    lambda ctx: (
                        setattr(ctx, "state", ctx.state.model_copy(update={"branch_state": "set-in-branch"})),
                        Event("done"),
                    )[-1],
                    name="state_branch",
                ),
                "values": simple.python_step(
                    lambda ctx: (
                        setattr(ctx.values, "shared_value", "visible-after-settlement"),
                        Event("done"),
                    )[-1],
                    name="values_branch",
                ),
                "write_a": simple.python_step(
                    lambda ctx: (ctx.write(overlap_path, "first branch write\n"), Event("done"))[-1],
                    name="write_a_branch",
                ),
                "write_b": simple.python_step(
                    lambda ctx: (ctx.write(overlap_path, "second branch write\n"), Event("done"))[-1],
                    name="write_b_branch",
                ),
            },
            routes={"done": "publish"},
        )
        publish = simple.python_step(
            lambda ctx: (
                setattr(
                    ctx,
                    "state",
                    ctx.state.model_copy(
                        update={
                            "publish_saw_state": ctx.state.branch_state,
                            "publish_saw_value": ctx.values.shared_value,
                        }
                    ),
                ),
                Event("done"),
            )[-1],
            routes={"done": simple.FINISH},
        )

    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        SharedEffectsWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-shared-effects",
        run_id="run-shared-effects",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == simple.FINISH
    assert result.history == ("reviews", "publish")
    assert result.state.branch_state == "set-in-branch"
    assert result.state.publish_saw_state == "set-in-branch"
    assert result.state.publish_saw_value == "visible-after-settlement"
    assert (tmp_path / overlap_path).exists()
    assert (tmp_path / overlap_path).read_text(encoding="utf-8") == "second branch write\n"

    manifest = json.loads((_branch_group_dir(task_folder, SharedEffectsWorkflow, "reviews") / "results.json").read_text(encoding="utf-8"))
    assert [branch["status"] for branch in manifest["branches"]] == ["completed", "completed", "completed", "completed"]


def test_parallel_branch_group_fan_in_request_input_checkpoints_at_composite_boundary_and_resumes(
    tmp_path: Path,
) -> None:
    class FanInRequestInputWorkflow(simple.Workflow):
        class State(BaseModel):
            fan_in_answer: str | None = None
            published: bool = False

        reviews = simple.parallel(
            name="reviews",
            branches={
                "security": simple.python_step(lambda ctx: Event("done"), name="security_review"),
                "cost": simple.python_step(lambda ctx: Event("done"), name="cost_review"),
            },
            fan_in=simple.python_step(
                lambda ctx: RequestInput("Approve merged review summary?")
                if ctx.input_response is None
                else (
                    setattr(ctx, "state", ctx.state.model_copy(update={"fan_in_answer": str(ctx.input_response)})),
                    Event("approved"),
                )[-1],
                name="combine_reviews",
                routes={"approved": "publish"},
            ),
        )
        publish = simple.python_step(
            lambda ctx: (
                setattr(ctx, "state", ctx.state.model_copy(update={"published": True})),
                Event("done"),
            )[-1],
            routes={"done": simple.FINISH},
        )

    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        FanInRequestInputWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    paused = engine.run(
        task_id="task-fan-in-input",
        run_id="run-fan-in-input",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert paused.terminal == simple.AWAIT_INPUT
    assert paused.checkpoint is not None
    assert paused.checkpoint.stage == "reviews"
    assert paused.checkpoint.pending_input is not None
    assert paused.checkpoint.pending_input.question == "Approve merged review summary?"
    assert paused.checkpoint.pending_input.source_step == "combine_reviews"

    resumed = engine.resume(
        task_id="task-fan-in-input",
        run_id="run-fan-in-input",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        answer="approved",
    )

    assert resumed.terminal == simple.FINISH
    assert resumed.history == ("reviews", "publish")
    assert resumed.state.fan_in_answer == "approved"
    assert resumed.state.published is True
    assert resumed.last_event is not None
    assert resumed.last_event.tag == "done"
    assert checkpoint_store.load() is None


def test_parallel_branch_group_fan_in_route_on_taken_runs_once_at_composite_boundary(tmp_path: Path) -> None:
    on_taken_calls: list[str] = []

    def on_taken(ctx: object) -> None:
        on_taken_calls.append("approved")

    class FanInOnTakenWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        reviews = simple.parallel(
            name="reviews",
            branches={
                "security": simple.python_step(lambda ctx: Event("done"), name="security_review"),
                "cost": simple.python_step(lambda ctx: Event("done"), name="cost_review"),
            },
            fan_in=simple.python_step(
                lambda ctx: Event("approved"),
                name="combine_reviews",
                routes={"approved": simple.Route.to("publish", on_taken=on_taken)},
            ),
        )
        publish = simple.python_step(lambda ctx: Event("done"), routes={"done": simple.FINISH})

    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        FanInOnTakenWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-fan-in-on-taken",
        run_id="run-fan-in-on-taken",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == simple.FINISH
    assert result.history == ("reviews", "publish")
    assert on_taken_calls == ["approved"]


def _fail_path_write(
    monkeypatch: pytest.MonkeyPatch,
    *,
    target_path: Path,
) -> None:
    original_write_text = Path.write_text

    def patched_write_text(self: Path, data: str, *args: object, **kwargs: object) -> int:
        if self.resolve() == target_path.resolve():
            raise OSError("disk full")
        return original_write_text(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", patched_write_text)


def test_branch_group_results_manifest_write_failure_stops_before_fan_in_and_downstream_routing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fan_in_called = False
    published: list[str] = []

    def fan_in_turn(request: object) -> Outcome:
        nonlocal fan_in_called
        fan_in_called = True
        return Outcome(raw_output="approved", tag="approved")

    class FanInWriteFailureWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        reviews = simple.parallel(
            name="reviews",
            branches={
                "security": simple.step("Review security.", name="security_review", session=simple.Session.fresh()),
                "cost": simple.step("Review cost.", name="cost_review", session=simple.Session.fresh()),
            },
            fan_in=simple.step(
                "Summarize reviews.",
                name="combine_reviews",
                after=lambda ctx: published.append("fan_in") or None,
                routes={"approved": "publish"},
            ),
        )
        publish = simple.python_step(lambda ctx: (published.append("publish"), Event("done"))[-1])

    task_folder, run_folder = _workspace(tmp_path)
    results_path = _branch_group_dir(task_folder, FanInWriteFailureWorkflow, "reviews") / "results.json"
    context_path = _branch_group_dir(task_folder, FanInWriteFailureWorkflow, "reviews") / "context.md"
    _fail_path_write(monkeypatch, target_path=results_path)

    with pytest.raises(OSError, match="disk full"):
        Engine(
            FanInWriteFailureWorkflow,
            provider=ScriptedLLMProvider(
                llm_turns=[
                    Outcome(raw_output="security ok", tag="done"),
                    Outcome(raw_output="cost ok", tag="done"),
                    fan_in_turn,
                ]
            ),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-fan-in-write-failure",
            run_id="run-fan-in-write-failure",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    assert fan_in_called is False
    assert published == []
    assert not results_path.exists()
    assert not context_path.exists()


def test_branch_group_context_write_failure_stops_before_fan_in_and_downstream_routing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fan_in_called = False
    published: list[str] = []

    def fan_in_turn(request: object) -> Outcome:
        nonlocal fan_in_called
        fan_in_called = True
        return Outcome(raw_output="approved", tag="approved")

    class FanInWriteFailureWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        reviews = simple.parallel(
            name="reviews",
            branches={
                "security": simple.step("Review security.", name="security_review", session=simple.Session.fresh()),
                "cost": simple.step("Review cost.", name="cost_review", session=simple.Session.fresh()),
            },
            fan_in=simple.step(
                "Summarize reviews.",
                name="combine_reviews",
                after=lambda ctx: published.append("fan_in") or None,
                routes={"approved": "publish"},
            ),
        )
        publish = simple.python_step(lambda ctx: (published.append("publish"), Event("done"))[-1])

    task_folder, run_folder = _workspace(tmp_path)
    results_path = _branch_group_dir(task_folder, FanInWriteFailureWorkflow, "reviews") / "results.json"
    context_path = _branch_group_dir(task_folder, FanInWriteFailureWorkflow, "reviews") / "context.md"
    _fail_path_write(monkeypatch, target_path=context_path)

    with pytest.raises(OSError, match="disk full"):
        Engine(
            FanInWriteFailureWorkflow,
            provider=ScriptedLLMProvider(
                llm_turns=[
                    Outcome(raw_output="security ok", tag="done"),
                    Outcome(raw_output="cost ok", tag="done"),
                    fan_in_turn,
                ]
            ),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-fan-in-context-write-failure",
            run_id="run-fan-in-context-write-failure",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    assert fan_in_called is False
    assert published == []
    assert results_path.exists()
    assert not context_path.exists()


def test_branch_group_evidence_write_failure_stops_before_mechanical_outcome_routing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    published: list[str] = []

    class OutcomeWriteFailureWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        reviews = simple.parallel(
            name="reviews",
            outcome="all_done",
            branches={
                "security": simple.python_step(lambda ctx: Event("done"), name="security_review"),
                "cost": simple.python_step(lambda ctx: Event("done"), name="cost_review"),
            },
            routes={"done": "publish"},
        )
        publish = simple.python_step(lambda ctx: (published.append("publish"), Event("done"))[-1])

    def fail_write(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(branch_group_runtime, "write_branch_group_evidence", fail_write)
    task_folder, run_folder = _workspace(tmp_path)

    with pytest.raises(OSError, match="disk full"):
        Engine(
            OutcomeWriteFailureWorkflow,
            provider=ScriptedLLMProvider(),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-outcome-write-failure",
            run_id="run-outcome-write-failure",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    assert published == []
    assert not (_branch_group_dir(task_folder, OutcomeWriteFailureWorkflow, "reviews") / "results.json").exists()
    assert not (_branch_group_dir(task_folder, OutcomeWriteFailureWorkflow, "reviews") / "context.md").exists()


def test_branch_group_mechanical_outcomes_support_all_settled_and_custom_aggregators(tmp_path: Path) -> None:
    class OutcomeWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        settled = simple.parallel(
            name="settled",
            outcome="all_settled",
            branches={
                "approved": simple.step(
                    "Approved.",
                    name="approved_branch",
                    session=simple.Session.fresh(),
                    routes={"approved": simple.FINISH},
                ),
                "done": simple.step("Done.", name="done_branch", session=simple.Session.fresh()),
            },
            routes={"done": simple.FINISH, "partial": simple.FINISH},
        )

    provider = ScriptedLLMProvider(
        llm_turns=[
            _prompt_routed_outcome,
            _prompt_routed_outcome,
        ]
    )
    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        OutcomeWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-all-settled",
        run_id="run-all-settled",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == simple.FINISH
    assert result.last_event is not None
    assert result.last_event.tag == "partial"

    class SuccessRoutesWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        settled = simple.parallel(
            name="settled_success_routes",
            outcome="all_settled",
            success_routes=("approved", "done"),
            branches={
                "approved": simple.step(
                    "Approved.",
                    name="approved_success_branch",
                    session=simple.Session.fresh(),
                    routes={"approved": simple.FINISH},
                ),
                "done": simple.step("Done.", name="done_success_branch", session=simple.Session.fresh()),
            },
            routes={"done": simple.FINISH, "partial": simple.FINISH},
        )

    success_routes_result = Engine(
        SuccessRoutesWorkflow,
        provider=ScriptedLLMProvider(
            llm_turns=[
                _prompt_routed_outcome,
                _prompt_routed_outcome,
            ]
        ),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-all-settled-success-routes",
        run_id="run-all-settled-success-routes",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert success_routes_result.terminal == simple.FINISH
    assert success_routes_result.last_event is not None
    assert success_routes_result.last_event.tag == "done"

    class CustomOutcomeWorkflow(simple.Workflow):
        class State(BaseModel):
            pass

        decide = simple.parallel(
            outcome=lambda manifest, ctx: Event("done" if manifest["branches"][0]["status"] == "failed" else "partial"),
            branches={
                "failer": simple.python_step(lambda ctx: (_ for _ in ()).throw(RuntimeError("boom")), name="failer"),
            },
            routes={"done": simple.FINISH, "partial": simple.SELF},
        )

    custom_result = Engine(
        CustomOutcomeWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-custom-outcome",
        run_id="run-custom-outcome",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert custom_result.terminal == simple.FINISH
    assert custom_result.last_event is not None
    assert custom_result.last_event.tag == "done"
