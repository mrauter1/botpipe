# ADR 001: Package And Module Layout

- Decision name: package/module layout

## Candidate A

- Description: keep almost all logic in one runtime package with light helper modules.
- correctness: workable, but core and runtime concerns would mix quickly.
- compatibility: legacy behavior is easy to bolt on, but isolation is weak.
- simplicity: simple at the start, then degrades as features accumulate.
- extensibility: weak because core contracts and workspace adapters live together.
- observability: runtime logging is easy to wire, but boundaries are unclear.
- testability: weaker because unit tests must import workspace-heavy modules.
- failure handling: harder to reason about because failure policy is distributed.
- performance: fine for this scale.
- migration risk: medium because later separation would be invasive.

## Candidate B

- Description: split strict `workflow` core from `runtime` adapters, with a thin repo-root `workflow` compatibility shim.
- correctness: strong because contracts live in one strict core and adapters stay outside it.
- compatibility: strong because legacy behavior can be handled at loader and compat boundaries.
- simplicity: strong after the initial structure because responsibilities are explicit.
- extensibility: strong because providers, stores, and loaders extend at the edges.
- observability: strong because runtime logging and engine events each have a clear owner.
- testability: strong because the core can be tested with in-memory fakes.
- failure handling: strong because engine and runtime failure modes are separated cleanly.
- performance: fine; compile once and run many keeps overhead low.
- migration risk: low because the shim can preserve imports while internals evolve.

## Candidate C

- Description: split every concern into many micro-packages from the start.
- correctness: strong in theory, but coordination overhead raises accidental complexity.
- compatibility: possible, but the boundary count is high.
- simplicity: weak because the problem size does not justify that many seams yet.
- extensibility: strong, but over-abstracted for the current workspace.
- observability: fragmented because state spans many packages.
- testability: good in isolation, but expensive in integration.
- failure handling: can be clean, but tracing across packages is slower.
- performance: neutral.
- migration risk: medium because early over-segmentation may lock in awkward APIs.

## Selected Option

Candidate B.

## Why The Selected Option Is The Book Architecture Choice

It creates one clean strict core, one explicit runtime boundary, and one compatibility shim for import ergonomics. That is the smallest structure that keeps invariants explicit and keeps workspace drift from contaminating the engine.
