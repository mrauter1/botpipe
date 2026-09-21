# Optimizer v2 requirements: native durable-function adaptation

**Status:** normative product and acceptance contract; not a test-pass report.  
**Scope:** `botpipe_optimizer`, the optimizer/refinement/evaluation-suite labs,
and the runtime provenance and provider-budget seams they use.

## 1. Product decision

Help a workflow maintainer decide what to improve next, why, and what evidence
would establish that it helped. The correct action may be to collect evidence
or make no change.

The governing rule is:

> Capture facts once. Models propose explanations and changes. Deterministic
> checks bind every result to the exact evidence and files it concerns.
> Improvement claims require a comparable experiment.

Recommendation and concrete validation remain separate. The optimizer never
edits, executes, or promotes the selected workflow. Refinement materializes one
chosen candidate and validates it in isolation. Optional paired evaluation runs
one frozen plan against baseline and candidate; it never promotes automatically.

The runtime and configured validation programs are trusted local code. File
identity and staging checks detect drift and accidental source substitution;
they are not an operating-system sandbox against malicious code running as the
same user.

## 2. Mapping from the upstream graph design

This major version deliberately keeps the evidence and integrity contract while
using a smaller native runtime:

| Upstream term | Native durable-function term |
| --- | --- |
| compiled workflow/topology | decorated callable contract and source fingerprint |
| step execution | journaled operation in an observed runtime scope |
| route tag/target | recorded operation outcome; Python owns the next branch |
| trace/checkpoint | SQLite run metadata, operation ledger, and replay cursor |
| provider attempt ledger | provider operation, attempt receipts, events, and usage |
| static authoring surface | exact callable package surface manifest |
| workflow result artifacts | immutable `ArtifactHandle`s returned from recorded operations |

Consequences:

- Arbitrary Python has no complete static topology. Source inspection says what
  may run; optimizer evidence says only what was observed.
- Rework is an explicit recorded outcome in one scope, not a reconstructed graph
  cycle. Independent runs are recurrence, never proof of one loop or cause.
- `route_tags` remains an input alias for filtering recorded outcome labels. It
  does not restore a route table.
- `provenance_start` and `provenance_end` replace inferred current topology and
  Git identity. Exact verified package hashes are used when available; missing
  historical identity remains unknown, and changed start/end surfaces are mixed.
- `Botpipe.inspect()` run metadata and operations are the canonical evidence
  input. This major version does not recreate obsolete raw trace directories or
  Git logs; absent historical dimensions remain explicit rather than inferred.
- Old filesystem checkpoints are unsupported. They are neither imported nor
  silently repaired; start a new run under this major version.
- Generic stage receipts are retired in favor of the journal and immutable
  handles. The optimizer's publication receipt remains because it atomically
  commits a multi-file, externally consumed handoff.

## 3. Records and ownership

| Record | Owner | Meaning |
| --- | --- | --- |
| `EvidenceSnapshot` | deterministic capture | admitted runs, observations, groups, metrics, shortlist, limits, and provenance |
| `CandidateSet` | producer, then independent reviewer | proposed changes or an explicit evidence/no-change action |
| surface/execution manifests | deterministic file enumeration | exact editable boundary and frozen runnable tree identities |
| `ValidationResult` | isolated validation runner | derived file changes, compilation/check results, environment, and resource evidence |
| recommendation receipt | optimizer publisher | reviewed candidate IDs and immutable evidence/baseline/handoff identities |
| paired evaluation record | paired runner | frozen two-arm protocol results and measured comparison state |

Every schema is versioned and strict where extra fields could alter execution or
publication meaning. Content IDs hash canonical record content and file
identities, excluding self-ID fields and temporary absolute paths.

Models may author candidate text and review findings. They never own operation
counts, usage, durations, hashes, source identity, execution status, comparison
metrics, or publication state. Deterministic code rejects invented citations,
duplicate IDs, disabled kinds, and altered facts; it does not silently rewrite
an accepted model claim.

