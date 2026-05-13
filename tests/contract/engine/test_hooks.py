from __future__ import annotations

from tests.contract.engine._shared import _chain_hooks, _workspace
from tests.contract.engine._shared import *

def test_llm_step_hooks_run_in_order_and_on_taken_follows_after_hooks(tmp_path: Path):
    seen_provider_state: list[list[str]] = []

    def before_ask(ctx):
        ctx.state = ctx.state.model_copy(update={"seen": [*ctx.state.seen, "before"]})

    def after_ask(ctx):
        assert ctx.state.seen == ["before", "handler"]
        ctx.state = ctx.state.model_copy(update={"seen": [*ctx.state.seen, "after"]})

    def on_taken(ctx):
        ctx.state.seen.append("on_taken")

    def _hookedllmworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'seen': [*ctx.state.seen, 'handler']})
        return None

    class HookedLLMWorkflow(Workflow):
        class State(BaseModel):
            seen: list[str] = Field(default_factory=list)

        ask = PromptStep(name="ask", producer="ask.md", before=before_ask, after=after_ask)
        entry = ask
        transitions = {ask: {"done": Route.to(FINISH, on_taken=on_taken)}}

    HookedLLMWorkflow.ask.after = _chain_hooks(_hookedllmworkflow_on_ask, HookedLLMWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        llm_turns=[
            lambda request: (
                seen_provider_state.append(list(request.context.state.seen)),
                Outcome(raw_output="ok", tag="done"),
            )[1]
        ]
    )
    result = Engine(
        HookedLLMWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.last_event is not None
    assert result.last_event.tag == "done"
    assert result.state.seen == ["before", "handler", "after", "on_taken"]
    assert seen_provider_state == [["before"]]
def test_system_step_hook_events_are_observable(tmp_path: Path):
    hook_events: list[tuple[str, str, str | None]] = []

    def before_publish(ctx):
        ctx.state = ctx.state.model_copy(update={"seen": [*ctx.state.seen, "before"]})

    def after_publish(ctx):
        assert ctx.outcome.tag == "done"
        ctx.state = ctx.state.model_copy(update={"seen": [*ctx.state.seen, "after"]})

    def on_taken(ctx):
        ctx.state.seen.append("on_taken")

    def _hookedsystemworkflow_on_publish(ctx):
        ctx.state = ctx.state.model_copy(update={'seen': [*ctx.state.seen, 'handler']})
        return Event('done')

    class HookedSystemWorkflow(Workflow):
        class State(BaseModel):
            seen: list[str] = Field(default_factory=list)

        publish = PythonStep(name="publish", before=before_publish, after=after_publish, handler=_hookedsystemworkflow_on_publish)
        entry = publish
        transitions = {publish: {"done": Route.to(FINISH, on_taken=on_taken)}}


    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        HookedSystemWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        hook_event_sink=lambda event_type, payload: hook_events.append(
            (event_type, str(payload.get("phase")), payload.get("route"))
        ),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.seen == ["before", "handler", "after", "on_taken"]
    assert hook_events == [
        ("hook_started", "before", None),
        ("hook_finished", "before", None),
        ("hook_started", "after", "done"),
        ("hook_finished", "after", "done"),
        ("hook_started", "on_taken", "done"),
        ("hook_finished", "on_taken", "done"),
    ]
def test_before_hook_route_short_circuits_without_provider_and_preserves_candidate_route_none(tmp_path: Path):
    def before_ask(ctx):
        ctx.state = ctx.state.model_copy(update={"seen": [*ctx.state.seen, "before"]})
        return Event("done")

    class BeforeHookRouteWorkflow(Workflow):
        class State(BaseModel):
            seen: list[str] = Field(default_factory=list)

        ask = PromptStep(name="ask", producer="ask.md", before=before_ask)
        entry = ask
        transitions = {ask: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(llm_turns=[Outcome(raw_output="unexpected", tag="done")])
    result = Engine(
        BeforeHookRouteWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.seen == ["before"]
    assert provider.calls == []
    assert result.last_transition is not None
    assert result.last_transition.candidate_route is None
    assert result.last_transition.final_route == "done"
    assert result.last_transition.provider_attributable is False
    assert result.last_transition.provider_attempted is False
    assert result.last_transition.source_hook == "before_ask"
    assert result.last_transition.source_phase == "before"
def test_before_verifier_route_short_circuits_verifier_and_preserves_candidate_route_none(tmp_path: Path):
    def before_verifier(ctx):
        return Event("approved")

    class BeforeVerifierRouteWorkflow(Workflow):
        class State(BaseModel):
            pass

        pair = ProduceVerifyStep(
            name="pair",
            producer="pair/producer.md",
            verifier="pair/verifier.md",
            before_verifier=before_verifier,
        )
        entry = pair
        transitions = {pair: {"approved": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        producer_turns=["draft copy"],
        verifier_turns=[Outcome(raw_output="unexpected", tag="approved")],
    )
    result = Engine(
        BeforeVerifierRouteWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert [call.kind for call in provider.calls] == ["producer"]
    assert result.last_transition is not None
    assert result.last_transition.candidate_route is None
    assert result.last_transition.final_route == "approved"
    assert result.last_transition.provider_attributable is False
    assert result.last_transition.provider_attempted is True
    assert result.last_transition.producer_attempted is True
    assert result.last_transition.verifier_attempted is False
    assert result.last_transition.source_hook == "before_verifier"
    assert result.last_transition.source_phase == "before_verifier"
def test_pair_hooks_before_verifier_preserve_state_mutations_on_success(tmp_path: Path):
    def after_producer(ctx):
        ctx.state = ctx.state.model_copy(update={"seen": [*ctx.state.seen, "after_producer"]})
        return None

    def before_verifier(ctx):
        ctx.state = ctx.state.model_copy(update={"seen": [*ctx.state.seen, "before_verifier"]})
        return None

    def _pairhookstateworkflow_on_pair(ctx):
        ctx.state = ctx.state.model_copy(update={"approved": bool(ctx.outcome.payload["approved"])})
        return None

    class PairHookStateWorkflow(Workflow):
        class State(BaseModel):
            seen: list[str] = Field(default_factory=list)
            approved: bool = False

        pair = ProduceVerifyStep(
            name="pair",
            producer="pair/producer.md",
            verifier="pair/verifier.md",
            after_producer=after_producer,
            before_verifier=before_verifier,
        )
        entry = pair
        transitions = {pair: {"approved": FINISH}}

    PairHookStateWorkflow.pair.after_verifier = _chain_hooks(
        _pairhookstateworkflow_on_pair,
        PairHookStateWorkflow.pair.after_verifier,
    )

    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        producer_turns=["draft copy"],
        verifier_turns=[Outcome(raw_output="approved", tag="approved", payload={"approved": True})],
    )
    result = Engine(
        PairHookStateWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert [call.kind for call in provider.calls] == ["producer", "verifier"]
    assert result.state.seen == ["after_producer", "before_verifier"]
    assert result.state.approved is True
    assert result.last_transition is not None
    assert result.last_transition.provider_attempted is True
    assert result.last_transition.producer_attempted is True
    assert result.last_transition.verifier_attempted is True
def test_before_producer_route_short_circuits_without_provider_and_preserves_candidate_route_none(tmp_path: Path):
    def before_producer(ctx):
        return Event("approved")

    def _beforeproducerrouteworkflow_on_pair(ctx):
        raise AssertionError('pair outcome handler should not run when before_producer short-circuits')

    class BeforeProducerRouteWorkflow(Workflow):
        class State(BaseModel):
            pass

        pair = ProduceVerifyStep(
            name="pair",
            producer="pair/producer.md",
            verifier="pair/verifier.md",
            before_producer=before_producer,
        )
        entry = pair
        transitions = {pair: {"approved": FINISH}}

    BeforeProducerRouteWorkflow.pair.after_verifier = _chain_hooks(_beforeproducerrouteworkflow_on_pair, BeforeProducerRouteWorkflow.pair.after_verifier)


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(
        producer_turns=["unexpected draft"],
        verifier_turns=[Outcome(raw_output="unexpected", tag="approved")],
    )
    result = Engine(
        BeforeProducerRouteWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert provider.calls == []
    assert result.last_transition is not None
    assert result.last_transition.candidate_route is None
    assert result.last_transition.final_route == "approved"
    assert result.last_transition.provider_attributable is False
    assert result.last_transition.provider_attempted is False
    assert result.last_transition.source_hook == "before_producer"
    assert result.last_transition.source_phase == "before_producer"
def test_engine_emits_scoped_hook_failure_events_with_step_execution_identity(tmp_path: Path):
    def before_review(ctx):
        raise RuntimeError("boom")

    def _scopedhookfailureworkflow_on_review(ctx):
        return None

    class ScopedHookFailureWorkflow(Workflow):
        class State(BaseModel):
            pass

        articles = Worklist.from_param("articles")
        review = PromptStep(name="review", producer="review.md", scope=articles, before=before_review)
        entry = review
        transitions = {review: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    hook_events: list[tuple[str, dict[str, object]]] = []
    engine = Engine(
        ScopedHookFailureWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        hook_event_sink=lambda event_type, payload: hook_events.append((event_type, dict(payload))),
    )

    with pytest.raises(WorkflowExecutionError, match="boom"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
            workflow_params={"articles": [{"id": "alpha", "title": "Alpha"}]},
        )

    hook_failed = [payload for event_type, payload in hook_events if event_type == "hook_failed"]
    assert hook_failed == [
        {
            "step_name": "review",
            "visit": 1,
            "step_execution_id": "review:articles:alpha:1",
            "scope": "articles",
            "item_id": "alpha",
            "hook_name": "before_review",
            "phase": "before",
            "error": "boom",
        }
    ]
def test_after_hook_returning_route_string_reroutes_execution(tmp_path: Path):
    def after_ask(ctx):
        return "rerouted"

    def _hookretryworkflow_on_ask(ctx):
        return None

    class HookRetryWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            after=after_ask,
            retry_policy=ProviderRetryPolicy(max_attempts=2),
        )
        entry = ask
        transitions = {ask: {"done": FINISH, "rerouted": FAIL}}


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(llm_turns=[Outcome(raw_output="first", tag="done")])

    result = Engine(
        HookRetryWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FAIL
    assert result.last_event is not None
    assert result.last_event.tag == "rerouted"
    assert [call.attempt for call in provider.calls] == [1]
def test_after_hook_dynamic_invalid_route_fails_as_runtime_error(tmp_path: Path):
    def after_ask(ctx):
        return ctx.state.redirect_to

    def _hookinvalidrouteworkflow_on_ask(ctx):
        return None

    class HookInvalidRouteWorkflow(Workflow):
        class State(BaseModel):
            redirect_to: str = "missing_route"

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            after=after_ask,
            retry_policy=ProviderRetryPolicy(max_attempts=2),
        )
        entry = ask
        transitions = {ask: {"done": FINISH, "failed": FAIL}}


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")])

    with pytest.raises(WorkflowExecutionError, match="produced illegal route 'missing_route'"):
        Engine(
            HookInvalidRouteWorkflow,
            provider=provider,
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    assert len(provider.calls) == 1
def test_provider_after_hook_event_override_reroutes_execution(tmp_path: Path):
    def after_ask(ctx):
        return Event("failed", reason="nope")

    def _hookhardfailworkflow_on_ask(ctx):
        return None

    class HookHardFailWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            after=after_ask,
            retry_policy=ProviderRetryPolicy(max_attempts=2),
        )
        entry = ask
        transitions = {ask: {"done": FINISH, "failed": FAIL}}


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")])

    result = Engine(
        HookHardFailWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FAIL
    assert result.last_event is not None
    assert result.last_event.tag == "failed"
    assert result.last_event.reason == "nope"
    assert len(provider.calls) == 1
def test_workflow_step_after_hook_can_mutate_state_after_child_completion(tmp_path: Path):
    task_folder, run_folder = _workspace(tmp_path)
    child_result_path = task_folder / "wf_workflow_hook_override_workflow" / "launch" / "child_result.json"
    child_runs: list[str] = []

    class ChildWorkflow(SimpleWorkflow):
        note = step("Write the child note.")

    def before_launch(ctx):
        ctx.state = ctx.state.model_copy(update={"seen": [*ctx.state.seen, "before"]})

    def after_launch(ctx):
        assert ctx.outcome.tag == "done"
        ctx.state = ctx.state.model_copy(update={"seen": [*ctx.state.seen, "after"]})

    class WorkflowHookOverrideWorkflow(SimpleWorkflow):
        class State(BaseModel):
            seen: list[str] = Field(default_factory=list)

        launch = workflow_step(
            ChildWorkflow,
            message="Run child workflow",
            writes=[Json("child_result")],
            before=before_launch,
            after=after_launch,
        )

    def invoke_child(workflow, *, message, parameters=None, input=None):
        child_runs.append(message)
        child_run_root = task_folder / "child-runs" / f"child-{len(child_runs)}"
        child_run_root.mkdir(parents=True, exist_ok=True)
        return ChildWorkflowResult(
            workflow_name="child_workflow",
            run_id=f"child-{len(child_runs)}",
            terminal=FINISH,
            status="success",
            last_event=Event("done"),
            output_metadata={},
            output_artifacts={},
            task_folder=task_folder,
            workflow_folder=child_run_root,
            run_folder=child_run_root / "run",
            package_folder=child_run_root / "package",
            request_file=child_run_root / "request.md",
            run_meta_file=child_run_root / "run.json",
            events_file=child_run_root / "events.jsonl",
            checkpoint_file=child_run_root / "checkpoint.json",
            sessions_dir=child_run_root / "sessions",
            trace_file=child_run_root / "trace.jsonl",
            raw_dir=child_run_root / "raw",
            parent_file=child_run_root / "parent.json",
        )

    result = Engine(
        WorkflowHookOverrideWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        workflow_invoker=invoke_child,
    )

    assert result.terminal == FINISH
    assert result.state.seen == ["before", "after"]
    assert child_runs == ["Run child workflow"]
    assert child_result_path.exists()
def test_route_hooks_can_reroute_across_a_chain_and_emit_redirect_events(tmp_path: Path):
    hook_events: list[tuple[str, str, str, str]] = []

    def after_ask(ctx):
        route = ctx.route.tag
        ctx.state.seen.append(f"after:{route}")
        if route == "draft":
            return "review"
        return None

    def on_review_taken(ctx):
        ctx.state.seen.append("on_taken:review")
        return Event("publish", reason="approved")

    def on_publish_taken(ctx):
        ctx.state.seen.append("on_taken:publish")

    def _routeredirectworkflow_on_ask(ctx):
        return None

    class RouteRedirectWorkflow(Workflow):
        class State(BaseModel):
            seen: list[str] = Field(default_factory=list)

        ask = PromptStep(name="ask", producer="ask.md", after=after_ask, retry_policy=ProviderRetryPolicy(max_attempts=1))
        entry = ask
        transitions = {
            ask: {
                "draft": Route.to(FINISH),
                "review": Route.to(FINISH, on_taken=on_review_taken),
                "publish": Route.to(FINISH, on_taken=on_publish_taken),
            }
        }


    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        RouteRedirectWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="draft")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        hook_event_sink=lambda event_type, payload: hook_events.append(
            (
                event_type,
                str(payload.get("phase")),
                str(payload.get("from_route")),
                str(payload.get("to_route")),
            )
        )
        if event_type == "hook_route_redirected"
        else None,
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.last_event is not None
    assert result.last_event.tag == "publish"
    assert result.state.seen == [
        "after:draft",
        "on_taken:review",
        "on_taken:publish",
    ]
    assert hook_events == [
        ("hook_route_redirected", "after", "draft", "review"),
        ("hook_route_redirected", "on_taken", "review", "publish"),
    ]
def test_engine_emits_scoped_after_hook_redirect_events_with_step_execution_identity(tmp_path: Path):
    def after_review(ctx):
        if ctx.route.tag == "draft":
            return "review"
        return None

    def on_review_taken(ctx):
        return "publish"

    def _scopedrouteredirectworkflow_on_review(ctx):
        return None

    class ScopedRouteRedirectWorkflow(Workflow):
        class State(BaseModel):
            pass

        articles = Worklist.from_param("articles")
        review = PromptStep(
            name="review",
            producer="review.md",
            scope=articles,
            after=after_review,
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = review
        transitions = {
            review: {
                "draft": Route.to(FINISH),
                "review": Route.to(FINISH, on_taken=on_review_taken),
                "publish": Route.to(FINISH),
            }
        }


    task_folder, run_folder = _workspace(tmp_path)
    hook_events: list[dict[str, object]] = []
    result = Engine(
        ScopedRouteRedirectWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="draft")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        hook_event_sink=lambda event_type, payload: hook_events.append(dict(payload))
        if event_type == "hook_route_redirected"
        else None,
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        workflow_params={"articles": [{"id": "alpha", "title": "Alpha"}]},
    )

    assert result.terminal == FINISH
    assert result.last_event is not None
    assert result.last_event.tag == "publish"
    assert hook_events == [
        {
            "step_name": "review",
            "visit": 1,
            "step_execution_id": "review:articles:alpha:1",
            "scope": "articles",
            "item_id": "alpha",
            "hook": "after_review",
            "hook_name": "after_review",
            "phase": "after",
            "from_route": "draft",
            "to_route": "review",
        },
        {
            "step_name": "review",
            "visit": 1,
            "step_execution_id": "review:articles:alpha:1",
            "scope": "articles",
            "item_id": "alpha",
            "hook": "on_review_taken",
            "hook_name": "on_review_taken",
            "phase": "on_taken",
            "from_route": "review",
            "to_route": "publish",
        },
    ]
def test_route_redirect_cycle_fails_after_max_hook_redirects(tmp_path: Path):
    hook_events: list[tuple[str, str]] = []

    def on_draft_taken(ctx):
        return "review"

    def on_review_taken(ctx):
        return "draft"

    def _redirectcycleworkflow_on_ask(ctx):
        return None

    class RedirectCycleWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md", retry_policy=ProviderRetryPolicy(max_attempts=1))
        entry = ask
        transitions = {
            ask: {
                "draft": Route.to(FINISH, on_taken=on_draft_taken),
                "review": Route.to(FINISH, on_taken=on_review_taken),
            }
        }


    task_folder, run_folder = _workspace(tmp_path)
    with pytest.raises(
        WorkflowExecutionError,
        match=r"Hook redirect limit exceeded for step 'ask'.*draft -> review -> draft",
    ):
        Engine(
            RedirectCycleWorkflow,
            provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="draft")]),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
            hook_event_sink=lambda event_type, payload: hook_events.append((payload["from_route"], payload["to_route"]))
            if event_type == "hook_route_redirected"
            else None,
        ).run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    assert len(hook_events) == Engine.max_hook_redirects + 1
    assert hook_events[:3] == [("draft", "review"), ("review", "draft"), ("draft", "review")]
def test_route_hook_failure_preserves_chained_state_in_checkpoint(tmp_path: Path):
    def after_ask(ctx):
        ctx.state.bucket = "rerouted"
        return "review"

    def on_taken(ctx):
        raise RuntimeError("route hook exploded")

    def _routehookrollbackworkflow_on_ask(ctx):
        return None

    class RouteHookRollbackWorkflow(Workflow):
        class State(BaseModel):
            bucket: str = "draft"

        ask = PromptStep(name="ask", producer="ask.md", after=after_ask, retry_policy=ProviderRetryPolicy(max_attempts=1))
        entry = ask
        transitions = {
            ask: {
                "draft": Route.to(FINISH),
                "review": Route.to(FINISH, on_taken=on_taken),
            }
        }


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    with pytest.raises(WorkflowExecutionError, match="route hook exploded"):
        Engine(
            RouteHookRollbackWorkflow,
            provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="draft")]),
            session_store=InMemorySessionStore(),
            checkpoint_store=checkpoint_store,
        ).run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.state is not None
    assert checkpoint.state.bucket == "rerouted"
