# Test Strategy

- Task ID: standalone-implementation-plan-final-autoloop-v3-f607e24e
- Pair: test
- Phase ID: route-info-rename-and-payload-cleanup
- Phase Directory Key: route-info-rename-and-payload-cleanup
- Phase Title: Route-Info Rename And Payload Cleanup
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Stdlib rename surface:
  `tests/unit/test_stdlib_and_extensions.py`
  Confirms `stdlib/route_infos.py` is the active pure-authoring module, `stdlib/contracts.py` is gone, and `review_gate_infos` / `publication_gate_infos` are the only exported helper names under test.
- Catalog and capability discovery:
  `tests/runtime/test_compatibility_runtime.py`
  Confirms discovered and inspected workflow entries expose `contracts.py` through `spec_paths` and no longer expose a `contracts_path` attribute.
- Capability / authoring / decomposition payloads:
  `tests/unit/test_stdlib_and_extensions.py`
  Confirms `contracts_path` and `contracts_path_repo_relative` are absent, while `contracts.py` still appears in `spec_paths`, `spec_paths_repo_relative`, and derived `editable_paths`.
- Runtime CLI JSON:
  `tests/runtime/test_package_cli.py`
  Confirms `workflows show` omits `contracts_path` and emits both `specs.py` and `contracts.py` in `spec_paths`.

## Preserved invariants checked

- `contracts.py` remains editable when present because authoring-surface `editable_paths` still includes all `spec_paths`.
- Support-file discovery ordering stays deterministic: `specs.py` first, `contracts.py` second when both exist.
- Removed stdlib helper names are not normalized via aliases.

## Edge cases and failure-path focus

- Workflow packages with only `contracts.py` in support files still surface that file through capability and decomposition payloads.
- Workflow packages with both `specs.py` and `contracts.py` preserve both paths in CLI and inspection payloads.
- Negative assertions guard against accidental reintroduction of `contracts_path` / `contracts_path_repo_relative`.

## Flake risks and stabilization

- All tests use temporary repositories/workflow packages and local JSON parsing only; no timing, network, or nondeterministic external dependencies are involved.
- Assertions use exact path sets or ordered lists derived from deterministic filename order to avoid filesystem-order flakes.

## Known gaps

- Full strictness scanning for banned legacy tokens remains owned by the later strictness phase rather than this phase-local test pass.
