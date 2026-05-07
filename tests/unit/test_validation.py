from __future__ import annotations

import pytest
from pydantic import BaseModel, Field

from autoloop.core.compiler import compile_workflow
from autoloop.core.artifacts import Artifact
from autoloop.core.effects import Effects, WorklistEffect
from autoloop.core.errors import RoutingError, WorkflowCompilationError, WorkflowValidationError
from autoloop.core.extensions import RunBinding
from autoloop.core.primitives import Event, Goto
from autoloop.core.providers.retries import ProviderRetryPolicy
from autoloop.core.route_required_writes import effective_route_required_writes, explicit_route_required_writes
from autoloop.core.routes import Route
from autoloop.core.steps import ControlRoutes, PromptStep, ProduceVerifyStep, Session, PythonStep, ChildWorkflowStep
from autoloop.core.worklists import Selector, Worklist
from autoloop.stdlib.validation import (
    contains_hidden_execution_signal,
    deduped_string_list_fields,
    extract_workflow_names_from_capability_snapshot,
    extract_workflow_names_from_portfolio_health,
    normalize_optional_string,
    normalize_unique_strings,
    optional_text_fields,
    read_required_text,
    require_existing_artifact_paths,
    positive_int_fields,
    read_json_object,
    require_mapping,
    require_mapping_list,
    require_non_negative_int,
    require_non_empty_string,
    require_positive_int,
    require_true_flag,
    required_text_fields,
    require_string_list,
    validate_authoritative_artifact_subset,
    validate_no_hidden_execution_signal,
    validate_publication_boundary,
)
from autoloop.core import AWAIT_INPUT, FAIL, FINISH, GLOBAL, SELF, Workflow




def _chain_hooks(*hooks):
    active = tuple(hook for hook in hooks if hook is not None)
    if not active:
        return None

    def chained(ctx):
        for hook in active:
            result = hook(ctx)
            if result is not None:
                return result
        return None

    return chained


def _patch_missing_jsonschema(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "jsonschema":
            raise ModuleNotFoundError("No module named 'jsonschema'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_validation_allows_missing_state_with_empty_fallback_model():
    def _missingstateworkflow_on_begin(ctx):
        return Event('done')

    class MissingStateWorkflow(Workflow):
        begin = PythonStep(name="begin", handler=_missingstateworkflow_on_begin)
        entry = begin
        transitions = {begin: {"done": FINISH}}


    compiled = compile_workflow(MissingStateWorkflow)

    assert compiled.entry_step_name == "begin"
    assert compiled.new_state().model_dump() == {}


def test_validation_defaults_missing_entry_to_first_declared_step():
    def _missingentryworkflow_on_begin(ctx):
        return Event('done')

    class MissingEntryWorkflow(Workflow):
        class State(BaseModel):
            pass

        begin = PythonStep(name="begin", handler=_missingentryworkflow_on_begin)
        transitions = {begin: {"done": FINISH}}


    compiled = compile_workflow(MissingEntryWorkflow)

    assert compiled.entry_step_name == "begin"


def test_validation_rejects_workflow_input_message_field() -> None:
    class InvalidInputWorkflow(Workflow):
        class State(BaseModel):
            pass

        class Input(BaseModel):
            message: str

        begin = PythonStep(name="begin", handler=lambda ctx: Event("done"))
        entry = begin
        transitions = {begin: {"done": FINISH}}

    with pytest.raises(
        WorkflowCompilationError,
        match=r"InvalidInputWorkflow\.Input must not declare field 'message'; "
        r"message is provided by client\.run\(\.\.\., message\)\.",
    ):
        compile_workflow(InvalidInputWorkflow)


def test_core_control_routes_compile_provider_visibility_and_non_provider_defaults() -> None:
    class ChildWorkflow(Workflow):
        class State(BaseModel):
            pass

        finish = PythonStep(name="finish", handler=lambda ctx: Event("done"))
        entry = finish
        transitions = {finish: {"done": FINISH}}

    class ControlRoutesWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md")
        always = PromptStep(
            name="always",
            producer="always.md",
            control_routes=ControlRoutes(question="always"),
        )
        silent = PromptStep(name="silent", producer="silent.md", control_routes=False)
        run = PythonStep(name="run", handler=lambda ctx: Event("done"))
        launch = ChildWorkflowStep(name="launch", workflow="child_workflow")
        entry = ask
        transitions = {
            ask: {"done": always},
            always: {"done": silent},
            silent: {"done": run},
            run: {"done": launch},
            launch: {"done": FINISH},
        }

    compiled = compile_workflow(ControlRoutesWorkflow)

    assert compiled.steps["ask"].runtime_control_routes == ("question",)
    assert compiled.steps["ask"].provider_visible_routes_interactive == ("done", "question")
    assert compiled.steps["ask"].provider_visible_routes_full_auto == ("done",)

    assert compiled.steps["always"].runtime_control_routes == ("question",)
    assert compiled.steps["always"].provider_visible_routes_interactive == ("done", "question")
    assert compiled.steps["always"].provider_visible_routes_full_auto == ("done", "question")

    assert compiled.steps["silent"].runtime_control_routes == ()
    assert compiled.steps["silent"].provider_visible_routes_interactive == ("done",)
    assert compiled.steps["silent"].provider_visible_routes_full_auto == ("done",)

    assert set(compiled.routes["run"]) == {"done"}
    assert compiled.steps["run"].runtime_control_routes == ()
    assert compiled.steps["run"].provider_visible_routes_interactive == ()
    assert compiled.steps["run"].provider_visible_routes_full_auto == ()

    assert set(compiled.routes["launch"]) == {"done"}
    assert compiled.steps["launch"].runtime_control_routes == ()
    assert compiled.steps["launch"].provider_visible_routes_interactive == ()
    assert compiled.steps["launch"].provider_visible_routes_full_auto == ()


def test_route_helper_defaults_and_global_suppression_compile_from_route_metadata() -> None:
    class HelperPayload(BaseModel):
        topic: str | None = None

    class HelperRouteWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            expected_output_schema=HelperPayload,
        )
        entry = ask
        transitions = {
            ask: {
                "done": FINISH,
                "failed": Route.disabled(),
            },
            GLOBAL: {
                "question": Route.question(),
                "blocked": Route.blocked(),
                "failed": Route.failed(),
            },
        }

    compiled = compile_workflow(HelperRouteWorkflow)
    question = compiled.route("ask", "question")
    blocked = compiled.route("ask", "blocked")

    assert question.inheritance_source == "global"
    assert question.preset_kind == "question"
    assert question.provider_visibility == "interactive_only"
    assert question.route_fields_schema is not None
    assert question.route_fields_schema["required"] == ["questions", "reason"]
    assert question.payload_schema_mode == "inherit"

    assert blocked.inheritance_source == "global"
    assert blocked.preset_kind == "blocked"
    assert blocked.provider_visibility == "interactive_only"
    assert blocked.route_fields_schema is not None
    assert blocked.route_fields_schema["required"] == ["reason"]

    assert compiled.steps["ask"].available_routes == ("done", "question", "blocked")
    assert compiled.steps["ask"].provider_visible_routes_interactive == ("done", "question", "blocked")
    assert compiled.steps["ask"].provider_visible_routes_full_auto == ("done",)
    assert "failed" not in compiled.steps["ask"].available_routes
    assert compiled.routes["ask"]["failed"].disabled is True
    with pytest.raises(RoutingError):
        compiled.route("ask", "failed")


def test_global_question_routes_compile_with_step_specific_provider_visibility() -> None:
    class GlobalQuestionVisibilityWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md")
        run = PythonStep(name="run", handler=lambda ctx: Event("done"))
        entry = ask
        transitions = {
            ask: {"done": run},
            run: {"done": FINISH},
            GLOBAL: {"question": Route.question()},
        }

    compiled = compile_workflow(GlobalQuestionVisibilityWorkflow)

    assert compiled.steps["ask"].available_routes == ("done", "question")
    assert compiled.steps["ask"].provider_visible_routes_interactive == ("done", "question")
    assert compiled.steps["run"].available_routes == ("done", "question")
    assert compiled.steps["run"].provider_visible_routes_interactive == ()
    assert compiled.steps["run"].provider_visible_routes_full_auto == ()
    assert compiled.routes["run"]["question"].inheritance_source == "global"
    assert compiled.routes["run"]["question"].provider_visible_interactive is False
    assert compiled.routes["run"]["question"].provider_visible_full_auto is False


LEGACY_ROUTE_KEYWORD = "route_" "contracts"


@pytest.mark.parametrize(
    ("factory", "expected_fragment"),
    [
        (lambda: PromptStep(name="ask", producer="ask.md", **{LEGACY_ROUTE_KEYWORD: {}}), LEGACY_ROUTE_KEYWORD),
        (
            lambda: ProduceVerifyStep(name="review", producer="producer.md", verifier="verifier.md", **{LEGACY_ROUTE_KEYWORD: {}}),
            LEGACY_ROUTE_KEYWORD,
        ),
        (lambda: PythonStep(name="publish", **{LEGACY_ROUTE_KEYWORD: {}}), LEGACY_ROUTE_KEYWORD),
        (lambda: ChildWorkflowStep(name="launch", workflow="child.workflow", **{LEGACY_ROUTE_KEYWORD: {}}), LEGACY_ROUTE_KEYWORD),
    ],
)
def test_core_step_constructors_reject_legacy_route_metadata_keyword(factory, expected_fragment: str) -> None:
    with pytest.raises(TypeError, match=expected_fragment):
        factory()


def test_validation_rejects_missing_system_handler():
    with pytest.raises(WorkflowValidationError, match="missing handler"):

        class MissingSystemHandlerWorkflow(Workflow):
            class State(BaseModel):
                pass

            begin = PythonStep(name="begin")
            entry = begin
            transitions = {begin: {"done": FINISH}}


def test_validation_accepts_direct_system_step_handler_without_on_step_method():
    class DirectHandlerWorkflow(Workflow):
        class State(BaseModel):
            notes: int = 0

        begin = PythonStep(name="begin", handler=lambda ctx: Event("done"))
        entry = begin
        transitions = {begin: {"done": FINISH}}

    compiled = compile_workflow(DirectHandlerWorkflow)

    assert compiled.entry_step_name == "begin"
    assert compiled.steps["begin"].python_handler is not None


def test_validation_rejects_invalid_workflow_step_child_class_reference():
    with pytest.raises(WorkflowValidationError, match="must reference a workflow class or workflow name"):

        class InvalidWorkflowReferenceWorkflow(Workflow):
            class State(BaseModel):
                pass

            launch = ChildWorkflowStep(name="launch", workflow=BaseModel)
            entry = launch
            transitions = {launch: {"done": FINISH}}


def test_validation_rejects_orphan_handlers():
    with pytest.raises(WorkflowValidationError, match="orphan handler"):

        def _orphanhandlerworkflow_on_begin(ctx):
            return Event('done')

        class OrphanHandlerWorkflow(Workflow):
            class State(BaseModel):
                pass

            begin = PythonStep(name="begin", handler=_orphanhandlerworkflow_on_begin)
            entry = begin
            transitions = {begin: {"done": FINISH}}


            @staticmethod
            def on_missing(state, outcome):
                return state


def test_validation_rejects_invalid_destinations():
    with pytest.raises(WorkflowValidationError, match="invalid transition destination"):

        def _invaliddestinationworkflow_on_begin(ctx):
            return Event('done')

        class InvalidDestinationWorkflow(Workflow):
            class State(BaseModel):
                pass

            begin = PythonStep(name="begin", handler=_invaliddestinationworkflow_on_begin)
            entry = begin
            transitions = {begin: {"done": "UNKNOWN"}}



def test_validation_rejects_legacy_success_terminal_string():
    legacy_finish = "SU" "CCESS"

    with pytest.raises(WorkflowValidationError, match="invalid transition destination"):

        def _legacysuccessworkflow_on_begin(ctx):
            return Event('done')

        class LegacySuccessWorkflow(Workflow):
            class State(BaseModel):
                pass

            begin = PythonStep(name="begin", handler=_legacysuccessworkflow_on_begin)
            entry = begin
            transitions = {begin: {"done": legacy_finish}}



def test_board_mutation_is_not_exported_from_public_modules():
    import autoloop
    import autoloop.core as core
    board_mutation_name = "Board" + "Mutation"

    assert not hasattr(autoloop, board_mutation_name)
    assert not hasattr(core, board_mutation_name)


def test_route_effects_module_exports_typed_effect_helpers():
    assert Effects.advance(exhausted="done") == Effects(
        worklists=(WorklistEffect(advance=True, exhausted="done"),)
    )
    assert Effects.complete_and_advance(worklist="items") == Effects(
        worklists=(WorklistEffect(worklist="items", set_current_status="completed", advance=True),)
    )


def test_validation_rejects_duplicate_artifact_names():
    with pytest.raises(WorkflowValidationError, match="duplicate artifact name"):

        def _duplicateartifactworkflow_on_begin(ctx):
            return Event('done')

        class DuplicateArtifactWorkflow(Workflow):
            class State(BaseModel):
                pass

            one = Artifact("one.txt", name="dup")
            two = Artifact("two.txt", name="dup")
            begin = PythonStep(name="begin", handler=_duplicateartifactworkflow_on_begin)
            entry = begin
            transitions = {begin: {"done": FINISH}}



def test_validation_rejects_schema_on_non_json_artifact():
    class Summary(BaseModel):
        text: str

    report_artifact = Artifact("{run_folder}/report.md", kind="markdown", schema=Summary)

    with pytest.raises(WorkflowValidationError, match="schema is only supported for json artifacts"):

        def _invalidartifactschemaworkflow_on_ask(ctx):
            return None

        class InvalidArtifactSchemaWorkflow(Workflow):
            class State(BaseModel):
                pass

            ask = PromptStep(name="ask", producer="ask.md", writes={"report": report_artifact})
            entry = ask
            transitions = {ask: {"done": FINISH}}

        InvalidArtifactSchemaWorkflow.ask.after = _chain_hooks(_invalidartifactschemaworkflow_on_ask, InvalidArtifactSchemaWorkflow.ask.after)



def test_validation_rejects_unsupported_artifact_schema_type():
    report_artifact = Artifact.json("{run_folder}/report.json", schema=object())

    with pytest.raises(WorkflowValidationError, match="unsupported schema type"):

        def _invalidartifactschematypeworkflow_on_ask(ctx):
            return None

        class InvalidArtifactSchemaTypeWorkflow(Workflow):
            class State(BaseModel):
                pass

            ask = PromptStep(name="ask", producer="ask.md", writes={"report": report_artifact})
            entry = ask
            transitions = {ask: {"done": FINISH}}

        InvalidArtifactSchemaTypeWorkflow.ask.after = _chain_hooks(_invalidartifactschematypeworkflow_on_ask, InvalidArtifactSchemaTypeWorkflow.ask.after)



def test_validation_rejects_raw_artifact_schema_without_jsonschema_dependency(monkeypatch):
    raw_schema = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
        },
        "required": ["summary"],
        "additionalProperties": False,
    }

    _patch_missing_jsonschema(monkeypatch)
    report_artifact = Artifact.json("{run_folder}/report.json", schema=raw_schema)

    with pytest.raises(WorkflowValidationError, match="optional jsonschema dependency"):

        def _rawartifactschemaworkflow_on_ask(ctx):
            return None

        class RawArtifactSchemaWorkflow(Workflow):
            class State(BaseModel):
                pass

            ask = PromptStep(name="ask", producer="ask.md", writes={"report": report_artifact})
            entry = ask
            transitions = {ask: {"done": FINISH}}

        RawArtifactSchemaWorkflow.ask.after = _chain_hooks(_rawartifactschemaworkflow_on_ask, RawArtifactSchemaWorkflow.ask.after)



