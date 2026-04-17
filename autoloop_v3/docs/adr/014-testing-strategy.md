# ADR 014: Testing Strategy

- Decision name: testing strategy

## Candidate A

- Description: focus mostly on end-to-end workflow runs and a few smoke tests.
- correctness: medium because broad scenarios run, but many invariants are under-specified.
- compatibility: medium because some parity issues will be caught.
- simplicity: simple test authoring, but diagnosis is slow.
- extensibility: weak because every new case needs a large fixture.
- observability: medium because failures are broad and noisy.
- testability: weak because unit-level regressions are hard to isolate.
- failure handling: medium because some edge cases are covered, many are not.
- performance: weak because the suite becomes slow quickly.
- migration risk: medium.

## Candidate B

- Description: use a test pyramid with unit tests for primitives and stores, contract tests for steps and routing, filesystem integration tests for the runtime, and golden or parity tests for legacy workflows.
- correctness: strong because invariants and end-to-end behavior are both covered.
- compatibility: strong because legacy workflows and runtime artifacts get explicit parity coverage.
- simplicity: strong because each test type has a clear purpose.
- extensibility: strong because new features slot into the right test layer.
- observability: strong because failures point to the broken layer.
- testability: strong because fakes keep most tests deterministic.
- failure handling: strong because failure paths can be targeted precisely.
- performance: strong because only a small subset of tests need filesystem or end-to-end execution.
- migration risk: low.

## Candidate C

- Description: rely mainly on snapshot tests for docs, compiled graphs, and logs.
- correctness: medium because snapshots catch shape changes, not always semantic bugs.
- compatibility: medium because outputs can be compared, but behavior gaps may hide.
- simplicity: medium; snapshots are easy to record but costly to review.
- extensibility: medium.
- observability: medium because diffs show changes, not intent.
- testability: medium because dynamic behavior still needs imperative tests.
- failure handling: weak because exceptional paths are awkward to encode as snapshots.
- performance: strong.
- migration risk: medium because snapshot churn can normalize regressions.

## Selected Option

Candidate B.

## Why The Selected Option Is The Book Architecture Choice

The problem has both strict engine invariants and legacy parity obligations. A layered test strategy is the only approach that keeps the suite fast, diagnostic, and strong enough to prove compatibility without relying on a few oversized end-to-end runs.
