from __future__ import annotations

from tests.contract.engine._shared import *

def test_on_start_opens_sessions_before_execution(tmp_path: Path):
    def _startsessionworkflow_on_start(ctx):
        ctx.open_session(StartSessionWorkflow.main)
        ctx.open_session(StartSessionWorkflow.auxiliary_slot)

    def _startsessionworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'session_id': ctx.outcome.payload['session_id']})
        return None

    class StartSessionWorkflow(Workflow):
        class State(BaseModel):
            session_id: str = ""

        main = Session()
        auxiliary_slot = Session()
        ask = PromptStep(name="ask", producer="ask.md", session=main)
        entry = ask
        transitions = {ask: {"done": FINISH}}


    StartSessionWorkflow.ask.before = _chain_hooks(_startsessionworkflow_on_start, StartSessionWorkflow.ask.before)
    StartSessionWorkflow.ask.after = _chain_hooks(_startsessionworkflow_on_ask, StartSessionWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    session_store = InMemorySessionStore()
    engine = Engine(
        StartSessionWorkflow,
        provider=ScriptedLLMProvider(
            llm_turns=[
                lambda request: Outcome(
                    raw_output="ok",
                    tag="done",
                    payload={"session_id": request.session.session_id},
                )
            ]
        ),
        session_store=session_store,
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    snapshot = session_store.snapshot()
    assert result.state.session_id.startswith("main:global:")
    assert snapshot.active_scopes == {"main": None, "auxiliary_slot": None}
def test_declared_session_auto_opens_without_on_start(tmp_path: Path):
    def _autoopensessionworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'seen': ctx.outcome.payload['session_id']})
        return None

    class AutoOpenSessionWorkflow(Workflow):
        class State(BaseModel):
            seen: str = ""

        main = Session(continuity=Continuity.task())
        ask = PromptStep(name="ask", producer="ask.md", session=main)
        entry = ask
        transitions = {ask: {"done": FINISH}}

    AutoOpenSessionWorkflow.ask.after = _chain_hooks(_autoopensessionworkflow_on_ask, AutoOpenSessionWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    session_store = InMemorySessionStore()
    engine = Engine(
        AutoOpenSessionWorkflow,
        provider=ScriptedLLMProvider(
            llm_turns=[
                lambda request: Outcome(
                    raw_output="ok",
                    tag="done",
                    payload={"session_id": request.session.session_id},
                )
            ]
        ),
        session_store=session_store,
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    checkpoint = session_store.snapshot()
    assert result.state.seen.startswith("main:task-1:")
    assert checkpoint.active_keys_by_slot["main"].domain == "task"
def test_provider_steps_without_explicit_session_use_default_session(tmp_path: Path):
    def _defaultsessionworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'llm_session': ctx.outcome.payload['session_id']})
        return None

    def _defaultsessionworkflow_on_review(ctx):
        ctx.state = ctx.state.model_copy(update={'pair_session': ctx.outcome.payload['session_id']})
        return None

    class DefaultSessionWorkflow(Workflow):
        class State(BaseModel):
            llm_session: str = ""
            pair_session: str = ""

        ask = PromptStep(name="ask", producer="ask.md")
        review = ProduceVerifyStep(name="review", producer="review.md", verifier="verify.md")
        entry = ask
        transitions = {
            ask: {"next": review},
            review: {"done": FINISH},
        }


    DefaultSessionWorkflow.ask.after = _chain_hooks(_defaultsessionworkflow_on_ask, DefaultSessionWorkflow.ask.after)
    DefaultSessionWorkflow.review.after_verifier = _chain_hooks(_defaultsessionworkflow_on_review, DefaultSessionWorkflow.review.after_verifier)


    task_folder, run_folder = _workspace(tmp_path)
    session_store = InMemorySessionStore()
    engine = Engine(
        DefaultSessionWorkflow,
        provider=ScriptedLLMProvider(
            llm_turns=[
                lambda request: Outcome(
                    raw_output="ask",
                    tag="next",
                    payload={"session_id": request.session.session_id},
                )
            ],
            producer_turns=[lambda request: "draft"],
            verifier_turns=[
                lambda request: Outcome(
                    raw_output="verify",
                    tag="done",
                    payload={"session_id": request.session.session_id},
                )
            ],
        ),
        session_store=session_store,
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    snapshot = session_store.snapshot()
    assert result.state.llm_session.startswith("global:global:")
    assert result.state.pair_session == result.state.llm_session
    assert snapshot.active_keys_by_slot["global"].domain == "run"
def test_llm_retry_reuses_pre_step_session_not_failed_attempt_session(tmp_path: Path):
    def _sessionretryworkflow_on_start(ctx):
        ctx.open_session(SessionRetryWorkflow.main)

    def _sessionretryworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'final_session_id': ctx.outcome.payload['session_id']})
        return None

    class SessionRetryWorkflow(Workflow):
        class State(BaseModel):
            final_session_id: str = ""

        main = Session()
        ask = PromptStep(name="ask", producer="ask.md", session=main)
        entry = ask
        transitions = {ask: {"done": FINISH}, GLOBAL: {"failed": FAIL}}


    SessionRetryWorkflow.ask.before = _chain_hooks(_sessionretryworkflow_on_start, SessionRetryWorkflow.ask.before)
    SessionRetryWorkflow.ask.after = _chain_hooks(_sessionretryworkflow_on_ask, SessionRetryWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    session_store = InMemorySessionStore()
    seen_request_sessions: list[tuple[int, str | None]] = []

    def illegal_route(request):
        seen_request_sessions.append((request.attempt, request.session.session_id if request.session is not None else None))
        assert request.session is not None
        return OutcomeResponse(
            outcome=Outcome(raw_output="bad", tag="unexpected"),
            session=SessionBinding(key=request.session.key, session_id="retry-attempt-1"),
        )

    def accepted(request):
        seen_request_sessions.append((request.attempt, request.session.session_id if request.session is not None else None))
        assert request.session is not None
        return OutcomeResponse(
            outcome=Outcome(
                raw_output="ok",
                tag="done",
                payload={"session_id": "retry-attempt-2"},
            ),
            session=SessionBinding(key=request.session.key, session_id="retry-attempt-2"),
        )

    result = Engine(
        SessionRetryWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[illegal_route, accepted]),
        session_store=session_store,
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert len(seen_request_sessions) == 2
    assert seen_request_sessions[0][0] == 1
    assert seen_request_sessions[1][0] == 2
    assert seen_request_sessions[0][1] is not None
    assert seen_request_sessions[1][1] == seen_request_sessions[0][1]
    final_binding = session_store.get("main")
    assert final_binding is not None
    assert final_binding.session_id == "retry-attempt-2"
def test_pair_retry_reuses_pre_step_session_but_keeps_attempt_local_session_chain(tmp_path: Path):
    def _pairsessionretryworkflow_on_start(ctx):
        ctx.open_session(PairSessionRetryWorkflow.main)

    def _pairsessionretryworkflow_on_review(ctx):
        if ctx.outcome.payload.get('write_report'):
            ctx.artifacts.report.write_text('ready')
        ctx.state = ctx.state.model_copy(update={'final_session_id': ctx.outcome.payload['session_id']})
        return None

    class PairSessionRetryWorkflow(Workflow):
        class State(BaseModel):
            final_session_id: str = ""

        main = Session()
        review = ProduceVerifyStep(
            name="review",
            producer="review.md",
            verifier="verify.md",
            session=main,
            producer_writes={"report": Artifact.md("report.md")},
            route_metadata={"done": Route(summary="review completed", required_writes=("report",))},
        )
        entry = review
        transitions = {review: {"done": FINISH}}


    PairSessionRetryWorkflow.review.before = _chain_hooks(_pairsessionretryworkflow_on_start, PairSessionRetryWorkflow.review.before)
    PairSessionRetryWorkflow.review.after_verifier = _chain_hooks(_pairsessionretryworkflow_on_review, PairSessionRetryWorkflow.review.after_verifier)


    task_folder, run_folder = _workspace(tmp_path)
    session_store = InMemorySessionStore()
    producer_sessions: list[tuple[int, str | None]] = []
    verifier_sessions: list[tuple[int, str | None]] = []

    def produce(request):
        producer_sessions.append((request.attempt, request.session.session_id if request.session is not None else None))
        assert request.session is not None
        return ProducerResponse(
            raw_output=f"draft-{request.attempt}",
            session=SessionBinding(key=request.session.key, session_id=f"producer-{request.attempt}"),
        )

    def verify(request):
        verifier_sessions.append((request.attempt, request.session.session_id if request.session is not None else None))
        assert request.session is not None
        return OutcomeResponse(
            outcome=Outcome(
                raw_output=f"verify-{request.attempt}",
                tag="done",
                payload={
                    "write_report": request.attempt == 2,
                    "session_id": f"verifier-{request.attempt}",
                },
            ),
            session=SessionBinding(key=request.session.key, session_id=f"verifier-{request.attempt}"),
        )

    result = Engine(
        PairSessionRetryWorkflow,
        provider=ScriptedLLMProvider(producer_turns=[produce, produce], verifier_turns=[verify, verify]),
        session_store=session_store,
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert len(producer_sessions) == 2
    assert len(verifier_sessions) == 2
    assert producer_sessions[0][1] is not None
    assert producer_sessions[1][1] == producer_sessions[0][1]
    assert verifier_sessions == [
        (1, "producer-1"),
        (2, "producer-2"),
    ]
    final_binding = session_store.get("main")
    assert final_binding is not None
    assert final_binding.session_id == "verifier-2"
def test_resume_reuses_legacy_global_session_binding(tmp_path: Path):
    def _resumeworkflow_on_ask(ctx):
        ctx.state = ctx.state.model_copy(update={'seen': ctx.outcome.payload['session_id']})
        return None

    class ResumeWorkflow(Workflow):
        class State(BaseModel):
            seen: str = ""

        main = Session()
        ask = PromptStep(name="ask", producer="ask.md", session=main)
        entry = ask
        transitions = {ask: {"done": FINISH}}

    ResumeWorkflow.ask.after = _chain_hooks(_resumeworkflow_on_ask, ResumeWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    session_store = InMemorySessionStore()
    checkpoint_store = InMemoryCheckpointStore()
    checkpoint_store.save(
        Checkpoint(
            stage="ask",
            state=ResumeWorkflow.State(),
            session_bindings=SessionSnapshot(
                bindings=(SessionBinding(ref_name="main", scope=None, session_id="legacy-main:global:7"),),
                active_scopes={"main": None},
            ),
        )
    )
    engine = Engine(
        ResumeWorkflow,
        provider=ScriptedLLMProvider(
            llm_turns=[
                lambda request: Outcome(
                    raw_output="ok",
                    tag="done",
                    payload={"session_id": request.session.session_id},
                )
            ]
        ),
        session_store=session_store,
        checkpoint_store=checkpoint_store,
    )

    resumed = engine.resume(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert resumed.terminal == FINISH
    assert resumed.state.seen == "legacy-main:global:7"
    snapshot = session_store.snapshot()
    assert snapshot.active_keys_by_slot["main"] == SessionKey("main", "run", "run-1")
    assert snapshot.bindings[0].key == SessionKey("main", "run", "run-1")
def test_phase_scoped_sessions_follow_active_scope_switches(tmp_path: Path):
    def _scopedworkflow_on_activate_a(ctx):
        ctx.open_session('phase_session', scope='phase-a')
        return Event('phase-a')

    def _scopedworkflow_on_use_a(ctx):
        ctx.state = ctx.state.model_copy(update={'seen': [*ctx.state.seen, ctx.outcome.payload['session_id']]})
        return None

    def _scopedworkflow_on_activate_b(ctx):
        ctx.open_session('phase_session', scope='phase-b')
        return Event('phase-b')

    def _scopedworkflow_on_use_b(ctx):
        ctx.state = ctx.state.model_copy(update={'seen': [*ctx.state.seen, ctx.outcome.payload['session_id']]})
        return None

    def _scopedworkflow_on_finish(ctx):
        return Event('end')

    class ScopedWorkflow(Workflow):
        class State(BaseModel):
            seen: list[str] = Field(default_factory=list)

        phase_session = Session()
        activate_a = PythonStep(name="activate_a", handler=_scopedworkflow_on_activate_a)
        use_a = PromptStep(name="use_a", producer="use.md", session=phase_session)
        activate_b = PythonStep(name="activate_b", handler=_scopedworkflow_on_activate_b)
        use_b = PromptStep(name="use_b", producer="use.md", session=phase_session)
        finish = PythonStep(name="finish", handler=_scopedworkflow_on_finish)
        entry = activate_a
        transitions = {
            activate_a: {"phase-a": use_a},
            use_a: {"next": activate_b},
            activate_b: {"phase-b": use_b},
            use_b: {"done": finish},
            finish: {"end": FINISH},
        }
    ScopedWorkflow.use_a.after = _chain_hooks(_scopedworkflow_on_use_a, ScopedWorkflow.use_a.after)
    ScopedWorkflow.use_b.after = _chain_hooks(_scopedworkflow_on_use_b, ScopedWorkflow.use_b.after)


    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        ScopedWorkflow,
        provider=ScriptedLLMProvider(
            llm_turns=[
                lambda request: Outcome(
                    raw_output="a",
                    tag="next",
                    payload={"session_id": request.session.session_id},
                ),
                lambda request: Outcome(
                    raw_output="b",
                    tag="done",
                    payload={"session_id": request.session.session_id},
                ),
            ]
        ),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert len(result.state.seen) == 2
    assert result.state.seen[0].startswith("phase_session:phase-a:")
    assert result.state.seen[1].startswith("phase_session:phase-b:")
    assert result.state.seen[0] != result.state.seen[1]
def test_work_item_session_resume_uses_dir_key_based_key_and_reuses_session(tmp_path: Path):
    class WorkItemSessionResumeWorkflow(Workflow):
        class State(BaseModel):
            pass

        gate_board = Artifact.json("{task_folder}/gates.json", required=True)
        gates = Worklist.from_artifact(
            name="gate",
            artifact=gate_board,
            collection="gates",
            item_id="gate_id",
            title="title",
            status="status",
        )
        reviewer = Session(continuity=Continuity.work_item(gates))
        assess = PromptStep(
            name="assess",
            producer="assess.md",
            scope=gates,
            session=reviewer,
            route_metadata={"passed": Route(summary="gate assessed")},
        )
        entry = assess
        transitions = {assess: {"passed": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "gates.json").write_text(
        '{"gates":[{"gate_id":"gate-a","dir_key":"phase-1","title":"Gate A","status":"queued"}]}\n',
        encoding="utf-8",
    )
    checkpoint_store = InMemoryCheckpointStore()
    first_session_id: str | None = None

    def _failing_turn(request):
        nonlocal first_session_id
        first_session_id = request.session.session_id
        raise RuntimeError("checkpoint me")

    failing_engine = Engine(
        WorkItemSessionResumeWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[_failing_turn]),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(WorkflowExecutionError, match="checkpoint me"):
        failing_engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.session_bindings.active_keys_by_slot["reviewer"] == SessionKey(
        slot="reviewer",
        domain="work_item",
        value="gate:phase-1",
    )
    assert first_session_id is not None

    def _resumed_turn(request):
        assert request.session.session_id == first_session_id
        return Outcome(raw_output="ok", tag="passed")

    resumed = Engine(
        WorkItemSessionResumeWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[_resumed_turn]),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    ).resume(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert resumed.terminal == FINISH
def test_non_scoped_work_item_session_fails_when_no_current_item_exists(tmp_path: Path):
    class EmptyWorkItemSessionWorkflow(Workflow):
        class State(BaseModel):
            pass

        gates = Worklist.from_items(name="gate", items=())
        reviewer = Session(continuity=Continuity.work_item(gates))
        publish = PromptStep(name="publish", producer="publish.md", session=reviewer)
        entry = publish
        transitions = {publish: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        EmptyWorkItemSessionWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    with pytest.raises(
        WorkflowExecutionError,
        match=r"session 'reviewer' uses work-item continuity for worklist 'gate', but no current work item is available for step 'publish'",
    ):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )
def test_invalid_goto_after_session_mutation_preserves_checkpoint_session_bindings(tmp_path: Path):
    def after(ctx):
        ctx.set_global_session("hook-mutated-session")
        return Goto("missing_step", reason="This target does not exist.")

    def _invalidgotosessionworkflow_on_ask(ctx):
        return Event("done")

    class InvalidGotoSessionWorkflow(Workflow):
        class State(BaseModel):
            note: str = "initial"

        ask = PythonStep(name="ask", after=after, handler=_invalidgotosessionworkflow_on_ask)
        entry = ask
        transitions = {ask: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        InvalidGotoSessionWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(WorkflowExecutionError, match="declared workflow step"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert any(binding.session_id == "hook-mutated-session" for binding in checkpoint.session_bindings.bindings)
    assert checkpoint.failure_context is not None
    assert checkpoint.failure_context["kind"] == "runtime_control_validation"
def test_produce_verify_step_verifier_session_override_uses_distinct_verifier_session_slot(tmp_path: Path):
    def after_assess(ctx):
        return None

    class ReviewWorkflow(SimpleWorkflow):
        main = Session()
        reviewer = Session()

        assess = produce_verify_step(
            producer_prompt="Draft the assessment.",
            verifier_prompt="Review the assessment.",
            producer_writes=[Md("draft")],
            verifier_writes=[Md("review_report")],
            routes={
                "approved": Route.to(FINISH, required_writes=[]),
            },
            session=main,
            verifier_session=reviewer,
            retry=1,
            after_verifier=after_assess,
        )

    task_folder, run_folder = _workspace(tmp_path)
    session_store = InMemorySessionStore()
    producer_sessions: list[tuple[str | None, str | None]] = []
    verifier_sessions: list[tuple[str | None, str | None]] = []

    def produce(request):
        producer_sessions.append(
            (request.session.ref_name if request.session is not None else None, request.session.session_id if request.session is not None else None)
        )
        assert request.session is not None
        assert request.session.ref_name == "main"
        return ProducerResponse(
            raw_output="draft text",
            session=SessionBinding(key=request.session.key, session_id="producer-main"),
        )

    def verify(request):
        verifier_sessions.append(
            (request.session.ref_name if request.session is not None else None, request.session.session_id if request.session is not None else None)
        )
        assert request.session is not None
        assert request.session.ref_name == "reviewer"
        assert request.session.session_id != "producer-main"
        return OutcomeResponse(
            outcome=Outcome(raw_output="approve", tag="approved"),
            session=SessionBinding(key=request.session.key, session_id="reviewer-verified"),
        )

    result = Engine(
        ReviewWorkflow,
        provider=ScriptedLLMProvider(producer_turns=[produce], verifier_turns=[verify]),
        session_store=session_store,
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert len(producer_sessions) == 1
    assert len(verifier_sessions) == 1
    assert producer_sessions[0][0] == "main"
    assert verifier_sessions[0][0] == "reviewer"
    assert producer_sessions[0][1] != verifier_sessions[0][1]
    main_binding = session_store.get("main")
    reviewer_binding = session_store.get("reviewer")
    assert main_binding is not None
    assert reviewer_binding is not None
    assert main_binding.session_id == "producer-main"
    assert reviewer_binding.session_id == "reviewer-verified"
