# Risk Register

| Risk | Why it matters | Control |
| --- | --- | --- |
| Session scope collisions across phases | Implement and test must share one phase session while different phases stay isolated | Explicit `ctx.open_session(slot, scope=...)` plus session rebinding tests |
| Prompt path drift in repo-root workflows | Prompt lookup is explicit now; hidden search-root hacks are gone | Prompt registry tests and explicit prompt paths in workflows |
| Generic runtime accidentally absorbs workflow policy | That would reintroduce Autoloop-specific coupling into the core | Keep parity behavior in `autoloop_v3.workflows.*` and prove toy workflow neutrality |
| Raw-log or decisions format drift for Autoloop-v1 | Those files are authoritative operational history | Dedicated parity harness tests |
| Resume semantics drift across question / blocked / failed flows | Resume depends on checkpoints, session bindings, and clarification persistence | Contract tests plus Autoloop-v1 resume parity tests |
| Missing import regressions in repo-root workflows | The loader no longer injects names, so workflow modules must be honest | Strict loader tests |
| Legacy session payloads with only `thread_id` | Existing files must still be readable | Filesystem session store compatibility tests |
| Documentation drift toward the removed compat model | The old docs advertised features that no longer exist | Baseline doc tests now freeze the strict public surface and migration notes |
