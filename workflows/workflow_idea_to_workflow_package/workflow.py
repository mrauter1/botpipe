"""Workflow-builder package."""

from __future__ import annotations

from pydantic import BaseModel, Field

try:  # pragma: no branch - supports both package and direct repo-root imports
    from autoloop_v3.stdlib.control import event_on_outcome_tags, global_routes, merge_transitions, pause_on_outcome_tags
    from autoloop_v3.stdlib.lifecycle import (
        open_workflow_sessions,
        write_invocation_contract,
        write_publication_receipt,
    )
except ModuleNotFoundError:  # pragma: no cover - direct repo-root import fallback
    from stdlib.control import event_on_outcome_tags, global_routes, merge_transitions, pause_on_outcome_tags
    from stdlib.lifecycle import open_workflow_sessions, write_invocation_contract, write_publication_receipt

from workflow import Artifact, FAIL, PairStep, Session, SUCCESS, SystemStep, Workflow
from workflow.primitives import Event, Outcome

from .contracts import (
    BUILD_PACKAGE_ROUTE_CONTRACTS,
    DESIGN_PACKAGE_ROUTE_CONTRACTS,
    EVALUATE_PACKAGE_ROUTE_CONTRACTS,
    FRAME_CANDIDATE_ROUTE_CONTRACTS,
    CandidateSelectionPayload,
    WorkflowBuildPayload,
    WorkflowDesignPayload,
    WorkflowEvaluationPayload,
)


