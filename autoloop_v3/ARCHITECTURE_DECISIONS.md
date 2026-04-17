# Architecture Decisions

This record freezes the final Book Architecture target for `autoloop_v3`.

The system is organized around one strict core, one generic runtime, and one workflow-owned parity layer:

- `autoloop_v3.workflow` is the canonical engine and authoring surface.
- `autoloop_v3.runtime` is the generic filesystem runtime for tasks, runs, prompts, checkpoints, events, and session persistence.
- `autoloop_v3.workflows` owns Autoloop-v1 parity policy and nothing more.
- Repo-root workflows such as `autoloop_v1.py` and `Ralph_loop.py` stay strict workflows written against canonical primitives.

Every decision below is evaluated against the same dimensions:

- correctness
- simplicity
- extensibility
- observability
- testability
- migration risk
- parity impact

## 1. Final Package / Module Layout

### Candidate A: Keep the current broad split, including the mixed Autoloop-v1 support layer
- correctness: medium; the system still works, but ownership remains ambiguous. simplicity: low; one file still mixes workflow semantics, parity policy, infrastructure, and observation. extensibility: low; every new concern risks landing in the same mixed layer. observability: medium; behavior exists, but not at a clean boundary. testability: medium; tests must cross layers to prove one concern. migration risk: low. parity impact: high.

### Candidate B: Keep `workflow` strict, keep `runtime` generic, move Autoloop-v1 parity into a small workflow-owned slice, and keep repo-root workflows strict
- correctness: high; each concern has one owner. simplicity: high; the architecture is short to explain. extensibility: high; new workflows reuse the core without inheriting Autoloop-v1 policy. observability: high; generic facts come from the engine, parity interpretation comes from the parity layer. testability: high; engine, runtime, workflows, and parity can be proved independently. migration risk: medium. parity impact: high.

### Candidate C: Collapse runtime and parity into one Autoloop-first package
- correctness: medium; fewer files, but the runtime stops being workflow-agnostic. simplicity: medium at first, low later; the explanation gets shorter only by mixing concerns. extensibility: low; every future workflow pays the Autoloop tax. observability: medium; everything is nearby, but nothing is cleanly separated. testability: medium; end-to-end tests dominate. migration risk: medium. parity impact: high for Autoloop-v1, low for everything else.

Decision: Candidate B.

Book choice: one strict core, one generic runtime, and one workflow-owned parity layer is the shortest explanation that preserves both reuse and legacy parity.

Why the others lost: Candidate A keeps the impurity in place. Candidate C solves proximity by violating the workflow-agnostic runtime requirement.

## 2. Final Ownership Boundary For Autoloop-v1 Support Code

### Candidate A: Let the support layer keep owning whatever Autoloop-v1 currently needs, including reusable infrastructure
- correctness: medium; behavior survives, but ownership stays blurry. simplicity: low; the support layer remains a disguised mini-runtime. extensibility: low; reusable code and parity policy keep drifting together. observability: medium. testability: medium. migration risk: low. parity impact: high.

### Candidate B: Limit Autoloop-v1 support ownership to workflow semantics, parity policy, and workflow-owned interpretation of generic execution facts
- correctness: high; reusable infrastructure moves out, while workflow-specific policy stays local. simplicity: high; the boundary is easy to state and defend. extensibility: high; reusable helpers can graduate cleanly. observability: high; the parity layer interprets, it does not impersonate the runtime. testability: high. migration risk: medium. parity impact: high.

### Candidate C: Push most support behavior down into the runtime so only minimal workflow code remains
- correctness: medium; parity works, but the runtime becomes domain-aware. simplicity: low; generic code acquires workflow semantics. extensibility: low; runtime evolution becomes coupled to one workflow. observability: medium. testability: medium. migration risk: medium. parity impact: high.

Decision: Candidate B.

Book choice: the Autoloop-v1 layer should own only Autoloop-v1 meaning and policy. Infrastructure belongs elsewhere.

Why the others lost: Candidate A preserves the mixed layer. Candidate C leaks workflow policy into the generic runtime.

## 3. Whether `autoloop_v1_support.py` Survives, Is Split, Or Is Deleted

### Candidate A: Keep `autoloop_v1_support.py` and clean it up in place
- correctness: medium; refactoring helps, but the file still advertises the wrong shape. simplicity: low; a mixed file remains a magnet for new concerns. extensibility: low. observability: medium. testability: medium. migration risk: low. parity impact: high.