def test_validation_rejects_future_required_artifacts():
    future_artifact = Artifact("produced.txt", name="produced")

    with pytest.raises(WorkflowValidationError, match="before it is produced"):

        def _futureartifactworkflow_on_first(ctx):
            return None

        def _futureartifactworkflow_on_second(ctx):
            return None

        class FutureArtifactWorkflow(Workflow):
            class State(BaseModel):
                pass

            first = PromptStep(name="first", producer="first.md", requires=[future_artifact])
            second = PromptStep(name="second", producer="second.md", writes={"produced": future_artifact})
            entry = first
            transitions = {first: {"next": second}, second: {"done": FINISH}}


        FutureArtifactWorkflow.first.after = _chain_hooks(_futureartifactworkflow_on_first, FutureArtifactWorkflow.first.after)
        FutureArtifactWorkflow.second.after = _chain_hooks(_futureartifactworkflow_on_second, FutureArtifactWorkflow.second.after)



def test_validation_rejects_undeclared_session_refs():
    with pytest.raises(WorkflowValidationError, match="undeclared session"):

        class UndeclaredSessionWorkflow(Workflow):
            class State(BaseModel):
                pass

            ask = PromptStep(name="ask", producer="ask.md", session=Session())
            entry = ask
            transitions = {ask: {"done": FINISH}}

            @staticmethod
            def on_ask(state, outcome, artifacts):
                return state


def test_validation_accepts_workflow_level_inputs_without_prior_producer():
    def _validinputworkflow_on_ask(ctx):
        return None

    class ValidInputWorkflow(Workflow):
        class State(BaseModel):
            pass

        request = Artifact("request.txt")
        ask = PromptStep(name="ask", producer="ask.md", requires=[request])
        entry = ask
        transitions = {ask: {"done": FINISH}}

    ValidInputWorkflow.ask.after = _chain_hooks(_validinputworkflow_on_ask, ValidInputWorkflow.ask.after)


    assert ValidInputWorkflow.__workflow_definition__.entry.name == "ask"


def test_validation_accepts_same_identity_workflow_level_artifact_written_by_one_step():
    shared_request = Artifact("request.txt")

    def _dualroleartifactworkflow_on_publish(ctx):
        return Event("done")

    class DualRoleArtifactWorkflow(Workflow):
        class State(BaseModel):
            pass

        request = shared_request
        publish = PythonStep(
            name="publish",
            writes={"request": shared_request},
            handler=_dualroleartifactworkflow_on_publish,
        )
        entry = publish
        transitions = {
            publish: {
                "done": Route.finish(required_writes=("request",)),
            }
        }

    compiled = compile_workflow(DualRoleArtifactWorkflow)

    assert DualRoleArtifactWorkflow.request.qualified_name == "request"
    assert DualRoleArtifactWorkflow.request.owner_step is None
    assert compiled.artifacts["request"].qualified_name == "request"
    assert compiled.artifacts["request"].workflow_level is True
    assert compiled.artifacts["request"].producer_steps == ("publish",)
    assert compiled.artifacts_by_qualified_name["request"].name == "request"
    assert compiled.steps["publish"].writes == ("request",)
    assert compiled.routes["publish"]["done"].required_writes == ("request",)


def test_validation_accepts_same_identity_workflow_level_artifact_written_by_multiple_steps():
    shared_request = Artifact("request.txt")

    def _firstdualroleartifactworkflow_on_plan(ctx):
        return Event("done")

    def _seconddualroleartifactworkflow_on_revise(ctx):
        return Event("done")

    class MultiProducerArtifactWorkflow(Workflow):
        class State(BaseModel):
            pass

        request = shared_request
        plan = PythonStep(name="plan", writes={"request": shared_request}, handler=_firstdualroleartifactworkflow_on_plan)
        revise = PythonStep(name="revise", writes={"request": shared_request}, handler=_seconddualroleartifactworkflow_on_revise)
        entry = plan
        transitions = {plan: {"done": revise}, revise: {"done": FINISH}}

    compiled = compile_workflow(MultiProducerArtifactWorkflow)

    assert compiled.artifacts["request"].qualified_name == "request"
    assert compiled.artifacts["request"].workflow_level is True
    assert compiled.artifacts["request"].producer_steps == ("plan", "revise")
    assert compiled.steps["plan"].writes == ("request",)
    assert compiled.steps["revise"].writes == ("request",)


