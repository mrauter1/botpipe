This is the final standalone handoff spec. It supersedes the mixed current implementation where provider output still has special top-level `question` / `reason` behavior while route selection comes from `Outcome.tag`. 

## Standalone spec: route helpers, route schemas, GLOBAL defaults, and structured provider outcomes

* **Objective**

  * Make all provider outcome behavior route-table driven.
  * Treat `question`, `blocked`, and `failed` as conventional route helper presets, not as a separate control-route subsystem.
  * Represent route-dependent provider fields through selected-route schema.
  * Preserve normal route behavior for all routes:

    * route target resolution
    * `after` hooks
    * `on_taken` hooks
    * route redirects
    * handoffs
    * required writes
    * artifact validation
    * static graph metadata
    * compile-report metadata
  * Keep the compiled route table as the single source of truth for:

    * provider legality
    * runtime route legality
    * route schema
    * route visibility
    * execution behavior

* **Core invariant**

  * Everything is a route.
  * Route helpers define conventional defaults.
  * GLOBAL defines workflow-wide route defaults.
  * Step-local routes override GLOBAL routes by tag.
  * Step-local `Route.disabled()` suppresses inherited GLOBAL routes.
  * Provider-visible compiled routes determine which tags a provider may return.
  * Runtime and hook route legality are determined by compiled available routes.
  * Provider output route selection is always `outcome.tag`.
  * `outcome.payload` is business/domain structured output.
  * `outcome.route_fields` is selected-route metadata.
  * Existing route finalization remains the execution path after a provider outcome is parsed and validated.

* **Non-goals**

  * Do not redesign route finalization.
  * Do not make `payload` participate in route selection.
  * Do not replace existing step-level output schema validation.
  * Do not require every route to declare a route-specific payload schema.
  * Do not remove legacy top-level `question` / `reason` parsing in the first migration patch.
  * Do not introduce `ControlRoutes(question=..., blocked=..., failed=...)` as the primary architecture.
  * Do not create a second “control route” mechanism parallel to the route table.

* **Legacy `ControlRoutes` policy**

  * Treat existing `ControlRoutes` as legacy compatibility.
  * New route-helper/GLOBAL route definitions are the preferred authoring model.
  * During migration, `ControlRoutes(question="auto")` may be translated internally into an inherited `Route.question()` default.
  * Do not extend `ControlRoutes` with `blocked` or `failed`.
  * Mark `ControlRoutes` as deprecated once route helper defaults are available.
  * Long-term authoring should express provider control behavior through routes:

    ```python
    transitions = {
        GLOBAL: {
            "question": Route.question(),
            "blocked": Route.blocked(),
            "failed": Route.failed(),
        }
    }
    ```

* **Route metadata**

  * Extend route metadata conceptually to include:

    * `target`
    * `summary`
    * `required_writes`
    * `handoff`
    * `on_taken`
    * `provider_visibility`
    * `payload_schema`
    * `route_fields_schema`
    * `preset` / `kind` for inspection only, such as `"question"`, `"blocked"`, `"failed"`, `"custom"`, `"hidden"`, or `"disabled"`
    * inheritance source metadata:

      * step-local
      * GLOBAL
      * framework default profile
    * disabled/suppressed marker for inherited route removal
  * Route helper presets must compile to ordinary route definitions.
  * Helper presets must not bypass normal route finalization.

* **Provider visibility**

  * Replace boolean-only provider visibility with normalized visibility modes:

    * `"hidden"`: route exists, provider cannot select it.
    * `"interactive_only"`: provider may select it only when human interaction / pausing is allowed.
    * `"always"`: provider may select it in both interactive and full-auto modes.
  * Backward-compatible normalization:

    * `provider_visible=False` → `"hidden"`
    * `provider_visible=True` → `"always"`
  * Provider-visible route lists are derived from compiled routes:

    * interactive mode includes `"interactive_only"` and `"always"`
    * full-auto mode includes `"always"` only
    * hidden routes are excluded
    * disabled routes are excluded
  * Provider output selecting a hidden, disabled, absent, or full-auto-hidden route is an illegal route.

* **Payload schema sentinel API**

  * Do not use `None` ambiguously for payload schema inheritance.
  * Define explicit route payload schema sentinel values or helper constructors:

    * `Route.inherit_payload_schema()`
    * `Route.no_payload_schema()`
  * Semantics:

    * `Route.inherit_payload_schema()`

      * use step-level `expected_output_schema` if present
      * default for route helpers
    * `Route.no_payload_schema()`

      * no payload schema validation for this route
    * concrete Pydantic model / JSON schema

      * validate this route’s `outcome.payload` against that schema
  * Route-specific payload schema overrides step-level schema.
  * Route-specific payload schema does not merge with step-level schema unless a future merge mode is explicitly designed.