### Candidate B: Delete `autoloop_v1_support.py` and replace it with narrower modules such as `autoloop_v1_parity.py` and `autoloop_v1_conventions.py`
- correctness: high; names and boundaries align with real ownership. simplicity: high; each module has one reason to change. extensibility: high; new parity policy and tiny shared conventions evolve separately. observability: high. testability: high. migration risk: medium because imports must move together. parity impact: high.

### Candidate C: Keep the file as a compatibility shell that re-exports new modules
- correctness: medium; behavior is fine, but the obsolete shape survives. simplicity: low; deletion is delayed under another name. extensibility: medium. observability: low; callers cannot tell which surface is authoritative. testability: medium. migration risk: low. parity impact: high.

Decision: Candidate B.

Book choice: the old file should disappear entirely once the workflow and harness have migrated off it.

Why the others lost: Candidate A keeps the wrong center of gravity. Candidate C is a compatibility layer in disguise.

## 4. Execution Observation Design

### Candidate A: Keep observation inside an Autoloop-v1 provider wrapper plus engine subclass
- correctness: medium; it works today, but observation is welded to one workflow. simplicity: low; two bespoke seams are needed to observe one execution. extensibility: low; every new observer concern must choose a wrapper or subclass. observability: medium. testability: medium. migration risk: low. parity impact: high.

### Candidate B: Add one minimal typed observer seam to the engine with three event categories: provider-turn, step-completion, and terminal
- correctness: high; the engine emits generic facts and nothing more. simplicity: high; there is one seam, one observer interface, and three crisp payload families. extensibility: high; multiple observers can consume the same facts without changing engine semantics. observability: high; parity, generic logging, and future diagnostics can all derive from the same stream. testability: high. migration risk: medium. parity impact: high.

### Candidate C: Add a large hook/plugin system with pre-step, post-step, pre-provider, post-provider, checkpoint, and workspace hooks
- correctness: medium; flexible, but much easier to misuse. simplicity: low; the abstraction is larger than the problem. extensibility: medium; everything is possible, but nothing is constrained. observability: high. testability: medium; hook ordering and interaction explode the matrix. migration risk: medium. parity impact: high.

Decision: Candidate B.

Book choice: one minimal observer seam is the exact reusable concept here. It is enough for parity and small enough to keep the engine strict.

Why the others lost: Candidate A is bespoke and workflow-owned. Candidate C over-generalizes a single cross-cutting concern into a hook framework.

## 5. Provider Wrapper Removal Strategy

### Candidate A: Keep the provider wrapper until the very end because it already preserves parity
- correctness: medium; parity stays intact, but the architecture stays impure. simplicity: low; the wrapper remains a second policy surface around providers. extensibility: low. observability: medium. testability: medium. migration risk: low. parity impact: high.

### Candidate B: Delete the wrapper and rebuild every needed side effect from generic observer events inside the parity harness
- correctness: high; observation moves to the right layer. simplicity: high; providers return provider results, observers interpret execution facts. extensibility: high; additional parity logging does not require provider surgery. observability: high. testability: high. migration risk: medium. parity impact: high.

### Candidate C: Replace the wrapper with a generic provider-decorator stack in the core
- correctness: medium; reusable in theory, but the current need is smaller and cleaner. simplicity: low; a new abstraction appears where a single observer seam already solves the problem. extensibility: medium. observability: high. testability: medium. migration risk: medium. parity impact: high.

Decision: Candidate B.

Book choice: provider wrappers disappear entirely; parity logging becomes workflow-owned interpretation of generic observer events.

Why the others lost: Candidate A leaves the impurity alive. Candidate C adds a second generic abstraction when one already suffices.

## 6. Engine Subclass Removal Strategy

### Candidate A: Keep an Autoloop-v1 engine subclass for step logging and phase event synthesis
- correctness: medium; behavior works, but the core is no longer the only engine. simplicity: low; the architecture now has a canonical engine and a real engine. extensibility: low. observability: medium. testability: medium. migration risk: low. parity impact: high.

### Candidate B: Delete the engine subclass and derive all workflow-specific side effects from the generic observer stream in the parity layer
- correctness: high; the strict engine stays singular. simplicity: high; there is one engine and one observation seam. extensibility: high; new parity behavior composes without subclassing execution. observability: high. testability: high. migration risk: medium. parity impact: high.

### Candidate C: Replace the subclass with a generic engine extension base class
- correctness: medium; cleaner than a bespoke subclass, but still a second execution model. simplicity: low; the engine becomes an extension framework. extensibility: medium. observability: medium. testability: medium. migration risk: medium. parity impact: high.

