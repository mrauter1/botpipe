Below is the revised standalone correction/spec list for the framework implementation. It incorporates the review and the KISS artifact/worklist adjustments. 

## Framework correction specs

* **Remove dual-role artifact ownership errors.**
  A workflow-level artifact may also be produced or updated by steps. Treat workflow-level visibility and step production as compatible metadata, not mutually exclusive roles.
  **Required changes:**

  * Remove the error that rejects artifacts that are both workflow-level and step-produced.
  * Remove `Artifact.managed(...)`.
  * Remove `ArtifactRole = Literal["managed"]`.
  * Remove `role=` from artifact constructors unless there is another concrete use.
  * Keep artifact inventory fields such as:

    ```python
    workflow_level: bool
    producer_steps: tuple[str, ...]
    ```

    but treat `producer_steps` as provenance, not ownership.
  * Keep diagnostics for genuinely ambiguous cases:

    * same public name with incompatible templates
    * same qualified name with different artifact objects
    * incompatible schemas
    * unresolved ambiguous artifact references
      **Acceptance tests:**
  * Same artifact object declared workflow-level and written by one step compiles.
  * Same artifact object declared workflow-level and written by multiple steps compiles.
  * Public artifact reference resolves to the canonical artifact name.
  * Different artifact objects with the same name but incompatible declarations fail clearly.
  * `Artifact.managed(...)` no longer exists.

* **Preserve canonical artifact names when workflow-level artifacts are produced.**
  If an artifact is workflow-level and step-produced, do not rebind it to a step-local qualified name such as `step_name.artifact_name`. Keep the workflow/public name canonical and record step producers separately.
  **Required changes:**

  * If `workflow_level=True`, keep `qualified_name` stable as the workflow-level/public name.
  * Register producing steps in `producer_steps`.
  * Provider contracts should show the same artifact identity regardless of whether it is read as workflow-level or produced by a step.
    **Acceptance tests:**
  * Workflow-level artifact written by `plan` still resolves as `artifact_name`, not only `plan.artifact_name`.
  * Route required writes can reference that artifact by public name.
  * Prompt/artifact references remain unambiguous.

* **Make rendered provider outcome `reason` optional.**
  Provider JSON parsing must match runtime behavior for direct `Outcome(...)` objects. `reason` should default to `""`; it should not be required for every route.
  **Required changes:**

  * Update provider outcome JSON parser so this is valid:

    ```json
    {"tag": "done"}
    ```
  * Default missing `reason` to `""`.
  * Keep `question` as the only built-in route with a special payload requirement.
  * When `tag == "question"`, require a non-empty top-level `question` string.
    **Acceptance tests:**
  * `{"tag":"done"}` parses successfully.
  * `{"tag":"failed"}` parses successfully when `failed` is an authored route.
  * `{"tag":"blocked"}` parses successfully when `blocked` is an authored route.
  * `{"tag":"question"}` fails.
  * `{"tag":"question","question":"What input is missing?"}` succeeds.
  * Fake provider and rendered provider have identical behavior for these cases.

* **Remove default provider-visible `blocked` and `failed`.**
  Providers should receive only authored domain routes plus policy-allowed `question`.
  **Required changes:**

  * Do not inject `blocked` by default.
  * Do not inject `failed` by default.
  * Do not inject `failed` into Python or child workflow steps by default.
  * Treat explicitly authored `blocked` and `failed` as ordinary route names.
  * Remove hidden non-empty-reason validation for route names `blocked` and `failed`.
    **Acceptance tests:**
  * Provider-facing step does not receive default `blocked`.
  * Provider-facing step does not receive default `failed`.
  * Python step does not receive default `failed`.
  * Child workflow step does not receive default `failed`.
  * Explicit authored `blocked` route remains legal.
  * Explicit authored `failed` route remains legal.
  * Authored `blocked`/`failed` routes do not require reason unless a declared schema requires it.

