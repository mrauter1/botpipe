Below is the revised standalone implementation spec for Codex CLI. It incorporates your latest decisions:

* **No redundant/bilingual names.**
* **No public legacy aliases unless there is a real runtime/data-migration reason.**
* **Use `produce_verify_step`, not `do_review_step`.**
* **Use `producer_prompt` and `verifier_prompt`.**
* **Remove `do_prompt` and `review_prompt`.**
* **Keep lowercase `"done"` as the plain-step default route.**
* **Use `FINISH` as the controlled terminal.**
* **Keep the framework centered on orchestrating agentic harnesses such as Codex CLI / Claude Code, where artifacts and SOP routing are the core interface.** This matches the core purpose previously identified: the workflow provides the SOP while the agentic harness executes each stage, with artifacts, routes, sessions, resumability, and audit trail as the framework’s value. 

---

# Autoloop v3 cleanup / completion spec for Codex CLI

## 1. Global implementation rule

* Remove redundant names instead of preserving compatibility aliases.
* Keep only one public name for each concept.
* Keep only one internal canonical field name for each concept.
* Do not keep old names such as `SUCCESS`, `RouteInfo`, `StrictWorkflow`, `review_step`, `do_review_step`, `system_step`, `out`, `outputs`, `produces`, `required_outputs`, `do_prompt`, or `review_prompt` unless Codex finds a concrete persisted-data migration reason.
* If persisted old run files need to be read, implement an internal one-way migration reader. Do **not** expose old names in the public authoring API.
* Update tests, examples, topology artifacts, provider rendering, static graph payloads, run metadata, and docs to use only the canonical names.
* Add strictness tests that grep or import-check that removed names are absent from the public API.
* The current implementation still exposes many redundant public names, including `SUCCESS`, `RouteInfo`, `StrictWorkflow`, `chain`, `do_review_step`, `review_step`, and `system_step`; the cleanup should remove these rather than keep them as normal exports. 

---

## 2. Canonical naming table

* Terminal:

  * Keep: `FINISH`
  * Remove: `SUCCESS`
  * Remove: `DONE`
  * Remove: `TERMINATE`

* Plain step success route:

  * Keep: lowercase `"done"`
  * This is a route tag, not a terminal.

* Producer/verifier primitive:

  * Keep: `produce_verify_step`
  * Remove: `do_review_step`
  * Remove: `review_step`
  * Remove internal/public wording `review_step`
  * Remove public/internal fields named `do_prompt`
  * Remove public/internal fields named `review_prompt`
  * Keep canonical fields:

    * `producer_prompt`
    * `verifier_prompt`

* Python step:

  * Keep: `python_step`
  * Remove: `system_step`
  * Rename internal `SystemStep` to `PythonStep` where practical.
  * Compiled kind should be `"python"`, not `"system"`.

* Agentic single-turn harness step:

  * Keep public function: `step`
  * Internally prefer `AgentStep` or `HarnessStep`.
  * Compiled kind should be `"step"` or `"agent"`, but choose one and use it everywhere.
  * Recommendation: use `kind="step"` because it matches the public primitive.

* Feedforward operations:

  * Keep: `llm`
  * Keep: `classify`
  * Compiled kind: `"operation"`
  * Operation kind: `"llm"` or `"classify"`
  * Do not compile feedforward operations as `"python"` or `"system"` nodes.

* Artifacts:

  * Keep: `writes`
  * Remove: `out`
  * Remove: `outputs`
  * Remove public/internal `produces` where possible.
  * Internal compiled field should be `writes`, not `produces`.

* Route metadata:

  * Keep: `Route`
  * Remove: `RouteInfo`
  * Keep: `required_writes`
  * Remove: `required_outputs`
  * Keep: `routes`
  * Remove: `route_infos`
  * Remove: `route_summaries`

* Workflow base:

  * Keep: `Workflow`
  * Remove: `StrictWorkflow`
  * Do not expose multiple workflow bases.

* Flow/topology:

  * Keep: step-local `routes={...}`
  * Remove: `chain`
  * Remove: class-level `flow`
  * Remove: class-level `transitions` as public authoring surface.
  * Compiler derives topology from step-local routes and default declaration order.

* Session:

  * Keep: `global_session`
  * Keep: `Session`
  * Keep: `Continuity`
  * Rename internal default session slot from `"default"` to `"global"` if feasible.
  * Avoid mixed terms `default_session` and `global_session` in public output. Use `global_session`.

---

## 3. Canonical public API

* `autoloop/__init__.py` should export only:

```python
Workflow

step
produce_verify_step
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
Worklist

Event
Outcome

FINISH
PAUSE
FAIL
SELF
```

* Do not export:

  * `SUCCESS`
  * `DONE`
  * `TERMINATE`
  * `RouteInfo`
  * `StrictWorkflow`
  * `WorkflowStep` class
  * `AfterHookResult`
  * `ResolvedArtifacts`
  * `Checkpoint`
  * `ChildWorkflowResult`
  * `chain`
  * `review_step`
  * `do_review_step`
  * `system_step`
  * route effect DSL classes such as `Advance`, `Refresh`, `ResetCompletion`, `SetStatus`, unless they are intentionally moved to an advanced/internal module.
* `Event` remains public because `python_step` may return an `Event` when reason/question/handoff fields are needed.
* `Outcome` remains public because hooks may inspect provider outcomes.

---

## 4. Terminal constants

* Define canonical terminals in `core/primitives.py` or equivalent:

```python
FINISH = "FINISH"
PAUSE = "PAUSE"
FAIL = "FAIL"
SELF = "SELF"
```

* Delete `SUCCESS`.
* Do not alias `SUCCESS = FINISH`.
* Update all engine checks:

```python
if destination == FINISH:
    ...
```

* `RunResult.terminal` must be one of:

```python
"FINISH"
"PAUSE"
"FAIL"
```

* Terminal events, run metadata, child workflow results, static graph payloads, topology artifacts, and trace events must use `FINISH`, not `SUCCESS`.
* Update any test that currently asserts `result.terminal == SUCCESS`.
* If old persisted run files contain `"SUCCESS"`, optionally support an internal migration function:

```python
normalize_terminal_for_old_run_file("SUCCESS") -> "FINISH"
```

* Do not expose `SUCCESS` in public Python imports.

---

## 5. Lowercase `"done"` route

* Keep lowercase `"done"` as the default route tag for a plain `step(...)`.
* Meaning:

```text
"done" = this step completed normally
FINISH = the workflow reached a controlled terminal
```

* Example generated topology:

```text
research.done -> draft
draft.done -> FINISH
```

* `"done"` must never be used as a terminal constant.
* `FINISH` must never be used as a route tag unless the author explicitly names a route `"FINISH"`, which should be discouraged and may be rejected as a reserved tag.

---

## 6. Public `Route` model

* Collapse route target and route metadata into one type.

```python
Route.to(
    target,
    *,
    summary: str | None = None,
    required_writes: Sequence[str] | None = None,
    handoff: str | None = None,
    on_taken: Callable[[HookContext], None] | None = None,
)
```

* Remove `RouteInfo`.
* Remove `required_outputs`.
* Remove positional `*effects`.
* Remove public effect DSL from `Route.to(...)`.
* Route fields:

```python
@dataclass(frozen=True)
class Route:
    target: object
    summary: str | None = None
    required_writes: tuple[str, ...] | None = None
    handoff: str | None = None
    on_taken: Callable[..., None] | None = None
```

* Important distinction:

```python
required_writes=None  # use artifact-level defaults
required_writes=[]    # this route requires no writes
```

* `Route.finish(...)` may exist as a convenience:

```python
Route.finish(required_writes=[...])
```

* Remove `Route.complete(...)` because “complete” continues the old `SUCCESS` language.

---

## 7. Route target resolution

* Route targets may be:

  * `FINISH`
  * `PAUSE`
  * `FAIL`
  * `SELF`
  * string step name
  * direct step declaration object if already declared
  * `Route.to(...)`

* Examples:

```python
routes={
    "ready": FINISH,
    "needs_legal_review": "legal_review",
    "needs_rework": SELF,
}
```

