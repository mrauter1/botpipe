## Standalone implementation spec: `ctx.*` prompt bindings for message, input, state, and params

* **Implementation objective**

  * Add a safe, explicit runtime-context prompt binding surface under the `ctx.*` namespace.
  * Workflow authors must be able to access the run message in:

    * Python/system steps: `ctx.message`
    * Prompt templates: `{ctx.message}`
  * Workflow authors must be able to access structured workflow values in prompt templates:

    * `{ctx.input.<field>}`
    * `{ctx.state.<field>}`
    * `{ctx.params.<field>}`
  * Keep message, typed input, state, and params semantically distinct:

    * `ctx.message`: natural-language run request.
    * `ctx.input`: typed structured workflow input.
    * `ctx.state`: workflow state model.
    * `ctx.params`: workflow parameter model.
  * Do not introduce bare `{message}`.
  * Preserve backward compatibility for existing placeholder behavior, including existing bare `{input.foo}`, `{state.foo}`, or `{params.foo}` behavior if already supported.
  * Make `ctx.*` the preferred and documented runtime-context prompt namespace.

* **Current code assumptions**

  * The runtime already persists run request text as a run-local `request.md`, and run path creation returns a `request_file` path. 
  * `Context` already exposes runtime surfaces such as `state`, `input`, `params`, `workflow_params`, `values`, `branch`, `fan_in`, `run`, and `workflow`; this patch adds request/message access and prompt binding for selected stable fields. 
  * Child workflow invocation already distinguishes `message` and typed `input`, so this patch must keep those concepts separate. 

* **Final author-facing API**

  * Python/system step access:

    ```python
    ctx.message
    ctx.request.text
    ctx.request.file
    ctx.request.task_file
    ctx.request_file
    ctx.input.<field>
    ctx.state.<field>
    ctx.params.<field>
    ```
  * Prompt-template access:

    ```text
    {ctx.message}
    {ctx.request.text}
    {ctx.request.file}
    {ctx.request.task_file}
    {ctx.request_file}
    {ctx.input.<field>}
    {ctx.state.<field>}
    {ctx.params.<field>}
    ```
  * Example:

    ```python
    class ReviewRequest(Workflow):
        name = "review_request"

        class Input(BaseModel):
            topic: str

        class Params(BaseModel):
            mode: str = "brief"

        class State(BaseModel):
            status: str = "draft"

        review = step(
            """
            Request:
            {ctx.message}

            Topic:
            {ctx.input.topic}

            Mode:
            {ctx.params.mode}

            Current status:
            {ctx.state.status}
            """,
            writes=(Md("review"),),
            routes={"done": FINISH},
        )
    ```

* **Message semantics**

  * `ctx.message`

    * Type: `str`.
    * Source: the current run’s run-local request snapshot file.
    * Default path: `ctx.run_folder / "request.md"`.
    * Must not read mutable task-level request metadata after run creation.
    * Must not read a fresh `RunnerOptions.message` during resume.
    * Must be stable across run resume.
  * Text normalization:

    * Read as UTF-8.
    * Return `request_file.read_text(encoding="utf-8").rstrip("\n")`.
    * Preserve internal newlines.
    * Preserve leading spaces.
    * Preserve trailing spaces except trailing newline characters.
  * Error behavior:

    * If the request file cannot be read for any filesystem reason, raise `WorkflowExecutionError`.
    * Error message:

      ```text
      run request snapshot could not be read: <path>
      ```

* **Request object semantics**

  * Add:

    ```python
    @dataclass(frozen=True, slots=True)
    class RequestContext:
        file: Path
        task_file: Path | None = None

        @property
        def text(self) -> str:
            try:
                return self.file.read_text(encoding="utf-8").rstrip("\n")
            except OSError as exc:
                raise WorkflowExecutionError(
                    f"run request snapshot could not be read: {self.file}"
                ) from exc
    ```
  * `ctx.request.text == ctx.message`.
  * `ctx.request.file == ctx.request_file`.
  * `ctx.request.file` points to the run-local request snapshot.
  * `ctx.request.task_file` points to task-level `request.md` when available; otherwise `None`.
  * `RequestContext.text` should read lazily, so simply accessing `ctx.request.file` does not read message text.

