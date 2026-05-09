# Test Strategy

- Task ID: botlane-internal-architecture-refactor-spec-this-3778d915
- Pair: test
- Phase ID: placeholder-reference-graph
- Phase Directory Key: placeholder-reference-graph
- Phase Title: Placeholder Reference Graph
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- Parser shape:
  `test_parse_placeholders_extracts_refs_exactly` checks `raw`, `root`, `path`, and `source` extraction for prompt/worklist placeholders.
- Compile-time validation parity:
  `test_validate_placeholder_ref_preserves_known_simple_prompt_surfaces` covers safe roots and inferred-read preservation for `ctx`, `input`, `params`, `state`, `worklist`, and prior-step artifact references.
- Branch/fan-in placement:
  `test_validate_placeholder_ref_preserves_branch_and_fan_in_placement_rules` covers both rejection outside allowed scope and acceptance when flags are enabled.
- Runtime rendering parity:
  `test_render_template_with_refs_preserves_runtime_behavior` covers mixed `ctx`, `input`, and unresolved branch placeholders.
  `test_render_placeholder_ref_preserves_runtime_resolution_behavior` covers direct helper behavior for scalar refs and unbound branch passthrough.
- Failure paths:
  `test_render_template_with_refs_preserves_error_quality` locks the existing unknown-input-field error text.
  `test_artifact_template_rejects_ctx_placeholders` locks `ctx.*` rejection in artifact paths.
- Internal value objects:
  `test_reference_graph_stores_placeholder_refs_and_inferred_reads` verifies `ReferenceGraph` stores parsed refs and `ArtifactId` payloads.
- Architecture invariants:
  `test_placeholders_module_does_not_import_context_at_runtime` checks the placeholder-module runtime import boundary.
  `test_artifacts_module_no_longer_defines_legacy_runtime_placeholder_helpers` locks the single-owner runtime placeholder implementation after the reviewer-found duplication issue.

## Preserved invariants checked

- No placeholder grammar expansion beyond currently supported forms.
- Existing validation and execution error wording remains stable on covered paths.
- Runtime branch placeholders remain brace-preserved when no branch context is active.
- Prompt-reference and artifact-path handling stay string-compatible at public boundaries.

## Edge cases

- Unresolved branch placeholder passthrough.
- Worklist payload placeholder parsing with deep paths.
- Safe-root direct helper rendering without template substitution.

## Failure paths

- Unknown runtime input field during rendering.
- `ctx.*` usage inside artifact templates.
- Branch/fan-in placeholders outside allowed compile-time scope.
- Runtime `Context` import leakage into `botlane/core/placeholders.py`.

## Flake risk / stabilization

- Tests are filesystem-local under `tmp_path` only; no network, time, or ordering dependence.
- AST-based architecture checks inspect source text directly to avoid import-side effects.

## Known gaps

- This phase-local file does not rerun the larger placeholder-adjacent suites itself; it relies on existing focused runtime/simple/context suites already exercised by the implementation pass for broader parity.