```python
routes={
    "approved": Route.to(FINISH, required_writes=["report"]),
    "needs_rework": Route.to(SELF, on_taken=record_rework),
}
```

* Compiler must:

  * resolve string targets after class creation;
  * reject unknown step targets;
  * reject ambiguous targets;
  * reject route tags not declared for a step;
  * normalize all shorthands to `Route`;
  * normalize terminal targets to canonical strings;
  * include route hooks in topology artifacts.

---

## 8. Step-local topology only

* Routes are declared on the step declaration.
* Remove class-level `flow`.
* Remove class-level `transitions`.
* Remove public `chain`.

```python
class MyWorkflow(Workflow):
    research = step(
        prompt=Prompt.file("prompts/research.md"),
        writes=[Md("findings", required=True)],
    )

    draft = step(
        prompt=Prompt.file("prompts/draft.md"),
        requires=[research.findings],
        writes=[Md("draft", required=True)],
    )
```

* If a step has no custom `routes`, compiler injects default routes and connects the success route to the next declared step.
* Entry step:

  * default: first declared step;
  * optional explicit:

```python
entry = "research"
```

* Compiler derives topology from:

  * declaration order;
  * step-local `routes`;
  * default routes;
  * explicit `entry`.

---

## 9. Default route injection

* Plain `step(...)` with no custom routes:

```text
done -> next declared step or FINISH
question -> PAUSE
blocked -> PAUSE
failed -> FAIL
```

* `produce_verify_step(...)` with no custom routes:

```text
accepted -> next declared step or FINISH
needs_rework -> SELF
question -> PAUSE
blocked -> PAUSE
failed -> FAIL
```

* `python_step(...)` with no custom routes:

```text
done -> next declared step or FINISH
failed -> FAIL
```

* `workflow_step(...)` with no custom routes:

```text
done -> next declared step or FINISH
failed -> FAIL
```

* `llm.step(...)` and `classify.step(...)`:

```text
done -> next declared step or FINISH
```

* Feedforward operation nodes do not have:

  * `question`
  * `blocked`
  * semantic choice routes.

* If a step declares custom semantic routes:

  * do not inject `"done"` for plain `step`;
  * do not inject `"accepted"` / `"needs_rework"` for `produce_verify_step`;
  * still inject control routes unless `control_routes=False`.

* Control routes:

  * default enabled for agentic `step` and `produce_verify_step`;
  * configurable:

```python
control_routes=False
```

---

## 10. Canonical artifact declarations

* Use only `writes` for plain steps, Python steps, workflow steps, and operation steps when applicable.

```python
writes=[
    Md("report", required=True),
    Json("manifest", Manifest, required=False),
]
```

* Artifact helpers:

```python
Md(name, *, path=None, required=False)
Json(name, schema=None, *, path=None, required=False)
Text(name, *, path=None, required=False)
Raw(name, *, path=None, required=False)
```

* Remove public and internal aliases:

  * `out`
  * `outputs`
  * `produces`

* If Codex keeps an internal field briefly to reduce patch size, the final code must not expose it in:

  * public API;
  * topology artifacts;
  * provider contracts;
  * compiled reports;
  * tests;
  * docs.

* Preferred internal compiled field:

```python
CompiledStep.writes: tuple[str, ...]
```

* Remove or rename:

```python
CompiledStep.produces
step.produces
ProviderTurnContext.writable_artifacts derived from produces
```

* Provider contracts should say “writes” or “writable artifacts,” never “outputs” or “produces.”

---

## 11. Required writes semantics

* Plain `step(...)`, `python_step(...)`, `workflow_step(...)`, and operation step final validation:

```python
if selected_route.required_writes is not None:
    required = selected_route.required_writes
else:
    required = [artifact.name for artifact in step.writes if artifact.required]
```

* Explicit empty list is meaningful:

```python
Route.to(FINISH, required_writes=[])
```

means the route requires no artifacts.

* Optional artifacts:

  * absent: okay;
  * present with schema: validate;
  * present without schema: no schema validation.

* Compiler must normalize `required_writes`:

  * local artifact name → canonical qualified name;
  * qualified artifact name → canonical qualified name;
  * unknown artifact → compile error.

* Do not use the phrase `required_outputs` anywhere in public or compiled metadata.

---

## 12. `requires` and `reads`

* Keep `requires`.
* Meaning:

  * hard precondition;
  * must exist before the step or phase starts;
  * missing required artifact fails before provider/harness call.

```python
draft = step(
    prompt=Prompt.file("prompts/draft.md"),
    requires=[research.findings],
    writes=[Md("draft", required=True)],
)
```

* Keep optional `reads` only as an extra non-validating readable context escape hatch.
* Reads are otherwise inferred from qualified prompt references.
* Do not collapse `requires` and `reads`.
* Do not make `reads` the main API path.
* If a prompt contains:

```text
{research.findings}
```

the compiler should infer that the current step reads `research.findings`.

* If the author also lists it in `reads`, dedupe.

---

## 13. Prompt model

* Prompts are first-class.
* Do not use docstrings as prompts.
* Canonical forms:

```python
Prompt.inline("...")
Prompt.file("prompts/research.md")
Prompt.ref("registered_prompt_name")
```

* Optional shorthand:

  * `str` means inline prompt.
  * `Path` means file prompt.
* Do not infer file prompts from string suffixes like `.md` or `.txt`.
* Therefore:

```python
prompt="prompts/research.md"
```

means inline text containing that literal string.

* To use a file:

```python
prompt=Prompt.file("prompts/research.md")
```

* This avoids ambiguous suffix-based behavior.

---

## 14. Prompt references

* Supported prompt placeholders:

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

* Recommended artifact reference form:

```text
{previous_step.artifact_name}
```

* Example:

```python
draft = step(
    prompt=Prompt.inline("Use {research.findings} to write {self.draft}."),
    writes=[Md("draft", required=True)],
)
```

* `self` references the current step.

* `{self.draft}` resolves to the current step’s `draft` artifact path.

* `{research.findings}` resolves to the path for the `findings` artifact written by step `research`.

* Inference:

  * qualified artifact references infer reads automatically;
  * unknown references are compile errors;
  * ambiguous bare references are compile errors.

* Bare artifact references such as `{findings}`:

  * may be disallowed entirely for simplicity; or
  * allowed only if globally unambiguous.

* Recommendation for Codex:

  * allow only qualified artifact references in generated docs/examples;
  * if bare references are supported, treat them as convenience only and reject ambiguity.

* Reserve pseudo-fields:

  * `value`
  * `state`
  * `item_state`
  * `meta`

* Artifact names cannot be any reserved pseudo-field.

---

## 15. `step(...)`

* `step(...)` is a single agentic harness stage.

* It is not an SDK LLM call.

* It hands Codex CLI / Claude Code a governed runtime contract and expects a route-bearing outcome.

* Public shape:

```python
step(
    *,
    prompt: PromptInput,
    requires: Sequence[ArtifactRef] = (),
    reads: Sequence[ArtifactRef | str | Path] = (),
    writes: Sequence[ArtifactSpec] = (),
    routes: Mapping[str, Route | str | object] | None = None,
    before: Hook | None = None,
    after: Hook | None = None,
    on_route: Hook | None = None,
    state: Mapping[str, StateVar] | None = None,
    session: str | Session | None = None,
    retry: int = 3,
    control_routes: bool = True,
)
```

* Positional prompt may be allowed:

```python
step(Prompt.file("prompts/research.md"), writes=[...])
```

* But docs should prefer keyword style for LLM authors:

```python
step(
    prompt=Prompt.file("prompts/research.md"),
    writes=[Md("findings", required=True)],
)
```

* Default routes if no custom routes:

  * `"done"` to next/`FINISH`
  * `"question"` to `PAUSE`
  * `"blocked"` to `PAUSE`
  * `"failed"` to `FAIL`

* Provider response for `step(...)` is an outcome JSON with a legal route tag.

---

## 16. `produce_verify_step(...)`

* This is the canonical producer/verifier primitive.

* It replaces:

  * `do_review_step`
  * `review_step`
  * `PairStep` public wording
  * `do_prompt`
  * `review_prompt`
  * `review_writes`
  * `review_requires`
  * `review_session`

