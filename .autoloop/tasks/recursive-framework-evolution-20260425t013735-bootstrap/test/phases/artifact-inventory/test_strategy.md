# Test Strategy

- Task ID: recursive-framework-evolution-20260425t013735-bootstrap
- Pair: test
- Phase ID: artifact-inventory
- Phase Directory Key: artifact-inventory
- Phase Title: Artifact Inventory Compilation
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- AC-03 step-local artifact binding:
  - `tests/unit/test_validation.py::test_step_local_artifacts_bind_names_and_qualified_names`
  - Confirms inline `produces` bind artifact name, owner-step metadata, qualified name, step attribute access, and compiled step output names.
- AC-03 preserved relative-path behavior:
  - `tests/unit/test_primitives_and_stores.py::test_artifact_template_resolution_supports_step_local_relative_artifacts`
  - Confirms step-local relative artifact paths resolve under `{workflow_folder}/{step_name}/`.
- AC-04 deterministic route-contract resolution:
  - `tests/unit/test_validation.py::test_route_contract_required_artifact_resolves_to_step_local_output`
  - Confirms same-step route contracts prefer `step.artifact` and normalize to canonical qualified names.
- AC-04 ambiguous reference rejection:
  - `tests/unit/test_validation.py::test_validation_rejects_ambiguous_unqualified_artifact_reference`
  - Confirms ambiguous string references fail instead of silently picking one artifact.
- Canonical-vs-alias inventory split:
  - `tests/unit/test_validation.py::test_compiled_workflow_artifact_items_distinguish_alias_and_authoritative_inventories`
  - Confirms alias inventory can be empty while authoritative inventory still exposes all canonical qualified artifacts.
- Downstream regression protection for authoritative inventory consumers:
  - `tests/runtime/test_compatibility_runtime.py::test_inspect_workflow_capabilities_includes_canonical_artifacts_when_unqualified_aliases_are_ambiguous`
  - `tests/runtime/test_compatibility_runtime.py::test_child_workflow_result_preserves_canonical_outputs_when_unqualified_aliases_are_ambiguous`
  - Confirms capability inspection and child workflow results enumerate canonical qualified artifacts when alias names are ambiguous.

## Preserved invariants checked

- Unique workflow/artifact behavior still exposes compatibility aliases through `compiled.artifacts`.
- Duplicate step-local names do not erase canonical artifacts from downstream inspection surfaces.
- Deterministic compiled workflow caching remains covered by the existing focused contract check in `tests/contract/test_engine_contracts.py::test_compiled_workflow_is_deterministic`.

## Edge cases and failure paths

- Ambiguous unqualified string references fail fast.
- Duplicate step-local output names remain accessible through canonical qualified names even when no public alias exists.
- Downstream consumers that previously relied on `compiled.artifacts` now preserve outputs via authoritative inventory enumeration.

## Reliability / stabilization

- All added coverage uses temporary directories, scripted fake providers, and deterministic route tags.
- No timing, network, randomness, or ordering-sensitive assertions were introduced.

## Known gaps

- Runtime artifact requiredness and post-step enforcement remain intentionally out of scope for this phase.
