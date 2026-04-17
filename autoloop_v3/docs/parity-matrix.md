# Parity Matrix

| Legacy behavior to preserve | Source evidence | v3 owner | Current proof |
| --- | --- | --- | --- |
| Workspace layout under `.autoloop/tasks/{task_id}` and `.autoloop/tasks/{task_id}/runs/{run_id}` | `autoloop.main.ensure_workspace`, `create_run_paths`, legacy workspace tests | `runtime.workspace` | `tests/runtime/test_compatibility_runtime.py`, `tests/runtime/test_workflow_integration_parity.py` |
| Immutable request snapshot in `runs/{run_id}/request.md` | `autoloop.main.create_run_paths` | `runtime.workspace` | Runtime integration tests for fresh run and resume |
| Task-level and run-level raw logs | `autoloop.main.ensure_workspace`, `create_run_paths`, `append_raw_phase_log` | `runtime.events` plus step log-artifact writes | Runtime artifact assertions in `test_compatibility_runtime.py` and clarification tests |
| Append-only decisions ledger with structured headers | `autoloop.main.append_decisions_header`, `append_clarification`, `parse_decisions_headers` | `runtime.events` | Decision-header parsing and clarification parity tests |
| Events log used to drive resume bookkeeping | `autoloop.main.load_resume_checkpoint` | `runtime.events` plus `workflow.engine` checkpointing | Resume checkpoint tests and run-status parity tests |
| Explicit `phase_plan.yaml` plus validation | `autoloop.main.load_phase_plan`, `validate_phase_plan` | `runtime.workspace` plus `workflow.compiler` consumers | Phase-plan scaffold and integration tests |
| Implicit single-phase fallback when no explicit phase plan exists | `autoloop.main.build_implicit_phase_plan` and selection logic | `runtime.workspace` | `test_autoloop_v1_invalid_phase_plan_falls_back_to_implicit_phase` |
| Phase-local artifact directories keyed by `phase_dir_key` | `autoloop.main.phase_dir_key`, `ensure_phase_artifacts` | `runtime.workspace` plus `workflow.artifacts` | Artifact path and workflow parity tests |
| Phase-scoped sessions shared across implement and test for the active phase | `autoloop.main.phase_session_file`, `resolve_session_file` | `workflow.context` plus `runtime.stores.filesystem` | Session-store tests and explicit multi-phase run assertions |
| Provider-neutral sessions with legacy `thread_id` compatibility | `SessionState`, `load_session_state`, `save_session_state` | `runtime.stores.filesystem` | Session migration and sparse-write preservation tests |
| Clarification note stored in the active phase session only | `append_clarification`, legacy tests | `runtime.events` plus `runtime.stores.filesystem` | Resume answer-injection parity tests |
| `plan.phase_plan` and `implement.impl_notes` produced-artifact attribute access | `autoloop_v1.py` | `workflow.steps` and `workflow.artifacts` | Compatibility and workflow integration tests |
| `on_verdict` middleware interception | `autoloop_v1.py`, `Ralph_loop.py` | `workflow.compat` plus `workflow.engine` | Middleware contract tests |
| `SessionLifecycle.ON_START` session policy | `Ralph_loop.py` | `workflow.compat` | Compatibility runtime tests |
| Legacy handler arities for pair, llm, and system steps | `autoloop_v1.py`, `Ralph_loop.py` | `workflow.compat` | Handler adapter and runtime execution tests |
| Legacy modules with missing annotation imports still load | `Ralph_loop.py` | `runtime.loader` | Import and execution tests for `Ralph_loop.py` |
| Config discovery from primary and legacy filenames | `discover_config_file`, `resolve_runtime_config`, legacy tests | `runtime.config` | Config precedence tests |
| CLI support for workspace, resume, provider selection, and compatibility flag validation | `autoloop.main.build_arg_parser`, legacy tests | `runtime.cli` plus `runtime.runner` | CLI unit coverage and end-to-end smoke execution |
| Target workflow execution for `autoloop_v1.py` and `Ralph_loop.py` | Workspace workflows in repo root | `runtime.runner` plus `workflow.engine` | End-to-end runtime tests with deterministic providers |
| Loop-control behavior remains outside the engine core | `autoloop.loop_control`, old runtime call sites | Provider factory boundary and legacy runtime | Option-rejection tests plus explicit compatibility documentation |

## High-Risk Parity Areas

- Loader compatibility for `Ralph_loop.py` because import failure can happen before normalization.
- Resume semantics because legacy behavior combines events, sessions, and clarification persistence.
- Decisions and raw-log append behavior because those artifacts are consumed as authoritative run history.
- Session scoping because phase-local state must remain isolated while plan-session state remains task-global within the run.
