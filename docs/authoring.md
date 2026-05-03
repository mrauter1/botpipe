# Authoring

## Simple Surface

`autoloop` is the active public authoring surface.

Use:

```python
from autoloop import Workflow, Prompt, Route, FINISH
from autoloop import Json, Md, Text, Raw, step, produce_verify_step, workflow_step, python_step
```

Use `from autoloop import ...` in public workflow code and examples.
`autoloop.core` remains the internal and power-user kernel surface for strict runtime code and tests; it is not the default public authoring API.
Legacy aliases are intentionally removed from the public authoring surface; use the canonical workflow, route, prompt, and artifact names consistently.

Greenfield authoring defaults:

- `State` is optional on `autoloop.Workflow`.
- prompt files are optional; inline prompts are first-class.
- `Prompt.inline(...)`, `Prompt.file(...)`, and `Prompt.ref(...)` are the canonical prompt forms.
- `reads` are optional context and do not fail when missing.
- `requires` are hard input preconditions.
- `writes` is the canonical output surface.
- artifact schemas validate files and stay distinct from provider `control_schema`.
- `python_step(...)` carries its handler explicitly on the step declaration.
- `workflow_step(...)` lowers to a dedicated child-workflow runtime step.
- step-local `routes={...}` are the canonical public topology surface.
- there is no `autoloop eject` or workflow source-expansion command.

## Workflow Shapes

Workflows commonly live under repo-root `workflows/`, but the runtime no longer requires one folder shape.

Supported authoring forms:

- single Python file such as `workflows/release_review.py`
- flow-first package such as `workflows/release_review/flow.py` plus optional `specs.py`
- mature package such as `workflows/release_review/flow.py` or `workflow.py` plus optional `workflow.toml`, `prompts/`, `assets/`, docs, and tests

Recommended serious-workflow shape:

```text
workflows/
  release_review/
    flow.py
    specs.py
```

`flow.py` plus `specs.py` is the recommended serious-workflow shape, but it is not required.

Single-file workflow:

```text
workflows/
  release_review.py
```

Compatible mature package:

```text
workflows/
  release_review/
    __init__.py
    flow.py or workflow.py
    specs.py
    workflow.toml
    prompts/
    assets/
```

`specs.py` is ordinary Python, not a runtime convention. Use it to keep `flow.py` readable when the workflow grows. The runtime does not enforce one folder structure beyond resolving the workflow reference you asked it to run.

When a package uses `__init__.py`, it should re-export the main workflow class and any workflow-specific `Params` from the executable module so package-local imports stay straightforward.

## Workflow Params

Top-level CLI runs pass workflow-specific parameters through repeatable `-wf` pairs:

```bash
autoloop run review task-42 \
  --message "Review this implementation" \
  -wf mode strict \
  -wf reviewer security
```

If a workflow supports parameters, expose a `Params` model through one of the supported resolution points. Resolution order is:

1. `Workflow.Params`
2. module-level `Params` in the executable flow module
3. package-exported `Params`
4. package-local `params.py` when the workflow keeps parameters there

The runtime validates and coerces `-wf` values through that model before execution starts. `specs.py` is never scanned specially; if you want it involved, import from it explicitly.

Typed parameter access:

```python
ctx.params.mode
ctx.workflow_params["mode"]
```

`ctx.params` is the typed `Params` model for the workflow. `ctx.workflow_params` remains the compatibility dict surface.

When a workflow declares `Params`, treat `ctx.params` as the default typed bootstrap surface and workflow-authoring surface.

Bootstrap handlers should project already-typed values from `ctx.params` into workflow state and invocation artifacts instead of re-reading and re-normalizing `ctx.workflow_params`.

`ctx.workflow_params` remains the raw mapping surface. Keep using the existing lifecycle helpers such as `open_workflow_sessions(...)` and `write_invocation_contract(...)` explicitly from workflow code rather than hiding bootstrap setup in runtime behavior.

When the same parameter bundle appears in more than one workflow, prefer shared stdlib-owned parameter models under `stdlib/parameters.py` before copying the same field scaffold again. Shared task framing, selected-workflow framing, and portfolio-review bundles belong there; workflow-specific identifier rules, literal pre-normalization, allow-lists, defaults, and order-sensitive output should stay in the local `params.py`.

## Step Control Contracts

Provider-backed simple steps may declare structured control contracts directly on `step(...)` and `produce_verify_step(...)`. The runtime renders those declarations into one shared human-readable Runtime Step Contract before CLI-backed providers run.

```python
from pydantic import BaseModel

from autoloop import FINISH, Md, Prompt, Route, step


class ReviewPayload(BaseModel):
    summary: str


review = step(
    prompt=Prompt.file("prompts/review.md"),
    writes=[Md("review_report", required=True)],
    control_schema=ReviewPayload,
    routes={
        "review_complete": Route.to(
            FINISH,
            summary="Review artifacts and verdict are complete.",
            required_writes=["review_report"],
        )
    },
)
```

Runtime behavior:

- `control_schema` defines the JSON-schema-like contract for `Outcome.payload`
- `available_routes` is derived mechanically from the declared step-local routes plus authored global routes plus any internal runtime-control routes
- step-local `Route.to(...)` metadata carries optional per-route summary, handoff, and selected-route output metadata for legal routes only
- `required_writes` is the normalized selected-route output obligation map derived from explicit `Route(...)` metadata or inferred empty tuples
- route metadata is authored on `Route(...)` when the workflow needs to override inferred summaries or declare route-specific `required_writes`
- author workflows with step-local `routes={...}`; `transitions` is not part of the canonical authoring surface
- `retry_policy` controls provider-attributable retries and defaults to `ProviderRetryPolicy(max_attempts=3)` on provider-backed steps
- the rendered Runtime Step Contract can also include resolved-target route handoff text and retry feedback when the engine supplies them

## Static And Runtime Validation

Static validation stays strict about workflow topology, declared names, route legality, declared worklists, artifact-reference ambiguity, callback existence, and schema shape.

Runtime validation owns worklist contents, generated boards, runtime-created prompt context, item-scoped artifact paths, provider failures, and semantic validation steps that depend on data created during the run.

That split is intentional: the framework should reject typos and invalid static contracts early without forcing authors to pre-create runtime data just to compile or start a run.

Authoring rules:

