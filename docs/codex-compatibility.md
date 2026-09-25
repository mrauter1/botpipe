# Codex compatibility

Botpipe uses the installed `codex app-server`, not `codex exec`. It has no pinned,
reviewed, maximum or accepted-version list. Model names also pass through.
Run `botpipe doctor` to check the installation that will execute your work.

For the official npm package, Botpipe resolves the launcher to its installed
native executable so disposal observes the app-server itself, including on
Windows. An incomplete or customized package launcher fails before dispatch;
configure the native executable directly in that case. Other custom commands
must run the server as the directly owned process.

## Required capabilities

| Capability | Requirement | Missing capability |
| --- | --- | --- |
| `thread/start`, `thread/resume`, `turn/start` | Every provider call | CapabilityError naming the method |
| Per-turn `sandboxPolicy` | Every provider call | CapabilityError before dispatch |
| `turn/interrupt` | Every provider call | CapabilityError before dispatch |
| `outputSchema` | Optional | Embed schema in prompt; validate and repair locally |
| `thread/backgroundTerminals/clean` | Native terminal cleanup when available | Fall back to process-group or Job cleanup |
| `thread/backgroundTerminals/list` | Confirming native recovery cleanup | Historical interrupted work stays `Unknown` |
| Tool-feature configuration | Calls with an explicit tool profile | CapabilityError before dispatch when the requested profile cannot be applied |
| Ambient MCP disablement | Read-only presets | Affected preset unavailable |

The probe reads the executable identity (resolved path, size and modification
time), version, generated app-server JSON schemas and reported feature inventory.
It caches capabilities in state and records the probe hash with each operation.
Executable changes trigger another probe. Corrupt cache data triggers probing,
not relaxed enforcement. The feature inventory comes from the installed Codex;
there is no maintained list of approved Codex releases. Unused schema item
versions do not veto the installation. A changed probe hash or derived execution
profile remains audit evidence rather than a durable replay-identity veto; a
capability actually required by the next dispatch is still enforced.

**Codex 0.156.0 is the earliest recorded measured reference for this rewrite.**
It is neither a minimum nor a claim about the current latest release. The CI
configuration installs the floating `@openai/codex@latest` tag and prints the
resolved version in each job, but the repository does not record that changing
version as a compatibility floor. Earlier versions are unverified and work only
if the capability probe accepts them; later versions are evaluated the same way.
A failed cross-version `thread/resume` raises `SessionError`, so a workflow can
choose a new session. Replayed operations do not require Codex.

Linux needs Codex's [Bubblewrap prerequisites](https://developers.openai.com/codex/concepts/sandboxing#prerequisites),
including Ubuntu's AppArmor profile where required. Contract CI installs those
prerequisites and checks the sandbox before running provider turns.

