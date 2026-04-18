# Implement ↔ Code Reviewer Feedback

- Task ID: this-prompt-is-grounded-in-the-current-strict-au-111e9032
- Pair: implement
- Phase ID: generic-runtime-filesystem-refactor
- Phase Directory Key: generic-runtime-filesystem-refactor
- Phase Title: Refactor The Generic Runtime
- Scope: phase-local authoritative verifier artifact

- `IMP-001` `blocking` `autoloop_v3/runtime/runner.py::_prepare_run_context`
  The runner still constructs `FilesystemPromptRegistry(workflow_parent, workspace.root, Path.cwd())`, so prompt resolution depends on the shell’s current working directory in addition to the workflow and runtime state. That contradicts the phase requirement to keep prompt resolution deterministic: the same workflow can pick up different prompt files, or go from “prompt found” to “prompt missing”, solely because it was launched from a different directory. Minimal fix: remove the ambient `Path.cwd()` fallback from the generic runner, or make any extra prompt search root explicit in runner config/options rather than implicit process state, and add a regression test proving identical prompt resolution across different invocation directories.

- `IMP-002` `non-blocking` `autoloop_v3/tests/runtime/test_compatibility_runtime.py`
  The new compatibility test only exercises `superloop.yaml`; the phase deliverable and decisions ledger call out preserving `superloop.*` discovery, which also includes `superloop.config`. The runtime code already supports both filenames, but the reviewable coverage is still partial. Minimal fix: extend the discovery test with a small parametrized case that covers both legacy filenames.

- Re-review cycle 2:
  `IMP-001` addressed by removing the ambient `Path.cwd()` prompt root and adding an explicit cwd-independence regression test.
  `IMP-002` addressed by covering both `superloop.yaml` and `superloop.config`.
  No remaining findings in scope; `pytest -q autoloop_v3/tests/runtime/test_compatibility_runtime.py autoloop_v3/tests/runtime/test_workflow_integration_parity.py` passed (`35 passed`).