def test_workflow_step_honors_hooks_and_can_participate_in_verifier_rework_loops(tmp_path: Path):
    class ChildWorkflow(SimpleWorkflow):
        note = step("Write the child note.")

    def before_launch(ctx):
        ctx.state = ctx.state.model_copy(update={"before_count": ctx.state.before_count + 1})

    def after_launch(ctx):
        ctx.state = ctx.state.model_copy(update={"after_count": ctx.state.after_count + 1})

    class ParentWorkflow(SimpleWorkflow):
        class State(BaseModel):
            before_count: int = 0
            after_count: int = 0

        launch = workflow_step(
            ChildWorkflow,
            message="Run child workflow",
            writes=[Json("child_result")],
            before=before_launch,
            after=after_launch,
        )
        review = produce_verify_step(
            producer_prompt="Review the child result.",
            verifier_prompt="Accept if the child result is usable.",
            reads=["child_result"],
            routes={"needs_rework": "launch", "accepted": FINISH},
        )

    task_folder, run_folder = _workspace(tmp_path)
    child_runs: list[str] = []

    def invoke_child(workflow, *, message, parameters=None, input=None):
        child_runs.append(message)
        child_run_root = task_folder / "child-runs" / f"child-{len(child_runs)}"
        child_run_root.mkdir(parents=True, exist_ok=True)
        return ChildWorkflowResult(
            workflow_name="child_workflow",
            run_id=f"child-{len(child_runs)}",
            terminal=FINISH,
            status="success",
            last_event=Event("done"),
            output_metadata={},
            output_artifacts={},
            task_folder=task_folder,
            workflow_folder=child_run_root,
            run_folder=child_run_root / "run",
            package_folder=child_run_root / "package",
            request_file=child_run_root / "request.md",
            run_meta_file=child_run_root / "run.json",
            events_file=child_run_root / "events.jsonl",
            checkpoint_file=child_run_root / "checkpoint.json",
            sessions_dir=child_run_root / "sessions",
            trace_file=child_run_root / "trace.jsonl",
            raw_dir=child_run_root / "raw",
            parent_file=child_run_root / "parent.json",
        )

    provider = ScriptedLLMProvider(
        producer_turns=["draft review", "draft review again"],
        verifier_turns=[
            Outcome(raw_output="redo", tag="needs_rework"),
            Outcome(raw_output="accept", tag="accepted"),
        ],
    )
    result = Engine(
        ParentWorkflow,
        provider=provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        workflow_invoker=invoke_child,
    )

    child_result_path = task_folder / "wf_parent_workflow" / "launch" / "child_result.json"

    compiled = compile_workflow(ParentWorkflow)

    assert result.terminal == FINISH
    assert result.history == ("launch", "review", "launch", "review")
    assert result.state.before_count == 2
    assert result.state.after_count == 2
    assert child_runs == ["Run child workflow", "Run child workflow"]
    assert child_result_path.exists()
    assert compiled.steps["launch"].kind == "workflow"
    assert compiled.steps["launch"].workflow is ChildWorkflow
    assert compiled.steps["launch"].python_handler is None
    assert "on_launch" not in ParentWorkflow.__dict__
