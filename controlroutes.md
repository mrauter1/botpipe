## Final standalone Codex CLI spec: `blocked` and `failed` are explicit opt-in provider routes

* **Objective**

  * Change the latest pasted implementation so `blocked` and `failed` are **not** default provider-selectable routes.
  * `question` is the **only** framework-injected provider runtime-control route.
  * `blocked` and `failed` are ordinary authored route tags:

    * absent by default
    * invalid when undeclared
    * provider-visible only when explicitly declared and visible
    * never classified as `runtime_control_routes`
  * Treat this as a greenfield contract. Update implementation, tests, snapshots, and docs to match this behavior.

* **Core route model**

  * `question`

    * Framework-owned runtime-control route.
    * May be injected automatically for provider-backed steps when question handling is enabled.
    * Defaults to `AWAIT_INPUT`.
    * Requires a non-empty `question` payload when selected by a provider.
    * Existing full-auto behavior must remain unchanged.
  * `blocked`

    * Ordinary authored route tag.
    * Never injected by the framework.
    * Never valid or provider-visible unless explicitly declared.
    * Does not require a `reason` field.
    * May target `AWAIT_INPUT`, `FINISH`, another step, or any valid author-selected destination.
  * `failed`

    * Ordinary authored route tag.
    * Never injected by the framework.
    * Never valid or provider-visible unless explicitly declared.
    * Does not require a `reason` field.
    * May target `FAIL`, another step, or any valid author-selected destination.
  * `blocked` and `failed` must **never** appear in `runtime_control_routes`, even when explicitly declared.

* **Author opt-in contract**

  * Authors opt in by declaring routes explicitly, for example:

    * `routes={"blocked": AWAIT_INPUT}`
    * `routes={"failed": FAIL}`
    * `routes={"blocked": Route(target=AWAIT_INPUT, summary="...")}`
    * `routes={"failed": Route(target=FAIL, summary="...")}`
  * Step-local and global route declarations both count as explicit opt-in.
  * Provider visibility follows the route’s normal `provider_visible` flag.
  * Hidden explicit routes remain deterministic runtime routes but are not provider-selectable:

    * `Route(target=AWAIT_INPUT, provider_visible=False)`
    * `Route(target=FAIL, provider_visible=False)`
  * `control_routes=True`, default `ControlRoutes(...)`, and `ControlRoutes(question=...)` must not imply `blocked` or `failed`.
  * `control_routes=False` disables `question` and still must not add `blocked` or `failed`.

* **Compiled route source of truth**

  * Fix the behavior at route construction / compilation time.
  * Do not solve this by filtering `blocked` and `failed` out of provider prompts after they have already been compiled.
  * The compiled route table is authoritative for:

    * valid runtime routes
    * authored routes
    * provider-visible routes
    * provider prompt route guidance
    * static graph output
    * topology hashes
    * compile reports
    * illegal-route retry validation
    * runtime finalization
  * If `blocked` or `failed` are absent from the compiled route table, provider output selecting either tag must follow the existing illegal-route retry/failure path.
  * If `blocked` or `failed` are present but hidden with `provider_visible=False`, provider output selecting them must also be rejected as not allowed for the provider.

