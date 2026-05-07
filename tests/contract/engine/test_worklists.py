from __future__ import annotations

from tests.contract.engine._shared import *

def test_scoped_step_advances_worklist_items_and_uses_item_placeholders(tmp_path: Path):
    def _advance_gate(ctx):
        if ctx.current_worklist.advance():
            return Goto("assess")
        return None

    def _scopedassessmentworkflow_on_assess(ctx):
        ctx.state = ctx.state.model_copy(update={'seen': [*ctx.state.seen, ctx.outcome.payload['item_id']], 'sessions': [*ctx.state.sessions, ctx.outcome.payload['session_id']]})
        return None

    class ScopedAssessmentWorkflow(Workflow):
        class State(BaseModel):
            seen: list[str] = Field(default_factory=list)
            sessions: list[str] = Field(default_factory=list)

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
            session=reviewer,
            scope=gates,
            writes={"report": Artifact.md("{workflow_folder}/reports/{item.dir_key}.md")},
            route_metadata={"passed": Route(summary="gate assessed")},
        )
        entry = assess
        transitions = {assess: {"passed": Route.to(FINISH, on_taken=_advance_gate)}}

    ScopedAssessmentWorkflow.assess.after = _chain_hooks(_scopedassessmentworkflow_on_assess, ScopedAssessmentWorkflow.assess.after)


    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "gates.json").write_text(
        '{"gates":[{"gate_id":"gate-a","title":"Gate A","status":"queued"},{"gate_id":"gate-b","title":"Gate B","status":"queued"}]}\n',
        encoding="utf-8",
    )

    def _turn(request):
        item = request.context.item
        assert item is not None
        request.artifacts.report.write_text(f"report for {item.id}\n")
        return Outcome(
            raw_output=f"assessed {item.id}",
            tag="passed",
            payload={"item_id": item.id, "session_id": request.session.session_id},
        )

    engine = Engine(
        ScopedAssessmentWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[_turn, _turn]),
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

    workflow_folder = task_folder / "wf_scoped_assessment_workflow"
    assert result.terminal == FINISH
    assert result.history == ("assess", "assess")
    assert result.state.seen == ["gate-a", "gate-b"]
    assert result.state.sessions[0] != result.state.sessions[1]
    assert (workflow_folder / "reports" / "gate-a.md").read_text(encoding="utf-8") == "report for gate-a\n"
    assert (workflow_folder / "reports" / "gate-b.md").read_text(encoding="utf-8") == "report for gate-b\n"
def test_selector_single_item_from_workflow_params_limits_scoped_execution(tmp_path: Path):
    def _advance_gate(ctx):
        if ctx.current_worklist.advance():
            return Goto("assess")
        return None

    def _selectedgateworkflow_on_assess(ctx):
        ctx.state = ctx.state.model_copy(update={'seen': [*ctx.state.seen, ctx.outcome.payload['item_id']]})
        return None

    class SelectedGateWorkflow(Workflow):
        class State(BaseModel):
            seen: list[str] = Field(default_factory=list)

        gates = Worklist.from_items(
            name="gate",
            items=(
                {"id": "gate-a", "title": "Gate A"},
                {"id": "gate-b", "title": "Gate B"},
            ),
            selector=Selector(item_param="gate_id", mode_param="mode", allowed_modes=("all", "single")),
        )
        assess = PromptStep(
            name="assess",
            producer="assess.md",
            scope=gates,
            route_metadata={"passed": Route(summary="selected gate assessed")},
        )
        entry = assess
        transitions = {assess: {"passed": Route.to(FINISH, on_taken=_advance_gate)}}

    SelectedGateWorkflow.assess.after = _chain_hooks(_selectedgateworkflow_on_assess, SelectedGateWorkflow.assess.after)


    def _turn(request):
        item = request.context.item
        assert item is not None
        return Outcome(raw_output="ok", tag="passed", payload={"item_id": item.id})

    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        SelectedGateWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[_turn]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    result = engine.run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        workflow_params={"gate_id": "gate-b", "mode": "single"},
    )

    assert result.terminal == FINISH
    assert result.history == ("assess",)
    assert result.state.seen == ["gate-b"]