class WorkflowIdeaToWorkflowPackage(Workflow):
    """Build a workflow package from a workflow idea."""

    name = "workflow_idea_to_workflow_package"

    class State(BaseModel):
        package_name: str = ""
        package_title: str | None = None
        workflow_kind: str = ""
        aliases: list[str] = Field(default_factory=list)
        target_test_command: str = "pytest"
        selected_candidate: str | None = None
        selected_candidate_kind: str | None = None
        design_status: str | None = None
        build_status: str | None = None
        evaluation_status: str | None = None
        published: bool = False

    frame_session = Session()
    design_session = Session()
    build_session = Session()
    evaluate_session = Session()

    request = Artifact("{run_folder}/request.md")
    framework_architecture_doc = Artifact("{package_folder}/../../docs/architecture.md")
    framework_authoring_doc = Artifact("{package_folder}/../../docs/authoring.md")
    workflow_instructions = Artifact("{package_folder}/../../Workflow_Instructions.md")
    core_steps_module = Artifact("{package_folder}/../../core/steps.py")
    core_validation_module = Artifact("{package_folder}/../../core/validation.py")
    core_compiler_module = Artifact("{package_folder}/../../core/compiler.py")
    core_engine_module = Artifact("{package_folder}/../../core/engine.py")
    runtime_cli_module = Artifact("{package_folder}/../../runtime/cli.py")
    existing_workflow_init = Artifact("{package_folder}/../autoloop_v1/__init__.py")
    existing_workflow_manifest = Artifact("{package_folder}/../autoloop_v1/workflow.toml")
    existing_workflow_definition = Artifact("{package_folder}/../autoloop_v1/workflow.py")
    existing_workflow_prompts = Artifact("{package_folder}/../autoloop_v1/prompts/README.md")
    builder_checklist = Artifact("{package_folder}/assets/workflow_package_checklist.md")

    invocation_contract = Artifact("{workflow_folder}/invocation_contract.json")
    candidate_comparison = Artifact("{workflow_folder}/candidate_comparison.md")
    selected_workflow_brief = Artifact("{workflow_folder}/selected_workflow_brief.md")
    workflow_package_spec = Artifact("{workflow_folder}/workflow_package_spec.md")
    step_contracts = Artifact("{workflow_folder}/step_contracts.json")
    prompt_contract_matrix = Artifact("{workflow_folder}/prompt_contract_matrix.md")
    verification_plan = Artifact("{workflow_folder}/verification_plan.md")
    build_report = Artifact("{workflow_folder}/build_report.md")
    verification_report = Artifact("{workflow_folder}/verification_report.md")
    promotion_record = Artifact("{workflow_folder}/promotion_record.md")
    rollback_plan = Artifact("{workflow_folder}/rollback_plan.md")
    publish_receipt = Artifact("{workflow_folder}/publish_receipt.json")

    generated_package_root = Artifact("{package_folder}/../{state.package_name}")
    generated_init = Artifact("{package_folder}/../{state.package_name}/__init__.py")
    generated_params = Artifact("{package_folder}/../{state.package_name}/params.py")
    generated_contracts = Artifact("{package_folder}/../{state.package_name}/contracts.py")
    generated_workflow = Artifact("{package_folder}/../{state.package_name}/workflow.py")
    generated_manifest = Artifact("{package_folder}/../{state.package_name}/workflow.toml")
    generated_prompts_dir = Artifact("{package_folder}/../{state.package_name}/prompts")
    generated_assets_dir = Artifact("{package_folder}/../{state.package_name}/assets")
    generated_prompt_index = Artifact("{package_folder}/../{state.package_name}/prompts/README.md")
    generated_doc = Artifact("{package_folder}/../../docs/workflows/{state.package_name}.md")
    generated_test = Artifact("{package_folder}/../../tests/runtime/test_{state.package_name}.py")

    bootstrap = SystemStep(
        name="bootstrap",
        requires=[request],
        produces={"invocation_contract": invocation_contract},
    )
    frame_candidate = PairStep(
        name="frame_candidate",
        session=frame_session,
        producer="prompts/frame_producer.md",
        verifier="prompts/frame_verifier.md",
        requires=[
            request,
            invocation_contract,
            framework_architecture_doc,
            framework_authoring_doc,
            workflow_instructions,
            existing_workflow_manifest,
            existing_workflow_definition,
            existing_workflow_prompts,
        ],
        produces={
            "candidate_comparison": candidate_comparison,
            "selected_workflow_brief": selected_workflow_brief,
        },
        expected_output_schema=CandidateSelectionPayload,
        route_contracts=FRAME_CANDIDATE_ROUTE_CONTRACTS,
    )
    design_package = PairStep(
        name="design_package",
        session=design_session,
        producer="prompts/design_producer.md",
        verifier="prompts/design_verifier.md",
        requires=[
            request,
            invocation_contract,
            framework_architecture_doc,
            framework_authoring_doc,
            workflow_instructions,
            core_steps_module,
            core_validation_module,
            core_compiler_module,
            core_engine_module,
            runtime_cli_module,
            builder_checklist,
            candidate_comparison,
            selected_workflow_brief,
        ],
        produces={
            "workflow_package_spec": workflow_package_spec,
            "step_contracts": step_contracts,
            "prompt_contract_matrix": prompt_contract_matrix,
            "verification_plan": verification_plan,
        },
        expected_output_schema=WorkflowDesignPayload,
        route_contracts=DESIGN_PACKAGE_ROUTE_CONTRACTS,
    )
    build_package = PairStep(
        name="build_package",
        session=build_session,
        producer="prompts/build_producer.md",
        verifier="prompts/build_verifier.md",
        requires=[
            request,
            invocation_contract,
            selected_workflow_brief,
            workflow_package_spec,
            step_contracts,
            prompt_contract_matrix,
            verification_plan,
            runtime_cli_module,
            existing_workflow_init,
            existing_workflow_manifest,
            existing_workflow_definition,
            builder_checklist,
        ],
        produces={
            "generated_package_root": generated_package_root,
            "generated_init": generated_init,
            "generated_params": generated_params,
            "generated_contracts": generated_contracts,
            "generated_workflow": generated_workflow,
            "generated_manifest": generated_manifest,
            "generated_prompts_dir": generated_prompts_dir,
            "generated_assets_dir": generated_assets_dir,
            "generated_prompt_index": generated_prompt_index,
            "generated_doc": generated_doc,
            "generated_test": generated_test,
            "build_report": build_report,
        },
        expected_output_schema=WorkflowBuildPayload,
        route_contracts=BUILD_PACKAGE_ROUTE_CONTRACTS,
    )
    evaluate_package = PairStep(
        name="evaluate_package",
        session=evaluate_session,
        producer="prompts/evaluate_producer.md",
        verifier="prompts/evaluate_verifier.md",
        requires=[
            request,
            invocation_contract,
            workflow_package_spec,
            step_contracts,
            prompt_contract_matrix,
            verification_plan,
            build_report,
            generated_package_root,
            generated_init,
            generated_params,
            generated_contracts,
            generated_workflow,
            generated_manifest,
            generated_prompts_dir,
            generated_assets_dir,
            generated_prompt_index,
            generated_doc,
            generated_test,
        ],
        produces={
            "verification_report": verification_report,
            "promotion_record": promotion_record,
            "rollback_plan": rollback_plan,
        },
        expected_output_schema=WorkflowEvaluationPayload,
        route_contracts=EVALUATE_PACKAGE_ROUTE_CONTRACTS,
    )
    publish_package = SystemStep(
        name="publish_package",
        requires=[promotion_record, rollback_plan],
        produces={"publish_receipt": publish_receipt},
    )

    entry = bootstrap

    transitions = merge_transitions(
        global_routes(pause_on_outcome_tags("question", "blocked"), failed=FAIL),
        {
            bootstrap: {"inputs_prepared": frame_candidate},
            frame_candidate: {
                "candidate_selected": design_package,
                "needs_rework": frame_candidate,
                "needs_replan": frame_candidate,
            },
            design_package: {
                "design_accepted": build_package,
                "needs_rework": design_package,
                "needs_replan": frame_candidate,
            },
            build_package: {
                "package_built": evaluate_package,
                "needs_rework": build_package,
                "needs_replan": design_package,
            },
            evaluate_package: {
                "evaluation_passed": publish_package,
                "needs_rework": build_package,
                "needs_replan": design_package,
            },
            publish_package: {"package_published": SUCCESS},
        },
    )

    @staticmethod
    def on_bootstrap(state: State, ctx) -> tuple[State, Event]:
        payload = dict(ctx.workflow_params)
        package_name = str(payload.get("package_name") or "").strip()
        workflow_kind = str(payload.get("workflow_kind") or "").strip()
        if not package_name or not workflow_kind:
            raise ValueError(
                "workflow_idea_to_workflow_package requires workflow parameters 'package_name' and 'workflow_kind'"
            )

        next_state = state.model_copy(
            update={
                "package_name": package_name,
                "package_title": payload.get("package_title"),
                "workflow_kind": workflow_kind,
                "aliases": list(payload.get("aliases") or []),
                "target_test_command": str(payload.get("target_test_command") or "pytest").strip() or "pytest",
                "selected_candidate": None,
                "selected_candidate_kind": None,
                "design_status": None,
                "build_status": None,
                "evaluation_status": None,
                "published": False,
            }
        )
        open_workflow_sessions(ctx, "frame_session", "design_session", "build_session", "evaluate_session")
        write_invocation_contract(
            ctx,
            {
                "package_name": next_state.package_name,
                "package_title": next_state.package_title,
                "workflow_kind": next_state.workflow_kind,
                "aliases": next_state.aliases,
                "target_test_command": next_state.target_test_command,
            },
        )
        return next_state, Event("inputs_prepared")

    @staticmethod
    def on_frame_candidate(state: State, outcome: Outcome, artifacts):
        del artifacts
        if outcome.tag != "candidate_selected":
            return state
        selected_candidate = outcome.payload.get("selected_candidate")
        selected_kind = outcome.payload.get("selected_kind")
        return state.model_copy(
            update={
                "selected_candidate": selected_candidate if isinstance(selected_candidate, str) else state.package_name,
                "selected_candidate_kind": (
                    selected_kind if isinstance(selected_kind, str) else state.workflow_kind
                ),
            }
        )

    @staticmethod
    def on_design_package(state: State, outcome: Outcome, artifacts):
        del artifacts
        return state.model_copy(update={"design_status": outcome.tag})

    @staticmethod
    def on_build_package(state: State, outcome: Outcome, artifacts):
        del artifacts
        return state.model_copy(update={"build_status": outcome.tag})

    @staticmethod
    def on_evaluate_package(state: State, outcome: Outcome, artifacts):
        del artifacts
        return state.model_copy(update={"evaluation_status": outcome.tag})

    @staticmethod
    def on_publish_package(state: State, ctx) -> tuple[State, Event]:
        promotion_path = ctx.workflow_folder / "promotion_record.md"
        rollback_path = ctx.workflow_folder / "rollback_plan.md"
        if not promotion_path.exists():
            raise FileNotFoundError(f"missing promotion record at {promotion_path}")
        if not rollback_path.exists():
            raise FileNotFoundError(f"missing rollback plan at {rollback_path}")
        write_publication_receipt(
            ctx,
            "publish_receipt.json",
            {
                "workflow_name": ctx.workflow_name,
                "package_name": state.package_name,
                "selected_candidate": state.selected_candidate or state.package_name,
                "published": True,
                "promotion_record": str(promotion_path),
                "rollback_plan": str(rollback_path),
            },
        )
        return state.model_copy(update={"published": True}), Event("package_published")

    on_outcome = staticmethod(event_on_outcome_tags("question", "blocked", "failed"))


__all__ = ["WorkflowIdeaToWorkflowPackage"]
