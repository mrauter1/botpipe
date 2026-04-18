# Test Strategy

- Task ID: this-prompt-is-grounded-in-the-current-strict-au-111e9032
- Pair: test
- Phase ID: strict-kernel-extension-seam
- Phase Directory Key: strict-kernel-extension-seam
- Phase Title: Refactor The Strict Kernel
- Scope: phase-local producer artifact

## Behavior-to-test coverage map

- AC-1 `autoloop_v3.workflow` / repo-root `workflow` strict surface:
  - `autoloop_v3/tests/unit/test_primitives_and_stores.py`
  - `autoloop_v3/tests/unit/test_validation.py`
  - `autoloop_v3/tests/contract/test_engine_contracts.py::test_extension_core_modules_remain_autoloop_agnostic`
- AC-2 workflow-declared extension seam:
  - bind once per run and preserve tuple order
  - pass structured `StepStart`, `StepFinish`, and `TerminalFinish`
  - clone state and outcome snapshots so extensions cannot mutate execution state
  - reject malformed bound extensions returned from `bind()` before any step executes
  - surface pause/fail/fatal terminal notifications
- AC-3 strict validation / compilation / engine contracts:
  - explicit entry and strict handler signatures
  - `SystemStep` handler requirement
  - optional `PairStep` / `LLMStep` outcome handlers
  - deterministic routing and deterministic compilation
  - explicit session opening; missing sessions fail clearly
  - required-artifact existence assertions
  - pause/resume answer injection exactly once
  - failure checkpoint capture for handler and extension exceptions

## Edge cases and failure paths

- Non-tuple `extensions` and extensions without `bind()` rejected at validation time.
- Bound extension objects missing required hook methods rejected at engine bind time.
- Extension hook failures checkpoint the latest state and still emit a fatal terminal event.
- Missing required artifacts and missing session bindings fail before hidden fallback behavior.

## Preserved invariants checked

- No observer-era Autoloop-specific names remain in kernel extension modules.
- Extensions observe only; they do not change workflow routing or live state.
- System steps do not invoke middleware.
- Checkpoints remain typed and resume uses the saved checkpoint state.

## Stability notes

- All coverage uses in-memory stores, scripted providers, and temporary directories.
- No network, timing, or nondeterministic ordering dependencies are introduced.

## Known gaps

- Runtime CLI/config wiring, workflow-owned parity policy details, and git policy remain out of phase scope.
