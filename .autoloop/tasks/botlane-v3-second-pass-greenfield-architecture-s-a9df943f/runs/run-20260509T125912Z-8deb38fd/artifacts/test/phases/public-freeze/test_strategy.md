# Test Strategy

- Task ID: botlane-v3-second-pass-greenfield-architecture-s-a9df943f
- Pair: test
- Phase ID: public-freeze
- Phase Directory Key: public-freeze
- Phase Title: Public Freeze
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Public root/core export freeze
  - `tests/unit/test_public_surface.py`
  - Exact `botlane.__all__`
  - Exact `botlane.core.__all__`
  - Exact current `botlane.core.branch_groups.__all__`
  - Internal plan/runtime types remain non-public
  - Deprecated/publicly removed names remain absent

- Branch-group export cutover staging
  - `tests/unit/test_public_surface.py`
  - Explicit skipped Phase 2 target assertion for removing compiled branch exports

- Simple public authoring and route sentinels
  - `tests/unit/test_simple_surface.py`
  - Workflow authoring example covering `step`, `produce_verify_step`, `python_step`, `workflow_step`
  - Route lowering coverage for `FINISH`, `AWAIT_INPUT`, `FAIL`, `SELF`, and `Route(target=SELF, summary=...)`

- SDK surface freeze
  - `tests/unit/test_sdk_facade.py`
  - Exact entrypoint signatures for `Botlane.run`, `Botlane.step`, `Botlane.prompt_step`, `Botlane.produce_verify_step`, `Botlane.python_step`, `Botlane.workflow_step`
  - Invocation-local policy layering without mutating supplied step objects
  - Existing SDK behavior coverage retained for helper execution, provider question handling, retention, and result shaping

- Botlane identity invariants
  - `tests/strictness/test_botlane_identity.py`
  - Canonical `.botlane`, `.botlane-sdk-task.json`, `botlane.sdk_task/v1`, and `botlane.branch_results/v1`
  - Direct `resolve_task_workspace(...)` assertion for `.botlane/tasks/<task_id>` path shape
  - Source scan against stale `autoloop*` package/state/schema identity strings
  - `botlane_optimizer` import graph still references the `botlane` namespace

## Preserved invariants checked

- No internal plan/runtime exports leaked through public package surfaces
- Current branch-group export surface is documented without forcing Phase 2 cutover early
- Public SDK helper surfaces remain stable without normalizing behavior regressions

## Edge cases and failure paths

- Import failures for non-public/internal names
- Identity scan fails on stale package or schema strings
- SDK policy test fails if invocation-local layering mutates the supplied step object

## Flake risk and stabilization

- No timing or network dependence
- Filesystem identity test uses `tmp_path` and deterministic path equality only
- Signature and export tests use exact tuples to avoid ordering ambiguity

## Known gaps

- Full `.botlane` runtime persistence behavior remains primarily covered by existing runtime suites outside this phase-local slice; this phase adds focused identity drift guards rather than duplicating the broader runtime tests.