* Public function name:

```python
produce_verify_step(...)
```

* Canonical public shape:

```python
produce_verify_step(
    *,
    producer_prompt: PromptInput,
    verifier_prompt: PromptInput,

    requires: Sequence[ArtifactRef] = (),
    reads: Sequence[ArtifactRef | str | Path] = (),

    verifier_requires: Sequence[ArtifactRef] = (),
    verifier_reads: Sequence[ArtifactRef | str | Path] = (),

    producer_writes: Sequence[ArtifactSpec] = (),
    verifier_writes: Sequence[ArtifactSpec] = (),

    routes: Mapping[str, Route | str | object] | None = None,

    state: Mapping[str, StateVar] | None = None,

    before_producer: Hook | None = None,
    after_producer: Hook | None = None,
    before_verifier: Hook | None = None,
    after_verifier: Hook | None = None,
    on_route: Hook | None = None,

    session: str | Session | None = None,
    verifier_session: str | Session | None = None,

    retry: int = 3,
    control_routes: bool = True,
)
```

* Do not accept:

  * `do=`
  * `review=`
  * `producer=`
  * `verifier=`
  * `do_prompt=`
  * `review_prompt=`
  * `writes=` for this primitive, if using explicit `producer_writes`.
  * `review_writes=`
  * `review_requires=`
  * `review_session=`

* Rationale for explicit names:

  * `producer_prompt` and `verifier_prompt` are clearer and align with the actual harness phases.
  * `producer_writes` and `verifier_writes` make phase ownership explicit.
  * `verifier_requires` and `verifier_reads` acknowledge that verifier inputs are not necessarily the same as producer inputs.

* Internal class should be renamed:

  * `PairStep` → `ProduceVerifyStep`
  * compiled kind: `"produce_verify"`

* Compiled fields should be:

```python
producer_prompt
verifier_prompt

producer_reads
producer_requires
producer_writes

verifier_reads
verifier_requires
verifier_writes
```

* Remove compiled fields:

  * `do_prompt`
  * `review_prompt`
  * `producer` as prompt field if it ambiguously means a step object
  * `verifier` as prompt field if it ambiguously means a step object
  * `review_writes`
  * `review_requires`

* The current implementation already demonstrates separate producer and verifier behavior, including verifier-specific session and verifier-specific requirements, but it still uses `do_review_step`, `do=`, `review=`, and `review_writes`; replace those with the canonical producer/verifier naming. 

---

## 17. `produce_verify_step` default routes

* If no custom routes are declared:

```text
accepted -> next declared step or FINISH
needs_rework -> SELF
question -> PAUSE
blocked -> PAUSE
failed -> FAIL
```

* If custom routes are declared, do not inject `accepted` or `needs_rework` unless explicitly included.
* Still inject control routes unless `control_routes=False`.
* Example custom routes:

```python
legal_review = produce_verify_step(
    producer_prompt=Prompt.file("prompts/legal_producer.md"),
    verifier_prompt=Prompt.file("prompts/legal_verifier.md"),
    producer_writes=[Md("legal_analysis", required=False)],
    verifier_writes=[Md("legal_review_report", required=True)],
    routes={
        "approved": Route.to(
            FINISH,
            required_writes=["legal_analysis", "legal_review_report"],
        ),
        "needs_rework": Route.to(
            SELF,
            required_writes=["legal_review_report"],
            on_taken=record_rework,
        ),
        "rejected": Route.to(
            FINISH,
            required_writes=["legal_review_report"],
        ),
    },
)
```

---

## 18. `produce_verify_step` lifecycle

* Runtime order:

```text
1. Build context
2. Validate producer requires
3. Run before_producer hook
4. Run producer harness phase
5. Run after_producer hook
6. Validate required producer_writes marked required=True
7. Validate verifier_requires
8. Run before_verifier hook
9. Run verifier harness phase
10. Parse verifier outcome
11. Validate route tag/control payload
12. Run after_verifier hook
13. Run step-level on_route hook
14. Run route-specific on_taken hook
15. Validate selected-route required_writes
16. Checkpoint state/session/artifact metadata
17. Transition to target
```

* Hooks run before final selected-route required write validation.
* This allows deterministic artifact healing/enrichment in hooks.
* Producer phase does not select the final route.
* Verifier phase selects the final route.
* Verifier prompt receives:

  * verifier prompt text;
  * verifier readable artifacts;
  * verifier required artifacts;
  * producer writes as readable artifact refs by default;
  * final route table;
  * route-required writes;
  * retry feedback if applicable.
* Producer prompt receives:

  * producer prompt text;
  * producer readable artifacts;
  * producer required artifacts;
  * producer writable artifacts;
  * no final route-selection responsibility.

---

## 19. Producer/verifier read/require defaults

* Producer phase:

  * `producer_requires = requires`
  * `producer_reads = reads + inferred qualified refs from producer_prompt`

* Verifier phase:

  * `verifier_requires = explicit verifier_requires only`
  * `verifier_reads = verifier_reads + inferred qualified refs from verifier_prompt + producer_writes`

* Do not automatically require all producer writes before verifier.

* If the author wants producer outputs to be mandatory before verifier runs, they set:

```python
producer_writes=[Md("draft", required=True)]
```

or:

```python
verifier_requires=["draft"]
```

* This preserves flexibility: a verifier can inspect partial/missing producer outputs and route to `needs_rework`, `blocked`, or `failed`.

---

## 20. Producer/verifier requiredness

* `producer_writes=[..., required=True]`

  * validate after producer phase and after `after_producer`.
  * missing/invalid required producer write should be provider-attributable and retryable if retry budget remains.

* `verifier_writes=[..., required=True]`

  * included in final required writes when selected route has `required_writes=None`.
  * route-specific `required_writes` overrides generic artifact-level final requiredness.

* Final selected route required writes:

```python
if route.required_writes is not None:
    required = route.required_writes
else:
    required = (
        all producer_writes with required=True
        + all verifier_writes with required=True
    )
```

* If route uses `required_writes=[]`, final route requires no artifacts, but already-enforced producer phase requirements still apply.

---

## 21. Hooks

* Hooks are the canonical place for step-state mutation and route side effects.

* No public route-effect DSL.

* Hook locations:

  * `before`
  * `after`
  * `on_route`
  * `Route.to(..., on_taken=...)`
  * `before_producer`
  * `after_producer`
  * `before_verifier`
  * `after_verifier`

* Hooks mutate `ctx` and return `None`.

```python
def record_rework(ctx):
    ctx.step_state.attempts += 1
    ctx.step_state.last_route = ctx.route.tag
```

* Do not use `AfterHookResult`.

* Remove `AfterHookResult` entirely from public API.

* Remove hook return support for:

  * route override;
  * event override;
  * handoff override.

* If route redirection is needed, use a visible `python_step(...)`.

* Hook failures:

  * emit `hook_failed`;
  * checkpoint failure context;
  * roll back state/session mutation if practical;
  * artifact rollback not required, but artifact helper writes should be atomic.

* Hook events:

  * `hook_started`
  * `hook_finished`
  * `hook_failed`

* Hook event payload:

  * hook name;
  * step name;
  * hook phase;
  * selected route, if available;
  * run id;
  * sequence number.

---

## 22. Route hooks

* Route-specific hook:

```python
Route.to(SELF, on_taken=record_rework)
```

* `on_taken` runs after route tag validation and before final required write validation.

* `on_taken` may:

  * mutate workflow state;
  * mutate step state;
  * mutate item state;
  * reset/set session;
  * heal/enrich artifacts;
  * write trace annotations.

* `on_taken` may not:

  * return a route;
  * return an `Event`;
  * mutate topology;
  * silently redirect to another step.

---

## 23. Deterministic artifact rewriting

* Allowed.
* Author-controlled.
* Usually implemented in hooks.
* No framework doctrine banning it.

```python
def normalize_manifest(ctx):
    manifest = ctx.read_json(ctx.artifacts.manifest)
    manifest["schema"] = "my.manifest/v1"
    ctx.write_json(ctx.artifacts.manifest, manifest)
```