* **Implementation changes**

  * In `autoloop/core/discovery.py::_inject_control_routes(...)`:

    * Keep `question` injection.
    * Remove all default injection of:

      * `blocked -> AWAIT_INPUT`
      * `failed -> FAIL`
    * Remove all additions of `blocked` and `failed` to `runtime_control_routes_by_step`.
    * Expected default result:

      * provider-backed step with question enabled: `runtime_control_routes == ("question",)`
      * provider-backed step with `control_routes=False`: `runtime_control_routes == ()`
  * In `autoloop/core/compiler.py::_internal_step_runtime_routes(...)`:

    * Keep internal semantic defaults such as:

      * prompt step: `done`
      * produce/verify step: `accepted`, `needs_rework`
    * Keep `question` injection when enabled.
    * Remove `routes.setdefault("blocked", AWAIT_INPUT)`.
    * Remove `routes.setdefault("failed", FAIL)`.
  * In `autoloop/core/compiler.py::_internal_step_runtime_control_routes(...)`:

    * Keep `question` when enabled.
    * Remove all logic appending or returning `blocked` or `failed`.
  * Do not special-case `_compiled_provider_visibility(...)` for `blocked` or `failed`.

    * Explicit visible `blocked` / `failed` should behave like any other visible authored route.
    * Explicit hidden `blocked` / `failed` should behave like any other hidden authored route.
  * Do not remove explicit `_BLOCKED_ROUTE` or `_FAILED_ROUTE` declarations inside packaged workflows. Those are author opt-ins.

* **Provider behavior**

  * Default provider-visible route lists must not include `blocked` or `failed`.
  * Default rendered provider prompts must not mention `blocked` or `failed` as selectable routes.
  * Scripted provider and rendered provider paths must enforce the same route legality rules.
  * Provider output `{"tag": "blocked"}` without an explicit provider-visible `blocked` route is illegal.
  * Provider output `{"tag": "failed"}` without an explicit provider-visible `failed` route is illegal.
  * With retries remaining, illegal `blocked` / `failed` selections must use the existing illegal-route retry feedback path, including the existing “selected route was not allowed” style message.
  * With retries exhausted, illegal `blocked` / `failed` selections must follow the existing illegal-route exhaustion path, including provider-attributable failure context.

* **Full-auto behavior**

  * Preserve existing `question` behavior:

    * default `question`: visible in interactive mode, hidden in full-auto
    * `ControlRoutes(question="always")`: visible in full-auto
    * `control_routes=False`: absent
  * `blocked` and `failed` have no special full-auto behavior:

    * absent when undeclared
    * visible if explicitly declared and provider-visible
    * hidden if explicitly declared with `provider_visible=False`

* **Payload validation**

  * Keep `question` strict: provider-selected `question` requires a non-empty `question` field.
  * Keep explicit `blocked` and `failed` lenient: no required `reason` field.
  * Do not add framework-level `reason` requirements for `blocked` or `failed`.
  * Do not treat `blocked` as a synonym for `question`.
  * Do not treat `failed` as a synonym for provider execution failure. It is just an authored route tag unless the runtime itself fails.

* **Compile-time tests**

  * Update default `PromptStep` tests:

    * `runtime_control_routes == ("question",)`
    * route table includes authored semantic routes plus `question`
    * route table does not include `blocked`
    * route table does not include `failed`
    * interactive provider-visible routes do not include `blocked` or `failed`
    * full-auto provider-visible routes do not include `blocked` or `failed`
  * Update default `ProduceVerifyStep` tests:

    * route table includes `accepted`, `needs_rework`, and `question`
    * route table does not include `blocked`
    * route table does not include `failed`
    * `runtime_control_routes == ("question",)`
  * Update `control_routes=False` tests:

    * no `question`
    * no `blocked`
    * no `failed`
    * `runtime_control_routes == ()`
  * Update `ControlRoutes(question="always")` tests:

    * `question` remains full-auto-visible
    * `blocked` and `failed` remain absent unless explicitly declared

* **Explicit opt-in tests**

  * Add or preserve tests where a step explicitly declares:

    * `routes={"blocked": AWAIT_INPUT}`
    * `routes={"failed": FAIL}`
  * Assert:

    * `blocked` and `failed` compile as authored routes
    * `blocked` and `failed` do not appear in `runtime_control_routes`
    * visible explicit routes appear in provider-visible route lists
    * scripted provider output `blocked` succeeds
    * scripted provider output `failed` succeeds
    * rendered provider output `{"tag": "blocked"}` succeeds
    * rendered provider output `{"tag": "failed"}` succeeds
    * no `reason` field is required
  * Add hidden explicit-route tests:

    * hidden `blocked` / `failed` appear in route tables as authored hidden routes
    * hidden `blocked` / `failed` do not appear in provider-visible route lists
    * provider output selecting hidden `blocked` / `failed` is rejected as not allowed
  * Add equivalent explicit-route coverage for `ProduceVerifyStep` verifier responses.