Decision: Candidate B.

Book choice: the strict engine should be the only engine. Observation belongs beside it, not beneath it.

Why the others lost: Candidate A preserves dual-engine architecture. Candidate C generalizes the wrong mechanism instead of deleting it.

## 7. Session Payload Helper Ownership

### Candidate A: Leave session payload placeholder creation and payload writing in the Autoloop-v1 parity layer
- correctness: medium; the behavior works, but the workflow layer serializes runtime infrastructure. simplicity: low; session persistence logic is split across layers. extensibility: medium. observability: medium. testability: medium. migration risk: low. parity impact: high.

### Candidate B: Move session payload writing and placeholder helpers fully into `runtime.stores.filesystem`
- correctness: high; the filesystem store owns serialization end to end. simplicity: high; one store reads and writes its own wire format. extensibility: high; future workflows can reuse the helpers without importing parity code. observability: high; session files have one owner. testability: high. migration risk: medium. parity impact: high.

### Candidate C: Split ownership so the store reads while the parity layer writes
- correctness: low; the serialization contract becomes bilateral. simplicity: low. extensibility: low. observability: low. testability: low. migration risk: medium. parity impact: medium.

Decision: Candidate B.

Book choice: the filesystem session store owns filesystem session serialization. Nothing else should write that JSON directly.

Why the others lost: Candidate A keeps infrastructure in the workflow layer. Candidate C creates an incoherent read/write split.

## 8. `phase_artifact_template` Removal

### Candidate A: Keep `phase_artifact_template` because it reduces duplication
- correctness: medium; it works, but it hides plain workflow DSL behind a helper. simplicity: low; another indirection survives for a problem the DSL already solves. extensibility: low. observability: medium. testability: medium. migration risk: low. parity impact: high.

### Candidate B: Delete `phase_artifact_template` and write explicit `Artifact(...)` templates directly in `autoloop_v1.py`
- correctness: high; the workflow owns its own artifact paths explicitly. simplicity: high; the final workflow is easier to read than the helper. extensibility: high; artifact intent stays in workflow code. observability: high. testability: high. migration risk: medium because source text changes. parity impact: high.

### Candidate C: Replace it with a new helper under another name
- correctness: medium; behavior stays the same, but the indirection remains. simplicity: low. extensibility: medium. observability: low. testability: medium. migration risk: low. parity impact: high.

Decision: Candidate B.

Book choice: the DSL already expresses phase artifact paths directly. The helper adds no architecture.

Why the others lost: Candidate A keeps needless indirection. Candidate C renames the same mistake.

## 9. Final Placement Of `parse_phase_ids`

### Candidate A: Promote `parse_phase_ids` into the core or runtime as a generic helper
- correctness: low; it interprets Autoloop-v1 phase-plan meaning, not generic engine semantics. simplicity: low. extensibility: low; the core inherits workflow policy. observability: medium. testability: medium. migration risk: medium. parity impact: high.

### Candidate B: Keep `parse_phase_ids` workflow-owned, inline in `autoloop_v1.py` unless the parity harness also needs it, in which case use a tiny workflow-owned helper
- correctness: high; the semantic rule stays next to the workflow that defines it. simplicity: high; no new framework helper is introduced. extensibility: high; other workflows are free to define different parsing. observability: high. testability: high. migration risk: low. parity impact: high.

### Candidate C: Put `parse_phase_ids` in `autoloop_v1_conventions.py` by default even if only the workflow uses it
- correctness: high; still workflow-owned. simplicity: medium; acceptable if shared, unnecessary if not. extensibility: high. observability: high. testability: high. migration risk: low. parity impact: high.

Decision: Candidate B.

Book choice: `parse_phase_ids` belongs to workflow semantics. It should live in the workflow file unless sharing is real, not speculative.

Why the others lost: Candidate A promotes workflow meaning into the framework. Candidate C is harmless but less compressed when no sharing exists.

## 10. Final Placement Of Exact `phase_dir_key`

### Candidate A: Promote the exact `_pid-...` encoding into the framework as a universal phase rule
- correctness: low; the exact string format is legacy parity policy, not framework law. simplicity: low. extensibility: low; every workflow inherits one legacy encoding. observability: medium. testability: medium. migration risk: medium. parity impact: high.

### Candidate B: Keep exact `phase_dir_key` behavior workflow-owned in a tiny conventions module shared by the strict workflow and the parity harness
- correctness: high; the exact encoding stays where it is needed and nowhere else. simplicity: high; one tiny shared helper is enough. extensibility: high; other workflows can ignore it or define their own neutral helpers. observability: high. testability: high. migration risk: low. parity impact: high.

