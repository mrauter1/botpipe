# Architecture Decisions

This record freezes the final Book Architecture target for `autoloop_v3`.

The final explanation is intentionally short:

- `autoloop_v3.workflow` is the strict canonical kernel.
- `autoloop_v3.runtime` is the workflow-agnostic filesystem runtime.
- `autoloop_v3.stdlib` is tiny pure authoring sugar.
- `autoloop_v3.extensions` is a tiny optional extension surface.
- `autoloop_v3.workflows` owns workflow-specific parity and conventions only.

Every decision below is evaluated against the same dimensions:

- correctness
- simplicity
- extensibility
- observability
- testability
- migration risk
- parity impact

## 1. Final Package Layout

### Candidate A: Keep the current loose split and let mixed workflow support modules continue to absorb shared behavior
- correctness: medium; behavior may survive, but ownership stays blurry. simplicity: low; too many layers can still mutate the shape. extensibility: low; every new concern risks landing in the mixed slice. observability: medium. testability: medium. migration risk: low. parity impact: high.

### Candidate B: Use `workflow`, `runtime`, `stdlib`, `extensions`, and workflow-owned `workflows` modules with sharp boundaries
- correctness: high; every concern has one owner. simplicity: high; the system is explainable in a few sentences. extensibility: high; new workflows reuse the same core without inheriting Autoloop-v1 policy. observability: high. testability: high. migration risk: medium. parity impact: high.

### Candidate C: Collapse runtime, extensions, and parity into one Autoloop-first package
- correctness: medium; fewer folders, but the runtime stops being generic. simplicity: medium at first, low later; mixed concerns accumulate. extensibility: low; unrelated workflows inherit Autoloop-v1 weight. observability: medium. testability: medium. migration risk: medium. parity impact: high for Autoloop-v1 and low for everything else.

Decision: Candidate B.

Book choice: it is the smallest package shape that preserves a strict kernel, a generic runtime, and workflow-owned parity.

Why the others lost: Candidate A preserves accidental architecture. Candidate C trades a shorter tree for the wrong ownership model.

## 2. Canonical Public Surface

### Candidate A: Keep broad root exports such as `Engine`, `compile_workflow`, and helper internals on the authoring surface
- correctness: medium; the symbols work, but they expose implementation details as authoring API. simplicity: low; authors must distinguish public intent from internal convenience. extensibility: medium. observability: medium. testability: medium. migration risk: low. parity impact: low.

### Candidate B: Expose only the strict workflow authoring symbols plus `Event`, `Outcome`, `Checkpoint`, and `ResolvedArtifacts`
- correctness: high; the public contract matches the prompt exactly. simplicity: high; one import surface means one meaning per concept. extensibility: high; internals can change without redefining authoring. observability: high. testability: high. migration risk: medium. parity impact: low.

### Candidate C: Publish the full internal module graph and rely on documentation to mark some APIs as discouraged
- correctness: medium; authors can still reach everything, including unstable internals. simplicity: low; documentation becomes the only real boundary. extensibility: low; internal refactors become breaking changes in practice. observability: medium. testability: medium. migration risk: low. parity impact: low.

Decision: Candidate B.

Book choice: the public surface is strict, minimal, and easy to memorize.

Why the others lost: Candidate A keeps internal machinery in the authoring path. Candidate C replaces a contract with convention.

## 3. Compatibility Removal Strategy

### Candidate A: Keep a hidden normalization layer that quietly adapts legacy workflows into the strict model
- correctness: low; the system would still have two execution models. simplicity: low; hidden adaptation is hard to explain and test. extensibility: low; every future change must preserve both meanings. observability: low. testability: low. migration risk: low at first and high later. parity impact: medium.

### Candidate B: Remove compatibility behavior entirely and retain only narrow operational compatibility for persisted runtime data and config discovery
- correctness: high; strict authoring has one meaning while runtime data compatibility stays targeted. simplicity: high; removals are explicit and retained compatibility is narrow. extensibility: high; the kernel is not burdened by old shapes. observability: high. testability: high. migration risk: medium. parity impact: high where explicitly preserved.

### Candidate C: Keep the removed names as deprecated aliases for one more generation
- correctness: medium; authoring stays ambiguous during the entire migration window. simplicity: low; deprecated aliases still preserve drift. extensibility: low. observability: medium. testability: medium. migration risk: low. parity impact: medium.

Decision: Candidate B.

Book choice: strict authoring plus narrow operational compatibility is the only version that removes drift without breaking persisted data gratuitously.