- keep provider-facing operational guidance in the prompt templates, not in runtime-only metadata
- reserve runtime-injected control data for the shared Runtime Step Contract: readable inputs, required inputs, writable artifacts, available routes, route summaries and route `required_writes`, explicit expected output payload requirements, optional route handoff, and optional retry feedback
- continue using `Outcome.tag` as the route carrier
- use `needs_rework` when the current work-item boundary still holds and `needs_replan` when the boundary changed materially
- do not declare provider control schemas on `python_step(...)`; Python steps mutate `ctx` directly and return `None`, a route tag, `Event(...)`, `RequestInput(...)`, `Goto(...)`, or `Fail(...)`

## Hook Style And Returns

Public hooks use one signature only:

```python
def before(ctx):
    ...


def after(ctx):
    ...


def on_taken(ctx):
    ...
```

Everything hook code needs is available on `ctx`, including `ctx.state`, `ctx.step_state`, `ctx.item_state`, `ctx.step_item_state`, `ctx.artifacts`, `ctx.outcome`, `ctx.event`, `ctx.route`, `ctx.input_response`, `ctx.meta`, and `ctx.history`.

Supported hook returns:

```python
None
"route_tag"
Event(...)
RequestInput(...)
Goto(...)
Fail(...)
```

Hooks do not replace workflow state by returning a `BaseModel`. Mutate state through `ctx` and return only route or direct-control values when the hook should change execution.

## Runtime Controls And Hidden Routes

Use runtime controls when workflow code, not the provider, owns the next move:

```python
from pydantic import BaseModel

from autoloop import AWAIT_INPUT, FINISH, Fail, Goto, Prompt, RequestInput, Route, Workflow, python_step, step


class ApprovalInput(BaseModel):
    approved: bool


def on_hidden_escalation(ctx):
    return RequestInput(
        "Approve publication?",
        reason="Verifier escalated the gate.",
        input_schema=ApprovalInput,
    )


def after_publish(ctx):
    if ctx.input_response is None:
        return Goto("draft", reason="Collect approval first.")
    if not ctx.input_response.approved:
        return Fail("Publication was not approved.")
    return None


class ApprovalWorkflow(Workflow):
    draft = step(
        prompt=Prompt.inline("Draft the release packet."),
        routes={
            "done": Route.to("publish"),
            "human_escalation": Route.to(
                "publish",
                provider_visible=False,
                on_taken=on_hidden_escalation,
            ),
        },
    )

    @python_step(name="publish", routes={"done": FINISH}, after=after_publish)
    def publish(ctx):
        return "done"
```

Key rules:

- `RequestInput(...)` suspends the run with terminal `AWAIT_INPUT`; resumed input is available on `ctx.input_response`
- `Goto(...)` jumps directly to a declared step and does not pretend a route was taken
- `Fail(...)` terminates with `FAIL` and preserves the current state/session snapshot
- plain hook-returned strings always mean route tags, never step targets
- use `Route.to(..., on_taken=...)` for route-local chaining
- use `provider_visible=False` for hidden SOP routes that workflow hooks may select but providers must not see

## Runtime Config And Provider Selection

Workflow code does not construct providers directly. Operators select the built-in runtime backend through typed config and generic CLI flags.

Typed config lives in `autoloop.yaml` or `autoloop.config` and uses the runtime-owned provider schema:

```yaml
provider:
  name: codex
  model: gpt-5.4
  model_effort: medium
runtime:
  max_steps: 100
```

`provider.name` selects the built-in backend. Generic `provider.model` and `provider.model_effort` overrides target that selected provider.

Public CLI overrides stay generic:

```bash
autoloop run review task-42 \
  --provider claude \
  --model claude-opus \
  --model-effort max \
  --message "Review this implementation"
```

If a workflow or template documents operational usage, keep it on this typed surface. Do not document ad-hoc backend construction or out-of-band provider injection.

Concrete runtime adapters live under `runtime/providers/`, but that package is framework-owned implementation detail. Workflow authors should target the typed runtime config surface and the generic CLI flags rather than importing provider adapters or describing non-public factory hooks.

For `produce_verify_step(...)` verifiers and provider-backed `step(...)` prompts, treat the provider-facing completion contract as strict JSON. The runtime now validates verifier and single-LLM outcomes locally, so prompts should ask for one JSON object matching the declared routes and payload contract rather than free-form prose.

## Runtime Observability Defaults

Runtime tracing is enabled by default.

Runtime git tracking is runtime-owned and enabled by default when the repository is clean.

Workflow authors do not declare `GitTracking` or `Tracing`; runtime observability is configured through typed runtime config files and CLI controls.

Runtime-owned observability writes `trace.jsonl`, `git_tracking.jsonl`, `static_step_graph.json`, and runtime-owned `raw/` outputs under the run folder.

Provider raw output is runtime telemetry and runtime-owned evidence for debugging and replay, not a workflow-authored prompt surface.

Git commits are the workspace replay boundary, so operators should start from a clean repository before a git-tracked run or resume.

## Compact Prompt Contract Style

Keep prompt families explicit without repeating the same boilerplate in every file.

Use `prompts/README.md` once per workflow package for the family-wide contract:

- the shared runtime/provider boundary reminder
- reserved-route baseline and any family-wide route summary
- a compact step-to-artifact map
- verifier payload model names
- family-wide publication-boundary reminders that apply to every prompt in the package

Keep each prompt file focused on the current step:

- step role and purpose
- current work-item boundary
- exact artifacts to read, write, or leave untouched
- step-specific evidence requirements
- step-specific route reminders and forbidden actions

Prompt files should not re-explain family-wide notes when the same wording already lives in `prompts/README.md`.

Prompt-style rules:

- keep provider-facing operational guidance in prompt files, not runtime-only metadata
- the runtime injects a compact human-readable step contract with readable inputs, required inputs, writable artifacts, route-specific output requirements, explicit expected output payload requirements, available routes, route summaries, optional route handoff, and optional retry feedback
- provider raw output is runtime telemetry: it is persisted for logs, traces, extension events, debugging, and replay, but it is not rendered into provider prompts
- prefer compact artifact tables when they shorten the prompt materially, such as `Artifact | Read/Write | Purpose | Handling`
- keep route guidance concise and local to the decision the current step must justify
- do not restate machine-readable route metadata verbatim when the runtime already injects it
- do not add workflow-local prompt template engines or competing prompt-renderer abstractions on top of the shared runtime renderer just to remove repeated prose

`prompts/README.md` is a workflow-local documentation seam, not a runtime input. Shared prompt text belongs there before it belongs in runtime behavior.

## Prompt And Artifact Resolution

Relative prompts and bundled assets resolve from the executable workflow container, never from the current working directory.

