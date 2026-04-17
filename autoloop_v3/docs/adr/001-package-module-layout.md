# ADR 001: Package And Module Layout

Status: Final

Authoritative record: [ARCHITECTURE_DECISIONS.md](../../ARCHITECTURE_DECISIONS.md)
Topic: `1. Package / Module Layout`

Final decision:
- `autoloop_v3.workflow` is the strict engine and authoring core.
- `autoloop_v3.runtime` is a workflow-agnostic filesystem runtime.
- `autoloop_v3.workflows` owns workflow-specific helpers and parity harnesses.
- The repo-root `workflow/` package is a strict re-export only.

Rejected shape:
- no root import shim with extra behavior
- no Autoloop-specific runtime core
- no package layout that mixes engine mechanics with workflow policy