def test_prompt_runtime_lazily_renders_item_and_worklist_placeholders(tmp_path: Path):
    class PromptRenderWorkflow(Workflow):
        class State(BaseModel):
            pass

        gates = Worklist.from_items(
            name="gate",
            items=({"id": "alpha", "title": "Alpha", "payload": {"foo": "bar"}},),
        )
        assess = PromptStep(
            name="assess",
            producer=Prompt.inline(
                "Inspect {item.id} / {item.payload.foo} / {worklist.gate.current.id} / {worklist.gate.current.payload.foo}."
            ),
            scope=gates,
        )
        entry = assess
        transitions = {assess: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)

    def _turn(request):
        assert request.prompt.text == "Inspect alpha / bar / alpha / bar."
        return Outcome(raw_output="ok", tag="done")

    engine = Engine(
        PromptRenderWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[_turn]),
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
def test_prompt_runtime_renders_item_state_placeholders(tmp_path: Path):
    class GateState(BaseModel):
        severity: str = "medium"

    class ItemStatePromptWorkflow(Workflow):
        class State(BaseModel):
            pass

        gates = Worklist.from_items(
            name="gate",
            items=({"id": "alpha", "title": "Alpha", "status": "pending"},),
            status="status",
            item_state=GateState,
        )
        assess = PromptStep(
            name="assess",
            producer=Prompt.inline("Inspect {item.state.status} / {item.state.severity}."),
            scope=gates,
        )
        entry = assess
        transitions = {assess: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)

    def _turn(request):
        assert request.prompt.text == "Inspect pending / medium."
        return Outcome(raw_output="ok", tag="done")

    result = Engine(
        ItemStatePromptWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[_turn]),
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
def test_prompt_runtime_reports_missing_item_state_field_with_placeholder_context(tmp_path: Path):
    class GateState(BaseModel):
        severity: str = "medium"

    class MissingItemStateFieldWorkflow(Workflow):
        class State(BaseModel):
            pass

        gates = Worklist.from_items(
            name="gate",
            items=({"id": "alpha", "title": "Alpha"},),
            item_state=GateState,
        )
        assess = PromptStep(
            name="assess",
            producer=Prompt.inline("Inspect {item.state.priority}."),
            scope=gates,
        )
        entry = assess
        transitions = {assess: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        MissingItemStateFieldWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    with pytest.raises(
        WorkflowExecutionError,
        match=r"prompt placeholder on step 'assess' \{item\.state\.priority\} references unknown runtime field 'priority' on worklist 'gate'",
    ):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )
def test_prompt_runtime_reports_missing_worklist_current_payload_path_with_placeholder_context(tmp_path: Path):
    class MissingWorklistPayloadPromptWorkflow(Workflow):
        class State(BaseModel):
            pass

        gates = Worklist.from_items(
            name="gate",
            items=({"id": "alpha", "title": "Alpha", "payload": {}},),
        )
        assess = PromptStep(
            name="assess",
            producer=Prompt.inline("Inspect {worklist.gate.current.payload.foo}."),
            scope=gates,
        )
        entry = assess
        transitions = {assess: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        MissingWorklistPayloadPromptWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    with pytest.raises(
        WorkflowExecutionError,
        match=r"prompt placeholder on step 'assess' \{worklist\.gate\.current\.payload\.foo\} references missing payload path 'foo' on worklist 'gate'",
    ):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )
def test_prompt_runtime_reports_missing_current_item_with_placeholder_context(tmp_path: Path):
    class MissingCurrentItemPromptWorkflow(Workflow):
        class State(BaseModel):
            pass

        gates = Worklist.from_items(name="gate", items=())
        assess = PromptStep(
            name="assess",
            producer=Prompt.inline("Inspect {worklist.gate.current.id}."),
        )
        entry = assess
        transitions = {assess: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        MissingCurrentItemPromptWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    with pytest.raises(
        WorkflowExecutionError,
        match=r"prompt placeholder on step 'assess' \{worklist\.gate\.current\.id\} requires a current item on worklist 'gate'",
    ):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )
def test_prompt_runtime_reports_missing_worklist_source_with_placeholder_context(tmp_path: Path):
    class MissingWorklistSourcePromptWorkflow(Workflow):
        class State(BaseModel):
            pass

        gate_board = Artifact.json("{task_folder}/gates.json", required=True)
        gates = Worklist.from_artifact(
            name="gate",
            artifact=gate_board,
            collection="gates",
            item_id="gate_id",
            title="title",
        )
        assess = PromptStep(
            name="assess",
            producer=Prompt.inline("Inspect {worklist.gate.current.id}."),
        )
        entry = assess
        transitions = {assess: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        MissingWorklistSourcePromptWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    with pytest.raises(
        WorkflowExecutionError,
        match=r"prompt placeholder on step 'assess' \{worklist\.gate\.current\.id\} could not load worklist 'gate'",
    ):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )
def test_unused_artifact_backed_worklist_does_not_load_on_non_scoped_path(tmp_path: Path):
    def _finish(_ctx):
        return Event("done")

    class UnusedArtifactWorklistWorkflow(Workflow):
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
        finalize = PythonStep(name="finalize", handler=_finish)
        entry = finalize
        transitions = {finalize: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        UnusedArtifactWorklistWorkflow,
        provider=ScriptedLLMProvider(),
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
    assert not (task_folder / "gates.json").exists()
def test_artifact_backed_worklist_materializes_after_runtime_creates_source(tmp_path: Path):
    runtime_events: list[tuple[str, dict[str, object]]] = []

    def _create_gates(ctx):
        ctx.write(
            ctx.task_folder / "gates.json",
            '{"gates":[{"gate_id":"gate-a","title":"Gate A","status":"queued"}]}\n',
        )
        return Event("done")

    class DeferredArtifactWorklistWorkflow(Workflow):
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
        create_gates = PythonStep(name="create_gates", handler=_create_gates)
        assess = PromptStep(
            name="assess",
            producer="assess.md",
            scope=gates,
            route_metadata={"passed": Route(summary="gate assessed")},
        )
        entry = create_gates
        transitions = {
            create_gates: {"done": assess},
            assess: {"passed": FINISH},
        }

    def _turn(request):
        item = request.context.item
        assert item is not None
        assert item.id == "gate-a"
        return Outcome(raw_output="ok", tag="passed")

    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        DeferredArtifactWorklistWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[_turn]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        runtime_event_sink=lambda event_type, payload: runtime_events.append((event_type, dict(payload))),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    resolved_events = [payload for event_type, payload in runtime_events if event_type == "worklist_selection_resolved"]
    assert result.terminal == FINISH
    assert len(resolved_events) == 1
    assert resolved_events[0]["worklist_name"] == "gate"
    assert resolved_events[0]["current_item_id"] == "gate-a"
    assert resolved_events[0]["current_index"] == 0
    assert resolved_events[0]["lazy"] is True
    assert resolved_events[0]["source"].startswith("artifact:")
def test_non_scoped_explicit_worklist_access_emits_resolution_event_for_only_requested_worklist(tmp_path: Path):
    runtime_events: list[tuple[str, dict[str, object]]] = []

    def _inspect(ctx):
        selection = ctx.selection("gate")
        assert selection.current is not None
        assert selection.current.id == "gate-a"
        assert set(ctx._selections) == {"gate"}
        return Event("done")

    class ExplicitSelectionWorkflow(Workflow):
        class State(BaseModel):
            pass

        gates = Worklist.from_items(
            name="gate",
            items=({"id": "gate-a", "title": "Gate A"},),
        )
        reviews = Worklist.from_items(
            name="review",
            items=({"id": "review-a", "title": "Review A"},),
        )
        inspect = PythonStep(name="inspect", handler=_inspect)
        entry = inspect
        transitions = {inspect: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        ExplicitSelectionWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        runtime_event_sink=lambda event_type, payload: runtime_events.append((event_type, dict(payload))),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    resolved_events = [payload for event_type, payload in runtime_events if event_type == "worklist_selection_resolved"]
    assert result.terminal == FINISH
    assert len(resolved_events) == 1
    assert resolved_events[0]["step_name"] == "inspect"
    assert resolved_events[0]["worklist_name"] == "gate"
    assert resolved_events[0]["current_item_id"] == "gate-a"
    assert resolved_events[0]["current_index"] == 0
    assert resolved_events[0]["lazy"] is True
    assert resolved_events[0]["source"] == "static"
def test_non_scoped_current_access_emits_resolution_event_for_only_requested_worklist(tmp_path: Path):
    runtime_events: list[tuple[str, dict[str, object]]] = []

    def _inspect(ctx):
        current = ctx.current("gate")
        assert current is not None
        assert current.id == "gate-a"
        assert set(ctx._selections) == {"gate"}
        return Event("done")

    class ExplicitCurrentWorkflow(Workflow):
        class State(BaseModel):
            pass

        gates = Worklist.from_items(
            name="gate",
            items=({"id": "gate-a", "title": "Gate A"},),
        )
        reviews = Worklist.from_items(
            name="review",
            items=({"id": "review-a", "title": "Review A"},),
        )
        inspect = PythonStep(name="inspect", handler=_inspect)
        entry = inspect
        transitions = {inspect: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        ExplicitCurrentWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
        runtime_event_sink=lambda event_type, payload: runtime_events.append((event_type, dict(payload))),
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    resolved_events = [payload for event_type, payload in runtime_events if event_type == "worklist_selection_resolved"]
    assert result.terminal == FINISH
    assert len(resolved_events) == 1
    assert resolved_events[0]["step_name"] == "inspect"
    assert resolved_events[0]["worklist_name"] == "gate"
    assert resolved_events[0]["current_item_id"] == "gate-a"
    assert resolved_events[0]["current_index"] == 0
    assert resolved_events[0]["lazy"] is True
    assert resolved_events[0]["source"] == "static"
def test_missing_artifact_backed_worklist_fails_at_first_scoped_use(tmp_path: Path):
    class MissingArtifactWorklistWorkflow(Workflow):
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
        assess = PromptStep(name="assess", producer="assess.md", scope=gates)
        entry = assess
        transitions = {assess: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    engine = Engine(
        MissingArtifactWorklistWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    with pytest.raises(
        WorkflowExecutionError,
        match="worklist 'gate' could not resolve selection from artifact source",
    ):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )
def test_artifact_backed_worklist_scaffold_policy_creates_source_at_first_scoped_use(tmp_path: Path):
    class ScaffoldArtifactWorklistWorkflow(Workflow):
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
            missing="scaffold",
        )
        assess = PromptStep(
            name="assess",
            producer="assess.md",
            scope=gates,
            route_metadata={"done": Route(summary="scaffold checked")},
        )
        entry = assess
        transitions = {assess: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        ScaffoldArtifactWorklistWorkflow,
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
    assert json.loads((task_folder / "gates.json").read_text(encoding="utf-8")) == {"gates": []}
def test_worklist_source_ensure_can_scaffold_backing_data_at_first_use(tmp_path: Path):
    class _ScaffoldSource:
        mutable = False
        artifact_backed = False

        def __init__(self, path: Path) -> None:
            self.path = path

        def ensure(self, ctx) -> None:
            if self.path.exists():
                return
            self.path.write_text(
                json.dumps(
                    [{"id": "gate-a", "title": "Gate A"}],
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

        def load(self, ctx) -> tuple[WorkItem[dict[str, str]], ...]:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return tuple(
                WorkItem(
                    id=str(entry["id"]),
                    title=str(entry["title"]),
                    payload=dict(entry),
                    dir_key=str(entry["id"]),
                )
                for entry in payload
            )

        def save(self, ctx, items) -> None:
            return None

        def validate(self, ctx, items) -> str | None:
            return None

    source_path = tmp_path / "scaffolded-gates.json"

    class ScaffoldedWorklistWorkflow(Workflow):
        class State(BaseModel):
            pass

        gates = Worklist(name="gate", source=_ScaffoldSource(source_path))
        assess = PromptStep(name="assess", producer="assess.md", scope=gates)
        entry = assess
        transitions = {assess: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        ScaffoldedWorklistWorkflow,
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
    assert source_path.exists()
def test_resume_does_not_reload_unused_checkpointed_worklists(tmp_path: Path):
    class _EnsureSource:
        mutable = False
        artifact_backed = False

        def __init__(self, path: Path) -> None:
            self.path = path

        def ensure(self, ctx) -> None:
            if self.path.exists():
                return
            self.path.write_text(
                json.dumps(
                    [{"id": "gate-a", "title": "Gate A"}],
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

        def load(self, ctx) -> tuple[WorkItem[dict[str, str]], ...]:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return tuple(
                WorkItem(
                    id=str(entry["id"]),
                    title=str(entry["title"]),
                    payload=dict(entry),
                    dir_key=str(entry["id"]),
                )
                for entry in payload
            )

        def save(self, ctx, items) -> None:
            return None

        def validate(self, ctx, items) -> str | None:
            return None

    def _pause(ctx):
        if ctx.input_response is None:
            return RequestInput("Continue?")
        return Event("done")

    source_path = tmp_path / "resume-gates.json"

    class ResumeEnsureWorkflow(Workflow):
        class State(BaseModel):
            pass

        gates = Worklist(name="gate", source=_EnsureSource(source_path))
        assess = PromptStep(name="assess", producer="assess.md", scope=gates)
        pause = PythonStep(name="pause", handler=_pause)
        entry = assess
        transitions = {
            assess: {"done": pause},
            pause: {"done": FINISH},
        }

    checkpoint_store = InMemoryCheckpointStore()
    task_folder, run_folder = _workspace(tmp_path)
    paused = Engine(
        ResumeEnsureWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert paused.terminal == AWAIT_INPUT
    source_path.unlink()

    resumed = Engine(
        ResumeEnsureWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    ).resume(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        answer="yes",
    )

    assert resumed.terminal == FINISH
    assert not source_path.exists()
def test_resume_reloads_checkpointed_worklist_on_first_access_only(tmp_path: Path):
    class _EnsureSource:
        mutable = False
        artifact_backed = False

        def __init__(self, path: Path) -> None:
            self.path = path

        def ensure(self, ctx) -> None:
            if self.path.exists():
                return
            self.path.write_text(
                json.dumps(
                    [{"id": "gate-a", "title": "Gate A"}],
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

        def load(self, ctx) -> tuple[WorkItem[dict[str, str]], ...]:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return tuple(
                WorkItem(
                    id=str(entry["id"]),
                    title=str(entry["title"]),
                    payload=dict(entry),
                    dir_key=str(entry["id"]),
                )
                for entry in payload
            )

        def save(self, ctx, items) -> None:
            return None

        def validate(self, ctx, items) -> str | None:
            return None

    def _pause(ctx):
        if ctx.input_response is None:
            return RequestInput("Continue?")
        return Event("done")

    source_path = tmp_path / "resume-lazy-gates.json"

    class ResumeEnsureOnAccessWorkflow(Workflow):
        class State(BaseModel):
            pass

        gates = Worklist(name="gate", source=_EnsureSource(source_path))
        assess = PromptStep(name="assess", producer="assess.md", scope=gates)
        pause = PythonStep(name="pause", handler=_pause)
        entry = assess
        transitions = {
            assess: {"done": pause},
            pause: {"done": assess},
        }

    checkpoint_store = InMemoryCheckpointStore()
    task_folder, run_folder = _workspace(tmp_path)
    paused = Engine(
        ResumeEnsureOnAccessWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[Outcome(raw_output="ok", tag="done")]),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert paused.terminal == AWAIT_INPUT
    source_path.unlink()

    def _turn(request):
        assert source_path.exists()
        item = request.context.item
        assert item is not None
        assert item.id == "gate-a"
        return Outcome(raw_output="ok", tag="done")

    resumed = Engine(
        ResumeEnsureOnAccessWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[_turn]),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    ).resume(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        answer="yes",
    )

    assert resumed.terminal == AWAIT_INPUT
    assert source_path.exists()
def test_worklist_refresh_uses_source_ensure_when_backing_data_is_missing(tmp_path: Path):
    class _EnsureSource:
        mutable = False
        artifact_backed = False

        def __init__(self, path: Path) -> None:
            self.path = path

        def ensure(self, ctx) -> None:
            if self.path.exists():
                return
            self.path.write_text(
                json.dumps(
                    [{"id": "gate-a", "title": "Gate A"}],
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

        def load(self, ctx) -> tuple[WorkItem[dict[str, str]], ...]:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return tuple(
                WorkItem(
                    id=str(entry["id"]),
                    title=str(entry["title"]),
                    payload=dict(entry),
                    dir_key=str(entry["id"]),
                )
                for entry in payload
            )

        def save(self, ctx, items) -> None:
            return None

        def validate(self, ctx, items) -> str | None:
            return None

    source_path = tmp_path / "refresh-gates.json"

    def _refresh(ctx):
        source_path.unlink()
        selection = ctx.worklist("gate").refresh()
        assert selection.current is not None
        assert selection.current.id == "gate-a"
        assert source_path.exists()
        return Event("done")

    class RefreshEnsureWorkflow(Workflow):
        class State(BaseModel):
            pass

        gates = Worklist(name="gate", source=_EnsureSource(source_path))
        assess = PromptStep(name="assess", producer="assess.md", scope=gates)
        refresh = PythonStep(name="refresh", handler=_refresh)
        entry = assess
        transitions = {
            assess: {"done": refresh},
            refresh: {"done": FINISH},
        }

    task_folder, run_folder = _workspace(tmp_path)
    result = Engine(
        RefreshEnsureWorkflow,
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
    assert source_path.exists()
def test_resume_restores_materialized_worklists_and_lazily_materializes_unused_ones(tmp_path: Path):
    def _pause(ctx):
        if ctx.input_response is None:
            return RequestInput("Continue?")
        return Event("done")

    def _create_gates(ctx):
        ctx.write(
            ctx.task_folder / "gates.json",
            '{"gates":[{"gate_id":"gate-a","title":"Gate A","status":"queued"}]}\n',
        )
        return Event("done")

    class ResumeLazyWorklistWorkflow(Workflow):
        class State(BaseModel):
            seen: list[str] = Field(default_factory=list)

        articles = Worklist.from_param("articles")
        gate_board = Artifact.json("{task_folder}/gates.json", required=True)
        gates = Worklist.from_artifact(
            name="gate",
            artifact=gate_board,
            collection="gates",
            item_id="gate_id",
            title="title",
            status="status",
        )
        review = PromptStep(
            name="review",
            producer="review.md",
            scope=articles,
            route_metadata={"passed": Route(summary="article reviewed")},
        )
        pause = PythonStep(name="pause", handler=_pause)
        create_gates = PythonStep(name="create_gates", handler=_create_gates)
        assess = PromptStep(
            name="assess",
            producer="assess.md",
            scope=gates,
            route_metadata={"passed": Route(summary="gate assessed")},
        )
        entry = review
        transitions = {
            review: {"passed": pause},
            pause: {"done": create_gates},
            create_gates: {"done": assess},
            assess: {"passed": FINISH},
        }

    checkpoint_store = InMemoryCheckpointStore()
    task_folder, run_folder = _workspace(tmp_path)
    initial_provider = ScriptedLLMProvider(
        llm_turns=[lambda request: Outcome(raw_output="ok", tag="passed", payload={"item_id": request.context.item.id})]
    )
    paused = Engine(
        ResumeLazyWorklistWorkflow,
        provider=initial_provider,
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    ).run(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        workflow_params={"articles": [{"id": "article-a", "title": "Article A"}]},
    )

    checkpoint = checkpoint_store.load()
    assert paused.terminal == AWAIT_INPUT
    assert checkpoint is not None
    assert checkpoint.worklist_selections is not None
    assert set(checkpoint.worklist_selections) == {"articles"}

    resumed = Engine(
        ResumeLazyWorklistWorkflow,
        provider=ScriptedLLMProvider(
            llm_turns=[lambda request: Outcome(raw_output="ok", tag="passed", payload={"item_id": request.context.item.id})]
        ),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    ).resume(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        workflow_params={"articles": [{"id": "article-a", "title": "Article A"}]},
        answer="yes",
    )

    assert resumed.terminal == FINISH
    assert (task_folder / "gates.json").exists()
def test_scoped_item_state_and_step_item_state_resume_from_checkpoint(tmp_path: Path):
    class ArticleItemState(BaseModel):
        attempts: int = 0

    class ReviewItemState(BaseModel):
        attempts: int = 0
        note: str | None = None

    def _advance_article(ctx):
        if ctx.current_worklist.advance():
            return Goto("review")
        return None

    def _scopedstateresumeworkflow_on_review(ctx):
        next_visits = ctx.state.resumed_visits
        if ctx.outcome.payload['item_id'] == 'beta':
            next_visits = int(ctx.outcome.payload['visits'])
        ctx.state = ctx.state.model_copy(update={'seen': [*ctx.state.seen, str(ctx.outcome.payload['item_id'])], 'resumed_visits': next_visits})
        return None

    class ScopedStateResumeWorkflow(Workflow):
        class State(BaseModel):
            seen: list[str] = Field(default_factory=list)
            resumed_visits: int | None = None

        articles = Worklist.from_param(
            "articles",
            status="status",
            item_state=ArticleItemState,
        )
        review = PromptStep(
            name="review",
            producer="review.md",
            scope=articles,
            item_state=ReviewItemState,
            route_metadata={"passed": Route(summary="article reviewed")},
        )
        entry = review
        transitions = {review: {"passed": Route.to(FINISH, on_taken=_advance_article)}}

    ScopedStateResumeWorkflow.review.after = _chain_hooks(_scopedstateresumeworkflow_on_review, ScopedStateResumeWorkflow.review.after)


    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_store = InMemoryCheckpointStore()

    def _alpha_turn(request):
        item = request.context.item
        assert item is not None
        assert item.id == "alpha"
        assert request.context.item_state.status == "pending"
        assert request.context.item_state.last_step == "review"
        assert request.context.step_item_state.visits == 1
        request.context.current_worklist.set_current_status("alpha-complete")
        request.context.item_state.attempts += 1
        request.context.step_item_state.attempts += 1
        request.context.step_item_state.note = "alpha"
        return Outcome(raw_output="ok", tag="passed", payload={"item_id": item.id, "visits": request.context.step_item_state.visits})

    def _beta_fail_turn(request):
        item = request.context.item
        assert item is not None
        assert item.id == "beta"
        assert request.context.item_state.status == "pending"
        assert request.context.item_state.last_step == "review"
        assert request.context.step_item_state.visits == 1
        request.context.current_worklist.set_current_status("beta-started")
        request.context.item_state.attempts += 1
        request.context.step_item_state.attempts += 1
        request.context.step_item_state.note = "checkpointed"
        raise RuntimeError("checkpoint me")

    failing_engine = Engine(
        ScopedStateResumeWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[_alpha_turn, _beta_fail_turn]),
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
            workflow_params={
                "articles": [
                    {"id": "alpha", "title": "Alpha", "status": "pending"},
                    {"id": "beta", "title": "Beta", "status": "pending"},
                ]
            },
        )

    checkpoint = checkpoint_store.load()
    assert checkpoint is not None
    assert checkpoint.item_states is not None
    assert len(checkpoint.item_states) == 2
    assert any(payload["status"] == "beta-started" and payload["attempts"] == 1 for payload in checkpoint.item_states.values())
    assert checkpoint.step_item_states is not None
    assert "review" in checkpoint.step_item_states
    assert len(checkpoint.step_item_states["review"]) == 2
    assert any(
        payload["note"] == "checkpointed" and payload["attempts"] == 1 and payload["visits"] == 1 and payload["last_route"] is None
        for payload in checkpoint.step_item_states["review"].values()
    )

    def _beta_resume_turn(request):
        item = request.context.item
        assert item is not None
        assert item.id == "beta"
        assert request.context.item_state.status == "beta-started"
        assert request.context.item_state.last_step == "review"
        assert request.context.item_state.attempts == 1
        assert request.context.step_item_state.attempts == 1
        assert request.context.step_item_state.note == "checkpointed"
        assert request.context.step_item_state.visits == 2
        request.context.current_worklist.set_current_status("beta-complete")
        request.context.item_state.attempts += 1
        request.context.step_item_state.attempts += 1
        return Outcome(raw_output="ok", tag="passed", payload={"item_id": item.id, "visits": request.context.step_item_state.visits})

    resumed_engine = Engine(
        ScopedStateResumeWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[_beta_resume_turn]),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    )

    result = resumed_engine.resume(
        task_id="task-1",
        run_id="run-1",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        workflow_params={
            "articles": [
                {"id": "alpha", "title": "Alpha", "status": "pending"},
                {"id": "beta", "title": "Beta", "status": "pending"},
            ]
        },
    )

    assert result.terminal == FINISH
    assert result.state.seen == ["alpha", "beta"]
    assert result.state.resumed_visits == 2
def test_resume_ignores_legacy_null_worklist_selection_payloads(tmp_path: Path):
    from autoloop.runtime.stores.filesystem import FilesystemCheckpointStore

    class LegacyNullSelectionWorkflow(Workflow):
        class State(BaseModel):
            resumed: bool = False

        gate_board = Artifact.json("{task_folder}/gates.json", required=True)
        gates = Worklist.from_artifact(
            name="gate",
            artifact=gate_board,
            collection="gates",
            item_id="gate_id",
            title="title",
            status="status",
        )

        @staticmethod
        def _publish(ctx):
            assert ctx._selection_snapshots == {}
            assert ctx._selections == {}
            ctx.state = ctx.state.model_copy(update={"resumed": True})
            return Event("done")

        publish = PythonStep(name="publish", handler=_publish)
        entry = publish
        transitions = {publish: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    checkpoint_path = run_folder / "checkpoint.json"
    checkpoint_store = FilesystemCheckpointStore(checkpoint_path, LegacyNullSelectionWorkflow.State)
    checkpoint_store.save(
        Checkpoint(
            stage="publish",
            state=LegacyNullSelectionWorkflow.State(),
            session_bindings=SessionSnapshot(bindings=(), active_keys_by_slot={}),
        )
    )

    payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    payload["worklist_selections"] = {"gate": None}
    checkpoint_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    result = Engine(
        LegacyNullSelectionWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=checkpoint_store,
    ).resume(
        task_id="task-legacy",
        run_id="run-legacy",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.state.resumed is True
    assert not (task_folder / "gates.json").exists()
def test_artifact_backed_worklist_duplicate_ids_fail_before_scoped_execution(tmp_path: Path):
    def _advance_gate(ctx):
        if ctx.current_worklist.advance():
            return Goto("assess")
        return None

    def _duplicategateworkflow_on_assess(ctx):
        ctx.state = ctx.state.model_copy(update={'seen': ctx.state.seen + 1})
        return None

    class DuplicateGateWorkflow(Workflow):
        class State(BaseModel):
            seen: int = 0

        gate_board = Artifact.json("{task_folder}/gates.json", required=True)
        gates = Worklist.from_artifact(
            name="gate",
            artifact=gate_board,
            collection="gates",
            item_id="gate_id",
            title="title",
            status="status",
        )
        assess = PromptStep(
            name="assess",
            producer="assess.md",
            scope=gates,
            route_metadata={"passed": Route(summary="gate assessed")},
        )
        entry = assess
        transitions = {assess: {"passed": Route.to(FINISH, on_taken=_advance_gate)}}

    DuplicateGateWorkflow.assess.after = _chain_hooks(_duplicategateworkflow_on_assess, DuplicateGateWorkflow.assess.after)


    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "gates.json").write_text(
        '{"gates":[{"gate_id":"dup","title":"Gate A","status":"queued"},{"gate_id":"dup","title":"Gate B","status":"queued"}]}\n',
        encoding="utf-8",
    )
    engine = Engine(
        DuplicateGateWorkflow,
        provider=ScriptedLLMProvider(llm_turns=[]),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    )

    with pytest.raises(WorkflowExecutionError, match="duplicate item id"):
        engine.run(
            task_id="task-1",
            run_id="run-1",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )
def test_python_step_effect_refresh_reloads_worklist_source(tmp_path: Path):
    def _refreshworkflow_on_start(ctx):
        assert ctx.current("gate") is not None
        assert ctx.current("gate").status == "queued"
        payload = ctx.read_json(ctx.task_folder / "gates.json")
        assert isinstance(payload, dict)
        payload["gates"][0]["status"] = "ready"
        ctx.write_json(ctx.task_folder / "gates.json", payload)
        return Effects(
            worklists=(WorklistEffect(worklist="gate", refresh=True),),
            event="done",
        )

    def _refreshworkflow_on_finish(ctx):
        assert ctx.current("gate") is not None
        assert ctx.current("gate").status == "ready"
        return Event("done")

    class RefreshWorkflow(Workflow):
        board = Artifact.json("{task_folder}/gates.json", required=True)
        gates = Worklist.from_artifact(
            name="gate",
            artifact=board,
            collection="gates",
            item_id="gate_id",
            title="title",
            status="status",
        )
        start = PythonStep(name="start", handler=_refreshworkflow_on_start)
        finish = PythonStep(name="finish", handler=_refreshworkflow_on_finish)
        entry = start
        transitions = {
            start: {"done": finish},
            finish: {"done": FINISH},
        }

    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "gates.json").write_text(
        '{"gates":[{"gate_id":"alpha","title":"Alpha","status":"queued"}]}\n',
        encoding="utf-8",
    )

    result = Engine(
        RefreshWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-refresh",
        run_id="run-refresh",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.history == ("start", "finish")
def test_python_step_may_return_direct_worklist_effect(tmp_path: Path):
    def _directeffectworkflow_on_assess(ctx):
        assert ctx.current("gate") is not None
        return WorklistEffect.complete_and_advance(worklist="gate", exhausted="done")

    class DirectEffectWorkflow(Workflow):
        board = Artifact.json("{task_folder}/gates.json", required=True)
        gates = Worklist.from_artifact(
            name="gate",
            artifact=board,
            collection="gates",
            item_id="gate_id",
            title="title",
            status="status",
        )
        assess = PythonStep(name="assess", handler=_directeffectworkflow_on_assess)
        entry = assess
        transitions = {assess: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)
    (task_folder / "gates.json").write_text(
        '{"gates":[{"gate_id":"alpha","title":"Alpha","status":"queued"}]}\n',
        encoding="utf-8",
    )

    result = Engine(
        DirectEffectWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-direct-effect",
        run_id="run-direct-effect",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    payload = json.loads((task_folder / "gates.json").read_text(encoding="utf-8"))

    assert result.terminal == FINISH
    assert result.last_event is not None
    assert result.last_event.tag == "done"
    assert payload["gates"][0]["status"] == "completed"
def test_effect_without_active_worklist_fails_clearly(tmp_path: Path):
    def _invalideffectsworkflow_on_start(ctx):
        return Effects.advance()

    class InvalidEffectsWorkflow(Workflow):
        start = PythonStep(name="start", handler=_invalideffectsworkflow_on_start)
        entry = start
        transitions = {start: {"done": FINISH}}

    task_folder, run_folder = _workspace(tmp_path)

    with pytest.raises(WorkflowExecutionError, match="without an active worklist"):
        Engine(
            InvalidEffectsWorkflow,
            provider=ScriptedLLMProvider(),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-invalid-effects",
            run_id="run-invalid-effects",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
        )
def test_python_step_effect_then_routes_without_worklist_mutation(tmp_path: Path):
    def _theneffectsworkflow_on_start(ctx):
        return Effects.then("next")

    def _theneffectsworkflow_on_finish(ctx):
        return Event("done")

    class ThenEffectsWorkflow(Workflow):
        start = PythonStep(name="start", handler=_theneffectsworkflow_on_start)
        finish = PythonStep(name="finish", handler=_theneffectsworkflow_on_finish)
        entry = start
        transitions = {
            start: {"next": finish},
            finish: {"done": FINISH},
        }

    task_folder, run_folder = _workspace(tmp_path)

    result = Engine(
        ThenEffectsWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-then-effects",
        run_id="run-then-effects",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
    )

    assert result.terminal == FINISH
    assert result.history == ("start", "finish")
    assert result.last_event is not None
    assert result.last_event.tag == "done"
