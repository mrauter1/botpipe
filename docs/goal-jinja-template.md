Implement Jinja as Autoloop’s default prompt-file templating system.

Context:
Autoloop is greenfield. Do not preserve an inferior legacy prompt-rendering behavior for compatibility. The current custom single-brace placeholder renderer is not part of a compatibility contract and should not remain as an alternate default path. The goal is a simpler, cleaner API surface: one default template language for standalone prompt files, with strict validation and minimal framework-specific syntax.

Primary objective:
Make file-backed prompts render through Jinja by default. Completely and correclty implement the goal stated in docs/goal-jinja-template.md without introducing regression bugs.

Design intent:
- Prompt files are first-class workflow artifacts.
- Non-trivial prompt files need ordinary template features: conditionals, loops, includes, whitespace control, and raw blocks.
- Jinja is the default and only file-template language.
- Avoid adding a template-engine option unless it is strictly necessary for tests or internal bootstrapping.
- Do not implement Mustache.
- Do not keep the old `{ctx.foo}` renderer as a parallel compatibility mode.
- Inline string prompts may remain simple literal prompt text if that is already the intended API, but file prompts must use Jinja.

Expected authoring model:
```python
class ReviewWorkflow(Workflow):
    draft = step(
        Prompt.file("prompts/draft.md"),
        writes=[Md("draft")]
    )

The file prompts/draft.md should be treated as Jinja automatically.

Recommended template context:
Expose a small, stable prompt context. Prefer short names over ctx.*.

Suggested roots:

message
input
params
state
artifacts
item
worklist
branch
fan_in
run
workflow

Example Jinja prompt:

# Review request

User message:
{{ message }}

{% if input.topic is defined %}
Topic: {{ input.topic }}
{% endif %}

{% if artifacts %}
Readable artifacts:
{% for artifact in artifacts %}
- {{ artifact.name }}: {{ artifact.path }}
{% endfor %}
{% endif %}

Implementation requirements:

Add Jinja as a runtime dependency if it is not already present.
Replace file-prompt rendering with a Jinja environment.
Configure Jinja for prompt files, not HTML:
autoescape=False
undefined=StrictUndefined
trim_blocks=True
lstrip_blocks=True
keep_trailing_newline=True
Use a filesystem loader rooted only in approved prompt/template directories.
Prevent template path escapes. Includes must not read outside approved prompt roots.
Do not expose the raw live runtime Context object to templates.
Build an explicit prompt-context view/dict from the runtime context.
Missing or misspelled variables must fail loudly.
Syntax errors, missing includes, unsafe paths, and undefined variables should produce clear Autoloop errors with the prompt path and, when available, line number.
Remove or bypass the old custom {...} placeholder substitution for file prompts.
Update compile-time/static prompt validation to understand Jinja templates where possible.
Use Jinja’s parsed AST/meta APIs where useful to detect undeclared variables and referenced templates during lint/compile.
Update tests to assert the new default behavior.
Delete or simplify tests that only exist to preserve the old file-prompt renderer.
Update docs/examples to show Jinja syntax as the normal prompt-file syntax.

Regression-avoidance requirements:

Keep the public authoring API simple.
Avoid adding a compatibility matrix or dual template modes.
Ensure existing non-prompt workflow execution behavior remains unchanged.
Ensure inline prompts, Python steps, routing, artifacts, policy, sessions, worklists, branch groups, and SDK behavior continue passing existing relevant tests.
Add focused tests before or alongside implementation changes.

Tests to add or update:

File prompt renders {{ message }}.
File prompt renders {{ input.some_field }} from a typed Input model.
File prompt renders {{ params.some_param }} from Params.
File prompt renders {{ state.some_field }}.
File prompt supports {% if %} conditionals.
File prompt supports {% for %} loops.
File prompt supports {% include %} within approved prompt roots.
File prompt rejects includes that escape prompt roots.
File prompt fails on undefined variables using StrictUndefined.
File prompt reports useful syntax errors.
Literal JSON with single braces does not require escaping.
Literal Jinja syntax can be represented with {% raw %} blocks.
Old {ctx.message} syntax is not silently rendered in file prompts.
autoloop lint or compile-time validation catches obvious missing variables/templates where applicable.
End-to-end workflow test confirms a provider-backed prompt step receives the rendered Jinja prompt.

Acceptance criteria:

Prompt.file("...") uses Jinja by default.
There is no legacy custom single-brace renderer for file prompts.
Jinja templates receive a small, documented, stable context.
Template errors are strict and actionable.
The test suite passes.
The public API is simpler, not more complex.
No new template-engine selection surface is introduced unless unavoidable and justified in code comments/tests.

Non-goals:

Do not add Mustache.
Do not preserve old file-prompt placeholder compatibility.
Do not expose raw ctx.
Do not implement arbitrary Python evaluation in templates.
Do not broaden file access through includes.
Do not add multiple prompt-template modes for greenfield compatibility.

I would use this version because it makes the greenfield constraint explicit and prevents Codex from “solving” the task by adding `template="jinja"` beside the old renderer.