Why the others lost: Candidate A is a compatibility layer under another name. Candidate C preserves the same ambiguity more politely.

## 4. Strict Workflow Migration Strategy

### Candidate A: Let workflows migrate slowly through wrappers, base classes, and compatibility helpers
- correctness: medium; workflows can keep running, but the final strict shape never becomes authoritative. simplicity: low; wrappers become the real API. extensibility: low. observability: medium. testability: medium. migration risk: low. parity impact: medium.

### Candidate B: Migrate workflows directly onto the strict kernel with explicit sessions, explicit entry, explicit transitions, and workflow-owned policy
- correctness: high; the workflow source becomes the source of truth again. simplicity: high; reading the workflow reveals semantics directly. extensibility: high; new workflows reuse the strict shape immediately. observability: high. testability: high. migration risk: medium. parity impact: high.

### Candidate C: Move workflow meaning into config or decorators so migration can touch fewer lines
- correctness: low; semantics leave Python code and hide behind a second DSL. simplicity: low; the local diff is smaller but the architecture is worse. extensibility: medium. observability: low. testability: low. migration risk: medium. parity impact: medium.

Decision: Candidate B.

Book choice: the migration target is the strict workflow language itself, not a transitional wrapper around it.

Why the others lost: Candidate A delays the real migration. Candidate C moves meaning into the wrong layer.

## 5. Session Model

### Candidate A: Compute session identity from workflow state or step names and let the engine open sessions automatically
- correctness: low; session ownership becomes implicit and brittle. simplicity: low; hidden rules replace explicit code. extensibility: low. observability: low. testability: low. migration risk: medium. parity impact: medium.

### Candidate B: Keep sessions as declared slots opened explicitly with `ctx.open_session(...)`
- correctness: high; creation, sharing, and rebinding are visible in workflow code. simplicity: high; the engine only looks up sessions that were opened. extensibility: high; workflows can define any sharing policy explicitly. observability: high. testability: high. migration risk: medium. parity impact: high.

### Candidate C: Add lifecycle enums and automatic session-opening policies to reduce workflow boilerplate
- correctness: medium; some cases work, but semantics shift into framework policy. simplicity: low; lifecycle policy becomes a second language. extensibility: medium. observability: medium. testability: medium. migration risk: low. parity impact: medium.

Decision: Candidate B.

Book choice: sessions are explicit resources, not inferred behavior.

Why the others lost: Candidate A hides identity. Candidate C reintroduces `SessionLifecycle` by policy instead of name.

## 6. Artifact Registry And Required-Artifact Enforcement

### Candidate A: Let handlers resolve file paths ad hoc from `ctx` and state without a compiled registry
- correctness: medium; workflows can work, but contract violations surface late. simplicity: medium locally and low globally; repeated path logic spreads. extensibility: low. observability: medium. testability: medium. migration risk: low. parity impact: medium.

### Candidate B: Compile workflow-declared artifacts into a registry, validate dependencies, and assert required-artifact existence before step execution
- correctness: high; artifact contracts are explicit and enforceable. simplicity: high; one compiled registry replaces scattered path logic. extensibility: high; workflows can add artifacts without changing runtime rules. observability: high. testability: high. migration risk: medium. parity impact: high.

### Candidate C: Keep a registry but make missing required artifacts best-effort warnings
- correctness: low; the contract exists but is not trustworthy. simplicity: low; steps must still defend against missing files. extensibility: medium. observability: medium. testability: low. migration risk: low. parity impact: medium.

Decision: Candidate B.

Book choice: artifact declarations are real contracts, not hints.

Why the others lost: Candidate A scatters ownership. Candidate C keeps the language while deleting the guarantee.

## 7. Prompt Model And Resolution

### Candidate A: Resolve prompts through hidden registries and search roots that vary by deployment
- correctness: medium; some prompts resolve, but provenance is indirect. simplicity: low; debugging depends on global state. extensibility: medium. observability: low. testability: low. migration risk: medium. parity impact: low.

### Candidate B: Use explicit prompt paths or `Prompt(...)` with deterministic workflow-module-relative resolution
- correctness: high; prompt provenance is stable and explainable. simplicity: high; authors can see where prompts come from. extensibility: high; bundles stay authoring sugar instead of runtime magic. observability: high. testability: high. migration risk: medium. parity impact: low.

### Candidate C: Move prompt selection into config so workflows can be changed without code edits
- correctness: low; workflow meaning becomes deployment policy. simplicity: low; runtime config turns into a second DSL. extensibility: medium. observability: low. testability: medium. migration risk: low. parity impact: low.

