# Test Strategy

- Task ID: botlane-internal-architecture-refactor-spec-this-3778d915
- Pair: test
- Phase ID: boundary-primitives-and-strictness
- Phase Directory Key: boundary-primitives-and-strictness
- Phase Title: Boundary Primitives
- Scope: phase-local producer artifact

## Behavior → Coverage Map

- `ArtifactId` invariants and inventory-backed adaptation
  Covered by `tests/unit/test_artifact_ids.py`.
  Happy path: workflow-level and step-level IDs, dotted artifact names.
  Edge case: step-local lookup preference.
  Failure path: empty names, missing step for step namespace, forbidden step on workflow namespace.

- `RunPaths` / `RunIdentity` primitive behavior and private Context synthesis
  Covered by `tests/unit/test_run_paths.py`.
  Happy path: path normalization, optional identity paths.
  Preserved invariant: legacy `ChildWorkflowResult` path fields remain intact.

- Core/runtime provider policy boundary protocol
  Covered by `tests/runtime/test_provider_policy_core_protocol.py`.
  Happy path: runtime resolver satisfies the core protocol and preserves step/operation layering.
  Regression hardening: direct `Engine(...)` without an explicit runtime resolver still resolves operation policy from the core-local fallback instead of crashing.

- No runtime imports from `botlane/core`
  Covered by `tests/strictness/test_core_runtime_boundary.py`.
  Failure path: absolute and relative runtime imports outside `TYPE_CHECKING`.
  Stabilization: AST parsing avoids grep false positives from strings/comments.

- Repo workflow reference compatibility adjacent to the boundary fix
  Covered by `tests/runtime/test_workflow_reference_resolution.py`.
  Regression hardening: inspecting an imported repo catalog workflow class preserves aliases, manifest-backed authoring shape, and exported `Params` metadata.

## Preserved Invariants Checked

- Public simple/SDK behavior stays green via:
  `tests/unit/test_simple_surface.py`
  `tests/unit/test_sdk_facade.py`
- Compatibility guardrails stay green via:
  `tests/strictness/test_no_compat.py`
- Boundary-adjacent workflow loading remains green via:
  `tests/runtime/test_workflow_reference_resolution.py`

## Edge Cases / Failure Paths

- Dotted artifact names are resolved from inventory records instead of naive string splitting.
- AST strictness catches both `import botlane.runtime...` and relative `from ..runtime ...` forms.
- Imported repo workflow classes no longer lose package-exported `Params` during capability inspection.
- Direct engine usage without an injected runtime resolver no longer fails on `None` policy validation.

## Flake Risks / Stabilization

- No network or wall-clock dependencies are introduced.
- All new coverage uses local temp directories and in-memory stores/providers.
- Workflow reference tests use explicit file contents and deterministic path layouts.

## Known Gaps

- This phase does not add route-contract, workflow-plan, or engine-migration coverage; those belong to later phases by contract.
- `plan_adapters.py` remains intentionally shell-only beyond ArtifactId helpers in this phase.
