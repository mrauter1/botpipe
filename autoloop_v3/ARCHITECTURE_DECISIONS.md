# Architecture Decisions

This record freezes the target architecture for the final `autoloop_v3` framework. It is written against the current `autoloop_v3` codebase, the repo-root workflows, the current docs and tests, and the legacy `autoloop/` runtime used as the Autoloop-v1 parity oracle.

The evaluation dimensions are the same for every decision:

- correctness
- simplicity
- extensibility
- observability
- testability
- migration risk
- parity impact

## 1. Package / Module Layout

### Candidate A: Keep the current split and retain `workflow.compat`
- correctness: medium; correctness depends on normalization staying aligned with strict execution.
- simplicity: low; the compatibility seam duplicates meaning across loader, validation, compiler, and docs.
- extensibility: low; new features must decide whether they belong to strict code, compat code, or both.
- observability: medium; behavior is inspectable, but the source of a behavior is hard to localize.
- testability: medium; compat behavior requires parallel proof paths.
- migration risk: low; least disruptive to the current tree.
- parity impact: high; parity is easy in the short term because drift stays tolerated.

### Candidate B: Keep `autoloop_v3.workflow` as the strict core, keep `autoloop_v3.runtime` generic, and move Autoloop-v1 parity behavior into workflow-owned modules
- correctness: high; the engine only executes canonical definitions, while parity behavior lives next to the workflow that needs it.
- simplicity: high; each layer has one job.
- extensibility: high; new workflows reuse the core without inheriting Autoloop-v1 policy.
- observability: high; side effects are owned either by the generic runtime or by the workflow harness.
- testability: high; engine, runtime, and workflow-owned parity helpers can be tested separately.
- migration risk: medium; requires moving behavior instead of merely deleting it.
- parity impact: high; parity stays possible without corrupting the core.

### Candidate C: Collapse runtime and workflow-specific behavior into a single Autoloop-first package
- correctness: medium; fewer boundaries, but runtime becomes domain-aware.
- simplicity: medium at first, low over time; one package is easy to start but hard to keep generic.
- extensibility: low; every new workflow inherits Autoloop-v1 structure.
- observability: medium; everything is colocated, but concerns are mixed.
- testability: medium; end-to-end tests dominate.
- migration risk: medium.
- parity impact: high for Autoloop-v1, low for every other workflow.

Decision: Candidate B.

Book choice: the clean shape is a strict engine plus a generic runtime plus workflow-owned parity helpers. It is the shortest explanation that still preserves Autoloop-v1.

Why the others lost: Candidate A preserves too much duplicated meaning. Candidate C gives up the workflow-agnostic runtime requirement.

## 2. Canonical Public API Surface

### Candidate A: Keep the existing surface, including `Verdict`, `SessionLifecycle`, and loader-assisted authoring
- correctness: medium; the public surface advertises contracts the strict core should not honor.
- simplicity: low; extra names imply extra semantics.
- extensibility: low; future workflows can keep depending on drift.
- observability: medium.
- testability: medium; alias paths need duplicate tests.
- migration risk: low.
- parity impact: high.

### Candidate B: Publish a minimal strict surface: `Workflow`, `Context`, `Session`, `Artifact`, `Prompt`, `PairStep`, `LLMStep`, `SystemStep`, `Event`, `Outcome`, `SUCCESS`, `PAUSE`, `FAIL`, `GLOBAL`, `Checkpoint`, and `ResolvedArtifacts`
- correctness: high; the public surface matches the real engine contract.
- simplicity: high; one meaning per name.
- extensibility: high; new helpers can be built outside the core.
- observability: high; there is no hidden alias path.
- testability: high; one contract per concept.
- migration risk: medium; workflows must import the actual names they use.
- parity impact: medium; parity must come from migrated workflows, not aliases.

### Candidate C: Shrink the public surface further by hiding `Context`, `Checkpoint`, and `ResolvedArtifacts`
- correctness: medium; runtime hooks still need explicit side-effect access.
- simplicity: medium; smaller API, but it forces informal escape hatches.
- extensibility: medium.
- observability: low; hidden helper access moves into ad hoc utilities.
- testability: medium.
- migration risk: medium.
- parity impact: low; Autoloop-v1 needs explicit runtime context.

Decision: Candidate B.

