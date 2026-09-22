# Provider-first rewrite acceptance

Snapshot: 2026-09-22 UTC, PRD revision 1.2, branch
`rewrite/provider-first-sdk`. The shared worktree was still changing during this
review. This is an acceptance audit, not a release claim.

**Pass** means the complete scenario has passing deterministic evidence in the
current suite. **Partial** means substantial behavior is implemented, but a
required branch, platform, or native proof is missing. **Blocked** means a
required behavior is absent or contradicted. Protocol transcripts and stub SDK
packages prove Botpipe's emitted protocol and fail-closed parsing; they are not
native integration receipts.

## Release decision

**Blocked.** The deterministic runtime is broadly implemented, but the completed
release baseline in section 7.5 is not met:

- Codex remains a public run-only profile. The source-audited app-server bridge
  is intentionally unwired because pinned Codex 0.131.0 always exposes
  `update_plan` and `request_user_input`, contradicting A07's empty-inventory
  requirement.
- The public Pi SDK profile still advertises `sessions=False` and rejects a
  Python request carrying a session, so its new bridge-level session locator is
  not yet wired through managed generate/query/run/generate continuity.
- Claude and Pi now prepare durable tool evidence before dispatch and write an
  observation before a successful tool result. In the current Pi handler,
  however, a `ToolEvidenceError` is caught by the generic tool-error handler and
  returned to the planner; the native turn can continue instead of being
  stopped and fenced after evidence persistence fails.
- No credentialed pinned-native receipts were produced for Codex, Claude, Pi,
  or JEV. The Codex/Claude/Pi bridge tests use fakes or stub transcripts. Native
  Linux and Windows containment, cancellation, resumed-session, hostile-config,
  and transition gates therefore remain unrun. The local host also cannot run
  the required bubblewrap isolation profile.
- A local clean-wheel smoke run imported packaged assets and `py.typed`, found
  all 20 packaged/labs workflows, and completed a durable fake-provider call.
  An isolated `claude-agent-sdk==0.2.155` install also passed adapter preflight
  and verified the closed option inventory without making a native turn. Final
  sdist/wheel artifacts and CI are still pending.

## Core and provider acceptance

| ID | Status | Evidence and remaining requirement |
| --- | --- | --- |
| A01 | Pass | Managed continuity, separate constructions, explicit `Session`, and `session=None` are covered by provider API tests. |
| A02 | Pass | Immutable derivation, lazy family/session sharing, explicit overrides, and empty command-grant clearing are tested. |
| A03 | Pass | Direct and workflow calls share the coordinator; typed values/errors, nested `Result`, artifacts, and usage aggregation are tested. |
| A04 | Partial | Durable handle reconstruction and fake-provider restart recovery pass. Pi has no resumable SDK session, and the required native restart matrix has no receipts. |
| A05 | Pass | Task/work-item continuity, stable child scopes, and pre-dispatch ownership/affinity rejection are covered. |
| A05b | Pass | Reconstructed aliases, sharing-topology drift, and stale cross-run revision rejection have focused tests. |
| A06 | Pass | Session claims and locks serialize shared turns; independent parallel sessions are exercised. |
| A07 | Blocked | Claude and Pi inventory closure has source/stub coverage, but no native receipts exist and the public Codex profile cannot provide tool-free generation. |
| A07b | Blocked | Descriptor/process mediation and exact-grant protocol tests exist; Codex is unwired, native receipts are absent, and the local isolation probe cannot execute. |
| A08 | Blocked | Bounded descriptor-confined read/list/search and exact-command tools have hostile local tests. Mandatory native query profiles and receipts are incomplete, including Codex. |
| A08b | Blocked | Requests reset permission each turn and Claude has session plumbing, but Pi rejects continuation, Codex lacks the profiles, and no native transition/repair/stream/resume receipt exists. |
| A09 | Partial | Common validation and concrete-profile rejection happen before dispatch in focused tests. The full mandatory native option/schema/continuation matrix is not proved. |
| A10 | Partial | Fake-provider substitutability and recorded provider/profile/version/model affinity pass. Real adapters do not implement the optional `session_affinity()` hook, so native account/default-model identity drift through environment credentials is not established; native equivalence and continuation also remain unproved. |
| A11 | Pass | Schema extra-field policy, malformed/unsupported distinctions, bounded repair, and repair charging are covered. |
| A12 | Partial | Native JEV payload shapes, session-free selection, typed replay, and uncertain recovery are tested with mock HTTP; no pinned credentialed JEV receipt exists. |
| A13 | Pass | Each dispatch/repair/retry receives a distinct dispatch identity and capability profile; usage and no-turn replay/recovery are covered. |
| A45 | Pass | Construction/derivation are I/O-free; lazy default pinning, explicit vendor precedence, missing-default errors, and new-family config changes are tested. |
| A46 | Pass | Saved adapter/config replay, cross-run family binding, unresolved-attempt routing, and saved-policy/current-ceiling intersection are covered, including tighter ceilings that do not invalidate committed replay. Secret-bearing durable settings are rejected. |
| A47 | Pass | Scoped `current_run().provider`, independent constructions/roots/children, and intentional stored-session sharing are tested. |
| A48 | Blocked | Supplied-read authorization/replay and bounded tool evidence have focused tests; Claude and Pi record successful observations before tool return. Pi currently converts evidence-write failure into a planner-visible tool error instead of stopping the turn. Native end-to-end receipts are absent, and live reads have a remaining race when no workspace marker exists at the fence check and a writer creates one before the read. |

