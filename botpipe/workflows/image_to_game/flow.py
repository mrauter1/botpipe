"""Build a reference-grounded game objective and run it through ``goal``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from botpipe import Artifact, Session, activity, ask, current_run, workflow
from botpipe.workflows.goal import goal


class Params(BaseModel):
    message: str | None = None
    reference_image_path: str | None = None


class GoalInputDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["accepted", "needs_rework"]
    reason: str | None = None
    reference_mode: Literal["provided_file", "inferred_file", "prompt_derived"]
    coverage_summary: str
    required_fixes: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class ImageToGameResult(BaseModel):
    status: Literal["complete", "blocked", "budget_limited"]
    reference_mode: Literal["provided_file", "inferred_file", "prompt_derived"]
    selected_reference_path: str | None = None
    goal_input_path: str
    goal_status: str
    goal_id: str | None = None
    final_report_path: str


_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg"}


@activity
def _reference_candidates(workspace: str, supplied: str | None) -> list[str]:
    root = Path(workspace).resolve()
    if supplied and supplied.strip():
        path = Path(supplied).expanduser()
        if not path.is_absolute():
            path = root / path
        path = path.resolve()
        if path.is_file() and path.suffix.lower() in _IMAGE_EXTENSIONS:
            return [str(path)]
        return []
    candidates: list[str] = []
    for path in sorted(root.glob("*")):
        if path.is_file() and path.suffix.lower() in _IMAGE_EXTENSIONS:
            candidates.append(str(path.resolve()))
        elif path.is_dir() and not path.name.startswith("."):
            candidates.extend(
                str(child.resolve())
                for child in sorted(path.glob("*"))
                if child.is_file() and child.suffix.lower() in _IMAGE_EXTENSIONS
            )
    return candidates


@activity
def _write_json(path: str, payload: dict[str, Any]) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return str(target)


@activity
def _write_text(path: str, text: str) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text.rstrip() + "\n", encoding="utf-8")
    return str(target)


BUILD_GOAL = """Build goal_input.md for the child persistent Goal workflow from the supplied request and resolved
reference contract. Do not inspect the image contents; the child must do that. The result must be a complete,
standalone implementation objective with every heading below:

# Objective
Require a real playable browser game, not a static mock.
# Source Request
Quote the resolved user request verbatim.
# Output Location
Resolve index.html and validation/ paths; prefer a single local-browser file without a build step.
# Reference Basis
Name the exact selected image or prompt-derived basis and require child-side visual inspection/summary first.
# Reference Fidelity Requirement
Treat the reference as the product specification and aim for the closest practical visual match.
# Visual Target Contract
Require validation/visual-target-summary.md covering layout, colors, type, spacing, proportions, playfield and states.
# Playable Game Contract
Require input handling, legal actions, state, scoring or completion, feedback, and reset/replay.
# Implementation Constraints
Require locally runnable HTML/CSS/JS unless a dependency is justified.
# UI Affordance Contract
Require validation/ui-affordance-inventory.md and implementation of every inferred control, option, mechanic and status.
# No Inert Controls Rule
Every visible affordance must work, be removed with documented reason, or be visibly disabled with rationale.
# Settings And Local Persistence
Persist the latest settings, modes, player options, difficulty, timers or themes when present.
# Validation Artifact Contract
Require specific visual-target-summary, ui-affordance-inventory, ui-affordance-matrix, reference-comparison, executable
browser validation script and shell entrypoint, evidence report, screenshots and logs.
# Browser Interaction Audit Requirements
Operate every visible control and prove state changes plus a meaningful game path and reset.
# Screenshot and Evidence Requirements
Require desktop/mobile screenshots, nonblank canvas/SVG checks, logs, commands and results.
# Screenshot Comparison Requirement
Compare rendered screenshots with the image or prompt-derived target for layout, proportions, typography, spacing,
colors, controls, labels, geometry and overall look; document unavoidable differences.
# Acceptance Criteria
Require a playable final index, faithful visuals, complete affordances, persistence, executed browser validation and
recorded comparison evidence.
# Failure Criteria
Fail static/non-playable output, inert controls, undocumented omissions, missing visual inspection, browser audit,
screenshots/comparison/evidence, persistence, or material unexplained visual divergence.