def test_validation_rejects_distinct_artifacts_with_same_public_name_across_workflow_and_step_output():
    workflow_request = Artifact("request.txt", name="request")
    produced_request = Artifact("produced-request.txt", name="request")

    with pytest.raises(
        WorkflowValidationError,
        match="declared by multiple artifact objects with the same public name",
    ) as exc_info:

        def _ownershipcollisionworkflow_on_publish(ctx):
            return Event("done")

        class OwnershipCollisionWorkflow(Workflow):
            class State(BaseModel):
                pass

            request = workflow_request
            publish = PythonStep(
                name="publish",
                writes={"request": produced_request},
                handler=_ownershipcollisionworkflow_on_publish,
            )
            entry = publish
            transitions = {publish: {"done": FINISH}}

    message = str(exc_info.value)
    assert "workflow-level declaration 'request'" in message
    assert "step output 'publish.request' from step 'publish'" in message
    assert "template='request.txt'" in message
    assert "template='produced-request.txt'" in message
    assert "reuse the same Artifact object" in message


def test_validation_rejects_non_tuple_extensions():
    with pytest.raises(WorkflowValidationError, match="extensions"):

        class NonTupleExtensionWorkflow(Workflow):
            class State(BaseModel):
                pass

            extensions = []
            ask = PromptStep(name="ask", producer="ask.md")
            entry = ask
            transitions = {ask: {"done": FINISH}}

            @staticmethod
            def on_ask(state, outcome, artifacts):
                return state


def test_validation_rejects_extension_without_bind():
    with pytest.raises(WorkflowValidationError, match="bind"):

        class MissingBindWorkflow(Workflow):
            class State(BaseModel):
                pass

            extensions = (object(),)
            ask = PromptStep(name="ask", producer="ask.md")
            entry = ask
            transitions = {ask: {"done": FINISH}}

            @staticmethod
            def on_ask(state, outcome, artifacts):
                return state


def test_compilation_preserves_declared_extensions():
    class RecordingExtension:
        def bind(self, binding: RunBinding):
            return self

        def before_step(self, event):
            return None

        def after_step(self, event):
            return None

        def on_terminal(self, event):
            return None

    extension = RecordingExtension()

    def _extensionworkflow_on_ask(ctx):
        return None

    class ExtensionWorkflow(Workflow):
        class State(BaseModel):
            pass

        extensions = (extension,)
        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"done": FINISH}}

    ExtensionWorkflow.ask.after = _chain_hooks(_extensionworkflow_on_ask, ExtensionWorkflow.ask.after)


    compiled = compile_workflow(ExtensionWorkflow)

    assert compiled.extensions == (extension,)


def test_dict_transition_shorthand_still_compiles_to_explicit_routes():
    def _shorthandworkflow_on_ask(ctx):
        return None

    class ShorthandWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"done": FINISH}}

    ShorthandWorkflow.ask.after = _chain_hooks(_shorthandworkflow_on_ask, ShorthandWorkflow.ask.after)


    compiled = compile_workflow(ShorthandWorkflow)

    route = compiled.routes["ask"]["done"]
    assert route.source_step == "ask"
    assert route.tag == "done"
    assert route.target == FINISH


def test_route_object_to_step_compiles():
    def _typedrouteworkflow_on_ask(ctx):
        return None

    def _typedrouteworkflow_on_finish(ctx):
        return Event('complete')

    class TypedRouteWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md")
        finish = PythonStep(name="finish", handler=_typedrouteworkflow_on_finish)
        entry = ask
        transitions = {
            ask: {"done": Route.to(finish)},
            finish: {"complete": FINISH},
        }


    TypedRouteWorkflow.ask.after = _chain_hooks(_typedrouteworkflow_on_ask, TypedRouteWorkflow.ask.after)


    compiled = compile_workflow(TypedRouteWorkflow)

    route = compiled.routes["ask"]["done"]
    assert route.target == "finish"


def test_handoff_route_to_provider_step_compiles():
    def _handoffworkflow_on_ask(ctx):
        return None

    def _handoffworkflow_on_review(ctx):
        return None

    class HandoffWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md")
        review = PromptStep(name="review", producer="review.md")
        entry = ask
        transitions = {
            ask: {"done": Route.to(review, handoff="Carry the unresolved feedback forward.")},
            review: {"complete": FINISH},
        }


    HandoffWorkflow.ask.after = _chain_hooks(_handoffworkflow_on_ask, HandoffWorkflow.ask.after)
    HandoffWorkflow.review.after = _chain_hooks(_handoffworkflow_on_review, HandoffWorkflow.review.after)


    compiled = compile_workflow(HandoffWorkflow)

    route = compiled.routes["ask"]["done"]
    assert route.target == "review"
    assert route.handoff == "Carry the unresolved feedback forward."


def test_validation_rejects_handoff_route_to_system_step():
    with pytest.raises(WorkflowValidationError, match="cannot deliver handoff metadata to PythonStep 'finish'"):

        def _invalidhandoffworkflow_on_ask(ctx):
            return None

        def _invalidhandoffworkflow_on_finish(ctx):
            return Event('complete')

        class InvalidHandoffWorkflow(Workflow):
            class State(BaseModel):
                pass

            ask = PromptStep(name="ask", producer="ask.md")
            finish = PythonStep(name="finish", handler=_invalidhandoffworkflow_on_finish)
            entry = ask
            transitions = {
                ask: {"done": Route.to(finish, handoff="Do not send this to a system step.")},
                finish: {"complete": FINISH},
            }


        InvalidHandoffWorkflow.ask.after = _chain_hooks(_invalidhandoffworkflow_on_ask, InvalidHandoffWorkflow.ask.after)



def test_route_complete_with_effects_compiles_when_effect_list_is_empty():
    def _completerouteworkflow_on_ask(ctx):
        return None

    class CompleteRouteWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"done": Route.finish()}}

    CompleteRouteWorkflow.ask.after = _chain_hooks(_completerouteworkflow_on_ask, CompleteRouteWorkflow.ask.after)


    compiled = compile_workflow(CompleteRouteWorkflow)

    route = compiled.routes["ask"]["done"]
    assert route.target == FINISH
    assert route.handoff is None


def test_route_effects_are_rejected_at_route_construction_time():
    with pytest.raises(TypeError, match="unexpected keyword argument 'effects'"):

        Route.to(FINISH, effects=())


def test_declared_worklist_allows_scoped_steps_and_on_taken_helpers():
    def _scopedworkflow_on_ask(ctx):
        return None

    class ScopedWorkflow(Workflow):
        class State(BaseModel):
            pass

        gates = Worklist.from_items(
            name="gate",
            items=(
                {"id": "alpha", "title": "Alpha"},
                {"id": "beta", "title": "Beta"},
            ),
            selector=Selector(item_param="gate_id", mode_param="mode", allowed_modes=("all", "single")),
        )
        ask = PromptStep(name="ask", producer="ask.md", scope=gates)
        entry = ask
        transitions = {ask: {"done": Route.to(FINISH, on_taken=lambda ctx: ctx.current_worklist.advance_or(Goto("ask")))}}

    ScopedWorkflow.ask.after = _chain_hooks(_scopedworkflow_on_ask, ScopedWorkflow.ask.after)


    compiled = compile_workflow(ScopedWorkflow)

    assert compiled.steps["ask"].scope_name == "gate"
    assert compiled.worklists["gate"].name == "gate"
    assert compiled.routes["ask"]["done"].on_taken is not None


def test_validation_rejects_unknown_scoped_step_worklist():
    with pytest.raises(WorkflowValidationError, match="unknown worklist 'gate'"):

        class InvalidScopeWorkflow(Workflow):
            class State(BaseModel):
                pass

            ask = PromptStep(name="ask", producer="ask.md", scope="gate")
            entry = ask
            transitions = {ask: {"done": FINISH}}

            @staticmethod
            def on_ask(state, outcome, artifacts):
                return state


def test_compilation_exposes_step_control_contracts():
    class ReviewPayload(BaseModel):
        summary: str

    def _contractworkflow_on_ask(ctx):
        return None

    class ContractWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            expected_output_schema=ReviewPayload,
            route_metadata={"done": "workflow completed cleanly"},
        )
        entry = ask
        transitions = {
            ask: {"done": FINISH},
            GLOBAL: {"failed": FAIL},
        }

    ContractWorkflow.ask.after = _chain_hooks(_contractworkflow_on_ask, ContractWorkflow.ask.after)


    compiled = compile_workflow(ContractWorkflow)
    compiled_step = compiled.steps["ask"]

    assert compiled_step.available_routes == ("done", "failed", "question")
    assert compiled_step.authored_routes == ("done", "failed")
    assert compiled_step.runtime_control_routes == ("question",)
    assert compiled_step.reads == ()
    assert compiled_step.expected_output_schema is not None
    assert compiled_step.expected_output_schema["type"] == "object"
    assert compiled_step.expected_output_schema["required"] == ["summary"]
    assert compiled.routes["ask"]["done"].summary == "workflow completed cleanly"
    assert compiled.routes["ask"]["question"].summary == "Clarification or user-input request."
    assert compiled.route("ask", "failed").target == "FAIL"
    assert compiled.route("ask", "failed").summary == "Routes from 'GLOBAL' to 'FAIL'."
    assert {
        route_name: compiled_route.required_writes
        for route_name, compiled_route in compiled.routes["ask"].items()
    } == {
        "done": (),
        "failed": (),
        "question": (),
    }
    assert compiled_step.retry_policy.max_attempts == 3


def test_authored_blocked_and_failed_routes_use_generic_fallback_summaries() -> None:
    class AuthoredFailureRouteWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {ask: {"blocked": AWAIT_INPUT, "failed": FAIL}}

    compiled = compile_workflow(AuthoredFailureRouteWorkflow)

    assert compiled.routes["ask"]["blocked"].summary == "Routes from 'ask' to 'AWAIT_INPUT'."
    assert compiled.routes["ask"]["failed"].summary == "Routes from 'ask' to 'FAIL'."


