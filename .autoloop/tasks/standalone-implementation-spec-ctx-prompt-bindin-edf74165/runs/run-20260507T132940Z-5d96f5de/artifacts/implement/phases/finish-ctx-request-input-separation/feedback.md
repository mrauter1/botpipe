# Implement ↔ Code Reviewer Feedback

- Task ID: standalone-implementation-spec-ctx-prompt-bindin-edf74165
- Pair: implement
- Phase ID: finish-ctx-request-input-separation
- Phase Directory Key: finish-ctx-request-input-separation
- Phase Title: Finish Ctx Request And Input Separation
- Scope: phase-local authoritative verifier artifact

## Findings

- IMP-002 `blocking` — `tests/runtime/test_workspace_and_context.py:736` and `tests/runtime/test_workspace_and_context.py:752` still exercise `request.context.input.message` for a workflow whose `Input` model only declares `topic`. The runtime implementation now correctly raises because `ctx.input.message` is no longer built in, so the focused runtime validation command fails on `test_resume_context_preserves_run_message_and_raw_input_fields`. That leaves the requested runtime regression coverage red and means AC-5 / the deliverable for updated runtime tests is not yet satisfied. Minimal fix: update that resume test to assert request text through `ctx.message` while keeping child input distinct, for example by recording `input_has_message: False` or another explicit non-alias check instead of reading undeclared `ctx.input.message`.

## Resolution Notes

- IMP-001 from verifier cycle 1 is resolved in the current workspace: `WorkflowInputView`, `Context.input`, discovery validation, and `ctx.*` runtime resolution no longer preserve undeclared `ctx.input.message`.