```python
Prompt.file("prompts/ask.md")
Artifact("{run_folder}/request.md")
Artifact("{workflow_folder}/notes.md")
Artifact("{package_folder}/assets/template.txt")
```

`package_folder` means:

- the parent directory of a single-file workflow
- the containing directory of `flow.py`
- the containing directory of `workflow.py`

Available runtime placeholders include:

- `task_folder`
- `workflow_folder`
- `run_folder`
- `package_folder`
- `workflow_name`
- `state.*`

`package_folder` is read-only workflow-adjacent source content. Mutable artifacts must never be written into the workflow source directory.

## Message Model

New runs are message-first:

- `autoloop run ... --message "..."` starts a new run
- `autoloop answer ... --answer "..."` resumes an awaiting-input run with an explicit answer

`message` and `answer` are distinct concepts. Resume and diagnostics do not accept a replacement message.

## Sessions And Resumability

The runtime persists resumability through an opaque `session_id` plus optional `provider_metadata`. Workflow code should treat session continuity as opaque runtime state and use the `Session` / context APIs rather than depending on persisted payload details.

Every workflow also has an implicit default session slot named `global`. Provider-backed `step(...)` and `produce_verify_step(...)` declarations use that slot automatically when no explicit `session=` is declared.

`Continuity` defines the default reuse policy for a session slot:

```python
worker = Session(continuity=Continuity.work_item("gate"))
```

Supported continuity policies are `Continuity.run()`, `Continuity.task()`, `Continuity.work_item(...)`, `Continuity.fresh()`, and `Continuity.key(...)`.

`ctx.open_session(..., scope=...)` remains supported and is the explicit runtime override surface:

```python
ctx.open_session(self.worker)
ctx.open_session(self.worker, scope="cluster-1")
ctx.open_session(self.worker, "cluster-1")
```

Mental model:

- `Session` is a named provider conversation slot
- `Continuity` is the default reuse policy for that slot
- `scope=` is an explicit runtime binding override, not a replacement for continuity

In other words, `scope= is an explicit runtime binding override` for the session slot chosen by the step or caller.

Implications for authors:

- do not assume provider-specific naming for the continuation handle
- do not read or write session JSON directly from workflow logic
- keep provider-specific behavior inside provider adapters or provider-specific prompts, not workflow contracts
- do not document or depend on any legacy provider-specific continuation alias outside the canonical `session_id` contract

## Artifact Declarations And Contracts

Class-level artifacts remain valid:

```python
report = Artifact("{workflow_folder}/report.md")
```

Step-local artifacts can now be declared inline:

```python
from autoloop import FINISH, Json, Md, Prompt, Route, produce_verify_step


class Summary(BaseModel):
    summary: str
    ready: bool


draft = produce_verify_step(
    producer_prompt=Prompt.file("prompts/draft_producer.md"),
    verifier_prompt=Prompt.file("prompts/draft_verifier.md"),
    writes=[
        Json("summary", Summary, required=True),
        Md("report", required=True),
    ],
    routes={
        "ready": Route.to(
            FINISH,
            required_writes=["summary", "report"],
        ),
    },
)
```

The step exposes those artifacts as attributes, so downstream steps may write `requires=[draft.summary, draft.report]`.

Selected-route output obligations live on the step-local route declarations, for example:

```python
routes = {
    "ready": Route.to(
        FINISH,
        summary="The report and summary are ready.",
        required_writes=["summary", "report"],
    )
}
```

Path rules:

- explicit templates such as `Artifact("{workflow_folder}/report.md")` resolve exactly as written
- class-level relative paths resolve under `workflow_folder`
- step-local relative paths resolve under `{workflow_folder}/{step_name}/`

`writes` and `requires` are different contracts:

- `requires` means the artifact must already exist before the step runs
- `writes` means the step owns a governed writable output handle

Artifact schema and provider output schema are also different:

- `Artifact.schema` validates artifact file content on disk
- `control_schema` validates `Outcome.payload`

Requiredness rules:

- `Md(..., required=True)` or `Json(..., required=True)` makes that declared write required by default on successful completion
- `Route.required_writes` is the selected-route-specific override
- optional writes may be absent
- optional schema-bearing writes that exist still validate

## Typed Routes And Effects

Canonical public topology is step-local:

```python
ask = step("Ask the reviewer.", routes={"done": FINISH})
```

Advanced routes still use Python objects, not a string DSL:

```python
assess = step(
    prompt=Prompt.file("prompts/assess.md"),
    writes=[Md("assessment", required=False)],
    routes={
        "passed": Route.to(
            FINISH,
            summary="Assessment is complete and ready to hand off.",
            required_writes=["assessment"],
        ),
        "needs_rework": Route.to(
            SELF,
            handoff="Repair the findings and preserve the current work-item boundary.",
        ),
    },
)
```

Canonical authoring declares step-local `routes={...}` and terminates with `FINISH`.

Use `Route.to(...)`, `Route.finish(...)`, `Route.await_input(...)`, and `Route.fail(...)` when the target alone is not expressive enough.

`Handoff(...)` adds source-step-to-target-step text that the runtime delivers only to the resolved provider-mediated target step. Dynamic handoff text may also be returned through `Event(tag="needs_rework", handoff="...")`. Handoffs are text-only and the current Runtime Step Contract remains authoritative.

Default provider-control policy is narrow:

- `question` is the only default runtime control route
- the default `question` route is provider-visible only when the engine is not running full-auto
- `blocked` and `failed` are never injected by default
- explicit application routes named `blocked` or `failed` remain legal ordinary routes
- provider transport failures, malformed output, illegal routes, and missing or invalid required artifacts stay runtime-owned failures rather than provider-selected `failed` outcomes

## Worklists And Scoped Steps

`Worklist` and `WorkItem` let workflows scope a step to the current selected item without introducing hidden looping.

```python
from autoloop import Goto, Prompt, RequestInput, Route, SELF, Worklist, produce_verify_step, step


gates = Worklist.from_artifact(
    name="gate",
    artifact=gate_board,
    collection="gates",
    item_id="gate_id",
    title="title",
    status="status",
)

assess = produce_verify_step(
    producer_prompt=Prompt.file("prompts/assess_producer.md"),
    verifier_prompt=Prompt.file("prompts/assess_verifier.md"),
    scope=gates,
)
```

Worklist helpers exposed on `Context`:

- `ctx.worklist("gate")`
- `ctx.worklists.gate`
- `ctx.current_worklist`
- `ctx.selection("gate")`
- `ctx.ensure_selection("gate")`

