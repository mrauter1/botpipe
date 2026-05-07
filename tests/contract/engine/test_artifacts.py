from __future__ import annotations

from tests.contract.engine._shared import *

def test_system_question_events_validate_strictly_and_failed_remains_authored(tmp_path: Path):
    def _askquestionworkflow_on_ask(ctx):
        return Event('question', question='Need input?')

    class AskQuestionWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PythonStep(name="ask", handler=_askquestionworkflow_on_ask)
        entry = ask
        transitions = {ask: {"question": AWAIT_INPUT}}


    def _invalidquestionworkflow_on_ask(ctx):
        return Event('question')

    class InvalidQuestionWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PythonStep(name="ask", handler=_invalidquestionworkflow_on_ask)
        entry = ask
        transitions = {ask: {"question": AWAIT_INPUT}}


    def _failworkflow_on_ask(ctx):
        return Event('failed', reason='Could not continue.')

    class FailWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PythonStep(name="ask", handler=_failworkflow_on_ask)
        entry = ask
        transitions = {ask: {"failed": FAIL}}


    task_folder, run_folder = _workspace(tmp_path)
    paused = Engine(
        AskQuestionWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-pause",
        run_id="run-pause",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )
    failed = Engine(
        FailWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-fail",
        run_id="run-fail",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert paused.terminal == AWAIT_INPUT
    assert paused.checkpoint is not None
    assert paused.checkpoint.pending_input is not None
    assert paused.checkpoint.pending_input.question == "Need input?"
    assert failed.terminal == FAIL
    assert failed.last_event is not None
    assert failed.last_event.reason == "Could not continue."

    with pytest.raises(WorkflowExecutionError, match="question route without a non-empty question"):
        Engine(
            InvalidQuestionWorkflow,
            provider=ScriptedLLMProvider(),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-bad-question",
            run_id="run-bad-question",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )
def test_missing_required_artifact_raises_and_checkpoints(tmp_path: Path):
    def _missinginputworkflow_on_ask(ctx):
        return None

    class MissingInputWorkflow(Workflow):
        class State(BaseModel):
            pass

        request = Artifact("{task_folder}/request.txt")
        ask = PromptStep(name="ask", producer="ask.md", requires=[request])
        entry = ask
        transitions = {ask: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        MissingInputWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(MissingArtifactError):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.stage == "ask"
def test_missing_required_produced_artifact_raises_provider_error_and_checkpoints_context(tmp_path: Path):
    def _requiredproducedworkflow_on_ask(ctx):
        return None

    class RequiredProducedWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            writes={"summary": Artifact.md("summary.md", required=True)},
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {ask: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        RequiredProducedWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(ProviderExecutionError, match=r"artifact validation failed.*route 'done'.*summary"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.stage == "ask"
    assert checkpoint.failure_context is not None
    assert checkpoint.failure_context["kind"] == "missing_required_output_artifact"
    assert checkpoint.failure_context["step_name"] == "ask"
    assert checkpoint.failure_context["candidate_route"] == "done"
    assert checkpoint.failure_context["final_route"] == "done"
    assert checkpoint.failure_context["provider_attributable"] is True
    assert checkpoint.failure_context["artifact_name"] == "summary"
    assert checkpoint.failure_context["qualified_name"] == "ask.summary"
    assert checkpoint.failure_context["path"] == str(task_folder / "wf_required_produced_workflow" / "ask" / "summary.md")
    assert checkpoint.failure_context["errors"] == ["artifact file does not exist"]
    assert "artifact validation failed for step 'ask' route 'done'" in checkpoint.failure_context["error"]
    assert checkpoint.failure_context["details"]["retry_attempts_consumed"] == 1
    assert checkpoint.failure_context["details"]["retry_max_attempts"] == 1
    assert checkpoint.failure_context["details"]["retry_exhausted"] is True
    assert len(engine.provider.calls) == 1
def test_invalid_middleware_route_still_fails_before_artifact_validation(tmp_path: Path):
    def _invalidmiddlewarerouteworkflow_on_outcome(ctx):
        return Event('bogus')

    class InvalidMiddlewareRouteWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            writes={"summary": Artifact.md("summary.md", required=True)},
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {ask: {"done": FINISH}}


    InvalidMiddlewareRouteWorkflow.ask.after = _invalidmiddlewarerouteworkflow_on_outcome


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        InvalidMiddlewareRouteWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(WorkflowExecutionError, match="produced illegal route 'bogus'"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.stage == "ask"
    assert checkpoint.failure_context is not None
    assert checkpoint.failure_context["kind"] == "hook_failure"
    assert checkpoint.failure_context["candidate_route"] == "done"
    assert checkpoint.failure_context["provider_attributable"] is False
    assert checkpoint.failure_context["source_hook"] == "_invalidmiddlewarerouteworkflow_on_outcome"
    assert checkpoint.failure_context["source_phase"] == "after"
    assert len(engine.provider.calls) == 1
def test_invalid_system_route_still_fails_before_artifact_validation(tmp_path: Path):
    def _invalidsystemrouteworkflow_on_publish(ctx):
        return Event('bogus')

    class InvalidSystemRouteWorkflow(Workflow):
        class State(BaseModel):
            pass

        publish = PythonStep(
            name="publish",
            writes={"summary": Artifact.md("summary.md", required=True)},
            handler=_invalidsystemrouteworkflow_on_publish,
        )
        entry = publish
        transitions = {publish: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        InvalidSystemRouteWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(WorkflowExecutionError, match="produced illegal route 'bogus'"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.stage == "publish"
    assert checkpoint.failure_context is not None
    assert checkpoint.failure_context["kind"] == "route_validation"
    assert checkpoint.failure_context["candidate_route"] == "bogus"
    assert engine.provider.calls == []
def test_engine_emits_artifact_validation_failure_events(tmp_path: Path):
    def _missingartifactworkflow_on_ask(ctx):
        return None

    class MissingArtifactWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            writes={"summary": Artifact.md("summary.md", required=True)},
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {ask: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    runtime_events: list[tuple[str, dict[str, object]]] = []
    engine = Engine(
        MissingArtifactWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        runtime_event_sink=lambda event_type, payload: runtime_events.append((event_type, dict(payload))),
    )

    with pytest.raises(ProviderExecutionError, match=r"artifact validation failed.*summary"):
        engine.run(
            task_id="task-artifact-events",
            run_id="run-artifact-events",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    artifact_events = [payload for event_type, payload in runtime_events if event_type == "artifact_validation_failed"]
    assert artifact_events == [
        {
            "step_name": "ask",
            "visit": 1,
            "step_execution_id": "ask:1",
            "route": "done",
            "artifact_name": "summary",
            "qualified_name": "ask.summary",
            "path": str(task_folder / "wf_missing_artifact_workflow" / "ask" / "summary.md"),
            "validation_kind": "missing_required_artifact",
            "errors": ["artifact file does not exist"],
            "provider_attributable": True,
        }
    ]
def test_required_json_artifact_written_by_handler_validates_after_handler(tmp_path: Path):
    class SummaryPayload(BaseModel):
        summary: str

    def _handlerartifactworkflow_on_ask(ctx):
        ctx.artifacts.summary.write_json({'summary': ctx.outcome.payload['summary']})
        ctx.state = ctx.state.model_copy(update={'summary': ctx.outcome.payload['summary']})
        return None

    class HandlerArtifactWorkflow(Workflow):
        class State(BaseModel):
            summary: str = ""

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            writes={"summary": Artifact.json("summary.json", schema=SummaryPayload, required=True)},
        )
        entry = ask
        transitions = {ask: {"done": FINISH}}

    HandlerArtifactWorkflow.ask.after = _chain_hooks(_handlerartifactworkflow_on_ask, HandlerArtifactWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        HandlerArtifactWorkflow,
        provider=ScriptedLLMProvider(
            llm_turns=[Outcome(raw_output="ok", tag="done", payload={"summary": "ready"})]
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
    assert result.state.summary == "ready"
    assert (
        task_folder / "wf_handler_artifact_workflow" / "ask" / "summary.json"
    ).read_text(encoding="utf-8").strip() == '{\n  "summary": "ready"\n}'
def test_optional_json_artifact_absent_is_allowed(tmp_path: Path):
    class SummaryPayload(BaseModel):
        summary: str

    def _optionalartifactworkflow_on_ask(ctx):
        return None

    class OptionalArtifactWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            writes={"summary": Artifact.json("summary.json", schema=SummaryPayload)},
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {ask: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        OptionalArtifactWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
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
def test_optional_present_schema_artifact_must_validate(tmp_path: Path):
    class SummaryPayload(BaseModel):
        summary: str

    def _invalidoptionalartifactworkflow_on_ask(ctx):
        ctx.artifacts.summary.write_json({'wrong': 'value'})
        return None

    class InvalidOptionalArtifactWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            writes={"summary": Artifact.json("summary.json", schema=SummaryPayload)},
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {ask: {"done": FINISH}}

    InvalidOptionalArtifactWorkflow.ask.after = _chain_hooks(_invalidoptionalartifactworkflow_on_ask, InvalidOptionalArtifactWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        InvalidOptionalArtifactWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(ProviderExecutionError, match=r"artifact validation failed.*summary"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.failure_context is not None
    assert checkpoint.failure_context["artifact_name"] == "summary"
    assert checkpoint.failure_context["route"] == "done"
    assert checkpoint.failure_context["kind"] == "invalid_output_artifact"
    assert checkpoint.failure_context["retry_attempts_consumed"] == 1
    assert checkpoint.failure_context["retry_max_attempts"] == 1
    assert checkpoint.failure_context["retry_exhausted"] is True
    assert len(engine.provider.calls) == 1
def test_route_specific_required_artifacts_override_required_defaults(tmp_path: Path):
    def _routeoverrideworkflow_on_ask(ctx):
        ctx.artifacts.report.write_text('ready')
        return None

    class RouteOverrideWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            writes={
                "summary": Artifact.md("summary.md", required=True),
                "report": Artifact.md("report.md"),
            },
            route_metadata={
                "done": Route(summary="only the report is required for this route", required_writes=("report",))
            },
        )
        entry = ask
        transitions = {ask: {"done": FINISH}}

    RouteOverrideWorkflow.ask.after = _chain_hooks(_routeoverrideworkflow_on_ask, RouteOverrideWorkflow.ask.after)


    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        RouteOverrideWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
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
    assert (task_folder / "wf_route_override_workflow" / "ask" / "summary.md").exists() is False
def test_system_step_route_specific_required_artifacts_raise_workflow_error(tmp_path: Path):
    def _systemrouteworkflow_on_publish(ctx):
        return Event('done')

    class SystemRouteWorkflow(Workflow):
        class State(BaseModel):
            pass

        publish = PythonStep(
            name="publish",
            writes={
                "summary": Artifact.md("summary.md", required=True),
                "report": Artifact.md("report.md"),
            },
            route_metadata={"done": Route(summary="publish completed", required_writes=("report",))},
            handler=_systemrouteworkflow_on_publish,
        )
        entry = publish
        transitions = {publish: {"done": FINISH}}


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()
    engine = Engine(
        SystemRouteWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    with pytest.raises(WorkflowExecutionError, match=r"artifact validation failed.*report"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.failure_context is not None
    assert checkpoint.failure_context["artifact_name"] == "report"
    assert checkpoint.failure_context["qualified_name"] == "publish.report"
def test_on_taken_runs_before_required_output_validation_and_can_heal_artifact(tmp_path: Path):
    def on_taken(ctx):
        ctx.artifacts.report.write_text("published report\n")

    def _overriderequiredoutputworkflow_on_ask(ctx):
        return None

    class OverrideRequiredOutputWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            writes={"report": Artifact.md("report.md")},
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {
            ask: {
                "done": Route.to(FINISH, required_writes=("report",), on_taken=on_taken),
            }
        }


    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        OverrideRequiredOutputWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
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
    assert (
        task_folder / "wf_override_required_output_workflow" / "ask" / "report.md"
    ).read_text(encoding="utf-8") == "published report\n"
def test_route_redirected_final_route_drives_required_write_validation(tmp_path: Path):
    def after_ask(ctx):
        return "publish"

    def _finalroutevalidationworkflow_on_ask(ctx):
        return None

    class FinalRouteValidationWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            writes={"report": Artifact.md("report.md")},
            after=after_ask,
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {
            ask: {
                "draft": Route.to(FINISH, required_writes=[]),
                "publish": Route.to(FINISH, required_writes=("report",)),
            }
        }


    task_folder, run_folder = _workspace(tmp_path)
    with pytest.raises(WorkflowExecutionError, match=r"artifact validation failed.*route 'publish'"):
        Engine(
            FinalRouteValidationWorkflow,
            provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="draft")]),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )
def test_explicit_empty_required_writes_override_skips_artifact_level_required_defaults(tmp_path: Path):
    def _optionalrouterequirementworkflow_on_ask(ctx):
        return None

    class OptionalRouteRequirementWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            writes={"report": Artifact.md("report.md", required=True)},
            retry_policy=ProviderRetryPolicy(max_attempts=1),
        )
        entry = ask
        transitions = {
            ask: {
                "done": Route.to(FINISH, required_writes=[]),
            }
        }


    task_folder, run_folder = _workspace(tmp_path)
    provider = ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")])
    result = Engine(
        OptionalRouteRequirementWorkflow,
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
    assert provider.calls[0].routes["done"].required_writes == ()
    assert provider.calls[0].routes["done"].explicit_required_writes == ()
    assert provider.calls[0].route_required_writes == {
        "done": (),
        "question": (),
    }
def test_produce_verify_step_validates_selected_route_required_writes_per_route(tmp_path: Path):
    def after_assess(ctx):
        ctx.artifacts.review_report.write_text("review report\n")
        return None

    class ReviewWorkflow(SimpleWorkflow):
        assess = produce_verify_step(
            producer_prompt="Draft the assessment.",
            verifier_prompt="Review the assessment.",
            producer_writes=[Md("draft")],
            verifier_writes=[Md("review_report")],
            retry=1,
            routes={
                "approved": Route.to(FINISH, required_writes=["draft", "review_report"]),
                "rejected": Route.to(FINISH, required_writes=["review_report"]),
            },
            after_verifier=after_assess,
        )

    task_folder, run_folder = _workspace(tmp_path)

    rejected_result = Engine(
        ReviewWorkflow,
        provider=ScriptedLLMProvider(
            producer_turns=["draft text"],
            verifier_turns=[Outcome(raw_output="reject", tag="rejected")],
        ),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-1",
        run_id="run-rejected",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert rejected_result.terminal == FINISH

    with pytest.raises(ProviderExecutionError, match=r"artifact validation failed.*route 'approved'.*draft"):
        Engine(
            ReviewWorkflow,
            provider=ScriptedLLMProvider(
                producer_turns=["draft text"],
                verifier_turns=[Outcome(raw_output="approve", tag="approved")],
            ),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-1",
            run_id="run-approved",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )
def test_validation_step_valid_routes_to_default_done_and_emits_runtime_event(tmp_path: Path):
    runtime_events: list[tuple[str, dict[str, object]]] = []

    class ValidateWorkflow(SimpleWorkflow):
        draft = Artifact.md("{task_folder}/draft.md", required=True, name="draft")
        feedback = Md("validation_feedback")

        @validation_step(name="validate", feedback=feedback, requires=[draft])
        def validate(ctx):
            return ValidationResult.valid()

        entry = validate

    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "draft.md").write_text("ready\n", encoding="utf-8")

    compiled = compile_workflow(ValidateWorkflow)
    result = Engine(
        compiled,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        runtime_event_sink=lambda event_type, payload: runtime_events.append((event_type, dict(payload))),
    ).run(
        task_id="task-validate-valid",
        run_id="run-validate-valid",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert compiled.steps["validate"].writes == ("validate.validation_feedback",)
    assert runtime_events[-1][0] == "validation_step_passed"
    assert runtime_events[-1][1]["feedback_artifact"] == str(
        task_folder / "wf_validate_workflow" / "validate" / "validation_feedback.md"
    )
def test_validation_step_invalid_writes_feedback_and_routes_repair(tmp_path: Path):
    runtime_events: list[tuple[str, dict[str, object]]] = []

    class ValidateWorkflow(SimpleWorkflow):
        draft = Artifact.md("{task_folder}/draft.md", required=True, name="draft")
        feedback = Md("validation_feedback")

        @validation_step(
            name="validate",
            feedback=feedback,
            requires=[draft],
            routes={"repair": FINISH},
        )
        def validate(ctx):
            return ValidationResult.invalid(
                "Fix the draft.",
                details=("Add a summary.", "Resolve open TODOs."),
            )

        entry = validate

    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "draft.md").write_text("draft\n", encoding="utf-8")

    result = Engine(
        ValidateWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        runtime_event_sink=lambda event_type, payload: runtime_events.append((event_type, dict(payload))),
    ).run(
        task_id="task-validate-invalid",
        run_id="run-validate-invalid",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    feedback_path = task_folder / "wf_validate_workflow" / "validate" / "validation_feedback.md"

    assert result.terminal == FINISH
    assert result.last_event is not None
    assert result.last_event.tag == "repair"
    assert result.last_event.reason == "Fix the draft."
    assert result.last_event.handoff == f"Review feedback artifact: {feedback_path}"
    assert feedback_path.read_text(encoding="utf-8") == (
        "# Validation Feedback\n\n"
        "Fix the draft.\n\n"
        "## Details\n"
        "- Add a summary.\n"
        "- Resolve open TODOs.\n"
    )
    assert runtime_events[-1][0] == "validation_step_failed_repairable"
    assert runtime_events[-1][1]["feedback_artifact"] == str(feedback_path)
def test_validation_step_exception_uses_failed_route_when_configured(tmp_path: Path):
    class ValidateWorkflow(SimpleWorkflow):
        draft = Artifact.md("{task_folder}/draft.md", required=True, name="draft")
        feedback = Md("validation_feedback")

        @validation_step(name="validate", feedback=feedback, requires=[draft], failed=FAIL)
        def validate(ctx):
            raise RuntimeError("validator exploded")

        entry = validate

    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "draft.md").write_text("draft\n", encoding="utf-8")

    result = Engine(
        ValidateWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-validate-exception",
        run_id="run-validate-exception",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FAIL
    assert result.last_event is not None
    assert result.last_event.tag == "failed"
    assert result.last_event.reason == "RuntimeError: validator exploded"