def test_after_hook_re_resolves_artifact_paths_before_on_taken(tmp_path: Path):
    seen_paths: list[Path] = []

    def after_ask(ctx):
        ctx.state.bucket = "published"

    def on_taken(ctx):
        seen_paths.append(ctx.artifacts.report.path)
        ctx.artifacts.report.write_text("published report\n")

    def _routehookartifactworkflow_on_ask(ctx):
        return None

    class RouteHookArtifactWorkflow(Workflow):
        class State(BaseModel):
            bucket: str = "draft"

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            writes={"report": Artifact.md("{{ workflow.folder }}/{{ state.bucket }}/report.md")},
            after=after_ask,
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {
            ask: {
                "publish": Route.to(FINISH, required_writes=("report",), on_taken=on_taken),
            }
        }


    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        RouteHookArtifactWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="publish")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.last_event is not None
    assert result.last_event.tag == "publish"
    assert result.state.bucket == "published"
    workflow_root = task_folder / "wf_route_hook_artifact_workflow"
    assert seen_paths == [workflow_root / "published" / "report.md"]
    assert not (workflow_root / "draft" / "report.md").exists()
    assert (workflow_root / "published" / "report.md").read_text(encoding="utf-8") == "published report\n"
def test_after_hook_state_mutation_re_resolves_artifact_paths_before_final_output_validation(tmp_path: Path):
    def after_ask(ctx):
        ctx.state = ctx.state.model_copy(update={"bucket": "published"})

    def _reresolvedartifactworkflow_on_ask(ctx):
        ctx.artifacts.report.write_text('draft report\n')
        return None

    class ReResolvedArtifactWorkflow(Workflow):
        class State(BaseModel):
            bucket: str = "draft"

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            writes={"report": Artifact.md("{{ workflow.folder }}/{{ state.bucket }}/report.md")},
            after=after_ask,
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {
            ask: {
                "publish": Route.to(FINISH, required_writes=("report",)),
            }
        }

    ReResolvedArtifactWorkflow.ask.after = _chain_hooks(_reresolvedartifactworkflow_on_ask, ReResolvedArtifactWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    with pytest.raises(ProviderExecutionError, match=r"artifact validation failed.*published/report.md"):
        Engine(
            ReResolvedArtifactWorkflow,
            provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="publish")]),
            session_store=InMemorySessionStore(),
            checkpoint_store=checkpoint_store,
        ).run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.failure_context is not None
    assert checkpoint.failure_context["path"].endswith("/published/report.md")
