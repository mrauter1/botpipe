# Test Strategy

- Task ID: standalone-implementation-plan-autoloop-v3-green-f94366a9
- Pair: test
- Phase ID: provider-and-engine-contract
- Phase Directory Key: provider-and-engine-contract
- Phase Title: Provider and engine contract
- Scope: phase-local producer artifact

## Behavior-to-test coverage
- Provider control-response contract:
  - `tests/unit/test_provider_boundary_core.py` covers rendered prompt sections, readable-vs-required artifact rendering, producer vs control-response modes, and missing-`reason` rejection in the shared parser.
  - `tests/runtime/test_runtime_providers.py` covers plain/fenced JSON parsing with required `reason`, runtime-provider parsing of verifier/llm outcomes, and rendered prompt section expectations seen by CLI transports.
- Engine prompt resolution:
  - `tests/contract/test_engine_contracts.py` covers low-level `Engine` failure for relative `Prompt.file(...)` without a prompt registry and success when `FilesystemPromptRegistry` is supplied.
- Hook/finalization and workflow-step runtime:
  - Existing focused contract tests in `tests/contract/test_engine_contracts.py` cover hook order, route override, post-hook artifact re-resolution, required-output enforcement, child-workflow terminal mapping, output writing, and verifier-loop legality.

## Preserved invariants checked
- Producer turns still return raw text instead of JSON control envelopes.
- Rendered-provider parsing remains strict about top-level control fields while transport layers keep returning raw strings until the core wrapper parses them.
- Low-level engine prompt resolution still supports inline prompts and absolute file prompts without adding hidden filesystem fallback rules.

## Edge cases and failure paths
- Missing top-level `reason` in rendered JSON control responses.
- Fenced JSON question responses that still require both `reason` and `question`.
- Relative file prompts with no prompt registry on low-level `Engine`.

## Known gaps
- Full-suite proof and broader legacy `RouteContract` cleanup remain deferred to later phases.
- Prompt-registry search-root precedence is still covered indirectly by `FilesystemPromptRegistry` unit tests rather than a broader runtime matrix here.
