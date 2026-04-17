# ADR 003: Topology And Routing Representation

- Decision name: topology/routing representation

## Candidate A

- Description: keep the author-declared `transitions` dict and resolve destinations dynamically from raw step objects.
- correctness: acceptable, but repeated object-identity lookups are fragile.
- compatibility: close to existing authoring style.
- simplicity: simple for authors, less simple for the engine.
- extensibility: medium; adding global routes or metadata increases runtime branching.
- observability: medium because the runtime graph is not normalized.
- testability: medium because route resolution is intertwined with step instances.
- failure handling: route errors surface at execution time.
- performance: acceptable.
- migration risk: medium because later normalization changes internals substantially.

## Candidate B

- Description: compile routes into a normalized table keyed by `step_name` and `tag`, with explicit terminal destinations and `GLOBAL` fallback.
- correctness: strong because every destination is validated once.
- compatibility: strong because authors still write the same `transitions` shape.
- simplicity: strong because routing becomes a pure lookup.
- extensibility: strong because route metadata can be added without changing authorship.
- observability: strong because the compiled graph is explicit.
- testability: strong because routing tests can assert compiled tables directly.
- failure handling: strong because missing destinations become explicit runtime errors with context.
- performance: strong because routing is constant-time lookup.
- migration risk: low.

## Candidate C

- Description: replace the transition table with per-step imperative `next()` callbacks.
- correctness: flexible, but easier to make inconsistent across steps.
- compatibility: weak because it changes the authoring surface.
- simplicity: weak because routing logic becomes distributed code.
- extensibility: medium; custom logic is powerful but less uniform.
- observability: weak because there is no single graph to inspect.
- testability: weaker because topology must be inferred from behavior.
- failure handling: weaker because unreachable states become harder to detect statically.
- performance: acceptable.
- migration risk: high because it breaks the declared topology model.

## Selected Option

Candidate B.

## Why The Selected Option Is The Book Architecture Choice

The compiled route table preserves the existing authoring surface while making execution deterministic, inspectable, and easy to validate. It keeps routing declarative instead of scattering it through handlers.
