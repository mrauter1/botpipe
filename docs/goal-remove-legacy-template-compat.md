# Goal: Remove Legacy Template Compatibility

Remove the remaining legacy single-brace/template compatibility paths from Botpipe without introducing unrelated behavior regressions.

## Context

Botpipe is greenfield. Prompt-like surfaces and artifact path templates should use one Jinja implementation. Python handlers use the runtime `ctx` object; Jinja templates use explicit roots. Do not preserve `{ctx.foo}`, `{input.foo}`, partial placeholder rendering, or request-text aliases as compatibility behavior.

This goal is limited to templating, prompt/message/artifact rendering, request/input separation, and related docs/tests. Do not remove broader persisted-data or provider migration shims such as legacy paused statuses, provider config mapping, route-field normalization, or old run metadata handling unless they are directly tied to the old template renderer.

## Design Decisions

- Jinja must not expose raw `ctx` or `context` roots.
- Jinja request text is available only as `{{ message }}` and `{{ request.text }}`.
- Jinja `input` means typed structured workflow input only.
- `{{ input.message }}` must not be a supported request-text alias.
- Python runtime `ctx.message` and `ctx.request.text` remain the request-text APIs.
- Python runtime `ctx.input` should be the typed workflow input object when present, otherwise unavailable or `None`; it must not be a composite object containing `message`.
- `ctx.input_fields` may remain temporarily only as an internal/backward-compatible Python alias to the typed input object if removing it would create broad unrelated churn. It must not be exposed as a Jinja root unless there is a documented reason.
- Artifact templates must render through Jinja only. Do not keep partial rendering or unresolved template preservation.
- If an artifact template references branch or fan-in data outside the correct scoped context, fail clearly instead of preserving `{{ branch... }}` or `{{ fan_in... }}` text.

## Required Cleanup

1. Remove `ctx` and `context` from Jinja roots.
   - Update `botpipe/core/prompt_templates.py`.
   - Delete factories that expose the raw runtime context.
   - Replace any tests/docs using `{{ ctx.* }}` with explicit roots such as `{{ message }}`, `{{ request.file }}`, `{{ workflow.folder }}`, or `{{ input.topic }}`.

2. Remove the request-text alias workaround.
   - Remove the `ctx.input.*`, `ctx.message`, and `ctx.request.text` blacklist logic.
   - Keep only the real rule: `input` is typed input, and `input.message` is not a request-text alias.
   - Prefer normal field validation from the workflow `Input` model plus the existing ban on `Input.message`. If an explicit `{{ input.message }}` error remains, make it narrow and clear.

3. Remove the old single-brace renderer.
   - Remove or rewrite `botpipe/core/placeholders.py` so it no longer exports or implements `parse_placeholders`, `render_template_with_refs`, `render_placeholder_ref`, old runtime placeholder resolution, or old `{ctx.message}` validation.
   - If compiler/reference graph code still needs a ref dataclass, keep a neutral `TemplateRef` or `PlaceholderRef` type in a small module with no single-brace parser or renderer.
   - Remove stale errors that tell authors to use `{ctx.message}`.

4. Remove the `ctx.*` safe-placeholder whitelist.
   - Delete `botpipe/core/context_placeholders.py` if it has no non-template use after the old renderer is removed.
   - Remove tests that assert safe `{ctx.*}` placeholder paths.

5. Remove compiler/discovery hooks for old placeholders.
   - Delete unused legacy helpers such as `_validate_placeholder_refs` and `_infer_prompt_artifact_reads`.
   - Replace branch-group artifact validation that uses `parse_placeholders` with Jinja validation/ref inspection.
   - Jinja refs should be the only prompt/message/artifact validation path.

6. Remove `WorkflowInputView.message` and `ctx.input.message`.
   - Update `botpipe/core/context.py`.
   - `ctx.input` should expose the typed workflow input object, not a composite request-plus-input view.
   - `ctx.input.model_dump()` must not include `message`.
   - Update SDK, runtime, branch-group, and child-workflow tests that currently assert `ctx.input.message`.

7. Remove the ignored `replace_roots` parameter.
   - Update `botpipe/core/artifacts.py`.
   - Remove partial-render API shape from call sites and tests.

8. Remove SDK string matching for `"placeholder {"`.
   - Update `botpipe/sdk.py`.
   - Do not normalize errors by inspecting old placeholder text. Use real exception types or Jinja validation messages.

9. Remove deferred unresolved Jinja references.
   - Delete `_DeferredJinjaReference`.
   - Branch/fan-in artifact templates must be resolved only with a branch/fan-in context, or fail with a clear Botpipe error naming the surface/template where possible.
   - Audit call sites that resolved branch/fan-in artifact templates early and move resolution to the correct scoped context.

10. Update docs and tests.
   - Remove docs that teach `{ctx.*}`, `ctx.input.message`, `{{ ctx.* }}`, or single-brace artifact templates.
   - Update `docs/authoring.md`, `docs/sdk.md`, `docs/simple-api.md`, and related examples.
   - Replace `tests/unit/test_placeholder_refs.py` with focused Jinja ref/validation tests, or delete it if all coverage moves to Jinja tests.

## Required Behavior After Cleanup

- File prompts, inline prompts, plain string prompts, operation prompts, workflow-step messages, and artifact path templates use Jinja.
- `{{ message }}` and `{{ request.text }}` render request text.
- `{{ input.topic }}` renders typed input fields.
- `{{ input.message }}` does not render request text.
- `{{ ctx.input.topic }}` and `{{ context.input.topic }}` fail as unknown Jinja roots, not as special request-text aliases.
- Dynamic access cannot recover raw context, for example `{{ ctx|attr('input') }}` fails because `ctx` is undefined.
- Old single-brace strings such as `{ctx.message}` and `{input.topic}` are literal in prompt text or rejected in artifact templates, but never rendered.
- Artifact Jinja refs still validate known state/input/params fields and branch/fan-in scope where practical.
- Artifact iteration remains deduped consistently, including `artifacts|length` if this code is touched.

## Verification

- Run focused tests for prompt rendering, artifact templates, workflow-step messages, branch/fan-in artifact paths, SDK facade behavior, and context/request/input separation.
- Run a source scan proving old template compatibility is gone:
  - no `parse_placeholders` renderer call path
  - no `render_template_with_refs`
  - no `render_placeholder_ref`
  - no `context_placeholders`
  - no `"placeholder {"` SDK string matching
  - no docs recommending `{ctx.*}` or `ctx.input.message`
- Run `py_compile` on changed Python files.
- Run the full test suite. If the wheel smoke test needs package-build network or sandbox permissions, report that separately and do not hide other failures.

## Guardrails

- Keep changes tightly scoped to template cleanup.
- Do not reintroduce a second template language, template mode flag, or compatibility matrix.
- Do not restrict Jinja object access globally beyond removing the raw `ctx`/`context` roots.
- Do not add unrelated refactors.
- Preserve durable resume semantics and run-local request snapshot behavior.
- Preserve permissive top-level `Prompt.file(...)` path behavior and Jinja include safety.
