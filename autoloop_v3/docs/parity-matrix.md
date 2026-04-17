# Parity Matrix

| Behavior | Owner | Proof |
| --- | --- | --- |
| `.autoloop/tasks/{task_id}` and `.autoloop/tasks/{task_id}/runs/{run_id}` layout | `runtime.workspace` | runtime workspace tests |
| Immutable `runs/{run_id}/request.md` snapshot | `runtime.workspace` | runtime integration tests |
| Generic `events.jsonl` sequencing and `latest_run_status` compatibility | `runtime.events` | runtime and parity integration tests |
| Strict compile/load of `autoloop_v1.py` and `Ralph_loop.py` without loader injection | `runtime.loader` + `workflow.validation` | runtime integration tests |
| Pair/LLM optional handlers and required `SystemStep` handlers | `workflow.engine` + `workflow.validation` | contract and unit tests |
| Explicit session opening and direct session lookup | `workflow.context` + `workflow.engine` | contract tests |
| Autoloop-v1 plan session at `sessions/plan.json` | `autoloop_v3.workflows.autoloop_v1_support` | parity harness tests |
| Autoloop-v1 phase sessions at `sessions/phases/{phase}.json` | `autoloop_v3.workflows.autoloop_v1_support` | parity harness tests |
| Autoloop-v1 phase artifact paths under `implement/phases/{phase}` and `test/phases/{phase}` | `autoloop_v1.py` + `autoloop_v3.workflows.autoloop_v1_support` | generic runtime and parity harness tests |
| Task/run `raw_phase_log.md` append format | `autoloop_v3.workflows.autoloop_v1_support` | parity harness tests |
| Task `decisions.txt` clarification persistence | `autoloop_v3.workflows.autoloop_v1_support` | parity harness tests |
| Clarification note stored in the active session payload | `autoloop_v3.workflows.autoloop_v1_support` + `runtime.stores.filesystem` | parity harness tests |
| `question`, `blocked`, and `failed` status mapping for Autoloop-v1 | `autoloop_v3.workflows.autoloop_v1_support` | parity harness tests |
| `thread_id` to `session_id` compatibility in session payloads | `runtime.stores.filesystem` | runtime store tests |
| Resume requires `checkpoint.json`; session-only/event-only resume is rejected by the generic runtime | `runtime.runner` | runtime tests |
| Runtime remains phase-agnostic for unrelated workflows | `runtime.runner` | toy workflow runtime tests |

## Meaning Of Parity

Parity for `autoloop_v1.py` means:

- the strict workflow compiles and runs without shims
- the workspace keeps legacy-important files such as `raw_phase_log.md`, `decisions.txt`, `plan.json`, and `sessions/phases/{phase}.json`
- implement and test share the active phase session because the workflow rebinds `phase_session` in `activate_next_phase`
- clarification answers are persisted in both logs and the active session file
- blocked and failed runs preserve legacy-relevant `run_finished.status` values
- request snapshots, checkpoints, and overall successful run behavior remain intact