* **Expose default `question` only when interaction policy allows it.**
  The provider-visible `question` route should be policy-gated at provider-contract construction time, not treated as an always-visible compile-time route.
  **Required changes:**

  * Keep a runtime interaction policy:

    ```python
    RuntimeInteractionPolicy(allow_provider_questions=not full_auto)
    ```
  * Provider contracts include default `question` only when `allow_provider_questions=True`.
  * Full-auto provider contracts omit default `question`.
  * If provider returns `question` when not visible, it should be handled as an illegal route through existing retry/failure logic.
    **Acceptance tests:**
  * Interactive producer/verifier/single LLM contracts include `question`.
  * Full-auto producer/verifier/single LLM contracts omit `question`.
  * No provider contract includes default `blocked` or `failed`.
  * Explicit authored routes remain visible according to their own `provider_visible` metadata.

* **Keep child workflow mapped `blocked`/`failed` explicit.**
  Child workflow terminal mapping must not rely on implicit framework routes.
  **Required changes:**

  * If a child workflow returns failure and maps to `failed`, the child step must explicitly declare `failed`.
  * If a child workflow awaits input without a concrete question and maps to `blocked`, the child step must explicitly declare `blocked`.
  * Error messages must include:

    * child step name
    * child terminal
    * mapped route
    * declared routes
    * recommended fix
      **Acceptance tests:**
  * Child failure maps to `failed` when declared.
  * Child failure without declared `failed` fails clearly.
  * Child awaiting input with question maps to `question` when policy allows.
  * Child awaiting input without question maps to `blocked` only when declared.
  * Missing `blocked` route yields a clear runtime error.

* **Make worklist contents lazy, not declaration-time data.**
  Worklist identity may be declared statically so topology can be validated, but the item collection must be opened, loaded, selected, and validated only at runtime first use.
  **Required changes:**

  * Static validation should check:

    * worklist name
    * selector declaration
    * item-state model
    * scoped steps reference declared worklists
  * Static validation must not:

    * read backing artifacts
    * load source data
    * validate item payloads
    * require non-empty selections
  * Runtime materialization happens when:

    * a scoped step is reached
    * `ctx.selection(...)` is called
    * `ctx.current(...)` is called
    * `ctx.item` is needed
    * artifact template needs `{item...}`
    * prompt render needs `{item...}` or `{worklist...}`
    * work-item session continuity needs current item
      **Acceptance tests:**
  * Workflow with missing artifact-backed worklist source compiles.
  * Fresh run does not load unused worklists.
  * Non-scoped execution path can finish without materializing unused worklists.
  * First scoped step materializes the relevant worklist.
  * `ctx.selection("x")` materializes `x`.
  * `ctx.current("x")` materializes `x`.

* **Make missing-source behavior source-policy-driven.**
  A missing source is not always an error. Some sources are required external inputs; others are workflow-created boards and should scaffold at first use.
  **Required changes:**

  * Define source policy explicitly:

    ```text
    missing="error"      # default
    missing="scaffold"   # create initial backing data at first use
    ```
  * For artifact-backed worklist sources:

    * default missing behavior should be `error`
    * scaffold behavior should be opt-in
  * `ensure(...)` should create/scaffold only when the source policy says so.
  * Invalid source data should fail at first use, not at declaration time.
    **Acceptance tests:**
  * Missing source with `missing="error"` fails at first use.
  * Missing source with `missing="scaffold"` creates backing data at first use.
  * Scaffolded source is then loaded, validated, selected, and cached.
  * Invalid scaffold payload fails during lazy validation.
  * Unused missing source does not fail.

* **Clarify checkpointed worklist restore policy.**
  The implementation must choose and document one of two valid behaviors.
  **Preferred policy: strict lazy restore**

  * Restore checkpointed selections as snapshots.
  * Do not load backing sources at resume entry.
  * Reconcile/load source only when the restored selection is first used.
    **Alternative policy: validated restore**
  * Restore only checkpointed selections, not all declared worklists.
  * Reconcile checkpointed selections against backing sources immediately during resume.
  * Document this as intentional.
    **Acceptance tests for preferred strict lazy restore:**
  * Resume does not load checkpointed source immediately.
  * First access to restored selection loads/reconciles source.
  * Missing backing source fails at first access, not resume entry.
  * Unused checkpointed selections do not block unrelated resume paths.
  * Old checkpoints with missing/null worklist selections resume with empty lazy selection map.