def test_after_hook_effects_complete_and_advance_persist_status_and_exhaust(tmp_path: Path):
    runtime_events: list[tuple[str, dict[str, object]]] = []

    def after_assess(ctx):
        return Effects.complete_and_advance(exhausted="done")

    class EffectsWorkflow(Workflow):
        board = Artifact.json("{{ task.folder }}/gates.json", required=True)
        gates = Worklist.from_artifact(
            name="gate",
            artifact=board,
            collection="gates",
            item_id="gate_id",
            title="title",
            status="status",
        )
        assess = PromptStep(name="assess", producer="assess.md", scope=gates, after=after_assess)
        entry = assess
        transitions = {
            assess: {
                "accepted": assess,
                "done": FINISH,
            }
        }

    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "gates.json").write_text(
        json.dumps(
            {
                "gates": [
                    {"gate_id": "alpha", "title": "Alpha", "status": "queued"},
                    {"gate_id": "beta", "title": "Beta", "status": "queued"},
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = Engine(
        EffectsWorkflow,
        provider=ScriptedLLMProvider(
            llm_turns=[
                Outcome(raw_output="ok-1", tag="accepted"),
                Outcome(raw_output="ok-2", tag="accepted"),
            ]
        ),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        runtime_event_sink=lambda event_type, payload: runtime_events.append((event_type, dict(payload))),
    ).run(
        task_id="task-effects",
        run_id="run-effects",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    payload = json.loads((task_folder / "gates.json").read_text(encoding="utf-8"))

    assert result.terminal == FINISH
    assert result.history == ("assess", "assess")
    assert [item["status"] for item in payload["gates"]] == ["completed", "completed"]
    assert [event_type for event_type, _ in runtime_events].count("worklist_status_set") == 2
    assert runtime_events[-1][0] == "worklist_exhausted"
def test_route_hook_may_return_direct_worklist_effect_for_active_scoped_worklist(tmp_path: Path):
    def _complete_current_item(_ctx):
        return WorklistEffect.complete_and_advance(exhausted="done")

    class DirectRouteHookEffectWorkflow(Workflow):
        board = Artifact.json("{{ task.folder }}/gates.json", required=True)
        gates = Worklist.from_artifact(
            name="gate",
            artifact=board,
            collection="gates",
            item_id="gate_id",
            title="title",
            status="status",
        )
        assess = PromptStep(name="assess", producer="assess.md", scope=gates)
        entry = assess
        transitions = {assess: {"done": Route.to(FINISH, on_taken=_complete_current_item)}}

    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "gates.json").write_text(
        '{"gates":[{"gate_id":"alpha","title":"Alpha","status":"queued"}]}\n',
        encoding="utf-8",
    )

    result = Engine(
        DirectRouteHookEffectWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-direct-route-hook-effect",
        run_id="run-direct-route-hook-effect",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    payload = json.loads((task_folder / "gates.json").read_text(encoding="utf-8"))

    assert result.terminal == FINISH
    assert result.last_event is not None
    assert result.last_event.tag == "done"
    assert payload["gates"][0]["status"] == "completed"
def test_after_hook_effect_event_takes_precedence_over_exhausted_route(tmp_path: Path):
    def after_assess(_ctx):
        return Effects(
            worklists=(WorklistEffect.complete_and_advance(exhausted="done"),),
            event="publish",
        )

    def finish_handler(_ctx):
        return Event("done")

    class EffectsPrecedenceWorkflow(Workflow):
        board = Artifact.json("{{ task.folder }}/gates.json", required=True)
        gates = Worklist.from_artifact(
            name="gate",
            artifact=board,
            collection="gates",
            item_id="gate_id",
            title="title",
            status="status",
        )
        assess = PromptStep(name="assess", producer="assess.md", scope=gates, after=after_assess)
        publish = PythonStep(name="publish", handler=finish_handler)
        entry = assess
        transitions = {
            assess: {"accepted": FINISH, "publish": publish, "done": FINISH},
            publish: {"done": FINISH},
        }

    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "gates.json").write_text(
        '{"gates":[{"gate_id":"alpha","title":"Alpha","status":"queued"}]}\n',
        encoding="utf-8",
    )

    result = Engine(
        EffectsPrecedenceWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="accepted")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-effects-precedence",
        run_id="run-effects-precedence",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    payload = json.loads((task_folder / "gates.json").read_text(encoding="utf-8"))

    assert result.terminal == FINISH
    assert result.history == ("assess", "publish")
    assert result.last_event is not None
    assert result.last_event.tag == "done"
    assert payload["gates"][0]["status"] == "completed"
@pytest.mark.parametrize(
    ("control_kind", "expected_terminal", "expected_history", "expected_last_tag"),
    [
        ("request_input", AWAIT_INPUT, ("assess",), None),
        ("goto", FINISH, ("assess", "publish"), "done"),
        ("fail", FAIL, ("assess",), "failed"),
    ],
)
def test_after_hook_effect_runtime_controls_match_direct_controls(
    tmp_path: Path,
    control_kind,
    expected_terminal,
    expected_history,
    expected_last_tag,
):
    def make_control():
        if control_kind == "request_input":
            return RequestInput("Need approval?", reason="Await operator input.")
        if control_kind == "goto":
            return Goto("publish", reason="Skip directly to publication.")
        if control_kind == "fail":
            return Fail("Stop after capturing the gate status.")
        raise AssertionError(f"unexpected control kind {control_kind!r}")

    def run_variant(*, use_effect: bool):
        def publish_handler(_ctx):
            return Event("done")

        def after_assess(ctx):
            ctx.current_worklist.set_current_status("completed")
            return make_control()

        def after_assess_effect(_ctx):
            return Effects(
                worklists=(WorklistEffect.complete_current(),),
                event=make_control(),
            )

        after_hook = after_assess_effect if use_effect else after_assess
        after_hook.__name__ = "control_hook"

        class ControlWorkflow(Workflow):
            board = Artifact.json("{{ task.folder }}/gates.json", required=True)
            gates = Worklist.from_artifact(
                name="gate",
                artifact=board,
                collection="gates",
                item_id="gate_id",
                title="title",
                status="status",
            )
            assess = PromptStep(name="assess", producer="assess.md", scope=gates, after=after_hook)
            publish = PythonStep(name="publish", handler=publish_handler)
            entry = assess
            transitions = {
                assess: {"accepted": FINISH},
                publish: {"done": FINISH},
            }

        ControlWorkflow.__name__ = f"ControlWorkflow_{control_kind}_{'effect' if use_effect else 'direct'}"
        ControlWorkflow.__qualname__ = ControlWorkflow.__name__

        variant_root = tmp_path / ("effect" if use_effect else "direct")
        variant_root.mkdir()
        task_folder, run_folder = _workspace(variant_root)
        (task_folder / "gates.json").write_text(
            '{"gates":[{"gate_id":"alpha","title":"Alpha","status":"queued"}]}\n',
            encoding="utf-8",
        )

        result = Engine(
            ControlWorkflow,
            provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="accepted")]),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-effect-controls",
            run_id="run-effect-controls",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

        payload = json.loads((task_folder / "gates.json").read_text(encoding="utf-8"))
        return result, payload

    direct_result, direct_payload = run_variant(use_effect=False)
    effect_result, effect_payload = run_variant(use_effect=True)

    assert direct_result.terminal == expected_terminal
    assert effect_result.terminal == expected_terminal
    assert direct_result.history == expected_history
    assert effect_result.history == expected_history
    assert direct_payload["gates"][0]["status"] == "completed"
    assert effect_payload["gates"][0]["status"] == "completed"

    if expected_terminal == AWAIT_INPUT:
        assert direct_result.last_transition.source_hook == "control_hook"
        assert effect_result.last_transition.source_hook == "control_hook"
        assert direct_result.last_transition.source_phase == "after"
        assert effect_result.last_transition.source_phase == "after"
        assert direct_result.checkpoint is not None
        assert effect_result.checkpoint is not None
        assert direct_result.checkpoint.pending_input is not None
        assert effect_result.checkpoint.pending_input is not None
        assert direct_result.checkpoint.pending_input.question == "Need approval?"
        assert effect_result.checkpoint.pending_input.question == "Need approval?"
    elif control_kind == "goto":
        assert direct_result.last_transition.source_hook == "handler"
        assert effect_result.last_transition.source_hook == "handler"
        assert direct_result.last_transition.source_phase == "python_step"
        assert effect_result.last_transition.source_phase == "python_step"
        assert direct_result.checkpoint is None
        assert effect_result.checkpoint is None
    elif control_kind == "fail":
        assert direct_result.last_transition.source_hook == "control_hook"
        assert effect_result.last_transition.source_hook == "control_hook"
        assert direct_result.last_transition.source_phase == "after"
        assert effect_result.last_transition.source_phase == "after"
        assert direct_result.last_transition.runtime_control == "fail"
        assert effect_result.last_transition.runtime_control == "fail"
        assert direct_result.last_event is None
        assert effect_result.last_event is None
    else:
        assert direct_result.last_event is not None
        assert effect_result.last_event is not None
        assert direct_result.last_event.tag == expected_last_tag
        assert effect_result.last_event.tag == expected_last_tag
