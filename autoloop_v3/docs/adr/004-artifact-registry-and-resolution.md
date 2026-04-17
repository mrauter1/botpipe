# ADR 004: Artifact Registry And Resolution

- Decision name: artifact registry and resolution

## Candidate A

- Description: resolve artifact templates directly from raw strings each time a step runs.
- correctness: acceptable, but repeated string handling invites drift.
- compatibility: close to legacy expectations.
- simplicity: simple at first, then duplicated across step execution paths.
- extensibility: weak because ownership, ordering, and dependency checks are harder.
- observability: weak because there is no unified artifact graph.
- testability: medium because template resolution can be tested, but registry invariants cannot.
- failure handling: weaker because missing producers are easier to miss until runtime.
- performance: acceptable, but repetitive.
- migration risk: medium.

## Candidate B

- Description: compile workflow-level and step-level artifacts into an immutable registry, then resolve handles per execution with a shared resolver.
- correctness: strong because uniqueness, ordering, and dependency rules are validated centrally.
- compatibility: strong because authoring still uses `Artifact(...)` and step-produced attribute access.
- simplicity: strong because one resolver owns template expansion and handle creation.
- extensibility: strong because registry metadata can grow without changing handlers.
- observability: strong because the registry can be inspected and logged.
- testability: strong because compile-time and runtime resolution are separable.
- failure handling: strong because missing or cyclic dependencies are detected early.
- performance: strong because registry metadata is reused.
- migration risk: low.

## Candidate C

- Description: let workflows provide artifact path callbacks instead of templates.
- correctness: flexible, but shifts correctness burden to user code.
- compatibility: weak because existing workflows already use templates.
- simplicity: weaker because every workflow must re-implement path logic.
- extensibility: medium; callback power is high, but conventions degrade.
- observability: weaker because path derivation is imperative.
- testability: weaker because registry-wide guarantees disappear.
- failure handling: weaker because invalid paths surface late.
- performance: acceptable.
- migration risk: high because it changes the authoring model.

## Selected Option

Candidate B.

## Why The Selected Option Is The Book Architecture Choice

It treats artifacts as first-class compiled objects with explicit ownership, dependency, and resolution rules. That keeps path handling deterministic and makes phase-local scoping and compatibility behavior testable.
