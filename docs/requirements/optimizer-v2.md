# Botpipe Optimizer — Trustworthy Evidence, Simple Improvement Workflows

**Status:** Implementation-ready after three review rounds · **Revision:** 1.0  
**Baseline:** `mrauter1/botpipe@7690d0d75cd18b45c5e84847c778f867179136ea`  
**Scope:** `botpipe_optimizer`, its lab consumers, and narrowly required runtime evidence/dispatch seams.  
**Deliverable:** Requirements and implementation sequence; no implementation or deployment is implied.

## 1. Product decision

Help a workflow maintainer decide **what to improve next, why, and what evidence would establish that the change helped**. Sometimes the correct next action is to collect missing evidence, repair an input, or make no change. Generating more candidate files is not the objective.

The governing rule is:

> Capture facts once. Models propose explanations and changes. Deterministic checks bind every result to the exact evidence and files it concerns. Improvement claims require a comparable experiment.

The default workflow remains candidate-only and does not execute or promote the selected workflow. Deliver two independently releasable increments: **optimizer v2** fixes integrity and simplifies recommendations; **paired validation** adds an explicit two-command comparison to the existing refinement workflow. The latter closes the measurement gap and is required for full PRD completion, but does not block releasing the corrected recommender. It is a deliberate scope addition with its own gate, not an autonomous experiment scheduler or a second workflow runtime.

### Required user journeys

| Journey | Required outcome |
|---|---|
| Diagnose recent runs | A bounded report of observed problems, coverage, candidate changes, and the next useful action. |
| Investigate a specific failure | Inspect selected run/route evidence with its surrounding context; do not turn the selected sample into a population success rate. |
| Validate a concrete candidate | Compile and check its exact files in isolation; publish the derived file changes and actual results. |
| Decide whether a candidate helped | Explicitly run the same frozen evaluation against baseline and candidate; report measured differences and limitations. |
| Resume interrupted work | Continue from the same evidence/baseline identities and remaining budgets, or clearly reject a stale/incompatible resume. |

Preserve provider-created multiple artifacts, required/optional artifact semantics, workflow parameter validation, stable case IDs, supported workflow reference forms, candidate/source separation, and explicit promotion. A candidate may affect multiple files and produce several artifacts.

### Alternatives considered

| Approach | Benefit | Burden / limitation | Decision |
|---|---|---|---|
| Patch individual helpers; retain nine model stages | Lowest immediate migration cost | Fixes defects but retains repeated facts, model calls, and ownership ambiguity | Use for the first correctness slice only. |
| One evidence snapshot, one bounded proposal/review cycle, deterministic validation/publication | Several defects disappear through shared ownership and identity rules; ordinary use becomes smaller | Requires coordinated schema and lab changes | **Selected release design.** |
| General experiment scheduler, policy engine, plugin registry, automatic promotion | Broad future automation | Adds services and abstractions before a demonstrated consumer needs them | Out of scope. |

Do not replace nine fixed stages with a generic stage scheduler. Use the existing Botpipe workflow, session, provider, artifact, and checkpoint mechanisms.

## 2. Success criteria and boundaries

Optimizer v2 is complete when criteria 1–6 and 8 hold; the paired-validation increment additionally requires criterion 7. Full PRD completion requires both:

1. An invalid candidate cannot pass the independent compilation check, including when the original workflow is already imported.
2. Every factual field in a successful receipt can be reproduced from its referenced, verified files and execution results.
3. Missing evidence is visible and never treated as zero cost, success, causal support, or a verified baseline.
4. Independent runs/items cannot be mislabeled as the same rework loop or a demonstrated causal chain.
5. An ordinary recommendation needs one producer turn and one independent verifier turn, absent repair/rework. No-evidence input needs no model call.
6. Limits are enforced by execution code; timeout/budget exhaustion cannot publish a successful or improved result.
7. Explicit paired evaluation produces a reproducible comparison without executing extra candidate generation or promotion.
8. Each reviewed issue is covered by a requirement and acceptance case in §12; the affected tests and maintained lab workflows pass.

There is no arbitrary line-count reduction target. Report removed stages, duplicate representations, public obligations, and model turns. A smaller line count is useful only if behavior and diagnosis also become simpler.

**Trust boundary:** the runtime and configured test/evaluation programs are trusted application components. Identity checks detect artifact/source drift and accidental edits; they are not a security sandbox against malicious code with unrestricted access to the same operating-system account. Keep checks independent of model-authored artifacts and do not claim stronger protection.

**Non-goals:** automatic deployment/promotion, a generic benchmark platform, learned/calibrated probability models, a new database or event bus, arbitrary repository dependency discovery, and a wholesale Botpipe SDK redesign.

## 3. Ownership and minimal representation

Use a small number of coherent records. Prefer ordinary typed data plus functions; no class hierarchy or registry is required.

| Record | Owner | Meaning |
|---|---|---|
| `EvidenceSnapshot` | Deterministic capture | Selected runs, normalized observations, evidence checks, comparable groups, computed metrics, selection policy, and source identity. |
| `CandidateSet` | Model producer; independently reviewed | Proposed changes or evidence-collection actions, with cited observation IDs, expected effect, risks, and a falsification/validation plan. |
| `SurfaceManifest` | Deterministic file enumeration | Exact baseline or candidate file identities and allowed boundary. |
| `ValidationResult` | Validation runner | Bound surface IDs, actual compilation/test/evaluation outcomes, command/environment identities, and resource use. |
| Recommendation receipt | Deterministic optimizer publisher | Reviewed proposal IDs and snapshot/baseline IDs; always `improvement = not_evaluated`. |
| Validation receipt | Deterministic refinement publisher | The selected proposal, concrete surface IDs, actual ValidationResult, and truthful comparison scope. |

### Explicit handoff and publication boundaries

