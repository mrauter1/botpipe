"""Workflow-builder package."""

from __future__ import annotations

from pydantic import BaseModel, Field

from autoloop.stdlib.lifecycle import open_workflow_sessions, write_invocation_contract, write_publication_receipt

from autoloop import Event, FAIL, FINISH, Outcome, Prompt, Session, Workflow, produce_verify_step, python_step
from autoloop.core import Artifact

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


def _after_frame_candidate(ctx, outcome: Outcome):
    if outcome.tag != "candidate_selected":
        return ctx.state
    selected_candidate = outcome.payload.get("selected_candidate")
    selected_kind = outcome.payload.get("selected_kind")
    return ctx.state.model_copy(
        update={
            "selected_candidate": (
                selected_candidate if isinstance(selected_candidate, str) else ctx.state.package_name
            ),
            "selected_candidate_kind": (
                selected_kind if isinstance(selected_kind, str) else ctx.state.workflow_kind
            ),
        }
    )


def _after_design_package(ctx, outcome: Outcome):
    return ctx.state.model_copy(update={"design_status": outcome.tag})


def _after_build_package(ctx, outcome: Outcome):
    return ctx.state.model_copy(update={"build_status": outcome.tag})


def _after_evaluate_package(ctx, outcome: Outcome):
    return ctx.state.model_copy(update={"evaluation_status": outcome.tag})


class WorkflowIdeaToWorkflowPackage(Workflow):
    """Build a workflow package from a workflow idea."""

    name = "workflow_idea_to_workflow_package"

    class State(BaseModel):
        package_name: str = ""
        package_title: str | None = None
        workflow_kind: str = ""
        authoring_shape: str = "flow_specs"
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
    generated_single_file = Artifact("{package_folder}/../{state.package_name}.py")
    generated_flow = Artifact("{package_folder}/../{state.package_name}/flow.py")
    generated_specs = Artifact("{package_folder}/../{state.package_name}/specs.py")
    generated_init = Artifact("{package_folder}/../{state.package_name}/__init__.py")
    generated_manifest = Artifact("{package_folder}/../{state.package_name}/workflow.toml")
    generated_prompts_dir = Artifact("{package_folder}/../{state.package_name}/prompts")
    generated_assets_dir = Artifact("{package_folder}/../{state.package_name}/assets")
    generated_prompt_index = Artifact("{package_folder}/../{state.package_name}/prompts/README.md")
    generated_layout = Artifact("{workflow_folder}/generated_layout.json")
    generated_doc = Artifact("{package_folder}/../../docs/workflows/{state.package_name}.md")
    generated_test = Artifact("{package_folder}/../../tests/runtime/test_{state.package_name}.py")

    frame_candidate = produce_verify_step(
        producer_prompt=Prompt.file("prompts/frame_producer.md"),
        verifier_prompt=Prompt.file("prompts/frame_verifier.md"),
        session=frame_session,
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
        producer_writes=[candidate_comparison, selected_workflow_brief],
        control_schema=CandidateSelectionPayload,
        routes=FRAME_CANDIDATE_ROUTE_CONTRACTS,
        after_verifier=_after_frame_candidate,
    )
    design_package = produce_verify_step(
        producer_prompt=Prompt.file("prompts/design_producer.md"),
        verifier_prompt=Prompt.file("prompts/design_verifier.md"),
        session=design_session,
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
        producer_writes=[workflow_package_spec, step_contracts, prompt_contract_matrix, verification_plan],
        control_schema=WorkflowDesignPayload,
        routes=DESIGN_PACKAGE_ROUTE_CONTRACTS,
        after_verifier=_after_design_package,
    )
    build_package = produce_verify_step(
        producer_prompt=Prompt.file("prompts/build_producer.md"),
        verifier_prompt=Prompt.file("prompts/build_verifier.md"),
        session=build_session,
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
        producer_writes=[
            generated_package_root,
            generated_single_file,
            generated_flow,
            generated_specs,
            generated_init,
            generated_manifest,
            generated_prompts_dir,
            generated_assets_dir,
            generated_prompt_index,
            generated_layout,
            generated_doc,
            generated_test,
            build_report,
        ],
        control_schema=WorkflowBuildPayload,
        routes=BUILD_PACKAGE_ROUTE_CONTRACTS,
        after_verifier=_after_build_package,
    )
    evaluate_package = produce_verify_step(
        producer_prompt=Prompt.file("prompts/evaluate_producer.md"),
        verifier_prompt=Prompt.file("prompts/evaluate_verifier.md"),
        session=evaluate_session,
        requires=[
            request,
            invocation_contract,
            workflow_package_spec,
            step_contracts,
            prompt_contract_matrix,
            verification_plan,
            build_report,
            generated_layout,
        ],
        producer_writes=[verification_report, promotion_record, rollback_plan],
        control_schema=WorkflowEvaluationPayload,
        routes=EVALUATE_PACKAGE_ROUTE_CONTRACTS,
        after_verifier=_after_evaluate_package,
    )
    @python_step(
        name="bootstrap",
        requires=[request],
        writes=[invocation_contract],
        routes={"inputs_prepared": "frame_candidate"},
    )
    def bootstrap(state: State, ctx):
        params = ctx.params
        next_state = state.model_copy(
            update={
                "package_name": params.package_name,
                "package_title": params.package_title,
                "workflow_kind": params.workflow_kind,
                "authoring_shape": params.authoring_shape,
                "aliases": list(params.aliases),
                "target_test_command": params.target_test_command,
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
                "authoring_shape": next_state.authoring_shape,
                "aliases": next_state.aliases,
                "target_test_command": next_state.target_test_command,
            },
        )
        ctx.state = next_state
        return "inputs_prepared"

    @python_step(
        name="publish_package",
        requires=[promotion_record, rollback_plan],
        writes=[publish_receipt],
        routes={"package_published": FINISH},
    )
    def publish_package(state: State, ctx):
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
        ctx.state = state.model_copy(update={"published": True})
        return "package_published"

    entry = bootstrap


__all__ = ["WorkflowIdeaToWorkflowPackage"]
