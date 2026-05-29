"""Provider-heavy workflow that recreates a codebase as a Botpipe workflow."""

from __future__ import annotations

from pydantic import BaseModel

from botpipe import FINISH, Prompt, Route, Session, Workflow, produce_verify_step, python_step
from botpipe.core import Artifact
from botpipe.stdlib.lifecycle import (
    open_workflow_sessions,
    write_invocation_contract,
    write_publication_receipt,
    write_workflow_json,
)

from .contracts import (
    BEHAVIOR_DISTILLATION_ROUTE_CONTRACTS,
    BUILD_VALIDATION_ROUTE_CONTRACTS,
    WORKFLOW_DESIGN_ROUTE_CONTRACTS,
    BehaviorDistillationPayload,
    BuildValidationPayload,
    WorkflowDesignPayload,
)
from .params import Params
from .specs import (
    capture_source_manifest,
    collect_trace_corpus,
    derive_generated_workflow_name,
    validate_publication_inputs,
)


def _after_distill_behavior(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    ctx.state.behavior_status = outcome.tag
    return None


def _after_design_botpipe_recreation(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    ctx.state.design_status = outcome.tag
    return None


def _after_build_and_validate(ctx):
    outcome = ctx.outcome
    assert outcome is not None
    ctx.state.build_status = outcome.tag
    return None


class CodeToWorkflow(Workflow):
    """Read the current workspace and generate an equivalent Botpipe workflow."""

    name = "code_to_workflow"
    Params = Params

    class State(BaseModel):
        generated_workflow_name: str = ""
        generated_workflow_root: str = ""
        behavior_status: str | None = None
        design_status: str | None = None
        build_status: str | None = None
        published: bool = False

    behavior_session = Session.run()
    behavior_verifier_session = Session.run()
    authoring_session = Session.run()
    design_verifier_session = Session.run()
    build_verifier_session = Session.run()

    request = Artifact("{{ run.folder }}/request.md", name="request")
    workflow_authoring_guidelines = Artifact(
        "{{ root }}/docs/workflow_authoring_guidelines.md",
        name="workflow_authoring_guidelines",
    )
    botpipe_workflow_authoring_skill = Artifact.md(
        "{{ package.folder }}/skills/botpipe-workflow-autoring.md",
        name="botpipe_workflow_authoring_skill",
        required=True,
    )
    ralph_loop_workflow = Artifact(
        "{{ package.folder }}/../ralph_loop/workflow.py",
        name="ralph_loop_workflow",
    )
    devloop_workflow = Artifact(
        "{{ package.folder }}/../devloop/workflow.py",
        name="devloop_workflow",
    )

    invocation_contract = Artifact.json(
        "{{ workflow.folder }}/invocation_contract.json",
        name="invocation_contract",
        required=True,
    )
    source_manifest = Artifact.json(
        "{{ workflow.folder }}/source_manifest.json",
        name="source_manifest",
        required=True,
    )
    trace_corpus = Artifact.json(
        "{{ workflow.folder }}/trace_corpus.json",
        name="trace_corpus",
        required=True,
    )
    behavior_inventory = Artifact.json(
        "{{ workflow.folder }}/behavior_inventory.json",
        name="behavior_inventory",
        required=True,
    )
    behavior_inventory_report = Artifact.md(
        "{{ workflow.folder }}/behavior_inventory.md",
        name="behavior_inventory_report",
        required=True,
    )
    trace_pattern_notes = Artifact.md(
        "{{ workflow.folder }}/trace_pattern_notes.md",
        name="trace_pattern_notes",
        required=True,
    )
    behavior_review = Artifact.md(
        "{{ workflow.folder }}/behavior_review.md",
        name="behavior_review",
        required=False,
    )
    workflow_design = Artifact.md(
        "{{ workflow.folder }}/workflow_design.md",
        name="workflow_design",
        required=True,
    )
    step_contracts = Artifact.json(
        "{{ workflow.folder }}/step_contracts.json",
        name="step_contracts",
        required=True,
    )
    prompt_contract_matrix = Artifact.md(
        "{{ workflow.folder }}/prompt_contract_matrix.md",
        name="prompt_contract_matrix",
        required=True,
    )
    equivalence_plan = Artifact.md(
        "{{ workflow.folder }}/equivalence_plan.md",
        name="equivalence_plan",
        required=True,
    )
    coverage_map = Artifact.json(
        "{{ workflow.folder }}/coverage_map.json",
        name="coverage_map",
        required=True,
    )
    design_review = Artifact.md(
        "{{ workflow.folder }}/design_review.md",
        name="design_review",
        required=False,
    )
    generated_workflow_root = Artifact.raw(
        "{{ root }}/.botpipe/workflows/{{ state.generated_workflow_name }}",
        name="generated_workflow_root",
        required=True,
    )
    generated_flow = Artifact.text(
        "{{ root }}/.botpipe/workflows/{{ state.generated_workflow_name }}/flow.py",
        name="generated_flow",
        required=True,
    )
    generated_manifest = Artifact.text(
        "{{ root }}/.botpipe/workflows/{{ state.generated_workflow_name }}/workflow.toml",
        name="generated_manifest",
        required=True,
    )
    generated_layout = Artifact.json(
        "{{ workflow.folder }}/generated_layout.json",
        name="generated_layout",
        required=True,
    )
    validation_report = Artifact.md(
        "{{ workflow.folder }}/validation_report.md",
        name="validation_report",
        required=True,
    )
    build_review = Artifact.md(
        "{{ workflow.folder }}/build_review.md",
        name="build_review",
        required=False,
    )
    publication_receipt = Artifact.json(
        "{{ workflow.folder }}/publication_receipt.json",
        name="publication_receipt",
        required=True,
    )

    distill_behavior = produce_verify_step(
        producer_prompt=Prompt.file("prompts/distill_behavior_producer.md"),
        verifier_prompt=Prompt.file("prompts/distill_behavior_verifier.md"),
        session=behavior_session,
        verifier_session=behavior_verifier_session,
        requires=[request, invocation_contract, source_manifest, trace_corpus],
        reads=[behavior_review],
        producer_writes=[behavior_inventory, behavior_inventory_report, trace_pattern_notes],
        verifier_requires=[request, invocation_contract, source_manifest, trace_corpus],
        verifier_reads=[behavior_review],
        verifier_writes=[behavior_review],
        control_schema=BehaviorDistillationPayload,
        routes=BEHAVIOR_DISTILLATION_ROUTE_CONTRACTS,
        after_verifier=_after_distill_behavior,
    )
    design_botpipe_recreation = produce_verify_step(
        producer_prompt=Prompt.file("prompts/design_recreation_producer.md"),
        verifier_prompt=Prompt.file("prompts/design_recreation_verifier.md"),
        session=authoring_session,
        verifier_session=design_verifier_session,
        requires=[
            request,
            invocation_contract,
            source_manifest,
            behavior_inventory,
            behavior_inventory_report,
            trace_pattern_notes,
        ],
        reads=[
            workflow_authoring_guidelines,
            botpipe_workflow_authoring_skill,
            ralph_loop_workflow,
            devloop_workflow,
            design_review,
        ],
        producer_writes=[
            workflow_design,
            step_contracts,
            prompt_contract_matrix,
            equivalence_plan,
            coverage_map,
        ],
        verifier_requires=[
            request,
            invocation_contract,
            source_manifest,
            behavior_inventory,
            behavior_inventory_report,
            trace_pattern_notes,
            behavior_review,
        ],
        verifier_reads=[
            workflow_authoring_guidelines,
            botpipe_workflow_authoring_skill,
            ralph_loop_workflow,
            devloop_workflow,
            design_review,
        ],
        verifier_writes=[design_review],
        control_schema=WorkflowDesignPayload,
        routes=WORKFLOW_DESIGN_ROUTE_CONTRACTS,
        after_verifier=_after_design_botpipe_recreation,
    )
    build_and_validate = produce_verify_step(
        producer_prompt=Prompt.file("prompts/build_and_validate_producer.md"),
        verifier_prompt=Prompt.file("prompts/build_and_validate_verifier.md"),
        session=authoring_session,
        verifier_session=build_verifier_session,
        requires=[
            request,
            invocation_contract,
            source_manifest,
            trace_corpus,
            behavior_inventory,
            behavior_inventory_report,
            trace_pattern_notes,
            behavior_review,
            workflow_design,
            step_contracts,
            prompt_contract_matrix,
            equivalence_plan,
            coverage_map,
            design_review,
        ],
        reads=[workflow_authoring_guidelines, botpipe_workflow_authoring_skill, build_review],
        verifier_requires=[
            request,
            invocation_contract,
            source_manifest,
            trace_corpus,
            behavior_inventory,
            behavior_inventory_report,
            trace_pattern_notes,
            behavior_review,
            workflow_design,
            step_contracts,
            prompt_contract_matrix,
            equivalence_plan,
            coverage_map,
            design_review,
        ],
        verifier_reads=[workflow_authoring_guidelines, botpipe_workflow_authoring_skill, build_review],
        producer_writes=[
            generated_workflow_root,
            generated_flow,
            generated_manifest,
            generated_layout,
            validation_report,
        ],
        verifier_writes=[build_review],
        control_schema=BuildValidationPayload,
        routes=BUILD_VALIDATION_ROUTE_CONTRACTS,
        after_verifier=_after_build_and_validate,
    )

    @python_step(
        name="bootstrap_capture",
        requires=[request],
        writes=[invocation_contract, source_manifest, trace_corpus],
        routes={
            "captured": Route.to(
                "distill_behavior",
                required_writes=["invocation_contract", "source_manifest", "trace_corpus"],
            )
        },
    )
    def bootstrap_capture(ctx):
        generated_workflow_name = derive_generated_workflow_name(ctx.root, ctx.params.generated_workflow_name)
        generated_workflow_root = ctx.root / ".botpipe" / "workflows" / generated_workflow_name
        next_state = ctx.state.model_copy(
            update={
                "generated_workflow_name": generated_workflow_name,
                "generated_workflow_root": str(generated_workflow_root),
                "behavior_status": None,
                "design_status": None,
                "build_status": None,
                "published": False,
            }
        )
        ctx.state = next_state
        open_workflow_sessions(
            ctx,
            "behavior_session",
            "behavior_verifier_session",
            "authoring_session",
            "design_verifier_session",
            "build_verifier_session",
        )
        write_invocation_contract(
            ctx,
            {
                "generated_workflow_name": generated_workflow_name,
                "generated_workflow_root": str(generated_workflow_root),
                "source_root": str(ctx.root),
                "equivalence_default": "externally observable behavior",
                "generated_output_policy": ".botpipe/workflows/<generated_workflow_name>",
            },
        )
        write_workflow_json(
            ctx,
            "source_manifest.json",
            capture_source_manifest(ctx.root, generated_workflow_name=generated_workflow_name),
        )
        write_workflow_json(
            ctx,
            "trace_corpus.json",
            collect_trace_corpus(ctx.root, exclude_run_dir=ctx.run_folder),
        )
        return "captured"

    @python_step(
        name="publish_generated_workflow",
        requires=[generated_flow, generated_manifest, generated_layout, validation_report, coverage_map, behavior_inventory],
        writes=[publication_receipt],
        routes={"published": FINISH},
    )
    def publish_generated_workflow(ctx):
        payload = validate_publication_inputs(
            root=ctx.root,
            workflow_folder=ctx.workflow_folder,
            generated_workflow_name=ctx.state.generated_workflow_name,
        )
        write_publication_receipt(ctx, "publication_receipt.json", payload)
        ctx.state.published = True
        return "published"

    entry = bootstrap_capture


__all__ = ["CodeToWorkflow"]