The optimizer finishes with a reviewed `CandidateSet`, its evidence snapshot ID, and its captured baseline surface ID. It does not assert that proposed code exists or has passed tests. A caller selects exactly one `candidate_id` (which may describe several coordinated file changes). Workflow/prompt/token/rubric proposals go to the existing refinement workflow. `evaluation_case` proposals go to the existing evaluation-authoring workflow and are rejected by the workflow-refinement entry point. New or repaired cases receive a new suite identity; they never modify the frozen evaluator/cases of an existing comparison. Cases generated from observed failures are development cases. Both handoffs carry the selected proposal and its evidence/baseline IDs. Refinement verifies them, materializes the candidate files from that baseline, and invokes validation. It may retain its existing concrete implementation steps; simplifying the recommender does not silently remove refinement functionality. Additional new changes require a new proposal/review, not silent widening of the selected candidate.

The handoff includes immutable IDs/paths and the selected proposal; refinement rejects unknown IDs, mismatched snapshots, or stale authoritative source. Recommendation publication succeeds without R5 execution. Concrete candidate publication requires R4/R5 and carries `not_evaluated` unless R6 ran. A schema-valid empty CandidateSet may produce a truthful gap/no-change recommendation receipt; invalid output only produces an incomplete/error receipt, and it cannot be handed off as an implementation candidate.

Canonical optimizer outputs are `workflow_optimization_evidence.json`, `workflow_optimization_candidates.json`, `workflow_optimization_report.md`, and `optimization_publication_receipt.json`, plus the existing `workflow_refinement_evidence.json` projection and referenced snapshots/raw/supporting artifacts. Disabled kinds use empty collections inside CandidateSet, not a collection of placeholder files. IDs hash canonical versioned record content and referenced file identities, excluding only the self-ID field and temporary absolute locations.

Serialization and in-memory structures share one schema definition per record. Use versioned JSON schemas/models with unknown fields rejected where they could change execution or publication meaning. Human-readable Markdown and legacy handoff envelopes are projections, not alternative sources of truth.

Model output must not own counters, file hashes, source identity, execution status, or measured comparison values. Models may write candidate content, explanation, and separate review findings. Preserve those bytes; validation returns errors rather than silently rewriting accepted model claims. A deterministically rendered report can quote model text while clearly labeling it as a hypothesis.

A candidate has a unique ID, a kind (`producer_prompt`, `verifier_rubric`, `tokens`, `workflow`, or `evaluation_case`), targets, cited evidence IDs, proposed change, expected effect, risks, and validation plan. Use a shared envelope and a typed payload for each meaningful kind. Do not force all changes into one unvalidated dictionary. “Collect evidence” and “no change” are explicit next actions, not fake candidates.

## 4. R1 — Capture usable evidence without inventing certainty

### Selection and eligibility

- Default to the latest 25 completed/paused runs across success, failure, awaiting-input, and blocked statuses for the selected workflow. Exclude actively changing runs by default. Capture a stable file/event watermark before reading; compare run status and input-file identities before and after capture, rejecting a concurrently resumed/changed run rather than publishing a torn snapshot.
- Explicit `run_refs` select those exact runs; automatic history/status selection does not silently override them. Reject wrong identities. Explicit active-run requests fail with an actionable message; this release does not analyze partial live runs.
- `route_tags=[]` means no route filter. A filter selects focus observations while preserving needed context separately. All aggregate metrics declare whether their denominator is the full captured group or the focused subset.
- Core eligibility requires parseable, supported run identity and trace records. Missing/invalid core input excludes that run with a machine-readable reason. Missing Git history, raw output, usage, or historical topology does not discard otherwise usable observations.
- Retain an issue per missing/invalid optional dimension. An empty Git log has no more evidentiary value than a missing log. Preserve existing commits when available; a dirty run-start repository is not an optimizer error.
- Resolve the workflow once per capture. Reuse its inspection for capability, parameter, authoring, and decomposition views; avoid resolve/write/read cycles.

### Observations and raw references

Preserve run/task/workflow identity, sequence, visit, step execution ID, scope, item ID, step kind, explicit runtime outcome/route semantics, provider attribution, hook/redirect metadata, and raw usage. An observation key combines run identity with execution identity; use sequence as a documented fallback, never pool identical step names into one execution.

A raw reference retains its path, recorded digest, recorded byte count, and a verification result. Resolve only run-relative paths under the captured run directory; reject absolute/traversal paths and symlink escapes. Verify regular-file existence, digest, and byte count. Copy verified selected bytes into the durable optimizer snapshot once, within the byte limits in R7. Later phases read that copy and verify its snapshot identity; they do not follow mutable original raw paths.

Unavailable/invalid raw content remains visible as a gap and cannot be cited as inspected evidence. Metrics directly supported by intact trace fields remain usable. Before publication, reject candidate citations to unknown observations or to evidence content that was not verified. Reports may explicitly cite the fact that evidence is missing.

## 5. R2 — Measure executions, recurrence, and usage correctly

### Failure and recurrence semantics

- Direct failures/rework come from explicit runtime/compiled route semantics. Custom application routes without a declared meaning remain unclassified; their names are not proof of success or failure.
- The execution lane key is `(run_ref, scope, item_id)`. Legacy unscoped events share one run lane only when recorded topology establishes sequential execution without branch/worklist ambiguity; otherwise lineage is unknown.
- A rework cycle requires an explicit rejection/rework whose observed or compiled target returns to the same step, followed by another execution of that step in the same lane with increasing execution/visit identity. Repeated visits alone can be normal iteration and are insufficient. Count cycles separately from rejected attempts.
- Recurrence across runs has a distinct-run count. Two runs containing one rejection each never establish a loop.
- A later-event association follows an observed route/target to the next execution in the same lane. Extend transitively only across fully matched hops. Missing hops/scope/topology mean unknown association. Static reachability alone is insufficient, and associations remain hypotheses about dependency or time, never proven causes.
- Remove automatic “downstream symptom” penalties and name-based prompt detection. Determine editable surfaces from the compiled authoring surface.

