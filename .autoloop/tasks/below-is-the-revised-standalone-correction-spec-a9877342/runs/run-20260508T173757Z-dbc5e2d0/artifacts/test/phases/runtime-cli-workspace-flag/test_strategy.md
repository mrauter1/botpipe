# Test Strategy

- Task ID: below-is-the-revised-standalone-correction-spec-a9877342
- Pair: test
- Phase ID: runtime-cli-workspace-flag
- Phase Directory Key: runtime-cli-workspace-flag
- Phase Title: Runtime CLI Workspace Flag
- Scope: phase-local producer artifact

## Behavior-to-test coverage map
- AC-1 required workspace selection:
  - `tests/runtime/test_package_cli.py::test_cli_requires_workspace_for_public_entry_points`
  - Covers omission failures for `workflows list`, `workflows show`, `run`, `resume`, `answer`, `runs list`, `runs show`, `logs`, and `init workflow`.
- AC-1 legacy flag rejection:
  - `tests/runtime/test_package_cli.py::test_cli_rejects_root_flag_for_public_entry_points`
  - Covers the same public entry points with valid `--workspace` plus rejected `--root`.
- AC-2 public help text uses workspace naming:
  - `tests/runtime/test_package_cli.py::test_cli_mutating_command_help_exposes_provider_and_hides_provider_factory`
  - `tests/runtime/test_package_cli.py::test_cli_common_workspace_help_surfaces_render_workspace_metavar`
  - `tests/runtime/test_package_cli.py::test_cli_help_exposes_package_commands_only`
  - `tests/runtime/test_runtime_cli_metadata_integration.py::test_cli_workflows_list_help_describes_package_and_dot_autoloop_roots`
  - Verifies `--workspace WORKSPACE`, rejects `--root` and `ROOT`, and preserves the package/workspace explanatory text.
- AC-3 touched public examples no longer advertise `--root`:
  - Covered indirectly by the doc update plus the runtime help assertions above; no separate doc parser exists in scope.

## Preserved invariants checked
- Shared `common` and `mutate` parser parents still expose their existing command-specific options.
- Top-level CLI help still lists the same package commands and does not grow subcommand-only options.
- Runtime command execution tests in `tests/runtime/test_package_cli.py` and `tests/runtime/test_runtime_cli_metadata_integration.py` still pass with the renamed flag.

## Edge cases and failure paths
- Missing required `--workspace` fails with argparse usage errors instead of silently defaulting to `cwd`.
- Unknown legacy `--root` fails even when a valid `--workspace` is present.
- Help rendering is checked across both mutating and common-parser command trees to catch metavar regressions.

## Stabilization notes
- Tests are deterministic: they use parser/help output or temporary workspace fixtures only, with no network or timing dependencies.
- The rejection tests provide `--workspace` alongside `--root` so argparse reports the unknown legacy flag rather than short-circuiting on the missing required option.

## Known gaps
- No broader documentation sweep was added because the phase contract limits docs to directly affected public examples in scope.
