# ADR 011: Validation Architecture

- Decision name: validation architecture

## Candidate A

- Description: validate workflow classes at definition time through `Workflow` subclass machinery, using a reusable validator that can also validate normalized classes from the compat loader.
- correctness: strong because invalid workflows fail early.
- compatibility: strong because normalized legacy workflows can still pass through the same validator.
- simplicity: strong because there is one validation policy reused at load time.
- extensibility: strong because new validation rules remain centralized.
- observability: strong because validation errors are explicit and contextual.
- testability: strong because every rule can be unit tested against class definitions.
- failure handling: strong because broken definitions fail before execution.
- performance: strong because validation runs once.
- migration risk: low.

## Candidate B

- Description: validate only during explicit compilation, not when classes are defined.
- correctness: medium because invalid definitions survive longer.
- compatibility: strong enough for loader-based normalization.
- simplicity: medium because author errors appear later in the lifecycle.
- extensibility: strong.
- observability: medium because invalid definitions may sit unnoticed until execution.
- testability: strong.
- failure handling: medium because failures move from import time to runtime setup.
- performance: strong.
- migration risk: medium.

## Candidate C

- Description: rely on runtime assertions inside the engine when a bad workflow shape is encountered.
- correctness: weak because many errors surface only after execution begins.
- compatibility: medium because permissiveness helps legacy imports.
- simplicity: weak because validation becomes scattered.
- extensibility: weak because every engine path grows more guards.
- observability: weak because failures happen far from the source definition.
- testability: weak because invalid cases require step execution.
- failure handling: weak because partially executed runs can fail late.
- performance: acceptable.
- migration risk: high because moving to stronger validation later is disruptive.

## Selected Option

Candidate A.

## Why The Selected Option Is The Book Architecture Choice

Definition-time validation keeps contracts explicit and catches authoring errors before execution. Reusing the same validator after compatibility normalization preserves one coherent rule set without scattering validation logic.
