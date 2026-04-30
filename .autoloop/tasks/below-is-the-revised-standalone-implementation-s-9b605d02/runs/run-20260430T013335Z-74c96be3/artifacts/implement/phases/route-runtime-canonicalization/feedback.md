# Implement ↔ Code Reviewer Feedback

- Task ID: below-is-the-revised-standalone-implementation-s-9b605d02
- Pair: implement
- Phase ID: route-runtime-canonicalization
- Phase Directory Key: route-runtime-canonicalization
- Phase Title: Canonicalize Route And Runtime Internals
- Scope: phase-local authoritative verifier artifact

- IMP-001 | blocking | `core/_compat.py`, `core/compiler.py::_compile_route`, `core/validation.py::_valid_route_destinations`
  Active compilation and validation still accept the legacy in-memory contract instead of confining it to persisted-run/session/checkpoint readers. `core._compat` exposes live step wrappers (`LLMStep`, `PairStep`, `SystemStep`, `WorkflowStep`) plus `SUCCESS`, and the active validator/compiler explicitly honor that surface by adding `SUCCESS` to valid destinations and rewriting it to `FINISH`. A workflow authored today with `core._compat.LLMStep` and `SUCCESS` still compiles and runs through the main pipeline, which violates AC-1 and AC-2 and contradicts the recorded decision that historical terminal normalization must stay behind an explicit persisted-run compatibility seam. Minimal fix: remove `SUCCESS` acceptance from active validation/compiler, stop using live compat step wrappers as an authoring path, and relocate any remaining legacy translation to persisted-run/session/checkpoint readers only.

- Recheck CYCLE 2: `IMP-001` is resolved. Active compiler/validation no longer import `_compat`, `core._compat` no longer exposes live step wrappers or legacy route/terminal names, and the rewritten runtime compatibility coverage now keeps legacy behavior only in persisted session/checkpoint normalization tests. No additional findings in this phase re-review.
