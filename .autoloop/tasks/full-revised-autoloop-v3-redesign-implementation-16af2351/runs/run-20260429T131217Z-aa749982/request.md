## Full revised Autoloop v3 redesign / implementation specification

* **Product framing**

  * Autoloop is an **SOP runtime for long-running agentic harnesses**, not a generic LLM-function workflow library.
  * The harness, such as Codex CLI or Claude Code, executes a governed stage.
  * Autoloop owns the multi-stage control plane:

    * step boundaries;
    * routes;
    * artifacts;
    * sessions;
    * retries;
    * verifier/review gates;
    * checkpointing;
    * resume;
    * topology inspection;
    * audit trail.
  * SDK-first LLM calls are not the architectural center for this version.
  * The runtime should remain a strict compiled FSM.
  * The authoring surface should become smaller, more natural, and easier for LLMs to write.

* **Current-codebase premise**

  * The current v3 skeleton already has useful foundations: compiled immutable workflow metadata, explicit routes, artifacts, sessions, provider contracts, checkpoints, and runtime tracing. The redesign should simplify authoring first, not discard the runtime core. 
  * The current public surface is too broad and overlapping: `Workflow`, `StrictWorkflow`, `Route`, `RouteInfo`, `chain`, `step`, `review_step`, `system_step`, `workflow_step`, `out`, `outputs`, `reads`, `requires`, and internal `produces` all coexist. The redesign should collapse this into one canonical public model. 

---

## Core design principle

* **Autoloop should enforce only execution invariants.**

  * Enforce:

    * step names are unique;
    * entry step resolves;
    * route targets resolve;
    * provider-produced route tags are legal;
    * `requires` artifacts exist before execution;
    * selected-route required writes validate;
    * prompt references resolve when available;
    * replay fingerprints do not silently mismatch;
    * resume does not silently use a different topology.
  * Do **not** enforce:

    * verifier/reviewer independence;
    * “no deterministic artifact rewriting”;
    * route summaries everywhere;
    * all writes must exist;
    * all agentic steps must support `question` / `blocked`;
    * all `do_review_step` routes must be `accepted` / `needs_rework`;
    * session reset policy;
    * git tracking policy;
    * prompt style preference;
    * whether state mutation is done in hooks or explicit Python steps.

* **Author policy should be expressed in Python hooks/functions, not framework DSLs.**

  * Avoid adding a large public route-effect DSL.
  * Use functions/hooks for route side effects, state mutation, artifact healing, session reset, and other workflow-specific policy.

---

## Public API target

* **Canonical public API exports**

```python
Workflow

step
do_review_step
python_step
workflow_step

llm
classify

Prompt
Md
Json
Text
Raw

Route
Session
Continuity
StateVar
Param

FINISH
PAUSE
FAIL
SELF
```

* **Deprecated compatibility aliases**

  * Keep temporarily:

    * `SUCCESS = FINISH`
    * `review_step = do_review_step`
    * `system_step = python_step`
    * `out` / `outputs` accepted as deprecated aliases for `writes`
  * Remove from examples and new docs:

    * `StrictWorkflow`
    * `RouteInfo`
    * `chain`
    * global `flow`
    * global `transitions`
    * public-first `reads`
    * public `produces`

---

## Terminal constants and route tags

* **Rename terminal `SUCCESS` to `FINISH`.**

  * Public terminals:

```python
FINISH = "FINISH"
PAUSE = "PAUSE"
FAIL = "FAIL"
SELF = "SELF"
```

* **Keep lowercase `"done"` as the default route tag for plain `step(...)`.**

  * Example compiled defaults:

```text
research.done -> draft
draft.done -> FINISH
```

* **Meaning distinction**

  * `"done"` is a **step route tag**.
  * `FINISH` is a **workflow terminal**.
  * `FINISH` means controlled workflow termination, not positive business success.
  * These are valid:

```python
routes={
    "ready_to_publish": FINISH,
    "rejected": FINISH,
    "duplicate": FINISH,
    "not_applicable": FINISH,
}
```

* **Run results should preserve both**

  * `terminal`: `FINISH`, `PAUSE`, or `FAIL`
  * `last_route`: for example `"rejected"`

---

## Workflow topology model

* **Routes are declared on step declarations.**

  * Step-local routes are the canonical source of topology.

```python
prepare = step(
    prompt=Prompt.file("prompts/prepare.md"),
    writes=[Md("publish_package", required=False)],
    routes={
        "ready_to_publish": "legal_review",
        "rejected": FINISH,
    },
)
```

* **No global transition table as the primary model.**

  * Old global `transitions` can remain as compatibility fallback during migration.
  * New compiler path should derive topology from each step’s `routes={...}`.

* **Entry step**

  * Default entry is the first declared step in class declaration order.
  * Authors may override:

```python
entry = "prepare"
```

* Also allow direct step object if already declared:

```python
entry = prepare
```

* **Use class namespace declaration order.**

  * Remove dependency on module-level global counters for ordering.
  * This also improves concurrency safety.

---

## Route target model

* **Allowed route targets**

  * Terminal constants:

    * `FINISH`
    * `PAUSE`
    * `FAIL`
  * `SELF`
  * string step names:

```python
"legal_review"
```

* direct step objects when already declared:

```python
legal_review
```

* rich route objects:

```python
Route.to("legal_review", ...)
```