## Durability and resource acceptance

| ID | Status | Evidence and remaining requirement |
| --- | --- | --- |
| A14 | Pass | Committed values/failures replay without execution; completed roots return without changing limits or provenance. |
| A15 | Pass | Completed effects survive compatible edits; input, position, type, callable, and structural-contract drift fail before new effects. Explicit contract registries restore structurally identical local/generated types. |
| A16 | Pass | Recorded and current retry safety govern automatic rerun; unsafe interruption remains unresolved unless explicitly reconciled. |
| A17 | Partial | Checkpoint, response, normalization, capture, and rollback crash tests are extensive. Every native spawn/session/terminal stage is not proved for every required adapter/platform. |
| A18 | Pass | Recovered terminal responses advance the saved session before pending artifact capture and the next turn. |
| A19 | Partial | Missing/malformed receipts and ambiguous/foreign ownership fail closed locally. Native cross-platform identity and live-descendant cases lack the required runner evidence. |
| A20 | Partial | Timeout/cancel now uses typed stop outcomes and retains ownership on uncertainty; POSIX/local and simulated Windows paths are tested. Native Windows and mandatory-provider receipts are absent. |
| A21 | Pass | Foreign clients/state directories cannot use unresolved workspaces; confirmed settlement/reconciliation releases ownership. |
| A22 | Pass | Lost storage acknowledgements are confirmed from durable state or remain uncertain without duplicate dispatch/publication. |
| A23 | Pass | Direct calls use durable internal roots; interrupted calls can be inspected, resumed, and reconciled without an application workflow. |
| A24 | Pass | Required/optional output sets, schemas, stale/preexisting files, aliases, duplicates, symlinks, rollback, and external drift are broadly covered. |
| A25 | Pass | Validated values checkpoint before capture; resume avoids revalidation/repair and preserves immutable versions. |
| A26 | Pass | Manual reconciliation uses typed stopped/completed outcomes plus complete digest/absence maps and detects later drift. |
| A27 | Pass | Invalid/correct typed answers, durable pending state, explicit `None`, single replay, and parallel targeting are covered. |
| A28 | Pass | Worklist selection/order/payload is durable across source/status changes and completed items are not repeated. |
| A29 | Pass | Atomic nested/parallel reservations, repair charging, recovery non-charging, absolute deadlines, and run-local limit changes are tested. |
| A30 | Partial | Sync/async streaming, ordered events, terminal-result reuse, bounded buffers, early-exit cancellation, and explicit replay markers pass locally. Required native live-stream and cancellation receipts have not run. |
| A31 | Partial | Sync run cancellation and async direct cancellation converge on durable typed outcomes and prevent late success; artifact/fence tests retain ownership. Native provider and Windows finalization receipts are absent. |
| A31b | Pass | Sync/async workflow, activity, nested, parallel, provider, and human-pause parity is covered without coroutine leakage. |
| A32 | Pass | Unavailable/dynamic/mutated/mixed source is labeled conservatively; compatible edits resume and optimizer attribution requires a stable verified revision. |

