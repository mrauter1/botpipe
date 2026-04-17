# ADR 002: Workflow Compilation Model

- Decision name: workflow compilation model

## Candidate A

- Description: interpret workflow class attributes directly on every step execution.
- correctness: acceptable, but repeated reflection increases edge-case risk.
- compatibility: easy to patch dynamically.
- simplicity: initially simple, then reflection rules become scattered.
- extensibility: weak because every new rule expands runtime reflection logic.
- observability: weaker because compiled structure does not exist to inspect.
- testability: weaker because validation and execution stay tightly coupled.
- failure handling: runtime-only failures arrive late.
- performance: acceptable for small workflows, but repeated introspection is wasteful.
- migration risk: medium because introducing compilation later would change behavior.

## Candidate B

- Description: normalize once, validate once, then compile into an immutable `CompiledWorkflow`.
- correctness: strong because routing, artifacts, handlers, and sessions are frozen before execution.
- compatibility: strong because legacy shims can normalize before compilation.
- simplicity: strong because the engine consumes one deterministic shape.
- extensibility: strong because new step kinds or registries attach to the compiled model.
- observability: strong because compiled graphs and registries are inspectable.
- testability: strong because compile output can be unit tested directly.
- failure handling: strong because many failures move to load time.
- performance: strong because reflection happens once.
- migration risk: low because the compiled form is internal and can evolve under stable authoring APIs.

## Candidate C

- Description: code-generate Python execution code from workflow definitions.
- correctness: potentially high, but generator bugs add another correctness surface.
- compatibility: weaker because legacy drift becomes harder to normalize cleanly.
- simplicity: weak because the generator is more complex than the problem requires.
- extensibility: medium; new features require generator updates.
- observability: medium because generated code is inspectable but indirect.
- testability: weaker because failures may sit in generated code paths.
- failure handling: compile failures can be explicit, but debugging is heavier.
- performance: strong.
- migration risk: high because code generation would be a large architectural commitment.

## Selected Option

Candidate B.

## Why The Selected Option Is The Book Architecture Choice

An immutable compiled model is the clearest way to make workflow execution deterministic, testable, and independent from legacy authoring drift. It creates explicit contracts without introducing code-generation complexity.