A candidate has one unique content-derived ID, kind, targets, cited observation
IDs, proposed change, expected effect, risks, and falsifiable validation plan.
Kinds are `producer_prompt`, `verifier_rubric`, `tokens`, `workflow`, and
`evaluation_case`. Empty candidate sets use `collect_evidence` or `no_change`,
not placeholder candidates.

## 4. Evidence capture and prioritization

Default selection considers the latest 25 matching terminal or paused runs.
Explicit `run_refs` select exact runs. Automatic status filtering never
overrides explicit references. Active or changing input must not be presented
as a stable snapshot.

Capture preserves run/task/workflow identity, operation ID and scope, kind,
name, status, outcome, timing, provider usage, and start/end provenance. An
observation ID binds run and operation identity. Missing provenance, usage, or
timing remains explicit and cannot be replaced by zero or current metadata.
Provider observations also retain each physical dispatch ID, attempt and
generation, outcome, usage availability and reported usage, elapsed seconds,
provider, effective model, effort, and full policy fingerprint. The full policy
fingerprint is audit evidence; it is not a profile grouping key.
These dispatch/profile additions and the physical-dispatch latency semantics are
published as `botpipe.workflow_optimization.evidence/v3`; candidate, review, and
workflow protocol versions do not change.

Evidence admission operates on complete records. Check byte limits before
parsing or copying; never parse truncated JSON. An oversized run may be excluded
with `input_limit_exceeded` while a later smaller run is admitted. Reports state
selected/admitted/excluded counts, focused and captured observation counts,
omitted bytes, and actual denominators.

Comparable groups require a verified workflow/surface identity. Unknown
identities do not compare equal. A start/end surface mismatch is mixed and not a
stable current baseline. Historical observations remain individually useful,
but they cannot be relabeled with the current source hash or pooled into a
current rate.

Provider profiles are a separate stratum inside an unchanged structural group.
The small profile key is the recorded provider, effective model, and effort.
Recorded effort explicitly set to null (known unset) differs from an absent
effort fact. A dispatch missing any profile component has no stable comparable
profile and does not compare equal to another unknown dispatch. Mixed-profile
retries and steps using different profiles retain separate per-step/profile
breakdowns. Reliability still deduplicates by affected run and step, so those
breakdowns do not count one failure more than once.

Objectives order observed burden only:

- `reliability`: distinct runs with direct failed/interrupted operations, then
  distinct runs with recorded rework/replan outcomes;
- `token_usage`: complete positive provider-token totals for every contributing
  dispatch; incomplete operations go to `measure_first`;
- `latency`: complete positive physical provider-dispatch time for every
  contributing dispatch; generic operation/activity duration is ineligible and
  incomplete dispatch timing goes to `measure_first`.

Token ranking uses `selection_basis=sum_of_reported_token_counts`. Reported
counts from different provider/model profiles can use different tokenizers, so
the profile strata remain visible and `profile_comparison=none`. Latency ranking
uses `selection_basis=sum_of_provider_dispatch_seconds`. Dispatch seconds are
additive observed provider burden, not end-to-end wall latency: ten parallel
one-second dispatches sum to ten provider-dispatch seconds even though wall time
may be close to one second. A step with complete objective facts and unknown
profile identity may rank by its absolute observed burden, but it cannot support
profile-relative claims.

`top_k_steps` is one total shortlist cap for the selected evidence group. No
per-profile quota or fairness allocation modifies that global ordering. No
eligible evidence produces zero model calls and a deterministic empty set.
Reports must not invent probability, confidence, monetary cost, causality, or
full-corpus claims.

## 5. Recommendation workflow and limits

The default workflow is:

1. Deterministically capture provenance, bounded observations, grouping,
   metrics, shortlist, and baseline identity.
2. If eligible evidence exists, run one producer for one strict `CandidateSet`
   and one independent verifier. Bounded rework stays inside that pair.
3. Deterministically validate identities and citations, render the report, and
   atomically publish the receipt and refinement handoff.

Candidate kinds are not mandatory specialist stages. Enable flags restrict
allowed kinds but do not dynamically add model conversations.