* **Route helper API**

  * Add route helper constructors on `Route`.
  * Proposed signatures:

    ```python
    Route.question(
        target=AWAIT_INPUT,
        *,
        summary: str | None = None,
        provider_visibility: Literal["hidden", "interactive_only", "always"] = "interactive_only",
        payload_schema=Route.inherit_payload_schema(),
        route_fields_schema=None,
        required_writes: Sequence[str] = (),
        handoff: str | None = None,
        on_taken: Callable | None = None,
    )

    Route.blocked(
        target=AWAIT_INPUT,
        *,
        summary: str | None = None,
        provider_visibility: Literal["hidden", "interactive_only", "always"] = "interactive_only",
        payload_schema=Route.inherit_payload_schema(),
        route_fields_schema=None,
        required_writes: Sequence[str] = (),
        handoff: str | None = None,
        on_taken: Callable | None = None,
    )

    Route.failed(
        target=FAIL,
        *,
        summary: str | None = None,
        provider_visibility: Literal["hidden", "interactive_only", "always"] = "always",
        payload_schema=Route.inherit_payload_schema(),
        route_fields_schema=None,
        required_writes: Sequence[str] = (),
        handoff: str | None = None,
        on_taken: Callable | None = None,
    )

    Route.hidden(
        target,
        *,
        summary: str | None = None,
        payload_schema=Route.inherit_payload_schema(),
        route_fields_schema=None,
        required_writes: Sequence[str] = (),
        handoff: str | None = None,
        on_taken: Callable | None = None,
    )

    Route.disabled()
    ```

* **Route helper defaults**

  * `Route.question(...)`

    * default target: `AWAIT_INPUT`
    * default provider visibility: `"interactive_only"`
    * default route-fields schema:

      * `questions: list[str]`

        * required
        * minimum one item
        * each item must be a non-empty string
      * `reason: str | null`

        * required in strict generated schemas as nullable
        * semantically optional
    * default payload schema: inherit step-level payload schema
    * default summary: clarification / user-input request
    * preset metadata: `"question"`
  * `Route.blocked(...)`

    * default target: `AWAIT_INPUT`
    * default provider visibility: `"interactive_only"`
    * default route-fields schema:

      * `reason: str | null`

        * required in strict generated schemas as nullable
        * semantically optional
    * default payload schema: inherit step-level payload schema
    * default summary: blocker / cannot proceed without external input
    * preset metadata: `"blocked"`
  * `Route.failed(...)`

    * default target: `FAIL`
    * default provider visibility: `"always"`
    * default route-fields schema:

      * `reason: str | null`

        * required in strict generated schemas as nullable
        * semantically optional
    * default payload schema: inherit step-level payload schema
    * default summary: terminal or unrecoverable failure
    * preset metadata: `"failed"`
  * `Route.hidden(...)`

    * route exists for hooks/runtime
    * provider visibility is `"hidden"`
  * `Route.disabled()`

    * suppresses an inherited GLOBAL/default route
    * route is absent from compiled available routes for that step
    * provider cannot select it
    * hooks/runtime cannot select it

* **Helper semantics are metadata-based, not tag-name-based**

  * A route is question-style because the route definition was created by `Route.question()` or carries equivalent route-fields schema metadata.

  * It is not question-style merely because the tag is `"question"`.

  * This must work:

    ```python
    routes = {
        "clarify": Route.question()
    }
    ```

  * Provider output:

    ```json
    {
      "outcome": {
        "tag": "clarify",
        "payload": {},
        "route_fields": {
          "questions": ["Which cloud region should I target?"],
          "reason": null
        }
      }
    }
    ```

  * Compatibility may temporarily preserve tag-based validation for legacy `"question"` routes, but the target design derives behavior from route metadata.

* **GLOBAL route defaults**

  * GLOBAL may define provider-facing workflow defaults:

    ```python
    transitions = {
        GLOBAL: {
            "question": Route.question(),
            "blocked": Route.blocked(),
            "failed": Route.failed(),
        }
    }
    ```

  * GLOBAL broadness is a feature:

    * a visible GLOBAL `failed` route means every provider-backed step may select `failed`
    * a visible GLOBAL `blocked` route means every provider-backed step may select `blocked`
    * a visible GLOBAL `question` route means every provider-backed step may select `question`

  * This is acceptable because GLOBAL routes are explicit, inspectable, and overridable.