### Usage and time

Each attempted provider dispatch is `known_total`, `partial`, or `unknown`; `not_attempted` is separate and contributes no cost or missing-data penalty. A provider-reported total, including zero, is authoritative. Otherwise derive a total only from known input and output components and label it derived. Cached input and reasoning tokens remain subcomponents of inclusive totals.

Prefer per-attempt records, keyed by dispatch/execution identity, and include failed, retried, and repair dispatches exactly once. Use step-finished phase aggregates only as a legacy fallback for an execution with no attempt records; never add both representations. Producer/verifier/direct-LLM/repair phase fields are not assumed to be independent if the schema describes one as an aggregate. Preserve partial evidence rather than inventing missing attempts.

New dispatch records contain dispatch ID, execution/lane identity, phase/attempt, effective provider/model/effort, start/end or elapsed time, outcome, and usage availability. Emit the start/reservation before launch and completion even on failure where observable. A reserved/interrupted dispatch with no result is attempted with unknown usage. Reuse the runtime trace/provider-event path, not a new log service.

“Complete usage” means every observed attempted dispatch has a known total. Report known subtotal and completeness/attempt coverage separately; a partial subtotal is never full run cost. Python steps with no provider calls have measured no-provider cost, not missing usage. Missing-usage detection uses availability, not dictionary truthiness.

Use recorded elapsed time with units. Step latency and run wall time are different measures; parallel step durations must not be summed into run latency. If timing is unavailable, latency ranking is unavailable. Do not translate tokens into money without an explicit versioned price table and applicable provider/model identity.

## 6. R3 — Honest comparison and prioritization

### Comparable evidence groups

The fixed structural group key is `(workflow identity, recorded workflow SurfaceManifest ID, normalized topology ID)`. The topology ID hashes executable step/route structure, excluding timestamps and temporary absolute paths. The workflow surface is the exact R4 editable boundary; optional additional local inputs must be explicitly declared there. No automatic dependency discovery is required.

At run start, runtime-owned provenance records these IDs, parameter/configuration digests, and the available provider policy identity. Record source identity again at run end; a changed surface makes that run mixed/unverified for pooling unless per-execution provenance is available. Effective provider/model/effort comes from dispatch records, since it may vary by step. Reuse existing trace/configuration fields and keep credentials out of stored identities.

Within one known structural group, rank observed burden across its steps and show parameter/provider/model/effort/case-mix breakdowns. Token counts mean reported token units and elapsed seconds mean recorded time; their sums may span providers but are not monetary cost, normalized efficiency, or predicted benefit. `top_k_steps` is one total cap for this group, never per provider stratum. Do not pool comparative rates or present before/after effects across unmatched strata. Case mix remains a displayed limitation for diagnosis; R6 controls it for measured comparisons. Runtime-only Git commits do not create a new structural group.

For the default shortlist, choose the most recently completed group whose recorded surface/topology matches the current capture; use `(completion timestamp, run_ref)` as a deterministic tie-break. Never assign a current fingerprint to old runs. Unknown identities are not mutually equal and do not establish a pooled group.

If no current matching group exists, retain per-run historical facts and hypotheses in the report, mark the recommendation basis `historical_unverified` or `historical_verified`, and suggest capturing current evidence. Explicit `run_refs` opt into historical investigation: a single known historical group can be shortlisted with a historical label; mixed/unknown groups produce separately labeled per-run findings and evidence-collection actions, never one pooled ranking. No additional stratum-selector API is introduced. Unknown-identity runs remain individually inspectable and can support cited single-run hypotheses, but cannot produce pooled rates or a current-compatible default shortlist. This preserves useful old evidence without manufacturing comparability.

### Ranking contract

Add `objective = reliability | token_usage | latency`, default `reliability`. These identify **observed operational burden**, not reducibility, expected benefit, or output quality. Constraints/free-text focus guide proposals without secretly changing numerical weights. R6 measures task quality and improvement.

Shortlist eligibility precedes ordering: reliability requires a direct failure/rework; token usage requires complete positive recorded usage; latency requires complete positive recorded time. Steps with no editable surface can yield an input/implementation/evidence action, not a fabricated prompt change. No eligible step means `no_actionable_evidence`, zero model calls/candidates, and a deterministic `collect_evidence` or `no_change` action. A model may likewise return zero candidates with a reason after inspecting eligible evidence.

| Objective | Deterministic starting order within the selected structural group |
|---|---|
| Reliability | Distinct runs with direct failures descending, then distinct runs requiring rework descending, then step ID. Report rates and denominators alongside counts. |
| Token usage | Complete total tokens descending, then step ID. Incomplete steps appear in a separate “measure first” list. |
| Latency | Complete total step elapsed time descending, then step ID. State that this is aggregate step time, not predicted workflow speedup. |

Show sample size, distinct runs, attempted dispatch count, selection/filter policy, coverage, group, and stratum. A failure-only sample never becomes a population success rate. No fabricated probabilities, numeric confidence, or `LLM attribution` label on deterministic output. A high-usage step may legitimately yield `no_change`.

The model can nominate a different target if it cites evidence and labels the rationale as a hypothesis; preserve the deterministic starting order. Objective changes are visible in invocation and report. Explicit single-run historical investigations can use an observed eligible event for a labeled hypothesis; they cannot assert current compatibility or pooled rates. For automatic history selection, the default comparable-group/zero-call rule remains unchanged.

## 7. R4 — Bind baseline, candidate, and publication to exact files

Use one canonical manifest derivation function for capture, checking, and receipt construction. Its identity is a digest of the versioned boundary plus sorted normalized relative paths, file digests, byte counts, and a normalized executable bit (where supported; record unsupported mode semantics explicitly). Absolute temporary paths and timestamps do not contribute to content identity.

