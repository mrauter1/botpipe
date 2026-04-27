# Test Strategy

- Task ID: standalone-implementation-plan-autoloop-v3-green-f94366a9
- Pair: test
- Phase ID: workflow-migration-docs-and-proof
- Phase Directory Key: workflow-migration-docs-and-proof
- Phase Title: Workflow migration, docs, and proof
- Scope: phase-local producer artifact

## Behaviors covered

- Simple authoring surface in `tests/unit/test_simple_surface.py`
  - export surface from `autoloop.simple`
  - `Workflow` / `StrictWorkflow` discovery and compilation
  - `step`, `review_step`, `system_step(fn)`, `workflow_step(...)`, `chain(...)`
  - artifact helper defaults, route metadata helpers, and conservative placeholder inference
- Engine/provider contract in `tests/contract/test_engine_contracts.py`
  - `system_step(fn)` return normalization matrix
  - before/after hook behavior, route override validation, and required-output recomputation
  - reserved routes, provider control-response requirements, and `WorkflowStep` execution/loop behavior
- Bundled workflow/runtime parity in `tests/runtime/*.py`
  - migrated `workflows/*` package route metadata, prompt contract markers, required outputs, and child-workflow behavior
  - capability/runtime route-required-output assertions updated to canonical qualified names
- Capability/stdlib proof in `tests/unit/test_stdlib_and_extensions.py`
  - authoritative selected-workflow capability and decomposition payloads
  - stdlib alias recovery for unique public artifact names
  - preserved selected-workflow authoring/decomposition surface shape
- Active docs and working-tree wording in `tests/test_architecture_baseline_docs.py`
  - active docs and prompt READMEs avoid removed legacy terminology
  - root `cleanup.md` note and recursive template docs stay on the greenfield vocabulary boundary

## Preserved invariants checked

- Reserved `question` / `blocked` / `failed` routes remain normalized and legal across step kinds
- Provider prompts keep the explicit readable-input / required-input / writable-artifact / route-info contract sections
- Capability payloads remain authoritative while stdlib consumers preserve ergonomic public-name access
- Archived `legacy_docs/` stays outside the active-term assertion boundary

## Edge cases

- Ambiguous placeholder inference does not silently create required dependencies
- Empty `route_required_outputs` lists remain legal in selected-workflow capability payload validation
- Child workflow result artifacts expose canonical names plus unqualified aliases only when the alias is unique
- Active docs tests avoid false positives by constructing removed tokens from split string literals

## Failure paths

- Missing required child artifacts and invalid child status/last-event contracts in stdlib composition helpers
- Invalid after-hook route overrides and missing required output artifacts after route changes
- Provider control responses missing `reason` or `question` content on reserved routes
- Reintroduction of removed legacy vocabulary in active docs, working-tree notes, or recursive template docs

## Known gaps

- Existing Pydantic warnings from `workflow_run_traces_to_optimization_candidates/contracts.py` are tolerated and not treated as failures in this phase
- Repo-wide removed-term proof still depends on the explicit grep step in addition to the focused docs/tests above

## Validation run

- `.venv/bin/pytest tests/test_architecture_baseline_docs.py -q`
- Full-suite and targeted runtime/contract validation evidence is recorded in the paired implementation artifacts for this same phase