* **Route resolution precedence**

  * Resolve routes by precedence:

    * step-local routes first
    * explicit workflow GLOBAL routes second
    * framework default route profile third, if one exists
  * Step-local route with the same tag replaces inherited route.
  * Step-local `Route.disabled()` suppresses inherited route before available/provider-visible route lists are computed.
  * Suppressed routes must not appear in runtime available routes for that step.
  * No implicit merge unless explicitly implemented and documented.

* **Step-local override examples**

  * Override failed target:

    ```python
    routes = {
        "failed": Route.failed(target=diagnose_failure)
    }
    ```

  * Suppress inherited failed route:

    ```python
    routes = {
        "failed": Route.disabled()
    }
    ```

  * Keep blocked runtime-valid but hide from providers:

    ```python
    routes = {
        "blocked": Route.blocked(provider_visibility="hidden")
    }
    ```

  * Override question route with custom target:

    ```python
    routes = {
        "question": Route.question(target=clarification_router)
    }
    ```

* **Payload schema semantics**

  * `payload` is the business/domain output.
  * Existing step-level `expected_output_schema` remains valid.
  * Route-level payload schema is optional.
  * Resolution order:

    * route-specific payload schema if concrete schema is set
    * otherwise step-level expected output schema if payload schema is inherited and a step schema exists
    * otherwise object-only validation
  * Route payload schemas validate provider outcomes only.
  * Plain hook-returned `Event`s validate route legality and Event fields, not provider payload schemas.
  * If hooks later support returning `Outcome`, the same payload and route-fields schema path may apply to hook-produced outcomes.

* **Route-fields schema semantics**

  * `route_fields` is selected-route metadata.
  * `route_fields` is separate from business payload.
  * Route helpers define default `route_fields_schema`.
  * Custom routes may define custom `route_fields_schema`.
  * If no route-fields schema is declared:

    * canonical internal representation uses `route_fields={}`
    * generated strict schemas still require `route_fields`
    * branch schema for that route should require `route_fields` as an empty object
  * `route_fields` should be used for:

    * clarification questions
    * blocker reason
    * failure reason
    * route-specific diagnostic metadata
    * route-specific explanation fields

* **Canonical provider response**

  * Preferred provider output shape:

    ```json
    {
      "outcome": {
        "tag": "<one provider-visible route>",
        "payload": {},
        "route_fields": {}
      }
    }
    ```

  * `outcome.tag`

    * required
    * string
    * route selection
    * must equal one provider-visible compiled route tag

  * `outcome.payload`

    * required in generated strict schemas
    * object
    * business/domain output
    * validates against selected route payload schema or step fallback schema

  * `outcome.route_fields`

    * required in generated strict schemas
    * object
    * selected-route metadata
    * validates against selected route-fields schema

  * Parser may accept omitted `payload` and normalize to `{}` only in legacy/non-strict mode.

  * Parser may accept omitted `route_fields` and normalize to `{}` only in legacy/non-strict mode.

* **Generated provider schema**

  * Generate a root object schema.

  * Do not use top-level `anyOf` or `oneOf`.

  * Root schema contains required property `outcome`.

  * `outcome` contains a nested `anyOf` branch per provider-visible route.

  * Each route branch contains:

    * `tag` with `const: "<route-tag>"`
    * `payload` schema for the selected route
    * `route_fields` schema for the selected route

  * Each strict branch requires:

    * `tag`
    * `payload`
    * `route_fields`

  * Use `additionalProperties: false` for:

    * root object
    * outcome branch objects
    * route-fields objects

  * For unconstrained payloads, use:

    ```json
    {
      "type": "object",
      "additionalProperties": true
    }
    ```

  * Avoid:

    * dynamically named fields such as `question_route_fields`
    * top-level `anyOf`
    * top-level `oneOf`
    * `if` / `then` / `else`
    * route names embedded into field names

  * Use nullable required fields for optional values in strict structured-output environments:

    * `reason: ["string", "null"]`

