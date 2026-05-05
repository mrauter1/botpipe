from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from autoloop.core.branch_groups import runtime as branch_group_runtime
from autoloop.core.engine import Engine
from autoloop.core.primitives import Event, Goto, Outcome, RequestInput
from autoloop.core.providers.fake import ScriptedLLMProvider
from autoloop.core.stores import InMemoryCheckpointStore, InMemorySessionStore
import autoloop.simple as simple


def _workspace(tmp_path: Path) -> tuple[Path, Path]:
    task_folder = tmp_path / "task"
    run_folder = tmp_path / "run"
    task_folder.mkdir()
    run_folder.mkdir()
    return task_folder, run_folder


def _prompt_routed_outcome(request: object) -> Outcome:
    prompt_text = request.prompt.text
    if prompt_text == "Approved.":
        return Outcome(raw_output="approved", tag="approved")
    return Outcome(raw_output="done", tag="done")


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
    results_path = tmp_path / "_branch_groups" / "reviews" / "results.json"
    context_path = tmp_path / "_branch_groups" / "reviews" / "context.md"
    manifest = json.loads(results_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == "autoloop.branch_results/v1"
    assert [branch["name"] for branch in manifest["branches"]] == ["security", "cost"]
    assert manifest["branches"][0]["status"] == "needs_input"
    assert manifest["branches"][0]["question"] == "Approve security review?"
    assert manifest["branches"][1]["status"] == "completed"
    assert "Approve security review?" in context_path.read_text(encoding="utf-8")


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
    assert str(seen["results_path"]).endswith("_branch_groups/reviews/results.json")
    assert str(seen["context_path"]).endswith("_branch_groups/reviews/context.md")
    assert "Branch Group: reviews" in str(seen["context_text"])
    assert any(str(path).endswith("_branch_groups/reviews/results.json") for path in seen["readable_paths"])
    assert any(str(path).endswith("_branch_groups/reviews/context.md") for path in seen["readable_paths"])


def test_fan_out_renders_branch_input_roots_artifacts_and_keeps_branch_sessions_local(tmp_path: Path) -> None:
    prompts: list[str] = []
    sessions: list[str | None] = []

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
                Outcome(raw_output="ok", tag="done"),
            )[-1],
            lambda request: (
                prompts.append(request.prompt.text),
                sessions.append(None if request.session is None else request.session.session_id),
                Outcome(raw_output="ok", tag="done"),
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
    assert len(set(session_id for session_id in sessions if session_id is not None)) == 2
    parent_snapshot = session_store.snapshot()
    assert all(binding.session_id not in sessions for binding in parent_snapshot.bindings)
    security_report = task_folder / "wf_fan_out_workflow" / "assess_one" / "reports" / "security.md"
    performance_report = task_folder / "wf_fan_out_workflow" / "assess_one" / "reports" / "performance.md"
    assert security_report.read_text(encoding="utf-8").strip() == "security"
    assert performance_report.read_text(encoding="utf-8").strip() == "performance"
    manifest = json.loads((tmp_path / "_branch_groups" / "assess" / "results.json").read_text(encoding="utf-8"))
    assert manifest["branches"][0]["artifacts"][0]["path"].endswith("wf_fan_out_workflow/assess_one/reports/security.md")
    assert manifest["branches"][1]["artifacts"][0]["path"].endswith("wf_fan_out_workflow/assess_one/reports/performance.md")


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
    manifest = json.loads((tmp_path / "_branch_groups" / "reviews" / "results.json").read_text(encoding="utf-8"))
    reroute_branch = next(branch for branch in manifest["branches"] if branch["name"] == "reroute")
    assert reroute_branch["status"] == "completed"
    assert reroute_branch["runtime_control"] == "goto"
    assert reroute_branch["destination"] == "repair"


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

    manifest = json.loads((tmp_path / "_branch_groups" / "reviews" / "results.json").read_text(encoding="utf-8"))
    assert manifest["settle"] == "fail_fast"
    assert [branch["name"] for branch in manifest["branches"]] == ["explode", "later_a", "later_b"]
    assert [branch["status"] for branch in manifest["branches"]] == ["failed", "skipped", "skipped"]
    assert manifest["branches"][1]["reason"] == "Branch was not scheduled because fail_fast stopped new branch launches."
    assert manifest["branches"][2]["reason"] == "Branch was not scheduled because fail_fast stopped new branch launches."


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
    assert result.state.branch_state == "set-in-branch"
    assert result.state.publish_saw_state == "set-in-branch"
    assert result.state.publish_saw_value == "visible-after-settlement"
    assert (tmp_path / overlap_path).exists()
    assert (tmp_path / overlap_path).read_text(encoding="utf-8") == "second branch write\n"

    manifest = json.loads((tmp_path / "_branch_groups" / "reviews" / "results.json").read_text(encoding="utf-8"))
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
    assert resumed.state.fan_in_answer == "approved"
    assert resumed.state.published is True
    assert resumed.last_event is not None
    assert resumed.last_event.tag == "done"
    assert checkpoint_store.load() is None


def test_branch_group_evidence_write_failure_stops_before_fan_in_and_downstream_routing(
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

    def fail_write(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(branch_group_runtime, "write_branch_group_evidence", fail_write)
    task_folder, run_folder = _workspace(tmp_path)

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
    assert not (tmp_path / "_branch_groups" / "reviews" / "results.json").exists()
    assert not (tmp_path / "_branch_groups" / "reviews" / "context.md").exists()


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
    assert not (tmp_path / "_branch_groups" / "reviews" / "results.json").exists()
    assert not (tmp_path / "_branch_groups" / "reviews" / "context.md").exists()


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