* Framework responsibilities:

  * trace hook execution;
  * revalidate final required artifacts;
  * preserve error context if validation fails;
  * optionally record before/after hashes.

---

## 24. `python_step(...)`

* Canonical deterministic/Python step.
* Replaces `system_step`.

```python
@python_step(
    routes={
        "continue": "produce",
        "stop": FINISH,
    },
)
def decide(ctx):
    if ctx.step_state.produce.attempts >= ctx.params.max_attempts:
        return "stop"
    return "continue"
```

* Public return convention:

  * `None` → `"done"`
  * `str` → route tag
  * `Event` → route tag plus reason/question/handoff metadata

* Remove public tuple return forms:

  * `(state, route)`
  * `(state, Event)`

* State is mutated through `ctx`, not by returning a new Pydantic model.

* Internal engine may normalize old forms only if existing internal tests require migration, but final public tests/docs should not use them.

---

## 25. Feedforward `llm()` and `classify()`

* `llm()` and `classify()` are feedforward operations.

* They are not agentic harness steps.

* They do not route.

* They do not pause.

* They do not ask questions.

* They do not return `blocked`.

* They either return a value or raise after retry exhaustion.

* Runtime calls:

```python
title = llm(
    Prompt.inline("Generate a title."),
    returns=str,
    retry=3,
)

risk = classify(
    Prompt.inline("Classify residual risk."),
    choices=["low", "medium", "high"],
    retry=3,
)
```

* Class-level declarations:

```python
title = llm.step(
    prompt=Prompt.inline("Generate a title from {draft.body}."),
    returns=str,
)

risk = classify.step(
    prompt=Prompt.inline("Classify {report.value}."),
    choices=["low", "medium", "high"],
)
```

* `.step(...)` operation nodes:

  * compiled kind: `"operation"`
  * operation kind: `"llm"` or `"classify"`
  * only default route: `"done"` to next/`FINISH`
  * no choice-based routes.

* If routing on a classification is needed, use explicit `python_step`:

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

---

## 26. Operation provider path

* Keep a value-returning provider operation path distinct from route-bearing harness turns.
* Required provider method:

```python
provider.run_operation(OperationRequest(...)) -> OperationResponse
```

* Or split:

```python
provider.run_value_llm(...)
provider.run_classify(...)
```

* Operation response:

  * raw text;
  * parsed value;
  * session binding if applicable;
  * usage metadata.

* Do not use `Outcome(tag=...)` for feedforward operations.

* Do not parse feedforward operation results with outcome JSON parser.

* Operation retry default: `retry=3`.

* Retry on:

  * transport failure;
  * malformed value;
  * schema validation failure;
  * invalid classification choice;
  * empty response when non-empty required.

---

## 27. Deterministic operation replay

* No user-provided `key=`.

* Runtime generates deterministic keys.

* Fingerprint includes:

  * workflow name;
  * topology hash;
  * source hash if available;
  * current step name;
  * operation kind;
  * callsite identity;
  * prompt hash;
  * input fingerprint;
  * return schema hash;
  * choices hash for `classify`;
  * session slot;
  * work item/scope coordinate;
  * occurrence index as final tie-breaker.

* On replay:

  * matching fingerprint → return recorded value;
  * mismatch → fail loudly or require explicit migration;
  * do not silently replay stale operation values.

* Store operation events in run folder.

* Include operation values in checkpoint/resume payloads.

---

## 28. State model

* Use explicit descriptors as public state model.

```python
class MyWorkflow(Workflow):
    attempts = StateVar(0)
    approved = StateVar(False)
    max_attempts = Param(3)
```

* `StateVar`:

  * mutable;
  * checkpointed;
  * available as `ctx.state.<name>`;
  * available in prompts as `{state.<name>}`.

* `Param`:

  * immutable run parameter;
  * available as `ctx.params.<name>`;
  * available in prompts as `{params.<name>}`.

* Support factories:

```python
StateVar(default_factory=list)
StateVar(default_factory=dict)
```

* Avoid shared mutable defaults.

* Remove public special handling for:

```python
class State(BaseModel): ...
class Parameters(BaseModel): ...
```

unless Codex identifies a hard functional dependency. If retained internally during migration, do not document it as public authoring style.

---

## 29. Step state

* Any step can declare step-local state.

```python
review = produce_verify_step(
    producer_prompt=Prompt.file("prompts/revise.md"),
    verifier_prompt=Prompt.file("prompts/check.md"),
    state={
        "attempts": StateVar(0),
        "last_route": StateVar[str | None](None),
    },
)
```

* Current step hook access:

```python
ctx.step_state.attempts += 1
```

* Cross-step access:

```python
ctx.steps.review.state.attempts
```

or:

```python
ctx.step_state_for("review").attempts
```

* Prompt access:

```text
{review.state.attempts}
```

* Step state is checkpointed.

---

## 30. Item and step-item state

* Static worklist item state:

```python
ctx.item_state.status = "in_progress"
```

* Step-item state:

```python
ctx.step_item_state.attempts += 1
```

* Prompt refs:

```text
{item.state.status}
{review.item_state.attempts}
```

* Scope identity includes:

  * run id;
  * worklist name;
  * item id;
  * step name for step-item state.

---

## 31. Context API

* Public `ctx` should expose:

```python
ctx.state
ctx.step_state
ctx.item_state
ctx.step_item_state
ctx.steps

ctx.values
ctx.artifacts

ctx.input
ctx.params

ctx.run
ctx.workflow
ctx.session
ctx.meta

ctx.route
ctx.outcome

ctx.read(...)
ctx.write(...)
ctx.read_json(...)
ctx.write_json(...)

ctx.reset_global_session()
ctx.set_global_session(...)
ctx.open_session(...)
```

* Artifact helper writes should be atomic where practical.
* `ctx.route` is available after route selection.
* `ctx.outcome` is available in verifier/agentic outcome hooks.
* `ctx.values` stores feedforward operation step values.

---

## 32. Global session

* Workflow has a global session.

```python
class MyWorkflow(Workflow):
    global_session = Session(open=True)
```

* If omitted, compiler injects an implicit global session:

```python
global_session = Session(open=True)
```

* Default slot name should be `"global"`, not `"default"`.

* Any provider-backed `step(...)` or `produce_verify_step(...)` phase without explicit `session` uses the global session.

* `produce_verify_step`:

  * producer phase uses `session` or global session;
  * verifier phase uses `verifier_session` if set, otherwise same session as producer/global.

* Explicit override:

```python
step(..., session="investigation")
produce_verify_step(..., verifier_session=Session.fresh())
```

* `open=True` means lazy-open on first provider use.

* Do not eagerly create provider sessions at run start unless required by provider backend.

* Context helpers:

```python
ctx.reset_global_session()
ctx.set_global_session(...)
```

* Session changes must be checkpointed and trace-recorded.

---

## 33. Worklists

* Common public worklist model is static list iteration.

```python
items = Worklist.from_param("articles")
```

or:

```python
items = Worklist.from_list([...])
```

* Step scope:

```python
review = produce_verify_step(
    scope=items,
    producer_prompt=Prompt.file("prompts/process_item.md"),
    verifier_prompt=Prompt.file("prompts/verify_item.md"),
    producer_writes=[Md("summary", required=True)],
)
```

* Scoped artifact paths include item coordinate.
* Advanced mutable board/worklist machinery can remain internal or in an advanced module if still functionally required.
* Do not expose heavy `Selector`/board mutation APIs in canonical public authoring surface.

---

## 34. Provider request/response contracts

* Provider turn kinds should use canonical names:

  * `"step"`
  * `"producer"`
  * `"verifier"`
  * `"operation"`

* Remove `"llm"` as a route-bearing provider turn kind if it refers to an agentic step.

* Use `"operation"` for feedforward `llm()`/`classify()`.

* Producer request fields:

  * `step_name`
  * `producer_prompt`
  * `context`
  * `readable_artifacts`
  * `required_artifacts`
  * `writable_artifacts`
  * `session`
  * `attempt`
  * `max_attempts`
  * `retry_feedback`