* **Generated schema example**

  * Example with `question` and `blocked` visible:

    ```json
    {
      "type": "object",
      "properties": {
        "outcome": {
          "anyOf": [
            {
              "type": "object",
              "properties": {
                "tag": { "const": "question" },
                "payload": {
                  "type": "object",
                  "additionalProperties": true
                },
                "route_fields": {
                  "type": "object",
                  "properties": {
                    "questions": {
                      "type": "array",
                      "items": {
                        "type": "string",
                        "minLength": 1
                      },
                      "minItems": 1
                    },
                    "reason": {
                      "type": ["string", "null"]
                    }
                  },
                  "required": ["questions", "reason"],
                  "additionalProperties": false
                }
              },
              "required": ["tag", "payload", "route_fields"],
              "additionalProperties": false
            },
            {
              "type": "object",
              "properties": {
                "tag": { "const": "blocked" },
                "payload": {
                  "type": "object",
                  "additionalProperties": true
                },
                "route_fields": {
                  "type": "object",
                  "properties": {
                    "reason": {
                      "type": ["string", "null"]
                    }
                  },
                  "required": ["reason"],
                  "additionalProperties": false
                }
              },
              "required": ["tag", "payload", "route_fields"],
              "additionalProperties": false
            }
          ]
        }
      },
      "required": ["outcome"],
      "additionalProperties": false
    }
    ```

* **Large-schema fallback**

  * If a route-discriminated generated schema exceeds provider schema limits or becomes too large:

    * fall back to a simpler provider schema:

      * `outcome.tag` enum over provider-visible routes
      * `outcome.payload` object
      * `outcome.route_fields` object
    * enforce full route-specific validation after parsing
  * The fallback must not weaken runtime validation.
  * It only relaxes provider-side constrained generation.
  * Compile reports should indicate when simplified provider schema fallback was used.

* **Parsing and normalization**

  * Parse canonical shape:

    ```json
    {
      "outcome": {
        "tag": "...",
        "payload": {},
        "route_fields": {}
      }
    }
    ```

  * Normalize to runtime `Outcome`:

    * `Outcome.tag = outcome.tag`
    * `Outcome.payload = outcome.payload`
    * `Outcome.route_fields = outcome.route_fields`

  * Add `Outcome.route_fields`.

  * Keep compatibility accessors or mirrored fields:

    * `Outcome.reason`
    * `Outcome.question`

  * `Outcome.reason` derives from `route_fields.reason` when present.

  * `Outcome.question` derives from question-style `route_fields.questions`.

  * If `questions` is a list:

    * canonical representation remains list
    * legacy `Outcome.question` / `Event.question` is a readable string projection
    * recommended projection is Markdown bullets

  * Example projection:

    ```text
    - Which deployment environment should I use?
    - Is downtime acceptable?
    ```

* **Legacy provider output compatibility**

  * Temporarily accept legacy shape:

    ```json
    {
      "tag": "question",
      "question": "...",
      "reason": "...",
      "payload": {}
    }
    ```

  * Normalize it to canonical shape:

    ```json
    {
      "outcome": {
        "tag": "question",
        "payload": {},
        "route_fields": {
          "questions": ["..."],
          "reason": "..."
        }
      }
    }
    ```

  * Prefer canonical `route_fields` when both canonical and legacy fields are present.

  * Rendered provider prompts should teach only canonical shape.

  * Legacy top-level `question` and `reason` should be documented as deprecated after migration.

* **Runtime event conversion**

  * Route selection:

    * `Event.tag` comes from `Outcome.tag`
  * Event reason:

    * `Event.reason` comes from `Outcome.route_fields.reason` when present
  * Event question:

    * for question-style routes, `Event.question` comes from projected `Outcome.route_fields.questions`
  * `Outcome.payload` is not route selection.
  * `Outcome.route_fields` is not route selection.
  * Route finalization looks up the compiled route by `Event.tag`.
  * Existing runtime context remains:

    * `ctx.route`
    * `ctx.event`
    * `ctx.outcome`
    * `ctx.outcome.payload`
  * Add:

    * `ctx.outcome.route_fields`
  * Existing hooks that read `ctx.outcome.payload` continue to work.

* **Validation sequence**

  * Validate provider response envelope:

    * valid JSON
    * root object
    * required or normalized `outcome`
    * required or normalized `tag`
    * required or normalized `payload`
    * required or normalized `route_fields`
  * Validate route legality:

    * selected tag is provider-visible for current interaction policy
  * Validate payload:

    * selected route’s payload schema if explicit
    * otherwise step-level expected output schema if inherited and present
    * otherwise object-only validation
  * Validate route fields:

    * selected route’s route-fields schema
  * Normalize to `Outcome`.
  * Convert to `Event`.
  * Run existing after hooks.
  * Run normal route finalization.
  * Run artifact guard / required-write validation as today.

