from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

import autoloop_v3.workflow as strict_workflow
import autoloop_v3.workflow.primitives as strict_primitives
import workflow as root_workflow
import workflow.primitives as root_primitives
from autoloop_v3.workflow.artifacts import ArtifactHandle, ResolvedArtifacts, resolve_artifact_template
from autoloop_v3.workflow.context import Context
from autoloop_v3.workflow import Session as StrictSession
from autoloop_v3.workflow import Workflow as StrictWorkflow
from autoloop_v3.workflow.primitives import Checkpoint, Event, Outcome
from autoloop_v3.workflow.prompts import Prompt, PromptRegistry
from autoloop_v3.workflow.stores import (
    InMemoryCheckpointStore,
    InMemorySessionStore,
    SessionBinding,
    SessionSnapshot,
)
from workflow import Session as RootSession
from workflow import Workflow as RootWorkflow


class _PhaseState(BaseModel):
    id: str = "phase-1"


class _State(BaseModel):
    phase: _PhaseState = _PhaseState()


def test_event_and_outcome():
    outcome = Outcome(raw_output="raw", tag="ok", payload={"x": 1})
    assert Event(tag="ok").tag == "ok"
    assert outcome.payload == {"x": 1}


def test_root_workflow_shim_reexports_strict_surface_only():
    assert RootWorkflow is StrictWorkflow
    assert RootSession is StrictSession
    assert not hasattr(root_workflow, "SessionLifecycle")
    assert not hasattr(strict_workflow, "SessionLifecycle")
    assert not hasattr(root_primitives, "Verdict")
    assert not hasattr(strict_primitives, "Verdict")


def test_artifact_template_resolution_supports_dot_notation_and_missing_keys(tmp_path: Path):
    context = Context(
        task_id="task-1",
        run_id="run-1",
        task_folder=tmp_path / "task",
        run_folder=tmp_path / "run",
        state=_State(),
        session_store=InMemorySessionStore(),
    )

    resolved = resolve_artifact_template(
        "{task_folder}/phases/{state.phase.id}/{state.missing}/file.txt",
        context,
    )

    assert resolved == tmp_path / "task" / "phases" / "phase-1" / "file.txt"


def test_resolved_artifacts_expose_attribute_access(tmp_path: Path):
    handle = ArtifactHandle(name="draft", path=tmp_path / "draft.txt")
    handle.write_text("hello")
    artifacts = ResolvedArtifacts({"draft": handle})

    assert artifacts["draft"].read_text() == "hello"
    assert artifacts.draft.read_text() == "hello"


def test_prompt_registry_resolves_prompt_objects_and_plain_strings():
    registry = PromptRegistry({"pair.md": "pair prompt", "llm.md": "llm prompt"})

    assert registry.resolve(Prompt("pair.md")).text == "pair prompt"
    assert registry.resolve("llm.md").text == "llm prompt"


def test_in_memory_session_store_tracks_active_scope_and_restores_snapshots():
    store = InMemorySessionStore()
    alpha = store.open("phase_session", scope="phase-a")
    store.open("phase_session", scope="phase-b")

    assert store.get("phase_session") != alpha
    assert store.get("phase_session").scope == "phase-b"

    snapshot = store.snapshot()
    restored = InMemorySessionStore()
    restored.restore(snapshot)

    assert restored.get("phase_session").scope == "phase-b"
    assert restored.get("phase_session", scope="phase-a") == alpha


def test_checkpoint_store_round_trip_preserves_pending_question_and_answer():
    session_store = InMemorySessionStore()
    session_store.upsert(SessionBinding(ref_name="main", scope=None, session_id="main:global:1"))
    checkpoint = Checkpoint(
        stage="ask",
        state=_State(),
        session_bindings=session_store.snapshot(),
        pending_question="What now?",
        pending_answer="Later",
    )
    store = InMemoryCheckpointStore()
    store.save(checkpoint)

    loaded = store.load()

    assert loaded == checkpoint
    assert loaded.pending_question == "What now?"
    assert loaded.pending_answer == "Later"
    assert loaded.session_bindings.active_scopes == {"main": None}