* Verifier request fields:

  * `step_name`
  * `verifier_prompt`
  * `context`
  * `readable_artifacts`
  * `required_artifacts`
  * `writable_artifacts`
  * `available_routes`
  * `route_summaries`
  * `route_required_writes`
  * `session`
  * `attempt`
  * `max_attempts`
  * `retry_feedback`
  * `producer_raw_output` only if needed for telemetry or optional renderer context.

* Remove or rename:

  * `raw_output` on verifier request → `producer_raw_output`
  * `route_infos` → route metadata from `Route`
  * `route_required_outputs` → `route_required_writes`

* Provider rendering must say:

  * “writable artifacts” or “declared artifacts this phase may write”;
  * “required writes for this route”;
  * not “outputs.”

---

## 35. Provider retry

* Retry policy default: `retry=3`.

* Applies to:

  * malformed outcome JSON;
  * illegal route;
  * invalid question payload;
  * missing reason for `blocked`/`failed`;
  * missing required write;
  * invalid required write;
  * provider transport failure.

* Retry feedback must use canonical names:

  * required writes;
  * routes;
  * writable artifacts;
  * `FINISH`, not `SUCCESS`.

* Avoid mutating exception instances with private `_provider_retry_kind` fields if feasible.

* Prefer a structured exception type:

```python
ProviderContractError(
    kind="illegal_route",
    step_name=...,
    route=...,
    failure_context={...},
)
```

* If current code is too dependent on private exception attributes, migrate gradually, but final public/runtime trace should use structured failure context.

---

## 36. Compiler responsibilities

* Discover workflow class members in declaration order.
* Bind step names.
* Bind artifact names.
* Reject reserved artifact names.
* Bind artifact owner step.
* Assign qualified artifact names.
* Normalize public `writes`.
* Normalize `producer_writes` and `verifier_writes`.
* Resolve `requires`.
* Resolve `verifier_requires`.
* Parse prompt references.
* Infer reads from qualified prompt refs.
* Resolve route targets.
* Normalize route shorthands into `Route`.
* Inject default routes.
* Inject control routes if enabled.
* Resolve `SELF`.
* Normalize terminals.
* Validate route tags.
* Validate duplicate step names.
* Validate duplicate artifact names.
* Validate route-required writes.
* Validate hook callability.
* Validate state declarations.
* Validate session references.
* Validate topology reachability.
* Generate topology artifacts.
* Produce immutable compiled workflow metadata.

---

## 37. Compiled model canonical fields

* `CompiledStep` should use:

```python
name
kind
session_name
scope_name

reads
requires
writes

available_routes
routes

retry_policy

prompt                 # for step(...)
producer_prompt         # for produce_verify_step
verifier_prompt         # for produce_verify_step

producer_reads
producer_requires
producer_writes

verifier_reads
verifier_requires
verifier_writes

state_fields
hooks
```

* Remove:

  * `produces`
  * `outputs`
  * `required_outputs`
  * `route_infos`
  * `do_prompt`
  * `review_prompt`
  * `system_handler` naming if public/compiled visible; use `python_handler`.

* `CompiledRoute` should use:

```python
source_step
tag
target
summary
required_writes
handoff
on_taken
```

* Remove:

  * `effects`
  * `required_outputs`

---

## 38. Runtime lifecycle for plain `step(...)`

```text
1. Build context
2. Validate requires
3. Run before hook
4. Run agentic harness step
5. Parse outcome
6. Validate route tag/control payload
7. Run after hook
8. Run on_route hook
9. Run route-specific on_taken hook
10. Validate selected-route required_writes
11. Checkpoint state/session/artifact metadata
12. Transition
```

---

## 39. Runtime lifecycle for `python_step(...)`

```text
1. Build context
2. Validate requires
3. Run before hook
4. Execute Python handler
5. Normalize handler result to Event
6. Validate route tag/control payload
7. Run after hook
8. Run on_route hook
9. Run route-specific on_taken hook
10. Validate selected-route required_writes
11. Checkpoint
12. Transition
```

---

## 40. Runtime lifecycle for operation step

```text
1. Build context
2. Validate requires
3. Resolve prompt
4. Execute/replay operation
5. Store value in ctx.values / checkpoint values
6. Emit operation events
7. Route "done" to next or FINISH
8. Checkpoint
```

* No route hooks by default unless operation step supports them explicitly.
* No control routes.

---

## 41. Runtime engine cleanup

* Add new authoring model by lowering into compiled FSM first.

* Do not rewrite the entire engine before canonical names are stable.

* Then refactor engine into modules:

  * FSM loop;
  * provider turn execution;
  * operation execution/replay;
  * hook execution;
  * artifact validation;
  * session selection;
  * checkpoint persistence;
  * child workflow invocation.

* Remove old branches:

  * `if step.kind == "pair"` → use `"produce_verify"`.
  * `if step.kind == "llm"` for route-bearing agentic step → use `"step"`.
  * `if step.kind == "system"` → use `"python"`.

---

## 42. Topology artifacts

* Always write/copy compiled topology to run folder.

* Try workflow folder if writable.

* Fallback to cache if source package is read-only.

* Do not fail only because source package is read-only.

* Generate:

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

* Use canonical names only:

  * `FINISH`
  * `produce_verify`
  * `producer_prompt`
  * `verifier_prompt`
  * `producer_writes`
  * `verifier_writes`
  * `required_writes`
  * `writes`
  * `python`

* Do not include:

  * `SUCCESS`
  * `do_review`
  * `review_step`
  * `do_prompt`
  * `review_prompt`
  * `review_writes`
  * `required_outputs`
  * `produces`
  * `RouteInfo`

---

## 43. Topology hash and resume safety

* Compiled workflow gets stable topology hash.

* Run metadata records:

  * workflow name;
  * topology hash;
  * source hash if available;
  * compile timestamp;
  * entry step;
  * terminals;
  * topology artifact paths.

* Resume:

  * resume against saved compiled topology;
  * or fail clearly if source topology changed and no explicit migration requested.

* Never silently resume against a different graph.

---

## 44. Child workflows

* Keep `workflow_step(...)`.
* Public shape:

```python
workflow_step(
    SomeWorkflow,
    input=...,
    writes=[Json("child_result", ChildResult, required=True)],
    routes={
        "done": "next_step",
        "failed": FAIL,
    },
)
```

* Child result must use canonical terminal names.

* Mapping:

  * child `FINISH` → parent route `"done"` by default;
  * child `PAUSE` question → parent `"question"` if supported;
  * child `PAUSE` non-question → parent `"blocked"` if supported;
  * child `FAIL` → parent `"failed"`.

* Do not refer to child terminal `SUCCESS`.

---

## 45. Concurrency

* Parent FSM remains sequential.

* No top-level parallel FSM steps in this version.

* Inter-run concurrency:

  * per-run context;
  * per-run checkpoint store;
  * per-run session store;
  * no module-level mutable step/session counters;
  * file locks for shared workspace/task state;
  * single-writer or locked event logs.

* Intra-run parallelism:

  * allowed inside `python_step`;
  * parallel bodies return values;
  * parent merges after join;
  * no unsynchronized shared state mutation in parallel bodies.

* Future helper:

```python
parallel(tasks, concurrency=5, failure="fail_fast")
```

---

## 46. Remove module-level counters

* Remove:

  * `_STEP_COUNTER = count()`
  * `_SESSION_COUNTER = count()`

* Ordering should come from:

  * class namespace declaration order;
  * explicit step name;
  * compiler discovery order.

* Session ordering should be deterministic from workflow declaration order.

---

## 47. Optimizer package separation

* Keep `autoloop_optimizer` as the location for optimizer/application-specific code.

* Remove duplicate optimizer modules from `stdlib`.

* Do not keep both active public surfaces.

* Core `stdlib` should contain only generic workflow helpers:

  * JSON artifact helpers;
  * validation helpers;
  * generic lifecycle helpers;
  * maybe simple prompt utilities.

* Remove or relocate from core `stdlib`:

  * optimization scoring;
  * candidate surfaces;
  * company snapshots;
  * diagnostics;
  * portfolio analysis;
  * recursive improvement workflows;
  * route info helpers.

* The implementation already created an `autoloop_optimizer` package, but the old `stdlib` tree still contains overlapping optimizer/application modules; finish the separation so there is a single canonical location. 

