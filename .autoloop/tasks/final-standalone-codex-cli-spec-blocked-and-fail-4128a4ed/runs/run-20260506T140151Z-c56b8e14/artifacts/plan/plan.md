# Plan

## Objective

Adopt the new greenfield control-route contract at compilation time:

- `question` is the only framework-injected provider runtime-control route when enabled.
- `blocked` and `failed` are ordinary authored route tags, absent by default, never auto-injected, never added to `runtime_control_routes`, and only provider-selectable when explicitly declared and visible.
- Illegal provider selections of undeclared or hidden `blocked` / `failed` must continue through the existing illegal-route retry and exhaustion paths.

## Concrete Edit Surfaces

- `autoloop/core/discovery.py`
  - Remove default `blocked` / `failed` injection from `_inject_control_routes(...)`.
  - Keep `question` injection semantics unchanged.
  - Ensure `runtime_control_routes_by_step` contains only `question` when enabled.
- `autoloop/core/compiler.py`
  - Remove implicit `blocked` / `failed` from `_internal_step_runtime_routes(...)`.
  - Remove implicit `blocked` / `failed` from `_internal_step_runtime_control_routes(...)`.
  - Leave `_compiled_provider_visibility(...)` generic for all non-`question` routes.
- Downstream consumers expected to change via compiled output only, not bespoke logic:
  - provider contract surfaces in engine/provider collaborators
  - static graph, topology, compile report, capability inspection, CLI compile payloads
  - topology hashes and route-table snapshots/assertions

## Required Invariants

- Default `PromptStep` route tables compile authored semantic routes plus `question`, without `blocked` or `failed`.
- Default `ProduceVerifyStep` route tables compile authored semantic routes plus `question`, without `blocked` or `failed`.
- `control_routes=False` yields no injected runtime-control routes.
- `ControlRoutes(question="always")` still exposes `question` in full-auto and still does not imply `blocked` or `failed`.
- Explicit `blocked` / `failed` routes remain authored routes only:
  - legal when declared locally or globally
  - visible only when `provider_visible=True`
  - rejected for providers when hidden
  - never marked runtime-control
- `question` keeps strict payload validation; `blocked` / `failed` keep optional `reason`.
- Packaged workflows that explicitly author `_BLOCKED_ROUTE` or `_FAILED_ROUTE` remain valid and should keep their expectations.

## Milestones

### 1. Route compilation contract

- Update discovery-time and internal compiler-time route injection so only `question` is framework-injected for provider-backed steps.
- Confirm simple-authoring and class-authoring compilation both inherit the same contract.
- Verify no special-case filtering is introduced later in provider prompt generation or route validation.

### 2. Runtime/provider regression coverage

- Update compile-level and contract tests for default prompt/pair steps, full-auto, and `control_routes=False`.
- Add or adjust explicit opt-in coverage for visible and hidden `blocked` / `failed` on scripted and rendered provider paths.
- Add negative provider tests for undeclared and hidden `blocked` / `failed`, including retry recovery and retry exhaustion.
- Refresh static graph, topology, compile report, capability inspection, and reference-resolution expectations that currently assert implicit `blocked` / `failed`.

### 3. Packaged workflow and documentation alignment

- Remove only expectations that relied on framework injection from packaged workflow tests.
- Keep explicit packaged workflow `blocked` / `failed` contracts and add assertions that distinguish authored routes from framework defaults where needed.
- Align docs, workflow prompt READMEs, and architecture/authoring references so they consistently describe `question` as the only default runtime-control route and treat undeclared provider route tags as invalid.

## Validation Plan

- Targeted compilation and contract tests:
  - `tests/contract/test_engine_contracts.py`
  - `tests/contract/test_canonical_runtime_contracts.py`
  - `tests/runtime/test_runtime_static_graph.py`
  - `tests/runtime/test_workflow_reference_resolution.py`
- Packaged workflow regression buckets:
  - workflow-package tests that currently assert implicit `blocked` / `failed` in compiled route lists or prompt contract markers
- Full suite expectation:
  - run the full test suite after targeted fixes because topology hashes, static artifacts, and packaged workflow surfaces are widely reused

## Compatibility / Intentional Behavior Break

- This is an intentional breaking contract change requested by the user:
  - provider-backed steps no longer accept `blocked` / `failed` by default
  - provider-visible route lists and rendered prompts lose implicit `blocked` / `failed`
  - compile reports, static graphs, topology payloads, and hashes change accordingly
- No migration layer should preserve the old default behavior.
- Explicit authored routes named `blocked` or `failed` remain supported and are the only compatibility path.

## Risk Register

- Risk: fixing only prompt rendering would leave compiled legality, topology, and provider-contract surfaces inconsistent.
  - Control: make discovery/compiler the source of truth and let downstream surfaces derive from compiled routes.
- Risk: simple-authoring internal compilation could diverge from class-authoring compilation.
  - Control: update both discovery and `_internal_step_*` helpers and keep shared tests for both surfaces.
- Risk: packaged workflow tests may fail for mixed reasons because some workflows explicitly opt in while others relied on defaults.
  - Control: inspect each failing expectation and preserve only explicit authored-route behavior.
- Risk: hidden explicit `blocked` / `failed` could accidentally stay provider-selectable.
  - Control: rely on compiled provider-visible route lists and add direct negative tests for scripted and rendered providers.
- Risk: broad route-name searches can catch unrelated runtime status/reporting uses of the words `blocked` and `failed`.
  - Control: limit implementation edits to route compilation/visibility surfaces and update only assertions/docs tied to provider-selectable routes.

## Out Of Scope

- Changing runtime status normalization for explicit `blocked` / `failed` events.
- Changing branch-group composite route semantics that do not participate in provider-backed step control-route injection.
- Adding new provider payload requirements beyond the existing `question` validation contract.