* **String step targets are important**

  * They allow natural forward references:

```python
prepare = step(
    prompt=...,
    routes={"needs_legal_review": "legal_review"},
)

legal_review = do_review_step(...)
```

* **Compiler must**

  * resolve string targets after class creation;
  * reject unknown targets;
  * reject ambiguous targets;
  * normalize all route shorthands to canonical `Route` objects;
  * store canonical route target names in compiled topology;
  * resolve `SELF` to the current step internally.

---

## `Route` model

* **Collapse `Route` and `RouteInfo`.**

  * Remove/deprecate public `RouteInfo`.
  * Route metadata lives on `Route`.

* **Public `Route` shape**

```python
Route.to(
    target,
    summary=None,
    required_writes=None,
    handoff=None,
    on_taken=None,
)
```

* **Fields**

  * `target`
  * `summary`
  * `required_writes`
  * `handoff`
  * `on_taken`

* **Compatibility**

  * Keep existing internal `effects` temporarily if existing workflows/tests rely on it.
  * Stop documenting public route-effect DSL.
  * Demote old effect objects to advanced/internal APIs later.

---

## Route hooks instead of public effect DSL

* **Route side effects should be plain hooks/functions.**

```python
def record_rework(ctx):
    ctx.step_state.attempts += 1
    ctx.step_state.last_route = ctx.route.tag
    ctx.reset_global_session()

routes={
    "needs_rework": Route.to(
        SELF,
        on_taken=record_rework,
    ),
}
```

* **Use route hooks for**

  * step state mutation;
  * workflow state mutation;
  * item state mutation;
  * deterministic artifact healing/enrichment;
  * global session reset;
  * global session reassignment;
  * worklist metadata updates;
  * trace annotations.

* **Route hooks must not secretly change topology.**

  * Do not allow route hooks to return a different route target.
  * If dynamic routing is needed, represent it as a visible `python_step(...)`.

* **Hook execution must be observable.**

  * Emit events:

    * hook started;
    * hook finished;
    * hook failed.
  * Include hook name, step, route, and phase.

---

## Default routes

* **Plain `step(...)` default routes**

```python
"done" -> next declared step or FINISH
"question" -> PAUSE
"blocked" -> PAUSE
"failed" -> FAIL
```

* **`do_review_step(...)` default routes**

```python
"accepted" -> next declared step or FINISH
"needs_rework" -> SELF
"question" -> PAUSE
"blocked" -> PAUSE
"failed" -> FAIL
```

* **Custom route behavior**

  * If custom semantic routes are provided, do **not** inject `"done"`.

```python
step(
    prompt=...,
    routes={
        "ready_to_publish": FINISH,
        "needs_legal_review": "legal_review",
        "rejected": FINISH,
    },
)
```

* **Control routes**

  * Inject by default for agentic steps:

    * `question`
    * `blocked`
    * `failed`
  * Allow opt-out:

```python
control_routes=False
```

* Allow override:

```python
routes={
    "blocked": "manual_triage",
    "failed": FAIL,
}
```

* **Feedforward operations**

  * `llm()` / `classify()` do not have `question` or `blocked`.
  * They return a value or fail after retries.

---

## Artifacts and writes

* **Use `writes`, not `out`, `outputs`, or public `produces`.**

```python
step(
    prompt=Prompt.file("prompts/research.md"),
    writes=[Md("findings", required=True)],
)
```

* **Artifact helpers support `required`.**

```python
Md("report", required=True)
Json("manifest", Manifest, required=False)
Text("notes", required=False)
Raw("archive", required=False)
```

* **Meaning of `writes`**

  * The step may write these artifacts.
  * They are governed output surfaces.
  * Requiredness is controlled by:

    * artifact-level `required=True`;
    * route-level `required_writes`.

* **Optional writes**

  * Optional artifacts need not exist.
  * If optional schema-bearing artifacts exist, validate them.
  * If absent, do not fail.

* **Internal naming**

  * It is acceptable to keep internal `produces` temporarily.
  * Public API, docs, and compile reports should use `writes`.

---

## Required writes

* **Generic rule for plain `step(...)`**

  * Effective required writes for a selected route:

```text
if route.required_writes is not None:
    required_writes = route.required_writes
else:
    required_writes = all writes with required=True
```

* **Distinguish `None` from empty list**

  * `required_writes=None`: use artifact-level defaults.
  * `required_writes=[]`: selected route requires no writes.

* **Example**

```python
step(
    prompt=Prompt.file("prompts/prepare.md"),
    writes=[
        Md("publish_package", required=True),
        Md("legal_risk_notes", required=False),
        Md("rejection_reason", required=False),
    ],
    routes={
        "ready_to_publish": Route.to(
            FINISH,
            required_writes=["publish_package"],
        ),
        "needs_legal_review": Route.to(
            "legal_review",
            required_writes=["publish_package", "legal_risk_notes"],
        ),
        "rejected": Route.to(
            FINISH,
            required_writes=["rejection_reason"],
        ),
    },
)
```

* **Compiler must normalize `required_writes`**

  * Accept local names.
  * Accept qualified names.
  * Store canonical qualified artifact names internally.

---

## `requires`

* **Keep `requires` public and important.**

```python
draft = step(
    prompt=Prompt.file("prompts/draft.md"),
    requires=[research.findings],
    writes=[Md("draft", required=True)],
)
```

