# Framework correction plan

## Current implementation snapshot

- Route policy is already partly aligned: discovery injects only runtime `question`, compiler persists authored versus runtime-control route sets plus interactive/full-auto provider-visible sets, and the engine already treats provider `question` under full-auto as illegal.
- Child workflow mapping is also partly aligned: `failed` and `blocked` already require explicit declaration on the parent step and current runtime errors already include step, terminal, mapped route, declared routes, and a recommended fix.
- The main Milestone A gaps are still real runtime changes:
  - artifact inventory still rejects workflow-level plus step-produced artifacts unless `managed` is used
  - `Artifact.managed(...)`, `ArtifactRole`, and `role=` are still public
  - rendered provider JSON parsing still requires non-empty `reason`
  - fallback route summaries still treat `blocked` and `failed` like reserved controls
  - checkpoint restore eagerly reloads worklist sources through `Engine._restore_worklist_selections()`
  - artifact-backed worklists have no explicit missing-source policy surface
- Lazy worklist behavior exists at first access through `Context.ensure_selection()` and scoped-step dispatch, so the plan should preserve that path and tighten restore/session/inspection behavior around it instead of replacing the mechanism.

## Milestone plan

### Phase 1: route and artifact contract corrections

Target modules:
- `autoloop/core/artifacts.py`
- `autoloop/core/inventory.py`
- `autoloop/core/compiler.py`
- `autoloop/core/lowering.py`
- `autoloop/core/providers/parsing.py`
- `autoloop/core/providers/rendered.py`
- `autoloop/core/engine.py`
- provider/validation contract tests

Implementation intent:
- Remove the managed-ownership model completely from artifact declarations.
- Treat workflow-level visibility and step production as compatible metadata on one canonical artifact identity.
- Preserve workflow/public artifact names when `workflow_level=True`; record producing steps in `producer_steps` without rebinding to `step.artifact`.
- Keep ambiguity diagnostics for truly distinct/incompatible artifacts or unresolved short-name references.
- Make rendered provider outcome parsing match direct `Outcome(...)` semantics by defaulting missing `reason` to `""`.
- Keep `question` as the only built-in route with special payload validation, and keep provider-visible `question` policy-gated through existing interactive/full-auto route sets.
- Remove reserved-style summary defaults for unauthored `blocked` and `failed`; authored uses of those names should get generic authored-route summaries.

Interface and compatibility notes:
- Intentional public API break: remove `Artifact.managed(...)`, `ArtifactRole`, and `role=` from public constructors unless another concrete internal use remains after refactor.
- `CompiledArtifact` and capability/static-graph payloads should continue exposing `workflow_level` and `producer_steps`, but `qualified_name` must remain the canonical public/workflow name for workflow-level artifacts.
- Existing authored workflows that explicitly declare `blocked` or `failed` must keep working without hidden non-empty `reason` rules.

Regression controls:
- Add and update tests for same-object workflow-level plus multi-step production, canonical name resolution, route-required-write resolution by public name, and distinct-artifact ambiguity failures.
- Add direct-versus-rendered provider parity tests for `done`, authored `blocked`/`failed`, valid `question`, invalid `question`, and illegal `question` under full-auto.

### Phase 2: strict lazy worklist materialization and session continuity

Target modules:
- `autoloop/core/worklists.py`
- `autoloop/core/context.py`
- `autoloop/core/sessions.py`
- `autoloop/core/engine.py`
- `autoloop/runtime/static_graph.py`
- `autoloop/runtime/inspection.py`
- `autoloop/core/workflow_capabilities.py`
- worklist/session/runtime contract tests

Implementation intent:
- Keep declaration-time validation limited to worklist identity, selector declaration, item-state model shape, and scoped-step references.
- Make source loading, payload validation, and selection creation happen only on first runtime use.
- Introduce explicit source policy for missing backing data, with artifact-backed sources defaulting to `missing="error"` and optional opt-in scaffold behavior.
- Change checkpoint restore to strict lazy restore: restore only snapshots/selection metadata at resume entry and defer source reconcile/load until first access.
- Make work-item session continuity resolve only after a current item can be obtained from the relevant selection.
- Make runtime `{item.state.<field>}` rendering and failures agree with compile-time placeholder validation.
- Distinguish declared-versus-materialized worklists in inspection/static graph outputs without implying eager loading.

Interface and compatibility notes:
- Resume semantics intentionally change: old checkpoints with materialized selections should resume without loading sources until the selection is used.
- Old checkpoints with missing or null worklist selections should restore as an empty lazy selection map.
- `ctx.selection(...)`, `ctx.current(...)`, scoped-step entry, worklist prompt/artifact placeholders, and work-item session keys become the authoritative materialization triggers.

Regression controls:
- Keep current lazy first-use behavior for non-scoped paths and explicit `ctx.selection(...)` access.
- Add tests proving unused missing sources do not fail, first scoped use materializes and validates, scaffold policy only creates backing data when opted in, resume does not eagerly load, and first access after resume performs reconcile/load.
- Add tests covering distinct session keys per item, stable reuse on resume, and clear failures when work-item continuity cannot resolve a current item.

### Phase 3: public-surface cleanup and documentation sweep

Status:
- Deferred until Milestone A semantics land cleanly.

Target modules:
- `autoloop/core/effects.py`
- `autoloop/simple.py`
- `docs/authoring.md`
- workflow docs and prompt READMEs
- architecture/doc baseline tests

Implementation intent:
- Decide explicitly whether `Effects` remains a supported public hook-control API or narrows to worklist-focused helpers only.
- Keep `validation_step(...)` as sugar that lowers to a Python step, reuses existing validation utilities, and does not introduce a separate validation subsystem.
- Remove stale documentation/examples that still describe default `blocked`/`failed` or `Artifact.managed(...)`.

Compatibility and risk notes:
- This phase may be deferred from the merge if Milestone A correctness is accepted first, but docs/examples must not be left contradicting shipped runtime behavior for long.
- If `Effects` is narrowed, add explicit rejection coverage for `Effects.then(...)` as a public return surface while preserving direct `Event`, `RequestInput`, `Goto`, and `Fail` control returns.

## Risk register

- Artifact canonical-name drift: inventory, public artifact aliases, route-required-write resolution, provider contracts, CLI/static graph payloads, and runtime artifact handles must all agree on the same canonical name after the dual-role change.
- Lazy restore regressions: changing resume from eager to strict lazy can break item-state restore, prompt rendering, or session-key reuse if selection snapshots and active-item sync are not updated together.
- Inspection drift: runtime topology/capability payloads already expose authored/runtime/provider-visible route splits; worklist materialization state must be added without regressing existing schema shape or implying eager validation.
- Docs/example skew: many workflow docs and prompt READMEs still describe default `blocked`/`failed`, so Phase 3 needs an explicit sweep rather than opportunistic edits.

## Validation and rollout

- Land Phase 1 and Phase 2 with focused unit plus contract coverage before considering Phase 3.
- Run the provider boundary tests, route/validation unit suite, worklist/session unit suite, and engine contract tests that cover provider routing, worklist lazy materialization, restore, prompt placeholders, child workflow mapping, and validation-step behavior.
- Roll back by restoring prior artifact naming or eager-restore behavior only if the new tests expose unavoidable compatibility breaks; do not keep hybrid semantics that mix canonical workflow-level names with step-local rebinding or mix lazy declaration with eager resume.