| Limit | Default | Contract |
| --- | ---: | --- |
| `history_limit` | 25 | selection bound before evidence admission |
| `top_k_steps` | 1 | one total deterministic shortlist |
| `max_candidates` | 3 | total candidate-set cap; never silently truncate |
| `max_provider_turns` | 6 | shared actual-dispatch cap |
| `provider_turn_timeout_seconds` | 600 | per-dispatch timeout |
| `max_analysis_seconds` | 1800 | absolute non-extending recommendation deadline |
| `max_evidence_bytes` | 50 MiB | complete admitted input records |
| `max_output_bytes` | 10 MiB | accepted candidate/review/supporting records |

`provider_budget(*, max_turns, max_seconds, turn_timeout_seconds)` is journal-backed
and dynamically inherited by nested workflows and parallel branches. It reserves
before every actual transport dispatch, including repair and authorized retry.
Native receipt recovery does not dispatch and does not consume a new turn.
Concurrent reservations are atomic. Nested budgets all apply.

Resume preserves consumed turns, the absolute UTC deadline, and the remaining
ceiling. Suspended time counts. A wall-clock rollback or changed limit is an
error; no resume path extends the deadline. Each dispatch receives the smallest
applicable configured timeout, per-turn timeout, and remaining time. Providers
using timed budgets must declare and honor `supports_timeout=True` by stopping
and joining all effects before returning.

Limit exhaustion may preserve an incomplete diagnostic receipt with a precise
reason. It may never publish unreviewed candidates as accepted.

## 6. Exact files and isolated validation

Freeze before candidate editing. A frozen candidate bundle binds:

- original source hashes and executable-mode semantics;
- the editable surface identity and allowed package roots;
- the complete execution-source tree identity; and
- an optional selected installed-package layer at its import-relative path.

The candidate may change or remove captured files and add files only below an
allowed captured directory boundary. Manifests derive all paths, sizes, hashes,
change kinds, counts, and IDs from disk. A submitted manifest cannot nominate a
different root or forge derived fields. Rehash authoritative sources, frozen
inputs, and candidate files before launch and publication.

Execution uses private baseline and candidate trees. The Python probe starts in
isolated mode, resolves project-owned flat, `src/`, namespace, and installed
package imports from staging, imports the requested `@workflow` definitions,
and validates their source origins and signatures. It does not claim to
enumerate dynamic branches. Compilation must succeed independently of an
external command's exit status.

External validation accepts `target_test_argv: list[str]`, runs without a shell
in the private working directory, and records that it is an external check.
Legacy `target_test_command` is POSIX-`shlex` convenience, is mutually exclusive
with argv, and is unsupported on Windows. Pytest argv is normalized to the
selected Python interpreter. Timeouts, output tails, and execution-tree size are
bounded. Owned descendants are terminated and reaped on timeout/cancellation.

These mechanisms protect authoritative inputs and provenance; they do not make
the external program untrusted or sandboxed. Candidate effects must cross a
non-retry-safe durable operation boundary. Validation never promotes.

## 7. Optional paired evaluation

`evaluation_spec_path` on refinement is the sole opt-in. Freeze and validate the
specification, evaluator bytes/mode, case bytes and ordered IDs, repetitions,
settings, metrics, thresholds, and limits before either arm launches. The
baseline and candidate get disjoint execution/output trees and the same plan.

Launch exactly one evaluator subprocess per arm. Pass absolute
`BOTPIPE_EVAL_REQUEST` and `BOTPIPE_EVAL_RESULT` paths. The strict result echoes
execution, surface, and specification IDs and contains exactly one ordered
record per `(case_id, repetition)`. Metrics are finite non-boolean numbers;
evidence is regular non-symlink content under the allowed output directory.

Stale/missing output, crashes, nonzero exit, timeout, cancellation, identity
mismatch, duplicate/unknown/missing cases, invalid metrics, source mutation, or
oversized output makes the comparison incomplete. A protocol failure cannot be
converted into a scored target failure.

For complete comparable results, normalize each metric so positive is better.
Any primary or guardrail regression beyond its threshold yields `regressed`;
otherwise meeting the primary minimum yields `improved`; otherwise
`no_material_change`. Incompatible settings or incomplete evidence yields
`inconclusive`. One stochastic repetition is an observed difference, not a
generalized result. Generated cases remain `development_cases` unless a truly
withheld suite establishes an evaluation claim.