* **Negative provider tests**

  * Add scripted-provider tests:

    * default `PromptStep`, provider returns undeclared `blocked`, retry occurs, then valid route succeeds
    * default `PromptStep`, provider returns undeclared `failed`, retry occurs, then valid route succeeds
    * default `ProduceVerifyStep`, verifier returns undeclared `blocked`, retry occurs, then valid route succeeds
    * default `ProduceVerifyStep`, verifier returns undeclared `failed`, retry occurs, then valid route succeeds
  * Add rendered-provider tests:

    * initial rendered prompt does not list `blocked` or `failed`
    * provider returns `{"tag": "blocked"}` or `{"tag": "failed"}`
    * retry prompt contains existing illegal-route feedback
    * subsequent valid route succeeds
  * Add exhaustion tests:

    * undeclared `blocked` with no retries follows existing illegal-route exhaustion behavior
    * undeclared `failed` with no retries follows existing illegal-route exhaustion behavior
    * failure context remains provider-attributable under the existing mechanism

* **Static graph, topology, and compile report tests**

  * Update static graph snapshots and assertions so default provider-backed steps do not show `blocked` or `failed`.
  * Update compile reports so default provider-backed steps do not list implicit `blocked` or `failed`.
  * Update topology expectations and hashes as needed.
  * Add an assertion that a default provider-backed step’s compile report and static graph payload do not mention `blocked` or `failed` anywhere except unrelated authored/domain data.
  * Preserve tests showing explicit hidden global routes appear in route tables / static graph metadata as hidden authored routes.

* **Packaged workflow tests**

  * Do not bulk-remove explicit `blocked` or `failed` routes from packaged workflows.
  * For each packaged workflow expectation involving `blocked` or `failed`:

    * if the route is explicitly declared, keep the expectation
    * if the route was only framework-injected, remove the expectation
  * Add assertions distinguishing explicit workflow-authored `blocked` / `failed` routes from framework defaults.
  * Do not add explicit `blocked` / `failed` to workflows only to preserve old framework behavior. Add them only where the workflow genuinely wants providers to select them.

* **Documentation updates**

  * Update docs, prompt templates, architecture notes, and baseline docs to say:

    * “The only default provider runtime-control route is `question` when enabled.”
    * “`blocked` and `failed` are ordinary authored routes.”
    * “Declare `blocked` or `failed` explicitly if providers may select them.”
    * “Unlisted provider route tags are invalid.”
  * Remove wording implying `blocked` or `failed` are:

    * reserved default routes
    * automatically injected routes
    * always-valid provider control routes
    * provider-visible by default
  * Keep examples showing explicit opt-in usage.

* **Acceptance criteria**

  * Default `PromptStep` never compiles `blocked` or `failed`.
  * Default `ProduceVerifyStep` never compiles `blocked` or `failed`.
  * Default provider-visible route lists never contain `blocked` or `failed`.
  * Default rendered provider prompts never list `blocked` or `failed`.
  * `runtime_control_routes` contains `question` only when question control is enabled.
  * `blocked` and `failed` never appear in `runtime_control_routes`, even when explicitly declared.
  * Provider output selecting undeclared `blocked` or `failed` is illegal.
  * Provider output selecting hidden explicit `blocked` or `failed` is illegal.
  * Explicit visible `blocked` and `failed` routes work for scripted and rendered providers.
  * Explicit `blocked` and `failed` routes do not require `reason`.
  * `question` behavior is unchanged.
  * Static graph, topology, compile reports, tests, and docs all reflect the new route contract.
  * Full test suite passes after implementation and test updates.

