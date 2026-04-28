# Plan ↔ Plan Verifier Feedback

- Replaced the empty planning artifacts with a three-phase implementation plan covering retry feedback specificity, public primitive export, `workflow/` deletion, legacy-name cleanup, strictness/doc updates, and proof. Captured two repo-state risks that need explicit handling during implementation: active `ResolvedWorkflow.package` callers outside loader tests, and docs-baseline drift around the missing root `cleanup.md` surface.
