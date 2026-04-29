# Implement ↔ Code Reviewer Feedback

- Task ID: full-revised-autoloop-v3-redesign-implementation-16af2351
- Pair: implement
- Phase ID: canonical-surface-and-topology-lowering
- Phase Directory Key: canonical-surface-and-topology-lowering
- Phase Title: Canonical surface and topology lowering
- Scope: phase-local authoritative verifier artifact

- IMP-001 `blocking` — `core/validation.py:_simple_prompt_text` (around lines 840-853) does not preserve `Prompt.ref(...)` registry semantics during compile-time placeholder analysis. It resolves every `Prompt.path` through `resolve_prompt_reference(..., search_roots=module_dir)`, so a registry prompt like `Prompt.ref("prompts/review.md")` can silently read a same-named filesystem file during validation and inferred-read extraction even though runtime `PromptRegistry.resolve(...)` would treat it as a registry lookup. That creates compile/runtime drift and can raise false unknown/ambiguous-placeholder errors or infer the wrong reads for registry-backed prompts. Minimal fix: branch on `prompt.source` and only search workflow-relative files for `Prompt.file(...)` / file shorthand, while `Prompt.ref(...)` should skip filesystem lookup unless registry text is explicitly available; add a regression test covering a registry prompt name that collides with a local file.

- IMP-002 `blocking` — `docs/authoring.md` still publishes legacy public examples and topology guidance instead of the requested canonical phase-1 surface. Examples at lines 128-143, 340-363, and 394-410 still teach `PairStep`, `Artifact`, global `transitions = {...}`, `Route.complete(...)`, and `SUCCESS`, which directly contradicts the accepted phase requirement to move public docs/examples/templates to `step`/`do_review_step`, `writes`, step-local `routes`, and `FINISH`. This means the main authoring doc still reinforces the legacy surface the phase is supposed to de-emphasize. Minimal fix: rewrite those public examples onto the canonical simple surface and move any remaining legacy-transition material into an explicit compatibility-only note instead of primary authoring examples.

- Review cycle 2 note — `IMP-001` is resolved: compile-time prompt analysis no longer reads colliding workflow-local files for `Prompt.ref(...)`, and the new regression test covers that case.

- IMP-003 `blocking` — `docs/authoring.md` still contains legacy public examples that keep AC-5 incomplete even after the broader doc rewrite. The prompt/artifact-resolution example at lines 250-255 still uses `Prompt("prompts/ask.md")` instead of the canonical `Prompt.file(...)`, and the worklist/scoped-step example at lines 430-445 still uses `PairStep(...)` as a primary authoring example rather than the phase-1 simple surface. These are still public guidance examples, not a compatibility appendix, so they continue reinforcing the legacy surface the phase is supposed to move away from. Minimal fix: rewrite those remaining examples to `Prompt.file(...)` and `step(...)` / `do_review_step(...)` with `scope=...`, or clearly fence them into an explicit compatibility-only section.
