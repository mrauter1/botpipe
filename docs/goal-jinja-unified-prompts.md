# Goal: Unified Jinja Prompt And Message Templating

Unify all prompt-like rendering on Jinja, without preserving legacy placeholder compatibility, and harden the existing Jinja file-prompt implementation without unrelated regressions.

## Context

This is a greenfield project. Do not keep the old single-brace `{ctx.foo}` renderer as a compatibility mode for prompts.

File-backed prompts, inline prompts, plain string prompt specs, operation prompts, and workflow-step messages should all use the same Jinja engine, the same context model, the same strict undefined behavior, and the same error style.

Do not sandbox or artificially restrict Jinja object access in this task. Expose the actual runtime objects needed by authors; authors are responsible for what their templates do. Do not use `SandboxedEnvironment`, safe proxy objects, or custom attribute/call blocking.

## Scope

Convert provider-facing prompt rendering to Jinja for:

- `Prompt.file(...)`
- `Prompt.inline(...)`
- plain string prompt specs that normalize to inline prompts
- `llm_call(...)` and `classify_call(...)` operation prompts

Convert `workflow_step(message=...)` rendering to Jinja.

Keep artifact path templates on the existing artifact placeholder system for now. Artifact path templating is a separate concern and should not be migrated in this task.

## Required Rendering Behavior

All prompt-like templates use Jinja syntax:

```jinja
{{ message }}
{{ input.topic }}
{{ params.mode }}
{{ state.status }}
{{ item.id }}
{{ worklist.gate.current.id }}
{{ branch.name }}
{{ fan_in.results }}
{% if input.topic %}
{% for artifact in artifacts %}
```

Do not render legacy single-brace prompt placeholders:

```text
{ctx.message}
{ctx.input.topic}
{input.topic}
{item.id}
```

These should either remain literal or fail validation where validation is expected. They must not be silently rendered in prompts or workflow-step messages.

Use one shared Jinja environment configuration for prompt-like rendering:

- `autoescape=False`
- `StrictUndefined`
- `trim_blocks=True`
- `lstrip_blocks=True`
- `keep_trailing_newline=True`

Expose full runtime objects through the Jinja context. At minimum expose:

- `message`
- `request`
- `input`
- `input_fields`
- `params`
- `workflow_params`
- `state`
- `artifacts`
- `item`
- `worklist`
- `branch`
- `fan_in`
- `run`
- `workflow`

Expose any existing prompt/runtime object roots required to avoid feature regression. These should behave consistently across file prompts, inline prompts, operation prompts, and workflow-step messages whenever the same runtime scope is available.

If a template references `{{ message }}` and the run request snapshot is unavailable, rendering must fail with a clear Botpipe error. Templates that do not reference `message` should not be forced to read the request snapshot.

## File Prompt Behavior

Preserve permissive top-level `Prompt.file(...)` path behavior. Do not newly restrict absolute paths or paths containing `..`. If the selected file is readable by the runtime filesystem/sandbox, it may be used. Do not add workspace-only prompt loading policy in this task.

Fix symlink/template-root semantics. Do not use `Path.resolve()` / realpath to choose the Jinja include root. The include root is the lexical parent directory of the prompt path selected by prompt resolution.

Examples:

- `Prompt.file("prompts/ask.md")` resolving to `/repo/workflow/prompts/ask.md`, where `ask.md` is a symlink to `/tmp/shared/ask.md`, uses `/repo/workflow/prompts` as the include root.
- `Prompt.file("../outside/ask.md")` resolving to `/repo/outside/ask.md` uses `/repo/outside` as the include root.
- `Prompt.file("/absolute/path/ask.md")` uses `/absolute/path` as the include root.

Keep include path safety for Jinja file prompts. Continue rejecting absolute include names and include names containing `..`. Includes should remain within the lexical loader root selected for the prompt.

## Static Validation

Static validation should understand Jinja everywhere practical.

- File prompts: recursively validate statically referenced includes with a visited set.
- Inline prompts and workflow-step messages: parse as Jinja and catch syntax errors and obvious unknown root variables.
- Dynamic includes may remain runtime-only if Jinja meta cannot resolve them.
- Error messages should identify the template surface, step/message/prompt path when available, and included template path/line when available.

## Required Tests

- File prompt renders Jinja variables, loops, conditionals, raw blocks, and includes.
- Inline prompt renders Jinja with the same roots as file prompts.
- Plain string prompt specs render through Jinja.
- `llm_call(...)` and `classify_call(...)` prompts render through Jinja.
- `workflow_step(message=...)` renders through Jinja.
- `item`, `worklist`, `branch`, and `fan_in` roots work in Jinja where the same runtime scope previously supported them.
- Legacy `{ctx.message}` / `{input.topic}` prompt syntax is not rendered.
- `{{ message }}` with no readable request snapshot fails clearly instead of rendering `None`.
- A prompt/message that does not reference `message` can render without a readable request snapshot.
- Unknown vars inside an included template are caught by compile/static validation.
- Syntax errors inside an included template are caught by compile/static validation.
- Nested missing includes and nested unsafe includes are caught by compile/static validation.
- A symlinked prompt under the prompt directory renders successfully when the filesystem/sandbox can read it.
- A relative include inside a symlinked prompt resolves from the symlink's lexical prompt directory, not the symlink target directory.
- Unsafe includes like `{% include "../secret.md" %}` remain rejected.
- Absolute `Prompt.file(...)` paths continue to work.
- `Prompt.file(...)` paths containing `..` continue to work when the selected file is readable.
- Artifact path templates still behave as before.

## Acceptance

- Focused prompt/Jinja tests pass.
- Existing relevant placeholder/artifact tests are updated only for intentional prompt-syntax migration.
- `py_compile` on changed Python files passes.
- Full test suite passes.
- No template-engine selection surface is added.
- No Mustache implementation is added.
- Docs/examples are updated to teach Jinja as the single prompt/message templating language.
