# Implementation Notes

- Task ID: recursive-framework-evolution-20260423t120129-bootstrap
- Pair: implement
- Phase ID: public-cli-provider-contract
- Phase Directory Key: public-cli-provider-contract
- Phase Title: Remove Public Provider Factory Surfaces
- Scope: phase-local producer artifact

## Files changed

- `runtime/cli.py`
- `runtime/config.py`
- `runtime/runner.py`
- `tests/runtime/test_package_cli.py`
- `tests/runtime/test_provider_backends.py`
- `.autoloop/tasks/recursive-framework-evolution-20260423t120129-bootstrap/decisions.txt`

## Symbols touched

- `runtime.cli.build_arg_parser`
- `runtime.cli._resolve_provider`
- `runtime.config.ProviderConfigOverride`
- `runtime.config.parse_runtime_config`
- `runtime.config._merge_provider_config`
- `runtime.config._optional_cli_provider_name`
- `runtime.runner.run_workflow_package`
- `runtime.runner.execute_workflow_package`

## Checklist mapping

- Plan Phase 2 / add public provider selector: added parser-level `--provider` on mutating commands.
- Plan Phase 2 / remove public provider-factory surfaces: removed parser exposure of `--provider-factory` and deleted the runner factory-loader helper.
- Plan Phase 2 / route generic overrides through effective provider: generic config and CLI model/effort overrides now apply after final provider selection.
- Plan Phase 2 / preserve non-public seam: kept `cli.main(..., provider_factory=...)` precedence unchanged for tests/programmatic callers.
- Plan Phase 2 / CLI tests: added help-text, unknown-argument rejection, and selected-provider merge coverage.

## Assumptions

- Parser-level rejection of removed public flags is acceptable for this phase; no runtime compatibility alias is retained.
- Docs and recursive-wrapper cleanup remain for later scoped phases.

## Preserved invariants

- `cli.main(..., provider_factory=...)` still injects a provider ahead of built-in backend resolution.
- `run_workflow_package(..., provider=...)` and `execute_workflow_package(..., provider=...)` remain the direct non-CLI runner surfaces.
- Provider backend resolution without injection still goes through `runtime.provider_backends.resolve_provider_backend(...)`.

## Intended behavior changes

- Mutating CLI commands expose `--provider` and no longer expose `--provider-factory`.
- Passing `--provider-factory` on the public CLI now fails as an argparse unknown-argument error.
- `provider.model`, `provider.model_effort`, `--model`, and `--model-effort` now target the effective provider instead of always mutating Codex config.

## Known non-changes

- No docs were updated in this phase.
- No session-payload or recursive-wrapper changes were made in this phase.
- The non-public `provider_factory` seam remains intentionally undocumented.

## Expected side effects

- Public CLI callers must select providers through typed config or `--provider`.
- Tests that previously asserted runtime-level provider-factory rejection now assert parser-level unknown-argument rejection.

## Validation performed

- `./.venv/bin/python -m pytest tests/runtime/test_provider_backends.py tests/runtime/test_package_cli.py -k 'not recursive_wrapper_targets_the_package_cli_contract'`
- `./.venv/bin/python -m pytest tests/runtime/test_compatibility_runtime.py tests/runtime/test_provider_backends.py tests/runtime/test_package_cli.py -k 'not recursive_wrapper_targets_the_package_cli_contract'`

## Deduplication / centralization decisions

- Kept the public provider selection merge logic centralized in `runtime.config._merge_provider_config` instead of duplicating provider-specific override wiring in CLI handlers.
- Removed the now-dead `runtime.runner.load_provider_factory(...)` helper instead of leaving an unused module:function loader in runtime code.
