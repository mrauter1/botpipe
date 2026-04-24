# Test Strategy

- Task ID: recursive-framework-evolution-20260424t114109-bootstrap
- Pair: test
- Phase ID: docs-templates-and-regression
- Phase Directory Key: docs-templates-and-regression
- Phase Title: Docs, Templates, And Regression Sweep
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Canonical docs doctrine:
  `tests/test_architecture_baseline_docs.py` checks that `docs/architecture.md` and `docs/authoring.md` describe single-file, flow-specs, and mature-package authoring while preserving metadata-only `workflow.toml`.
- Recursive template doctrine:
  `tests/runtime/test_package_cli.py` checks recursive template text for flow-first wording, name-first CLI usage, and removal of mandatory package-minimum claims.
- Recursive-memory baseline sync:
  `tests/test_architecture_baseline_docs.py` checks `.autoloop_recursive/framework_evolution_charter.md` and `.autoloop_recursive/framework_roadmap.md` for the updated flow-first doctrine, current seam wording, and removal of stale active wrapper-drift claims.
- CLI/help surface:
  `tests/runtime/test_package_cli.py` checks package-CLI wording, shallow listing language, workflow-reference help text, and scaffold-shape text.
- Preserved invariants:
  `tests/strictness/test_no_compat.py` keeps removed public compatibility surfaces blocked while allowing only the documented internal provider-native `thread_id` exception.
- Regression expectations updated by adjacent slices:
  `tests/contract/test_engine_contracts.py` covers snake_case unnamed workflow fallback for extension binding context.
  `tests/runtime/test_workflow_reference_resolution.py` covers duplicate canonical-name conflict reporting for inferred workflow candidates.

## Edge cases / failure paths

- Recursive-memory roadmap must not reintroduce stale active wrapper-drift wording once the wrapper/template cleanup is shipped.
- Strictness coverage must not treat negative prompt guidance or internal provider session normalization as public compatibility regressions.
- Name-conflict and unnamed-workflow expectations must match the shipped resolver/catalog rules rather than silently normalizing older behavior.

## Flake risks and stabilization

- All covered tests are filesystem-local and deterministic.
- No timing, network, or nondeterministic ordering dependencies are introduced.

## Known gaps

- This phase does not add new fixtures for every workflow doc under `docs/workflows/`; coverage stays focused on canonical docs, recursive templates/baselines, and adjacent regression surfaces with material drift risk.