* **Error kinds**

  * Bad JSON:

    * `malformed_provider_output`
  * Missing `outcome` or invalid envelope shape:

    * `malformed_provider_output`
  * Missing `tag`:

    * `malformed_provider_output`
  * `tag` not provider-visible:

    * `illegal_route`
  * `payload` not object:

    * `invalid_payload`
  * `payload` fails selected payload schema:

    * `invalid_payload`
  * `route_fields` not object:

    * `invalid_payload`
  * `route_fields` fails selected route-fields schema:

    * `invalid_payload`
  * question-style route selected with empty or missing `questions`:

    * `invalid_payload`
  * All provider-attributable validation failures should continue through existing retry feedback and retry exhaustion machinery.

* **Provider prompt behavior**

  * Render the canonical provider response format.
  * Include only provider-visible routes under the current interaction policy.
  * For each visible route, include:

    * route tag
    * route summary
    * route target description, if appropriate
    * required writes
    * payload schema
    * route-fields schema
  * Explain:

    * `tag` chooses one route
    * `payload` is domain/business output
    * `route_fields` contains metadata for the selected route only
  * Do not list hidden routes.
  * Do not list disabled routes.
  * Do not teach legacy top-level `question` / `reason`.

* **Compile reports**

  * Compile reports should show whether a route is:

    * step-local
    * inherited from GLOBAL
    * inherited from framework defaults
    * suppressed/disabled
  * Compile reports should show:

    * all available routes
    * provider-visible interactive routes
    * provider-visible full-auto routes
    * per-route payload schema
    * per-route route-fields schema
    * schema fallback status if simplified schema generation is used

* **Static graph**

  * Static graph should show:

    * route tag
    * target
    * summary
    * provider visibility
    * payload schema source/name/fingerprint
    * route-fields schema source/name/fingerprint
    * helper preset kind
    * inherited vs step-local
    * suppressed/disabled state
    * required writes
    * handoff
    * hook identity
  * Static graph should not infer helper behavior from tag names alone.
  * Static graph should reflect compiled route metadata exactly.

* **Topology hash**

  * Topology hash must include:

    * route tag
    * route target
    * provider visibility
    * payload schema fingerprint / inheritance mode
    * route-fields schema fingerprint
    * preset kind
    * required writes
    * handoff text
    * route hook identity
    * disabled/suppressed status
    * inheritance source if relevant
  * Changing a route schema must change topology hash.
  * Changing provider visibility must change topology hash.
  * Changing step-local override/suppression must change topology hash.

* **Provider backend compatibility**

  * Structured-output capable providers should receive the generated schema.
  * Providers with strict JSON Schema subsets should receive the root-object-with-nested-`anyOf` form.
  * If a backend cannot support the route-discriminated schema due to size or complexity:

    * use simplified schema fallback
    * enforce full validation post-parse
  * Scripted/fake providers must validate returned `Outcome` against the same route legality, payload schema, and route-fields schema as rendered providers.

* **Implementation touchpoints**

  * `Route` model / route normalization:

    * add helper constructors
    * add provider visibility normalization
    * add payload schema mode
    * add route-fields schema
    * add disabled/suppressed route representation
  * Compiler/discovery:

    * implement GLOBAL inheritance and step-local suppression
    * compile route helper metadata into `CompiledRoute`
    * preserve route table as source of truth
  * Provider request generation:

    * generate canonical provider schema from provider-visible compiled routes
    * include route schemas in provider contracts
  * Provider parsing:

    * parse canonical envelope
    * support legacy envelope
    * normalize to `Outcome`
  * Engine validation:

    * validate provider route legality
    * validate payload schema
    * validate route-fields schema
  * Runtime context:

    * expose `ctx.outcome.route_fields`
    * preserve `ctx.outcome.payload`
    * preserve compatibility `ctx.outcome.question` and `ctx.outcome.reason`
  * Static graph / compile report / topology hash:

    * include route schema metadata and inheritance/suppression state

* **Testing: route helper defaults**

  * Test `Route.question()`:

    * target is `AWAIT_INPUT`
    * provider visibility is `"interactive_only"`
    * route-fields schema requires non-empty `questions`
    * nullable `reason`
  * Test `Route.blocked()`:

    * target is `AWAIT_INPUT`
    * provider visibility is `"interactive_only"`
    * route-fields schema includes nullable `reason`
  * Test `Route.failed()`:

    * target is `FAIL`
    * provider visibility is `"always"`
    * route-fields schema includes nullable `reason`
  * Test helper override of:

    * target
    * provider visibility
    * payload schema
    * route-fields schema
    * handoff
    * required writes
    * `on_taken`

