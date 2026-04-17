# Compatibility Notes

There is no workflow compatibility layer in `autoloop_v3`.

Removed authoring compatibility:

- `workflow.compat`
- `Verdict`
- `on_verdict`
- `SessionLifecycle`
- loader-injected authoring symbols
- handler arity adaptation
- inferred entry fallback

What still remains intentionally compatible:

- session payloads that only contain legacy `thread_id`
- runtime config discovery from both `autoloop.*` and legacy `superloop.*` filenames
- `events.jsonl` `run_finished.status` values readable by legacy helpers such as `latest_run_status(...)`

Autoloop-v1 parity is preserved through workflow-owned code in `autoloop_v3.workflows.autoloop_v1_support`, not through hidden runtime or compiler behavior.
