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

Autoloop-v1 parity is preserved through workflow-owned code in `autoloop_v3.workflows.autoloop_v1_conventions` and `autoloop_v3.workflows.autoloop_v1_parity`, not through hidden runtime or compiler behavior.

The generic observer seam in `workflow.observers` is not a compatibility layer. It is the only reusable execution-observation mechanism, and it carries generic facts only.

There is also no generic workspace-hook system hiding under another name. Autoloop-v1 workspace augmentation remains explicit workflow-owned parity code because only that workflow needs it.
