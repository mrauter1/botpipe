# Provider-first rewrite acceptance

Snapshot: 2026-09-22 UTC, PRD revision 1.3, branch
`rewrite/provider-first-sdk`. This is an acceptance audit, not a release claim.

**Pass** means the complete scenario has passing deterministic evidence in the
current suite. **Partial** means substantial behavior is implemented, but a
required branch, platform, or native proof is missing. **Blocked** means a
required behavior is absent or contradicted. Protocol transcripts and stub SDK
packages prove Botpipe's emitted protocol and fail-closed parsing; they are not
native integration receipts.

## Release decision

**Blocked.** The deterministic runtime is broadly implemented, but the completed
release baseline in section 7.5 is not met:

- Codex's public app-server profile implements mediated query and nonempty
  exact-grant generation. Pinned Codex 0.131.0 always exposes `update_plan` and
  `request_user_input`, so empty-grant generation is rejected before dispatch.
  A07's required empty inventory cannot be established with that interface.
- Pi uses the same pinned SDK and persistent session format for generate,
  query, and run. Cross-process locator continuity and permission resets have
  deterministic coverage; credentialed native transitions remain unproved.
- Real adapters do not establish a verified non-secret native account identity.
  Common provider/configuration/profile/version/model/workspace affinity is
  enforced, but account and native default-model drift remain A10 gaps.
- A shared host/account registry now coordinates overlapping workspace roots,
  dynamic read claims, and unresolved effects. Deterministic admission,
  reader/writer, crash-recovery, and identity checks pass; mandatory native
  end-to-end evidence for A48 is still required.
- No credentialed pinned-native receipts were produced for Codex, Claude, Pi,
  or JEV. The Codex/Claude/Pi bridge tests use fakes or stub transcripts. Native
  Linux and Windows containment, cancellation, resumed-session, hostile-config,
  and transition gates therefore remain unrun. The local host also cannot run
  the required bubblewrap isolation profile.
- Actual Claude Agent SDK 0.2.155 and Pi 0.73.1 package startup checks passed
  without inference. They establish dependency/API compatibility, not native
  conformance. See `native-capability-evidence.md` for the exact checks.
- The earlier remote CI run exposed Python 3.13 path serialization and nonroot
  test-fixture failures. Both have focused fixes. Current branch CI is tracked
  separately from credentialed native conformance.

## Core and provider acceptance