def test_explicit_prompt_blocked_and_failed_routes_remain_authored_only() -> None:
    class ExplicitPromptRoutesWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {
            ask: {
                "done": FINISH,
                "blocked": AWAIT_INPUT,
                "failed": Route.to(FAIL, provider_visible=False),
            }
        }

    compiled = compile_workflow(ExplicitPromptRoutesWorkflow)
    compiled_step = compiled.steps["ask"]

    assert compiled_step.available_routes == ("done", "blocked", "failed", "question")
    assert compiled_step.authored_routes == ("done", "blocked", "failed")
    assert compiled_step.runtime_control_routes == ("question",)
    assert compiled_step.provider_visible_routes_interactive == ("done", "blocked", "question")
    assert compiled_step.provider_visible_routes_full_auto == ("done", "blocked")
    assert compiled.routes["ask"]["blocked"].is_runtime_control is False
    assert compiled.routes["ask"]["failed"].is_runtime_control is False
    assert compiled.routes["ask"]["blocked"].provider_visible_interactive is True
    assert compiled.routes["ask"]["blocked"].provider_visible_full_auto is True
    assert compiled.routes["ask"]["failed"].provider_visible_interactive is False
    assert compiled.routes["ask"]["failed"].provider_visible_full_auto is False


def test_explicit_produce_verify_blocked_and_failed_routes_remain_authored_only() -> None:
    class ExplicitProduceVerifyRoutesWorkflow(Workflow):
        class State(BaseModel):
            pass

        review = ProduceVerifyStep(name="review", producer="producer.md", verifier="verifier.md")
        entry = review
        transitions = {
            review: {
                "approved": FINISH,
                "blocked": Route.to(AWAIT_INPUT, provider_visible=False),
                "failed": FAIL,
            }
        }

    compiled = compile_workflow(ExplicitProduceVerifyRoutesWorkflow)
    compiled_step = compiled.steps["review"]

    assert compiled_step.available_routes == ("approved", "blocked", "failed", "question")
    assert compiled_step.authored_routes == ("approved", "blocked", "failed")
    assert compiled_step.runtime_control_routes == ("question",)
    assert compiled_step.provider_visible_routes_interactive == ("approved", "failed", "question")
    assert compiled_step.provider_visible_routes_full_auto == ("approved", "failed")
    assert compiled.routes["review"]["blocked"].is_runtime_control is False
    assert compiled.routes["review"]["failed"].is_runtime_control is False
    assert compiled.routes["review"]["blocked"].provider_visible_interactive is False
    assert compiled.routes["review"]["blocked"].provider_visible_full_auto is False
    assert compiled.routes["review"]["failed"].provider_visible_interactive is True
    assert compiled.routes["review"]["failed"].provider_visible_full_auto is True


def test_provider_retry_policy_validates_max_attempts() -> None:
    with pytest.raises(TypeError, match="must be an integer"):
        ProviderRetryPolicy(max_attempts=True)

    with pytest.raises(ValueError, match="must be >= 1"):
        ProviderRetryPolicy(max_attempts=0)


def test_validation_rejects_provider_retry_policy_on_system_step() -> None:
    with pytest.raises(
        WorkflowValidationError,
        match="python_steps do not call a provider and cannot declare provider retry policy.",
    ):

        def _invalidsystemretryworkflow_on_publish(ctx):
            return Event('done')

        class InvalidSystemRetryWorkflow(Workflow):
            class State(BaseModel):
                pass

            publish = PythonStep(name="publish", retry_policy=ProviderRetryPolicy(max_attempts=2), handler=_invalidsystemretryworkflow_on_publish)
            entry = publish
            transitions = {publish: {"done": FINISH}}



def test_compilation_normalizes_route_metadata_required_writes():
    class ReviewPayload(BaseModel):
        summary: str

    def _contractworkflow_on_ask(ctx):
        return None

    class ContractWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            expected_output_schema=ReviewPayload,
            route_metadata={"done": Route(summary="workflow completed cleanly", required_writes=("report",))},
            writes={"report": Artifact("{run_folder}/report.md")},
        )
        entry = ask
        transitions = {ask: {"done": FINISH}}

    ContractWorkflow.ask.after = _chain_hooks(_contractworkflow_on_ask, ContractWorkflow.ask.after)


    compiled = compile_workflow(ContractWorkflow)

    assert compiled.routes["ask"]["done"].summary == "workflow completed cleanly"
    assert compiled.routes["ask"]["done"].required_writes == ("ask.report",)
    assert {
        route_name: compiled_route.required_writes
        for route_name, compiled_route in compiled.routes["ask"].items()
    } == {
        "done": ("ask.report",),
        "question": (),
    }


def test_compilation_keeps_public_empty_required_writes_but_marks_explicit_empty_overrides_privately():
    def _emptyoverrideworkflow_on_ask(ctx):
        return None

    class EmptyOverrideWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            writes={"report": Artifact.md("report.md", required=True)},
        )
        entry = ask
        transitions = {
            ask: {
                "default_done": FINISH,
                "optional_done": Route.to(FINISH, required_writes=[]),
            }
        }

    EmptyOverrideWorkflow.ask.after = _chain_hooks(_emptyoverrideworkflow_on_ask, EmptyOverrideWorkflow.ask.after)


    compiled = compile_workflow(EmptyOverrideWorkflow)

    default_route = compiled.routes["ask"]["default_done"]
    optional_route = compiled.routes["ask"]["optional_done"]

    assert default_route.required_writes == ()
    assert optional_route.required_writes == ()
    assert default_route._required_writes_explicit is False
    assert optional_route._required_writes_explicit is True
    assert explicit_route_required_writes(default_route) is None
    assert explicit_route_required_writes(optional_route) == ()
    assert effective_route_required_writes(compiled, step_name="ask", route_tag="default_done") == ("ask.report",)
    assert effective_route_required_writes(compiled, step_name="ask", route_tag="optional_done") == ()


def test_compilation_preserves_extended_artifact_metadata():
    class ReviewPayload(BaseModel):
        summary: str

    def _artifactmetadataworkflow_on_ask(ctx):
        return None

    report_artifact = Artifact(
        "{run_folder}/report.json",
        kind="json",
        schema=ReviewPayload,
        required=True,
        owner_step="ask",
        qualified_name="ask.report",
    )

    class ArtifactMetadataWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md", writes={"report": report_artifact})
        entry = ask
        transitions = {ask: {"done": FINISH}}

    ArtifactMetadataWorkflow.ask.after = _chain_hooks(_artifactmetadataworkflow_on_ask, ArtifactMetadataWorkflow.ask.after)


    compiled = compile_workflow(ArtifactMetadataWorkflow)
    artifact = compiled.artifacts["report"]

    assert artifact.kind == "json"
    assert artifact.schema is ReviewPayload
    assert artifact.required is True
    assert artifact.owner_step == "ask"
    assert artifact.qualified_name == "ask.report"


def test_step_local_artifacts_bind_names_and_qualified_names():
    def _steplocalartifactworkflow_on_draft(ctx):
        return None

    class StepLocalArtifactWorkflow(Workflow):
        class State(BaseModel):
            pass

        draft = PromptStep(
            name="draft",
            producer="draft.md",
            writes={
                "summary": Artifact.json("summary.json", required=True),
                "report": Artifact.md("report.md"),
            },
        )
        entry = draft
        transitions = {draft: {"done": FINISH}}

    StepLocalArtifactWorkflow.draft.after = _chain_hooks(_steplocalartifactworkflow_on_draft, StepLocalArtifactWorkflow.draft.after)


    compiled = compile_workflow(StepLocalArtifactWorkflow)

    assert StepLocalArtifactWorkflow.draft.summary.name == "summary"
    assert StepLocalArtifactWorkflow.draft.summary.owner_step == "draft"
    assert StepLocalArtifactWorkflow.draft.summary.qualified_name == "draft.summary"
    assert compiled.artifacts["summary"].owner_step == "draft"
    assert compiled.artifacts["summary"].qualified_name == "draft.summary"
    assert compiled.artifacts_by_qualified_name["draft.summary"].name == "draft.summary"
    assert compiled.steps["draft"].writes == ("draft.summary", "draft.report")


def test_compilation_requires_accept_step_local_artifact_reference():
    def _steplocaldependencyworkflow_on_draft(ctx):
        return None

    def _steplocaldependencyworkflow_on_publish(ctx):
        return Event('complete')

    class StepLocalDependencyWorkflow(Workflow):
        class State(BaseModel):
            pass

        draft = PromptStep(
            name="draft",
            producer="draft.md",
            writes={"summary": Artifact.md("summary.md")},
        )
        publish = PythonStep(name="publish", requires=[draft.summary], handler=_steplocaldependencyworkflow_on_publish)
        entry = draft
        transitions = {draft: {"done": publish}, publish: {"complete": FINISH}}


    StepLocalDependencyWorkflow.draft.after = _chain_hooks(_steplocaldependencyworkflow_on_draft, StepLocalDependencyWorkflow.draft.after)


    compiled = compile_workflow(StepLocalDependencyWorkflow)

    assert compiled.steps["publish"].requires == ("draft.summary",)


def test_compilation_tracks_optional_read_artifact_references():
    def _readdependencyworkflow_on_draft(ctx):
        return None

    def _readdependencyworkflow_on_publish(ctx):
        return Event('complete')

    class ReadDependencyWorkflow(Workflow):
        class State(BaseModel):
            pass

        draft = PromptStep(
            name="draft",
            producer="draft.md",
            writes={"summary": Artifact.md("summary.md")},
        )
        publish = PythonStep(name="publish", reads=["summary"], handler=_readdependencyworkflow_on_publish)
        entry = draft
        transitions = {draft: {"done": publish}, publish: {"complete": FINISH}}


    ReadDependencyWorkflow.draft.after = _chain_hooks(_readdependencyworkflow_on_draft, ReadDependencyWorkflow.draft.after)


    compiled = compile_workflow(ReadDependencyWorkflow)

    assert compiled.steps["publish"].reads == ("draft.summary",)
    assert compiled.steps["publish"].requires == ()


