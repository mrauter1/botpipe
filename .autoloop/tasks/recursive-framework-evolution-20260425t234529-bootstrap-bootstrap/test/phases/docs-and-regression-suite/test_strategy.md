# Test Strategy

- Task ID: recursive-framework-evolution-20260425t234529-bootstrap-bootstrap
- Pair: test
- Phase ID: docs-and-regression-suite
- Phase Directory Key: docs-and-regression-suite
- Phase Title: Docs And Regression Sweep
- Scope: phase-local producer artifact

## Behavior to coverage map

- Broader runtime contract wording in public docs:
  covered by `tests/test_architecture_baseline_docs.py` assertions for `docs/architecture.md` and `docs/authoring.md`, including `RenderedLLMProvider`, `ProviderTransport`, `Handoff`, `ProviderRetryPolicy`, raw-output telemetry, and prompt-renderer boundary guidance.
- Scoped prompt README contract expansion:
  covered by `tests/test_architecture_baseline_docs.py::test_scoped_prompt_readmes_share_the_compact_contract_sections`, now locking required inputs, writable artifacts, route-specific artifact requirements, expected output payload requirements, optional route handoff, optional retry feedback, and raw-output telemetry wording across all scoped prompt READMEs.
- Workflow package README/runtime-doc drift:
  covered by the existing workflow-specific runtime doc tests updated in the implementation phase to assert the new contract language instead of the old three-field contract.
- Strict public authoring surface:
  covered by `tests/strictness/test_no_compat.py`, which now accepts `Handoff` in `workflow.__all__` and preserves the rest of the strict shim boundary.

## Preserved invariants checked

- Provider raw output remains documented as telemetry only and not provider-prompt input.
- Public CLI/config surface stays unchanged while docs move to the new rendered-provider boundary.
- The root `workflow` shim remains strict and does not re-expose engine/compiler internals.

## Edge cases / failure paths

- Future doc edits that keep the umbrella phrase but drop retry-feedback or route-handoff wording are now caught by baseline tests.
- Future shim regressions that remove `Handoff` from the public authoring surface are caught by strictness tests.

## Validation performed

- `.venv/bin/pytest -q tests/test_architecture_baseline_docs.py`

## Known gaps

- This turn did not add new engine/runtime execution-path tests because those paths were already covered and passing from the implementation phase’s targeted/full validation; the added value here is stronger baseline locking for AC-1 wording drift.