- Capture baseline files into a durable run-owned snapshot before model work. Persist its canonical manifest/ID, evidence snapshot ID, and invocation identity in the existing checkpoint before dispatch. Resume reuses and rehashes those exact bytes; it never recaptures. A displayed manifest is a projection of that runtime-owned anchor, never populated from provider outcomes.
- All baseline/candidate validators require the expected resolved root from runtime context. A manifest cannot nominate another directory. Validate every path under that root and the declared editable boundary; reject duplicate paths and escaping links.
- Derive exact listings, counts, sizes, digests, added/changed paths, and change flags from disk plus the baseline. Compare all submitted derived fields with that result. Remove opt-in switches that weaken these invariants.
- Preserve all baseline paths in this release; additions follow the existing explicit allowed boundary. Deletion support is a separate future product decision.
- Regenerating both a modified source manifest and its source must fail against the runtime-held baseline anchor. Recheck authoritative source drift immediately before publication. Do not claim coverage of undeclared external dependencies.
- Safe cleanup/write targets must be nonempty contained child paths; reject absolute paths, `..`, equality with the parent, and overlap between baseline/candidate/authoritative roots before mutation. Allocate staging using `tempfile` under a dedicated run-owned parent; recursive cleanup accepts only returned allocation paths or an exact matching run-identity ownership marker. Never delete an arbitrary preexisting caller directory, even if it is contained. Per-file atomic rename prevents torn files; a final atomic receipt commits the set, and readers ignore uncommitted siblings.

Each validation works on a frozen staging copy. Completely enumerate and hash its code boundary before and after every execution phase, detecting additions, deletions, content/type/link/executable-bit changes. Exclude only fixed documented cache/output roots. Unexpected source mutation invalidates the result. Immediately before committing a receipt, rehash the durable baseline snapshot and candidate and require agreement with ValidationResult IDs. Changed candidates require new validation; previous results cannot be combined with new files.

Resume requires checkpoint ID, snapshot rehash, evidence ID, and invocation identity to agree, and preserves consumed budgets. If captured evidence/baseline or authoritative source has changed, stop with “baseline/evidence changed; start a new analysis,” rather than refreshing the anchor silently. Runtime storage is trusted as stated in §2; this is consistency across resume, not cryptographic protection from the runtime owner.

## 8. R5 — Execute the exact candidate with bounded validation

Replace in-process candidate import/compilation and `_preserved_workflow_modules` with a small internal subprocess probe. Reuse the existing loader/compiler in that probe.

1. For concrete refinement, freeze one complete project source tree at baseline capture. Exclude `.git`, `.botpipe`, `.venv*`, known caches/build outputs, and the harness-owned staging/output roots; persist the exact exclusion list and sorted inventory. Existing project files needed to run may not be silently excluded. If excluded generated/build material is required, fail with setup instructions. This Python-focused increment does not execute preparation/build commands or silently synthesize a different common base. This snapshot is the **execution tree**, distinct from the smaller editable workflow surface. Its ID binds unchanged sibling helpers/framework code as well as editable files. Inventory only regular files/directories; reject symlinks and special files in the captured code boundary with an actionable path error. Symlink materialization is outside this increment. Before copying, enforce `max_execution_tree_files=100000` and `max_execution_tree_bytes=512 MiB` per tree (positive configurable limits). The baseline source snapshot and two arm trees use at most three owned full copies; do not duplicate the candidate tree for the compile probe. Fail before staging/launch on overflow; never truncate source.
2. When the selected workflow is supplied by an installed Python package outside the project tree, capture the complete owning top-level package from its exact resolved origin (for built-ins, the resolved `botpipe/` directory) as a **selected-package layer**. Stage it at its import-relative path before overlaying candidate files. Its inventory joins the execution-tree ID and the same combined per-tree size/file limits, drift checks, and resume rules. Resolve that package prefix only from staging, never from the installed/editable original. Do not copy an arbitrary checkout or all of site-packages. Reject conflicting project/package paths explicitly; if the package is already inside the project snapshot, capture it only once.
3. Make separate private baseline/candidate execution trees from those frozen bytes, overlaying only allowed candidate paths. Never silently substitute another importable checkout. Record interpreter and third-party distribution/environment identities. All project-local code is the captured source tree, so no dependency-discovery framework is needed.
4. Use an isolated Python bootstrap that starts without inherited project imports or executable site customization, then adds only the staged project and explicit third-party dependency roots. A supported implementation is explicit-interpreter `-I -S` plus a bootstrap that adds approved paths before importing Botpipe. Do not process editable-install `.pth`/site hooks that redirect project packages. Validate module origins against staged project and approved third-party roots; project package prefixes resolve only to staged code. Record origins/digests for the selected workflow and loaded project modules.
5. Run Python/pytest checks through the same bootstrap. Detect/reject conftest/plugin path changes that load project modules from authoritative or other copies. A generic external command is recorded as an external check, not proof of Python source coverage. No fallback to ordinary imports after isolation failure.
6. Re-enumerate the source tree after each phase. Return requested/compiled workflow identities and source digests; reject missing/duplicate/mismatched probe results. Actual compilation must succeed independently of the external command's exit code.

Canonical command input is `argv: list[str]`, executed without a shell. Legacy strings are parsed using documented POSIX rules only; require argv on Windows rather than guessing Windows quoting. Retain pytest-to-explicit-interpreter normalization. Test executable/argument paths containing spaces.

Default compile timeout: **60 seconds**. Default test/evaluation timeout: **600 seconds per invocation**. Defaults are overridable by positive explicit values. Terminate the process tree on timeout/cancellation, wait for it to exit, and clean only owned staging directories. Use owned process groups on POSIX and a supported Windows Job Object implementation with descendant cleanup; prefer existing/standard-library facilities over a new mandatory dependency. Fail before launch if the containment primitive cannot be established. Deliberately detached/malicious children are outside the trust boundary. After graceful cancellation, use a bounded termination grace (default five seconds), then force termination and reap the owned process tree.