def test_route_metadata_required_write_resolves_to_step_local_output():
    def _routescopedartifactworkflow_on_draft(ctx):
        return None

    def _routescopedartifactworkflow_on_review(ctx):
        return None

    class RouteScopedArtifactWorkflow(Workflow):
        class State(BaseModel):
            pass

        draft = PromptStep(
            name="draft",
            producer="draft.md",
            writes={"summary": Artifact.md("summary.md")},
            route_metadata={"done": Route(summary="draft finished", required_writes=("summary",))},
        )
        review = PromptStep(name="review", producer="review.md", writes={"summary": Artifact.md("summary.md")})
        entry = draft
        transitions = {draft: {"done": review}, review: {"done": FINISH}}


    RouteScopedArtifactWorkflow.draft.after = _chain_hooks(_routescopedartifactworkflow_on_draft, RouteScopedArtifactWorkflow.draft.after)
    RouteScopedArtifactWorkflow.review.after = _chain_hooks(_routescopedartifactworkflow_on_review, RouteScopedArtifactWorkflow.review.after)


    compiled = compile_workflow(RouteScopedArtifactWorkflow)

    assert compiled.routes["draft"]["done"].required_writes == ("draft.summary",)
    assert "summary" not in compiled.artifacts
    assert set(compiled.artifacts_by_qualified_name) >= {"draft.summary", "review.summary"}


def test_compilation_uses_explicit_transition_route_metadata():
    def _explicitroutemetadataworkflow_on_ask(ctx):
        return None

    class ExplicitRouteMetadataWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            writes={"report": Artifact.md("report.md")},
        )
        entry = ask
        transitions = {
            ask: {
                "done": Route.finish(
                    summary="publish the generated report",
                    required_writes=("report",),
                )
            }
        }

    ExplicitRouteMetadataWorkflow.ask.after = _chain_hooks(_explicitroutemetadataworkflow_on_ask, ExplicitRouteMetadataWorkflow.ask.after)


    compiled = compile_workflow(ExplicitRouteMetadataWorkflow)

    assert compiled.routes["ask"]["done"].summary == "publish the generated report"
    assert compiled.routes["ask"]["done"].required_writes == ("ask.report",)
    assert {
        route_name: compiled_route.required_writes
        for route_name, compiled_route in compiled.routes["ask"].items()
    } == {
        "done": ("ask.report",),
        "question": (),
    }


def test_validation_rejects_ambiguous_unqualified_artifact_reference():
    with pytest.raises(WorkflowValidationError, match="ambiguous artifact reference 'summary'"):

        def _ambiguousartifactreferenceworkflow_on_draft(ctx):
            return None

        def _ambiguousartifactreferenceworkflow_on_review(ctx):
            return None

        def _ambiguousartifactreferenceworkflow_on_publish(ctx):
            return Event('complete')

        class AmbiguousArtifactReferenceWorkflow(Workflow):
            class State(BaseModel):
                pass

            draft = PromptStep(name="draft", producer="draft.md", writes={"summary": Artifact.md("summary.md")})
            review = PromptStep(name="review", producer="review.md", writes={"summary": Artifact.md("summary.md")})
            publish = PythonStep(name="publish", requires=["summary"], handler=_ambiguousartifactreferenceworkflow_on_publish)
            entry = draft
            transitions = {
                draft: {"done": review},
                review: {"done": publish},
                publish: {"complete": FINISH},
            }



        AmbiguousArtifactReferenceWorkflow.draft.after = _chain_hooks(_ambiguousartifactreferenceworkflow_on_draft, AmbiguousArtifactReferenceWorkflow.draft.after)
        AmbiguousArtifactReferenceWorkflow.review.after = _chain_hooks(_ambiguousartifactreferenceworkflow_on_review, AmbiguousArtifactReferenceWorkflow.review.after)



def test_validation_rejects_ambiguous_declared_read_reference():
    with pytest.raises(WorkflowValidationError, match="ambiguous artifact reference 'summary'"):

        def _ambiguousreadworkflow_on_draft(ctx):
            return None

        def _ambiguousreadworkflow_on_review(ctx):
            return None

        def _ambiguousreadworkflow_on_publish(ctx):
            return Event('complete')

        class AmbiguousReadWorkflow(Workflow):
            class State(BaseModel):
                pass

            draft = PromptStep(name="draft", producer="draft.md", writes={"summary": Artifact.md("summary.md")})
            review = PromptStep(name="review", producer="review.md", writes={"summary": Artifact.md("summary-2.md")})
            publish = PythonStep(name="publish", reads=["summary"], handler=_ambiguousreadworkflow_on_publish)
            entry = draft
            transitions = {
                draft: {"done": review},
                review: {"done": publish},
                publish: {"complete": FINISH},
            }



        AmbiguousReadWorkflow.draft.after = _chain_hooks(_ambiguousreadworkflow_on_draft, AmbiguousReadWorkflow.draft.after)
        AmbiguousReadWorkflow.review.after = _chain_hooks(_ambiguousreadworkflow_on_review, AmbiguousReadWorkflow.review.after)


        compile_workflow(AmbiguousReadWorkflow)


def test_validation_rejects_future_read_artifacts():
    def _futurereadworkflow_on_publish(ctx):
        return Event('complete')

    def _futurereadworkflow_on_draft(ctx):
        return None

    class FutureReadWorkflow(Workflow):
        class State(BaseModel):
            pass

        publish = PythonStep(name="publish", reads=["summary", "workspace/optional.md"], handler=_futurereadworkflow_on_publish)
        draft = PromptStep(
            name="draft",
            producer="draft.md",
            writes={"summary": Artifact.md("summary.md")},
        )
        entry = publish
        transitions = {
            publish: {"complete": draft},
            draft: {"done": FINISH},
        }


    FutureReadWorkflow.draft.after = _chain_hooks(_futurereadworkflow_on_draft, FutureReadWorkflow.draft.after)


    compiled = compile_workflow(FutureReadWorkflow)

    assert compiled.steps["publish"].reads == ("draft.summary", "workspace/optional.md")


def test_compiled_workflow_artifact_items_distinguish_alias_and_authoritative_inventories():
    def _artifactitemsworkflow_on_draft(ctx):
        return None

    def _artifactitemsworkflow_on_review(ctx):
        return None

    class ArtifactItemsWorkflow(Workflow):
        class State(BaseModel):
            pass

        draft = PromptStep(name="draft", producer="draft.md", writes={"summary": Artifact.md("summary.md")})
        review = PromptStep(name="review", producer="review.md", writes={"summary": Artifact.md("summary.md")})
        entry = draft
        transitions = {draft: {"done": review}, review: {"done": FINISH}}


    ArtifactItemsWorkflow.draft.after = _chain_hooks(_artifactitemsworkflow_on_draft, ArtifactItemsWorkflow.draft.after)
    ArtifactItemsWorkflow.review.after = _chain_hooks(_artifactitemsworkflow_on_review, ArtifactItemsWorkflow.review.after)


    compiled = compile_workflow(ArtifactItemsWorkflow)

    assert compiled.artifact_items() == ()
    assert compiled.artifact_items(authoritative=True) == (
        ("draft.summary", compiled.artifacts_by_qualified_name["draft.summary"]),
        ("review.summary", compiled.artifacts_by_qualified_name["review.summary"]),
    )


def test_validation_rejects_raw_json_schema_output_contract_without_jsonschema_dependency(monkeypatch):
    raw_schema = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
        },
        "required": ["summary"],
        "additionalProperties": False,
    }

    _patch_missing_jsonschema(monkeypatch)

    with pytest.raises(WorkflowValidationError, match="optional jsonschema dependency"):

        def _rawschemaworkflow_on_ask(ctx):
            return None

        class RawSchemaWorkflow(Workflow):
            class State(BaseModel):
                pass

            ask = PromptStep(
                name="ask",
                producer="ask.md",
                expected_output_schema=raw_schema,
                route_metadata={"done": "success path"},
            )
            entry = ask
            transitions = {ask: {"done": FINISH}}

        RawSchemaWorkflow.ask.after = _chain_hooks(_rawschemaworkflow_on_ask, RawSchemaWorkflow.ask.after)


def test_validation_rejects_raw_route_payload_schema_without_jsonschema_dependency(monkeypatch):
    raw_schema = {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
        "additionalProperties": False,
    }

    _patch_missing_jsonschema(monkeypatch)

    class RawRoutePayloadSchemaWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {
            ask: {
                "done": Route.finish(payload_schema=raw_schema),
            }
        }

    with pytest.raises(WorkflowCompilationError, match="optional jsonschema dependency"):
        compile_workflow(RawRoutePayloadSchemaWorkflow)


def test_validation_rejects_raw_route_fields_schema_without_jsonschema_dependency(monkeypatch):
    raw_schema = {
        "type": "object",
        "properties": {"reason": {"type": "string"}},
        "required": ["reason"],
        "additionalProperties": False,
    }

    _patch_missing_jsonschema(monkeypatch)

    class RawRouteFieldsSchemaWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {
            ask: {
                "done": Route.finish(route_fields_schema=raw_schema),
            }
        }

    with pytest.raises(WorkflowCompilationError, match="optional jsonschema dependency"):
        compile_workflow(RawRouteFieldsSchemaWorkflow)


def test_validation_allows_helper_default_route_fields_without_jsonschema_dependency(monkeypatch):
    _patch_missing_jsonschema(monkeypatch)

    class HelperDefaultRouteFieldsWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {
            ask: {"done": FINISH},
            GLOBAL: {"question": Route.question(), "blocked": Route.blocked(), "failed": Route.failed()},
        }

    compiled = compile_workflow(HelperDefaultRouteFieldsWorkflow)

    assert compiled.route("ask", "question").route_fields_validator is None
    assert compiled.route("ask", "blocked").route_fields_validator is None
    assert compiled.route("ask", "failed").route_fields_validator is None


