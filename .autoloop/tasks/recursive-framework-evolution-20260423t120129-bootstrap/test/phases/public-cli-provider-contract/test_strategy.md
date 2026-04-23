# Test Strategy

- Task ID: recursive-framework-evolution-20260423t120129-bootstrap
- Pair: test
- Phase ID: public-cli-provider-contract
- Phase Directory Key: public-cli-provider-contract
- Phase Title: Remove Public Provider Factory Surfaces
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Public mutating CLI help surface:
  `tests/runtime/test_package_cli.py::test_cli_mutating_command_help_exposes_provider_and_hides_provider_factory`
  Confirms `run`, `resume`, and `answer` help expose `--provider` and omit `--provider-factory`.

- Public removed-flag failure path:
  `tests/runtime/test_package_cli.py::test_cli_run_rejects_public_provider_factory_flag`
  Confirms the public parser rejects `--provider-factory` as an unknown argument.

- Non-public injection seam preserved:
  `tests/runtime/test_package_cli.py::test_cli_mutating_commands_accept_non_public_provider_factory_injection_seam`
  `tests/runtime/test_provider_backends.py::test_cli_resolve_provider_preserves_non_public_injection_seam_precedence`
  Confirms `cli.main(..., provider_factory=...)` still works and still wins over the built-in resolver path.

- Typed provider selection and merge order:
  `tests/runtime/test_package_cli.py::test_cli_mutating_commands_route_public_provider_selection_through_typed_config`
  `tests/runtime/test_provider_backends.py::test_resolve_runtime_config_routes_generic_file_overrides_to_selected_provider`
  `tests/runtime/test_provider_backends.py::test_resolve_runtime_config_preserves_later_provider_specific_override_precedence`
  `tests/runtime/test_provider_backends.py::test_resolve_runtime_config_applies_generic_file_override_to_cli_selected_provider`
  `tests/runtime/test_provider_backends.py::test_resolve_runtime_config_applies_cli_override_after_provider_specific_file_config`
  `tests/runtime/test_provider_backends.py::test_resolve_runtime_config_routes_cli_overrides_to_selected_provider`
  Covers final-provider routing, later file-specific precedence over earlier generic config, and CLI last-wins behavior.

- Preserved non-CLI runner surface:
  `tests/runtime/test_workspace_and_context.py`
  Keeps direct `run_workflow_package(..., provider=...)` execution covered after removing the factory-loader helper.

## Preserved invariants checked

- Built-in resolver remains the normal non-injected CLI path.
- Public provider selection remains typed and backend-name-based only.
- File config, provider-specific config, and CLI overrides keep deterministic precedence.

## Edge cases / failure paths

- `--help` exits via argparse with stable captured output.
- Removed public flag rejection is asserted on the parser error text.
- Config precedence is checked across global config, local config, and CLI overlays without relying on YAML parsing being installed.

## Reliability notes

- Tests monkeypatch `load_runtime_config_file(...)` and write empty placeholder config files to avoid PyYAML/environment variance.
- CLI help and parser-error tests use local `capsys` capture and deterministic argument vectors only.

## Known gaps

- The recursive-wrapper contract test remains intentionally out of phase and was not expanded here.