Declared worklists are lazy. The framework validates the static worklist contract at compile time, but it does not require the backing source artifact or generated board to exist until the run first touches that worklist through a scoped step, prompt placeholder, session continuity, or explicit worklist access.

Worklist helpers mutate selection and status only. They never route automatically.

```python
def complete_and_advance(ctx):
    ctx.current_worklist.set_current_status("completed")
    if not ctx.current_worklist.advance():
        return Goto("finalize")
    return None


review = step(
    prompt=Prompt.inline("Review the selected gate."),
    scope=gates,
    routes={
        "accepted": Route.to(SELF, on_taken=complete_and_advance),
        "needs_input": Route.to(
            SELF,
            on_taken=lambda ctx: ctx.current_worklist.advance_or(
                RequestInput("Choose the next gate.", reason="Selection exhausted.")
            ),
        ),
    },
)
```

Useful helper methods:

- `ctx.current_worklist.refresh()`
- `ctx.current_worklist.set_current_status("completed")`
- `ctx.current_worklist.reset_current_status()`
- `ctx.current_worklist.advance()`
- `ctx.current_worklist.advance_or(Goto("finalize"))`
- `ctx.current_worklist.validate()`
- `ctx.current_worklist.validation_error()`

The engine does not silently loop a whole worklist. Progression stays explicit in `on_taken` hooks and direct-control returns.

When a common worklist transition is deterministic, use typed effects instead of repeating imperative hook glue:

```python
from autoloop import Effects, Route


review = step(
    prompt=Prompt.inline("Review the selected gate."),
    scope=gates,
    routes={
        "accepted": Route.complete_current(SELF),
        "done": Route.advance("finalize", exhausted="finalize"),
    },
)


def after_review(ctx):
    return Effects.complete_and_advance(exhausted="finalize")
```

`Effects.then(...)`, `Effects.advance(...)`, `Effects.complete_and_advance(...)`, and `Effects.refresh(...)` reuse the normal worklist runtime APIs, so status changes, refreshes, advancement, runtime events, and checkpointing all stay on the same execution path.

Workflow-level artifacts and step-produced artifacts are different roles:

- workflow-level artifacts are inputs or managed external artifacts
- step `writes` are produced artifacts
- do not declare the same artifact in both roles unless and until an explicit managed-artifact role is introduced

## Typed Child Workflow Contracts

Child composition still centers on `ctx.invoke_workflow(...)`, and workflows may now declare typed `Input` and `Output` models:

```python
result = ctx.invoke_workflow(
    ChildWorkflow,
    message="Review this package",
    input=ChildWorkflow.Input(topic="release", urgency=2),
)
```

If the child workflow declares `Output` and `build_output(...)`, the returned `ChildWorkflowResult.output` carries the validated typed output. The low-level compatibility fields remain available on `ChildWorkflowResult`, including run paths, metadata, and artifact maps.

## Optional Lifecycle Helpers

`stdlib/lifecycle.py` provides a small opt-in helper seam for deterministic authoring tasks such as opening declared sessions and writing workflow-local JSON artifacts like invocation contracts and publication receipts.

```python
from autoloop.stdlib import (
    open_workflow_sessions,
    write_invocation_contract,
    write_publication_receipt,
)
```

Use it only as authoring support inside explicit workflow hooks such as `before(ctx)`, `after(ctx)`, or `Route.to(..., on_taken=...)`.

- these helpers do not create hidden runtime sequencing or automatic `python_step` execution
- they only operate on the workflow-owned `ctx` surface and `ctx.workflow_folder`
- they do not broaden the shared runtime step contract or move provider-facing prompt rendering into authoring helpers
- publication-artifact validation and any workflow-specific receipt semantics still belong in workflow code

## Typed JSON Artifact Contracts

When a workflow owns a durable JSON summary or manifest, keep its artifact contract explicit in the workflow package instead of starting publish handlers from raw dictionaries.

```python
from autoloop.stdlib import JsonArtifactSpec


PACKAGE_SUMMARY_ARTIFACT = JsonArtifactSpec(
    "strategy_summary.json",
    StrategySummaryPayload,
)
```

Typed JSON artifact boundary:

- declare workflow-local `JsonArtifactSpec(...)` surfaces in `contracts.py` when the JSON artifact belongs to one workflow family
- treat that typed read as the default publish-handler entrypoint for durable package summaries and validated output manifests
- prefer `artifact_spec.read(path)` or `read_model_file(path, Model)` for publish-step reads so the workflow starts from a validated model, not `summary.get(...)`
- use `artifact_spec.validate(path)` or `validate_model_file(path, Model)` for focused proof or readable failure reports when a workflow-local JSON contract needs direct validation
- use this seam for durable package summaries and validated output manifests; raw proposal or draft inputs may stay workflow-local until a validation step writes the authoritative artifact
- split durable artifact models from verifier payload models when the on-disk JSON omits verifier-only prose fields such as `summary`
- keep typed artifact models focused on stable shape and mechanical presence checks; workflow-local allow-lists, publication-boundary policy, cross-artifact drift checks, and receipt shaping should stay in workflow code when they preserve clearer local error semantics
- keep artifact filenames and top-level JSON keys stable; the typed seam should clarify authoring, not rename surfaces
- keep cross-artifact alignment, state-drift checks, hidden-execution policy, and receipt shaping in workflow code
- do not force every intermediate JSON draft through `JsonArtifactSpec(...)` when the workflow has not validated it yet
- do not turn this into a generic publication registry or runtime-owned publication framework

## Optional Validation Helpers

`stdlib/validation.py` provides a small opt-in helper seam for generic workflow-local JSON, string, list, mapping, non-negative-int, and positive-int validation.

```python
from autoloop.stdlib import (
    extract_workflow_names_from_capability_snapshot,
    extract_workflow_names_from_portfolio_health,
    read_required_text,
    normalize_optional_string,
    normalize_unique_strings,
    read_json_object,
    require_existing_artifact_paths,
    require_mapping,
    require_mapping_list,
    require_non_negative_int,
    require_non_empty_string,
    require_positive_int,
    require_true_flag,
    require_string_list,
    validate_authoritative_artifact_subset,
    validate_no_hidden_execution_signal,
    validate_publication_boundary,
)
```

Validation helper boundary:

- generic validation belongs in stdlib rather than copied workflow-local helper tails
- use these helpers for shared JSON-object reads, non-empty string checks, string-list normalization, mapping checks, duplicate guards, non-negative-int validation, and positive-int validation
- use `require_existing_artifact_paths(...)` and `read_required_text(...)` for mechanical publish-step artifact existence and non-empty text checks
- use `validate_publication_boundary(...)`, `validate_authoritative_artifact_subset(...)`, `require_true_flag(...)`, and `validate_no_hidden_execution_signal(...)` for reusable publish-handler mechanics
- use `extract_workflow_names_from_capability_snapshot(...)` and `extract_workflow_names_from_portfolio_health(...)` when governance-facing workflows need the shared workflow-name snapshot surface instead of copying local readers
- treat those publication-validation and snapshot-reader helpers as one shared governance/diagnostic helper family in `stdlib/validation.py`, not as a publication framework or runtime policy seam
- use the selected-workflow snapshot validators in the same module when multiple workflows need the same capability, authoring-surface, decomposition-surface, or cross-artifact selected-workflow-name checks
  - `validate_selected_workflow_capability_snapshot(...)` validates the compiled selected-workflow snapshot contract
  - `validate_selected_workflow_authoring_surface_snapshot(...)` validates the editable selected-workflow surface contract
  - `validate_selected_workflow_decomposition_surface_snapshot(...)` validates the decomposition snapshot contract
  - `validate_selected_workflow_artifact_alignment(...)` handles top-level `selected_workflow_name` alignment across artifacts
  - `validate_selected_workflow_capability_and_authoring_snapshots(...)` validates the paired capability and authoring surfaces without repeating local cross-check code
- keep workflow-specific publication assertions, domain allow-lists, and artifact-family invariants in workflow code
- keep package section requirements, scoped-task extraction, unknown-reference checks, state-drift assertions, and receipt shaping in workflow code
- the helpers only validate explicit workflow-local inputs and artifacts; they do not add runtime-owned routing, publication policy, or hidden execution

For repairable semantic validation, prefer `validation_step(...)` plus `ValidationResult` over one-off `try/except` plumbing inside ad hoc `python_step(...)` handlers.

```python
from autoloop import FINISH, Md, ValidationResult, validation_step


feedback = Md("manifest_feedback")


@validation_step(
    name="validate_manifest",
    feedback=feedback,
    success=FINISH,
    repair="repair",
)
def validate_manifest(ctx) -> ValidationResult:
    if ctx.artifacts.manifest.path.exists():
        return ValidationResult.valid()
    return ValidationResult.invalid("Manifest is missing.", details=("Create manifest.json.",))
```

The helper lowers to a normal Python step, writes a deterministic feedback artifact on repairable failure, emits runtime validation events, and keeps `success`, `repair`, and optional `failed` routing explicit in workflow code.

For workflow `Params` models, reuse the shared Pydantic validator factories instead of copying the same `field_validator(...)` bodies into every `params.py`.

```python
from autoloop.stdlib import (
    deduped_string_list_fields,
    optional_text_fields,
    positive_int_fields,
    required_text_fields,
)


class Params(BaseModel):
    task_title: str
    selected_workflow: str
    sponsor_role: str | None = None
    constraints: list[str] = Field(default_factory=list)
    max_runs: int = 25

    _required_text = required_text_fields(
        "task_title",
        "selected_workflow",
        error_message="value must be non-empty",
    )
    _optional_text = optional_text_fields("sponsor_role")
    _repeatable_strings = deduped_string_list_fields("constraints")
    _positive_int = positive_int_fields("max_runs", error_message="max_runs must be a positive integer")
```

Parameter-model helper boundary:

- generic `params.py` mechanics belong in stdlib rather than repeated local `field_validator(...)` loops
- keep field lists explicit in the `Params` model so required, optional, repeatable, and bounded fields stay easy to read
- keep workflow-specific identifier rules, literal pre-normalization, and order-sensitive output local when the shared seam would hide intent
- these helpers do not change runtime-owned parameter coercion; `runtime/loader.py` still owns workflow-parameter validation and error surfacing

## Optional Portfolio Snapshot Helpers

`autoloop_optimizer.portfolio` provides a small opt-in helper seam for portfolio-routing workflows that need an inspectable snapshot of the current workflow library.

```python
from autoloop_optimizer import (
    write_workflow_portfolio_health_snapshot,
    write_workflow_portfolio_snapshot,
)

write_workflow_portfolio_snapshot(ctx)
write_workflow_portfolio_health_snapshot(ctx, statuses=["awaiting_input", "failed"], max_runs_per_workflow=5)
```

Portfolio snapshot boundary:

- the helper writes `workflow_portfolio_snapshot.json` under `ctx.workflow_folder` by default
- it uses the shared workflow catalog seam to capture manifest metadata plus inferred source paths such as `flow.py`, `workflow.py`, top-level single-file workflows, optional `specs.py`, prompts, assets, docs, and tests when present
- it does not add new `workflow.toml` fields and preserves the metadata-only manifest doctrine
- it does not auto-rank, auto-select, auto-adapt, or auto-run workflows
- it does not import autoloop.runtime-owned routing behavior into workflow packages; portfolio-routing workflows still own ranking, selection, adaptation, create-new policy, and prompt semantics

Portfolio health snapshot boundary:

- `write_workflow_portfolio_health_snapshot` writes `workflow_portfolio_health_snapshot.json` under `ctx.workflow_folder` by default
- it reuses the shared workflow resolution and read-only run discovery seams to publish grouped per-workflow run counts, status counts, and recent-run excerpts
- it supports deterministic status filtering and `max_runs_per_workflow` bounds
- it does not mutate `.autoloop` run state or workflow packages
- it keeps the health surface lightweight: identifying workflow metadata, normalized recent-run excerpts, and summary counts rather than full event logs or runtime-owned lifecycle scoring
- it does not add CLI flags, new `workflow.toml` fields, runtime-owned governance scoring, automatic recommendations, or hidden downstream execution
- workflow code and prompt templates still own governance framing, lifecycle interpretation, recommendation policy, publication gating, and any downstream follow-through
- it does not auto-rank workflows, auto-select actions, auto-cluster failure modes, or impose runtime-owned portfolio policy

## Optional Company Operation Snapshot Helpers

`autoloop_optimizer.company` provides a narrow authoring-only seam for workflows that need one bounded snapshot of repo-local company operation history.

```python
from autoloop_optimizer import write_company_operation_snapshot

write_company_operation_snapshot(
    ctx,
    task_ids=("recursive-framework-evolution-20260423t173132-c12",),
    workflows=("workflow_portfolio_to_operating_system", "workflow_idea_to_workflow_package"),
    statuses=("success", "awaiting_input"),
    max_tasks=10,
    max_runs_per_workflow=5,
    max_messages_per_task=3,
)
```