On native Windows, complete Codex's sandbox setup before calling Botpipe. Codex
recommends `[windows] sandbox = "elevated"`: its offline sandbox user is subject
to firewall restrictions. The `unelevated` fallback has weaker network isolation;
Botpipe inherits the selected Codex implementation's limits. See
[Codex's Windows sandbox documentation](https://developers.openai.com/codex/windows).
When the installed protocol exposes `windowsSandbox/readiness`, Botpipe checks it
before dispatch and reports incomplete or outdated setup. Botpipe never performs
administrator setup on the SDK user's behalf. Windows contract CI provisions the
elevated sandbox explicitly in its isolated Codex home.

Botpipe starts or resumes a durable thread in a temporary app-server for each
complete provider operation. That server remains subscribed across the
operation's validation and repair turns, then Botpipe disposes it before the
session is available for another operation. Sandbox policy is sent with each
turn. A later operation resumes the recorded thread and may apply a different
tool profile in its new server. Durable conversation history crosses this
boundary; yielded background terminals, child processes, and live tool handles
do not have a cross-operation survival guarantee.

Codex 0.156.1 holds an [exclusive cross-process writer lease](https://github.com/openai/codex/blob/rust-v0.156.1/codex-rs/rollout/src/writer_lock.rs)
for a loaded thread. Botpipe releases the session lock only after confirming
operation-scoped disposal (or explicit resolution), so it does not require a
live handoff primitive or broker writer ownership between app-server processes.
Because a different operation uses a new server, Botpipe also does not depend on
unsubscribe as a way to reconfigure an already loaded thread.

## Enforcement

Approval is always `never`. Presets use Codex read-only/no-network policy for
commands inside its sandbox; opted-in remote MCP servers and web tools remain
outside that filesystem guarantee. For an explicit allowlist, Botpipe disables
known, discovered tool-enabling feature flags, preserves unrelated and unknown
flags, and audits observed calls. Ambient MCP servers are disabled unless
explicitly named. If the installed protocol cannot express a required
restriction, Botpipe reports the missing capability before dispatch.

Some native core tools remain advertised even with optional features disabled.
The audit rejects an actual disallowed call, including planning and human-input
requests, and retains the event evidence; an empty advertised tool inventory is
not claimed. Audit detection cannot undo an effect already performed by a remote
tool, so nonrepeatable remote work should use `retry_safe=False`.

`full-access` inherits no Codex sandbox guarantee. Codex's unrestricted policy
cannot enforce network off, so full access also requires an explicit network
opt-in when that native limitation applies. A named remote MCP server can have
remote effects; filesystem read-only does not constrain that server.

Each complete provider operation owns an app-server process in a POSIX process
group or a Windows kill-on-close Job. The measured Codex behavior does not stop
on stdin EOF. Normal idle disposal therefore closes the transport, then stops
only the app-server parent: parent-directed `SIGINT` on POSIX or
`TerminateProcess` on Windows. Botpipe waits to confirm parent exit. This path
does not call `turn/interrupt`, clean background terminals, or terminate the
contained process tree. On Windows it clears kill-on-close before closing the
containment handle. Child survival is not guaranteed or carried as a Botpipe
contract.

Cancellation and timeout instead request `turn/interrupt` and use Codex's native
background-terminal cleanup when available: interrupt alone may leave those
terminals running. Botpipe captures still-attached descendant process groups
before cleanup and checks their identities before signalling.

Attempt preparation, dispatch authorization, native IDs, responses and cleanup
evidence are recorded in the owning run's ledger. A pre-ack attempt is `Stopped`
only when the ledger proves dispatch was not authorized or records completed,
verified local teardown. Native history marked failed, interrupted or cancelled
is `Stopped` only after cleanup and a bounded, paginated inventory proves empty.
The historical status or successful cleanup RPC alone is not proof. Missing
support, a nonempty inventory, timeout or inspection error yields `Unknown`.
Native `Completed` history can still be adopted when terminal items pass the
tool audit and an assistant message supplies the response.

A result made durable before normal disposal fails remains `Completed` and is
never redispatched. The separate uncertainty concerns shutdown. Botpipe blocks
that session from another operation until shutdown succeeds on retry or an
operator resolves the lifecycle uncertainty; it does not treat visible result
bytes as proof that the old process is gone.

A daemon already detached from the process tree is outside Botpipe's
containment. One operation owns the process being escalated; unrelated
operations use different app-server processes.

## Validation and release gate

The deterministic suite uses fake adapters and recorded app-server behavior,
without a Codex installation, model credentials or network access. Required CI
contract jobs install the then-current `@openai/codex@latest` on Linux, macOS and
Windows, record its version, and use a local Responses fixture to exercise the
protocol and sandbox. Pull requests, pushes to `main`, manual runs, and the
nightly schedule run these contracts against whatever version `latest` resolves
to at that time.

Local fixture evidence verifies transport and effects handling. It does not
establish authentication, a live model response, hosted tool behavior, or a
real cross-version resume. Those claims require credentialed smoke tests. Before
tagging 2.0.0, run `run`, `query`, and `generate` against a real model on each
supported platform and record the exact `codex --version`, `botpipe doctor`
output, preset inputs, and results. Until that evidence exists, describe 0.156.0
as the measured reference and the CI target as floating latest, not as a verified
minimum or verified current-latest release.