Decision: Candidate B.

Book choice: prompt resolution is deterministic, explicit, and owned by workflow authoring.

Why the others lost: Candidate A hides provenance. Candidate C moves semantics out of workflow code.

## 8. Validation And Compilation Model

### Candidate A: Validate only when a run starts and normalize malformed declarations if possible
- correctness: medium; some bad workflows are caught, but too late. simplicity: low; normalization adds a hidden boundary. extensibility: low. observability: medium. testability: medium. migration risk: low. parity impact: low.

### Candidate B: Validate strictly at definition time and compile deterministically into an immutable workflow model
- correctness: high; malformed workflows fail early and consistently. simplicity: high; there is one execution model and one compiled representation. extensibility: high; later runtime logic assumes canonical inputs. observability: high. testability: high. migration risk: medium. parity impact: low.

### Candidate C: Skip compilation and interpret class attributes dynamically on every step
- correctness: medium; it can work, but stateful interpretation invites drift. simplicity: medium at first and low later; repeated interpretation spreads logic. extensibility: medium. observability: medium. testability: medium. migration risk: low. parity impact: low.

Decision: Candidate B.

Book choice: strict validation plus deterministic compilation is the smallest reliable kernel.

Why the others lost: Candidate A keeps a hidden normalization boundary. Candidate C duplicates compilation work at runtime.

## 9. Checkpoint Model

### Candidate A: Treat `events.jsonl` as the canonical resume source and reconstruct runtime state from logs
- correctness: medium; history exists, but replay-based resume is indirect and fragile. simplicity: low; resume requires log interpretation. extensibility: medium. observability: high. testability: medium. migration risk: medium. parity impact: medium.

### Candidate B: Use typed checkpoints as the canonical resume source and keep `events.jsonl` as history
- correctness: high; resume state is explicit, structured, and bounded. simplicity: high; pause and resume use one data model. extensibility: high; workflows can add history files without redefining resume. observability: high. testability: high. migration risk: medium. parity impact: high.

### Candidate C: Store provider-owned opaque resume blobs and let each provider decide what resuming means
- correctness: low; resume semantics would vary by backend. simplicity: low; the workflow kernel loses ownership of control flow. extensibility: low. observability: low. testability: low. migration risk: medium. parity impact: low.

Decision: Candidate B.

Book choice: typed checkpoints keep resumability explicit and workflow-agnostic.

Why the others lost: Candidate A confuses history with state. Candidate C outsources core semantics to providers.

## 10. Provider And Store Protocols

### Candidate A: Use a monolithic runtime service object that owns provider calls, prompts, checkpoints, and sessions
- correctness: medium; a single object can work, but contracts blur together. simplicity: low; one dependency hides many roles. extensibility: low. observability: medium. testability: low. migration risk: low. parity impact: low.

### Candidate B: Keep small typed provider and store protocols with fake and filesystem implementations
- correctness: high; each dependency has a crisp job. simplicity: high; protocols stay small and composable. extensibility: high; new providers and stores can swap in without redefining the engine. observability: high. testability: high. migration risk: medium. parity impact: low.

### Candidate C: Embed Autoloop-v1 helper methods directly in provider and store protocols for convenience
- correctness: low; generic contracts would now encode one workflow. simplicity: low; convenience for one workflow burdens every implementation. extensibility: low. observability: medium. testability: low. migration risk: medium. parity impact: medium.

Decision: Candidate B.

Book choice: the kernel depends on small protocols, not on a god object or workflow-specific methods.

Why the others lost: Candidate A centralizes too much. Candidate C leaks workflow policy into generic interfaces.

## 11. Runtime Harness Design

### Candidate A: Let the runtime understand phases, review loops, and workflow-specific file naming so it can run Autoloop-v1 directly
- correctness: medium; parity can work, but the runtime stops being neutral. simplicity: low; generic runtime becomes domain-aware. extensibility: low. observability: medium. testability: medium. migration risk: low. parity impact: high.

### Candidate B: Keep the runtime generic and let workflow-owned composition roots wire any parity policies, session-path strategies, or optional extensions
- correctness: high; generic runtime and workflow-specific behavior stay separate. simplicity: high; the runner owns only generic run orchestration. extensibility: high; any workflow can compose its own policy layer. observability: high. testability: high. migration risk: medium. parity impact: high.

