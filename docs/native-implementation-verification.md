# Native implementation verification

Verified on 2026-09-22 against Botpipe commit
`dc8a93f084b41bd2ae2c1ff4af3ce9e6b4fef45a`.
The observations below describe the pre-implementation feasibility checks, not
a release-conformance claim. The implementation follow-up records the subsequent
fixes separately.

## Decisions after verification

1. **Support current Codex; do not require the old 0.131.0 release.** The current
   stable release was 0.155.1, released on September 18. The installed 0.153.3
   binary was used for preliminary checks, then the current official release
   was downloaded and tested independently. The old claim that two internal
   tools cannot be disabled does not apply to 0.155.1.
2. **Use app-server per-turn collaboration instructions for roles.** Native
   request captures verified changed-role updates, unchanged-role deduplication,
   explicit role reset, structured output, and conversation continuation across
   a process restart. Base instructions, the prior input prefix, and the prompt
   cache key remained unchanged in the tested profile.
3. **Specify the effective operation profile on every turn.** In particular,
   query/generate must send `environments: []` each time. A restarted thread
   reintroduced native tools when this field was omitted, despite having been
   created with an empty environment list. The existing Botpipe bridge already
   sends this field explicitly. Retain empty environments for mediated turns
   when RUN moves onto the shared transport; RUN must explicitly supply its own
   full environment and permission profile on each turn.
4. **Share transport code, not an assumed universal tool registry.** Dynamic
   tools remain thread-scoped. Keep exact inventory bindings for mediated
   threads and a separate native RUN profile until each proposed same-thread
   transition has equivalent inventory and permission evidence. Never relax a
   fingerprint or silently replace a conversation to make a transition pass.
5. **The simple bubblewrap-wrapper proposal is not approved as a complete
   lifetime fix.** Namespace-init death has the required kernel semantics, but
   outer bubblewrap-process exit does not establish that fact. Startup ownership
   and namespace-init termination need a separately verified lifecycle contract.

## Current Codex evidence

Tested executable: official `codex-cli 0.155.1`, release source commit
`be2951ea34f0d295ed0becf97079f92fa5f6950e`.
The downloaded Linux musl `.zst` asset matched its published SHA-256:
`42d0611ac331ea324c343fabadde30d05018af9a270557765aeef7afe028f7eb`.

The probes launched the actual executable with a disposable configuration home,
a disposable workspace, and a localhost Responses API fixture. The fixture
returned fixed assistant responses and never requested tool execution. No account
credentials or external model service were used. The configured model was
`gpt-5.4`; therefore inventory results cover that local model-catalog profile,
not every account-provided model catalog or hostile configuration.

| Check | Observed result |
| --- | --- |
| Current generated protocol schema | Per-turn environments, approval policy, sandbox policy/permission profile, collaboration mode, and output schema are present. Dynamic tools are present only on thread creation. |
| Role A, role B, unchanged B, reset, unchanged reset | Developer-message counts were `1, 2, 2, 3, 3`. |
| Resume the same thread in a new app-server process and repeat | Counts were `4, 5, 5, 6, 6`; native thread identity was unchanged. |
| Conversation preservation | Each preceding request's entire input array was an exact prefix of the next, including across process restart. |
| Stable request components | Base instructions, prompt cache key, tool definitions, and output schema stayed equal in the explicit-profile continuation test. |
| Exact single-tool profile | Only the declared `botpipe_read` appeared in all five initial and five resumed requests. |
| Empty dynamic inventory | The native model request contained `tools: []` in all five requests. |
| Omitted environment override after restart | `apply_patch` and `view_image` reappeared alongside `botpipe_read`; explicitly sending `environments: []` removed them. |
| Native RUN startup with ordinary local environment/document loading | Failed before the model request because this host denies a socket required by the native filesystem sandbox. |
| Existing Botpipe focused tests | `31 passed, 1 skipped` across app-server, process-containment, and native SDK adapter tests. |

These are native protocol and request-history observations. They do not measure
real model compliance, real provider cache hits, authenticated account behavior,
or successful native command execution. The fixture's usage counters are synthetic.
Reset appends instructions superseding the earlier role; it does not delete old
role messages. The [machine-readable evidence](evidence/native-verification-2026-09-22.json)
records request hashes and per-request assertions for the accepted continuation,
zero-tool, and omitted-environment diagnostic cases.

### Required closures in the tested mediated profile

In addition to the existing ambient-feature closures, isolated configuration,
disabled web search, disabled project-document loading, and explicit empty
environments, these current settings matter:

```json
{
  "tools.experimental_request_user_input.enabled": false,
  "tools.update_plan.enabled": false,
  "features.goals": false,
  "orchestrator.skills.enabled": false
}
```

The initial no-override inventory included `request_user_input`, the three goal
tools, `skills`, the declared dynamic tool, and `tool_search`. Disabling the old
feature switches alone still left `skills`. Disabling `orchestrator.skills`
removed that remaining source. `features.default_mode_request_user_input` alone
does not hide the current request-user-input tool.

The probe also explicitly disabled skill search, recommended plugins, token
budget tools, current-time reminders, sleep, and deferred execution. This is
not a claim that these switches close all possible model-specific tools: current
source can register additional utilities from model metadata. Exact inventory
and ambient-configuration coverage remain part of profile conformance.

### Version and session policy

Replace the old exact-version requirement with a maintained compatibility
contract targeting current stable Codex. Required protocol fields and effective
configuration must be checked, and operation-specific native conformance tests
must run against supported releases, including current stable. Record the exact
version in evidence for reproducibility; do not force users to downgrade to an
obsolete release.

Protocol schema presence alone does not prove tool containment. Do not replace
the old equality check with an unconditional `version >= minimum` acceptance
rule for strict mediated profiles. Newly supported tool surfaces need equivalent
inventory evidence. Session compatibility should follow the verified semantic
profile and native compatibility, with explicit rejection of incompatible
transitions before dispatch and no automatic conversation reset.

## Linux lifetime evidence

The host has bubblewrap 0.9.0 and util-linux unshare 2.39.3. Harmless launch
probes failed before running their payload:

| Probe | Result |
| --- | --- |
| Bubblewrap user + PID namespace | `setting up uid map: Operation not permitted` |
| Bubblewrap PID namespace | `Creating new namespace failed: Operation not permitted` |
| Bubblewrap network namespace / existing exact-command mediator | `Failed to create NETLINK_ROUTE socket: Operation not permitted` |
| `unshare --user --map-root-user` / `unshare --pid --fork` | Permission denied |
| Delegated cgroup availability | cgroup v2 is mounted read-only; no writable delegated subtree |
| User systemd scope | No user bus available |

No host restriction was disabled. Consequently, filesystem/environment/network
parity and actual namespace cleanup could not be established here. The native
Codex 0.155.1 local-environment startup failed for the same NETLINK_ROUTE reason.

The source review establishes two different facts:

- Linux kills all remaining namespace members when that namespace's init dies.
- The runtime must prove that init died. Waiting for the outer bubblewrap
  process alone does not prove it. Upstream issue 633 documents a parent-death
  signal setup race affecting the `--unshare-pid` default reaper too.

Therefore retain the Windows Job Object backend, and do not ship a Linux fix
that merely wraps `Popen` in bubblewrap and waits for the wrapper. A namespace
backend needs a verified pre-execution ownership handshake, stable ownership of
namespace init, and confirmation of its termination. A deployment-provided
cgroup with creation-time membership and confirmed empty state remains an
alternative. Process-group enumeration is not an equivalent fallback.

## Remaining acceptance work

- Validate the selected Linux lifecycle backend on a host that permits its
  required kernel mechanisms, including startup interruption, parent death,
  detached descendants, and cleanup failure. Preserve the existing native
  filesystem, network, credential, environment, and stdio behavior.
- Exercise native RUN tools, permission transitions, cancellation, and artifact
  writes on supported hosts. Per-turn protocol support is established; full
  native execution parity is not.
- Exercise authenticated/account model catalogs and hostile ambient
  configuration before advertising broad current-Codex mediated support.
- Measure actual cached-token usage separately; request-prefix preservation is
  established for the tested continuation sequence, not a cache-hit guarantee.

## Implementation follow-up

The branch now implements the six reviewed fixes:

- Linux uses an atomic namespace-init ownership handshake and stable pidfds;
  Windows retains suspended-start Job Object ownership. Effectful payloads
  start only after ownership is established, and cleanup confirms the kernel
  lifetime boundary. Unsupported hosts fail closed before dispatch.
- Codex RUN uses the app-server transport and explicit per-turn permissions.
  Role updates append to the same native conversation; unchanged roles deduplicate
  and reset uses a superseding developer instruction. No model is substituted.
- Standalone query/generate roots retain read ownership, while arbitrary
  workflows, runs, and records lacking a narrower mode retain write ownership.
