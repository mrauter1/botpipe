# Implement ↔ Code Reviewer Feedback

- Task ID: framework-authoring-flexibility-change-spec-goal-2ee572cd
- Pair: implement
- Phase ID: restore-runtime-contracts
- Phase Directory Key: restore-runtime-contracts
- Phase Title: Restore Runtime Contracts
- Scope: phase-local authoritative verifier artifact

- `IMP-001` `blocking` [autoloop/runtime/config.py::_load_narrow_yaml_mapping]
  The no-PyYAML fallback silently reparents indented child keys when the parent line held a scalar instead of opening a mapping, so malformed YAML is accepted with a different meaning instead of failing fast. Reproductions in the current tree: `runtime: true` followed by an indented `full_auto: false` parses as `{'runtime': True, 'full_auto': False}`, and `provider:` / `name: codex` followed by an over-indented `model: gpt-5` is also accepted. That violates the recorded decision that unsupported config constructs must still raise `ConfigError`, and it creates behavior drift between PyYAML and no-PyYAML environments on the exact runtime-config path this follow-up was meant to stabilize. Minimal fix: keep the fallback centralized in `_load_narrow_yaml_mapping(...)`, but track whether an indentation increase is only allowed immediately after an empty-value mapping entry; otherwise raise `ConfigError` instead of attaching the key to the wrong parent.

- Re-review cycle 2: `IMP-001` no longer reproduces. The fallback now rejects both malformed indentation shapes with `ConfigError`, focused regressions were added in `tests/runtime/test_provider_backends.py`, and the audited slice passed afterward.