## Product acceptance

| ID | Status | Evidence and remaining requirement |
| --- | --- | --- |
| A33 | Partial | Ralph plan rejection/replan, item rework feedback, completion, reports, and per-item session boundaries are covered. Worklist interruption/replay is tested at the shared primitive, but no focused interruption through the packaged Ralph workflow was found. |
| A34 | Pass | Devloop phase repair and test failure paths, final audit/follow-up preservation, docloop skip behavior, and depth controls are exercised. |
| A35 | Pass | Goal objective/subgoal/status/edit/resume/clear actions, blocker/replan/budget/repair paths, and Image-to-game input/child/result flow have focused tests. |
| A36 | Pass | Code-to-workflow source evidence, discovery, verifier-driven replan, materialization, and validated publication are exercised. |
| A37 | Partial | Every labs manifest discovers and every lab completes a staged fake-provider success run; shared rework/replan/question/failure/publication controls are tested, but each lab's applicable branch matrix is not enumerated end to end. |
| A38 | Pass | Empty evidence makes zero provider calls; bounded producer/independent-review evidence and unknown/mixed filtering are covered. |
| A39 | Pass | Interrupted/tampered generations, identities, handoffs, receipt switches, and loaders are tested without mixed publication. |
| A40 | Pass | Authority preservation, isolated bounded validation, four comparison outcomes, and interrupted/saved/tampered pair recovery are covered. |
| A41 | Pass | CLI/SDK workflow inputs, config precedence, typed answers, reconciliation, JSON output, exits, and non-importing discovery have subprocess tests. |
| A42 | Partial | A local clean-wheel smoke run covered imports, assets, `py.typed`, all 20 workflow catalog entries, and a durable fake-provider call. An isolated Claude SDK extra install passed real-package option preflight without a native turn. Final sdist/wheel CI and other documented optional-adapter installation paths are still pending. |
| A43 | Pass | New application/user versions are checked before mutation, incompatible stores are rejected untouched, legacy APIs/readers/converters are absent, and old data cannot enter optimizer/labs history. New-format manual response usage remains supported. |
| A44 | Pass | `provider-first-design-decisions.md` compares all four representative authoring jobs with the baseline and a credible simpler alternative, and records the remaining ergonomic costs. |

## Test evidence snapshot

The latest complete run reported by the coordinating review while Pi integration
was still changing had **922 passed, 1 failed, 2 skipped**. The remaining failure
was in the in-flight Pi bridge work; the skips were platform-specific. This does
not satisfy the release suite gate. Earlier concurrent runs also produced
subprocess import and checkpoint failures that were not reproducible once the
edited files stabilized, so they are not counted as stable acceptance failures.

The following evidence must still be attached before this document can record a
release pass:

1. A green full suite and clean-wheel/install job, including the complete A42
   checks.
2. Native pinned-version receipts on supported Linux and Windows profiles for
   all mandatory provider/capability combinations, fresh and resumed sessions,
   hostile ambient configuration, cancellation, recovery, and transitions.
3. A compliant Codex command-free interface, fully wired resumable Pi SDK
   sessions, fail-closed Pi evidence-write handling, and closure of the
   no-marker live-read race, or an explicit approved PRD scope change.
4. An enumerated A37 branch record showing every applicable labs path.