* **Meaning**

  * Hard precondition.
  * Artifact must exist before the step starts.
  * Runtime validates before invoking provider/harness.
  * Missing required artifacts fail early.

* **`requires` is different from inferred reads.**

  * Inferred reads provide context.
  * `requires` validates existence.

---

## Reads

* **Common path**

  * Do not require public `reads`.
  * Infer readable artifacts from prompt references.

* **Prompt reference inference**

```text
Use {research.findings} to write {self.draft}.
```

* Compiler infers current step reads `research.findings`.

* **Keep `reads` as an escape hatch**

  * Use for:

    * workspace files;
    * files not referenced literally in prompts;
    * explicit provider context.

```python
step(
    prompt=Prompt.file("prompts/analyze.md"),
    reads=["docs/architecture.md"],
    requires=[prepare.package],
    writes=[Md("analysis", required=True)],
)
```

* **Do not emphasize `reads` in the primary README path.**

---

## Prompt model

* **Prompts are first-class.**

  * Do not use docstrings as prompts.

* **Supported forms**

```python
Prompt.inline("...")
Prompt.file("prompts/research.md")
Prompt.ref("research")  # if registry remains
```

* **Optional shorthand**

  * Plain string may mean inline prompt.
  * `Path(...)` may mean file prompt.
  * Prefer explicit `Prompt.file(...)` in docs/examples.

* **Avoid suffix-based detection as primary behavior**

  * Do not silently treat `"prompts/foo.md"` as a file purely because it ends in `.md`, unless that behavior is deliberately documented.
  * Canonical examples should use `Prompt.file(...)`.

---

## Prompt references

* **Canonical references**

```text
{input.field}
{params.field}
{state.field}

{step_name.artifact_name}
{self.artifact_name}

{step_name.value}
{step_name.state.field}
{item.state.field}
{step_name.item_state.field}

{run.id}
{workflow.folder}
```

* **`{self.artifact}`**

  * Refers to current step’s own write artifact.
  * Compiler rewrites internally to `{current_step.artifact}`.

* **Recorded values**

  * Use explicit `.value`:

```text
{claims.value}
```

* Do not make bare `{claims}` mean a value.

* **State**

  * Workflow state:

```text
{state.attempts}
```

* Step state:

```text
{review.state.attempts}
```

* Work item state:

```text
{item.state.status}
```

* Step-item state:

```text
{review.item_state.attempts}
```

* **Reserved pseudo-fields**

  * Reserve artifact names that would collide with step pseudo-fields:

    * `value`
    * `state`
    * `item_state`
    * `meta`
  * Or implement a separate namespace such as `{values.claims}`.
  * Preferred: reserve pseudo-fields to keep prompt syntax compact.

* **Bare artifact names**

  * Allow `{report}` only if globally unambiguous.
  * If ambiguous, compile error requiring `{step.report}`.

* **Unknown placeholders**

  * Compile error when prompt text is available at compile time.
  * Runtime/preflight error if prompt is resolved later.

---

## `do_review_step`

* **Rename `review_step` to `do_review_step`.**

  * Keep deprecated alias `review_step`.

* **Rationale**

  * The primitive performs a do phase and a review phase.
  * “review step” sounds like only review.

* **Public shape**

```python
do_review_step(
    do=Prompt.file("prompts/do.md"),
    review=Prompt.file("prompts/review.md"),

    requires=[...],
    review_requires=[...],

    writes=[...],
    review_writes=[...],

    state={...},

    before_do=...,
    after_do=...,
    before_review=...,
    after_review=...,
    on_route=...,

    routes={...},

    session=...,
    review_session=...,
    retry=...,
)
```

* **Deprecated aliases**

  * `producer -> do`
  * `verifier -> review`

* **Separate do and review artifacts**

  * `writes`: do-phase writable artifacts.
  * `review_writes`: review-phase writable artifacts.
  * Producer/do and reviewer/review may have different required outputs.

---

## `do_review_step` requiredness

* **Phase-level requiredness**

  * For `do_review_step`, `required=True` on `writes` means the artifact is required after the do phase **if the author wants phase-level strictness**.
  * `required=True` on `review_writes` means the artifact is required after the review phase.

* **Flexible route-specific mode**

  * Authors can set artifacts `required=False` and use route-level `required_writes`.

```python
do_review_step(
    writes=[
        Md("legal_analysis", required=False),
    ],
    review_writes=[
        Md("legal_review_report", required=False),
        Json("decision", Decision, required=False),
    ],
    routes={
        "approved": Route.to(
            FINISH,
            required_writes=["legal_analysis", "legal_review_report", "decision"],
        ),
        "rejected": Route.to(
            FINISH,
            required_writes=["legal_review_report", "decision"],
        ),
    },
)
```

* **Review flexibility**

  * Do not automatically make all do writes hard preconditions for review.
  * Reviewer should be able to inspect missing/partial do output and route accordingly unless author declared strict phase requirements.

---

## `review_requires`

* **Default behavior**

  * `review_requires` defaults to explicitly declared `review_requires` only.
  * Review readable inputs should include:

    * inferred prompt references;
    * do writes;
    * original requires;
    * any explicit `review_requires`.

* **Do not hard-require all do writes before review by default.**

  * If strict behavior is wanted, author uses:

    * `writes=[..., required=True]`;
    * `review_requires=[...]`;
    * or an `after_do` validation hook.