* **Context implementation**

  * In `autoloop/core/context.py`, add optional keyword-only parameters to `Context.__init__`:

    ```python
    request_file: Path | None = None
    task_request_file: Path | None = None
    ```
  * Derive request paths:

    ```python
    self._request_file = Path(request_file) if request_file is not None else run_folder / "request.md"

    if task_request_file is not None:
        self._task_request_file = Path(task_request_file)
    else:
        candidate = task_folder / "request.md"
        self._task_request_file = candidate if candidate.exists() else None
    ```
  * Add read-only properties:

    ```python
    @property
    def request_file(self) -> Path:
        return self._request_file

    @property
    def request(self) -> RequestContext:
        return RequestContext(file=self._request_file, task_file=self._task_request_file)

    @property
    def message(self) -> str:
        return self.request.text
    ```
  * Ensure synthetic unit-test contexts work by deriving `request_file` from `run_folder` when omitted.

* **Branch and fan-in context propagation**

  * In `autoloop/core/branch_groups/context.py`, preserve request context when cloning contexts.
  * In `create_branch_context(...)`, pass:

    ```python
    request_file=parent.request_file
    task_request_file=parent.request.task_file
    ```
  * In `create_fan_in_context(...)`, pass the same values.
  * Branch and fan-in contexts must observe the same `ctx.message` as the parent run.

* **Runner context construction**

  * In `autoloop/runtime/runner.py`, update every root `Context(...)` construction.
  * Pass the run request file explicitly:

    ```python
    request_file=<run request file path>
    ```
  * Pass the task request file when available:

    ```python
    task_request_file=<task request file path or None>
    ```
  * Child workflow runs must receive the child run’s own `request_file`, not the parent run’s request file.
  * Do not change CLI flags.
  * Do not change run persistence layout.

* **Typed input semantics**

  * `ctx.input` remains typed structured workflow input.
  * `ctx.input` must never alias `ctx.message`.
  * `{ctx.input.<field>}` is valid only when:

    * The workflow declares `class Input(BaseModel)`.
    * `<field>` exists in `Input.model_fields`.
  * `{ctx.input}` is invalid.
  * Runtime behavior:

    * If `{ctx.input.<field>}` renders while `ctx.input is None`, raise `WorkflowExecutionError`.
    * Error message:

      ```text
      ctx.input.<field> requires workflow input, but no input was provided
      ```

* **State semantics**

  * `ctx.state` remains the workflow state object.
  * `{ctx.state.<field>}` is valid only when `<field>` exists in the effective workflow state model.
  * `{ctx.state}` is invalid.
  * Runtime rendering:

    * `None` renders as an empty string.
    * Scalar values render with `str(value)`.
    * Supported scalar types:

      * `str`
      * `int`
      * `float`
      * `bool`
      * `Path`
      * `None`
    * Complex values should raise `WorkflowExecutionError`.
    * Error message:

      ```text
      <placeholder_label> {ctx.state.<field>} resolved to a non-scalar value
      ```

* **Params semantics**

  * `ctx.params` remains the typed workflow params object.
  * `{ctx.params.<field>}` is valid only when:

    * The workflow declares an effective `Params` model.
    * `<field>` exists in `Params.model_fields`.
  * `{ctx.params}` is invalid.
  * Runtime scalar rendering rules match `ctx.state.<field>`.

* **Prompt binding grammar**

  * Supported required `ctx.*` placeholders:

    ```text
    {ctx.message}
    {ctx.request.text}
    {ctx.request.file}
    {ctx.request.task_file}
    {ctx.request_file}
    {ctx.input.<field>}
    {ctx.state.<field>}
    {ctx.params.<field>}
    ```
  * Supported optional stable metadata placeholders:

    ```text
    {ctx.task_id}
    {ctx.run_id}
    {ctx.workflow_name}
    {ctx.task_folder}
    {ctx.workflow_folder}
    {ctx.run_folder}
    {ctx.package_folder}
    {ctx.root}
    {ctx.run.id}
    {ctx.run.folder}
    {ctx.workflow.name}
    {ctx.workflow.folder}
    ```
  * Explicitly unsupported:

    ```text
    {message}
    {ctx}
    {ctx.request}
    {ctx.input}
    {ctx.state}
    {ctx.params}
    {ctx.values.*}
    {ctx.artifacts.*}
    {ctx.session.*}
    {ctx.step_state.*}
    {ctx.item_state.*}
    {ctx.step_item_state.*}
    ```
  * Existing non-`ctx` placeholder behavior must remain backward-compatible.