Use the declared goal_input artifact and resolve every value. Do not leave template placeholders."""

VERIFY_GOAL = """Independently verify goal_input.md against the supplied request, input_contract and
reference_resolution. Do not visually inspect a selected image. Accept only when the reference mode is sound and all
required headings and gates are concrete: visual inspection, playable mechanics, complete affordances, no inert
controls, persistence, validation artifacts, browser interaction audit, screenshots, structured reference comparison,
acceptance criteria and failure criteria. Write goal_input_audit.md and return the structured verdict."""


@workflow(name="image-to-game", version="1")
def image_to_game(
    message: str | None = None,
    *,
    reference_image_path: str | None = None,
    params_message: str | None = None,
) -> ImageToGameResult:
    ctx = current_run()
    request = (params_message or message or "").strip()
    if not request:
        request = ask("Describe the browser game to create.", returns=str).strip()

    candidates = _reference_candidates(str(ctx.workspace), reference_image_path)
    selected: str | None = None
    if reference_image_path:
        if not candidates:
            replacement = ask(
                "The supplied reference image was not a readable supported image. Provide a valid path or say prompt-derived.",
                returns=str,
            ).strip()
            if replacement.lower() != "prompt-derived":
                retry = _reference_candidates(str(ctx.workspace), replacement)
                if not retry:
                    raise ValueError(
                        "replacement reference image is not readable or has an unsupported extension"
                    )
                selected = retry[0]
        else:
            selected = candidates[0]
        mode: Literal["provided_file", "inferred_file", "prompt_derived"] = (
            "provided_file" if selected else "prompt_derived"
        )
    elif len(candidates) == 1:
        selected, mode = candidates[0], "inferred_file"
    elif len(candidates) > 1:
        choice = ask(
            "Multiple reference images were found. Provide the exact image path, or say prompt-derived.",
            returns=str,
        ).strip()
        if choice.lower() == "prompt-derived":
            mode = "prompt_derived"
        else:
            resolved = _reference_candidates(str(ctx.workspace), choice)
            if not resolved:
                raise ValueError(
                    "selected reference image is not readable or has an unsupported extension"
                )
            selected, mode = resolved[0], "inferred_file"
    else:
        mode = "prompt_derived"

    input_contract_payload = {
        "schema": "botpipe.image-to-game.input/v1",
        "source_request": request,
        "params_message": params_message,
        "initial_message": message,
        "provided_reference_image_path": reference_image_path,
        "candidate_reference_paths": candidates,
        "selected_reference_path": selected,
        "notes": "Parent checked path existence/type only; child owns visual inspection.",
    }
    resolution_payload = {
        "schema": "botpipe.image-to-game.reference/v1",
        "mode": mode,
        "selected_reference_path": selected,
        "confidence": "high" if selected else "medium",
        "evidence": [selected]
        if selected
        else ["source request supplies the visual/game basis"],
        "verifier_gate": "Child must inspect or create a visual target summary before implementation.",
    }
    input_path = _write_json(
        str(ctx.folder / "input_contract.json"), input_contract_payload
    )
    resolution_path = _write_json(
        str(ctx.folder / "reference_resolution.json"), resolution_payload
    )
    input_contract = Artifact.json(input_path, name="input_contract", required=True)
    reference_resolution = Artifact.json(
        resolution_path, name="reference_resolution", required=True
    )
    goal_input = Artifact.md(
        str(ctx.folder / "goal_input.md"), name="goal_input", required=True
    )
    audit_spec = Artifact.md(
        str(ctx.folder / "goal_input_audit.md"), name="goal_input_audit", required=True
    )
    builder, verifier = Session(key="goal-builder"), Session.fresh()
    feedback: tuple[Any, ...] = ()
    while True:
        built = builder.run(
            BUILD_GOAL,
            input={
                "source_request": request,
                "reference_resolution": resolution_payload,
            },
            reads=(input_contract.path, reference_resolution.path, *feedback),
            writes=(goal_input,),
        )
        checked = verifier.run(
            VERIFY_GOAL,
            input={
                "source_request": request,
                "reference_resolution": resolution_payload,
            },
            reads=(
                input_contract.path,
                reference_resolution.path,
                built.artifacts.goal_input,
            ),
            writes=(audit_spec,),
            returns=GoalInputDecision,
        )
        if checked.value.verdict == "accepted":
            break
        feedback = (checked.artifacts.goal_input_audit,)

    child = goal(
        objective=built.artifacts.goal_input.read_text(),
        action="set",
        replace_existing=True,
        allow_replace_completed=True,
    )
    receipt_path = ctx.folder / "goal_child_receipt.json"
    _write_json(
        str(receipt_path),
        {
            "workflow_name": "goal",
            "status": child.status,
            "goal_id": child.goal_id,
            "goal_path": child.goal_path,
            "subgoals_path": child.subgoals_path,
            "final_report_path": child.final_report_path,
        },
    )
    report_path = ctx.folder / "final_report.md"
    _write_text(
        str(report_path),
        "# Image to Game Report\n\n"
        f"- Reference mode: `{mode}`\n"
        f"- Selected reference: `{selected or 'none'}`\n"
        f"- Goal status: `{child.status}`\n"
        f"- Goal id: `{child.goal_id or 'none'}`\n"
        f"- Goal input: `{built.artifacts.goal_input.source_path}`\n"
        f"- Goal audit: `{checked.artifacts.goal_input_audit.source_path}`\n"
        f"- Child receipt: `{receipt_path}`\n",
    )
    result_status: Literal["complete", "blocked", "budget_limited"] = (
        "complete"
        if child.status == "complete"
        else "budget_limited"
        if child.status in {"budget_limited", "usage_limited"}
        else "blocked"
    )
    return ImageToGameResult(
        status=result_status,
        reference_mode=mode,
        selected_reference_path=selected,
        goal_input_path=str(built.artifacts.goal_input.source_path),
        goal_status=child.status,
        goal_id=child.goal_id,
        final_report_path=str(report_path),
    )


WebGameGoalBuilderWorkflow = image_to_game

__all__ = [
    "GoalInputDecision",
    "ImageToGameResult",
    "Params",
    "WebGameGoalBuilderWorkflow",
    "image_to_game",
]