---

## `do_review_step` lifecycle order

* **Runtime order**

```text
1. Build context
2. Validate requires
3. before_do
4. Run do phase
5. after_do
6. Validate review_requires, if declared
7. before_review
8. Run review phase
9. Parse review outcome
10. Validate route tag/control payload
11. after_review
12. step-level on_route hook
13. route-specific on_taken hook
14. Validate selected-route required writes
15. Checkpoint state/session/artifact metadata
16. Transition to target
```

* **Important**

  * Hooks run before final selected-route required-write validation.
  * This allows hooks to heal/enrich artifacts before validation.

---

## Plain `step(...)` lifecycle order

* **Runtime order**

```text
1. Build context
2. Validate requires
3. before hook
4. Run provider/harness
5. Parse provider outcome
6. Validate route tag/control payload
7. after hook
8. step-level on_route hook
9. route-specific on_taken hook
10. Validate selected-route required writes
11. Checkpoint state/session/artifact metadata
12. Transition to target
```

---

## Hooks

* **Hook locations**

  * Plain step:

    * `before`
    * `after`
    * `on_route`
    * route-level `on_taken`
  * `do_review_step`:

    * `before_do`
    * `after_do`
    * `before_review`
    * `after_review`
    * `on_route`
    * route-level `on_taken`

* **Hook context should expose**

```python
ctx.state
ctx.step_state
ctx.item_state
ctx.step_item_state

ctx.route
ctx.outcome
ctx.artifacts
ctx.values

ctx.input
ctx.params
ctx.run
ctx.workflow
ctx.session
ctx.meta

ctx.read(...)
ctx.write(...)
ctx.read_json(...)
ctx.write_json(...)

ctx.reset_global_session()
ctx.set_global_session(...)
ctx.open_session(...)
```

* **Return convention**

  * Hooks normally return `None`.
  * Unsupported return values raise clear errors.
  * Hooks should not redirect the route.

* **Mutation semantics**

  * State/session mutations should be transactional:

    * snapshot before hook;
    * commit on success;
    * restore on failure;
    * checkpoint failure context.
  * Artifact writes should use atomic helper methods where possible:

    * write temp file;
    * rename into place.

* **Artifact mutation**

  * If hook mutates required artifacts, final route validation catches invalid outputs.

---

## Deterministic artifact rewriting

* **Allowed but author-controlled.**

  * Do not enforce a framework rule banning it.
  * Do not force it either.

* **Preferred implementation**

  * Use hooks.

```python
def normalize_manifest(ctx):
    manifest = ctx.read_json(ctx.artifacts.manifest)
    manifest["schema"] = "my.manifest/v1"
    ctx.write_json(ctx.artifacts.manifest, manifest)

step(
    prompt=Prompt.file("prompts/write_manifest.md"),
    writes=[Json("manifest", Manifest, required=True)],
    after=normalize_manifest,
)
```

* **Framework responsibilities**

  * Trace hook execution.
  * Revalidate required artifacts after hooks.
  * Record failures clearly.
  * Do not add moral/policy restrictions beyond execution safety.

---

## State model

* **Do not treat every remembered thing as state.**

  * Keep separate:

    * artifacts;
    * recorded values;
    * mutable state;
    * execution metadata.

* **Workflow state**

  * Run-scoped mutable state.

```python
class MyWorkflow(Workflow):
    attempts = StateVar(0)
    approved = StateVar(False)
```

* **Step state**

  * Step-scoped mutable state.

```python
review = do_review_step(
    ...,
    state={
        "attempts": StateVar(0),
        "last_route": StateVar[str | None](None),
    },
)
```

* **Item state**

  * Worklist-item-scoped mutable state.

```python
ctx.item_state.status = "in_progress"
```

* **Step-item state**

  * State scoped to current step + current worklist item.

```python
ctx.step_item_state.attempts += 1
```

* **StateVar defaults**

  * Support immutable defaults:

```python
StateVar(0)
StateVar(None)
StateVar(False)
```

* Support factories for mutable defaults:

```python
StateVar(default_factory=list)
StateVar(default_factory=dict)
```

* **Avoid raw annotation magic**

  * Do not automatically interpret all class annotations as mutable state.

```python
max_attempts: int = 3  # ambiguous: state, param, or constant?
```

* **Use explicit descriptors**

```python
attempts = StateVar(0)
max_attempts = Param(3)
```

* **Compatibility**

  * Keep `class State(BaseModel)` as advanced/compatibility path.

---

## Params

* **Add public `Param(...)`.**

```python
max_attempts = Param(3)
```

* **Integrate with existing parameter mechanisms.**

  * Do not create a completely separate parameter system unless necessary.

* **Precedence**

  * Runtime/CLI override.
  * `Param(...)` default.
  * Existing `Parameters` model default if compatibility mode is used.

* **Prompt access**

```text
{params.max_attempts}
```

* **Python access**

```python
ctx.params.max_attempts
```

---

## Step state mutation

* **Hooks are the natural mutation location.**

```python
def record_rework(ctx):
    ctx.step_state.attempts += 1
    ctx.step_state.last_route = ctx.route.tag
    ctx.step_state.last_reason = ctx.outcome.reason

review = do_review_step(
    ...,
    state={
        "attempts": StateVar(0),
        "last_route": StateVar[str | None](None),
        "last_reason": StateVar[str | None](None),
    },
    routes={
        "needs_rework": Route.to(SELF, on_taken=record_rework),
    },
)
```