---

## 48. Packaging cleanup

* Remove dual import shims such as package aliasing between `core` and `autoloop_v3.core` if possible.
* Use one package import path.
* Avoid repo-root import fallback unless there is a functional CLI packaging reason.
* Public code should import from:

```python
import autoloop
```

or internal relative imports.

* Do not expose internal package layout as public API.

---

## 49. Schema registry

* Centralize schema IDs in one module:

```python
core/schema_registry.py
```

* Avoid scattering strings like:

```text
autoloop.runtime_trace/v1
autoloop.workflow_optimization.trace_corpus/v1
```

* Provide:

  * current schema constants;
  * migration hooks;
  * validation helpers.

---

## 50. Git tracking

* Git tracking is runtime policy.
* Do not declare git tracking on workflows.
* Public runtime options:

```python
Runtime(git_tracking=False)
Runtime(git_tracking="per_run")
Runtime(git_tracking="per_step")
```

* Avoid duplicate workflow extension + runtime tracker systems.
* If current extension architecture remains, runtime should own git tracking and workflow declarations should not.

---

## 51. Static graph

* Static graph generation consumes compiled topology.

* It must use canonical fields:

  * `FINISH`
  * `produce_verify`
  * `producer_prompt`
  * `verifier_prompt`
  * `writes`
  * `producer_writes`
  * `verifier_writes`
  * `required_writes`
  * route hooks.

* It must not emit:

  * `SUCCESS`
  * `produces`
  * `required_outputs`
  * `RouteInfo`
  * `do_prompt`
  * `review_prompt`.

---

## 52. Observability and audit trail

* Preserve:

  * `run.json`
  * `events.jsonl`
  * `trace.jsonl`
  * `checkpoint.json`
  * raw provider logs
  * compiled topology copy
  * artifact contracts
  * session metadata
  * hook events
  * operation replay records.

* Run result should include:

  * terminal;
  * last step;
  * last route;
  * state;
  * values;
  * output;
  * output validation status;
  * checkpoint if paused/failed;
  * topology hash;
  * final artifact paths.

* Use canonical names in all payloads.

---

## 53. Testing requirements

* Public API absence tests:

  * importing `SUCCESS` from `autoloop` fails;
  * importing `RouteInfo` from `autoloop` fails;
  * importing `StrictWorkflow` from `autoloop` fails;
  * importing `chain` from `autoloop` fails;
  * importing `review_step` from `autoloop` fails;
  * importing `do_review_step` from `autoloop` fails;
  * importing `system_step` from `autoloop` fails;
  * importing `AfterHookResult` from `autoloop` fails.

* Public API presence tests:

  * `Workflow`
  * `step`
  * `produce_verify_step`
  * `python_step`
  * `workflow_step`
  * `llm`
  * `classify`
  * `Prompt`
  * `Md`, `Json`, `Text`, `Raw`
  * `Route`
  * `Session`
  * `Continuity`
  * `StateVar`
  * `Param`
  * `Worklist`
  * `FINISH`, `PAUSE`, `FAIL`, `SELF`.

* Terminal tests:

  * terminal is `FINISH`;
  * no runtime result returns `SUCCESS`;
  * child workflow mapping uses `FINISH`;
  * topology uses `FINISH`.

* Route tests:

  * `Route.to(..., required_writes=None)`;
  * `Route.to(..., required_writes=[])`;
  * `Route.to(..., on_taken=...)`;
  * no `required_outputs`;
  * no `RouteInfo`.

* `produce_verify_step` tests:

  * accepts `producer_prompt`;
  * accepts `verifier_prompt`;
  * rejects `do`;
  * rejects `review`;
  * rejects `do_prompt`;
  * rejects `review_prompt`;
  * rejects `review_writes`;
  * rejects `review_requires`;
  * supports `producer_writes`;
  * supports `verifier_writes`;
  * supports `verifier_requires`;
  * supports `verifier_session`;
  * default routes are correct;
  * custom routes are correct;
  * route required writes validate across both producer and verifier writes;
  * lifecycle hook order is correct.

* `step` tests:

  * lowercase `"done"` default;
  * custom semantic routes omit `"done"`;
  * control routes injection;
  * `control_routes=False`.

* Prompt reference tests:

  * `{previous.artifact}` infers reads;
  * `{self.artifact}` resolves;
  * `{step.value}` resolves operation value;
  * `{step.state.field}` resolves step state;
  * unknown placeholder errors;
  * reserved pseudo-field artifact names fail.

* Hook tests:

  * hook mutates state;
  * hook mutates step state;
  * hook resets global session;
  * hook heals artifact before final validation;
  * hook cannot redirect route;
  * hook failure emits trace/checkpoint.

* Operation tests:

  * `llm()` standalone;
  * `classify()` standalone;
  * `llm.step(...)`;
  * `classify.step(...)`;
  * retries;
  * replay;
  * fingerprint mismatch failure;
  * operation node kind is `"operation"`.

* Session tests:

  * implicit global session exists;
  * default provider-backed step uses global session;
  * producer/verifier share global session unless `verifier_session` is set;
  * `ctx.reset_global_session()` works;
  * session state survives checkpoint/resume.

* Strictness grep tests:

  * no `SUCCESS` outside migration fixtures;
  * no `do_review_step`;
  * no `review_step`;
  * no `RouteInfo`;
  * no `required_outputs`;
  * no `do_prompt`;
  * no `review_prompt`;
  * no public `produces`;
  * no `system_step`.

---

## 54. Canonical example

```python
from pydantic import BaseModel

from autoloop import (
    Workflow,
    Prompt,
    Md,
    Json,
    Route,
    StateVar,
    Param,
    Session,
    FINISH,
    SELF,
    step,
    produce_verify_step,
    python_step,
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

    max_legal_attempts = Param(3)

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

    legal_review = produce_verify_step(
        producer_prompt=Prompt.file("prompts/legal_producer.md"),
        verifier_prompt=Prompt.file("prompts/legal_verifier.md"),

        requires=[prepare.publish_package],

        producer_writes=[
            Md("legal_analysis", required=False),
        ],

        verifier_writes=[
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
                SELF,
                required_writes=["legal_review_report"],
                on_taken=record_rework,
            ),
            "rejected": Route.to(
                FINISH,
                required_writes=["legal_review_report", "decision"],
            ),
        },
    )

    @python_step(
        routes={
            "continue": "legal_review",
            "exhausted": FINISH,
        },
    )
    def legal_rework_gate(ctx):
        if ctx.steps.legal_review.state.attempts >= ctx.params.max_legal_attempts:
            return "exhausted"
        return "continue"
```

---

## 55. Canonical generated topology example

```json
{
  "workflow_name": "article_publication",
  "entry": "prepare",
  "terminals": ["FINISH", "PAUSE", "FAIL"],
  "steps": [
    {
      "name": "prepare",
      "kind": "step",
      "prompt": "prompts/prepare_publication.md",
      "writes": [
        "prepare.publish_package",
        "prepare.legal_risk_notes",
        "prepare.rejection_reason"
      ],
      "routes": {
        "ready_to_publish": {
          "target": "FINISH",
          "required_writes": ["prepare.publish_package"]
        },
        "needs_legal_review": {
          "target": "legal_review",
          "required_writes": [
            "prepare.publish_package",
            "prepare.legal_risk_notes"
          ]
        },
        "rejected": {
          "target": "FINISH",
          "required_writes": ["prepare.rejection_reason"]
        }
      }
    },
    {
      "name": "legal_review",
      "kind": "produce_verify",
      "producer_prompt": "prompts/legal_producer.md",
      "verifier_prompt": "prompts/legal_verifier.md",
      "producer_writes": ["legal_review.legal_analysis"],
      "verifier_writes": [
        "legal_review.legal_review_report",
        "legal_review.decision"
      ],
      "routes": {
        "approved": {
          "target": "FINISH",
          "required_writes": [
            "legal_review.legal_analysis",
            "legal_review.legal_review_report",
            "legal_review.decision"
          ]
        },
        "needs_rework": {
          "target": "legal_review",
          "required_writes": ["legal_review.legal_review_report"],
          "on_taken": "record_rework"
        },
        "rejected": {
          "target": "FINISH",
          "required_writes": [
            "legal_review.legal_review_report",
            "legal_review.decision"
          ]
        }
      }
    }
  ]
}
```