Company operation snapshot boundary:

- `write_company_operation_snapshot` writes `company_operation_snapshot.json` under `ctx.workflow_folder` by default
- it captures repo-local `.autoloop` task history plus read-only workflow telemetry; it is not an external business-system integration seam
- it publishes bounded task summaries, recent message excerpts, per-task workflow telemetry, and authoritative source paths
- it supports deterministic `task_ids`, workflow, and status filtering plus `max_tasks`, `max_runs_per_workflow`, and `max_messages_per_task` bounds
- it writes only workflow-local JSON artifacts under `ctx.workflow_folder`
- it does not mutate `.autoloop` task or run state, workflow packages, or external business systems
- it does not add CLI flags, runtime-owned company scoring, automatic prioritization, or hidden downstream execution
- it does not widen the runtime-injected control contract beyond readable inputs, required inputs, writable artifacts, `available_routes`, step-local route metadata, `required_writes`, and an explicit `expected_output_schema` when present
- workflow code and prompt templates still own company framing, recursive-improvement analysis, prioritization policy, publication gating, and next-cycle recommendations
- it does not auto-rank tasks, auto-select improvements, auto-run downstream workflows, or imply external CRM, incident, or ticketing integration

## Optional Selected-Workflow Snapshot Helper Family

The selected-workflow snapshot helpers form one converged authoring seam across:

- `autoloop_optimizer.adaptation`
- `autoloop_optimizer.refinement`
- `autoloop_optimizer.decomposition`

Family boundary:

- the private `autoloop_optimizer._selected_workflow.py` seam owns canonical selected-workflow resolution, `selected_workflow_name` capture, and shared envelope writing so later selected-workflow consumers can shorten capture steps without widening the public stdlib or root `workflow` surface
- `core/workflow_capabilities.py` owns the authoritative payload builders for the compiled capability, editable authoring-surface, and decomposition-surface views
- the optimizer helper modules stay thin artifact writers over those builders and keep the emitted artifacts explicit under `ctx.workflow_folder`
- `stdlib/validation.py` owns the generic snapshot identity and alignment checks, including capability, authoring-surface, decomposition-surface, and cross-artifact selected-workflow-name validation
- adjacent selected-workflow helpers such as `autoloop_optimizer.diagnostics.py` and `autoloop_optimizer.optimization.py` may reuse that private capture seam while keeping their workflow-local publication artifacts and policy separate from this public snapshot-helper family
- workflows still own domain-specific publication policy, evidence policy, state-drift handling, and receipt shaping
- the family intentionally keeps `selected_workflow_capability.json`, `selected_workflow_authoring_surface.json`, and `selected_workflow_decomposition_surface.json` as three distinct artifact contracts instead of collapsing compiled and editable surfaces into one payload
- the family does not add CLI flags, widen the root `workflow` authoring surface, or introduce runtime-owned adaptation, refinement, or decomposition behavior

## Optional Selected-Workflow Adaptation Helpers

`autoloop_optimizer.adaptation` provides a small authoring seam for workflows that need to inspect one already-selected workflow and publish a validated parameter artifact for that choice.

```python
from autoloop_optimizer import (
    write_selected_workflow_capability_snapshot,
    write_validated_workflow_parameters,
)

write_selected_workflow_capability_snapshot(ctx, "release_candidate_to_go_no_go")
write_validated_workflow_parameters(
    ctx,
    "release_candidate_to_go_no_go",
    {"mode": "strict", "reviewers": ["ops", "qa"]},
)
```

Adaptation helper boundary:

- the helpers write only workflow-local JSON artifacts under `ctx.workflow_folder`
- they reuse the existing workflow discovery, resolution, and parameter coercion seams instead of re-implementing schema logic
- `write_selected_workflow_capability_snapshot(...)` writes the authoritative compiled selected-workflow payload built in `core/workflow_capabilities.py`, so adaptation flows share the same capability surface used by later refinement, decomposition, and validation helpers
- they accept the same workflow references the shared loader resolves, including canonical names, aliases, and main workflow classes
- they are authoring-only support for explicit workflow code; they do not add CLI syntax, manifest fields, runtime-owned adaptation, or automatic downstream execution
- they do not broaden the shared runtime step contract or move provider-facing prompt rendering into authoring helpers
- portfolio-routing workflows still own ranking, selection, adaptation, create-new policy, and prompt semantics in workflow code and prompt templates
- the helper does not import autoloop.runtime-owned routing behavior into workflow packages; it only writes a workflow-local artifact

## Optional Refinement Surface Helpers

`autoloop_optimizer.refinement` provides a narrow authoring-only seam for workflows that need a workflow-local snapshot of one selected workflow's editable authoring surface.

```python
from autoloop_optimizer import write_selected_workflow_authoring_surface

write_selected_workflow_authoring_surface(ctx, "release_candidate_to_go_no_go")
```

Refinement helper boundary:

- the helper writes only workflow-local JSON artifacts under `ctx.workflow_folder`
- it reuses the shared workflow resolution and catalog seams instead of ad hoc repo scraping or `workflow.toml` expansion
- it writes the authoritative selected-workflow authoring-surface payload built in `core/workflow_capabilities.py`, so later helpers and workflows consume one canonical editable-surface shape
- it keeps the compiled selected-workflow contract separate from the editable selected-workflow surface; workflows that need both should call `write_selected_workflow_capability_snapshot(...)` and `write_selected_workflow_authoring_surface(...)` explicitly
- it captures the selected workflow's primary source file (`flow.py`, `workflow.py`, or a single-file workflow), optional `__init__.py`, optional `workflow.toml`, optional `specs.py`, optional support files such as `params.py` and `contracts.py`, prompt files, asset files, linked workflow doc paths, and inferred test paths when present
- it writes the canonical result to `selected_workflow_authoring_surface.json` by default
- it does not mutate, auto-run, auto-adapt, auto-refine, or auto-promote the selected workflow
- it does not add CLI flags, new `workflow.toml` fields, or runtime-owned refinement automation
- it does not widen the runtime-injected control contract beyond readable inputs, required inputs, writable artifacts, `available_routes`, step-local route metadata, `required_writes`, and an explicit `expected_output_schema` when present
- prompt templates and workflow code still own refinement policy, baseline/candidate strategy, file copying, verification evidence, and promotion/rollback decisions