* **Make work-item session continuity lazy.**
  Work-item session keys should resolve when a current item exists, not at declaration time.
  **Required changes:**

  * A session may declare work-item continuity for a named worklist.
  * Before resolving the session key, runtime must ensure the referenced worklist selection exists.
  * Use stable key:

    ```text
    <worklist_name>:<item_dir_key_or_id>
    ```
  * Prefer `dir_key` when available, otherwise use item ID.
  * Non-scoped steps may use work-item continuity only when a current item can be resolved.
    **Acceptance tests:**
  * Work-item continuity does not load source at compile time.
  * Scoped step materializes selection before session resolution.
  * Different items get different session keys.
  * Same item resumes same session key.
  * Missing current item fails clearly.

* **Resolve `item.state.<field>` at runtime or reject it at compile time.**
  Compile-time prompt validation and runtime rendering must agree.
  **Required changes:**

  * If `{item.state.foo}` is allowed in prompts, runtime rendering must resolve it from active `ctx.item_state.foo`.
  * If no active item exists, fail clearly.
  * If no item state exists, fail clearly.
  * If field is missing, fail clearly.
    **Acceptance tests:**
  * Scoped prompt with `{item.state.foo}` compiles when item-state field `foo` exists.
  * Runtime rendering resolves `{item.state.foo}`.
  * Missing active item fails with placeholder context.
  * Missing item-state field fails with placeholder context.
  * Existing `{item.id}`, `{item.title}`, `{item.status}`, `{item.dir_key}`, and `{item.payload...}` behavior remains unchanged.

* **Keep prompt placeholders and artifact-template placeholders separate.**
  Prompt placeholder validation and artifact path rendering are different surfaces and should have separate tests.
  **Required changes:**

  * Prompt validation should allow late-bound scoped context only where legal.
  * Artifact templates should resolve runtime item/worklist data only when active context exists.
  * Neither should silently substitute empty strings for required runtime item fields.
    **Acceptance tests:**
  * Prompt `{item.payload.foo}` compiles and renders for scoped step.
  * Artifact template `{item.dir_key}` resolves with active item.
  * Artifact template `{item.dir_key}` fails without active item.
  * Unknown worklist in prompt fails at compile time.
  * Missing runtime payload path fails at render time with clear placeholder context.

* **Narrow or explicitly document the public effects API.**
  The first effects surface should be worklist-focused unless the broader API is intentionally accepted.
  **Required changes if narrowing:**

  * Keep `WorklistEffect` public.
  * Remove or privatize generic `Effects`.
  * Remove public `Effects.event`.
  * Remove public `Effects.then(...)`.
  * Do not route `RequestInput`, `Goto`, or `Fail` through effect fields.
  * Hooks/Python steps should still return `Event`, route strings, `RequestInput`, `Goto`, or `Fail` directly through existing normalization.
    **Acceptance tests if narrowing:**
  * Returning `WorklistEffect.complete_current()` works.
  * Returning `WorklistEffect.advance_current(exhausted="done")` works.
  * Returning `Effects.then("done")` is not accepted as public API.
  * Exhausted route supports `str | Event | None`.
  * Runtime controls still work through direct return values.

* **If keeping broader `Effects`, document it as a hook-control API.**
  If the implementation keeps generic `Effects`, it must be specified and tested as a broader API, not an accidental extension.
  **Required tests if keeping it:**

  * `Effects.event` precedence is deterministic.
  * `Effects` with worklist mutation plus event behaves predictably.
  * `RequestInput`, `Goto`, and `Fail` inside effects behave identically to direct returns.
  * Checkpoint state is correct after effect mutation.
  * Route finalization records source hook/phase correctly.