* **Use `python_step` only when**

  * the mutation is itself a meaningful SOP step;
  * the logic chooses among multiple visible routes;
  * the logic should appear as a node in the topology diagram.

---

## Execution metadata

* **Expose runtime metadata without requiring custom state.**

  * Step visits.
  * Last route.
  * Retry attempt.
  * Route history.
  * Provider attempt count.

* **Possible prompt references**

```text
{review.visits}
{review.last_route}
```

* **Possible Python access**

```python
ctx.meta.step.visits
ctx.meta.step.last_route
```

---

## Feedforward `llm()` and `classify()`

* **Use cases**

  * Standalone outside workflows.
  * Inside `python_step`.
  * Inside helper functions called during a workflow run.
  * As class-level feedforward steps via `.step(...)`.

* **Runtime calls**

```python
title = llm("Generate a title", returns=str)

risk = classify(
    "Classify residual risk.",
    choices=["low", "medium", "high"],
)
```

* **Class-level declarations**

```python
summary = llm.step(
    prompt=Prompt.inline("Summarize {draft.body}."),
    returns=str,
)

risk = classify.step(
    prompt=Prompt.inline("Classify {report.value}."),
    choices=["low", "medium", "high"],
)
```

* **No context-dependent declaration**

  * `llm(...)` executes or records.
  * `llm.step(...)` declares a workflow node.
  * Same for `classify`.

---

## Feedforward provider path

* **Do not reuse route-oriented `run_llm` unchanged.**

  * Current v3 `run_llm` path is outcome/route-oriented in important places. 

* **Add a value-returning provider operation path**

  * Possible API:

```python
provider.run_operation(OperationRequest(...)) -> OperationResponse
```

* Or split:

```python
provider.run_value_llm(...)
provider.run_classify(...)
```

* **Operation response**

  * Returns value, not `Outcome(tag=...)`.
  * No `question`.
  * No `blocked`.
  * No route tag.

* **`llm()` result**

  * text by default;
  * typed value if `returns=...`.

* **`classify()` result**

  * one of declared choices.

---

## `llm()` and `classify()` retry

* **Both accept `retry`.**

  * Default: `retry=3`.

```python
llm("...", returns=Report, retry=3)

classify(
    "...",
    choices=["low", "medium", "high"],
    retry=3,
)
```

* **Retry on**

  * provider/transport failure;
  * malformed value;
  * schema validation failure;
  * invalid classification choice;
  * parser failure;
  * empty response if non-empty required.

* **After retry exhaustion**

  * raise operation error;
  * fail enclosing `python_step` or feedforward node;
  * persist failure context.

---

## Deterministic operation keys

* **No public `key=` parameter.**

  * Keys are generated by the runtime.

* **Operation fingerprint should include**

  * workflow name/id;
  * topology hash;
  * source hash if available;
  * current step name;
  * operation kind;
  * callsite identity;
  * resolved prompt hash;
  * argument/input fingerprint;
  * return schema hash;
  * choices hash for `classify`;
  * scope/work-item coordinate if any;
  * occurrence index only as final tie-breaker.

* **Do not rely on ordinal-only replay.**

* **Replay behavior**

  * If matching recorded result exists, return it.
  * If fingerprint differs, fail loudly or require migration.
  * Do not silently replay stale values.

* **Failed attempts**

  * Record attempt events.
  * Only successful result becomes replayable operation result.

---

## `classify.step` and routing

* **`classify.step(...)` returns a recorded value.**

  * It does not automatically create FSM routes.

* **Routing on classification should be explicit.**

```python
verdict = classify.step(
    prompt=Prompt.inline("Classify {report.value}."),
    choices=["solid", "weak"],
)

@python_step(
    routes={
        "solid": FINISH,
        "weak": "rebut",
    },
)
def route_verdict(ctx):
    return ctx.values.verdict
```

* **Optional future primitive**

  * A later explicit helper may exist:

```python
route_by(
    value=verdict,
    routes={
        "solid": FINISH,
        "weak": "rebut",
    },
)
```

* **Do not implement implicit classifier-routing in the first pass.**

---

## `python_step`

* **Rename public `system_step` to `python_step`.**

  * Keep deprecated alias.

* **Reason**

  * Python steps may call `llm()` and `classify()`.
  * “System step” implies pure deterministic logic.

* **Public style**

```python
@python_step(
    requires=[...],
    writes=[...],
    routes={...},
)
def my_step(ctx):
    ...
    return "done"
```

* **Allowed behavior**

  * mutate state;
  * read/write artifacts;
  * call `llm()` and `classify()`;
  * invoke child workflows;
  * use `parallel(...)`;
  * return route tag.

* **Simplified return convention**

  * `None` means `"done"`.
  * `str` means route tag.
  * `Event(...)` only when reason/question/handoff is needed.
  * Avoid many tuple/model return shapes in the public path.

---

## Global session

* **Workflow has a global session field.**

```python
class MyWorkflow(Workflow):
    global_session = Session(open=True)
```

* **Default behavior**

  * Provider-backed steps use global session if `session` is unspecified.
  * Open lazily on first provider-backed use unless current provider requires eager open.

