# Implement ↔ Code Reviewer Feedback

- Task ID: recursive-framework-evolution-20260427t144615-bootstrap
- Pair: implement
- Phase ID: simple-lowering
- Phase Directory Key: simple-lowering
- Phase Title: Simple Workflow Lowering
- Scope: phase-local authoritative verifier artifact

- IMP-001 | blocking | `core/validation.py::_lower_simple_steps` rejects `workflow_step(...)` outright with `WorkflowValidationError("simple workflow step ... is not yet lowered in this implementation phase")`. The active phase contract keeps `workflow_step` in scope and requires simple declarations to lower into the existing workflow model. Concrete failure: a simple parent workflow with `start = workflow_step(Child)` and `flow = chain(start)` cannot compile at all. Minimal fix: implement the promised lowering for `workflow_step` into the existing definition/compiled model in this phase, or remove the helper from the in-scope deliverable only after an authoritative clarification changes intent.
- IMP-002 | blocking | `core/validation.py::_infer_simple_prompt_reads` only inspects inline prompt text and ignores `Prompt.file(...)` / `Path(...)` prompts, so file-backed simple prompts never infer readable artifacts. Concrete failure: `publish = step(Path("prompt.md"))` where `prompt.md` contains `{analysis}` compiles with `compiled.steps["publish"].reads == ()`, which breaks the phase requirement to infer unambiguous prompt-placeholder reads and drops provider-readable/dependency metadata for the same authored workflow when the prompt moves from inline text to a file. Minimal fix: centralize placeholder extraction through the existing prompt-resolution seam used for file prompts so simple read inference works for both inline and file-backed prompts without inferring `requires`.
- IMP-003 | non-blocking | `core/prompts.py::PromptRegistry.resolve` now routes absolute string keys through the shared filesystem-aware resolver, so a nominally in-memory registry will prefer an on-disk file over a registry entry when the key is an absolute path. I did not find an in-repo caller relying on absolute registry keys, so this is not a release blocker for the phase. Minimal follow-up: either add a regression test that documents this new precedence intentionally, or keep `source=\"registry\"` lookups registry-authoritative and reserve filesystem fallback for the explicit file-backed prompt paths.
