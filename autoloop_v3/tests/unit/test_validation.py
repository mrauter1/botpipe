from __future__ import annotations

import pytest
from pydantic import BaseModel

from autoloop_v3.workflow import Artifact, LLMStep, PairStep, Session, SystemStep, SUCCESS, Workflow
from autoloop_v3.workflow.errors import WorkflowValidationError
from autoloop_v3.workflow.primitives import Event


def test_validation_rejects_missing_state():
    with pytest.raises(WorkflowValidationError, match="State"):

        class MissingStateWorkflow(Workflow):
            begin = SystemStep(name="begin")
            entry = begin
            transitions = {begin: {"done": SUCCESS}}

            @staticmethod
            def on_begin(state):
                return state, Event("done")


def test_validation_rejects_missing_entry():
    with pytest.raises(WorkflowValidationError, match="entry"):

        class MissingEntryWorkflow(Workflow):
            class State(BaseModel):
                pass

            begin = SystemStep(name="begin")
            transitions = {begin: {"done": SUCCESS}}

            @staticmethod
            def on_begin(state):
                return state, Event("done")


def test_validation_rejects_missing_system_handler():
    with pytest.raises(WorkflowValidationError, match="missing handler"):

        class MissingSystemHandlerWorkflow(Workflow):
            class State(BaseModel):
                pass

            begin = SystemStep(name="begin")
            entry = begin
            transitions = {begin: {"done": SUCCESS}}


def test_validation_rejects_orphan_handlers():
    with pytest.raises(WorkflowValidationError, match="orphan handler"):

        class OrphanHandlerWorkflow(Workflow):
            class State(BaseModel):
                pass

            begin = SystemStep(name="begin")
            entry = begin
            transitions = {begin: {"done": SUCCESS}}

            @staticmethod
            def on_begin(state, ctx):
                return state, Event("done")

            @staticmethod
            def on_missing(state, outcome):
                return state


def test_validation_rejects_invalid_destinations():
    with pytest.raises(WorkflowValidationError, match="invalid transition destination"):

        class InvalidDestinationWorkflow(Workflow):
            class State(BaseModel):
                pass

            begin = SystemStep(name="begin")
            entry = begin
            transitions = {begin: {"done": "UNKNOWN"}}

            @staticmethod
            def on_begin(state, ctx):
                return state, Event("done")


def test_validation_rejects_duplicate_artifact_names():
    with pytest.raises(WorkflowValidationError, match="duplicate artifact name"):

        class DuplicateArtifactWorkflow(Workflow):
            class State(BaseModel):
                pass

            one = Artifact("one.txt", name="dup")
            two = Artifact("two.txt", name="dup")
            begin = SystemStep(name="begin")
            entry = begin
            transitions = {begin: {"done": SUCCESS}}

            @staticmethod
            def on_begin(state, ctx):
                return state, Event("done")


def test_validation_rejects_future_required_artifacts():
    future_artifact = Artifact("produced.txt", name="produced")

    with pytest.raises(WorkflowValidationError, match="before it is produced"):

        class FutureArtifactWorkflow(Workflow):
            class State(BaseModel):
                pass

            first = LLMStep(name="first", producer="first.md", requires=[future_artifact])
            second = LLMStep(name="second", producer="second.md", produces={"produced": future_artifact})
            entry = first
            transitions = {first: {"next": second}, second: {"done": SUCCESS}}

            @staticmethod
            def on_first(state, outcome):
                return state

            @staticmethod
            def on_second(state, outcome):
                return state


def test_validation_rejects_undeclared_session_refs():
    with pytest.raises(WorkflowValidationError, match="undeclared session"):

        class UndeclaredSessionWorkflow(Workflow):
            class State(BaseModel):
                pass

            ask = LLMStep(name="ask", producer="ask.md", session=Session())
            entry = ask
            transitions = {ask: {"done": SUCCESS}}

            @staticmethod
            def on_ask(state, outcome):
                return state


def test_validation_accepts_workflow_level_inputs_without_prior_producer():
    class ValidInputWorkflow(Workflow):
        class State(BaseModel):
            pass

        request = Artifact("request.txt")
        ask = LLMStep(name="ask", producer="ask.md", requires=[request])
        entry = ask
        transitions = {ask: {"done": SUCCESS}}

        @staticmethod
        def on_ask(state, outcome):
            return state

    assert ValidInputWorkflow.__workflow_definition__.entry.name == "ask"