### Candidate C: Add a generic workspace-hook system to let workflows alter runtime behavior imperatively
- correctness: medium; flexible, but the runtime now hosts a second behavior model. simplicity: low; hook ordering and side effects become part of the contract. extensibility: medium. observability: medium. testability: medium. migration risk: medium. parity impact: high.

Decision: Candidate B.

Book choice: the runtime remains generic because workflow meaning stays outside it.

Why the others lost: Candidate A violates the workflow-agnostic boundary. Candidate C creates a hook framework larger than the problem.

## 12. Configuration Boundary

### Candidate A: Let config drive workflow topology, phase semantics, and commit policy so behavior can change without code edits
- correctness: low; config becomes a second workflow language. simplicity: low; meaning moves away from source. extensibility: medium. observability: low. testability: low. migration risk: low. parity impact: medium.

### Candidate B: Keep config small and typed for generic runtime/provider policy only, such as `max_steps`, `intent_mode`, provider settings, and extension config
- correctness: high; config controls operations, not workflow meaning. simplicity: high; config remains small and reviewable. extensibility: high; new operational concerns can still opt in cleanly. observability: high. testability: high. migration risk: medium. parity impact: high where retained compatibility matters.

### Candidate C: Avoid config entirely and require all runtime/provider policy in code
- correctness: medium; explicitness is good, but deployments lose a small useful policy layer. simplicity: medium; code-only policy forces boilerplate for generic operations. extensibility: medium. observability: high. testability: medium. migration risk: medium. parity impact: medium.

Decision: Candidate B.

Book choice: config should be operational and typed, not semantic.

Why the others lost: Candidate A turns config into a DSL. Candidate C removes a legitimate deployment seam.

## 13. Stdlib Shape

### Candidate A: Do not ship a stdlib at all; force every workflow to repeat common control helpers and prompt bundles
- correctness: high; the kernel remains strict, but repeated boilerplate spreads. simplicity: medium; the framework is small but workflow code becomes noisier. extensibility: medium. observability: high. testability: medium. migration risk: low. parity impact: low.

### Candidate B: Ship a tiny pure-authoring stdlib with `control`, `prompts`, `steps`, and `state.cursor`
- correctness: high; helpers solve repeated authoring problems without changing semantics. simplicity: high; sugar remains small and transparent. extensibility: high; workflows can opt in selectively. observability: high. testability: high. migration risk: medium. parity impact: low.

### Candidate C: Add base classes, mixins, decorators, and workflow families to compress authoring further
- correctness: medium; some workflows get shorter, but semantics hide behind framework inheritance. simplicity: low; a second authoring language emerges. extensibility: low. observability: low. testability: medium. migration risk: medium. parity impact: medium.

Decision: Candidate B.

Book choice: the stdlib is pure sugar, not a second execution model.

Why the others lost: Candidate A duplicates solved authoring problems. Candidate C adds framework cleverness instead of helpers.

## 14. Workflow Extension Seam

### Candidate A: Keep cross-cutting behavior in core observers or bespoke runtime hooks
- correctness: medium; some side effects can be wired, but the seam is either obsolete or too broad. simplicity: low; different concerns would use different mechanisms. extensibility: medium. observability: medium. testability: medium. migration risk: low. parity impact: medium.

### Candidate B: Add one minimal `Workflow.extensions` seam with bound extensions that receive run binding, step start, step finish, and terminal events
- correctness: high; cross-cutting side effects are explicit and constrained. simplicity: high; one seam replaces multiple bespoke ones. extensibility: high; git, tracing, and session-path strategies share the same model. observability: high. testability: high. migration risk: medium. parity impact: high.

### Candidate C: Build a generic event bus or plugin platform with many hook types and hidden best-effort behavior
- correctness: medium; flexible, but the surface is much larger than necessary. simplicity: low; hook composition becomes a system of its own. extensibility: high in theory and low in practice; policy becomes hard to reason about. observability: medium. testability: low. migration risk: medium. parity impact: high.

Decision: Candidate B.

Book choice: one minimal extension seam is enough for orthogonal side effects without changing workflow meaning.

Why the others lost: Candidate A keeps legacy or bespoke seams alive. Candidate C over-generalizes into a platform.

## 15. Git Extension Placement

### Candidate A: Put git tracking in the generic runtime and enable it from runtime config when a repository is present
- correctness: low; git policy would run without workflow opt-in and runtime becomes policy-aware. simplicity: low; repository detection becomes hidden behavior. extensibility: medium. observability: medium. testability: medium. migration risk: low. parity impact: medium.