Bound captured logs while the process runs, retaining at most **1 MiB per stream** plus a truncation indicator. Record argv, phase, elapsed time, exit code, timeout/cancellation state, and diagnostic tail. Hanging compilation is bounded just like hanging tests.

A successful `ValidationResult` contains baseline/candidate content IDs, validated boundary/root identity, derived change list, probe records, checks, environment identity, and optional evaluation comparison. The publication receipt uses this result unchanged; it does not reread model-supplied factual claims.

## 9. R6 — Optional paired validation, a separate increment

Optimizer v2 always publishes recommendations with `improvement = not_evaluated`. The follow-on capability is a small paired-command runner in the existing refinement path: **exactly one evaluator subprocess per arm**, with a fixed request/result contract. The supplied evaluator owns execution of its frozen cases through existing Botpipe or test tools. The harness does not add per-case scheduling, evaluator plugins, statistical modeling, or automatic search/promotion.

The caller explicitly supplies an evaluation specification; omission means no paired execution. It freezes evaluator argv/content, cases and case IDs, repetition count (default one), parameter/provider/environment settings, metrics, thresholds, and budgets before either arm runs. Evaluator/spec/case files live outside the candidate-editable surface and have recorded IDs. A candidate cannot change its evaluator or acceptance criteria. Different treatment settings are allowed only when explicitly part of the selected proposal and frozen plan.

### Fixed evaluator protocol

Launch the byte-identical evaluator/argv template once per arm in separate clean execution trees and independent session/workspace state. The harness supplies `BOTPIPE_EVAL_REQUEST` and `BOTPIPE_EVAL_RESULT` environment variables containing absolute paths in a newly allocated per-arm output directory. Other environment differences are limited to staged/output/session paths and declared treatment settings. Use opaque execution IDs in evaluator requests; the parent retains their baseline/candidate mapping.

The strict request JSON contains `schema`, `execution_id`, `surface_id`, `execution_tree_id`, `spec_id`, staged workspace path, frozen case-input path, ordered case IDs, repetition count, effective settings, allowed output directory, and remaining limits. The evaluator writes one atomic `botpipe.optimizer.eval_result/v1` JSON at the requested fresh result path:

- `execution_id`, `surface_id`, `spec_id` must echo the request and are verified against parent-owned records.
- `cases` has exactly one record for every planned `(case_id, repetition)` pair, with `outcome`, finite numeric metric values, optional evidence paths, usage availability, and elapsed seconds. Required metrics must be present; booleans, NaN, infinity, duplicate or unknown pairs are invalid.
- Evidence paths identify regular non-symlink files under the allowed output directory and are hashed by the harness. Stale/preexisting result files cannot satisfy a new invocation. `max_evaluation_output_bytes` defaults to 50 MiB per arm including the result JSON and referenced evidence, with at most 10000 files. Size-check/stream before parsing or copying; excessive output is incomplete, never truncated into a valid result. Monitor the owned output directory and cancel an oversized evaluator; this is an admission/cancellation limit, not a disk quota for arbitrary external writes.
- A nonzero evaluator exit, missing/invalid result, timeout, or exhausted budget is an execution failure/incomplete result even if another arm succeeds. Preserve both arms' diagnostics.

An expected target-workflow failure may be a valid scored case only when the frozen evaluator contract maps that outcome to specified metrics (for example, quality 0). An evaluator crash/protocol error cannot be converted after the fact into a convenient metric. All planned pairs stay in the denominator.

### Comparison and claim scope

The harness computes aggregates; evaluator summaries are non-authoritative. Support only `mean` and `sum` over the complete case/repetition set in this increment. Each metric declares units and direction. Normalize improvement as `d = candidate − baseline` for higher-is-better and `d = baseline − candidate` otherwise. Require a primary metric with positive `minimum_improvement` and nonnegative `maximum_regression`; each required guardrail has a nonnegative `maximum_regression`, all in the metric's stated units.

For complete comparable results: any primary/guardrail `d < −maximum_regression` yields `regressed`; otherwise primary `d >= minimum_improvement` yields `improved`; otherwise `no_material_change`. Missing evidence or incompatible settings yields `inconclusive`. Execution state separately records `not_run | complete | failed | timed_out | cancelled | budget_exhausted`; omission yields `not_evaluated`. Execution failure never yields `improved`.

Case/repetition order is frozen; record unsupported seeds/nondeterminism. One stochastic repetition supports an observed difference only, not a statistically established general improvement. Cases exposed during generation/refinement are development cases. Claims about generalization require a separate evaluation set withheld from those model contexts. Otherwise label `claim_scope = development_cases`; independent evaluations use `evaluation_cases`, never an unqualified universal claim.

The plan has explicit `max_elapsed_seconds` (default 1200), `per_arm_timeout_seconds` (default 600), and, for Botpipe-backed evaluators, `max_provider_turns_per_arm` (required). Both arms receive the same frozen per-arm dispatch cap and enforce it through R7's budget wrapper across all their cases/retries; a crash cannot return unused capacity to the other arm. Only elapsed time is shared: each arm receives at most its timeout and the total remaining time. A Botpipe-backed evaluator claiming enforcement must initialize and reuse that budget context for all its runtime calls; bypassing it is an unsupported integration. Arbitrary external evaluators receive a process deadline but no claimed internal model-call cap. Fixed retries belong to the supplied evaluator/spec, consume the same per-arm budget, and are reported. No hidden third evaluation or automatic promotion is allowed.

## 10. R7 — A smaller default workflow and real limits

### Default flow

1. **Capture:** deterministic inspection, evidence verification, grouping, metrics, and baseline anchoring. If no objective-eligible evidence exists under R3, publish a deterministic gap/no-change report with zero candidates and model calls.
2. **Propose and review:** one existing producer/verifier pair. The producer writes a `CandidateSet` and optional supporting artifacts; the independent verifier checks evidence references, relevance, constraints, and validation plans. It cannot alter captured facts. Rework stays in this pair.
3. **Publish:** deterministically validate IDs/references/boundaries, render the report, and write the receipt plus the refinement handoff.

