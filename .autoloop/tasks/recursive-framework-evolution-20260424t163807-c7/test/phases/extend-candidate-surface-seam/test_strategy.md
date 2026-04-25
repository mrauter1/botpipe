# Test Strategy

- Task ID: recursive-framework-evolution-20260424t163807-c7
- Pair: test
- Phase ID: extend-candidate-surface-seam
- Phase Directory Key: extend-candidate-surface-seam
- Phase Title: Extend Candidate Surface Seam
- Scope: phase-local producer artifact

## Behavior coverage map

- Shared baseline manifest validation:
  - happy path: boundary-aligned manifest validates and returns normalized file metadata
  - failure paths: mismatched boundary field and copied-surface digest drift both fail deterministically
- Shared candidate manifest validation:
  - happy path: boundary-aligned candidate manifest validates and returns normalized file metadata
  - edge case: optional exact-path allowances may contain `None` without widening the allowed boundary
  - failure paths: out-of-bound added file and candidate-surface digest drift both fail deterministically
- Shared overlay normalization:
  - happy paths: single-workflow and multi-workflow receipt shapes normalize correctly
  - failure paths: single-workflow mode rejects multiple compiled workflows; normalization rejects negative return codes

## Preserved invariants checked

- The shared seam remains authoring-only and unit-scoped in this phase
- Candidate boundary validation still preserves every baseline relative path
- Digest checks still bind baseline and candidate manifests to the copied surfaces
- Overlay normalization still preserves the original test command and return code fields

## Edge cases

- Optional doc/runtime-test exact-path allowances forwarded as `None`
- Multi-workflow overlay validation receipts for decomposition-style callers

## Failure paths

- Boundary field mismatch
- Out-of-bound candidate path addition
- Baseline copied-surface digest drift
- Candidate copied-surface digest drift
- Invalid overlay normalization shape for single-workflow receipts
- Invalid negative overlay return code

## Flake risk and stabilization

- No timing, network, or external process nondeterminism added beyond the existing mocked overlay test path
- Overlay validation continues to monkeypatch compiler/loader/subprocess seams so the tests stay deterministic

## Known gaps

- No runtime workflow tests were added in this phase because the refinement and decomposition callers are intentionally unchanged here
- Caller migration and runtime regression proof remain for the later `migrate-refinement-decomposition-callers` phase
