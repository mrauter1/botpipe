# Test Strategy

- Task ID: recursive-framework-evolution-20260425t013735-bootstrap
- Pair: test
- Phase ID: artifact-model
- Phase Directory Key: artifact-model
- Phase Title: Artifact Model Upgrade
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Artifact declaration metadata:
  `tests/unit/test_primitives_and_stores.py`
  Covers factory constructors, `bind_name()`, `bind_owner_step()`, and step-local relative-path resolution when an `Artifact` carries `owner_step`.
- Preserved artifact-handle invariants:
  `tests/unit/test_primitives_and_stores.py`
  Keeps coverage for `read_text()`, `write_text()`, `append()`, `exists()`, and `ResolvedArtifacts` attribute access.
- New JSON/model handle helpers:
  `tests/unit/test_primitives_and_stores.py`
  Covers `read_json()`, `write_json()`, `read_model()`, and `write_model()` happy path plus `read_model()` failure without a schema.
- Artifact validation helper behavior:
  `tests/unit/test_primitives_and_stores.py`
  Covers missing required artifact failure, invalid Pydantic-schema payload failure, and missing optional artifact success.
- Compile-time schema placement rules:
  `tests/unit/test_validation.py`
  Covers schema rejection on non-JSON artifacts, unsupported schema type rejection, and raw JSON-schema rejection when `jsonschema` is unavailable.
- Compiled metadata preservation:
  `tests/unit/test_validation.py`
  Covers compiled artifact retention of `kind`, `schema`, `required`, `owner_step`, and `qualified_name`.

## Preserved invariants checked

- Existing plain `Artifact(...)` declarations still validate and compile.
- Existing handle text APIs remain unchanged while JSON/model helpers are additive.
- Adjacent engine/runtime behavior remains stable under targeted contract/runtime regression suites.

## Edge cases and failure paths

- Calling `read_model()` on an artifact without a schema raises `TypeError`.
- Optional schema-bearing artifacts may be absent without failing validation.
- Environment-sensitive raw-schema declarations fail cleanly when `jsonschema` cannot be imported.

## Stabilization approach

- Filesystem-only tests using `tmp_path`; no network, time, or ordering dependencies.
- Dependency-missing paths are simulated with `monkeypatch` on `__import__` for deterministic failure coverage.

## Known gaps

- Route-specific artifact enforcement and step-local inventory qualification are intentionally deferred to later phases.