Do not automatically create token, adversarial, verifier, producer, and workflow-level passes. Those are candidate kinds, not mandatory conversations. Preserve explicit enable/disable flags as allowed-kind restrictions. Specialized follow-up work is a new, focused invocation with its own explicit request. The default workflow never dynamically expands its topology or budget.

Use existing session objects and `verifier_session` to separate producer and verifier context. The verifier receives evidence, the candidate, and review criteria, without the producer’s private deliberation. Read immutable invocation parameters directly; checkpoint only evolving facts, anchors, consumed budgets, and reviewed candidates. Remove the repeated Params → State → invocation-contract field copies and per-pass empty-artifact factories. Validate all input before writing capture/evaluation-case outputs; invalid case input leaves previous outputs unchanged. Commit multi-artifact results with a final receipt so interrupted partial writes are never treated as complete.

### Limits and visible parameters

| Input | Default | Enforcement |
|---|---:|---|
| `history_limit` | 25 runs | Before capture. |
| `top_k_steps` | 1 | Deterministic shortlist; preserve justified alternative hypotheses. |
| `max_candidates` | 3 total | Schema/publication limit; excess output receives bounded rework, never silent truncation. |
| `max_provider_turns` | 6 | Hard maximum of Botpipe transport dispatches, shared across proposal/review/retry/repair. |
| `provider_turn_timeout_seconds` | 600 | Cancel/terminate the owned provider process on expiry. |
| `max_analysis_seconds` | 1800 | Overall recommendation deadline, including capture and model work. |
| `max_evidence_bytes` | 50 MiB | Total admitted run metadata, trace, Git/provenance, topology, and copied raw bytes; check before parsing/copying. |
| `max_output_bytes` | 10 MiB | Total admitted CandidateSet/supporting-artifact bytes; check sizes before reading/publication. |

Reserve a dispatch before calling the common provider transport; use the existing rendered-provider/transport adapter with an optional budget context and checkpoint fields, not a separate budget service. Count each Botpipe transport call once, including additional calls for runtime retries/repair. Persist `used_turns` before dispatch; interrupted attempts consume their reservation and resume does not reset it. Serialize reservations if concurrent calls occur. Custom integrations that bypass this boundary cannot opt into the guaranteed mode.

`max_provider_turns` bounds Botpipe dispatches, not hidden provider-internal recovery/model/tool activity, dollars, or tokens. Track reported usage; observed-token stop limits can stop future dispatches but are not hard token ceilings without provider support. Built-in CLI transports must terminate their owned process tree; custom async providers must support cancellation before the configured guarantee is advertised.

The recommendation deadline covers capture, proposal/review, and successful publication; refinement/paired validation are separate invocations. Persist an absolute UTC deadline, last observed UTC timestamp, and remaining-time ceiling in the checkpoint; use a monotonic clock while running. On resume, remaining time is the lesser of the saved ceiling and deadline-minus-current-time; it never increases. A detected wall-clock rollback invalidates resume rather than extending the budget. Every phase/turn uses `min(configured_timeout, remaining_time)`. Paused downtime counts. Bounded termination and writing an incomplete diagnostic receipt are allowed after expiry; accepted publication is not.

Byte limits apply before parsing/copying, including metadata/Git/provenance. Admit complete core run records in the declared run-selection order (newest completion first, stable run-ref tie); an over-limit run is excluded as `input_limit_exceeded`, and later smaller runs may still be admitted. Never parse a truncated JSON prefix or use outcome/route to decide core-run admission. Then admit optional evidence within the remaining cap: raw focus observations first, nearest matched-lane context next, with stable run/observation ties. Report selected/admitted/excluded counts and reasons, omitted IDs/bytes, and `budget_limited` when the sample changes. Every rate denominator is the actual admitted runs/observations; make no full-corpus claim. Raw omissions lower content coverage without changing intact trace denominators. R4 baseline capture and R5 trees independently obey the execution-tree file/byte admission limits; oversized baselines fail before copying. If a complete required result cannot fit, stop with an explicit limit reason. Output-byte limits bound accepted artifacts, not arbitrary filesystem writes by external tools. Log streams remain bounded during execution as in R5.

Budget/deadline/output-limit exhaustion preserves diagnostic work with an incomplete receipt and precise stop reason; it never publishes unreviewed candidates as accepted. Exceeding candidate count may use remaining bounded rework; exceeding admitted output bytes does not trigger an unbounded read or silent truncation.

## 11. R8 — Integration, migration, and implementation sequence

### Existing code responsibilities

| Current area | Required change |
|---|---|
| `optimization.py` | Split only by actual responsibilities if needed: capture/metrics, proposal publication. Reuse typed records; remove causal scoring, false confidence, and mutable fact ownership. |
| `candidate_surfaces.py` | One strict manifest projection; expected-root binding; subprocess validation; bounded commands and result-derived receipts. |
| `_selected_workflow.py`, snapshot helpers | Reuse one inspection; retain useful small wrappers. |
| `evaluation.py` | Validate cases in memory before outputs; reuse inspection; support the evaluation specification/result contract without another runtime. |
| `company.py` | Normalize statuses only; preserve task identifiers byte-for-byte after documented text validation. |
| Optimizer lab | Replace nine fixed pairs with the §10 flow; preserve purpose and the workflow name. |
| Refinement/decomposition labs | Pass expected roots; consume derived validation results; update publication receipts. Paired evaluation belongs to the refinement path. |
| Runtime tracing/provider transport | Add only missing provenance/attempt evidence and enforce configured optimizer dispatch limits through the existing seam. Defaults for unrelated workflows remain unchanged. |

### Representative interaction and input contracts

These are proposed interfaces, not claims about the current CLI:

```bash
botpipe run labs/workflows/workflow_run_traces_to_optimization_candidates review-1 \
  -wf selected_workflow devloop -wf task_title "Diagnose devloop" \
  -wf objective reliability
```

The response names the selected group, coverage, candidate IDs or a no-change/evidence action, and the recommendation receipt. To implement a selected workflow proposal, pass `optimization_receipt_path` and `candidate_id` to the existing refinement workflow. That entry point accepts exactly one primary source: this pair **or** its existing `evaluation_summary_path` plus `evaluation_findings_path`. Preserve the evaluated-evidence path; reject ambiguous combinations and selected-workflow mismatches. Additional supporting evidence remains explicitly referenced.

`evaluation_spec_path` is an optional refinement parameter enabling R6; no legacy depth flag implies it. The spec's canonical fields are `schema`, `evaluator_argv`, evaluator/cases content IDs and paths, ordered `case_ids`, `repetitions`, effective settings, primary/guardrail metric definitions, and the named limits in R6. Freeze/validate them before any paired launch. Test commands additionally accept `target_test_argv`; reject conflicting argv/string inputs. Evaluation-case proposals instead enter the evaluation-authoring path described in §3.

### Migration rules

- Version changed optimizer artifacts/results as v2. Existing runtime trace versions remain readable through a single normalization path; missing historical fields stay unknown. Do not rewrite history or recreate obsolete trace directories.
- Legacy candidate/validation receipts are historical evidence, never silently upgraded to proof under v2. Revalidate old candidates to obtain new receipts. Reject incompatible in-progress checkpoints with a clear restart instruction.
- Keep `workflow_refinement_evidence.json` as a deterministic handoff projection. Update all repository consumers together; it references v2 snapshot/candidate/result IDs. Do not maintain two independent candidate models.
- Preserve public helper names/signatures where safe and unambiguous with thin delegating wrappers. New strict identity/root requirements may require explicit keyword additions; document those breaks. Deprecate redundant root exports for one release instead of assuming that absence of repository call sites means absence of external users. No general compatibility framework.
- Replace `max_candidates_per_pass` with `max_candidates`; the legacy name maps to the new total cap with a visible migration warning. Conflicting old/new values fail validation.
- `optimization_depth=cheap|standard` becomes a deprecated alias: cheap uses 6 provider dispatches/1800 seconds and standard uses 12/3600; both use the same single proposal/review topology. Explicit limits take precedence. `ablation` remains planning-only and never enables execution. Tell callers to supply an evaluation specification for actual comparison. No mode can hide extra target execution.
- Replace obsolete README test paths and `stdlib/optimization.py` references. Document exact workflow-path invocation for labs, limitations, failure messages, and new output ownership.

### Delivery slices

**A. Correctness foundation:** establish focused regression cases; fix exact-candidate compilation, manifest/root/anchor checks, evidence verification, optional Git, usage/identity handling, task-ID normalization, and bounded subprocesses. Retain the current orchestration temporarily.

**B. Coherent evidence and recommendation:** v2 records, comparable groups, honest ranking, one proposal/review pair, deterministic projections, hard limits, transactional publication, and consumer migration. Remove superseded machinery in the same slice.

**C. Measured candidate comparison:** integrate the explicit paired-evaluation specification/runner contract with refinement, independent evaluation cases, receipts, and end-to-end acceptance. A+B constitute the optimizer v2 release and always report unmeasured improvement. C is separately releasable and optional to invoke. Full PRD completion requires C and its own evaluation gate; do not describe the measurement issue as solved when only A+B have shipped.

## 12. Acceptance and complete issue coverage

Use focused real subprocess tests for import/path/timeout behavior, deterministic fixtures for analysis, and a fake provider/evaluator for normal CI. Live paid-model evaluation is optional validation, not a prerequisite for testing the contracts.