### Candidate B: Implement git as a workflow-declared extension with generic repo mechanics in the extension and workflow-owned commit policy objects
- correctness: high; opt-in, ordering, and policy ownership are explicit. simplicity: high; the runtime stays git-agnostic. extensibility: high; different workflows can define different commit policy without changing the extension core. observability: high. testability: high. migration risk: medium. parity impact: high.

### Candidate C: Add git behavior directly to workflows and duplicate repo mechanics wherever needed
- correctness: medium; workflows can own policy, but shared git mechanics would repeat. simplicity: medium locally and low globally. extensibility: medium. observability: high. testability: medium. migration risk: low. parity impact: medium.

Decision: Candidate B.

Book choice: repo mechanics are reusable, commit policy is workflow meaning, and opt-in must be explicit.

Why the others lost: Candidate A hides policy in runtime operations. Candidate C duplicates shared mechanics.

## 16. Session-Path Strategy Placement

### Candidate A: Hardcode session path naming in the generic filesystem store
- correctness: medium; generic defaults can work, but exact workflow naming rules become framework law. simplicity: low; the store now knows too much about workflow conventions. extensibility: low. observability: medium. testability: medium. migration risk: low. parity impact: medium.

### Candidate B: Provide a generic optional session-path strategy extension while keeping exact Autoloop-v1 names workflow-owned
- correctness: high; reusable path strategy stays generic and exact parity naming stays local. simplicity: high; one optional strategy seam is enough. extensibility: high; other workflows can opt in or ignore it. observability: high. testability: high. migration risk: medium. parity impact: high.

### Candidate C: Duplicate exact Autoloop-v1 path logic in the workflow and in the store and accept the drift risk
- correctness: medium; it can work until the copies diverge. simplicity: medium at first and low later. extensibility: low. observability: medium. testability: medium. migration risk: medium. parity impact: medium.

Decision: Candidate B.

Book choice: generic path strategy is optional infrastructure, while exact naming stays with the workflow that owns it.

Why the others lost: Candidate A promotes workflow-specific naming into the framework. Candidate C trades boundaries for duplication.

## 17. Observability And Event Model

### Candidate A: Put workflow-specific raw logs and event taxonomies into the generic runtime event system
- correctness: low; shared runtime logs would now encode workflow semantics. simplicity: low; one log would have multiple meanings. extensibility: low. observability: medium. testability: medium. migration risk: medium. parity impact: high.

### Candidate B: Keep generic append-only `events.jsonl` in the runtime and let workflow-owned parity code or optional tracing extensions add their own side effects separately
- correctness: high; generic history stays generic and extra logs stay local. simplicity: high; there is one shared log and optional sidecar outputs. extensibility: high; tracing and parity do not distort the core schema. observability: high. testability: high. migration risk: medium. parity impact: high.

### Candidate C: Replace `events.jsonl` with a tracing-first system and let tracing become the main history artifact
- correctness: medium; tracing can be useful, but not every run wants or needs it. simplicity: low; optional tracing becomes core behavior. extensibility: medium. observability: high. testability: medium. migration risk: medium. parity impact: medium.

Decision: Candidate B.

Book choice: generic history is always present, and everything else is explicitly layered around it.

Why the others lost: Candidate A pollutes the shared schema. Candidate C turns an optional concern into the primary runtime artifact.

## 18. Testing Strategy

### Candidate A: Rely mainly on broad end-to-end runs because they prove the whole stack at once
- correctness: medium; integration matters, but failures become hard to localize. simplicity: medium; fewer test categories, but more debugging cost. extensibility: low. observability: medium. testability: low. migration risk: low. parity impact: medium.

### Candidate B: Use layered proof with unit, contract, runtime integration, no-compat, workflow, toy-workflow, and parity tests
- correctness: high; claims are tied to explicit proof layers. simplicity: high; each test class answers one architectural question. extensibility: high; new features get the smallest needed proof. observability: high. testability: high. migration risk: medium. parity impact: high.

### Candidate C: Keep only unit tests plus documentation assertions and trust architecture discipline for the rest
- correctness: low; emergent integration bugs slip through. simplicity: medium; fewer tests, but weaker proof. extensibility: low. observability: low. testability: low. migration risk: medium. parity impact: low.

Decision: Candidate B.

Book choice: the architecture is only real if each layer is independently provable and the final parity claims are tested explicitly.

Why the others lost: Candidate A over-relies on broad runs. Candidate C mistakes documentation for proof.
