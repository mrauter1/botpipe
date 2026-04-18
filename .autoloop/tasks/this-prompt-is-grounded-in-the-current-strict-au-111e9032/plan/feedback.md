# Plan ↔ Plan Verifier Feedback

- Added a six-phase implementation plan because the current codebase is already partially strict but still anchored on `workflow.observers`, lacks `stdlib/` and `extensions/`, and therefore needs a staged kernel/runtime/optional-surface/workflow/parity rewrite instead of a single undifferentiated refactor.
- Captured the key non-obvious boundaries explicitly: narrow the canonical root export surface, replace observers rather than carrying two extension models, keep persisted `thread_id` session compatibility unless later clarified otherwise, and keep exact Autoloop-v1 session/log/git policy workflow-owned rather than leaking it into runtime or reusable extensions.