---

## 56. Banned-name cleanup checklist for Codex

* Remove or rename all public/internal occurrences unless clearly inside an old-run migration test fixture:

```text
SUCCESS
RouteInfo
StrictWorkflow
chain
flow
transitions
review_step
do_review_step
system_step
AfterHookResult

do_prompt
review_prompt
review_writes
review_requires
review_session

out
outputs
produces
required_outputs
route_infos
route_summaries

PairStep
LLMStep          # if it means route-bearing harness step
SystemStep
```

* Replace with:

```text
FINISH
Route
Workflow
step-local routes
produce_verify_step
python_step

producer_prompt
verifier_prompt
producer_writes
verifier_writes
verifier_requires
verifier_session

writes
required_writes
PythonStep
ProduceVerifyStep
OperationStep
```

---

## 57. Implementation order

* First pass:

  * Rename public exports.
  * Delete aliases.
  * Make `FINISH` canonical.
  * Update tests to fail old names.
  * Rename `do_review_step` → `produce_verify_step`.
  * Rename arguments and fields to `producer_prompt` / `verifier_prompt`.
  * Rename `review_writes` → `verifier_writes`.
  * Rename `review_requires` → `verifier_requires`.
  * Rename `system_step` → `python_step`.
  * Collapse `RouteInfo` into `Route`.

* Second pass:

  * Rename compiled fields:

    * `produces` → `writes`;
    * `required_outputs` → `required_writes`;
    * `pair` → `produce_verify`;
    * `system` → `python`;
    * route-bearing `llm` step → `step` or `agent`.
  * Update provider contracts.
  * Update topology artifacts.
  * Update static graph.

* Third pass:

  * Remove global transitions/chain/flow.
  * Make step-local routes the only topology source.
  * Use first-declared step as default entry.
  * Generate topology from step routes and default routes.

* Fourth pass:

  * Finish state/session cleanup.
  * Add `StateVar`, `Param`, step state, global session.
  * Remove old state return conventions from public tests/docs.

* Fifth pass:

  * Finish operation path.
  * Ensure `llm`/`classify` are feedforward operations.
  * Ensure operation nodes compile as `"operation"`.

* Sixth pass:

  * Finish optimizer separation.
  * Remove duplicate `stdlib` application modules.

---

## 58. Final acceptance criteria

* `from autoloop import SUCCESS` fails.
* `from autoloop import produce_verify_step` works.
* `from autoloop import do_review_step` fails.
* `from autoloop import review_step` fails.
* `from autoloop import system_step` fails.
* `from autoloop import RouteInfo` fails.
* `from autoloop import StrictWorkflow` fails.
* New workflows can be authored using only the canonical public API.
* Topology artifacts contain no legacy names.
* Run results return `FINISH`, not `SUCCESS`.
* Provider contracts use `producer_prompt` and `verifier_prompt`.
* There is no `do_prompt` or `review_prompt`.
* There is no public route-effect DSL.
* Hooks mutate state/session/artifacts through `ctx`.
* `llm` and `classify` are feedforward operations, not route-bearing steps.
* The runtime still preserves the framework’s core value: long-running agentic SOP execution with artifacts, routes, sessions, verification, checkpoints, resume, and audit trail.

Below is the updated standalone spec patch. It replaces the prior `StateVar` / `Param` sections with a standard Pydantic model approach.

---

# State / params model update

## Replace descriptor-based state with Pydantic model state

* Remove `StateVar` from the canonical public API.

* Do not use descriptor-based state declarations as the main authoring model.

* Workflow and step state should be declared with normal Pydantic models using standard Python type annotations.

* Remove this style from the canonical spec:

```python
attempts = StateVar(0)
approved = StateVar(False)
max_attempts = Param(3)
```

* Use this style instead:

```python
from pydantic import BaseModel, Field

class WorkflowState(BaseModel):
    approved: bool = False

class WorkflowParams(BaseModel):
    max_attempts: int = 3
```

---

## Canonical public API update

* Public `autoloop.__init__` should export:

```python
Workflow

step
produce_verify_step
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
Worklist

Event
Outcome

FINISH
PAUSE
FAIL
SELF
```

* Remove from canonical public API:

```python
StateVar
Param
```

* If Codex finds an internal migration need for `StateVar` or `Param`, keep them private or move them to an internal compatibility module.
* Do not document them.
* Do not use them in examples.
* Do not expose them from `autoloop.__init__`.

---

## Workflow-level state

* Workflow state is declared through a Pydantic model assigned to `State`.

```python
from pydantic import BaseModel

class ArticlePublicationState(BaseModel):
    approved: bool = False
    last_terminal_reason: str | None = None

class ArticlePublication(Workflow):
    State = ArticlePublicationState
```

* If a workflow does not declare `State`, the compiler should use an empty state model.

```python
class EmptyState(BaseModel):
    pass
```

* Runtime access:

```python
ctx.state.approved = True
ctx.state.last_terminal_reason = "Rejected by legal verifier."
```

* Prompt access:

```text
{state.approved}
{state.last_terminal_reason}
```

* Workflow state must be:

  * instantiated fresh per run;
  * checkpointed;
  * restored on resume;
  * deep-copied for hook rollback/snapshotting.

---

## Workflow params

* Replace descriptor-style `Param(...)` with a Pydantic params model.

```python
class ArticlePublicationParams(BaseModel):
    max_legal_attempts: int = 3
    require_legal_review: bool = True

class ArticlePublication(Workflow):
    Params = ArticlePublicationParams
```

* Runtime access:

```python
ctx.params.max_legal_attempts
```

* Prompt access:

```text
{params.max_legal_attempts}
```

* If a workflow does not declare `Params`, the compiler should use an empty params model.

```python
class EmptyParams(BaseModel):
    pass
```

* Runtime parameter overrides should be validated through the `Params` model.

* Use the single canonical class name:

```python
Params
```

* Do not support both `Params` and `Parameters` in the final public API.
* If old code uses `Parameters`, fail with a clear compile-time error:

```text
Use Params, not Parameters.
```

---

## Step-level state

* Step-local state is declared by passing a Pydantic model class to the step declaration.

```python
class LegalReviewState(BaseModel):
    attempts: int = 0
    last_route: str | None = None
    last_reason: str | None = None

legal_review = produce_verify_step(
    producer_prompt=Prompt.file("prompts/legal_producer.md"),
    verifier_prompt=Prompt.file("prompts/legal_verifier.md"),
    state=LegalReviewState,
    ...
)
```

* Do not use:

```python
state={
    "attempts": StateVar(0),
    "last_route": StateVar[str | None](None),
}
```

* Do not use descriptor dictionaries as the canonical model.

* Runtime access for the current step:

```python
ctx.step_state.attempts += 1
ctx.step_state.last_route = ctx.route.tag
ctx.step_state.last_reason = ctx.outcome.reason
```

* Cross-step access:

```python
ctx.steps.legal_review.state.attempts
```

or:

```python
ctx.step_state_for("legal_review").attempts
```

* Prompt access:

```text
{legal_review.state.attempts}
{legal_review.state.last_route}
```

* Step state must be:

  * instantiated fresh per run;
  * scoped to the step;
  * checkpointed;
  * restored on resume;
  * safe across repeated visits to the same step.

---

## Mutable defaults

* Use Pydantic `Field(default_factory=...)` for mutable defaults.

```python
from pydantic import BaseModel, Field

class ReviewState(BaseModel):
    attempts: int = 0
    previous_routes: list[str] = Field(default_factory=list)
    notes_by_route: dict[str, str] = Field(default_factory=dict)
```

* Codex should not implement special mutable-default logic in Autoloop for state fields.
* Let Pydantic handle default factories.

---

## Item and step-item state

* If item-scoped state is implemented, use the same Pydantic model pattern.

```python
class ArticleItemState(BaseModel):
    status: str = "pending"
    attempts: int = 0

articles = Worklist.from_param(
    "articles",
    item_state=ArticleItemState,
)
```

