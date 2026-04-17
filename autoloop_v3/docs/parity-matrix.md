# Parity Matrix

| Legacy behavior to preserve | Source evidence | Planned v3 owner | Planned proof |
| --- | --- | --- | --- |
| Workspace layout under `.autoloop/tasks/{task_id}` and `.autoloop/tasks/{task_id}/runs/{run_id}` | `autoloop.main.ensure_workspace`, `create_run_paths`, tests in `test_phase_local_behavior.py` | `runtime.workspace` | Filesystem integration tests |
| Immutable request snapshot in `runs/{run_id}/request.md` | `autoloop.main.create_run_paths` | `runtime.workspace` | Integration tests for fresh run and resume |
| Task-level and run-level raw logs | `autoloop.main.ensure_workspace`, `create_run_paths`, `append_raw_phase_log` | `runtime.logging` plus step log artifact writes | Golden log fixtures |
| Append-only decisions ledger with structured headers | `autoloop.main.append_decisions_header`, `append_clarification`, `parse_decisions_headers` | `runtime.logging` | Ledger parsing and sequence tests |
| Events log used to drive resume | `autoloop.main.load_resume_checkpoint` | `runtime.logging` plus `workflow.engine` checkpointing | Resume checkpoint tests |
| Explicit `phase_plan.yaml` plus validation | `autoloop.main.load_phase_plan`, `validate_phase_plan` | `runtime.workspace` plus workflow compiler inputs | Unit and integration tests |
| Implicit single-phase fallback when no explicit phase plan exists | `autoloop.main.build_implicit_phase_plan` and selection logic | `runtime.workspace` | Integration tests |
| Phase-local artifact directories keyed by `phase_dir_key` | `autoloop.main.phase_dir_key`, `ensure_phase_artifacts`, tests | `runtime.workspace` plus artifact registry | Artifact path tests |
| Phase-scoped sessions shared across implement and test for the active phase | `autoloop.main.phase_session_file`, `resolve_session_file`, tests | `workflow.context` plus `runtime.stores.filesystem` | Session store tests |
| Provider-neutral sessions with legacy `thread_id` compatibility | `SessionState`, `load_session_state`, `save_session_state` | `runtime.stores.filesystem` | Session migration tests |
| Clarification note stored in the active phase session only | `append_clarification`, tests | `workflow.engine` checkpoint semantics plus `runtime.logging` | Clarification tests |
| `plan.phase_plan` and `implement.impl_notes` produced-artifact attribute access | `autoloop_v1.py` | `workflow.steps` and `workflow.artifacts` | Authoring compatibility tests |
| `on_verdict` middleware interception | `autoloop_v1.py`, `Ralph_loop.py` | `workflow.compat` plus `workflow.engine` | Middleware contract tests |
| `SessionLifecycle.ON_START` session policy | `Ralph_loop.py` | `workflow.compat` | Compatibility tests |
| Legacy handler arities for pair, llm, and system steps | `autoloop_v1.py`, `Ralph_loop.py` | `workflow.compat` | Handler adapter tests |
| Legacy modules with missing annotation imports still load | `Ralph_loop.py` | `runtime.loader` | Import and execution tests |
| Config discovery from primary and legacy filenames | `discover_config_file`, `resolve_runtime_config`, tests | `runtime.config` | Config precedence tests |
| CLI support for workspace, resume, phase targeting, provider selection, and git toggles | `autoloop.main.build_arg_parser`, tests | `runtime.cli` | CLI smoke tests |
| Loop-control parsing and retry behavior where required by workspace workflows | `autoloop.loop_control`, old runtime call sites | `runtime.providers` adapters | Provider integration tests |

## High-Risk Parity Areas

- Loader compatibility for `Ralph_loop.py` because import failure can happen before normalization.
- Resume semantics because legacy behavior combines events, session state, and clarification persistence.
- Decisions and raw log append behavior because these artifacts are consumed as authoritative run history.
- Session scoping because phase-local state must remain isolated while the plan session remains task-global within the run.
