# Plan ↔ Plan Verifier Feedback

- Replaced the empty planning artifacts with an adapter-first implementation plan grounded in the current Botlane ownership boundaries: `compiler.py`, `context.py`, `engine_collaborators.py`, `runtime/workspace.py`, and `runtime/loader.py`.
- Decomposed the work into ordered phases that preserve `CompiledWorkflow`/`CompiledStep`/`CompiledRoute` and the current synthetic `Botlane.step(...)` path as rollback anchors until parity tests prove later migrations safe.