* **Template safety rules**

  * The renderer must remain a safe dotted-path resolver.
  * The renderer must not evaluate Python.
  * For `ctx.*`, reject any placeholder containing:

    * `__`
    * A path segment starting with `_`
    * `(`
    * `)`
    * `[`
    * `]`
    * quotes
    * whitespace inside a path segment
  * Invalid examples:

    ```text
    {ctx.message.upper()}
    {ctx.__dict__}
    {ctx.request.file.read_text()}
    {ctx["message"]}
    {open(ctx.request.file).read()}
    ```
  * Do not expose raw `Context` internals.
  * Do not expose session stores, provider metadata, runtime event sinks, workflow invokers, or runtime-private fields.

* **Shared placeholder contract module**

  * Create a shared helper module:

    ```text
    autoloop/core/context_placeholders.py
    ```
  * This module owns:

    * Safe `ctx.*` segment validation.
    * Allowed scalar `ctx` fields.
    * Allowed nested `ctx` fields.
    * Allowed model roots.
    * Compile-time validation helpers.
    * Runtime path validation helpers.
  * Suggested constants:

    ```python
    CTX_SCALAR_FIELDS = {
        "message",
        "request_file",
        "task_id",
        "run_id",
        "workflow_name",
        "task_folder",
        "workflow_folder",
        "run_folder",
        "package_folder",
        "root",
    }

    CTX_NESTED_FIELDS = {
        "request": {"text", "file", "task_file"},
        "run": {"id", "folder"},
        "workflow": {"name", "folder"},
    }

    CTX_MODEL_ROOTS = {"input", "state", "params"}
    ```
  * Suggested helper:

    ```python
    def validate_safe_ctx_reference(reference: str) -> tuple[str, ...]:
        ...
    ```
  * Use this module from:

    * `autoloop/core/discovery.py`
    * `autoloop/core/artifacts.py`
    * `autoloop/core/prompt_validation.py`, if applicable.
  * Do not duplicate allowlists across files.

* **Runtime prompt view**

  * In `autoloop/core/artifacts.py`, add a lazy prompt context view.
  * Do **not** use a dataclass that eagerly materializes `message=context.message`.
  * Use a lazy wrapper:

    ```python
    class PromptContextView:
        def __init__(self, context: Context) -> None:
            self._context = context

        @property
        def message(self) -> str:
            return self._context.message

        @property
        def request(self) -> RequestContext:
            return self._context.request

        @property
        def request_file(self) -> Path:
            return self._context.request_file

        @property
        def input(self) -> BaseModel | None:
            return self._context.input

        @property
        def state(self) -> BaseModel:
            return self._context.state

        @property
        def params(self) -> BaseModel:
            return self._context.params

        @property
        def task_id(self) -> str:
            return self._context.task_id

        @property
        def run_id(self) -> str:
            return self._context.run_id

        @property
        def workflow_name(self) -> str:
            return self._context.workflow_name

        @property
        def task_folder(self) -> Path:
            return self._context.task_folder

        @property
        def workflow_folder(self) -> Path:
            return self._context.workflow_folder

        @property
        def run_folder(self) -> Path:
            return self._context.run_folder

        @property
        def package_folder(self) -> Path:
            return self._context.package_folder

        @property
        def root(self) -> Path:
            return self._context.root

        @property
        def run(self):
            return self._context.run

        @property
        def workflow(self):
            return self._context.workflow
    ```
  * This avoids reading `request.md` unless `{ctx.message}` or `{ctx.request.text}` is actually rendered.

* **Runtime placeholder resolution**

  * In `autoloop/core/artifacts.py`, update `_resolve_placeholder(...)`.
  * Add:

    ```python
    elif root_name == "ctx":
        current = PromptContextView(context)
    ```
  * Apply safe `ctx.*` path validation before traversing the view.
  * Add scalar rendering for `ctx.*` resolved values.
  * Recommended helper:

    ```python
    def _render_prompt_value(value: Any, *, expression: str, placeholder_label: str) -> str:
        if value is None:
            return ""
        if isinstance(value, (str, int, float, bool, Path)):
            return str(value)
        raise WorkflowExecutionError(
            f"{placeholder_label} {{{expression}}} resolved to a non-scalar value"
        )
    ```
  * Use scalar rendering for `ctx.*`.
  * Preserve existing non-`ctx` rendering behavior.