Botpipe-backed evaluators require equal per-arm provider budgets reused across
all cases, retries, and repairs. External evaluators receive process/output
limits but no claimed internal provider-call cap. No hidden third arm, search,
or automatic promotion is allowed.

## 8. Handoffs and migration

The optimizer publishes `workflow_refinement_evidence.json` and
`optimization_publication_receipt.json`. Select exactly one `candidate_id`.
Refinement accepts either that receipt/ID pair or the legacy complete
`evaluation_summary_path`/`evaluation_findings_path` pair, never both.
`evaluation_case` candidates route to `workflow_to_eval_suite`; all other kinds
route to refinement. Optional paired evaluation belongs only to refinement.

Versioned v1 artifacts remain historical evidence, not current proof.
Revalidate old candidates. Changed evidence, baseline, evaluator, case bytes, or
invocation identity fails closed instead of refreshing a durable anchor.
`max_candidates_per_pass` is a deprecated alias for the total cap;
`optimization_depth` changes budget defaults only and never enables hidden
execution.

## 9. Acceptance scenarios

The release must exercise all of these behaviors; the separate acceptance
inventory maps them to native tests without asserting that a particular CI run
has passed.

| ID | Scenario | Required result |
| --- | --- | --- |
| T01 | Original workflow is already importable; candidate is invalid; external command exits zero | Isolated compilation fails; no accepted validation |
| T02 | Valid candidate in flat/`src`/namespace or installed package layout | Staged origins and behavior are used; authoritative bytes stay unchanged |
| T03 | Forged roots, paths, flags, sizes, hashes, counts, or IDs | Derived-field validation rejects them |
| T04 | Source, frozen input, candidate, or manifest changes across phases/resume | Identity drift prevents accepted publication |
| T05 | Evidence record is malformed, oversized, or changed | It is excluded or rejected; no partial parse or false citation |
| T06 | Historical provenance is missing, unknown, or mixed | Facts remain visible but are not pooled as current evidence |
| T07 | Separate runs have similar failures | They remain recurrence, not one causal/rework loop |
| T08 | Nested/parallel scopes interleave | No cross-scope parentage or blame is invented |
| T09 | Usage is complete, partial, unknown, zero, repaired, or retried | Availability and dispatch totals remain distinct and exact |
| T10 | Source/model/provider identities differ | Structural groups remain unchanged; per-step provider/model/effort strata remain separate; unknown stays noncomparable; one literal-burden top-K applies globally |
| T11 | Failure-only or outcome-filtered sample | Actual denominators are visible; no probability claim |
| T12 | Reliability, usage, and latency leaders differ | Objective ordering is reproducible with one total shortlist cap |
| T13 | Model invents citations, counts, IDs, metrics, or disabled kinds | Strict records and deterministic anchors reject publication |
| T14 | Eligible evidence, then no eligible evidence | One proposal/review pair in the first case; zero provider calls in the second |
| T15 | Repair/retry/parallel child/resume reaches a provider cap or deadline | Shared reservations persist; no extra dispatch or successful over-budget receipt |
| T16 | Compile/test/provider hangs or emits excess output/children | Bounded diagnostics survive; owned process tree exits; sources remain unchanged |
| T17 | Evaluator/result identity, cases, metrics, output, or frozen bytes are invalid | Comparison cannot report improvement |
| T18 | Improvement, regression, tie, guardrail failure, or noncomparable environment | Correct state and claim scope; never automatic promotion |
| T19 | Unsafe staging/cleanup path or invalid eval manifest | No unrelated path changes; previous accepted output is not overwritten |
| T20 | Old receipt/checkpoint/alias and every maintained consumer | Honest unknowns, explicit restart/revalidation, and coherent handoffs |

Passing focused optimizer, runtime/provider, labs, subprocess containment,
packaging, and import tests is a release gate. This document does not itself
claim that those gates passed or that any proposed optimization improves an
unseen workload.
