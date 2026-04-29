# Test Strategy

- Task ID: full-revised-autoloop-v3-redesign-implementation-16af2351
- Pair: test
- Phase ID: canonical-surface-and-topology-lowering
- Phase Directory Key: canonical-surface-and-topology-lowering
- Phase Title: Canonical surface and topology lowering
- Scope: phase-local producer artifact

## Behavior Coverage Map

- AC-1 terminal/default-route surface:
  covered in `tests/unit/test_simple_surface.py` for `done -> FINISH`, `SUCCESS` compatibility, and custom-route no-implicit-`done` behavior.
- AC-2 canonical Python-step surface:
  covered in `tests/unit/test_simple_surface.py` for `python_step`, `system_step` alias compatibility, and `None` / `str` / `Event` return normalization.
- AC-3 deterministic topology lowering:
  covered in `tests/unit/test_simple_surface.py` for string forward refs, `SELF`, explicit entry, and first-declared entry behavior.
- AC-4 prompt contract:
  covered in `tests/unit/test_simple_surface.py` for `Prompt.inline`, `Prompt.file`, `Prompt.ref`, inferred reads, ambiguous/unknown placeholders, and the registry-prompt/local-file collision regression.
- AC-5 topology artifacts and public guidance:
  covered in `tests/runtime/test_runtime_static_graph.py`, `tests/runtime/test_package_cli.py`, and `tests/test_architecture_baseline_docs.py` for additive topology artifacts, canonical scaffold output, canonical prompt examples, and compatibility-fenced scoped-worklist guidance.

## Preserved Invariants Checked

- Legacy `SUCCESS`, `review_step`, `system_step`, `out`, and `outputs` compatibility remains accepted.
- Legacy static graph output remains present while topology sidecars are added.
- Public docs keep using `autoloop.simple` / `autoloop` imports instead of non-public module paths.

## Edge Cases And Failure Paths

- Prompt placeholder compile-time failure paths:
  unknown placeholders, ambiguous bare artifact names, and unresolved self-artifact references.
- Registry prompt edge case:
  compile-time analysis must not read a same-named workflow-local file for `Prompt.ref(...)`.
- Docs regression edge case:
  `Prompt("...")` shorthand must not reappear as a primary public example, and scoped `PairStep(...)` guidance must remain explicitly compatibility-fenced.

## Known Gaps

- This phase does not add new tests for later-phase state/item/meta prompt namespaces, hook semantics, or feedforward `llm()` / `classify()` operations because they are out of scope.
- Scoped worklist execution stays on existing strict-surface coverage; this phase only hardens the public-doc framing around that compatibility seam.