* **Artifact path rejection**

  * `ctx.*` placeholders must be rejected in artifact path templates.
  * Add:

    ```python
    def _reject_ctx_placeholders_in_artifact_template(template: str) -> None:
        for placeholder in _PLACEHOLDER_RE.findall(template):
            if placeholder.strip().split(".", 1)[0] == "ctx":
                raise WorkflowExecutionError(
                    "ctx.* placeholders are only supported in prompts and workflow-step messages, not artifact paths"
                )
    ```
  * Call this at the start of `resolve_artifact_template(...)`, before generic template rendering.
  * Do not alter existing artifact template placeholder behavior except this explicit rejection.
  * Existing placeholders such as `{workflow_folder}`, `{run_folder}`, `{item.id}`, and `{branch.name}` must keep working where they already work.

* **Compile-time simple prompt validation**

  * In `autoloop/core/discovery.py`, update `_validate_simple_prompt_reference(...)`.
  * Handle `ctx` before generic single-segment handling:

    ```python
    if reference == "ctx":
        raise WorkflowValidationError(
            f"simple step {step_name!r} prompt placeholder {{ctx}} must qualify a runtime context field"
        )

    if reference.startswith("ctx."):
        return _validate_ctx_prompt_reference(...)
    ```
  * Do not add bare `message` to `SIMPLE_CONTEXT_BARE_NAMES`.
  * Do not make `{message}` valid.
  * Add `_validate_ctx_prompt_reference(...)`.
  * Validation requirements:

    * Reject unsafe syntax through shared helper.
    * Accept:

      * `ctx.message`
      * `ctx.request.text`
      * `ctx.request.file`
      * `ctx.request.task_file`
      * `ctx.request_file`
      * `ctx.input.<field>`
      * `ctx.state.<field>`
      * `ctx.params.<field>`
      * optional stable metadata listed above.
    * For `ctx.input.<field>`:

      * Require `Input` model exists.
      * Require `<field>` exists in `Input.model_fields`.
    * For `ctx.state.<field>`:

      * Require `<field>` exists in effective state model fields.
    * For `ctx.params.<field>`:

      * Require effective params model exists.
      * Require `<field>` exists in params model fields.
    * Reject:

      * `ctx.input`
      * `ctx.state`
      * `ctx.params`
      * `ctx.request`
      * unknown fields.
  * Return `None` for valid `ctx.*` references because they do not imply artifact reads.
  * Preserve artifact read inference for existing artifact placeholders.
  * Preserve existing validation for `item`, `worklist`, `branch`, `fan_in`, artifacts, and prior step outputs.

* **Provider prompt rendering**

  * In `autoloop/core/engine.py`, find provider prompt rendering, likely `_resolve_prompt(...)`.
  * Add `ctx` to the runtime replacement roots:

    ```python
    replace_roots=frozenset({"ctx", "item", "worklist", "branch", "fan_in"})
    ```
  * This must cover:

    * `step(...)`
    * `produce_verify_step(...)` producer prompt
    * `produce_verify_step(...)` verifier prompt.
  * Providers should receive fully rendered prompt text.
  * No Codex/Claude provider adapter-specific changes should be needed unless tests show prompt text bypasses this path.

* **Operation prompt rendering**

  * In `autoloop/core/operations.py`, find operation prompt rendering for:

    * `llm.step(...)`
    * `classify.step(...)`
  * Add `ctx` to replacement roots:

    ```python
    replace_roots=frozenset({"ctx", "item", "worklist", "branch", "fan_in"})
    ```
  * Verify both `llm.step(prompt=...)` and `classify.step(prompt=...)` render:

    * `{ctx.message}`
    * `{ctx.input.<field>}`
    * `{ctx.state.<field>}`
    * `{ctx.params.<field>}`.

