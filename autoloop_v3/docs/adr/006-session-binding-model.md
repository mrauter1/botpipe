# ADR 006: Session Binding Model

- Decision name: session binding model

## Candidate A

- Description: store concrete session ids directly inside workflow state.
- correctness: workable, but state stops being pure workflow state.
- compatibility: medium because legacy runs do persist session data, but outside workflow state.
- simplicity: simple for handlers, weak for clean architecture.
- extensibility: weak because provider metadata leaks into state schemas.
- observability: medium because state dumps include session info.
- testability: weaker because state assertions become provider-specific.
- failure handling: weaker because state persistence and session persistence are coupled.
- performance: acceptable.
- migration risk: high because workflow state becomes a compatibility burden.

## Candidate B

- Description: compile declared `Session` slots and persist concrete bindings externally in a `SessionStore`, keyed by slot and optional scope.
- correctness: strong because state remains pure while session bindings remain explicit.
- compatibility: strong because plan and phase session files already live outside workflow state.
- simplicity: strong because `Context` exposes the same binding model to all step kinds.
- extensibility: strong because scopes, providers, and metadata evolve without changing state.
- observability: strong because bindings are inspectable separately from state.
- testability: strong because in-memory session stores are trivial to fake.
- failure handling: strong because session recovery does not require mutating workflow state.
- performance: strong because lookups are simple key resolution.
- migration risk: low.

## Candidate C

- Description: keep a global in-process session manager keyed by step name.
- correctness: weak for resume and multi-run safety.
- compatibility: weak because persisted run state is required.
- simplicity: simple only for single-process prototypes.
- extensibility: weak because scoping and persistence must be added later.
- observability: weak because bindings are process-local.
- testability: weak because tests must manage global state.
- failure handling: weak because process death loses sessions.
- performance: strong.
- migration risk: high because persistence would require redesign.

## Selected Option

Candidate B.

## Why The Selected Option Is The Book Architecture Choice

It keeps workflow state immutable and portable while making concrete sessions explicit runtime bindings. That matches the spec and the legacy workspace layout without mixing provider concerns into the core model.