* **Explicit overrides**

```python
step(..., session="investigation")
step(..., session=Session.fresh())
```

* **`do_review_step` may specify separate review session**

```python
do_review_step(
    ...,
    session="global",
    review_session=Session.fresh(),
)
```

* **Do not force reviewer independence.**

  * Global session remains default.

* **Session hooks**

  * Context should expose:

```python
ctx.reset_global_session()
ctx.set_global_session(...)
```

* **Session changes must be**

  * trace-recorded;
  * checkpointed;
  * deterministic on resume.

---

## Provider contracts

* **Agentic step provider contract should include**

  * rendered prompt;
  * step name;
  * phase: do/review/step;
  * readable artifacts;
  * required artifacts;
  * writable artifacts;
  * available routes;
  * route summaries;
  * route-required writes;
  * retry feedback;
  * handoff;
  * expected control response.

* **Provider-specific transports should not own semantic rendering.**

  * Shared renderer builds the contract.
  * Provider adapter executes it.

* **`do_review_step` provider contract**

  * Do phase receives:

    * do prompt;
    * do requires;
    * inferred readable inputs;
    * do writable artifacts;
    * no final route contract unless explicitly supported.
  * Review phase receives:

    * review prompt;
    * review requires;
    * do artifacts as readable inputs;
    * review writable artifacts;
    * final available routes;
    * route-required writes.

---

## Provider retry

* **Provider-attributable errors should be retryable according to policy**

  * malformed outcome/control JSON;
  * illegal route tag;
  * invalid `question`;
  * missing reason for `blocked` or `failed`;
  * missing selected-route required write;
  * invalid output artifact;
  * invalid structured payload.

* **Retry feedback should be specific**

  * illegal route;
  * allowed routes;
  * missing required artifact;
  * schema error;
  * required fix.

---

## Topology artifacts

* **Generate topology artifacts**

  * At compile time or first runtime compile.

* **Suggested files**

```text
topology.json
topology.mmd
route_table.md
artifact_contracts.json
prompt_refs.json
state_contracts.json
session_contracts.json
compile_report.md
```

* **Write behavior**

  * Always write/copy compiled topology into run folder.
  * Try workflow folder if writable.
  * Fallback to cache if not writable.
  * Do not fail solely because source package is read-only.

* **`topology.json` should include**

  * workflow name/id;
  * source hash;
  * topology hash;
  * entry step;
  * terminal constants;
  * steps;
  * routes;
  * implicit routes;
  * route hooks;
  * writes;
  * required writes;
  * requires;
  * inferred reads;
  * sessions;
  * state declarations;
  * prompt references.

* **Mermaid diagram should show**

  * explicit routes;
  * implicit routes;
  * terminal targets;
  * route hooks.

```text
review -- needs_rework / record_rework --> review
review -- accepted --> FINISH
```

---

## Topology hash and resume

* **Compiled workflow gets stable topology hash.**

* **Run metadata records**

  * workflow name;
  * topology hash;
  * source hash if available;
  * compiled timestamp;
  * entry step;
  * terminal constants;
  * compile artifact paths.

* **Resume behavior**

  * Resume against saved compiled topology.
  * Or fail clearly if current topology differs and no explicit migration is requested.
  * Never silently resume against a different graph.

---

## Compiler responsibilities

* Discover workflow class members in declaration order.
* Bind step names.
* Bind artifact names.
* Bind artifact owner step.
* Assign qualified artifact names.
* Normalize `writes`.
* Normalize `review_writes`.
* Resolve `requires`.
* Parse prompt placeholders.
* Infer reads.
* Resolve route targets.
* Normalize route shorthands into `Route`.
* Inject default routes.
* Inject control routes if enabled.
* Resolve `SELF`.
* Normalize `FINISH`, `PAUSE`, `FAIL`.
* Validate route tags.
* Validate duplicate step names.
* Validate artifact name collisions.
* Reserve step pseudo-fields.
* Validate ambiguous bare prompt references.
* Validate route-required writes.
* Validate hook callability.
* Validate state declarations.
* Validate session references.
* Validate topology reachability.
* Generate topology artifacts.
* Produce immutable compiled workflow metadata.

---

## Runtime engine model

* **Preserve compiled FSM execution.**

  * Do not rewrite engine and public API simultaneously.
  * Add new authoring model by lowering into existing compiled route table first.

* **Execution loop**

```text
current = entry
while current not terminal:
    execute current step
    obtain route tag
    validate route tag
    resolve route
    run hooks
    validate selected-route required writes
    checkpoint
    current = route.target
```

* **Refactor over time**

  * Extract:

    * step dispatch;
    * provider retry orchestration;
    * hook execution;
    * artifact validation;
    * route finalization;
    * state persistence;
    * session selection;
    * child workflow invocation;
    * operation recording.

---

## Context API

* **Expose organized public context**

  * State:

    * `ctx.state`
    * `ctx.step_state`
    * `ctx.item_state`
    * `ctx.step_item_state`
  * Values/artifacts:

    * `ctx.values`
    * `ctx.artifacts`
  * Inputs/config:

    * `ctx.input`
    * `ctx.params`
  * Runtime:

    * `ctx.run`
    * `ctx.workflow`
    * `ctx.session`
    * `ctx.meta`
  * Route:

    * `ctx.route`
    * `ctx.outcome`
  * IO helpers:

    * `ctx.read(...)`
    * `ctx.write(...)`
    * `ctx.read_json(...)`
    * `ctx.write_json(...)`
  * Session helpers:

    * `ctx.reset_global_session()`
    * `ctx.set_global_session(...)`
    * `ctx.open_session(...)`