Book choice: the minimal stable surface is the canonical primitives plus the explicit runtime context. It is small without being evasive.

Why the others lost: Candidate A leaves compatibility drift in the public contract. Candidate C hides concepts that workflows genuinely need.

## 3. Compatibility Removal Strategy

### Candidate A: Preserve compatibility behind a renamed module or hidden compiler branch
- correctness: low; hidden compatibility is still compatibility.
- simplicity: low.
- extensibility: low.
- observability: low; users cannot tell why malformed workflows still work.
- testability: low; absence is impossible to prove.
- migration risk: low.
- parity impact: high.

### Candidate B: Delete `workflow.compat`, delete alias-based middleware and arity adaptation, delete entry inference, and make workflows compile only when already canonical
- correctness: high.
- simplicity: high.
- extensibility: high; the core only grows along canonical lines.
- observability: high; any drift is now a validation error.
- testability: high; no-compat invariants are directly provable.
- migration risk: medium.
- parity impact: medium; parity shifts into workflow migration work.

### Candidate C: Keep compatibility only in the loader by rewriting modules before import
- correctness: medium; the drift moves earlier but still exists.
- simplicity: low; import-time rewriting is more magical than normalization.
- extensibility: low.
- observability: low.
- testability: medium.
- migration risk: medium.
- parity impact: high.

Decision: Candidate B.

Book choice: deletion is the only architecture that actually removes compat. Anything else is a disguised compatibility layer.

Why the others lost: Candidate A violates the request directly. Candidate C is even more hidden than the current design.

## 4. Workflow Migration Strategy

### Candidate A: Let workflows stay mostly unchanged and rely on framework tolerance
- correctness: low; framework tolerance becomes architecture.
- simplicity: low.
- extensibility: low.
- observability: medium.
- testability: low.
- migration risk: low in the short term.
- parity impact: high.

### Candidate B: Rewrite each in-scope workflow to the canonical surface and keep workflow-specific policy inside workflow-owned helpers
- correctness: high.
- simplicity: high; workflow code becomes readable without hidden framework rules.
- extensibility: high; new workflows copy the strict pattern, not a shim.
- observability: high.
- testability: high; workflow behavior is visible in workflow code.
- migration risk: medium.
- parity impact: high.

### Candidate C: Generate canonical wrappers around non-canonical workflows
- correctness: medium.
- simplicity: medium at first, low once wrappers diverge from sources.
- extensibility: medium.
- observability: low; actual behavior lives in generated glue.
- testability: medium.
- migration risk: medium.
- parity impact: high.

Decision: Candidate B.

Book choice: the cleanest architecture is to make the workflows real workflows. Anything else preserves authoring drift as a system feature.

Why the others lost: Candidate A keeps the core permissive. Candidate C replaces explicit migration with another layer of machinery.

## 5. Session Model

### Candidate A: Compute session identity from workflow state or step-time templates
- correctness: low; session identity becomes an implicit derivation rule.
- simplicity: low.
- extensibility: medium; flexible, but too magical.
- observability: low; sharing is discovered indirectly.
- testability: low; identity bugs are timing-dependent.
- migration risk: medium.
- parity impact: medium; can emulate legacy, but opaquely.

### Candidate B: Declare session slots, open them explicitly with `ctx.open_session(...)`, and look them up directly with `ctx.get_session(...)`
- correctness: high; session lifetime is explicit.
- simplicity: high; the engine does lookup, not inference.
- extensibility: high; rebinding is obvious and generic.
- observability: high; topology plus open points show sharing.
- testability: high; missing-open and rebinding behavior are deterministic.
- migration risk: medium.
- parity impact: high; plan and phase sessions map directly to Autoloop-v1 behavior.

### Candidate C: Use runtime-managed automatic slot opening with optional overrides
- correctness: medium; safer than full derivation, but still implicit.
- simplicity: medium.
- extensibility: medium.
- observability: medium.
- testability: medium.
- migration risk: low.
- parity impact: high.

Decision: Candidate B.

Book choice: “sessions are created, not computed” is the crisp model. It explains sharing, rebinding, and missing-session failures in one sentence.

Why the others lost: Candidate A hides identity. Candidate C hides lifecycle.

## 6. Artifact Registry And Resolution

