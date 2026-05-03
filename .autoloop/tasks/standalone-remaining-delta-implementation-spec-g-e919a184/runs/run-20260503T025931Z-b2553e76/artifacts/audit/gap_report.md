# Intent Audit Gap Report

## Original intent considered

Source of truth reviewed:
- `request.md`: requested three concrete outcomes plus two focused pytest reruns.
- `raw_phase_log.md`: authoritative chronological ledger for clarifications and phase outputs.
- `decisions.txt`: run-local non-obvious decisions.
- Plan, implement, and test artifacts under this run's `artifacts/` tree.
- Final repository state in `cleanup.md`, `autoloop/runtime/cli.py`, `tests/runtime/test_package_cli.py`, and `tests/test_architecture_baseline_docs.py`.

Requested behavior checked:
- `cleanup.md` should document only the `autoloop` public authoring surface and remove remaining `autoloop.simple` guidance.
- `autoloop/runtime/cli.py` scaffolds for `single`, `flow-specs`, and `package` should emit the finalized `python_step` contract and compile under the current validator.
- `tests/runtime/test_package_cli.py` should validate the final scaffold contract directly, not only file creation.
- The two named pytest commands should be rerun.

## Clarifications / superseding decisions

- `raw_phase_log.md` contains no later user clarification that narrows or reverses the immutable request.
- `decisions.txt` block 1 preserves original scope and constrains implementation to one coherent slice: keep workflow shapes and init payloads unchanged while updating emitted starter source to the finalized one-argument `python_step` contract.
- `decisions.txt` block 2 records the final scaffold form used across shapes: decorator-based `@python_step(..., routes=...)`, single `ctx` parameter, and `ctx.state` mutation.
- `decisions.txt` block 3 records one extra regression guard consistent with intent: the default-shape scaffold test should assert the compiled bootstrap contract too.

## Implemented behavior

- `cleanup.md:3-11` now documents only the greenfield `autoloop` surface, explicitly tells authors to import from `autoloop`, names the canonical public symbols, and contains no `autoloop.simple` guidance.
- `autoloop/runtime/cli.py:516-569` now emits the finalized bootstrap scaffold in both source generators used by supported shapes:
  - `_single_file_workflow_source(...)` for `single`
  - `_flow_package_source(...)` for `flow-specs` and `package`
- The emitted starter contract is the finalized form requested by the run:
  - `@python_step(name="bootstrap", routes={"ready": FINISH})`
  - `def bootstrap(ctx):`
  - `ctx.state = ctx.state.model_copy(update={"ready": True})`
  - `return Event("ready")`
- `tests/runtime/test_package_cli.py:70-85` adds direct scaffold-source and compiled-contract helpers that assert the finalized contract and reject the legacy `_bootstrap(state, ctx)` / `python_step(_bootstrap, ...)` pattern.
- `tests/runtime/test_package_cli.py:980-1042` applies those checks to all supported shapes and to the default implicit `flow-specs` path, while preserving file-creation and duplicate-rejection assertions.
- `tests/test_architecture_baseline_docs.py:31-35` and `:175-180` continue to forbid `autoloop.simple`, and the requested doc test passes against the current `cleanup.md`.
- Requested validations rerun successfully in this audit turn:
  - `./.venv/bin/pytest -q tests/test_architecture_baseline_docs.py` -> `11 passed`
  - `./.venv/bin/pytest -q tests/runtime/test_package_cli.py -k 'init_workflow_scaffolds_supported_shapes_and_rejects_duplicates or init_workflow_defaults_to_flow_specs_shape'` -> `4 passed, 17 deselected`

## Unresolved gaps

No material unresolved gaps found.

## Differences justified by later clarification or analysis

- The run added one stronger regression check than the request stated explicitly: the default-shape `flow-specs` test now validates the compiled bootstrap contract in addition to emitted source and file creation. This is consistent with the request to check the final contract directly and does not remove or weaken any requested behavior.
- The decision ledger explicitly accepts `return Event("ready")` as the finalized starter route carrier under the current validator. This matches the current compiled behavior checked by `tests/runtime/test_package_cli.py:81-85` and is not a deviation from user intent.

## Recommended next run

No follow-up implementation is required for this request.
