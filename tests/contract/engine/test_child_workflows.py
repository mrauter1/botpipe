from __future__ import annotations

from tests.contract.engine._shared import *

@pytest.mark.parametrize(
    ("child_terminal", "child_event", "expected_terminal", "expected_tag"),
    [
        (FINISH, Event("done"), FINISH, "done"),
        (FAIL, Event("failed", reason="child failed"), FAIL, "failed"),
        (AWAIT_INPUT, Event("question", question="Need input?"), AWAIT_INPUT, "question"),
        (AWAIT_INPUT, Event("blocked", reason="Waiting on a dependency."), AWAIT_INPUT, "blocked"),
    ],
)
def test_workflow_step_maps_child_terminals_and_writes_outputs(
    tmp_path: Path,
    child_terminal: str,
    child_event: Event,
    expected_terminal: str,
    expected_tag: str,
):
    class ChildWorkflow(SimpleWorkflow):
        note = step("Write the child note.")

    class ParentWorkflow(SimpleWorkflow):
        launch = workflow_step(
            ChildWorkflow,
            message="Run child workflow",
            writes=[Json("child_result"), Md("child_summary")],
            routes={"done": FINISH, "question": AWAIT_INPUT, "blocked": AWAIT_INPUT, "failed": FAIL},
        )

    task_folder, run_folder = _workspace(tmp_path)

    def invoke_child(workflow, *, message, parameters=None, input=None):
        child_run_root = task_folder / "child-runs" / expected_tag
        child_run_root.mkdir(parents=True, exist_ok=True)
        return ChildWorkflowResult(
            workflow_name="child_workflow",
            run_id=f"child-{expected_tag}",
            terminal=child_terminal,
            status="success" if child_terminal == FINISH else ("failed" if child_terminal == FAIL else "paused"),
            last_event=child_event,
            output_metadata={"score": 1},
            output_artifacts={"report": child_run_root / "report.md"},
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
        ParentWorkflow,
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

    workflow_root = task_folder / "wf_parent_workflow" / "launch"
    child_result_payload = json.loads((workflow_root / "child_result.json").read_text(encoding="utf-8"))
    child_summary = (workflow_root / "child_summary.md").read_text(encoding="utf-8")

    assert result.terminal == expected_terminal
    assert result.last_event is not None
    assert result.last_event.tag == expected_tag
    assert child_result_payload["terminal"] == child_terminal
    assert child_result_payload["last_event"] == child_event.tag
    assert "Child workflow: child_workflow" in child_summary
    assert "Output artifacts:" in child_summary
def test_workflow_step_rejects_child_question_without_question_payload(tmp_path: Path):
    class ChildWorkflow(SimpleWorkflow):
        note = step("Write the child note.")

    class ParentWorkflow(SimpleWorkflow):
        launch = workflow_step(ChildWorkflow, message="Run child workflow", routes={"question": AWAIT_INPUT})

    task_folder, run_folder = _workspace(tmp_path)

    def invoke_child(workflow, *, message, parameters=None, input=None):
        child_run_root = task_folder / "child-runs" / "invalid-question"
        child_run_root.mkdir(parents=True, exist_ok=True)
        return ChildWorkflowResult(
            workflow_name="child_workflow",
            run_id="child-invalid-question",
            terminal=AWAIT_INPUT,
            status="paused",
            last_event=Event("question"),
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

    with pytest.raises(
        WorkflowExecutionError,
        match=r"returned terminal 'AWAIT_INPUT'.*maps to route 'blocked'.*declared routes are: question",
    ):
        Engine(
            ParentWorkflow,
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
def test_workflow_step_maps_child_question_from_projected_event_question_not_tag_name(tmp_path: Path):
    class ChildWorkflow(SimpleWorkflow):
        note = step("Write the child note.")

    class ParentWorkflow(SimpleWorkflow):
        launch = workflow_step(ChildWorkflow, message="Run child workflow", routes={"question": AWAIT_INPUT})

    task_folder, run_folder = _workspace(tmp_path)

    def invoke_child(workflow, *, message, parameters=None, input=None):
        child_run_root = task_folder / "child-runs" / "projected-question"
        child_run_root.mkdir(parents=True, exist_ok=True)
        return ChildWorkflowResult(
            workflow_name="child_workflow",
            run_id="child-projected-question",
            terminal=AWAIT_INPUT,
            status="paused",
            last_event=Event("clarify", reason="Need a decision.", question="Approve the rollout?"),
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
        ParentWorkflow,
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

    assert result.terminal == AWAIT_INPUT
    assert result.last_event is not None
    assert result.last_event.tag == "question"
    assert result.last_event.reason == "Need a decision."
    assert result.last_event.question == "Approve the rollout?"
def test_workflow_step_requires_explicit_failed_route_for_child_fail(tmp_path: Path):
    class ChildWorkflow(SimpleWorkflow):
        note = step("Write the child note.")

    class ParentWorkflow(SimpleWorkflow):
        launch = workflow_step(ChildWorkflow, message="Run child workflow", routes={"done": FINISH})

    task_folder, run_folder = _workspace(tmp_path)

    def invoke_child(workflow, *, message, parameters=None, input=None):
        child_run_root = task_folder / "child-runs" / "missing-failed-route"
        child_run_root.mkdir(parents=True, exist_ok=True)
        return ChildWorkflowResult(
            workflow_name="child_workflow",
            run_id="child-missing-failed-route",
            terminal=FAIL,
            status="failed",
            last_event=Event("failed", reason="child failed"),
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

    with pytest.raises(
        WorkflowExecutionError,
        match=r"child workflow step 'launch' returned terminal 'FAIL'.*maps to route 'failed'.*declared routes are: done.*declare the route or change child-result mapping",
    ):
        Engine(
            ParentWorkflow,
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
def test_workflow_step_requires_explicit_blocked_route_for_child_await_without_question(tmp_path: Path):
    class ChildWorkflow(SimpleWorkflow):
        note = step("Write the child note.")

    class ParentWorkflow(SimpleWorkflow):
        launch = workflow_step(ChildWorkflow, message="Run child workflow", routes={"done": FINISH})

    task_folder, run_folder = _workspace(tmp_path)

    def invoke_child(workflow, *, message, parameters=None, input=None):
        child_run_root = task_folder / "child-runs" / "missing-blocked-route"
        child_run_root.mkdir(parents=True, exist_ok=True)
        return ChildWorkflowResult(
            workflow_name="child_workflow",
            run_id="child-missing-blocked-route",
            terminal=AWAIT_INPUT,
            status="paused",
            last_event=Event("blocked", reason="Waiting on a dependency."),
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

    with pytest.raises(
        WorkflowExecutionError,
        match=r"child workflow step 'launch' returned terminal 'AWAIT_INPUT'.*maps to route 'blocked'.*declared routes are: done.*declare the route or change child-result mapping",
    ):
        Engine(
            ParentWorkflow,
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
def test_workflow_step_message_can_forward_ctx_message_into_child_request_snapshot(tmp_path: Path) -> None:
    class ChildWorkflow(SimpleWorkflow):
        class Input(BaseModel):
            topic: str

        class State(BaseModel):
            pass

        note = step("Child note.")

    class ParentWorkflow(SimpleWorkflow):
        class Input(BaseModel):
            topic: str

        launch = workflow_step(
            ChildWorkflow,
            message="{ctx.message}",
            input={"topic": "structured-topic"},
            routes={"done": FINISH},
        )

    task_folder, run_folder = _workspace(tmp_path)
    (run_folder / "request.md").write_text("Natural-language request\n", encoding="utf-8")
    seen: dict[str, object] = {}

    def invoke_child(workflow, *, message, parameters=None, input=None):
        seen["workflow"] = workflow
        seen["message"] = message
        seen["input"] = input
        child_run_root = task_folder / "child-runs" / "ctx-child"
        child_run_folder = child_run_root / "run"
        child_run_folder.mkdir(parents=True, exist_ok=True)
        (child_run_root / "package").mkdir(parents=True, exist_ok=True)
        request_file = child_run_folder / "request.md"
        request_file.write_text(f"{message}\n", encoding="utf-8")
        child_context = Context(
            task_id="task-ctx-child",
            run_id="child-ctx",
            workflow_name="child_workflow",
            task_folder=task_folder,
            workflow_folder=child_run_root,
            run_folder=child_run_folder,
            package_folder=child_run_root / "package",
            request_file=request_file,
            task_request_file=task_folder / "request.md",
            state=workflow.State(),
            workflow_input=workflow.Input.model_validate(input),
            session_store=InMemorySessionStore(),
        )
        seen["child_payload"] = {
            "message": child_context.message,
            "request_text": child_context.request.text,
            "request_file": str(child_context.request.file),
            "task_request_file": None if child_context.request.task_file is None else str(child_context.request.task_file),
            "input_has_message": (
                child_context.input_fields is not None
                and "message" in type(child_context.input_fields).model_fields
            ),
            "input_topic": child_context.input.topic,
            "input_fields_topic": None if child_context.input_fields is None else child_context.input_fields.topic,
            "topic": child_context.input.topic,
        }
        return ChildWorkflowResult(
            workflow_name="child_workflow",
            run_id="child-ctx",
            terminal=FINISH,
            status="success",
            last_event=Event("done"),
            output_metadata={},
            output_artifacts={},
            task_folder=task_folder,
            workflow_folder=child_run_root,
            run_folder=child_run_folder,
            package_folder=child_run_root / "package",
            request_file=request_file,
            run_meta_file=child_run_folder / "run.json",
            events_file=child_run_folder / "events.jsonl",
            checkpoint_file=child_run_folder / "checkpoint.json",
            sessions_dir=child_run_folder / "sessions",
            trace_file=child_run_folder / "trace.jsonl",
            raw_dir=child_run_folder / "raw",
            parent_file=child_run_folder / "parent.json",
        )

    result = Engine(
        ParentWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-ctx-child",
        run_id="run-ctx-child",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        workflow_input=ParentWorkflow.Input(topic="alpha"),
        workflow_invoker=invoke_child,
    )

    assert result.terminal == FINISH
    assert seen["workflow"] is ChildWorkflow
    assert seen["message"] == "Natural-language request"
    assert seen["input"] == {"topic": "structured-topic"}
    assert seen["child_payload"] == {
        "message": "Natural-language request",
        "request_text": "Natural-language request",
        "request_file": str(task_folder / "child-runs" / "ctx-child" / "run" / "request.md"),
        "task_request_file": str(task_folder / "request.md"),
        "input_has_message": False,
        "input_topic": "structured-topic",
        "input_fields_topic": "structured-topic",
        "topic": "structured-topic",
    }
    assert seen["message"] != "structured-topic"
    assert (task_folder / "child-runs" / "ctx-child" / "run" / "request.md").read_text(encoding="utf-8") == (
        "Natural-language request\n"
    )
def test_workflow_step_message_renders_composite_ctx_input_bindings_before_child_invocation(tmp_path: Path) -> None:
    class ChildWorkflow(SimpleWorkflow):
        class Input(BaseModel):
            topic: str

        class State(BaseModel):
            pass

        note = step("Child note.")

    class ParentWorkflow(SimpleWorkflow):
        class Input(BaseModel):
            topic: str

        launch = workflow_step(
            ChildWorkflow,
            message="Parent request: {ctx.input.message}; topic={ctx.input.topic}",
            input={"topic": "structured-topic"},
            routes={"done": FINISH},
        )

    task_folder, run_folder = _workspace(tmp_path)
    (run_folder / "request.md").write_text("Natural-language request\n", encoding="utf-8")
    seen: dict[str, object] = {}

    def invoke_child(workflow, *, message, parameters=None, input=None):
        seen["workflow"] = workflow
        seen["message"] = message
        seen["input"] = input
        child_run_root = task_folder / "child-runs" / "ctx-child-mixed"
        child_run_folder = child_run_root / "run"
        child_run_folder.mkdir(parents=True, exist_ok=True)
        (child_run_root / "package").mkdir(parents=True, exist_ok=True)
        request_file = child_run_folder / "request.md"
        request_file.write_text(f"{message}\n", encoding="utf-8")
        child_context = Context(
            task_id="task-ctx-child-mixed",
            run_id="child-ctx-mixed",
            workflow_name="child_workflow",
            task_folder=task_folder,
            workflow_folder=child_run_root,
            run_folder=child_run_folder,
            package_folder=child_run_root / "package",
            request_file=request_file,
            task_request_file=task_folder / "request.md",
            state=workflow.State(),
            workflow_input=workflow.Input.model_validate(input),
            session_store=InMemorySessionStore(),
        )
        seen["child_payload"] = {
            "message": child_context.message,
            "request_text": child_context.request.text,
            "input_has_message": (
                child_context.input_fields is not None
                and "message" in type(child_context.input_fields).model_fields
            ),
            "input_fields_topic": None if child_context.input_fields is None else child_context.input_fields.topic,
            "topic": child_context.input.topic,
        }
        return ChildWorkflowResult(
            workflow_name="child_workflow",
            run_id="child-ctx-mixed",
            terminal=FINISH,
            status="success",
            last_event=Event("done"),
            output_metadata={},
            output_artifacts={},
            task_folder=task_folder,
            workflow_folder=child_run_root,
            run_folder=child_run_folder,
            package_folder=child_run_root / "package",
            request_file=request_file,
            run_meta_file=child_run_folder / "run.json",
            events_file=child_run_folder / "events.jsonl",
            checkpoint_file=child_run_folder / "checkpoint.json",
            sessions_dir=child_run_folder / "sessions",
            trace_file=child_run_folder / "trace.jsonl",
            raw_dir=child_run_folder / "raw",
            parent_file=child_run_folder / "parent.json",
        )

    result = Engine(
        ParentWorkflow,
        provider=ScriptedLLMProvider(),
        session_store=InMemorySessionStore(),
        checkpoint_store=InMemoryCheckpointStore(),
    ).run(
        task_id="task-ctx-child-mixed",
        run_id="run-ctx-child-mixed",
        task_folder=task_folder,
        run_folder=run_folder,
        root=tmp_path,
        workflow_input=ParentWorkflow.Input(topic="alpha"),
        workflow_invoker=invoke_child,
    )

    assert result.terminal == FINISH
    assert seen["workflow"] is ChildWorkflow
    assert seen["message"] == "Parent request: Natural-language request; topic=alpha"
    assert seen["input"] == {"topic": "structured-topic"}
    assert seen["child_payload"] == {
        "message": "Parent request: Natural-language request; topic=alpha",
        "request_text": "Parent request: Natural-language request; topic=alpha",
        "input_has_message": False,
        "input_fields_topic": "structured-topic",
        "topic": "structured-topic",
    }
    assert seen["message"] != "structured-topic"
@pytest.mark.parametrize(
    ("message_template", "expected_expression"),
    (
        ("{ctx.input.missing}", r"ctx\.input\.missing"),
        ("{ctx.state.missing}", r"ctx\.state\.missing"),
        ("{ctx.params.missing}", r"ctx\.params\.missing"),
    ),
)
def test_workflow_step_message_invalid_ctx_field_raises_workflow_execution_error(
    tmp_path: Path,
    message_template: str,
    expected_expression: str,
) -> None:
    class ChildWorkflow(SimpleWorkflow):
        note = step("Child note.")

    class ParentWorkflow(SimpleWorkflow):
        class Input(BaseModel):
            topic: str

        class Params(BaseModel):
            mode: str = "brief"

        class State(BaseModel):
            status: str = "draft"

        launch = workflow_step(
            ChildWorkflow,
            message=message_template,
            routes={"done": FINISH},
        )

    workflow_suffix = expected_expression.replace("\\", "").replace(".", "_")
    ParentWorkflow.__name__ = f"ParentWorkflow_{workflow_suffix}"
    ParentWorkflow.__qualname__ = ParentWorkflow.__name__

    task_folder, run_folder = _workspace(tmp_path)
    (run_folder / "request.md").write_text("Natural-language request\n", encoding="utf-8")

    def invoke_child(workflow, *, message, parameters=None, input=None):
        raise AssertionError("child invoker should not run when workflow-step message rendering fails")

    with pytest.raises(
        WorkflowExecutionError,
        match=rf"workflow step 'launch' message placeholder \{{{expected_expression}\}} references unknown runtime field 'missing'",
    ):
        Engine(
            ParentWorkflow,
            provider=ScriptedLLMProvider(),
            session_store=InMemorySessionStore(),
            checkpoint_store=InMemoryCheckpointStore(),
        ).run(
            task_id="task-ctx-child-invalid",
            run_id="run-ctx-child-invalid",
            task_folder=task_folder,
            run_folder=run_folder,
            root=tmp_path,
            params=ParentWorkflow.Params(mode="brief"),
            workflow_input=ParentWorkflow.Input(topic="alpha"),
            workflow_invoker=invoke_child,
        )