* **Child workflow message rendering**

  * In `autoloop/core/engine.py`, update `_resolve_workflow_step_message(...)`.
  * Current behavior that returns `step.message` literally must change only for supported placeholders.
  * New behavior:

    ```python
    if step.message is not None:
        return render_runtime_template(
            step.message,
            context,
            placeholder_label=f"workflow step {step.name!r} message placeholder",
            replace_roots=frozenset({"ctx", "item", "worklist", "branch", "fan_in"}),
        )
    ```
  * Preserve `message_from` behavior:

    * If `message_from` points to an artifact/path, read file content literally.
    * Do not render templates inside `message_from` content.
  * Preserve fallback default:

    ```text
    Run child workflow <workflow_name>.
    ```
  * This must enable:

    ```python
    workflow_step(
        ChildWorkflow,
        message="{ctx.message}",
        input={"topic": "alpha"},
        routes={"done": FINISH},
    )
    ```

* **Prompt validation module**

  * Inspect `autoloop/core/prompt_validation.py`.
  * If it performs independent placeholder validation:

    * Add `ctx.*` support using `context_placeholders.py`.
  * If it does not validate these placeholders:

    * No change required.
  * Do not create inconsistent validation paths.

* **Simple authoring surface**

  * In `autoloop/simple.py`:

    * No public function signature changes are required.
    * No new import is required for authors to use `{ctx.message}`.
    * Update examples/docstrings if present.
  * Keep `workflow_step(...)` parameters:

    * `message`
    * `message_from`
    * `params`
    * `input`

* **Backward compatibility**

  * Existing workflows without `ctx.*` placeholders must behave exactly as before.
  * Existing Python steps manually reading `ctx.run_folder / "request.md"` must keep working.
  * Existing prompt placeholders for `item`, `worklist`, `branch`, and `fan_in` must keep working.
  * Existing artifact placeholders must keep working except explicit rejection of `ctx.*`.
  * Existing `workflow_step(message="literal text")` must still pass literal text.
  * Existing `workflow_step(message_from=...)` must still read file/artifact content literally.
  * Existing `ctx.input`, `ctx.params`, and `ctx.state` behavior in Python steps must not change.
  * Existing bare `{input.foo}`, `{state.foo}`, and `{params.foo}` behavior must remain compatible if already supported.
  * Bare `{message}` remains unsupported.

* **Compile-time error messages**

  * `{message}`:

    ```text
    simple step '<step>' prompt placeholder {message} is unknown; use {ctx.message}
    ```
  * `{ctx}`:

    ```text
    simple step '<step>' prompt placeholder {ctx} must qualify a runtime context field
    ```
  * `{ctx.request}`:

    ```text
    simple step '<step>' prompt placeholder {ctx.request} must qualify a request field
    ```
  * `{ctx.input}`:

    ```text
    simple step '<step>' prompt placeholder {ctx.input} must qualify an input field
    ```
  * `{ctx.input.missing}`:

    ```text
    simple step '<step>' prompt placeholder {ctx.input.missing} references unknown Input field 'missing'
    ```
  * `{ctx.params}`:

    ```text
    simple step '<step>' prompt placeholder {ctx.params} must qualify a params field
    ```
  * `{ctx.params.missing}`:

    ```text
    simple step '<step>' prompt placeholder {ctx.params.missing} references unknown Params field 'missing'
    ```
  * `{ctx.state}`:

    ```text
    simple step '<step>' prompt placeholder {ctx.state} must qualify a state field
    ```
  * `{ctx.state.missing}`:

    ```text
    simple step '<step>' prompt placeholder {ctx.state.missing} references unknown State field 'missing'
    ```
  * Unsafe placeholder:

    ```text
    simple step '<step>' prompt placeholder {ctx.__dict__} is not a supported safe dotted path
    ```
  * Artifact path rejection:

    ```text
    ctx.* placeholders are only supported in prompts and workflow-step messages, not artifact paths
    ```

* **Runtime error messages**

  * Request file read error:

    ```text
    run request snapshot could not be read: <path>
    ```
  * Missing runtime input:

    ```text
    ctx.input.<field> requires workflow input, but no input was provided
    ```
  * Non-scalar value:

    ```text
    <placeholder_label> {ctx.state.<field>} resolved to a non-scalar value
    ```
  * Unsafe runtime placeholder:

    ```text
    <placeholder_label> {ctx.__dict__} is not a supported safe dotted path
    ```

