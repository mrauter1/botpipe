# Intent Audit Gap Report

## Original intent considered

- The immutable request in `request.md` asked for Milestone A runtime fixes plus the later public-surface/doc cleanup, including:
  - no dual-role artifact rejection and no `Artifact.managed(...)`
  - canonical workflow-level artifact naming with `producer_steps` as provenance
  - optional rendered-provider `reason`
  - no default provider-visible `blocked` / `failed`
  - policy-gated default `question`
  - explicit child-workflow `blocked` / `failed`
  - lazy worklist materialization, missing-source policy, strict lazy restore, lazy work-item session continuity, and runtime `item.state.<field>` support
  - docs/examples reflecting the new route model and managed-artifact removal
- The authoritative raw log contains no later user clarification changing that intent.

## Clarifications / superseding decisions

- `decisions.txt` block 1 adopted the preferred strict lazy restore policy.
- `decisions.txt` block 2 fixed the public missing-source surface at `Worklist.from_artifact(..., missing="error" | "scaffold")`.
- `decisions.txt` block 6 chose the allowed alternative to keep `Effects` public and document/test it as an intentional hook-control API.
- The phase artifacts consistently treated Milestone A runtime semantics as required before merge and the broader docs/examples cleanup as part of the final public-surface phase.

## Implemented behavior

- Runtime artifact semantics appear aligned with the request:
  - `autoloop/core/artifacts.py` no longer exposes `Artifact.managed(...)`, `ArtifactRole`, or `role=`.
  - `autoloop/core/inventory.py` keeps workflow-level artifacts canonical and accumulates `producer_steps` without rejecting same-object workflow-level plus step-produced usage.
- Provider route semantics appear aligned:
  - `autoloop/core/providers/parsing.py` defaults missing `reason` to `""` and gives `question` the only special top-level payload requirement.
  - `autoloop/runtime/runner.py` still builds `RuntimeInteractionPolicy(allow_provider_questions=not full_auto)`.
- Worklist/runtime semantics appear aligned:
  - `autoloop/core/engine.py` restores checkpointed worklists as lazy `SelectionSnapshot`s and materializes them only on first use through `_ensure_worklist_selection(...)`.
  - `autoloop/core/worklists.py` exposes `missing="error" | "scaffold"` on `Worklist.from_artifact(...)`.
  - `autoloop/core/artifacts.py` resolves `{item.state.<field>}` through active runtime item state.
  - `autoloop/runtime/static_graph.py` distinguishes declared worklists from runtime materialization state.
- Public docs/README cleanup was partly completed:
  - `docs/authoring.md`, `docs/workflows/*.md`, and `workflows/*/prompts/README.md` now describe `question` as the only default runtime control route and describe authored `blocked` / `failed` as ordinary application routes.

## Unresolved gaps

- Material documentation/example drift remains in workflow prompt bodies.
  - There are still `46` prompt markdown files under `workflows/**/prompts/*.md` containing `Reserved routes` wording.
  - Representative examples:
    - `workflows/workflow_idea_to_workflow_package/prompts/frame_producer.md` still says `Reserved routes \`question\`, \`blocked\`, and \`failed\`...`
    - `workflows/workflow_run_traces_to_optimization_candidates/prompts/frame_producer.md` still says `Reserved routes are only \`question\`, \`blocked\`, and \`failed\`.`
  - This conflicts with the request’s required doc statements:
    - only `question` is a default provider control route
    - `blocked` and `failed` are never injected by default
    - docs/examples should not show default `blocked` or `failed`
- The test suite currently preserves that stale wording instead of guarding the corrected contract for prompt bodies.
  - Example: `tests/runtime/test_workflow_portfolio_to_operating_system.py` still asserts prompt text contains `Reserved routes are only`.
  - Similar assertions remain across multiple runtime prompt-package tests, so the outdated contract is currently codified rather than prevented.

## Differences justified by later clarification or analysis

- Keeping `Effects` public is justified, not a gap. The request explicitly allowed either narrowing the API or keeping it with explicit documentation/tests, and `decisions.txt` block 6 chose the documented/tested broader API.
- The out-of-phase mechanical cleanup of package artifact declarations using removed `role="managed"` is justified. Once the public `Artifact` constructor stopped accepting `role=`, adjacent workflow package imports had to be updated for the requested API removal to be coherent.
- Strict lazy restore and the artifact-backed `missing=` surface match explicit run decisions and the preferred policy in the request.

## Recommended next run

- Narrow follow-up only:
  - update workflow prompt bodies under `workflows/**/prompts/*.md` to replace the retired `Reserved routes` wording with the shipped route model
  - ensure prompt bodies say `question` is the only default runtime control route and that authored `blocked` / `failed` are ordinary application routes
  - update the runtime prompt-package tests that currently assert `Reserved routes are only` / `Use reserved routes only`
  - add one shared baseline or helper assertion that guards prompt-body route wording, not only `docs/workflows/*.md` and prompt `README.md`
