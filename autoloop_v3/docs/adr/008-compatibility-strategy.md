# ADR 008: Compatibility Strategy For Legacy And Workspace Drift

- Decision name: compatibility strategy for legacy/workspace drift

## Candidate A

- Description: spread compatibility conditionals throughout the compiler, engine, stores, and runtime.
- correctness: possible, but drift handling becomes hard to reason about.
- compatibility: high in the short term because every layer can patch locally.
- simplicity: weak because rules are duplicated and hidden.
- extensibility: weak because each new drift case touches multiple modules.
- observability: weak because it is hard to tell which path is strict versus legacy.
- testability: weak because every core test must account for compatibility paths.
- failure handling: weak because legacy fallbacks can mask strict-mode bugs.
- performance: acceptable.
- migration risk: high because cleanup later is expensive.

## Candidate B

- Description: isolate compatibility in `runtime.loader` and `workflow.compat`, normalize once, then compile only strict workflow objects.
- correctness: strong because the core sees only one canonical model.
- compatibility: strong because loader and adapters can cover real workspace drift.
- simplicity: strong because strict and legacy paths are separated.
- extensibility: strong because new shims are added in one boundary.
- observability: strong because normalization outputs are inspectable.
- testability: strong because compatibility tests stay separate from core tests.
- failure handling: strong because unsupported drift fails at a single boundary.
- performance: strong because normalization happens once.
- migration risk: low.

## Candidate C

- Description: edit legacy workflow files in place until they match the strict v3 surface.
- correctness: possible, but it changes the oracle we are supposed to preserve.
- compatibility: weak because in-place edits can hide real compatibility gaps.
- simplicity: simple for a one-off migration, not for ongoing parity work.
- extensibility: weak because each new workspace workflow may need edits.
- observability: medium because the runtime becomes simpler, but history is lost.
- testability: weak because parity is no longer measured against untouched sources.
- failure handling: medium because fewer runtime shims exist, but breakage moves to source control.
- performance: acceptable.
- migration risk: high because it breaks the non-negotiable read-only oracle constraint.

## Selected Option

Candidate B.

## Why The Selected Option Is The Book Architecture Choice

It gives the core one strict truth while letting the runtime adapt real-world drift in a single, explicit boundary. That is the cleanest way to keep backward compatibility without sacrificing maintainability.
