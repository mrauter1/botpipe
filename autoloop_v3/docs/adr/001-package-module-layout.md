# ADR 001: Package And Module Layout

Status: Final

Authoritative record: [ARCHITECTURE_DECISIONS.md](../../ARCHITECTURE_DECISIONS.md)
Topic: `1. Final Package Layout`

Final decision:
- `autoloop_v3.workflow` is the strict canonical kernel.
- `autoloop_v3.runtime` is the workflow-agnostic filesystem runtime.
- `autoloop_v3.stdlib` is tiny pure authoring sugar.
- `autoloop_v3.extensions` is the tiny optional cross-cutting surface.
- `autoloop_v3.workflows` owns workflow-specific parity and conventions only.

Rejected shape:
- no mixed support layer that keeps absorbing reusable runtime behavior
- no Autoloop-specific runtime core
- no package layout that collapses generic runtime and workflow policy together