- Recovery combines exact-attempt stopped/completed cancellation evidence,
  rejects conflicting facts, and validates provider response families before
  session, artifact, or checkpoint mutation.
- Optimizer supporting artifacts come only from the accepted proposal.

`tests/test_codex_native_contract.py` exercises the actual current Codex binary
against a local Responses fixture: continued roles, exact empty inventories,
native command execution, and writable/read-only policy enforcement. CI downloads
the current stable release and verifies its published asset digest; it does not
install an old Codex release. Linux and Windows native-contract jobs must pass
before these new integration checks count as evidence. They do not establish
authenticated account behavior or real cached-token usage.

## Review follow-up: ownership, results, and interruption recovery

One OS-backed execution guard now owns each canonical journal/run across initial
execution, resume, and manual resolution. Workspace read claims still permit
independent readers and parallel child operations. Cancellation and inspection
remain available while the execution guard is held.

Linux namespace init sends the payload's wait status over its private control
socket. The owner reports that status separately from the launcher's exit code,
and confirms both namespace-init and monitor exit before releasing ownership.
This preserves signal termination, including SIGKILL, without self-signaling
namespace init. Forced termination can have no recoverable payload exit status;
that is distinct from an ordinary command failure.

Codex's current attempt receipt records spawn intent, thread binding, turn intent,
turn acknowledgement, the response, and confirmed process-tree cleanup. Required
receipt writes precede the next protocol action. A completed response is exposed
only with cleanup evidence; an interrupted attempt with confirmed cleanup is
stopped and may be explicitly reconciled or retried on its retained thread.
Cancellation cannot replace an already durable completed result or allow later
protocol events to rewrite a stopped result. Unsupported receipt schemas and
unproven cleanup remain unknown. In particular, an abrupt owner crash before
cleanup is recorded can still require manual investigation: a missing PID or
released run lock is not cross-process proof of tree quiescence.

Continuation retains the private Codex home and native thread. Generated system
skill cache files may remain, but their instruction/discovery paths are disabled;
unapproved additional skill/configuration sources are rejected. Native tests
exercise a hostile cached skill on both an initial and a resumed request while
checking that preceding model inputs remain an exact prefix.
Codex's generated project-trust configuration is retained only when its parsed
contents contain project paths with `trust_level = "trusted"` and no other settings.
Project configuration files remain prohibited before native dispatch.
Native RUN preserves the inherited home environment for Git, SSH, and other native
tools; mediated turns use the private home. Preflight checks include explicit home
environment overrides so they cannot introduce an unchecked skill source.

CI installs the complete current Linux Codex distribution, including its matching
sandbox resources. Downloading only the standalone executable omitted Bubblewrap;
the older Ubuntu system package then exposed a native launcher compatibility
failure. Windows installation retains all packaged helpers, and restricted RUN
uses Codex's unelevated sandbox rather than leaving the backend disabled. Both
platforms keep the requested approval and filesystem policies.
The Windows native fixture follows Codex's own sandbox tests by placing its
isolated writable workspace outside `USERPROFILE/AppData`, which the restricted
token excludes, with inherited directory ACLs. Python's private temporary-directory
ACL is unsuitable for that native token. The requested write policy is unchanged.

The native suite also interrupts an actual Codex turn after its acknowledgement,
checks the durable stopped outcome after cleanup, and completes an explicitly
authorized retry on the same thread. These checks use the local Responses fixture
and do not measure authenticated model behavior or cache hits.

## Sources

- [Codex 0.155.1 release](https://github.com/openai/codex/releases/tag/rust-v0.155.1)
- [Current turn protocol](https://github.com/openai/codex/blob/be2951ea34f0d295ed0becf97079f92fa5f6950e/codex-rs/app-server-protocol/src/protocol/v2/turn.rs)
- [Current thread protocol](https://github.com/openai/codex/blob/be2951ea34f0d295ed0becf97079f92fa5f6950e/codex-rs/app-server-protocol/src/protocol/v2/thread.rs)
- [Current tool registration](https://github.com/openai/codex/blob/be2951ea34f0d295ed0becf97079f92fa5f6950e/codex-rs/core/src/tools/spec_plan.rs)
- [Current configuration resolution](https://github.com/openai/codex/blob/be2951ea34f0d295ed0becf97079f92fa5f6950e/codex-rs/core/src/config/mod.rs)
- [Linux PID namespace semantics](https://man7.org/linux/man-pages/man7/pid_namespaces.7.html)
- [Bubblewrap parent-death race](https://github.com/containers/bubblewrap/issues/633)
- [Linux cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html)
