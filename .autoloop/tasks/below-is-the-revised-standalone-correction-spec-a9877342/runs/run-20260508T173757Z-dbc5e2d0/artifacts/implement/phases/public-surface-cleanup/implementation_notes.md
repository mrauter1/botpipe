# Implementation Notes

- Task ID: below-is-the-revised-standalone-correction-spec-a9877342
- Pair: implement
- Phase ID: public-surface-cleanup
- Phase Directory Key: public-surface-cleanup
- Phase Title: Public Surface Cleanup
- Scope: phase-local producer artifact

## Files changed
- `autoloop/sdk.py`
- `autoloop/simple.py`
- `autoloop/core/steps.py`
- `autoloop/core/discovery.py`
- `autoloop/policy.py`
- `tests/unit/test_sdk_facade.py`
- `tests/unit/test_simple_surface.py`
- `tests/unit/test_simple_policy.py`

## Symbols touched
- `_normalize_sdk_policy_input`
- `simple._normalize_provider_policy`
- `core.steps._normalize_provider_policy`
- `core.discovery._validate_workflow_policy`
- `resolve_policy_layer`
- `test_sdk_constructor_rejects_invalid_default_policy_with_public_wording`
- `test_sdk_run_rejects_removed_typed_input_and_parameters_keywords`
- `test_policy_module_export_lists_match_public_surface_contract`
- `test_public_policy_validation_wording_hides_internal_override_types`

## Checklist mapping
- Plan milestone 2: completed for public-facing policy wording cleanup in SDK/simple/core discovery/step normalization paths.
- Plan milestone 2: completed for export regression coverage without widening any public surface.
- Plan validation bullets for `tests/unit/test_sdk_facade.py`, `tests/unit/test_simple_surface.py`, and `tests/unit/test_simple_policy.py`: completed for removed keyword rejection, export guarantees, sequence-style public helper usage coverage preservation, and public wording assertions.
- Plan milestone 3: intentionally deferred in this phase; no runtime CLI edits were made.

## Assumptions
- The active phase contract is authoritative over the broader task-global spec for this turn, so runtime CLI renaming remains outside this phase-local implementation.

## Preserved invariants
- Public exports stay unchanged; tests only lock the existing intended `__all__` shape.
- Internal compatibility with concrete `ProviderPolicy` and `ProviderPolicyOverride` remains intact.
- Mapping-style writes remain available only in lower-level/core paths already using them; public SDK helper coverage remains sequence-based.

## Intended behavior changes
- Public normalization and discovery errors now refer to `Policy` or a `core provider policy object` instead of exposing `ProviderPolicyOverride`.
- SDK regression tests now explicitly reject removed `typed_input=` and `parameters=` keywords for both `client.run(...)` and `client.step(...)`.

## Known non-changes
- No runtime CLI `--workspace` migration in this phase.
- No payload-kind or fingerprint changes here beyond the earlier phase.
- No new public `PolicyOverride` alias, constructor, docs path, or export.

## Expected side effects
- User-visible validation failures for invalid public policy inputs now use the tightened greenfield wording.

## Validation performed
- `python3 -m py_compile autoloop/sdk.py autoloop/simple.py autoloop/core/steps.py autoloop/core/discovery.py autoloop/policy.py tests/unit/test_sdk_facade.py tests/unit/test_simple_surface.py tests/unit/test_simple_policy.py`
- Attempted but blocked: `python3 -m pytest tests/unit/test_sdk_facade.py tests/unit/test_simple_surface.py tests/unit/test_simple_policy.py` failed because `pytest` is not installed in this environment.
- Attempted but blocked: direct Python smoke imports also failed because `pydantic` is not installed in this environment.

## Deduplication / centralization
- Kept public wording changes in the existing normalization and discovery helpers rather than adding new wrappers or compatibility aliases.