def test_validation_allows_helper_default_route_fields_without_jsonschema_dependency_after_named_target_resolution(monkeypatch):
    _patch_missing_jsonschema(monkeypatch)

    class HelperDefaultRouteFieldsNamedTargetWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md")
        followup = PythonStep(name="followup", handler=lambda ctx: Event("done"))
        entry = ask
        transitions = {
            ask: {"done": FINISH},
            followup: {"done": FINISH},
            GLOBAL: {"question": Route.question(target="followup")},
        }

    compiled = compile_workflow(HelperDefaultRouteFieldsNamedTargetWorkflow)

    assert compiled.route("ask", "question").target == "followup"
    assert compiled.route("ask", "question").route_fields_validator is None


def test_validation_rejects_custom_helper_route_fields_override_without_jsonschema_dependency(monkeypatch):
    raw_schema = {
        "type": "object",
        "properties": {
            "questions": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "reason": {"type": ["string", "null"]},
            "severity": {"type": "string"},
        },
        "required": ["questions", "reason", "severity"],
        "additionalProperties": False,
    }

    _patch_missing_jsonschema(monkeypatch)

    class CustomHelperRouteFieldsWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(name="ask", producer="ask.md")
        entry = ask
        transitions = {
            ask: {"done": FINISH},
            GLOBAL: {"question": Route.question(route_fields_schema=raw_schema)},
        }

    with pytest.raises(WorkflowCompilationError, match="optional jsonschema dependency"):
        compile_workflow(CustomHelperRouteFieldsWorkflow)



def test_validation_rejects_system_step_control_contracts():
    class ResultPayload(BaseModel):
        status: str

    with pytest.raises(WorkflowValidationError, match="python_step 'begin' cannot declare expected_output_schema"):

        def _systemcontrolworkflow_on_begin(ctx):
            return Event('done')

        class SystemControlWorkflow(Workflow):
            class State(BaseModel):
                pass

            begin = PythonStep(name="begin", expected_output_schema=ResultPayload, handler=_systemcontrolworkflow_on_begin)
            entry = begin
            transitions = {begin: {"done": FINISH}}



def test_validation_rejects_unknown_route_metadata():
    with pytest.raises(WorkflowValidationError, match="declares route metadata for unknown routes"):

        def _unknownroutemetadataworkflow_on_ask(ctx):
            return None

        class UnknownRouteMetadataWorkflow(Workflow):
            class State(BaseModel):
                pass

            ask = PromptStep(
                name="ask",
                producer="ask.md",
                route_metadata={"missing": "not legal"},
            )
            entry = ask
            transitions = {ask: {"done": FINISH}}

        UnknownRouteMetadataWorkflow.ask.after = _chain_hooks(_unknownroutemetadataworkflow_on_ask, UnknownRouteMetadataWorkflow.ask.after)



def test_validation_allows_application_routes_without_explicit_route_metadata():
    def _missingroutemetadataworkflow_on_ask(ctx):
        return None

    class MissingRouteMetadataWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            route_metadata={"done": "success path"},
        )
        entry = ask
        transitions = {ask: {"done": FINISH, "retry": FINISH}}

    MissingRouteMetadataWorkflow.ask.after = _chain_hooks(_missingroutemetadataworkflow_on_ask, MissingRouteMetadataWorkflow.ask.after)


    compiled = compile_workflow(MissingRouteMetadataWorkflow)

    assert compiled.routes["ask"]["done"].summary == "success path"
    assert compiled.routes["ask"]["retry"].summary == "Routes from 'ask' to 'FINISH'."
    assert {
        route_name: compiled_route.required_writes
        for route_name, compiled_route in compiled.routes["ask"].items()
    } == {
        "done": (),
        "retry": (),
        "question": (),
    }


def test_validation_rejects_route_metadata_unknown_artifacts():
    with pytest.raises(WorkflowValidationError, match="unknown artifact reference"):

        def _unknownartifactroutemetadataworkflow_on_ask(ctx):
            return None

        class UnknownArtifactRouteMetadataWorkflow(Workflow):
            class State(BaseModel):
                pass

            ask = PromptStep(
                name="ask",
                producer="ask.md",
                route_metadata={"done": Route(summary="success path", required_writes=("missing_report",))},
            )
            entry = ask
            transitions = {ask: {"done": FINISH}}

        UnknownArtifactRouteMetadataWorkflow.ask.after = _chain_hooks(_unknownartifactroutemetadataworkflow_on_ask, UnknownArtifactRouteMetadataWorkflow.ask.after)



def test_validation_rejects_route_required_writes_not_produced_by_step():
    with pytest.raises(WorkflowValidationError, match="route required write 'request' is not produced by the step"):

        def _invalidrouterequiredoutputworkflow_on_ask(ctx):
            return None

        class InvalidRouteRequiredOutputWorkflow(Workflow):
            class State(BaseModel):
                pass

            request = Artifact("{task_folder}/request.txt")
            ask = PromptStep(
                name="ask",
                producer="ask.md",
                writes={"report": Artifact.md("report.md")},
            )
            entry = ask
            transitions = {
                ask: {
                    "done": Route.finish(required_writes=("request",)),
                }
            }

        InvalidRouteRequiredOutputWorkflow.ask.after = _chain_hooks(_invalidrouterequiredoutputworkflow_on_ask, InvalidRouteRequiredOutputWorkflow.ask.after)



def test_validation_rejects_route_metadata_required_writes_not_produced_by_step():
    with pytest.raises(WorkflowValidationError, match="route required write 'request' is not produced by the step"):

        def _invalidroutemetadatarequiredoutputworkflow_on_ask(ctx):
            return None

        class InvalidRouteMetadataRequiredOutputWorkflow(Workflow):
            class State(BaseModel):
                pass

            request = Artifact("{task_folder}/request.txt")
            ask = PromptStep(
                name="ask",
                producer="ask.md",
                writes={"report": Artifact.md("report.md")},
                route_metadata={"done": Route(summary="success path", required_writes=("request",))},
            )
            entry = ask
            transitions = {ask: {"done": FINISH}}

        InvalidRouteMetadataRequiredOutputWorkflow.ask.after = _chain_hooks(_invalidroutemetadatarequiredoutputworkflow_on_ask, InvalidRouteMetadataRequiredOutputWorkflow.ask.after)



def test_validation_rejects_conflicting_route_handoff_metadata():
    with pytest.raises(WorkflowValidationError, match="defines conflicting handoff values"):

        def _conflictingroutehandoffworkflow_on_ask(ctx):
            return None

        class ConflictingRouteHandoffWorkflow(Workflow):
            class State(BaseModel):
                pass

            ask = PromptStep(
                name="ask",
                producer="ask.md",
                route_metadata={"done": Route(summary="success path", handoff="Share the draft.")},
            )
            entry = ask
            transitions = {ask: {"done": Route.finish(handoff="Escalate to review.")}}

        ConflictingRouteHandoffWorkflow.ask.after = _chain_hooks(_conflictingroutehandoffworkflow_on_ask, ConflictingRouteHandoffWorkflow.ask.after)



def test_validation_prefers_route_required_writes_over_step_route_metadata_defaults():
    def _explicitrouterequiredoutputworkflow_on_ask(ctx):
        return None

    report_artifact = Artifact("{run_folder}/report.md")

    class ExplicitRouteRequiredOutputWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            writes={"report": report_artifact},
            route_metadata={"done": Route(summary="success path", required_writes=("report", "report"))},
        )
        entry = ask
        transitions = {ask: {"done": Route.finish(required_writes=("report",))}}

    ExplicitRouteRequiredOutputWorkflow.ask.after = _chain_hooks(_explicitrouterequiredoutputworkflow_on_ask, ExplicitRouteRequiredOutputWorkflow.ask.after)


    compiled = compile_workflow(ExplicitRouteRequiredOutputWorkflow)

    assert compiled.routes["ask"]["done"].summary == "success path"
    assert compiled.routes["ask"]["done"].required_writes == ("ask.report",)


def test_validation_allows_pair_route_required_writes_across_do_and_review_artifacts():
    def _pairroutewritesworkflow_on_assess(ctx):
        return None

    class PairRouteWritesWorkflow(Workflow):
        class State(BaseModel):
            pass

        assess = ProduceVerifyStep(
            name="assess",
            producer="assess.md",
            verifier="review.md",
            producer_writes={"draft": Artifact.md("draft.md")},
            verifier_writes={"decision": Artifact.json("decision.json")},
        )
        entry = assess
        transitions = {
            assess: {
                "approved": Route.to(FINISH, required_writes=("draft", "decision")),
                "rejected": Route.to(FINISH, required_writes=("decision",)),
            }
        }

    PairRouteWritesWorkflow.assess.after_verifier = _chain_hooks(_pairroutewritesworkflow_on_assess, PairRouteWritesWorkflow.assess.after_verifier)


    compiled = compile_workflow(PairRouteWritesWorkflow)

    assert compiled.routes["assess"]["approved"].required_writes == (
        "assess.draft",
        "assess.decision",
    )
    assert compiled.routes["assess"]["rejected"].required_writes == ("assess.decision",)


def test_validation_rejects_pair_verifier_requires_artifact_written_only_in_review_phase():
    with pytest.raises(WorkflowValidationError, match="written only during the review phase"):

        def _invalidreviewrequiresworkflow_on_assess(ctx):
            return None

        class InvalidReviewRequiresWorkflow(Workflow):
            class State(BaseModel):
                pass

            assess = ProduceVerifyStep(
                name="assess",
                producer="assess.md",
                verifier="review.md",
                verifier_requires=("decision",),
                producer_writes={"draft": Artifact.md("draft.md")},
                verifier_writes={"decision": Artifact.json("decision.json")},
            )
            entry = assess
            transitions = {assess: {"approved": FINISH}}

        InvalidReviewRequiresWorkflow.assess.after_verifier = _chain_hooks(_invalidreviewrequiresworkflow_on_assess, InvalidReviewRequiresWorkflow.assess.after_verifier)



def test_validation_rejects_legacy_on_start_handler_even_when_step_is_named_start():
    with pytest.raises(WorkflowValidationError, match="legacy workflow-level on_start handlers are no longer supported"):

        class StartNamedWorkflow(Workflow):
            class State(BaseModel):
                pass

            start = PromptStep(name="start", producer="start.md")
            entry = start
            transitions = {start: {"done": FINISH}}

            @staticmethod
            def on_start(state, outcome, artifacts):
                return state