### Candidate A: Keep ad hoc artifact paths on steps and let handlers resolve files manually
- correctness: medium; works, but no global inventory.
- simplicity: medium at first, low in larger workflows.
- extensibility: low.
- observability: low; it is hard to know what artifacts exist.
- testability: medium.
- migration risk: low.
- parity impact: medium.

### Candidate B: Compile a workflow-wide artifact registry from workflow-level and step-level declarations, then resolve path templates generically at runtime
- correctness: high.
- simplicity: high; one artifact model for all steps.
- extensibility: high; reusable without workflow leakage.
- observability: high; the registry is inspectable.
- testability: high; resolution and dependency errors are deterministic.
- migration risk: medium.
- parity impact: high; phase-local path templates stay workflow-owned but use the same resolver.

### Candidate C: Move artifact management fully into the runtime workspace layer
- correctness: medium; runtime gains too much workflow knowledge.
- simplicity: low.
- extensibility: low.
- observability: medium.
- testability: medium.
- migration risk: medium.
- parity impact: high for Autoloop-v1, low elsewhere.

Decision: Candidate B.

Book choice: artifacts are part of workflow semantics, so they belong in compilation plus a generic resolver, not in hand-written handlers or a domain-aware runtime.

Why the others lost: Candidate A has no crisp contract. Candidate C pollutes the runtime with workflow structure.

## 7. Prompt Model

### Candidate A: Allow arbitrary strings, loader hacks, and path fallbacks
- correctness: medium; prompts resolve eventually, but with hidden rules.
- simplicity: low.
- extensibility: medium.
- observability: low.
- testability: medium.
- migration risk: low.
- parity impact: high.

### Candidate B: Keep a canonical `Prompt` concept and also allow plain string prompt paths as an intentional documented shorthand
- correctness: high.
- simplicity: high.
- extensibility: high; registries can resolve either form cleanly.
- observability: high; the resolution path is explicit.
- testability: high.
- migration risk: low; current strict workflows already fit this.
- parity impact: high.

### Candidate C: Require `Prompt(...)` objects everywhere
- correctness: high.
- simplicity: medium; explicit but noisy.
- extensibility: high.
- observability: high.
- testability: high.
- migration risk: medium.
- parity impact: medium.

Decision: Candidate B.

Book choice: prompt paths should be explicit, but the syntax does not need ceremony. A documented string shorthand keeps the surface small.

Why the others lost: Candidate A depends on hidden resolution. Candidate C adds syntax without architectural gain.

## 8. Workflow Compilation And Validation Model

### Candidate A: Validate loosely and normalize at compile time
- correctness: medium.
- simplicity: low; compilation has to interpret malformed authoring.
- extensibility: low.
- observability: low.
- testability: medium.
- migration risk: low.
- parity impact: high.

### Candidate B: Validate strictly at definition time, compile only canonical definitions, and require exact handler signatures
- correctness: high.
- simplicity: high.
- extensibility: high.
- observability: high; errors occur at the boundary.
- testability: high.
- migration risk: medium.
- parity impact: medium; migrated workflows must be explicit.

### Candidate C: Move most validation to runtime execution
- correctness: low; errors arrive too late.
- simplicity: medium in code, low in system behavior.
- extensibility: low.
- observability: low.
- testability: low.
- migration risk: medium.
- parity impact: medium.

Decision: Candidate B.

Book choice: definition-time rejection of malformed workflows is the shortest path to deterministic behavior.

Why the others lost: Candidate A preserves drift. Candidate C turns authoring errors into runtime failures.

## 9. Checkpoint Model

### Candidate A: Keep checkpointing as event reconstruction only
- correctness: medium; event logs are valuable but indirect.
- simplicity: medium.
- extensibility: medium.
- observability: high for history, low for exact resume state.
- testability: medium.
- migration risk: low.
- parity impact: high because legacy does this.

### Candidate B: Use a typed checkpoint snapshot containing stage, state, session bindings, pending question, and pending answer
- correctness: high.
- simplicity: high.
- extensibility: high.
- observability: high; resume state is explicit.
- testability: high.
- migration risk: medium.
- parity impact: high; parity tests can compare snapshot side effects and event logs separately.

### Candidate C: Checkpoint only opaque runtime blobs from the provider layer
- correctness: low; workflow semantics become provider-coupled.
- simplicity: medium.
- extensibility: low.
- observability: low.
- testability: low.
- migration risk: medium.
- parity impact: low.