* **Tests: context API**

  * Create a `Context` with `run_folder / "request.md"` containing:

    ```text
    Build a rollout plan
    ```
  * Assert:

    ```python
    ctx.message == "Build a rollout plan"
    ctx.request.text == "Build a rollout plan"
    ctx.request.file == ctx.request_file
    ctx.request_file == run_folder / "request.md"
    ```
  * Add internal-newline test:

    * File content:

      ```text
      Line one
      Line two
      ```
    * Assert:

      ```python
      ctx.message == "Line one\nLine two"
      ```
  * Add missing-file test:

    * Delete request file.
    * Access `ctx.message`.
    * Assert `WorkflowExecutionError`.

* **Tests: prompt validation**

  * Valid workflows compile:

    ```text
    {ctx.message}
    {ctx.request.text}
    {ctx.request.file}
    {ctx.request.task_file}
    {ctx.request_file}
    {ctx.input.topic}
    {ctx.state.status}
    {ctx.params.mode}
    ```
  * Invalid workflows fail:

    ```text
    {message}
    {ctx}
    {ctx.request}
    {ctx.input}
    {ctx.state}
    {ctx.params}
    {ctx.input.missing}
    {ctx.state.missing}
    {ctx.params.missing}
    {ctx.message.upper()}
    {ctx.__dict__}
    {ctx.request.file.read_text()}
    {ctx.values.foo}
    {ctx.artifacts.foo}
    ```

* **Tests: provider `step(...)` rendering**

  * Workflow:

    ```python
    class MessageStepDemo(Workflow):
        name = "message_step_demo"

        class Input(BaseModel):
            topic: str

        class Params(BaseModel):
            mode: str = "brief"

        class State(BaseModel):
            status: str = "draft"

        summary = step(
            "Message={ctx.message}; Topic={ctx.input.topic}; Mode={ctx.params.mode}; Status={ctx.state.status}",
            writes=(Md("summary"),),
            routes={"done": FINISH},
        )
    ```
  * Run with:

    * Message: `Ship the release safely.`
    * Input: `{"topic": "release"}`
    * Params: `{"mode": "brief"}`
  * Assert provider receives:

    ```text
    Message=Ship the release safely.
    Topic=release
    Mode=brief
    Status=draft
    ```
  * Assert provider does not receive literal `{ctx.message}`.

* **Tests: `llm.step(...)` rendering**

  * Define:

    ```python
    risk = llm.step(
        prompt="Risk for {ctx.message}; topic={ctx.input.topic}; mode={ctx.params.mode}; status={ctx.state.status}",
    )
    ```
  * Assert rendered operation prompt contains actual values.

* **Tests: `classify.step(...)` rendering**

  * Define:

    ```python
    kind = classify.step(
        prompt="Classify {ctx.message} for {ctx.input.topic}",
        choices=("bug", "feature"),
    )
    ```
  * Assert rendered classification prompt contains actual values.

* **Tests: `produce_verify_step(...)` rendering**

  * Use `{ctx.message}`, `{ctx.input.topic}`, `{ctx.params.mode}`, and `{ctx.state.status}` in both producer and verifier prompts.
  * Assert both rendered prompts contain actual values.

* **Tests: child workflow message rendering**

  * Parent:

    ```python
    child = workflow_step(
        ChildWorkflow,
        message="{ctx.message}",
        input={"topic": "alpha"},
        routes={"done": FINISH},
    )
    ```
  * Child writes `ctx.message` and `ctx.input.topic` to an artifact.
  * Assert:

    ```python
    child_ctx.message == parent_message
    child_ctx.input.topic == "alpha"
    ```
  * Assert child run-local `request.md` contains the rendered parent message.
  * Add mixed message test:

    ```python
    message="Parent request: {ctx.message}; topic={ctx.input.topic}"
    ```
  * Assert child message renders both values.

* **Tests: message/input separation**

  * Parent message:

    ```text
    Natural-language request
    ```
  * Child input:

    ```python
    {"topic": "structured-topic"}
    ```
  * Assert inside child:

    ```python
    ctx.message == "Natural-language request"
    ctx.input.topic == "structured-topic"
    ctx.message != ctx.input.topic
    ```

* **Tests: missing typed input**

  * Define workflow with `Input.topic`.
  * Use prompt:

    ```text
    {ctx.input.topic}
    ```
  * Run without typed input through programmatic runner or child workflow harness.
  * Assert runtime `WorkflowExecutionError`:

    ```text
    ctx.input.topic requires workflow input, but no input was provided
    ```