## Optional Decomposition Surface Helpers

`autoloop_optimizer.decomposition` provides a narrow authoring-only seam for workflows that need one read-only artifact combining a selected workflow's identity, editable authoring surface, and compiled step/route topology.

```python
from autoloop_optimizer import write_selected_workflow_decomposition_surface

write_selected_workflow_decomposition_surface(ctx, "release_candidate_to_go_no_go")
```

Decomposition helper boundary:

- the helper writes only workflow-local JSON artifacts under `ctx.workflow_folder`
- it is read-only: it snapshots existing workflow/compiler data and does not mutate selected workflow files
- it reuses the shared workflow resolution, catalog, and compiler seams instead of ad hoc repo scraping or `workflow.toml` expansion
- it writes the authoritative selected-workflow decomposition payload built in `core/workflow_capabilities.py`, so authoring-surface and compiled-surface fields stay synchronized across decomposition consumers
- it combines selected workflow identity, editable authoring surface paths, repo-root-relative path metadata, and compiled step/route topology in one artifact
- it captures the selected workflow's primary source file (`flow.py`, `workflow.py`, or a single-file workflow), optional `__init__.py`, optional `workflow.toml`, optional `specs.py`, optional support files such as `params.py` and `contracts.py`, prompt files, asset files, linked workflow doc paths, and inferred test paths when present
- compiled step summaries include session names, readable/required/writable/log artifacts, available routes, route summaries, route `required_writes`, local route targets, and package-relative plus repo-relative prompt paths
- it writes the canonical result to `selected_workflow_decomposition_surface.json` by default
- it does not mutate, auto-decompose, auto-run, auto-adapt, auto-refine, or auto-promote the selected workflow
- it does not add CLI flags, new `workflow.toml` fields, runtime-owned decomposition automation, or hidden downstream routing
- it does not widen the runtime-injected control contract beyond readable inputs, required inputs, writable artifacts, `available_routes`, step-local route metadata, `required_writes`, and an explicit `expected_output_schema` when present
- workflow code and prompt templates still own decomposition policy, baseline/candidate strategy, building-block extraction boundaries, verification evidence, and promotion/rollback decisions

## Optional Candidate-Surface Publication Helpers

`autoloop_optimizer.candidate_surfaces` provides a narrow authoring-only seam for workflows that need the repeated mechanical parts of candidate-only publication for one selected workflow surface.

```python
from autoloop_optimizer import (
    derive_candidate_surface_manifest,
    materialize_baseline_surface,
    normalize_candidate_surface_overlay_result,
    normalize_candidate_surface_boundary,
    validate_baseline_surface_manifest,
    validate_authoritative_surface_sources_unchanged,
    validate_candidate_surface_manifest,
    validate_candidate_surface_overlay,
)
```

Candidate-surface helper boundary:

- the helpers own only the mechanical baseline/candidate publication operations: repo-relative boundary normalization, baseline surface materialization, candidate-manifest diff derivation, baseline/candidate manifest validation, authoritative-source drift rejection, isolated overlay validation, and overlay-result normalization
- they reuse the shared selected-workflow surface artifacts and repo-relative path hardening instead of ad hoc workflow-local copy, digest, and traversal checks
- manifest validators cover shared mechanics such as `repo_root` and `surface_kind` alignment, boundary-field comparison, `relative_paths` versus `files` consistency, copied-surface digest checks, and caller-supplied added-path allow-lists
- callers still own workflow-specific boundary policy, optional boundary-field wiring, domain-specific error wording, and any post-validation receipt semantics
- they write only workflow-local surface folders and manifest metadata under `ctx.workflow_folder`
- overlay validation still runs against an isolated repo copy with the same runnable-root fallback used by the workflow-local publication path
- overlay-result normalization only validates the mechanical compile/test receipt shape, including whether the caller expects one compiled workflow or many
- they do not own refinement-specific evaluation alignment, decomposition-specific evidence capture, building-block extraction policy, or publication receipt shaping
- they do not mutate, auto-promote, auto-decompose, auto-refine, or auto-run the selected workflow
- they do not add CLI flags, new `workflow.toml` fields, runtime-owned publication automation, or hidden downstream routing
- they do not broaden the shared runtime step contract or move provider-facing prompt rendering into authoring helpers
- workflow code and prompt templates still own domain-specific publication policy, evidence requirements, allowed-path rules, and promotion or rollback decisions

## Optional Diagnostic Snapshot Helpers

`autoloop_optimizer.diagnostics` provides a narrow authoring-only seam for workflows that need a workflow-local snapshot of one selected workflow's historical run evidence.

```python
from autoloop_optimizer import write_selected_workflow_run_history_snapshot

write_selected_workflow_run_history_snapshot(
    ctx,
    "release_candidate_to_go_no_go",
    statuses=("failed", "awaiting_input"),
    max_runs=25,
)
```

Diagnostic helper boundary:

- the helper writes only workflow-local JSON artifacts under `ctx.workflow_folder`
- it reuses the shared workflow resolution and read-only run discovery seams instead of ad hoc `.autoloop` scraping
- it captures normalized run metadata, request text, parsed `events.jsonl` entries, parsed `children.jsonl` entries, parsed `parent.json` metadata when present, and authoritative source paths
- it supports deterministic status filtering and `max_runs` bounds while keeping the selected history set explicit in `selected_workflow_run_history.json`
- it does not mutate `.autoloop` run state or selected workflow files
- it does not add CLI flags, new `workflow.toml` fields, runtime-owned diagnostics automation, or hidden downstream routing
- it does not auto-cluster failure modes, auto-rank severity, or impose runtime-owned failure-mode policy
- it does not widen the runtime-injected control contract beyond readable inputs, required inputs, writable artifacts, `available_routes`, step-local route metadata, `required_writes`, and an explicit `expected_output_schema` when present
- workflow code and prompt templates still own diagnostic framing, failure-mode clustering, severity ranking, publication gating, and next-action recommendations

## Optional Evaluation Manifest Helpers

`autoloop_optimizer.evaluation` provides a narrow authoring-only seam for workflows that need to validate and canonicalize one workflow-local evaluation case manifest against one selected workflow.

```python
from autoloop_optimizer import write_validated_eval_case_manifest

write_validated_eval_case_manifest(
    ctx,
    "release_candidate_to_go_no_go",
    {
        "cases": [
            {
                "case_id": "baseline_release_readiness",
                "case_kind": "benchmark",
                "prompt": "Assess a routine release candidate with complete evidence.",
                "workflow_parameters": {"mode": "strict"},
                "expected_artifacts": ["assessment_note"],
            }
        ]
    },
)
```

