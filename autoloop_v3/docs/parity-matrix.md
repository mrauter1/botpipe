# Parity Matrix

| Behavior | Owner | Proof |
| --- | --- | --- |
| `.autoloop/tasks/{task_id}` and `.autoloop/tasks/{task_id}/runs/{run_id}` layout | `runtime.workspace` | runtime integration tests |
| Immutable `runs/{run_id}/request.md` snapshot | `runtime.workspace` | runtime integration tests |
| Generic append-only `events.jsonl` | `runtime.events` | runtime integration tests |
| Typed checkpoint persistence and resume | `workflow.primitives` + `runtime.runner` | contract and runtime tests |
| Deterministic prompt resolution | `runtime.prompts` + `workflow.prompts` | unit and runtime tests |
| Strict load/compile without loader injection or inferred entry | `runtime.loader` + `workflow.validation` + `workflow.compiler` | runtime integration and strictness tests |
| Pair/LLM optional handlers and required `SystemStep` handlers | `workflow.engine` + `workflow.validation` | contract tests |
| Explicit session opening and direct session lookup | `workflow.context` + `workflow.engine` | contract tests |
| Workflow-declared extension lifecycle invocation | `workflow.extensions` + `workflow.engine` + `runtime.runner` | contract tests |
| Autoloop-v1 plan session at `sessions/plan.json` | `autoloop_v3.workflows.autoloop_v1_conventions` + workflow-owned session-path policy | parity tests |
| Autoloop-v1 phase sessions at `sessions/phases/{phase}.json` | `autoloop_v3.workflows.autoloop_v1_conventions` + workflow-owned session-path policy | parity tests |
| Task/run `raw_phase_log.md` append behavior | `autoloop_v3.workflows.autoloop_v1_parity` | parity tests |
| Task `decisions.txt` clarification persistence | `autoloop_v3.workflows.autoloop_v1_parity` | parity tests |
| Clarification note stored in the active session payload | `autoloop_v3.workflows.autoloop_v1_parity` + `runtime.stores.filesystem` | parity tests |
| `question`, `blocked`, and `failed` status mapping for Autoloop-v1 | `autoloop_v3.workflows.autoloop_v1_parity` | parity tests |
| Legacy session payload compatibility for `thread_id` | `runtime.stores.filesystem` | unit and runtime tests |
| Config discovery from `autoloop.*` and legacy `superloop.*` | `runtime.config` | runtime tests |
| Runtime neutrality for unrelated workflows | `runtime.runner` | toy workflow runtime tests |

## Meaning Of Parity

Parity for `autoloop_v1.py` means:

- the strict workflow compiles and runs without shims
- the workspace keeps `raw_phase_log.md`, `decisions.txt`, `plan.json`, and `sessions/phases/{phase}.json`
- implement and test share the active phase session because the workflow rebinds it explicitly
- clarification answers persist in both workflow-owned parity artifacts and the active session payload
- blocked, question, failed, and success flows keep legacy-relevant operational behavior
- generic runtime artifacts such as `request.md`, `events.jsonl`, and `checkpoint.json` remain intact