---

## Worklists and scopes

* **Common path should be simple static lists**

```python
items = Worklist.from_param("articles")
```

or:

```python
items = Worklist.from_list([...])
```

* **Scoped step**

```python
step(..., scope=items)
```

* **Scoped artifacts**

  * Artifact paths include item coordinate.

* **Advanced board/mutable worklist machinery**

  * Keep available.
  * Demote from primary docs.
  * Do not delete early because existing code has substantial board/worklist support. 

---

## Concurrency

* **Inter-run concurrency**

  * Runs are isolated.
  * Per-run context.
  * Per-run checkpoint store.
  * Per-run session store.
  * Workspace/task locks where shared filesystem state exists.
  * No module-level mutable counters.
  * Event writes need locking or documented single-writer semantics.

* **Intra-run concurrency**

  * Parent FSM remains sequential.
  * Parallel lightweight work can happen inside `python_step`.
  * Parallel long-running agentic work should use child workflows.

* **No top-level parallel FSM steps in this version.**

* **Possible `parallel(...)` helper**

```python
results = parallel(
    [
        lambda item=item: llm(f"Summarize {item}", returns=Summary)
        for item in items
    ],
    concurrency=5,
    failure="fail_fast",
)
```

* **Parallel mutation rule**

  * Parallel bodies should return values.
  * Do not allow unsynchronized shared state mutation inside parallel bodies.
  * Parent step merges results after join.

* **Parallel sessions**

  * Parallel operations should not share global session concurrently unless serialized by a session lock.
  * Child workflows get their own session hierarchy.

---

## Child workflows

* **Keep `workflow_step`.**

```python
child = workflow_step(
    SomeWorkflow,
    input=...,
    writes=[Json("child_result", ChildResult, required=True)],
    routes={
        "done": "next_step",
        "failed": FAIL,
    },
)
```

* **Child result should preserve**

  * child workflow name;
  * child run id;
  * terminal;
  * final route/event;
  * output artifacts;
  * output value;
  * metadata.

---

## Git tracking

* **Runtime policy, not workflow mandate.**

```python
Runtime(git_tracking=False)
Runtime(git_tracking="per_run")
Runtime(git_tracking="per_step")
```

* Do not bake auto-commit behavior into the workflow authoring model.
* Avoid conflicting workflow-declared and runtime-declared git tracking paths.

---

## Stdlib separation

* **Move optimizer/application-specific stdlib code out of framework core.**

  * Target sibling package:

```text
autoloop_optimizer
```

* **Move or demote**

  * optimization scoring;
  * candidate surfaces;
  * company snapshots;
  * portfolio diagnostics;
  * recursive improvement workflows;
  * optimizer-specific route info helpers;
  * workflow package builder logic that is not generic infrastructure.

* **Keep small generic stdlib**

  * artifact helpers;
  * static worklist helpers;
  * generic do/review patterns;
  * fake/test provider;
  * common retry defaults.

---

## Packaging cleanup

* Remove dual import shims after migration.
* Prefer typed declaration objects over public dunder marker protocols.
* Normalize package imports.
* Avoid requiring repo-root script execution patterns.
* Keep compatibility only as long as necessary for migration.

---

## Schema registry

* Centralize schema IDs.
* Add something like:

```python
core/schema_registry.py
```

* Avoid scattered literal schema strings.
* Prepare for future schema migration.

---

## Static graph inspection

* Update static graph generation to consume compiled route table.
* Include:

  * route tags;
  * terminals;
  * hooks;
  * implicit routes;
  * required writes;
  * state/session annotations where useful.

---

## Run metadata and audit trail

* Preserve and strengthen:

  * `run.json`
  * `events.jsonl`
  * `trace.jsonl`
  * `checkpoint.json`
  * raw provider logs
  * compiled topology copy
  * artifact contract records
  * prompt reference records
  * session metadata
  * hook execution events
  * operation replay records

* Run result should include:

  * terminal;
  * last step;
  * last route;
  * state;
  * output;
  * output validation status;
  * checkpoint if paused/failed;
  * topology hash;
  * final artifact paths.

---

## Testing requirements

* **Terminal rename**

  * `FINISH` works.
  * `SUCCESS` alias works temporarily.
  * Generated topology uses `FINISH`.

* **Lowercase `"done"`**

  * Plain step defaults to `"done"`.
  * Final plain step routes `"done" -> FINISH`.
  * Custom semantic routes do not inject `"done"`.

* **Step-local routes**

  * string forward refs;
  * direct object refs;
  * `SELF`;
  * unknown target compile error;
  * explicit entry;
  * first-declared entry default.

* **Route metadata**

  * `summary`;
  * `required_writes`;
  * `handoff`;
  * `on_taken`;
  * no `RouteInfo` required.

* **Writes**

  * `writes=[...]`;
  * `required=True`;
  * `required=False`;
  * route-specific required writes;
  * optional schema artifacts validate only if present.

* **Requires**

  * Missing `requires` artifact fails before provider call.