Evaluation helper boundary:

- the helper writes only workflow-local JSON artifacts under `ctx.workflow_folder`
- it refreshes `selected_workflow_capability.json` through `write_selected_workflow_capability_snapshot(...)` instead of duplicating selected-workflow inspection logic
- it validates per-case workflow parameters through the shared loader coercion path instead of re-implementing parameter schema logic
- it validates unique case ids, legal case kinds (`benchmark`, `edge`, `adversarial`), non-empty case prompts, and non-empty expected artifacts
- it validates expected artifacts against the selected workflow's compiled artifact surface derived from the selected-workflow capability snapshot
- it writes the canonical result to `validated_eval_case_manifest.json` by default
- it does not add CLI flags, new `workflow.toml` fields, runtime-owned evaluation execution, or hidden downstream routing
- it does not widen the runtime-injected control contract beyond readable inputs, required inputs, writable artifacts, `available_routes`, step-local route metadata, `required_writes`, and an explicit `expected_output_schema` when present
- workflows still own evaluation policy, category coverage requirements, prompt semantics, publication gating, and any downstream execution behavior in workflow code and prompt templates

## Optional Optimization Helpers

`autoloop_optimizer.optimization` provides deterministic authoring-only helpers for workflows that need to ingest runtime observability and publish candidate-only optimization evidence.

```python
from autoloop_optimizer import (
    build_step_trace_metrics,
    list_selected_workflow_runs,
    normalize_trace_corpus,
    rank_optimization_targets,
    validate_selected_workflow_source_unchanged,
    write_optimization_refinement_evidence,
    write_selected_workflow_source_manifest,
)
```

Optimization helper boundary:

- the helpers write only workflow-local artifacts under `ctx.workflow_folder`
- they reuse shared selected-workflow resolution and read-only run discovery seams instead of adding runtime-owned optimization behavior
- `run_refs` use `<task_id>/<run_id>` identity and remain distinct from run-level status filters
- `run_statuses` filter run-level terminal state, while `route_tags` filter step-level evidence inside eligible runs
- they capture deterministic evidence such as trace normalization, route counts, token counts, static centrality, source manifests, and refinement-evidence envelopes
- they support the bundled `workflow_run_traces_to_optimization_candidates` workflow without mutating the selected workflow or widening `workflow.toml`
- they do not auto-run target workflows, auto-refine, auto-materialize prompts, auto-promote changes, or execute ablations
- verifier/rubric optimization remains one merged acceptance-function pass owned by workflow code and prompt templates, not by stdlib helper policy
- workflow code and prompt templates still own optimization policy, candidate ranking explanations, adversarial-case handling, and publication receipts

## Optional Workflow Capability Snapshot Helpers

`autoloop_optimizer.portfolio` also provides an opt-in helper for portfolio workflows that need richer importing inspection of workflow parameters and compiled step contracts while keeping the lightweight catalog seam unchanged.

```python
from autoloop_optimizer import write_workflow_capability_snapshot

write_workflow_capability_snapshot(ctx)
```

Capability snapshot boundary:

- the helper writes `workflow_capability_snapshot.json` under `ctx.workflow_folder` by default
- it uses the separate capability-inspection seam to capture catalog metadata plus normalized workflow parameters and compiled step summaries
- compiled step summaries include the declared artifact surface, available routes, route summaries, route `required_writes`, prompt paths, and whether a typed output schema exists
- it does not add new `workflow.toml` fields and does not change the lightweight non-importing catalog discovery contract
- it reuses only the existing narrow runtime-injected control metadata: readable inputs, required inputs, writable artifacts, `available_routes`, step-local route metadata, `required_writes`, and an explicit `expected_output_schema` when present
- it does not auto-rank, auto-select, auto-adapt, or auto-run workflows
- portfolio workflows still own comparison policy, fit-gap reasoning, adaptation policy, and downstream routing in workflow code and prompt templates

## Workflow Composition

Runtime-backed contexts can invoke child workflows by package name or by a workflow class object that is already in scope:

```python
result = ctx.invoke_workflow(
    "child_workflow",
    message="Do the child task",
    parameters={"mode": "strict"},
)
```

Child workflows run as normal workflow packages with their own run ids and run-local artifacts. They are reusable building blocks, not a special execution mode.

For optional authoring-level composition helpers, `stdlib/composition.py` keeps the same runtime semantics while making artifact adoption explicit in workflow code:

```python
from autoloop.stdlib import (
    adopt_child_artifacts,
    require_child_workflow_result,
    run_child_workflow,
)

child = run_child_workflow(
    ctx,
    "child_workflow",
    message="Do the child task",
    parameters={"mode": "strict"},
)
require_child_workflow_result(
    child,
    status="success",
    last_event="evidence_pack_published",
    required_artifacts=("evidence_pack",),
)
adopted = adopt_child_artifacts(
    ctx,
    child,
    mapping={"evidence_pack": "adopted/evidence_pack.md"},
)
```

Composition helper boundary:

- `run_child_workflow(...)` is a thin authoring wrapper over `ctx.invoke_workflow(...)`
- `require_child_workflow_result(...)` validates the expected child status, terminal route, and required artifacts before parent-local adoption
- `adopt_child_artifacts(...)` copies explicitly named child artifacts into `ctx.workflow_folder`
- these helpers do not create hidden runtime sequencing, automatic `python_step` execution, or new child-run metadata
- they do not broaden the shared runtime step contract or move provider-facing prompt rendering into authoring helpers
- parent workflows still own explicit `question` and `blocked` routing for child runs; the validation helper does not propagate or translate those routes automatically
- parent workflows still own which child artifacts are adopted, where they land, and whether overwriting those parent-local files is acceptable

## Recursive And Workflow-Reference Guidance

If a workflow, template, or recursive harness emits Autoloop instructions, keep them workflow-reference-aware and repo-layout-accurate:

- `autoloop run <workflow> <task-id> --root ... --message ...`
- `autoloop resume <workflow> <task-id> --root ...`
- `autoloop answer <workflow> <task-id> --root ... --answer ...`
- explicit file or module refs are allowed when the operator needs them, but recursive wrappers should keep their stable name-first contract unless they have a reason to pin an origin directly
- refer readers to `docs/architecture.md`, `docs/authoring.md`, `core/`, `runtime/`, `extensions/`, `stdlib/`, `workflows/`, and `.autoloop_recursive/`
