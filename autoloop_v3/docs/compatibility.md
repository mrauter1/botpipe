# Operational Compatibility Notes

There is no workflow compatibility layer in `autoloop_v3`.

Removed authoring compatibility:

- `workflow.compat`
- `Verdict`
- `on_verdict`
- `SessionLifecycle`
- loader-injected names
- handler arity adaptation
- inferred entry behavior
- observer-era public extension plumbing

Retained compatibility is narrow and operational only:

- legacy session payload compatibility for `thread_id`
- legacy-readable status values where parity tests require them
- config discovery from `autoloop.*` and legacy `superloop.*`

Autoloop-v1 parity remains workflow-owned through `autoloop_v3.workflows.autoloop_v1_conventions` and `autoloop_v3.workflows.autoloop_v1_parity`.

This document exists only to name the deliberately retained runtime/data compatibility surface.
