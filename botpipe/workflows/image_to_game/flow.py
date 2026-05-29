"""Reference-driven web-game goal prompt builder.

This workflow prepares a complete `goal_input.md` from a user request and an
optional reference image, verifies that the prompt is grounded enough, then
passes the prompt to the existing `goal` workflow as the child objective.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from botpipe import FAIL, FINISH, Prompt, Route, Session, Workflow, produce_verify_step, python_step, workflow_step
from botpipe.core import Artifact


class Params(BaseModel):
    """Workflow parameters supplied through `-wf` pairs."""

    message: str | None = None
    reference_image_path: str | None = None


class BuilderState(BaseModel):
    status: Literal["missing", "building", "ready", "running_goal", "complete", "failed"] = "missing"


class AcceptedFields(BaseModel):
    reason: str | None = None
    reference_mode: Literal["provided_file", "inferred_file", "prompt_derived"]
    coverage_summary: str
    risks: list[str] = Field(default_factory=list)


class ReworkFields(BaseModel):
    reason: str
    required_fixes: list[str] = Field(default_factory=list)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class WebGameGoalBuilderWorkflow(Workflow):
    """Generate and verify a web-game `goal_input.md`, then delegate to `goal`."""

    name = "image-to-game"
    Params = Params
    State = BuilderState

    builder_session = Session.run()
    builder_verifier_session = Session.fresh()

    input_contract = Artifact.json(
        "{{ workflow.folder }}/input_contract.json",
        name="input_contract",
        required=True,
    )
    reference_resolution = Artifact.json(
        "{{ workflow.folder }}/reference_resolution.json",
        name="reference_resolution",
        required=True,
    )
    goal_input = Artifact.md(
        "{{ workflow.folder }}/goal_input.md",
        name="goal_input",
        required=True,
    )
    goal_input_audit = Artifact.md(
        "{{ workflow.folder }}/goal_input_audit.md",
        name="goal_input_audit",
        required=True,
    )
    goal_child_receipt = Artifact.json(
        "{{ workflow.folder }}/goal_child_receipt.json",
        name="goal_child_receipt",
        required=True,
    )
    goal_child_summary = Artifact.md(
        "{{ workflow.folder }}/goal_child_summary.md",
        name="goal_child_summary",
        required=True,
    )
    final_report = Artifact.md(
        "{{ workflow.folder }}/final_report.md",
        name="final_report",
        required=True,
    )

    validate_and_generate_goal_input = produce_verify_step(
        name="validate_and_generate_goal_input",
        session=builder_session,
        verifier_session=builder_verifier_session,
        producer_writes=[input_contract, reference_resolution, goal_input],
        verifier_writes=[goal_input_audit],
        producer_prompt=Prompt.inline(
            """
            Goal:
            Validate the incoming web-game request with minimal local
            inspection and generate a complete `goal_input.md` that will be
            passed directly to the existing `goal` workflow as its objective.

            Inputs:
            - Initial message: {{ message }}
            - Params message override, if non-empty: {{ params.message }}
            - Optional reference image path: {{ params.reference_image_path }}
            - Workflow folder: {{ workflow.folder }}

            Scope limits:
            - Do not inspect `.botpipe/workflows`, Botpipe source files, skill
              files, previous run traces, or Git history.
            - Do not run broad repository searches.
            - Do not run `git status`.
            - Do not visually inspect the reference image when
              `params.reference_image_path` is provided and the file exists.
              Treat the child `goal` workflow as responsible for visual
              inspection.
            - Use only the source request, workflow params, the provided
              reference path, and the target output folder unless inference is
              required because no explicit reference path was supplied.
            - On the common provided-reference path, complete this step with at
              most one path-existence/readability check, one image-type check,
              and artifact writes.

            Reference resolution policy:
            - `provided_file`: `params.reference_image_path` is non-empty,
              exists, is readable, and has a plausible image extension or MIME
              type. Do not inspect image contents.
            - `inferred_file`: no explicit path was supplied, but the source
              request or workspace yields one unambiguous local image path.
              Search only a directory explicitly named by the prompt, or the
              current working directory at depth <= 2, for common image
              extensions. Return `question` if more than one plausible candidate
              exists.
            - `prompt_derived`: no image file is available, but the source
              request contains enough visual/game direction for the downstream
              goal to require a reference-generation or visual-target-summary
              phase before implementation. Do not search the repo unless the
              prompt names a file or directory.

            Fast path:
            When `params.reference_image_path` is non-empty and valid, do not
            infer, search, inspect visuals, or read unrelated files. Generate
            the three artifacts directly from the fixed schema and template
            below.

            Tasks:
            1. Determine the source request. Use `params.message` when it is
               non-empty; otherwise use the initial message.
            2. Resolve the reference basis using exactly one mode:
               `provided_file`, `inferred_file`, or `prompt_derived`.
            3. If multiple plausible reference images exist, or no usable image
               or prompt-derived visual basis can be established, route
               `question` instead of guessing.
            4. Write `input_contract.json` with:
               - schema: `botpipe.image-to-game.input/v1`
               - source_request
               - params_message
               - initial_message
               - provided_reference_image_path
               - candidate_reference_paths
               - selected_reference_path
               - notes
            5. Write `reference_resolution.json` with:
               - schema: `botpipe.image-to-game.reference/v1`
               - mode: `provided_file`, `inferred_file`, or `prompt_derived`
               - selected_reference_path
               - confidence: `high`, `medium`, or `low`
               - evidence
               - verifier_gate
            6. Write `goal_input.md`, a complete implementation objective for
               the child `goal` workflow. Use the full goal prompt contract
               below. Replace all placeholder values with resolved values; do
               not leave template placeholders in the final artifact.

            `goal_input.md` must include these headings:
            - Objective
            - Source Request
            - Output Location
            - Reference Basis
            - Reference Fidelity Requirement
            - Visual Target Contract
            - Playable Game Contract
            - Implementation Constraints
            - UI Affordance Contract
            - No Inert Controls Rule
            - Settings And Local Persistence
            - Validation Artifact Contract
            - Browser Interaction Audit Requirements
            - Screenshot and Evidence Requirements
            - Screenshot Comparison Requirement
            - Acceptance Criteria
            - Failure Criteria

            Full goal prompt contract:

            # Objective

            Create a playable browser web game from the user request and the
            reference basis below.

            The result must be a real playable game, not a static mock.

            # Source Request

            Include the resolved source request verbatim in a block quote.

            # Output Location

            Prefer a single-file `index.html` deliverable unless the source
            request explicitly asks for a different structure.

            If the selected reference image is inside a dedicated project
            subfolder, or the source request names an output subfolder, place
            the final `index.html` in that same subfolder and place validation
            artifacts under that subfolder's `validation/` directory.

            State the resolved final file path and validation directory.

            # Reference Basis

            If a reference image file exists, name its exact path and require
            the child workflow to inspect it before implementation.

            State that the parent workflow has only validated path existence and
            readability; it has not performed visual analysis.

            If using `prompt_derived`, require the child workflow to first
            create a visual target summary and, when practical, a generated or
            sketched reference artifact before implementation.

            # Reference Fidelity Requirement

            Treat the provided reference image as the primary product
            specification.

            Every control, option, menu, mechanic, status surface, score
            surface, interaction pattern, and game behavior that can reasonably
            be inferred from the reference image must be implemented unless it
            is impossible in a browser-only local implementation. Any omission
            must be documented in `validation/ui-affordance-matrix.md` with a
            concrete reason.

            The rendered page must match the reference image as closely as
            possible in layout, look, feel, typography, spacing, proportions,
            color, visual hierarchy, and component states. Aim for pixel-perfect
            fidelity where practical.

            Do not treat the reference image as loose inspiration. It is the
            visual and interaction target.

            # Visual Target Contract

            Before coding, inspect the reference image or prompt-derived visual
            basis and write `validation/visual-target-summary.md`.

            The visual target summary must capture layout, colors, typography,
            visible controls, game state surfaces, board/playfield structure,
            spacing, proportions, and any visual cues needed to recreate the
            game faithfully.

            # Playable Game Contract

            Implement meaningful gameplay:
            - input handling
            - game state
            - legal actions
            - scoring, win/loss/draw, or completion conditions
            - reset/replay behavior
            - visible feedback for turns, actions, invalid moves, and completed
              games

            # Implementation Constraints

            The final file must run locally in a browser without a build step.

            Use plain HTML, CSS, and JavaScript unless a library is clearly
            necessary for the game mechanics or validation.

            # UI Affordance Contract

            Before coding, write `validation/ui-affordance-inventory.md`.

            Inventory every visible or reasonably inferred control, menu,
            option, input, status surface, score surface, data surface,
            mechanic, and game action from the request and reference basis.

            Every visible affordance in the final game must be one of:
            - fully functional
            - intentionally omitted because it conflicts with the requested
              scope, with the omission documented
            - visibly disabled with an in-app rationale

            # No Inert Controls Rule

            No visible placeholder, decorative, inert, or no-op controls are
            allowed. Each visible affordance must work, be intentionally
            removed, or be visibly disabled with an in-app rationale.

            # Settings And Local Persistence

            If the game exposes settings, mode selectors, player options,
            difficulty controls, timers, themes, or similar options, persist the
            latest selected values locally using browser storage.

            Defaults must be sensible and must not force optional features
            unless requested.

            # Validation Artifact Contract

            Every validation artifact must be concrete, specific to this game,
            and useful for auditing the final result. Do not create placeholder
            files.

            `validation/visual-target-summary.md`
            Purpose: document what the reference image or prompt-derived visual
            basis requires before implementation begins.
            Contents:
            - reference image path, or prompt-derived visual basis
            - viewport/aspect ratio assumptions
            - layout structure
            - major regions and their relative proportions
            - colors, gradients, shadows, borders, and backgrounds
            - typography, font sizes, weights, and text hierarchy
            - board/playfield geometry
            - controls, menus, buttons, options, labels, and status displays
              visible in the image or implied by the request
            - inferred game mechanics or options suggested by the UI
            - visual states that should exist, such as hover, selected, active,
              disabled, win/loss/draw, timer, score, or turn states

            `validation/ui-affordance-inventory.md`
            Purpose: list every control, option, mechanic, and status surface
            inferred from the reference basis and user request.
            Contents:
            - each visible control
            - each visible or implied setting/option
            - each game mechanic implied by the UI
            - each score, timer, turn, status, or message surface
            - source of inference: `reference image`, `user request`, or both
            - expected behavior for each item
            - whether the item is required, optional, or intentionally excluded

            `validation/ui-affordance-matrix.md`
            Purpose: prove every inferred affordance was implemented and tested.
            Contents:
            - affordance name
            - source evidence
            - implemented location in `index.html`
            - selector or UI label used by validation
            - expected behavior
            - validation action performed
            - observed result
            - status: `passed`, `failed`, `disabled-with-rationale`, or
              `omitted-with-rationale`

            `validation/reference-comparison.md`
            Purpose: compare the rendered page screenshot against the reference
            image or prompt-derived visual target.
            Contents:
            - reference image path, or prompt-derived visual target path/summary
            - rendered screenshot path
            - viewport used for the comparison
            - comparison method used
            - layout comparison
            - typography comparison
            - spacing/proportion comparison
            - color/look-and-feel comparison
            - control and label comparison
            - board/playfield geometry comparison
            - list of visible differences
            - judgment on whether the result is pixel-perfect or as close as
              practical
            - rationale for any unavoidable differences

            `validation/<game-slug>-validation.mjs`
            Purpose: executable browser validation.
            Contents:
            - opens the final `index.html`
            - captures desktop and mobile screenshots
            - verifies the page renders nonblank
            - verifies the main game surface is visible
            - clicks or operates every visible control
            - plays at least one meaningful game path
            - verifies win/loss/draw or completion behavior
            - verifies reset/replay
            - verifies settings persistence with browser storage when settings
              exist
            - captures console errors
            - performs or assists the screenshot/reference comparison
            - exits nonzero on failure

            `validation/<game-slug>-validation.sh`
            Purpose: reproducible validation entrypoint.
            Contents:
            - runs the browser validation script
            - uses deterministic paths
            - records logs where practical
            - exits nonzero if validation fails
            - can be run from the project root without manual setup beyond
              normal local dependencies

            `validation/<game-slug>-evidence.md`
            Purpose: summarize what was validated and where the evidence is.
            Contents:
            - validation command run
            - exit status
            - browser/device viewports used
            - screenshots produced
            - logs produced
            - controls tested
            - game paths tested
            - persistence checks performed
            - reference-comparison result
            - remaining known gaps, if any

            # Browser Interaction Audit Requirements

            Require a browser-operated interaction audit that clicks or
            operates every visible control and verifies state/UI changes.

            # Screenshot and Evidence Requirements

            Require desktop and mobile screenshots, screenshot/log artifacts,
            and nonblank checks for canvas/SVG/game surfaces when applicable.

            # Screenshot Comparison Requirement

            Browser validation must capture a screenshot of the rendered page
            and compare it against the provided reference image or
            prompt-derived visual target.

            The comparison must evaluate:
            - layout structure
            - relative proportions
            - typography scale and weight
            - spacing and alignment
            - colors and contrast
            - visible controls and labels
            - board/playfield geometry
            - overall look and feel

            Write the comparison results to
            `validation/reference-comparison.md`.

            If exact pixel comparison is impractical because of browser
            rendering differences, viewport differences, or generated assets,
            perform a structured visual comparison using the screenshot and
            reference basis, and document the remaining differences.

            # Acceptance Criteria

            The task is complete only when:
            - the final `index.html` exists
            - the game is playable
            - the result visually follows the reference basis as closely as
              practical
            - all controls, options, mechanics, and status surfaces reasonably
              inferred from the reference image or request are implemented,
              documented as omitted, or visibly disabled with rationale
            - latest settings/options persist locally when settings exist
            - validation artifacts exist
            - browser validation has been run
            - screenshots, comparison results, and evidence are recorded

            # Failure Criteria

            Fail validation if:
            - the page is static or non-playable
            - any visible control is inert
            - inferred controls, options, mechanics, or status surfaces from the
              reference basis are missing without documented rationale
            - the reference image or visual basis was not inspected
            - no browser interaction audit was performed
            - no rendered screenshot was captured
            - the rendered screenshot was not compared against the reference
              basis
            - screenshots are missing
            - settings exist but latest options are not persisted locally
            - the layout, typography, proportions, or look and feel materially
              diverge from the reference basis without documented reason
            """.strip()
        ),
        verifier_prompt=Prompt.inline(
            """
            Independently verify the generated web-game goal input.

            Inspect:
            - The initial message and workflow params.
            - `input_contract.json`.
            - `reference_resolution.json`.
            - `goal_input.md`.
            - The selected reference path only when one is present.

            Verifier scope:
            - Read only `input_contract.json`, `reference_resolution.json`,
              `goal_input.md`, and the selected reference path if one is
              present.
            - For `provided_file`, verify existence/readability/type only. Do
              not inspect image contents.
            - For `inferred_file`, verify the candidate search was bounded and
              ambiguity was handled.
            - Do not inspect workflow source, previous traces, skill files, or
              Git state.

            Accept only if:
            - `goal_input.md` exists and is specific enough to be used directly
              as the `goal` workflow objective.
            - The reference mode is valid:
              `provided_file`, `inferred_file`, or `prompt_derived`.
            - For `provided_file` and `inferred_file`, the selected reference
              path exists, is readable, and is plausibly an image.
            - For `prompt_derived`, the source request contains enough visual
              and gameplay detail to proceed without an image, and
              `goal_input.md` includes a gate requiring the child workflow to
              produce a visual target summary before implementation.
            - If no reliable reference can be located or inferred, route
              `question` with a concise request for either a reference image
              path or more concrete visual/game direction.
            - The prompt requires visual inspection/summary, playable game
              mechanics, implementation of every reasonably inferred control,
              option, mechanic, and status surface, no inert controls, local
              settings persistence where settings exist, validation artifacts
              with defined purposes and contents, browser interaction audit,
              screenshots, screenshot/reference comparison, and explicit
              failure criteria.
            - The prompt does not invent a fundamentally different game than
              the user requested.

            Reject with `needs_rework` if artifacts are missing, the reference
            logic is weak, the prompt is generic, or any required verifier gate
            is absent.

            Write `goal_input_audit.md` with:
            - decision
            - reference-resolution audit
            - required-heading audit
            - verifier-gate audit
            - missing requirements or required fixes
            """.strip()
        ),
        routes={
            "accepted": Route.to(
                "run_goal_subworkflow",
                required_writes=["input_contract", "reference_resolution", "goal_input", "goal_input_audit"],
                route_fields_schema=AcceptedFields,
            ),
            "needs_rework": Route.to(
                "validate_and_generate_goal_input",
                required_writes=["input_contract", "reference_resolution", "goal_input", "goal_input_audit"],
                route_fields_schema=ReworkFields,
                handoff="Read goal_input_audit.md and address every required fix before rewriting goal_input.md.",
            ),
            "question": Route.question(summary="A reference image or clearer visual/game direction is required."),
            "failed": FAIL,
        },
    )

    run_goal_subworkflow = workflow_step(
        "goal",
        name="run_goal_subworkflow",
        message_from=goal_input,
        params={
            "action": "set",
            "replace_existing": True,
            "allow_replace_completed": True,
        },
        requires=[goal_input],
        writes=[goal_child_receipt, goal_child_summary],
        routes={
            "done": Route.to("finish", required_writes=["goal_child_receipt", "goal_child_summary"]),
            "failed": Route.to("finish", required_writes=["goal_child_receipt", "goal_child_summary"]),
            "blocked": Route.to("finish", required_writes=["goal_child_receipt", "goal_child_summary"]),
            "question": Route.question(summary="The child goal workflow requires user input."),
        },
    )

    @python_step(
        name="finish",
        reads=[input_contract, reference_resolution, goal_input, goal_input_audit, goal_child_receipt, goal_child_summary],
        writes=[final_report],
        routes={"done": FINISH},
    )
    def finish(ctx):
        ctx.state.status = "complete"
        receipt = {}
        try:
            receipt = ctx.artifacts.goal_child_receipt.read_json()
        except Exception:
            receipt = {"status": "unknown", "error": "Could not read child workflow receipt."}

        resolution = {}
        try:
            resolution = ctx.artifacts.reference_resolution.read_json()
        except Exception:
            resolution = {}

        lines = [
            "# Image to Game Report",
            "",
            f"- Completed at: `{_now()}`",
            f"- Reference mode: `{resolution.get('mode', 'unknown')}`",
            f"- Selected reference: `{resolution.get('selected_reference_path') or 'none'}`",
            f"- Child workflow: `{receipt.get('workflow_name') or 'unknown'}`",
            f"- Child run id: `{receipt.get('run_id') or 'unknown'}`",
            f"- Child terminal: `{receipt.get('terminal') or 'unknown'}`",
            f"- Child status: `{receipt.get('status') or 'unknown'}`",
            f"- Child last event: `{receipt.get('last_event') or 'unknown'}`",
            "",
            "## Artifacts",
            "",
            f"- Goal input: `{ctx.artifacts.goal_input.path}`",
            f"- Goal input audit: `{ctx.artifacts.goal_input_audit.path}`",
            f"- Reference resolution: `{ctx.artifacts.reference_resolution.path}`",
            f"- Child receipt: `{ctx.artifacts.goal_child_receipt.path}`",
            f"- Child summary: `{ctx.artifacts.goal_child_summary.path}`",
        ]

        output_artifacts = receipt.get("output_artifacts")
        if isinstance(output_artifacts, dict) and output_artifacts:
            lines.extend(["", "## Child Output Artifacts", ""])
            for name, path in output_artifacts.items():
                lines.append(f"- `{name}`: `{path}`")

        ctx.artifacts.final_report.write_text("\n".join(lines) + "\n")
        return "done"