* Step-item state should also use a Pydantic model class.

```python
class PerItemLegalReviewState(BaseModel):
    attempts: int = 0
    last_route: str | None = None

legal_review = produce_verify_step(
    ...,
    scope=articles,
    item_state=PerItemLegalReviewState,
)
```

* Runtime access:

```python
ctx.item_state.status = "in_progress"
ctx.step_item_state.attempts += 1
```

* Prompt access:

```text
{item.state.status}
{legal_review.item_state.attempts}
```

* If item/step-item state is not implemented in the current pass, leave the spec hooks in place but do not expose half-working APIs.

---

## State mutation rules

* State mutation happens through `ctx` in hooks or Python steps.

```python
def record_rework(ctx):
    ctx.step_state.attempts += 1
    ctx.step_state.last_route = ctx.route.tag
    ctx.step_state.last_reason = ctx.outcome.reason
```

* Hooks should normally return `None`.

```python
Route.to(SELF, on_taken=record_rework)
```

* Do not return a new state model from hooks as the canonical path.
* Do not use tuple return conventions such as:

```python
return state, "done"
```

* Public `python_step` return convention remains:

```python
None      -> "done"
str       -> route tag
Event     -> explicit event
```

* State is mutated directly through the context.

---

## Why not infer state from plain class attributes?

* Do not infer mutable state from arbitrary annotated class attributes.

Reject or ignore this as state:

```python
class Review(Workflow):
    attempts: int = 0
    max_attempts: int = 3
```

* This is ambiguous:

  * mutable state?
  * parameter?
  * constant?
  * compiler config?
  * class metadata?

* Require explicit namespaces instead:

```python
class ReviewState(BaseModel):
    attempts: int = 0

class ReviewParams(BaseModel):
    max_attempts: int = 3

class Review(Workflow):
    State = ReviewState
    Params = ReviewParams
```

This keeps the authoring model standard while avoiding implicit compiler magic.

---

## Compiler updates

* Remove descriptor discovery for `StateVar`.
* Remove descriptor discovery for `Param`.
* Add validation for workflow state:

```text
If Workflow.State is declared:
    it must be a Pydantic BaseModel subclass.
    it must be instantiable with no arguments.
Else:
    use EmptyState.
```

* Add validation for workflow params:

```text
If Workflow.Params is declared:
    it must be a Pydantic BaseModel subclass.
Else:
    use EmptyParams.
```

* Add validation for step state:

```text
If step.state is declared:
    it must be a Pydantic BaseModel subclass.
    it must be instantiable with no arguments.
Else:
    use EmptyStepState.
```

* Add validation for scoped item state if implemented:

```text
If Worklist.item_state is declared:
    it must be a Pydantic BaseModel subclass.

If step.item_state is declared:
    it must be a Pydantic BaseModel subclass.
```

* Compiler output should include state model metadata:

```json
{
  "state_contracts": {
    "workflow_state": {
      "model": "ArticlePublicationState",
      "fields": {
        "approved": "bool",
        "last_terminal_reason": "str | None"
      }
    },
    "workflow_params": {
      "model": "ArticlePublicationParams",
      "fields": {
        "max_legal_attempts": "int",
        "require_legal_review": "bool"
      }
    },
    "step_states": {
      "legal_review": {
        "model": "LegalReviewState",
        "fields": {
          "attempts": "int",
          "last_route": "str | None",
          "last_reason": "str | None"
        }
      }
    }
  }
}
```

* Do not emit `StateVar` or `Param` in topology artifacts.

---

## Checkpoint and resume updates

* Checkpoint payload should store:

  * workflow state;
  * step states;
  * item states, if implemented;
  * step-item states, if implemented;
  * params snapshot or validated params payload.

* Store state using Pydantic-compatible serialization:

```python
model_dump(mode="json")
```

or equivalent filesystem-store encoding.

* Restore using:

```python
StateModel.model_validate(payload)
```

* Hook rollback should snapshot state using deep copies:

```python
before = state.model_copy(deep=True)
```

* If a hook fails:

  * restore workflow state snapshot;
  * restore step state snapshot;
  * restore item/step-item state snapshots if applicable;
  * checkpoint failure context.

---

## Prompt reference updates

* Keep prompt references unchanged:

```text
{state.field}
{params.field}
{step_name.state.field}
{item.state.field}
{step_name.item_state.field}
```

* These now resolve against Pydantic model instances, not descriptor-backed state containers.

* Unknown field should fail clearly:

```text
Unknown state field: legal_review.state.attemps
Did you mean: legal_review.state.attempts?
```

Typo suggestions are optional but useful.

---

## Public examples update

* Replace previous example using `StateVar` and `Param`:

```python
class ArticlePublication(Workflow):
    max_legal_attempts = Param(3)

    legal_review = produce_verify_step(
        ...,
        state={
            "attempts": StateVar(0),
            "last_route": StateVar[str | None](None),
        },
    )
```

* With this:

```python
from pydantic import BaseModel
from autoloop import (
    Workflow,
    Prompt,
    Md,
    Json,
    Route,
    Session,
    FINISH,
    SELF,
    step,
    produce_verify_step,
)

class Decision(BaseModel):
    approved: bool
    reason: str

class ArticlePublicationParams(BaseModel):
    max_legal_attempts: int = 3

class ArticlePublicationState(BaseModel):
    approved: bool = False
    last_terminal_reason: str | None = None

class LegalReviewState(BaseModel):
    attempts: int = 0
    last_route: str | None = None
    last_reason: str | None = None

def record_rework(ctx):
    ctx.step_state.attempts += 1
    ctx.step_state.last_route = ctx.route.tag
    ctx.step_state.last_reason = ctx.outcome.reason

class ArticlePublication(Workflow):
    Params = ArticlePublicationParams
    State = ArticlePublicationState

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

    legal_review = produce_verify_step(
        producer_prompt=Prompt.file("prompts/legal_producer.md"),
        verifier_prompt=Prompt.file("prompts/legal_verifier.md"),

        requires=[prepare.publish_package],

        producer_writes=[
            Md("legal_analysis", required=False),
        ],

        verifier_writes=[
            Md("legal_review_report", required=True),
            Json("decision", Decision, required=False),
        ],

        state=LegalReviewState,

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
                SELF,
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

## Banned-name cleanup update

* Add these to the banned-name cleanup list for canonical public code:

```text
StateVar
Param
```

* Remove from canonical examples/tests/docs:

```text
StateVar(...)
Param(...)
state={ "x": StateVar(...) }
```

* Replace with:

```text
State = SomeBaseModel
Params = SomeBaseModel
state=SomeBaseModel
```

---

## Testing updates

* Add public API absence tests:

```python
with pytest.raises(ImportError):
    from autoloop import StateVar

with pytest.raises(ImportError):
    from autoloop import Param
```

* Add workflow state tests:

  * workflow with `State = MyState`;
  * state defaults instantiate correctly;
  * hook mutates `ctx.state`;
  * checkpoint/resume preserves `ctx.state`.

* Add params tests:

  * workflow with `Params = MyParams`;
  * runtime overrides validate through model;
  * invalid override fails clearly;
  * prompt `{params.field}` resolves.

* Add step state tests:

  * `produce_verify_step(..., state=MyStepState)`;
  * route hook mutates `ctx.step_state`;
  * repeated self-route preserves step state;
  * checkpoint/resume preserves step state.

* Add mutable default tests:

```python
class StepState(BaseModel):
    history: list[str] = Field(default_factory=list)
```

* two runs do not share the same list;

* two scoped items do not share the same list if item state is implemented.

* Add compile error tests:

  * `State` is not a `BaseModel` subclass;
  * `Params` is not a `BaseModel` subclass;
  * `step.state` is not a `BaseModel` subclass;
  * workflow declares `Parameters` instead of `Params`;
  * arbitrary annotated class fields are not treated as state.

---

## Final revised rule

```text
Use standard Python type annotations inside explicit Pydantic model namespaces.
Do not use descriptor objects for state.
Do not infer durable state from arbitrary class attributes.
```

This gives us the same compiler clarity that `StateVar` was trying to provide, but with a more standard, predictable, and LLM-friendly authoring model.