def test_validation_rejects_legacy_on_outcome_handler_even_when_step_is_named_outcome():
    with pytest.raises(WorkflowValidationError, match="legacy workflow-level on_outcome handlers are no longer supported"):

        class OutcomeNamedWorkflow(Workflow):
            class State(BaseModel):
                pass

            outcome = PromptStep(name="outcome", producer="outcome.md")
            entry = outcome
            transitions = {outcome: {"done": FINISH}}

            @staticmethod
            def on_outcome(state, outcome, artifacts):
                return state


def test_validation_rejects_legacy_class_level_step_handler_methods():
    with pytest.raises(WorkflowValidationError, match="legacy class-level step handler 'on_verdict' is no longer supported"):

        class VerdictNamedWorkflow(Workflow):
            class State(BaseModel):
                pass

            verdict = PromptStep(name="verdict", producer="verdict.md")
            entry = verdict
            transitions = {verdict: {"done": FINISH}}

            @staticmethod
            def on_verdict(state, outcome, artifacts):
                return state


def test_validation_rejects_on_verdict_alias_without_matching_step():
    with pytest.raises(WorkflowValidationError, match="orphan handler"):

        def _verdictaliasworkflow_on_ask(ctx):
            return None

        class VerdictAliasWorkflow(Workflow):
            class State(BaseModel):
                pass

            ask = PromptStep(name="ask", producer="ask.md")
            entry = ask
            transitions = {ask: {"done": FINISH}}


            @staticmethod
            def on_verdict(state, outcome):
                return None
        VerdictAliasWorkflow.ask.after = _chain_hooks(_verdictaliasworkflow_on_ask, VerdictAliasWorkflow.ask.after)



def test_validation_rejects_legacy_pair_handler_methods():
    with pytest.raises(WorkflowValidationError, match="legacy class-level step handler 'on_ask' is no longer supported"):

        class LegacyPairHandlerWorkflow(Workflow):
            class State(BaseModel):
                pass

            ask = PromptStep(name="ask", producer="ask.md")
            entry = ask
            transitions = {ask: {"done": FINISH}}

            @staticmethod
            def on_ask(state, outcome):
                return state


def test_validation_rejects_multi_argument_python_step_handler():
    with pytest.raises(WorkflowValidationError, match="python_step 'begin' handler"):

        class LegacySystemHandlerWorkflow(Workflow):
            class State(BaseModel):
                pass

            begin = PythonStep(name="begin", handler=lambda ctx, extra, third: Event("done"))
            entry = begin
            transitions = {begin: {"done": FINISH}}


def test_validation_does_not_infer_after_hook_routes_from_source() -> None:
    class RuntimeValidatedAfterHookWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = PromptStep(
            name="ask",
            producer="ask.md",
            after=lambda ctx: Event("done"),
        )
        entry = ask
        transitions = {ask: {"done": FINISH}}

    compiled = compile_workflow(RuntimeValidatedAfterHookWorkflow)

    assert compiled.steps["ask"].after_hook is not None


def test_validation_rejects_multi_argument_after_hook_signature() -> None:
    with pytest.raises(WorkflowValidationError, match="after hook"):

        class InvalidAfterHookWorkflow(Workflow):
            class State(BaseModel):
                pass

            ask = PromptStep(
                name="ask",
                producer="ask.md",
                after=lambda ctx, event: None,
            )
            entry = ask
            transitions = {ask: {"done": FINISH}}


def test_validation_does_not_infer_after_producer_redirects_from_source() -> None:
    class RuntimeValidatedProducerAfterHookWorkflow(Workflow):
        class State(BaseModel):
            pass

        ask = ProduceVerifyStep(
            name="ask",
            producer="ask-producer.md",
            verifier="ask-verifier.md",
            after_producer=lambda ctx: Event("accepted", handoff="carry this forward"),
        )
        entry = ask
        transitions = {ask: {"accepted": FINISH, "needs_rework": SELF}}

    compiled = compile_workflow(RuntimeValidatedProducerAfterHookWorkflow)

    assert compiled.steps["ask"].after_producer_hook is not None


def test_validation_rejects_multi_argument_after_producer_hook_signature() -> None:
    with pytest.raises(WorkflowValidationError, match="after_producer hook"):

        class InvalidAfterProducerHookWorkflow(Workflow):
            class State(BaseModel):
                pass

            ask = ProduceVerifyStep(
                name="ask",
                producer="ask-producer.md",
                verifier="ask-verifier.md",
                after_producer=lambda ctx, raw_output: None,
            )
            entry = ask
            transitions = {ask: {"accepted": FINISH}}


def test_validation_rejects_static_on_start_signature():
    with pytest.raises(WorkflowValidationError, match="legacy workflow-level on_start handlers are no longer supported"):

        class StaticStartHookWorkflow(Workflow):
            class State(BaseModel):
                pass

            ask = PromptStep(name="ask", producer="ask.md")
            entry = ask
            transitions = {ask: {"done": FINISH}}

            @staticmethod
            def on_start(ctx):
                return None


def test_stdlib_validation_normalizes_optional_and_unique_strings():
    assert normalize_optional_string("  ready  ") == "ready"
    assert normalize_optional_string(None) is None
    assert normalize_unique_strings([" a ", "b", "a", ""], field_name="items") == ["a", "b"]
    assert normalize_unique_strings(" solo ", field_name="items", allow_scalar=True) == ["solo"]
    assert require_non_empty_string(9, error_message="custom text message", coerce=True) == "9"
    assert require_string_list(
        " solo ",
        field_name="items",
        error_message="custom list message",
        allow_scalar=True,
        dedupe=True,
        coerce=True,
    ) == ["solo"]

    with pytest.raises(ValueError, match="items must be a string or null"):
        normalize_optional_string(1, field_name="items", coerce=False)
    with pytest.raises(ValueError, match="items must be a list of non-empty strings"):
        normalize_unique_strings("solo", field_name="items")


def test_stdlib_validation_requires_mappings_positive_ints_and_json_objects(tmp_path):
    payload_path = tmp_path / "payload.json"
    payload_path.write_text('{"status": "ready"}\n', encoding="utf-8")
    bad_payload_path = tmp_path / "payload-list.json"
    bad_payload_path.write_text('["wrong"]\n', encoding="utf-8")

    assert read_json_object(payload_path) == {"status": "ready"}
    assert require_mapping({"status": "ready"}, field_name="payload") == {"status": "ready"}
    assert require_mapping_list([{"status": "ready"}], field_name="payloads") == [{"status": "ready"}]
    assert require_non_negative_int(0, field_name="count") == 0
    assert require_positive_int(2, field_name="count") == 2

    with pytest.raises(ValueError, match="payload-list.json must contain a JSON object"):
        read_json_object(bad_payload_path)
    with pytest.raises(ValueError, match="payload must be a JSON object"):
        require_mapping([], field_name="payload")
    with pytest.raises(ValueError, match="payloads must contain at least 2 item\\(s\\)"):
        require_mapping_list([{"status": "ready"}], field_name="payloads", min_length=2)
    with pytest.raises(ValueError, match="count must be a non-negative integer"):
        require_non_negative_int(-1, field_name="count")
    with pytest.raises(ValueError, match="count must be a positive integer"):
        require_positive_int(True, field_name="count")


def test_stdlib_validation_preserves_custom_messages_and_strict_modes():
    assert normalize_unique_strings([" b ", "a", "b"], field_name="items") == ["b", "a"]
    assert require_string_list(
        [" b ", "a", "b"],
        field_name="items",
        dedupe=True,
        sort_output=True,
    ) == ["a", "b"]

    with pytest.raises(ValueError, match="custom optional message"):
        normalize_optional_string(object(), error_message="custom optional message", coerce=False)
    with pytest.raises(ValueError, match="custom list message"):
        normalize_unique_strings(
            None,
            field_name="items",
            error_message="custom list message",
            allow_none=False,
        )
    with pytest.raises(ValueError, match="custom entry message"):
        normalize_unique_strings(
            ["ok", object()],
            field_name="items",
            item_error_message="custom entry message",
            coerce=False,
        )
    with pytest.raises(ValueError, match="custom text message"):
        require_non_empty_string(None, error_message="custom text message", coerce=True)
    with pytest.raises(ValueError, match="custom required list message"):
        require_string_list(
            [],
            field_name="items",
            error_message="custom required list message",
        )


def test_stdlib_validation_accepts_legacy_positional_error_message_shape():
    with pytest.raises(ValueError, match="positional text message"):
        require_non_empty_string(None, "positional text message", coerce=True)
    with pytest.raises(ValueError, match="positional list message"):
        require_string_list([], "positional list message")
    with pytest.raises(ValueError, match="positional int message"):
        require_positive_int(False, "positional int message")
    with pytest.raises(ValueError, match="positional non-negative int message"):
        require_non_negative_int(False, "positional non-negative int message")
    with pytest.raises(ValueError, match="positional mapping message"):
        require_mapping([], "positional mapping message")
    with pytest.raises(ValueError, match="positional mapping list message"):
        require_mapping_list([[]], "positional mapping list message")


def test_publication_validation_helpers_require_existing_artifacts_and_non_empty_text(tmp_path):
    summary_path = tmp_path / "summary.json"
    notes_path = tmp_path / "notes.md"
    summary_path.write_text('{"status": "ready"}\n', encoding="utf-8")
    notes_path.write_text("  explicit publication boundary  \n", encoding="utf-8")

    required_paths = require_existing_artifact_paths(
        {
            "summary": summary_path,
            "notes": notes_path,
        }
    )

    assert required_paths == {"summary": summary_path, "notes": notes_path}
    assert read_required_text(notes_path, "notes.md must not be empty") == "explicit publication boundary"

    notes_path.write_text(" \n", encoding="utf-8")

    with pytest.raises(ValueError, match="notes.md must not be empty"):
        read_required_text(notes_path, "notes.md must not be empty")

    with pytest.raises(FileNotFoundError, match="missing required publication artifact"):
        require_existing_artifact_paths({"missing": tmp_path / "missing.md"})