### Candidate C: Duplicate the exact logic in both `autoloop_v1.py` and the parity harness
- correctness: medium; duplication invites drift. simplicity: medium at first, low later. extensibility: low. observability: medium. testability: medium. migration risk: medium. parity impact: medium.

Decision: Candidate B.

Book choice: the exact encoding should stay workflow-owned, but duplication is worse than one tiny shared conventions helper.

Why the others lost: Candidate A over-generalizes legacy parity. Candidate C sacrifices coherence for purity theater.

## 11. Workspace Augmentation Ownership

### Candidate A: Introduce a generic workspace hook/plugin system in the runtime
- correctness: medium; it could work, but it solves only one known workflow need by changing the whole runtime. simplicity: low. extensibility: medium. observability: medium. testability: medium; hook ordering becomes a new concern. migration risk: medium. parity impact: high.

### Candidate B: Keep workspace creation generic in `runtime.workspace` and perform Autoloop-v1 augmentation explicitly inside the parity harness
- correctness: high; the runtime stays workflow-agnostic. simplicity: high; augmentation is an explicit call sequence, not a framework extension point. extensibility: high; new workflows can choose their own setup logic without burdening the runtime. observability: high. testability: high. migration risk: low. parity impact: high.

### Candidate C: Add Autoloop-specific flags to `runtime.workspace`
- correctness: medium; parity works, but the runtime learns one workflow's layout. simplicity: low; flags are a disguised compatibility layer. extensibility: low. observability: medium. testability: medium. migration risk: low. parity impact: high.

Decision: Candidate B.

Book choice: only one workflow needs augmentation, so augmentation should stay explicit and workflow-owned.

Why the others lost: Candidate A over-abstracts. Candidate C leaks workflow policy into the runtime.

## 12. Cycle / Attempt Tracking Ownership

### Candidate A: Promote cycle and attempt counters into engine semantics
- correctness: low; these counters are not generic workflow facts. simplicity: low; the engine learns parity-specific operational policy. extensibility: low. observability: medium. testability: medium. migration risk: medium. parity impact: high.

### Candidate B: Track cycle and attempt in parity observer state during a run and reconstruct them on resume from checkpoint/raw-log context
- correctness: high; the counters stay local to the parity policy that needs them. simplicity: high; the engine emits facts, the parity layer interprets them. extensibility: high; other workflows can ignore the concept entirely. observability: high. testability: high. migration risk: medium. parity impact: high.

### Candidate C: Hide cycle and attempt in provider session metadata as the default mechanism
- correctness: medium; it works, but operational policy gets buried in provider persistence. simplicity: medium. extensibility: medium. observability: low; counters become indirect metadata. testability: medium. migration risk: low. parity impact: high.

Decision: Candidate B.

Book choice: cycle and attempt are workflow-owned observer state, not engine state and not provider protocol.

Why the others lost: Candidate A pollutes the core. Candidate C hides parity semantics inside session metadata.

## 13. Clarification Ledger Ownership

### Candidate A: Generalize the decisions/clarification ledger schema into the runtime
- correctness: low; the exact schema and header format are legacy Autoloop-v1 policy. simplicity: low. extensibility: low. observability: medium. testability: medium. migration risk: medium. parity impact: high.

### Candidate B: Keep clarification ledger writes fully inside the Autoloop-v1 parity module
- correctness: high; exact headers, field names, and append rules stay local to the policy that owns them. simplicity: high. extensibility: high; the runtime remains neutral. observability: high; parity files are written by the parity layer only. testability: high. migration risk: low. parity impact: high.

### Candidate C: Move only ledger formatting into a generic docs utility package
- correctness: medium; better than runtime promotion, but still unnecessary generalization. simplicity: medium. extensibility: medium. observability: medium. testability: medium. migration risk: low. parity impact: high.

Decision: Candidate B.

Book choice: the clarification ledger is a legacy operational artifact, so it stays strictly Autoloop-v1-specific.

Why the others lost: Candidate A promotes legacy schema into framework law. Candidate C still generalizes a one-workflow artifact without a second user.

## 14. Raw Phase Log Ownership

### Candidate A: Add a generic raw-phase-log abstraction to the runtime or engine
- correctness: low; raw phase logs are not generic engine primitives. simplicity: low; the core learns one workflow's artifact format. extensibility: low. observability: medium. testability: medium. migration risk: medium. parity impact: high.