* **Tests: resume behavior**

  * Start a run with:

    ```text
    Original request
    ```
  * Pause or interrupt at a resumable point.
  * Mutate task-level request text if test harness allows.
  * Resume original run.
  * Assert subsequent step sees:

    ```python
    ctx.message == "Original request"
    ```
  * Assert resumed run reads existing run-local `request.md`.

* **Tests: no auto-injection**

  * Workflow prompt:

    ```python
    step("Write a generic summary.", writes=(Md("summary"),))
    ```
  * Run with distinct message:

    ```text
    THIS SHOULD NOT APPEAR UNLESS BOUND
    ```
  * Assert provider prompt does not contain that string.

* **Tests: artifact path rejection**

  * Define:

    ```python
    Md("outputs/{ctx.message}.md")
    ```
  * Assert compile-time or runtime failure with:

    ```text
    ctx.* placeholders are only supported in prompts and workflow-step messages, not artifact paths
    ```
  * Verify existing safe path templates still work:

    * `{workflow_folder}`
    * `{run_folder}`
    * `{item.id}`
    * `{branch.name}` where already allowed.

* **Tests: scalar and complex values**

  * Assert scalar values render:

    * `ctx.state.status: str`
    * `ctx.state.count: int`
    * `ctx.params.enabled: bool`
    * `ctx.input.topic: str`
  * Define complex input:

    ```python
    class Input(BaseModel):
        tags: list[str]
    ```
  * Prompt:

    ```text
    {ctx.input.tags}
    ```
  * Assert runtime failure with non-scalar value error unless explicit JSON serialization is intentionally implemented.

* **Documentation updates**

  * Add a section titled:

    ```text
    Runtime context prompt bindings
    ```
  * Document:

    ```text
    {ctx.message}
    {ctx.request.text}
    {ctx.input.<field>}
    {ctx.state.<field>}
    {ctx.params.<field>}
    ```
  * Explicitly state:

    * Use `{ctx.message}`, not `{message}`.
    * `ctx.message` is natural-language request text.
    * `ctx.input` is typed structured input.
    * `ctx.params` is workflow configuration.
    * `ctx.state` is workflow state.
    * Existing bare input/state/params behavior is retained for compatibility where it already exists, but `ctx.*` is preferred.
  * Update child workflow docs:

    ```python
    workflow_step(
        ChildWorkflow,
        message="{ctx.message}",
        input={"topic": "alpha"},
    )
    ```
  * Update examples that copy `request.md` into an artifact solely to make request text available to prompts.

* **Acceptance criteria**

  * `ctx.message` works in Python/system steps.
  * `{ctx.message}` works in provider prompts.
  * `{ctx.message}` works in operation prompts.
  * `{ctx.input.<field>}` works for declared `Input` fields.
  * `{ctx.state.<field>}` works for declared `State` fields.
  * `{ctx.params.<field>}` works for declared `Params` fields.
  * `{ctx.request.text}` equals `{ctx.message}`.
  * `{ctx.request.file}` and `{ctx.request_file}` render the run-local request path.
  * `{message}` is rejected.
  * `{ctx}` is rejected.
  * Unsafe `ctx.*` paths are rejected.
  * Complex non-scalar field values are rejected unless explicit JSON rendering is implemented.
  * `workflow_step(message="{ctx.message}")` forwards the rendered parent request to the child workflow.
  * `workflow_step(message_from=...)` remains literal file/artifact content behavior.
  * `ctx.input` remains separate from `ctx.message`.
  * Resume uses run-local `request.md`, not mutable task request metadata.
  * `ctx.*` is rejected in artifact path templates.
  * Existing bare `input/state/params` behavior remains compatible where already supported.
  * No provider adapter-specific implementation is required.
  * All existing tests pass.

* **Non-goals**

  * Do not add bare `{message}`.
  * Do not auto-inject messages into prompts.
  * Do not evaluate Python expressions in templates.
  * Do not expose raw `Context` internals.
  * Do not expose `ctx.values`, `ctx.artifacts`, `ctx.session`, or step/item state in this patch.
  * Do not change CLI flags.
  * Do not change run persistence layout.
  * Do not change provider adapters unless rendered prompt plumbing is broken.