def test_publication_validation_helpers_validate_boundary_authoritative_subset_and_ready_flag():
    assert (
        validate_publication_boundary(
            " diagnostic_publication_only ",
            expected_boundary="diagnostic_publication_only",
            missing_error_message="summary must define publication_boundary",
            mismatch_error_message="summary publication_boundary must stay diagnostic_publication_only",
        )
        == "diagnostic_publication_only"
    )
    assert validate_authoritative_artifact_subset(
        ["summary", "next_actions", "receipt"],
        required_artifacts={"summary", "next_actions"},
        missing_error_message="summary must define authoritative_artifacts",
        subset_error_message="summary authoritative_artifacts must include summary and next_actions",
    ) == ["summary", "next_actions", "receipt"]
    assert require_true_flag(True, "summary must confirm ready_for_publication=true") is True

    with pytest.raises(ValueError, match="summary publication_boundary must stay diagnostic_publication_only"):
        validate_publication_boundary(
            "auto_refinement",
            expected_boundary="diagnostic_publication_only",
            missing_error_message="summary must define publication_boundary",
            mismatch_error_message="summary publication_boundary must stay diagnostic_publication_only",
        )
    with pytest.raises(ValueError, match="summary authoritative_artifacts must include summary and next_actions"):
        validate_authoritative_artifact_subset(
            ["summary"],
            required_artifacts={"summary", "next_actions"},
            missing_error_message="summary must define authoritative_artifacts",
            subset_error_message="summary authoritative_artifacts must include summary and next_actions",
        )
    with pytest.raises(ValueError, match="summary must confirm ready_for_publication=true"):
        require_true_flag(False, "summary must confirm ready_for_publication=true")


def test_publication_validation_helpers_extract_workflow_names_from_shared_snapshots():
    capability_snapshot = {
        "workflows": [
            {"workflow_name": "workflow_portfolio_to_operating_system"},
            {"workflow_name": " company_operation_to_recursive_improvement_cycle "},
            {"workflow_name": ""},
        ]
    }
    portfolio_health = {
        "workflows": [
            {"workflow_name": "workflow_portfolio_to_operating_system"},
            {"workflow_name": "company_operation_to_recursive_improvement_cycle"},
        ]
    }

    assert extract_workflow_names_from_capability_snapshot(capability_snapshot) == {
        "workflow_portfolio_to_operating_system",
        "company_operation_to_recursive_improvement_cycle",
    }
    assert extract_workflow_names_from_portfolio_health(portfolio_health) == [
        "workflow_portfolio_to_operating_system",
        "company_operation_to_recursive_improvement_cycle",
    ]


def test_publication_validation_helpers_preserve_snapshot_name_errors():
    with pytest.raises(ValueError, match="workflow_capability_snapshot.json must contain at least one workflow_name"):
        extract_workflow_names_from_capability_snapshot({"workflows": [{"workflow_name": "   "}]})

    with pytest.raises(
        ValueError,
        match="workflow_portfolio_health_snapshot.json scoped workflow names must be unique",
    ):
        extract_workflow_names_from_portfolio_health(
            {
                "workflows": [
                    {"workflow_name": "workflow_portfolio_to_operating_system"},
                    {"workflow_name": "workflow_portfolio_to_operating_system"},
                ]
            }
        )


def test_publication_validation_helpers_reject_invalid_snapshot_shapes():
    with pytest.raises(ValueError, match="workflow_capability_snapshot.json must define a workflows list"):
        extract_workflow_names_from_capability_snapshot({"workflows": {}})

    with pytest.raises(ValueError, match="workflow_capability_snapshot.json workflows entries must be objects"):
        extract_workflow_names_from_capability_snapshot({"workflows": ["workflow_portfolio_to_operating_system"]})

    with pytest.raises(
        ValueError,
        match="workflow_portfolio_health_snapshot.json must define workflow_portfolio_health.workflows as a JSON array of objects",
    ):
        extract_workflow_names_from_portfolio_health({"workflows": {}})


def test_publication_validation_helpers_preserve_missing_messages_and_require_literal_true():
    with pytest.raises(ValueError, match="summary must define publication_boundary"):
        validate_publication_boundary(
            " \n ",
            expected_boundary="diagnostic_publication_only",
            missing_error_message="summary must define publication_boundary",
            mismatch_error_message="summary publication_boundary must stay diagnostic_publication_only",
        )
    with pytest.raises(ValueError, match="summary must define authoritative_artifacts"):
        validate_authoritative_artifact_subset(
            None,
            required_artifacts={"summary", "next_actions"},
            missing_error_message="summary must define authoritative_artifacts",
            subset_error_message="summary authoritative_artifacts must include summary and next_actions",
        )
    with pytest.raises(ValueError, match="summary must confirm ready_for_publication=true"):
        require_true_flag(1, "summary must confirm ready_for_publication=true")


def test_publication_validation_hidden_execution_helpers_reject_implicit_automation_and_allow_negation():
    assert contains_hidden_execution_signal("This workflow will launch the next workflow after publication.") is True
    assert contains_hidden_execution_signal(
        "Keep downstream execution explicit and do not auto-run the next workflow."
    ) is False

    validate_no_hidden_execution_signal(
        "This package stops at publication and does not automatically run downstream work.",
        "text must not imply hidden downstream execution",
    )

    with pytest.raises(ValueError, match="text must not imply hidden downstream execution"):
        validate_no_hidden_execution_signal(
            "The runtime queues the refinement workflow automatically after publication.",
            "text must not imply hidden downstream execution",
        )


def test_stdlib_validation_parameter_validator_factories_preserve_normalization_and_messages():
    class SharedParameterModel(BaseModel):
        task_title: str
        selected_workflow: str
        sponsor_role: str | None = None
        constraints: list[str] = Field(default_factory=list)
        max_runs: int = 25

        _required_task_title = required_text_fields("task_title")
        _required_workflow = required_text_fields(
            "selected_workflow",
            error_message="value must be non-empty",
        )
        _optional_text = optional_text_fields("sponsor_role")
        _repeatable_strings = deduped_string_list_fields("constraints")
        _positive_int = positive_int_fields("max_runs")

    model = SharedParameterModel(
        task_title="  Review release readiness  ",
        selected_workflow="  release_candidate_to_go_no_go  ",
        sponsor_role="  ops  ",
        constraints=["  evidence  ", "evidence", "  ", "rollback"],
        max_runs=3,
    )

    assert model.model_dump() == {
        "task_title": "Review release readiness",
        "selected_workflow": "release_candidate_to_go_no_go",
        "sponsor_role": "ops",
        "constraints": ["evidence", "rollback"],
        "max_runs": 3,
    }

    with pytest.raises(ValueError, match="task_title must be non-empty"):
        SharedParameterModel(
            task_title="   ",
            selected_workflow="workflow_to_eval_suite",
        )
    with pytest.raises(ValueError, match="value must be non-empty"):
        SharedParameterModel(
            task_title="Analyze failures",
            selected_workflow="   ",
        )
    with pytest.raises(ValueError, match="max_runs must be a positive integer"):
        SharedParameterModel(
            task_title="Analyze failures",
            selected_workflow="workflow_run_history_to_failure_modes",
            max_runs=0,
        )


def test_stdlib_validation_parameter_validator_factories_support_custom_messages():
    class StrictParameterModel(BaseModel):
        status_filters: list[str] = Field(default_factory=list)
        max_runs_per_workflow: int = 10

        _status_filters = deduped_string_list_fields(
            "status_filters",
            error_message="status_filters must be a list of non-empty strings",
            item_error_message="status_filters entries must be non-empty strings",
        )
        _positive_int = positive_int_fields(
            "max_runs_per_workflow",
            error_message="must be a positive integer",
        )

    assert StrictParameterModel(
        status_filters=[" paused ", "paused", "failed", "  "],
        max_runs_per_workflow=4,
    ).model_dump() == {
        "status_filters": ["paused", "failed"],
        "max_runs_per_workflow": 4,
    }

    with pytest.raises(ValueError, match="must be a positive integer"):
        StrictParameterModel(max_runs_per_workflow=0)


def test_stdlib_validation_parameter_validator_factories_support_multi_field_reuse():
    class MultiFieldParameterModel(BaseModel):
        task_title: str
        selected_workflow: str
        sponsor_role: str | None = None
        desired_outcome: str | None = None
        constraints: list[str] = Field(default_factory=list)
        evidence_expectations: list[str] = Field(default_factory=list)
        max_tasks: int = 5
        max_runs_per_workflow: int = 10

        _required_text = required_text_fields(
            "task_title",
            "selected_workflow",
            error_message="value must be non-empty",
        )
        _optional_text = optional_text_fields("sponsor_role", "desired_outcome")
        _repeatable_strings = deduped_string_list_fields("constraints", "evidence_expectations")
        _positive_ints = positive_int_fields(
            "max_tasks",
            "max_runs_per_workflow",
            error_message="must be a positive integer",
        )

    model = MultiFieldParameterModel(
        task_title="  audit cycle  ",
        selected_workflow="  workflow_portfolio_to_operating_system  ",
        sponsor_role="  platform  ",
        desired_outcome="   ",
        constraints=["  narrow scope  ", "narrow scope", "focus"],
        evidence_expectations=["  receipts  ", "receipts", "artifacts"],
        max_tasks=3,
        max_runs_per_workflow=2,
    )

    assert model.model_dump() == {
        "task_title": "audit cycle",
        "selected_workflow": "workflow_portfolio_to_operating_system",
        "sponsor_role": "platform",
        "desired_outcome": None,
        "constraints": ["narrow scope", "focus"],
        "evidence_expectations": ["receipts", "artifacts"],
        "max_tasks": 3,
        "max_runs_per_workflow": 2,
    }

    with pytest.raises(ValueError, match="value must be non-empty"):
        MultiFieldParameterModel(
            task_title="ok",
            selected_workflow="   ",
        )
    with pytest.raises(ValueError, match="must be a positive integer"):
        MultiFieldParameterModel(
            task_title="ok",
            selected_workflow="workflow_to_eval_suite",
            max_tasks=0,
        )
