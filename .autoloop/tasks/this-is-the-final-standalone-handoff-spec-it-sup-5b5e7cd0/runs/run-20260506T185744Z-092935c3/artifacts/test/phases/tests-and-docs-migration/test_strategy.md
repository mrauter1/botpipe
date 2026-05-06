# Test Strategy

- Task ID: this-is-the-final-standalone-handoff-spec-it-sup-5b5e7cd0
- Pair: test
- Phase ID: tests-and-docs-migration
- Phase Directory Key: tests-and-docs-migration
- Phase Title: Migrate Tests And Docs
- Scope: phase-local producer artifact

## Behavior-to-coverage map

- Canonical shared route guidance:
  - Coverage: `tests/test_architecture_baseline_docs.py::test_workflow_instructions_freeze_runtime_contract_vocabulary`
  - Checks: `Workflow_Instructions.md` keeps everything-is-a-route wording, requires `outcome.route_fields` metadata wording, and explicitly names `ControlRoutes(question=...)` plus top-level `question` / `reason` as compatibility-only migration surfaces.
- Public authoring compatibility note:
  - Coverage: `tests/test_architecture_baseline_docs.py::test_authoring_doc_describes_greenfield_public_surface`
  - Checks: `docs/authoring.md` keeps the canonical `outcome.route_fields` contract and the explicit compatibility-only note for legacy `ControlRoutes` and top-level provider fields.
- Preserved prompt/doc cleanup:
  - Coverage: `tests/test_architecture_baseline_docs.py::test_workflow_instructions_freeze_runtime_contract_vocabulary`
  - Checks: stale phrases such as `helper routes and compatibility routes`, `blocker/failure/question fields only when applicable`, and `Reserved routes are always:` remain forbidden.

## Preserved invariants checked

- Shared prompt guidance still freezes the runtime contract vocabulary (`readable inputs`, `required inputs`, `writable artifacts`, `route summaries`, `route_required_writes`).
- The canonical provider outcome contract remains `outcome.tag` / `outcome.payload` / `outcome.route_fields`.

## Edge cases and failure paths

- Failure path: regressions that quietly weaken the Workflow Instructions note to generic “compatibility” wording without naming `ControlRoutes(question=...)` or top-level `question` / `reason` now fail deterministically.
- Failure path: any reintroduction of the reserved-route wording or top-level route-field phrasing in the central instruction file now fails the docs suite.

## Flake risk and stabilization

- Low flake risk: assertions are pure file-content checks with no timing, network, or ordering dependency.

## Known gaps

- This slice hardens the central docs contract only; it does not duplicate the same exact compatibility-note assertion across every workflow prompt body because those files already inherit the shared wording pattern and would add redundant maintenance surface.