### Candidate B: Keep raw phase log emission in the Autoloop-v1 parity layer, driven by generic provider-turn and terminal observer events
- correctness: high; exact legacy formatting remains workflow-owned while observation becomes generic. simplicity: high; one observer stream feeds one parity logger. extensibility: high; other workflows can build different logs or none at all. observability: high. testability: high. migration risk: medium. parity impact: high.

### Candidate C: Keep raw phase log writing inside a provider wrapper
- correctness: medium; parity works, but observation remains bolted to providers. simplicity: low. extensibility: low. observability: medium. testability: medium. migration risk: low. parity impact: high.

Decision: Candidate B.

Book choice: generic observer facts plus workflow-owned raw-log formatting is the clean split.

Why the others lost: Candidate A makes the core domain-aware. Candidate C keeps the wrapper mechanism that the observer seam is meant to delete.

## 15. Terminal Status Mapping Ownership

### Candidate A: Move legacy status mapping into the engine
- correctness: low; values such as `blocked` are workflow-owned operational policy. simplicity: low. extensibility: low. observability: medium. testability: medium. migration risk: medium. parity impact: high.

### Candidate B: Keep terminal status mapping local to the Autoloop-v1 parity layer, derived from engine terminal events and workflow outcomes
- correctness: high; the engine reports generic terminal facts while parity maps them to legacy vocabulary. simplicity: high. extensibility: high; other workflows can map differently or not at all. observability: high. testability: high. migration risk: low. parity impact: high.

### Candidate C: Put status mapping in the generic runtime event logger
- correctness: medium; better than engine promotion, but still leaks one workflow's operational policy into the shared runtime. simplicity: medium. extensibility: low. observability: medium. testability: medium. migration risk: low. parity impact: high.

Decision: Candidate B.

Book choice: terminal mapping belongs where the legacy vocabulary belongs: the Autoloop-v1 parity layer.

Why the others lost: Candidate A pollutes the core. Candidate C pollutes the runtime.

## 16. Final Shape Of `run_autoloop_v1(...)`

### Candidate A: Let `run_autoloop_v1(...)` remain a second runtime with custom execution logic
- correctness: medium; parity survives, but architecture duplicates the runtime. simplicity: low; there are now two places to explain workspace, execution, resume, and logging. extensibility: low. observability: medium. testability: medium. migration risk: low. parity impact: high.

### Candidate B: Keep `run_autoloop_v1(...)` as a thin composition root that wires generic runtime pieces, the generic observer seam, session-path conventions, workspace augmentation, and parity-only policies
- correctness: high; it assembles parts without re-implementing them. simplicity: high; the entrypoint is composition, not machinery. extensibility: high; parity changes stay local and generic pieces stay generic. observability: high. testability: high. migration risk: medium. parity impact: high.

### Candidate C: Delete `run_autoloop_v1(...)` and force callers to reconstruct parity wiring manually
- correctness: medium; possible, but too easy to mis-wire. simplicity: medium in code, low in usage. extensibility: medium. observability: medium. testability: medium. migration risk: high. parity impact: medium.

Decision: Candidate B.

Book choice: `run_autoloop_v1(...)` should survive only as the explicit composition root for Autoloop-v1 parity.

Why the others lost: Candidate A keeps a mini-runtime. Candidate C removes the one workflow-owned place where parity wiring should live.

## 17. Test Strategy Proving The Final Shape

### Candidate A: Rely mostly on end-to-end parity tests
- correctness: medium; parity is covered, but architectural regressions local to the core are harder to isolate. simplicity: medium. extensibility: low; every change requires expensive broad tests. observability: medium. testability: medium. migration risk: low. parity impact: high.

### Candidate B: Use a layered strategy: engine observer contracts, runtime store ownership tests, strict workflow tests, Autoloop parity tests, and no-over-abstraction neutrality tests
- correctness: high; each boundary is proved directly. simplicity: high; the test layout mirrors the architecture. extensibility: high; new behavior slots into the right layer. observability: high; failures point to the correct owner. testability: high. migration risk: medium. parity impact: high.

### Candidate C: Rely mostly on doc-baseline and source-shape tests
- correctness: low; structure matters, but behavior can still drift. simplicity: high at first, low later because missing behavioral proof invites regressions. extensibility: medium. observability: low. testability: medium. migration risk: low. parity impact: medium.

Decision: Candidate B.

Book choice: the final architecture should be proved at the same boundaries where it is explained.

Why the others lost: Candidate A under-tests the core shape. Candidate C freezes text more strongly than behavior.