Decision: Candidate B.

Book choice: a typed checkpoint is the smallest object that fully explains pause and resume.

Why the others lost: Candidate A is not enough for generic deterministic resume. Candidate C gives ownership of workflow state to the wrong layer.

## 10. Provider / Store Protocol Design

### Candidate A: Keep rich provider and store interfaces with Autoloop-specific helpers built in
- correctness: medium.
- simplicity: low.
- extensibility: medium.
- observability: medium.
- testability: medium.
- migration risk: low.
- parity impact: high.

### Candidate B: Keep tiny typed protocols: provider requests and responses, session store, checkpoint store, prompt registry
- correctness: high.
- simplicity: high.
- extensibility: high.
- observability: high; adapter boundaries are explicit.
- testability: high; fakes are trivial.
- migration risk: medium.
- parity impact: high; filesystem implementations can still preserve required payload shapes.

### Candidate C: Hide adapters behind one monolithic runtime service object
- correctness: medium.
- simplicity: medium at first, low as behavior grows.
- extensibility: low.
- observability: low.
- testability: low.
- migration risk: medium.
- parity impact: medium.

Decision: Candidate B.

Book choice: small protocols give the engine a crisp dependency set and keep adapters replaceable.

Why the others lost: Candidate A leaks policy into protocols. Candidate C creates a god object.

## 11. Runtime Harness Design

### Candidate A: Keep the current runtime as a mixed generic-and-Autoloop orchestration layer
- correctness: medium.
- simplicity: low.
- extensibility: low.
- observability: medium.
- testability: medium.
- migration risk: low.
- parity impact: high.

### Candidate B: Reduce `autoloop_v3.runtime` to a generic filesystem harness and move Autoloop-v1-specific workspace and orchestration rules into workflow-owned helpers
- correctness: high.
- simplicity: high.
- extensibility: high.
- observability: high.
- testability: high.
- migration risk: medium.
- parity impact: high.

### Candidate C: Remove the runtime harness entirely and force each workflow to own all filesystem concerns
- correctness: medium.
- simplicity: medium for one workflow, low for many.
- extensibility: low; common concerns duplicate immediately.
- observability: medium.
- testability: medium.
- migration risk: high.
- parity impact: medium.

Decision: Candidate B.

Book choice: the runtime should own only generic run mechanics, not workflow topology or policy.

Why the others lost: Candidate A keeps leakage. Candidate C abandons reusable infrastructure too aggressively.

## 12. Configuration Design

### Candidate A: Encode workflow policy as runtime config flags
- correctness: medium.
- simplicity: low; config becomes a hidden orchestration language.
- extensibility: low.
- observability: low.
- testability: medium.
- migration risk: low.
- parity impact: high.

### Candidate B: Keep configuration only for generic policy and adapter wiring, and keep workflow-specific behavior in workflow code
- correctness: high.
- simplicity: high.
- extensibility: high.
- observability: high.
- testability: high.
- migration risk: medium.
- parity impact: high.

### Candidate C: Remove nearly all configuration and hardcode policy in runtime defaults
- correctness: medium.
- simplicity: medium.
- extensibility: low.
- observability: medium.
- testability: medium.
- migration risk: medium.
- parity impact: low.

Decision: Candidate B.

Book choice: configuration should tune generic policy, not smuggle workflow semantics into the runtime.

Why the others lost: Candidate A turns the runtime into a policy engine. Candidate C overcorrects and removes useful generic knobs.

## 13. Git Policy Placement

### Candidate A: Keep git init, tracking, and artifact-commit policy in the generic runtime
- correctness: medium; it works for Autoloop-v1 but couples the runtime to one workflow’s operational model.
- simplicity: low.
- extensibility: low.
- observability: medium.
- testability: medium.
- migration risk: low.
- parity impact: high.

### Candidate B: Keep generic git utilities reusable, but keep git policy and `track_autoloop_artifacts` in the Autoloop-v1 harness if parity still requires them
- correctness: high.
- simplicity: high.
- extensibility: high; other workflows opt in explicitly.
- observability: high; policy is visible where it is used.
- testability: high.
- migration risk: medium.
- parity impact: high.

