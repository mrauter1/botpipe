"""Recreate a codebase as a Botpipe durable-function workflow."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from botpipe import Artifact, Prompt, Provider, Session, activity, current_run, workflow

from .contracts import (
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


class CodeToWorkflowResult(BaseModel):
    generated_workflow_name: str
    generated_workflow_root: str
    publication_receipt: str
    behavior_status: str
    design_status: str
    build_status: str


@activity
def _bootstrap_capture(
    workspace: str,
    run_folder: str,
    generated_workflow_name: str,
) -> dict[str, str]:
    root = Path(workspace)
    folder = Path(run_folder)
    folder.mkdir(parents=True, exist_ok=True)
    generated_root = root / ".botpipe" / "workflows" / generated_workflow_name
    payloads = {
        "invocation_contract.json": {
            "generated_workflow_name": generated_workflow_name,
            "generated_workflow_root": str(generated_root),
            "source_root": str(root),
            "equivalence_default": "externally observable behavior",
            "generated_output_policy": ".botpipe/workflows/<generated_workflow_name>",
        },
        "source_manifest.json": capture_source_manifest(
            root, generated_workflow_name=generated_workflow_name
        ),
        "trace_corpus.json": collect_trace_corpus(root, exclude_run_dir=folder),
    }
    paths: dict[str, str] = {}
    for filename, payload in payloads.items():
        path = folder / filename
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        paths[filename] = str(path)
    return paths


@activity
def _publish(workspace: str, run_folder: str, generated_workflow_name: str) -> str:
    payload = validate_publication_inputs(
        root=Path(workspace),
        workflow_folder=Path(run_folder),
        generated_workflow_name=generated_workflow_name,
    )
    path = Path(run_folder) / "publication_receipt.json"
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return str(path)


def _read_specs(folder: Path) -> tuple[Artifact, Artifact, Artifact]:
    return (
        Artifact.json(
            str(folder / "invocation_contract.json"),
            name="invocation_contract",
            required=True,
        ),
        Artifact.json(
            str(folder / "source_manifest.json"), name="source_manifest", required=True
        ),
        Artifact.json(
            str(folder / "trace_corpus.json"), name="trace_corpus", required=True
        ),
    )


@workflow(name="code_to_workflow", version="1")
def code_to_workflow(
    request: str, generated_workflow_name: str | None = None
) -> CodeToWorkflowResult:
    ctx = current_run()
    name = derive_generated_workflow_name(
        ctx.workspace,
        Params(generated_workflow_name=generated_workflow_name).generated_workflow_name,
    )
    generated_root = ctx.workspace / ".botpipe" / "workflows" / name
    _bootstrap_capture(str(ctx.workspace), str(ctx.folder), name)
    invocation_contract, source_manifest, trace_corpus = _read_specs(ctx.folder)

    base = Provider()
    behavior_provider = base.with_config(session=Session())
    behavior_verifier = base.with_config(session=None)
    authoring_provider = base.with_config(session=Session())
    design_verifier = base.with_config(session=None)
    build_verifier = base.with_config(session=None)

    behavior_inventory = Artifact.json("behavior_inventory.json", required=True)
    behavior_report = Artifact.md(
        "behavior_inventory.md", name="behavior_inventory_report", required=True
    )
    trace_notes = Artifact.md("trace_pattern_notes.md", required=True)
    behavior_review = Artifact.md("behavior_review.md", required=True)
    design_review = Artifact.md("design_review.md", required=True)
    build_review = Artifact.md("build_review.md", required=True)

    behavior_feedback = ()
    while True:
        distilled = behavior_provider.run(
            Prompt.file("prompts/distill_behavior_producer.md"),
            input={"request": request, "generated_workflow_name": name},
            reads=(
                invocation_contract.path,
                source_manifest.path,
                trace_corpus.path,
                *behavior_feedback,
            ),
            writes=(behavior_inventory, behavior_report, trace_notes),
        )
        behavior_check = behavior_verifier.run(
            Prompt.file("prompts/distill_behavior_verifier.md"),
            input={"request": request, "generated_workflow_name": name},
            reads=(
                invocation_contract.path,
                source_manifest.path,
                trace_corpus.path,
                distilled.artifacts.behavior_inventory,
                distilled.artifacts.behavior_inventory_report,
                distilled.artifacts.trace_pattern_notes,
            ),
            writes=(behavior_review,),
            returns=BehaviorDistillationPayload,
        )
        if behavior_check.value.verdict == "behavior_distilled":
            break
        behavior_feedback = (behavior_check.artifacts.behavior_review,)

    pending_design_feedback: tuple = ()
    while True:
        design_feedback = pending_design_feedback
        pending_design_feedback = ()
        replan_behavior = False
        while True:
            workflow_design = Artifact.md("workflow_design.md", required=True)
            step_contracts = Artifact.json("step_contracts.json", required=True)
            prompt_matrix = Artifact.md("prompt_contract_matrix.md", required=True)
            equivalence_plan = Artifact.md("equivalence_plan.md", required=True)
            coverage_map = Artifact.json("coverage_map.json", required=True)
            designed = authoring_provider.run(
                Prompt.file("prompts/design_recreation_producer.md"),
                input={"request": request, "generated_workflow_name": name},
                reads=(
                    invocation_contract.path,
                    source_manifest.path,
                    distilled.artifacts.behavior_inventory,
                    distilled.artifacts.behavior_inventory_report,
                    distilled.artifacts.trace_pattern_notes,
                    behavior_check.artifacts.behavior_review,
                    *design_feedback,
                ),
                writes=(
                    workflow_design,
                    step_contracts,
                    prompt_matrix,
                    equivalence_plan,
                    coverage_map,
                ),
            )
            design_check = design_verifier.run(
                Prompt.file("prompts/design_recreation_verifier.md"),
                input={"request": request, "generated_workflow_name": name},
                reads=(
                    invocation_contract.path,
                    source_manifest.path,
                    distilled.artifacts.behavior_inventory,
                    distilled.artifacts.behavior_inventory_report,
                    distilled.artifacts.trace_pattern_notes,
                    behavior_check.artifacts.behavior_review,
                    *tuple(designed.artifacts.values()),
                    *design_feedback,
                ),
                writes=(design_review,),
                returns=WorkflowDesignPayload,
            )
            if design_check.value.verdict == "design_accepted":
                break
            if design_check.value.verdict == "needs_replan":
                replan_behavior = True
                break
            design_feedback = (design_check.artifacts.design_review,)

        if replan_behavior:
            behavior_feedback = (design_check.artifacts.design_review,)
            while True:
                distilled = behavior_provider.run(
                    Prompt.file("prompts/distill_behavior_producer.md"),
                    input={"request": request, "generated_workflow_name": name},
                    reads=(
                        invocation_contract.path,
                        source_manifest.path,
                        trace_corpus.path,
                        *behavior_feedback,
                    ),
                    writes=(behavior_inventory, behavior_report, trace_notes),
                )
                behavior_check = behavior_verifier.run(
                    Prompt.file("prompts/distill_behavior_verifier.md"),
                    input={"request": request, "generated_workflow_name": name},
                    reads=tuple(distilled.artifacts.values()),
                    writes=(behavior_review,),
                    returns=BehaviorDistillationPayload,
                )
                if behavior_check.value.verdict == "behavior_distilled":
                    break
                behavior_feedback = (behavior_check.artifacts.behavior_review,)
            continue

        build_feedback = ()
        needs_redesign = False
        while True:
            generated_flow = Artifact.text(
                str(generated_root / "flow.py"), name="generated_flow", required=True
            )
            generated_manifest = Artifact.text(
                str(generated_root / "workflow.toml"),
                name="generated_manifest",
                required=True,
            )
            generated_layout = Artifact.json("generated_layout.json", required=True)
            validation_report = Artifact.md("validation_report.md", required=True)
            built = authoring_provider.run(
                Prompt.file("prompts/build_and_validate_producer.md"),
                input={
                    "request": request,
                    "generated_workflow_name": name,
                    "output_root": str(generated_root),
                },
                reads=(
                    invocation_contract.path,
                    source_manifest.path,
                    trace_corpus.path,
                    distilled.artifacts.behavior_inventory,
                    distilled.artifacts.behavior_inventory_report,
                    distilled.artifacts.trace_pattern_notes,
                    behavior_check.artifacts.behavior_review,
                    *tuple(designed.artifacts.values()),
                    design_check.artifacts.design_review,
                    *build_feedback,
                ),
                writes=(
                    generated_flow,
                    generated_manifest,
                    generated_layout,
                    validation_report,
                ),
            )
            build_check = build_verifier.run(
                Prompt.file("prompts/build_and_validate_verifier.md"),
                input={
                    "request": request,
                    "generated_workflow_name": name,
                    "output_root": str(generated_root),
                },
                reads=(
                    invocation_contract.path,
                    source_manifest.path,
                    trace_corpus.path,
                    distilled.artifacts.behavior_inventory,
                    distilled.artifacts.behavior_inventory_report,
                    distilled.artifacts.trace_pattern_notes,
                    behavior_check.artifacts.behavior_review,
                    *tuple(designed.artifacts.values()),
                    design_check.artifacts.design_review,
                    *tuple(built.artifacts.values()),
                    *build_feedback,
                ),
                writes=(build_review,),
                returns=BuildValidationPayload,
            )
            if build_check.value.verdict == "build_validated":
                receipt = _publish(str(ctx.workspace), str(ctx.folder), name)
                return CodeToWorkflowResult(
                    generated_workflow_name=name,
                    generated_workflow_root=str(generated_root),
                    publication_receipt=receipt,
                    behavior_status=behavior_check.value.verdict,
                    design_status=design_check.value.verdict,
                    build_status=build_check.value.verdict,
                )
            if build_check.value.verdict == "needs_replan":
                pending_design_feedback = (build_check.artifacts.build_review,)
                needs_redesign = True
                break
            build_feedback = (build_check.artifacts.build_review,)
        if needs_redesign:
            continue


CodeToWorkflow = code_to_workflow

__all__ = ["CodeToWorkflow", "CodeToWorkflowResult", "code_to_workflow"]
