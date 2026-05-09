# Test Strategy

- Task ID: botlane-internal-architecture-refactor-spec-this-3778d915
- Pair: test
- Phase ID: branch-results-locators-and-policy-rules
- Phase Directory Key: branch-results-locators-and-policy-rules
- Phase Title: Branch Results And Locators
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- `BranchResult` manifest serialization exactness:
  - `completed` entry shape omits cancellation fields while preserving artifact/raw-output/provider/usage fields.
  - `skipped` entry shape includes cancellation fields with current values.
  - `cancelled` entry shape includes cancellation fields plus the legacy cancellation error payload.
- Branch manifest/context/outcome compatibility:
  - `build_branch_manifest(...)` preserves `botlane.branch_results/v1`.
  - `render_branch_group_context(...)` accepts serialized mappings and typed branch results during migration.
  - `select_branch_group_outcome(...)` still produces the same question summary from serialized branch results.
- `WorkflowLocator` adapter parity:
  - Catalog locator resolves like a named catalog reference.
  - Python-file locator resolves like a file reference with explicit class selection.
  - Python-module locator resolves like a repo-module reference with explicit class selection.
  - Directory locator resolves like a directory reference.
- Locator failure paths:
  - Missing file locator fails clearly with the existing file-not-found error.
  - `workflow_locator_from_resolved(...)` rejects `workflow_class` resolutions because imported-class locators are intentionally out of scope for the approved union.

## Preserved invariants checked

- No workflow-resolution precedence changes: locators are validated only against `runtime.loader` parity.
- No branch manifest schema or context/outcome regressions in the typed serialization path.
- Provider policy emitter outputs remain unchanged in this phase by rerunning the existing emitter suite unchanged.

## Edge cases and stabilization

- Imported-class locator rejection uses a temp module loaded via `importlib.util.spec_from_file_location(...)`; the module is registered in `sys.modules` during the assertion so `inspect.getfile(...)` remains deterministic.
- All tests use temp directories and in-process fixtures only; no network, time-based waiting, or ordering-sensitive assertions were introduced.

## Failure-path coverage

- Unsupported locator source path.
- Unsupported resolved-reference kind for locator conversion.

## Validation executed

- `./.venv/bin/python -m pytest tests/contract/test_branch_result_serialization.py`
- `./.venv/bin/python -m pytest tests/runtime/test_workflow_locator_variants.py`
- `./.venv/bin/python -m pytest tests/contract/test_branch_group_runtime.py tests/runtime/test_provider_policy_emitters.py`

## Known gaps

- No new rule-table tests were added for provider policy emitters because this phase did not introduce rule-table production code.
- Full-suite validation remains out of scope for this phase-local test turn.