### Candidate C: Remove git support entirely from the final system
- correctness: medium.
- simplicity: high.
- extensibility: medium.
- observability: medium.
- testability: high.
- migration risk: medium.
- parity impact: low; legacy behavior would regress.

Decision: Candidate B.

Book choice: git is policy, not architecture. The framework may offer tools, but only the workflow harness should decide when to use them.

Why the others lost: Candidate A violates the runtime boundary. Candidate C drops important parity behavior too early.

## 14. Observability / Event Model

### Candidate A: Let each workflow invent its own event log shape
- correctness: medium.
- simplicity: medium.
- extensibility: low; cross-workflow tooling becomes hard.
- observability: medium for one workflow, low for the framework.
- testability: medium.
- migration risk: low.
- parity impact: medium.

### Candidate B: Keep a generic append-only runtime event log and let workflow-owned helpers add workflow-specific raw logs and ledgers without teaching the engine about them
- correctness: high.
- simplicity: high.
- extensibility: high.
- observability: high.
- testability: high.
- migration risk: medium.
- parity impact: high; `events.jsonl`, raw logs, and decisions can still be preserved.

### Candidate C: Move all observability into the engine as first-class structured events
- correctness: medium.
- simplicity: low.
- extensibility: medium.
- observability: high.
- testability: medium.
- migration risk: high.
- parity impact: medium.

Decision: Candidate B.

Book choice: the engine should expose deterministic execution results, while the runtime and workflow harness own append-only operational logs.

Why the others lost: Candidate A gives up shared observability. Candidate C puts too much filesystem policy into the engine.

## 15. Parity-Testing Strategy

### Candidate A: Treat unit and contract tests as enough and trust architecture for parity
- correctness: low.
- simplicity: high.
- extensibility: medium.
- observability: low.
- testability: medium.
- migration risk: high.
- parity impact: low.

### Candidate B: Use a layered proof suite: strict unit tests, engine-contract tests, workflow execution tests, and explicit legacy parity tests against `autoloop/`
- correctness: high.
- simplicity: medium.
- extensibility: high.
- observability: high.
- testability: high.
- migration risk: medium.
- parity impact: high.

### Candidate C: Use only end-to-end parity tests against the legacy runtime
- correctness: medium; broad but hard to localize.
- simplicity: medium.
- extensibility: low.
- observability: low.
- testability: low; failures are expensive to diagnose.
- migration risk: medium.
- parity impact: high.

Decision: Candidate B.

Book choice: parity must be proven at the edges, but strict contracts must be proven locally. The layered suite is the shortest route to confidence.

Why the others lost: Candidate A does not prove parity. Candidate C proves too little about the new architecture itself.

## 16. Migration Strategy From Current `autoloop_v3`

### Candidate A: Ship incremental compatibility-preserving patches until the architecture converges
- correctness: medium.
- simplicity: low; mixed states last too long.
- extensibility: low.
- observability: low; it is hard to know which rules are final.
- testability: medium.
- migration risk: low per patch, high overall because drift persists.
- parity impact: high.

### Candidate B: Freeze the target architecture in one decision record, remove strict-core compatibility behavior first, then reduce the runtime, then finish workflow-owned parity helpers
- correctness: high.
- simplicity: high.
- extensibility: high.
- observability: high.
- testability: high.
- migration risk: medium; the sequence is deliberate, not improvised.
- parity impact: high.

### Candidate C: Rewrite the whole package from scratch in a new namespace and migrate later
- correctness: medium.
- simplicity: medium conceptually, low operationally.
- extensibility: high.
- observability: medium.
- testability: medium.
- migration risk: high.
- parity impact: medium.

Decision: Candidate B.

Book choice: the right migration is staged by architecture boundaries: strict core first, runtime boundary second, workflow parity harness last.

Why the others lost: Candidate A never cleanly exits the mixed state. Candidate C throws away too much working structure and slows parity proof.

## Final Shape

The final architecture is:

- a strict `autoloop_v3.workflow` core with no compatibility layer
- a generic `autoloop_v3.runtime` harness
- canonical workflows that explicitly import and use the public API
- workflow-owned parity helpers for Autoloop-v1 behavior that does not generalize
- explicit session creation and direct session lookup
- typed checkpoints and small replaceable provider/store protocols
- parity proved by layered tests, not by hidden compatibility machinery