* **Prompt refs**

  * `{step.artifact}`;
  * `{self.artifact}`;
  * `{step.value}`;
  * `{step.state.field}`;
  * unknown placeholder error;
  * ambiguous bare name error;
  * reserved pseudo-field collision error.

* **`do_review_step`**

  * do/review prompt names;
  * deprecated producer/verifier aliases;
  * separate `writes` / `review_writes`;
  * defaults;
  * custom routes;
  * route-required writes across both artifact sets;
  * lifecycle hooks order.

* **Hooks**

  * hook mutates step state;
  * hook resets session;
  * hook heals artifact;
  * hook failure checkpointed;
  * hook cannot redirect route.

* **State**

  * workflow `StateVar`;
  * step state;
  * item state;
  * step-item state;
  * default factories;
  * checkpoint/resume.

* **`llm()` / `classify()`**

  * standalone;
  * inside `python_step`;
  * `.step(...)`;
  * retry default;
  * schema retry;
  * invalid choice retry;
  * replay;
  * fingerprint mismatch.

* **Sessions**

  * global default;
  * explicit override;
  * review session override;
  * reset global session via hook;
  * checkpoint persistence.

* **Topology artifacts**

  * files generated;
  * hooks included;
  * implicit routes marked;
  * stable topology hash.

* **Concurrency hygiene**

  * no global step ordering race;
  * separate run stores;
  * event writes safe or documented single-writer.

---

## Migration phases

* **Phase 1: public API and route topology**

  * Add `FINISH`.
  * Keep `SUCCESS` alias.
  * Add `SELF`.
  * Add `writes`.
  * Add `required` to artifact helpers.
  * Add step-local `routes`.
  * Lower step-local routes into existing compiled route table.
  * Preserve old global transitions as fallback.
  * Generate basic topology artifacts.

* **Phase 2: `do_review_step`**

  * Add `do_review_step`.
  * Keep `review_step` alias.
  * Add `do` / `review` prompt names.
  * Add `review_writes`.
  * Add review lifecycle hooks.
  * Separate do/review provider contracts.
  * Add route-required writes across both write sets.

* **Phase 3: hooks and state**

  * Add `StateVar`.
  * Add workflow state descriptors.
  * Add step state.
  * Add item/step-item state if needed.
  * Add hook context.
  * Add `Route.on_taken`.
  * Add hook execution events.
  * Add global session reset/set APIs.

* **Phase 4: feedforward operations**

  * Add standalone `llm()` / `classify()`.
  * Add `.step(...)`.
  * Add operation recorder.
  * Add deterministic operation keys.
  * Add retry.
  * Add value-returning provider operation path.

* **Phase 5: cleanup**

  * Update built-in workflows.
  * Move optimizer stdlib out.
  * Demote old route effects DSL.
  * Deprecate `chain`, `RouteInfo`, `StrictWorkflow`, `out`, `outputs`, public `produces`.
  * Refactor engine modules after behavior is stable.

---

## Canonical target example

```python
from pydantic import BaseModel

from autoloop import (
    Workflow,
    Session,
    Prompt,
    Md,
    Json,
    Route,
    StateVar,
    FINISH,
    SELF,
    step,
    do_review_step,
)

class Decision(BaseModel):
    approved: bool
    reason: str

def record_rework(ctx):
    ctx.step_state.attempts += 1
    ctx.step_state.last_route = ctx.route.tag
    ctx.step_state.last_reason = ctx.outcome.reason

class ArticlePublication(Workflow):
    global_session = Session(open=True)

    prepare = step(
        prompt=Prompt.file("prompts/prepare_publication.md"),
        writes=[
            Md("publish_package", required=False),
            Md("legal_risk_notes", required=False),
            Md("rejection_reason", required=False),
        ],
        routes={
            "ready_to_publish": Route.to(
                FINISH,
                required_writes=["publish_package"],
            ),
            "needs_legal_review": Route.to(
                "legal_review",
                required_writes=["publish_package", "legal_risk_notes"],
            ),
            "rejected": Route.to(
                FINISH,
                required_writes=["rejection_reason"],
            ),
        },
    )

    legal_review = do_review_step(
        do=Prompt.file("prompts/legal_review.md"),
        review=Prompt.file("prompts/verify_legal_review.md"),
        requires=[prepare.publish_package],
        writes=[
            Md("legal_analysis", required=False),
        ],
        review_writes=[
            Md("legal_review_report", required=True),
            Json("decision", Decision, required=False),
        ],
        state={
            "attempts": StateVar(0),
            "last_route": StateVar[str | None](None),
            "last_reason": StateVar[str | None](None),
        },
        routes={
            "approved": Route.to(
                FINISH,
                required_writes=[
                    "legal_analysis",
                    "legal_review_report",
                    "decision",
                ],
            ),
            "needs_rework": Route.to(
                "prepare",
                required_writes=["legal_review_report"],
                on_taken=record_rework,
            ),
            "rejected": Route.to(
                FINISH,
                required_writes=["legal_review_report", "decision"],
            ),
        },
    )
```

---

## Final implementation instruction

* Add the new authoring model by **lowering it into the existing compiled FSM first**.
* Do not simultaneously rewrite the engine, provider layer, state system, and public API in one pass.
* Prioritize preserving current runtime reliability while replacing the authoring surface.
* Treat author preferences as hooks/options, not framework law.
* Keep the public model small enough for LLMs to write correctly.
