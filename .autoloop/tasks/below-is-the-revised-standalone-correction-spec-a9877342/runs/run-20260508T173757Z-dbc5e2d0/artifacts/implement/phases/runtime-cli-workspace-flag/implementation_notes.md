# Implementation Notes

- Task ID: below-is-the-revised-standalone-correction-spec-a9877342
- Pair: implement
- Phase ID: runtime-cli-workspace-flag
- Phase Directory Key: runtime-cli-workspace-flag
- Phase Title: Runtime CLI Workspace Flag
- Scope: phase-local producer artifact

## Files changed
- `autoloop/runtime/cli.py`
- `tests/runtime/test_package_cli.py`
- `tests/runtime/test_runtime_cli_metadata_integration.py`
- `docs/authoring.md`

## Symbols touched
- `autoloop.runtime.cli._WORKSPACE_HELP`
- `autoloop.runtime.cli.build_arg_parser`

## Checklist mapping
- Plan milestone 3 / AC-1: replaced public `--root` with required `--workspace` on shared runtime parser parents; updated covered runtime CLI command tests; added omission and legacy-flag rejection coverage.
- Plan milestone 3 / AC-2: aligned runtime CLI help assertions to workspace wording and absence of `--root`.
- Plan milestone 3 / AC-3: updated authoring doc command examples from `--root` to `--workspace`.

## Assumptions
- Keeping `dest="root"` is acceptable because the phase contract explicitly allows internal variables to keep the `root` name after argument resolution.

## Preserved invariants
- Runtime handlers still consume `args.root` and resolve the same workspace path semantics.
- Package-vs-workspace discovery behavior and workflow execution paths are unchanged apart from public flag parsing.

## Intended behavior changes
- Covered public runtime CLI entry points now require `--workspace`.
- Public runtime CLI no longer accepts `--root`.
- Public help and touched examples now describe the project directory as the workspace.

## Known non-changes
- No runtime handler logic or downstream variable names were renamed beyond parser argument wiring.
- No non-runtime SDK/simple surfaces were edited in this phase.

## Expected side effects
- Calls that previously relied on the implicit current working directory or the removed `--root` flag now fail with argparse usage errors until migrated to `--workspace`.

## Validation performed
- `./.venv/bin/pytest tests/runtime/test_package_cli.py tests/runtime/test_runtime_cli_metadata_integration.py`

## Deduplication / centralization
- Centralized the repeated workspace help string in `_WORKSPACE_HELP` so both shared parser parents stay text-identical.
