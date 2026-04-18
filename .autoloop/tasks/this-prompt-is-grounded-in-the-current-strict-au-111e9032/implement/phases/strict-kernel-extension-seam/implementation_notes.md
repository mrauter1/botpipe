# Implementation Notes

- Task ID: this-prompt-is-grounded-in-the-current-strict-au-111e9032
- Pair: implement
- Phase ID: strict-kernel-extension-seam
- Phase Directory Key: strict-kernel-extension-seam
- Phase Title: Refactor The Strict Kernel
- Scope: phase-local producer artifact

## Files changed
- `autoloop_v3/workflow/{__init__.py,compiler.py,engine.py,extensions.py,primitives.py,validation.py}`
- `workflow/{__init__.py,primitives.py}`
- `autoloop_v3/runtime/runner.py`
- `autoloop_v3/workflows/autoloop_v1_parity.py`
- `autoloop_v3/tests/{contract/test_engine_contracts.py,runtime/test_compatibility_runtime.py,unit/test_primitives_and_stores.py,unit/test_validation.py}`
- `.autoloop/tasks/this-prompt-is-grounded-in-the-current-strict-au-111e9032/decisions.txt`

## Symbols touched
- `Workflow.extensions`
- `RunBinding`, `StepStart`, `StepFinish`, `TerminalFinish`, `WorkflowExtension`
- `WorkflowDefinition.extensions`, `CompiledWorkflow.extensions`
- `Engine.run`, `Engine.resume`, extension bind/notify helpers
- repo-root strict re-export shims in `workflow/`
- workflow-owned parity adapter classes in `autoloop_v1_parity.py`

## Checklist mapping
- AC-1 / plan step "Refactor strict workflow kernel and repo-root strict re-export surface": completed
- AC-2 / plan step "Replace observer-era contracts with workflow-declared extension seam in engine/tests": completed
- AC-3 / plan step "Validation, compilation, and engine behavior enforce explicit entry, strict handlers, typed checkpoints, required-artifact assertions, and deterministic routing": completed

## Assumptions
- Adding an optional `root` argument to `Engine.run` / `Engine.resume` is acceptable inside this phase because the extension seam requires `RunBinding.root` and the generic runner can provide the authoritative workspace root.

## Preserved invariants
- Explicit `entry`, strict handler arities, required system handlers, typed checkpoints, explicit session opening, required-artifact existence checks, and answer injection exactly once on resume remain intact.
- Root `workflow` and `workflow.primitives` now expose only the requested strict authoring surfaces.
- Autoloop-v1 parity workspace/session behavior remains workflow-owned; no phase semantics were pushed into the generic runtime.

## Intended behavior changes
- The kernel no longer supports observer-based execution hooks; `Workflow.extensions` is now the sole engine lifecycle seam.
- Bound extensions are strict by default and run in declaration order on step start, step finish, and terminal completion.

## Known non-changes
- Runtime CLI/config policy, generic extension packages, and workflow migrations outside the parity adapter needed to remove observer dependencies were not changed in this phase.

## Expected side effects
- `autoloop_v3/workflows/autoloop_v1_parity.py` now reconstructs parity from a workflow-owned provider wrapper plus bound parity extension so the observer-free kernel still supports existing parity tests.

## Validation performed
- `pytest autoloop_v3/tests`

## Deduplication / centralization
- Extension binding and lifecycle dispatch live entirely in `workflow.engine`; the repo-root shim only re-exports the narrowed strict surface.
- Parity-specific side effects were kept inside `autoloop_v3.workflows.autoloop_v1_parity` rather than reintroducing generic observer plumbing.
