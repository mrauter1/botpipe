# ADR 009: Handler Dispatch And Signature Adaptation

- Decision name: handler dispatch and signature adaptation

## Candidate A

- Description: inspect handler signatures at every invocation and branch dynamically.
- correctness: workable, but repeated reflection increases edge-case risk.
- compatibility: high because ad hoc legacy forms are easy to accept.
- simplicity: weak because invocation logic becomes noisy.
- extensibility: weak because every new accepted arity grows runtime branching.
- observability: medium because dispatch can log reflected signatures.
- testability: medium because dispatch rules are executable but not compiled.
- failure handling: medium because bad signatures are caught only at first call.
- performance: acceptable, but reflection repeats.
- migration risk: medium.

## Candidate B

- Description: resolve handlers during compilation into normalized call adapters with explicit accepted signatures and strict runtime call sites.
- correctness: strong because invalid signatures fail before execution.
- compatibility: strong because legacy pair, llm, and system handler forms can be adapted once.
- simplicity: strong because the engine only calls normalized adapters.
- extensibility: strong because new compatibility rules stay in adapter construction.
- observability: strong because compiled handlers can record which form was selected.
- testability: strong because adapter resolution is independently testable.
- failure handling: strong because orphan or invalid handlers fail early.
- performance: strong because no repeated reflection occurs at runtime.
- migration risk: low.

## Candidate C

- Description: require only strict signatures and reject all legacy handler forms.
- correctness: strong for new workflows, but incompatible with the required workspace targets.
- compatibility: weak because `autoloop_v1.py` and `Ralph_loop.py` would fail.
- simplicity: strong for the engine, but only by dropping scope.
- extensibility: medium.
- observability: strong because there is only one path.
- testability: strong for strict-mode only.
- failure handling: strong because mismatches fail immediately.
- performance: strong.
- migration risk: high because it violates the compatibility requirement.

## Selected Option

Candidate B.

## Why The Selected Option Is The Book Architecture Choice

Compile-time adapter selection keeps the engine simple and deterministic while still covering the real legacy handler drift already present in the workspace workflows.
