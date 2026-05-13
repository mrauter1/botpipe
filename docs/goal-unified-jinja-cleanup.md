# Goal: Unified Jinja Templating Cleanup

Implement the unified Jinja templating cleanup and audit the behavior for regressions.

## Context

This is a greenfield project. Do not preserve old single-brace placeholder compatibility for prompts, workflow-step messages, or artifact path templates. Jinja is the only template language for these surfaces.

## Design Decisions

### Request Text

- In Jinja, request text is available only as `{{ message }}` and `{{ request.text }}`.
- `{{ input.message }}` must not be supported in Jinja. `input` means typed structured workflow input only.
- If a template references `message` or `request.text` and the run request snapshot is unreadable, fail with a clear Botpipe error naming the template surface and path when available.
- Templates that do not reference request text must not read `request.md`.

### Context Construction

- Fix eager root hydration in prompt, message, and artifact Jinja rendering.
- Build Jinja context roots lazily from the parsed required roots.
- Do not materialize `input`, `message`, `request.text`, `history`, worklist state, branch/fan_in, or other potentially failing roots unless referenced.
- Keep full object access. Do not add `SandboxedEnvironment` or object-access restrictions.

### Artifact Templates

- Migrate artifact path rendering from old `{...}` placeholders to Jinja.
- Replace examples like `{workflow_folder}/reports/{input.topic}.md` with `{{ workflow.folder }}/reports/{{ input.topic }}.md` or the chosen canonical Jinja equivalent.
- Remove tests/docs that assert old artifact placeholder behavior, except where testing that old syntax is literal or rejected.
- Preserve important validation behavior: state/input/params/workflow/run/worklist/item/branch/fan_in refs must still be validated for scope and obvious unknown fields where practical.

### Prompt-Like Surfaces

- File prompts, inline prompts, plain string prompts, operation prompts, workflow-step messages, and artifact path templates should use one shared Jinja environment/configuration and compatible context roots.
- Legacy syntax such as `{ctx.message}`, `{input.topic}`, and `{item.id}` must not render.

### Artifact Namespace Correctness

- Replace plain dict step-artifact namespaces with collision-safe namespace views.
- `{{ review.items }}` must resolve the `items` artifact, not `dict.items`.
- Apply the same principle to framework-created dynamic value namespaces, such as `{{ summary.items }}`.
- Support both dot and bracket access.

### Artifact Iteration

- `artifacts` iteration should expose each real artifact once.
- Deduplicate by artifact identity, qualified name, or path, not by display name.
- Same-name artifacts from different steps, such as `draft.report` and `review.report`, must not collapse.

### Workflow-Step Messages

- Treat `workflow_step(message=...)` as a first-class Jinja surface.
- Include message refs in validation, reference graph, and inferred artifact reads.
- In simple workflow lowering, message artifact refs should infer reads like prompt refs.
- Do not convert inferred reads into required artifacts. Missing files should fail naturally only when rendered or read.

### File Prompt Paths

- Preserve permissive top-level `Prompt.file(...)` behavior: absolute paths and `..` paths are allowed when readable.
- Do not resolve symlinks to choose the include root. The include root is the lexical parent of the selected prompt path.
- Keep Jinja include safety for file prompts: reject absolute include names and include names containing `..`.

## Required Tests

Add focused regression tests for:

- `{{ input.message }}` rejected or undefined in Jinja while `{{ message }}` and `{{ request.text }}` work.
- Templates not referencing request text do not read missing or unreadable `request.md`.
- Artifact path templates use Jinja.
- Old single-brace artifact syntax no longer renders.
- Collision-safe artifact/value namespaces for names like `items`, `keys`, and `values`.
- Artifact iteration keeps same-name artifacts from different steps distinct.
- Workflow-step message artifact refs appear in the reference graph and infer reads.
- Existing prompt/file/symlink/include behavior remains correct.

## Verification

- Run focused prompt, artifact, and workflow-step tests.
- Run `py_compile` on changed Python files.
- Run the full test suite.
- Do not introduce unrelated refactors or regressions.