* **Keep validation-step helper as routing/feedback sugar only.**
  The helper should not become a parallel validation subsystem.
  **Required changes:**

  * `validation_step(...)` should lower to a Python step.
  * It should standardize:

    * success route
    * repair route
    * feedback artifact writing
    * handoff text
    * validation runtime events
  * It should reuse existing artifact/schema/structured validation utilities.
    **Acceptance tests:**
  * Valid result routes to success.
  * Invalid result writes feedback and routes to repair.
  * Feedback includes message and details.
  * Exceptions route/fail according to declared failed behavior.
  * Feedback artifact is declared as a write.

* **Clean up route-summary defaults for `blocked` and `failed`.**
  Since `blocked` and `failed` are no longer default framework routes, fallback summaries should not describe them as reserved controls.
  **Required changes:**

  * Remove reserved-looking default summaries for `blocked` and `failed`.
  * If authors use those names without summaries, give generic authored-route summaries.
  * Keep runtime-control wording for `question`.
    **Acceptance tests:**
  * Unauthored `blocked` and `failed` do not appear in route metadata.
  * Authored `blocked` without summary gets generic summary.
  * Authored `failed` without summary gets generic summary.
  * Runtime-control `question` gets appropriate question/await-input summary.

* **Inspection must distinguish declared worklists from materialized selections.**
  Static graph and inspection should not imply lazy worklists are already loaded.
  **Required changes:**

  * Static graph shows declared worklist scopes without source validation.
  * Runtime inspection can show materialization state when available:

    * declared
    * unmaterialized
    * materialized
    * current item
    * selected item IDs
    * source descriptor
    * scaffold-capable or error-on-missing policy
      **Acceptance tests:**
  * Static graph renders with missing artifact-backed worklist source.
  * Inspection before first use marks worklist as unmaterialized.
  * Inspection after first use shows materialized selection metadata.

* **Inspection/static graph must distinguish authored routes from runtime controls.**
  Provider-visible routes now depend on interaction policy. Inspection should show that without polluting the authored graph.
  **Required changes:**

  * Expose authored routes separately from runtime-control routes.
  * Show provider-visible routes under an interaction policy.
  * Static graph should not show default `blocked` or `failed`.
  * If `question` is shown, mark it as policy-gated runtime control.
    **Acceptance tests:**
  * Static graph does not show default `blocked`.
  * Static graph does not show default `failed`.
  * Static graph distinguishes authored `failed` from runtime failure mechanics.
  * Inspection shows `question` visible interactively and hidden in full-auto.

* **Add fake-provider versus rendered-provider parity tests.**
  Any provider route/payload rule tested with direct `Outcome(...)` must also be tested through rendered JSON parsing.
  **Acceptance tests:**

  * Direct `Outcome(tag="done")` and rendered `{"tag":"done"}` both work.
  * Direct/rendered `blocked` and `failed` without reason both work when authored.
  * Direct/rendered `question` without question both fail.
  * Direct/rendered illegal route under full-auto both follow retry/illegal-route behavior.

* **Update authoring documentation for the new route model.**
  Documentation must reflect the actual contract.
  **Required doc statements:**

  * Only `question` is a default provider control route.
  * `question` is visible only when runtime policy allows provider questions.
  * `blocked` and `failed` are never injected by default.
  * Runtime failures are runtime-owned.
  * Domain-level blocked/failure states must be authored explicitly.
  * Workflow-level artifacts may also be written by steps.
  * Worklist contents are lazy and validated at first use.
    **Acceptance checks:**
  * Docs/examples do not show default `blocked` or `failed`.
  * Examples with `failed` declare it explicitly.
  * Full-auto examples show no provider-visible `question`.
  * Artifact examples do not use `Artifact.managed(...)`.

* **Keep milestone boundaries clear.**
  Runtime semantics should be accepted before larger authoring ergonomics.
  **Milestone A: must be correct before merge**

  * route policy and full-auto gating
  * no default `blocked`/`failed`
  * optional rendered `reason`
  * no hidden `blocked`/`failed` reason requirement
  * lazy worklist materialization
  * lazy work-item session binding
  * checkpoint policy documented and tested
  * artifact dual-role allowed without `Artifact.managed(...)`
    **Milestone B: can follow after A**
  * worklist effect helpers
  * validation-step helper
  * expanded late-bound prompt context
  * inspection polish
  * docs and examples refinements
