# Test Strategy

- Task ID: based-on-the-latest-pasted-v3-codebase-this-is-t-47dfd55c
- Pair: test
- Phase ID: public-surface-terminal-cut
- Phase Directory Key: public-surface-terminal-cut
- Phase Title: Public Surface And Terminal Cut
- Scope: phase-local producer artifact

## Behavior Coverage Map

- Public export hard cut:
  `tests/unit/test_simple_surface.py` covers canonical `autoloop` / `core` exports (`FINISH`, `AWAIT_INPUT`, `FAIL`, `SELF`, `RequestInput`, `Goto`, `Fail`) and verifies removed public names like `PAUSE`, `SUCCESS`, `review_step`, and related aliases fail import/surface checks.
- Authoring declaration hard cut:
  `tests/unit/test_stdlib_and_extensions.py` and adjacent strictness checks cover removed `on_route` entrypoints and the renamed route helper surface (`Route.await_input(...)`, `await_input_on_outcome_tags(...)`).
- Public runtime payload rename:
  `tests/runtime/test_package_cli.py` covers `run`, `resume`, `answer`, `runs show`, and `runs list` emitting canonical `status: "awaiting_input"` and `awaiting_input: bool`.
- Legacy persisted status compatibility:
  `tests/runtime/test_workspace_and_context.py` covers summary/task telemetry normalization from persisted `status="paused"` to public `awaiting_input`, and this turn adds direct `list_run_records(..., status="awaiting_input")` coverage for the read/filter boundary.
- Public CLI compatibility edge:
  `tests/runtime/test_package_cli.py` now covers `runs list --status awaiting_input` matching a legacy persisted `status="paused"` run and emitting normalized payload fields.

## Preserved Invariants

- Legacy `paused` survives only as persisted-fixture input for compatibility-read-path tests; public outputs and direct consumer expectations stay on `AWAIT_INPUT` / `awaiting_input`.
- Removed public names stay unavailable from `autoloop`, `autoloop.simple`, and `core`.
- The CLI/output boundary reports normalized status while resumability/selection semantics remain unchanged.

## Edge Cases And Failure Paths

- Empty/invalid summary filter values still raise `ValueError` in workspace summary helpers.
- Importing removed public symbols still fails explicitly rather than silently aliasing compatibility names.
- Status filtering accepts canonical `awaiting_input` even when persisted run metadata still stores legacy `paused`.

## Known Gaps

- This phase does not add runtime-control execution semantics coverage; those behaviors belong to later phases once `RequestInput`, `Goto`, and `Fail` are executable controls rather than public surface definitions only.
- Full test execution was not completed in this turn because the current interpreter environment is missing `pytest` (and import-time smoke runs remain blocked without `pydantic`).
