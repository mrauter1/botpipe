# Test Strategy

- Task ID: recursive-framework-evolution-20260427t144615-bootstrap
- Pair: test
- Phase ID: compatibility-docs-cleanup
- Phase Directory Key: compatibility-docs-cleanup
- Phase Title: Compatibility Migration And Cleanup
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Public authoring docs reject deprecated vocabulary:
  Covered by `tests/test_architecture_baseline_docs.py::test_public_docs_do_not_teach_route_contract_or_board_mutation_authoring`
- Repo-root authoring guide is part of the public surface:
  Covered by `tests/test_architecture_baseline_docs.py::test_package_foundation_docs_exist`
- Repo-root authoring guide teaches the replacement route-metadata vocabulary:
  Covered by `tests/test_architecture_baseline_docs.py::test_workflow_instructions_teach_route_metadata_vocabulary`

## Preserved invariants checked

- `Workflow_Instructions.md` remains present while no longer teaching `RouteContract` / `route_contracts`
- The replacement vocabulary stays aligned with the public runtime contract terms already documented elsewhere: `readable inputs`, `required inputs`, `writable artifacts`, `route_infos`, `route_required_outputs`

## Edge cases

- Token scan covers both `docs/` and the repo-root guide, so future drift outside `docs/` fails deterministically

## Failure paths

- Reintroduction of `RouteContract`, `route_contracts`, `route contracts`, `route-contract`, or `BoardMutation` in public authoring docs fails the forbidden-token scan
- Removal of the positive replacement vocabulary from `Workflow_Instructions.md` fails the new targeted assertion

## Flake risk / stabilization

- Low flake risk: tests are pure file-content assertions with no timing, network, or environment dependence beyond repo-local files

## Known gaps

- The broader recursive-memory assertions in `tests/test_architecture_baseline_docs.py` remain outside this phase’s scope and are intentionally not normalized here