| ID | Status | Evidence and remaining requirement |
| --- | --- | --- |
| A01 | Pass | Managed continuity, separate constructions, explicit `Session`, and `session=None` are covered by provider API tests. |
| A02 | Pass | Immutable derivation, lazy family/session sharing, explicit overrides, and empty command-grant clearing are tested. |
| A03 | Pass | Direct and workflow calls share the coordinator; typed values/errors, nested `Result`, artifacts, and usage aggregation are tested. |
| A04 | Partial | Durable handle reconstruction and fake-provider restart recovery pass. Pi's persisted locator resumes across stub bridge processes, but the required native restart matrix has no receipts. |
| A05 | Pass | Task/work-item continuity, stable child scopes, and pre-dispatch ownership/affinity rejection are covered. |
| A05b | Pass | Reconstructed aliases, sharing-topology drift, and stale cross-run revision rejection have focused tests. |
| A06 | Pass | Session claims and locks serialize shared turns; independent parallel sessions are exercised. |
| A07 | Blocked | Claude and Pi inventory closure has source/stub coverage, but no native receipts exist and the public Codex profile cannot provide tool-free generation. |
| A07b | Partial | All three SDK/app-server adapters mediate exact grants and persist resolved envelopes before dispatch. Descriptor/process and hostile-policy tests pass; native receipts are absent and the local bubblewrap isolation probe cannot execute. |
| A08 | Partial | All three SDK/app-server query profiles implement bounded descriptor-confined read/list/search and the scoped snapshot-based count-lines command. Hostile local and protocol tests pass; mandatory credentialed native receipts remain absent. |
| A08b | Blocked | Requests reset permission each turn, Pi uses the same SDK across all operations, and session continuation has deterministic coverage. Codex rejects required empty-grant turns and binds native threads to a tool-registry fingerprint; no required native transition/repair/stream/resume matrix is proved. |
| A09 | Partial | Common validation and concrete-profile rejection happen before dispatch in focused tests. The full mandatory native option/schema/continuation matrix is not proved. |
| A10 | Partial | Fake-provider substitutability and recorded provider/profile/version/model affinity pass. Real adapters do not implement the optional `session_affinity()` hook, so native account/default-model identity drift through environment credentials is not established; native equivalence and continuation also remain unproved. |
| A11 | Pass | Schema extra-field policy, malformed/unsupported distinctions, bounded repair, and repair charging are covered. |
| A12 | Partial | Native JEV payload shapes, session-free selection, typed replay, and uncertain recovery are tested with mock HTTP; no pinned credentialed JEV receipt exists. |
| A13 | Pass | Each dispatch/repair/retry receives a distinct dispatch identity and capability profile; usage and no-turn replay/recovery are covered. |
| A45 | Pass | Construction/derivation are I/O-free; lazy default pinning, explicit vendor precedence, missing-default errors, and new-family config changes are tested. |
| A46 | Pass | Saved adapter/config replay, cross-run family binding, unresolved-attempt routing, and saved-policy/current-ceiling intersection are covered, including tighter ceilings that do not invalidate committed replay. Secret-bearing durable settings are rejected. |
| A47 | Pass | Scoped `current_run().provider`, independent constructions/roots/children, and intentional stored-session sharing are tested. |
| A48 | Partial | Supplied-read authorization/replay, descriptor identity, and bounded immutable tool evidence have focused tests. All three mediated profiles record observations before delivery. The shared ownership registry atomically coordinates overlapping roots, including newly claimed ancestors, dynamic reads, independent state directories, and unresolved effects. Credentialed native end-to-end receipts remain required. |

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
| A33 | Pass | Packaged Ralph covers plan rejection/replan, item rework feedback, reports, per-item session boundaries, and completion. A focused second-item interruption is reconciled and resumed through the packaged workflow; the completed first item and plan turns are not repeated, the interrupted item alone retries, and completed replay makes no provider calls. |
| A34 | Pass | Devloop phase repair and test failure paths, final audit/follow-up preservation, docloop skip behavior, and depth controls are exercised. |
| A35 | Pass | Goal objective/subgoal/status/edit/resume/clear actions, blocker/replan/budget/repair paths, and Image-to-game input/child/result flow have focused tests. |
| A36 | Pass | Code-to-workflow source evidence, discovery, verifier-driven replan, materialization, and validated publication are exercised. |
| A37 | Pass | All fifteen labs discover and complete. The fourteen ordinary labs have independent normative artifact inventories and per-lab rework, backward-replan, question, blocked, and terminal-failure scenarios; deterministic publication gates are exercised in-workflow. The optimizer lab covers empty/eligible evidence, rejected-review retry, terminal review failure without publication, generation integrity, and consumer handoffs. See `labs-acceptance.md`. |
| A38 | Pass | Empty evidence makes zero provider calls; bounded producer/independent-review evidence and unknown/mixed filtering are covered. |
| A39 | Pass | Interrupted/tampered generations, identities, handoffs, receipt switches, and loaders are tested without mixed publication. |
| A40 | Pass | Authority preservation, isolated bounded validation, four comparison outcomes, and interrupted/saved/tampered pair recovery are covered. |
| A41 | Pass | CLI/SDK workflow inputs, config precedence, typed answers, reconciliation, JSON output, exits, and non-importing discovery have subprocess tests. |
| A42 | Pass | Built the final sdist and built its wheel in isolation; installed that wheel into a fresh environment. Verified base/adapter imports without extras, assets and `py.typed`, all 20 workflow catalog entries, durable sync/async fake-provider calls and replay. Strict mypy consumer checks preserve typed values through derivation, scoped defaults, sync/async operations, decisions, streams, and context managers. The documented Claude extra installed and passed actual-package empty-tool preflight; the separately pinned Pi npm package passed actual startup checks. Native turns and remote CI remain separate gates. |
| A43 | Pass | The chosen journal application/user versions are checked before mutation and unsupported stores are rejected untouched. Existing journal mechanisms are retained where useful; compatibility-only readers/converters are unnecessary for the selected format. Historical implementations are permitted on engineering merit, with no legacy compatibility obligation. Manual response reconciliation remains supported. |
| A44 | Pass | `provider-first-design-decisions.md` compares all four representative authoring jobs with the baseline and a credible simpler alternative, and records the remaining ergonomic costs. |

## Test evidence snapshot

The integrated fix suite passed **1,151 tests**, with **two Windows-only skips**
on Linux, in 144.62 seconds. This receipt includes request recovery, cancellation
response adoption, typed direct errors, ownership coordination, policy narrowing,
portable path serialization and fixtures, and the optimizer's separate continuing
review session. It also covers Codex incremental role updates, dynamic and
ancestor reads, operation-specific recovery ownership, and unknown-run rejection.
A subsequent focused ownership check covers removal of settled dynamic-reader
claims so normal queries do not accumulate orphan metadata.

The two skipped cases are native Windows Job Object acceptance and smoke tests.
Windows CI also includes the new app-server and workspace coordination suites.
Credentialed adapter conformance remains a separate gate.

Subprocess tests run with an absolute worktree `PYTHONPATH` to avoid accidentally
importing the baseline editable checkout. The isolated sdist/wheel build, clean
installed-wheel imports/assets/catalog and sync/async/replay smoke, strict public
API type check, Python compilation, JavaScript syntax check, and diff whitespace
check passed. The package discovers all 20 workflows. Supported-platform CI is
verified separately on the published commit.

The following evidence must still be attached before this document can record a
release pass:

1. Supported-platform CI, including the native Windows containment cases skipped
   on this Linux host.
2. Native pinned-version receipts on supported Linux and Windows profiles for
   all mandatory provider/capability combinations, fresh and resumed sessions,
   hostile ambient configuration, cancellation, recovery, and transitions.
3. A compliant Codex command-free interface, verified native account affinity,
   or an explicit approved PRD scope change. The former no-marker race is
   covered by shared hierarchical claims. No scope reduction has been assumed.