| ID | Reviewed issue / acceptance scenario | Required result | Requirement |
|---|---|---|---|
| T01 | Original `ralph_loop` imported, editable `.pth`/sibling helper points at original; candidate invalid; external command exits 0 | Compilation fails and no success receipt is written. Repeat with an installed editable original package. | R5 |
| T02 | Valid candidate changes behavior; also test a consumer project without Botpipe source selecting an installed built-in | Compile/tests load staged candidate origins/digests, including the captured installed-package layer despite an original editable `.pth`; authoritative/installed files stay unchanged. | R4–R5 |
| T03 | Forge changed/added paths, change flags, sizes, counts, content IDs, or candidate root | Each false claim is rejected; receipt contains only recomputed metadata. | R4 |
| T04 | Change source plus manifest; corrupt resumed snapshot; alter candidate after validation; create/import a new code file during a check | Runtime anchor/result binding detects drift; publication fails. | R4 |
| T05 | Delete/tamper raw bytes; supply wrong length, digest, absolute/traversal/symlink-escape reference | Affected raw evidence is unavailable/invalid, cannot substantiate a citation; intact trace metrics remain usable. | R1 |
| T06 | Same valid run with no Git log, empty log, or disabled Git tracking | Same usable trace observations; no fabricated additional provenance or blanket exclusion. | R1 |
| T07 | Two independent runs with one rejection each; two real rework cycles in one lineage | First is recurrence only; explicit matched returns establish rework. Distinct-run and cycle counts remain separate. | R2 |
| T08 | Interleaved items/branches, normal iterative visits, unknown historical scope | No cross-lineage blame or invented loop/causal conclusion; unknown evidence is labeled. | R2 |
| T09 | LLM=100 tokens, repair=900; unknown usage; measured zero; partial retry/cached usage | Total 1000 for first; unknown differs from zero; incomplete totals and inclusive subcomponents are handled correctly. | R2 |
| T10 | Changed model/topology/source, commits containing runtime artifacts only, and missing metadata | Separate meaningful groups, no false commit-driven fragmentation, no relabeling old data as current. | R3 |
| T11 | Failure-only selection, empty route filter, Python step named like a model step, model step named `publish*` | Denominators/selection visible; empty filter works; structural surface detection; no invented probabilities. | R1–R3 |
| T12 | Fixtures with different failure, token, and time leaders | Objective changes reconstructible starting order; mixed providers yield visible resource breakdowns and one total top-k cap, never a cost/efficiency claim; incomplete data is a gap. | R3 |
| T13 | Model alters deterministic metrics or invents citations/IDs/counts; duplicate IDs across kinds | Facts remain anchored; structural validation rejects false references and duplicate IDs. | R1, R4, R7 |
| T14 | Typical valid input; no useful evidence; disabled candidate kind | Two nominal model turns; zero calls/candidates for no objective-eligible evidence; valid empty/no-change model output; no hidden specialist pass or forbidden kind. | R7 |
| T15 | Excess candidates, provider retries/repair, interrupted resume, elapsed deadline | Hard caps/deadline/admission respected; huge newest trace can be skipped for later small runs with admitted denominators; oversized baseline/tree fails before copy; reservations survive resume; no accepted unreviewed output. | R7 |
| T16 | Hanging compile/test/provider with child process and excessive output | Process tree exits on limit/cancel; bounded diagnostics survive; oversized tree/evaluator evidence and source symlinks/special files fail explicitly; authoritative source is unchanged. | R5, R7 |
| T17 | Candidate weakens evaluator; wrong/duplicate case IDs; NaN metrics; stale/missing results; evaluator crash vs declared failed case; single stochastic repetition | Frozen evaluator enforced; invalid/incomplete evidence cannot produce a valid improvement claim. | R6 |
| T18 | Known improvement, regression, tie, conflicting guardrail, noncomparable environment, development-only cases | Correct comparison state and claim scope; identical plan for both arms; no automatic promotion. | R6 |
| T19 | Task ID `paused`, traversal/overlapping/contained-but-unowned cleanup paths, invalid evaluation case manifest | ID preserved; no outside sentinel changed/deleted; invalid input changes no previous artifacts. | R4, R7–R8 |
| T20 | Old artifacts/checkpoints/parameters and every maintained consumer/import | History readable with honest unknowns; unsafe resume rejected; aliases documented; workflow/evaluation-case handoffs and both refinement input paths work with coherent receipts. | R8 |

**Gates:** optimizer v2 requires T01–T16 and T19–T20; paired validation additionally requires T17–T18. For each increment, all applicable cases are implemented and passing; optimizer unit tests plus affected runtime/provider and lab integration tests pass; packaging/import smoke checks pass; no stale authoritative producer-writable artifacts, obsolete candidate models, or broken documented commands remain. Test the default full recommendation and refinement publication paths, not just helper calls.

## 13. Review record

Round 1 used three independent reviews of architecture, evidence semantics, and validation/evaluation boundaries. Material revisions: separate recommendation/validation receipts and release increments; explicit proposal-to-refinement handoff; frozen execution-tree scope; durable snapshot/resume rules; isolated import bootstrap; portable argv/process containment; evaluator request/result protocol; precise lineage and usage precedence; actionable-evidence stop rules; grouping versus comparison strata; and byte/deadline admission semantics.

Round 2 confirmed the first-round blockers resolved, then identified bounded source/output admission, evaluation-case routing, an undefined preparation phase, global top-k versus provider strata, and per-arm evaluation budgets. Revision 0.3 resolves these with conservative source admission, existing evaluation-authoring handoff, no preparation command, direct resource-burden ordering with visible provider breakdowns, and symmetric per-arm budgets. Round 3 found no remaining architecture or evidence-semantics blocker. Surface review identified one final compatibility gap for installed built-in workflows; the selected-package capture rule and T02 now cover it without copying an unrelated checkout. The parent accepted these changes against the inspected loader/provider seams and checked complete issue coverage. No known material product-contract blocker remains. Further review should now target implementation behavior against the acceptance matrix rather than add abstractions to the PRD. “Implementation-ready” is a review conclusion, not a claim that the future implementation is proven correct.

## 14. Source anchors

All implementation observations refer to the baseline commit above; they are not claims about an uninspected later revision. The prior audit ran 76 optimizer tests successfully and reproduced defects outside their coverage. This PRD changes no repository code: its acceptance tests and release gates are requirements for the future implementation, not claims that those fixes already pass.

- [Optimizer package and public surface](https://github.com/mrauter1/botpipe/tree/7690d0d75cd18b45c5e84847c778f867179136ea/botpipe_optimizer)
- [Evidence normalization, attribution, ranking, publication](https://github.com/mrauter1/botpipe/blob/7690d0d75cd18b45c5e84847c778f867179136ea/botpipe_optimizer/optimization.py)
- [Candidate surface derivation and validation](https://github.com/mrauter1/botpipe/blob/7690d0d75cd18b45c5e84847c778f867179136ea/botpipe_optimizer/candidate_surfaces.py)
- [Optimizer workflow and contracts](https://github.com/mrauter1/botpipe/tree/7690d0d75cd18b45c5e84847c778f867179136ea/labs/workflows/workflow_run_traces_to_optimization_candidates)
- [Refinement workflow](https://github.com/mrauter1/botpipe/tree/7690d0d75cd18b45c5e84847c778f867179136ea/labs/workflows/workflow_and_eval_to_refined_workflow_package)
- [Runtime trace writer](https://github.com/mrauter1/botpipe/blob/7690d0d75cd18b45c5e84847c778f867179136ea/botpipe/runtime/tracing.py) and [provider transport contract](https://github.com/mrauter1/botpipe/blob/7690d0d75cd18b45c5e84847c778f867179136ea/botpipe/core/providers/protocols.py)

Design decisions also follow the current `Architecture_Design_Guide.md`: compare credible alternatives, make structure enforce a few clear rules, and count caller and operational burden alongside implementation size.