* **Testing: GLOBAL and step overrides**

  * GLOBAL route defaults are inherited by provider-backed steps.
  * Step-local route with same tag overrides GLOBAL.
  * Step-local `Route.disabled()` suppresses inherited route.
  * Step-local hidden route remains runtime-valid but not provider-visible.
  * Visible GLOBAL `failed` makes `failed` provider-visible globally unless overridden/suppressed.
  * Step override can change `failed` target from `FAIL` to a recovery step.

* **Testing: provider schema generation**

  * Generated root schema is an object with required `outcome`.
  * `outcome` uses nested `anyOf` branches for visible routes.
  * Hidden routes are excluded.
  * Interactive-only routes are excluded from full-auto schema.
  * Disabled routes are excluded.
  * Each branch has route-specific `tag.const`.
  * Each branch has correct payload schema.
  * Each branch has correct route-fields schema.
  * Large-schema fallback still post-validates route-specific fields.

* **Testing: parsing and validation**

  * Canonical valid output parses.
  * Legacy output parses and normalizes.
  * Missing `outcome` fails as malformed provider output.
  * Unknown route tag fails as illegal route.
  * Hidden route tag fails as illegal route.
  * Question-style route with missing/empty questions fails invalid payload.
  * Blocked route with `reason: null` passes.
  * Failed route with `reason: null` passes.
  * Payload schema failure triggers invalid payload.
  * Route-fields schema failure triggers invalid payload.
  * Retry feedback paths remain correct.

* **Testing: runtime behavior**

  * Provider-selected route still flows through normal after hooks.
  * After hook can redirect to another route.
  * `on_taken` hook runs for helper routes.
  * Required writes are enforced for helper routes.
  * Handoffs are scheduled for helper routes.
  * Artifact guard behavior is unchanged.
  * `ctx.outcome.payload` is available in hooks.
  * `ctx.outcome.route_fields` is available in hooks.
  * `ctx.event.question` is projected from `route_fields.questions`.
  * `ctx.event.reason` is projected from `route_fields.reason`.

* **Migration requirements**

  * Keep accepting legacy top-level `tag`, `payload`, `question`, `reason` during transition.
  * Emit canonical `Outcome.route_fields` internally.
  * Keep compatibility accessors for `Outcome.question` and `Outcome.reason`.
  * Update rendered prompts to canonical `outcome` wrapper.
  * Update docs to prefer route helpers over `ControlRoutes`.
  * Mark legacy top-level route-dependent fields as deprecated after migration.

* **Documentation updates**

  * Document:

    * Everything is a route.
    * Route helpers define conventional defaults.
    * GLOBAL defines workflow defaults.
    * Step-local routes override GLOBAL.
    * `Route.disabled()` suppresses inherited routes.
    * `provider_visibility="interactive_only"` means provider-visible in interactive mode but not in full-auto.
    * `payload` is domain output.
    * `route_fields` is selected-route metadata.
    * `Route.question()` requires `route_fields.questions`.
    * `Route.blocked()` and `Route.failed()` use nullable `route_fields.reason`.
  * Remove or de-emphasize:

    * separate control-route terminology
    * top-level `question` / `reason` as the preferred provider output
    * default implicit `blocked` / `failed` injection

* **Acceptance criteria**

  * Provider output uses or normalizes to:

    * `outcome.tag`
    * `outcome.payload`
    * `outcome.route_fields`
  * Route selection is always `outcome.tag`.
  * Business payload validation uses route payload schema or step fallback schema.
  * Route metadata validation uses selected route-fields schema.
  * `Route.question()` enforces non-empty questions through route schema.
  * `Route.blocked()` and `Route.failed()` provide conventional nullable reason fields.
  * `Route.failed()` defaults to provider visibility `"always"`.
  * GLOBAL route defaults work.
  * Step-local overrides work.
  * Step-local suppression works.
  * Hidden routes are runtime-valid but not provider-selectable.
  * Disabled routes are absent.
  * Full-auto provider schemas exclude interactive-only routes.
  * Existing route finalization and hooks remain normal.
  * Static graph, compile report, topology hash, provider prompts, parser, and tests all reflect route-schema metadata.
