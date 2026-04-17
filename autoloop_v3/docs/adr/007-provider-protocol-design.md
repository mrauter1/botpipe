# ADR 007: Provider Protocol Design

- Decision name: provider protocol design

## Candidate A

- Description: one generic `invoke()` method with role flags for producer, verifier, and llm steps.
- correctness: workable, but call contracts become flag-driven and easy to misuse.
- compatibility: flexible enough for legacy behavior.
- simplicity: simple signature, but complexity moves into branching payloads.
- extensibility: medium because new turn kinds increase flag combinations.
- observability: medium because request types are less explicit.
- testability: medium because fake providers must emulate many modes in one call.
- failure handling: medium because errors must explain which hidden mode failed.
- performance: acceptable.
- migration risk: medium.

## Candidate B

- Description: a typed `LLMProvider` protocol with explicit turn methods for producer, verifier, and llm calls, all returning typed response models with session updates and metadata.
- correctness: strong because each step contract maps to one explicit provider method.
- compatibility: strong because provider adapters can still wrap legacy CLI behavior.
- simplicity: strong because mode-specific fields stay in mode-specific requests.
- extensibility: strong because new request or response fields can evolve by type.
- observability: strong because request and response models are explicit.
- testability: strong because fakes can implement exact turn methods deterministically.
- failure handling: strong because errors are attributed to a precise turn kind.
- performance: strong enough; the extra typing cost is negligible.
- migration risk: low.

## Candidate C

- Description: embed provider-specific execution classes directly into step objects.
- correctness: workable, but step definitions become provider-aware.
- compatibility: medium because adapters can be attached, but the core is polluted.
- simplicity: weak because authoring and runtime concerns mix.
- extensibility: weak because adding providers touches workflow definitions.
- observability: medium.
- testability: weak because step tests need provider fixtures.
- failure handling: weak because provider errors leak through step internals.
- performance: acceptable.
- migration risk: high because provider concerns become part of the authoring API.

## Selected Option

Candidate B.

## Why The Selected Option Is The Book Architecture Choice

Explicit typed turn methods preserve the distinct contracts of `PairStep` and `LLMStep` without overloading the engine with provider-specific flags. The protocol stays small, clear, and easy to fake in tests.
