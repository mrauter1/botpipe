# Codex compatibility

Botpipe uses the installed `codex app-server`, not `codex exec`. It has no pinned,
reviewed, maximum or accepted-version list. Model names also pass through.
Run `botpipe doctor` to check the installation that will execute your work.

## Required capabilities

| Capability | Requirement | Missing capability |
| --- | --- | --- |
| `thread/start`, `thread/resume`, `turn/start` | Every provider call | CapabilityError naming the method |
| Per-turn `sandboxPolicy` | Every provider call | CapabilityError before dispatch |
| `turn/interrupt` | Every provider call | CapabilityError before dispatch |
| `outputSchema` | Optional | Embed schema in prompt; validate and repair locally |
| `thread/unsubscribe` | Changing a loaded thread's configuration | CapabilityError before dispatch; unchanged calls still work |
| `thread/backgroundTerminals/clean` | Native terminal cleanup when available | Fall back to process-group or Job cleanup |
| Tool-feature configuration | Read-only presets | Affected preset unavailable |
| Ambient MCP disablement | Read-only presets | Affected preset unavailable |

The probe reads the executable identity (resolved path, size and modification
time), version, generated app-server JSON schemas and reported feature inventory.
It caches capabilities in state and records the probe hash with each operation.
Executable changes trigger another probe. Corrupt cache data triggers probing,
not relaxed enforcement. The feature inventory comes from the installed Codex;
there is no maintained list of approved Codex releases.

The earliest installation checked during this rewrite is **Codex 0.156.0**.
This is a measured compatibility reference, not a hard-coded minimum. Earlier
versions may work if they expose the required capabilities; they have not been
established by this rewrite's validation. A later release is accepted on its
capabilities. A failed cross-version `thread/resume` raises `SessionError`, so a
workflow can choose a new session. Replayed operations do not require Codex.

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

Codex keeps loaded threads subscribed and ignores configuration changes on that
resume path. When a session's profile changes, Botpipe unsubscribes it before
resuming the same thread so Codex reloads its configuration and conversation.

## Enforcement

Approval is always `never`. Presets use Codex read-only/no-network policy;
generation restricts configured tools and audits observed tool calls. Ambient
MCP servers are disabled unless explicitly named. If the installed protocol
cannot express a restriction, Botpipe reports the missing capability before
dispatch. It does not silently broaden the requested profile.

Some native core tools remain advertised even with optional features disabled.
Generation's audit rejects disallowed observed calls, including planning and
human-input requests; an empty advertised tool inventory is not claimed.

`full-access` inherits no Codex sandbox guarantee. Codex's unrestricted policy
cannot enforce network off, so full access also requires an explicit network
opt-in when that native limitation applies. A named remote MCP server can have
remote effects; filesystem read-only does not constrain that server.

The app-server process uses a POSIX process group or a Windows kill-on-close Job.
Cancellation requests `turn/interrupt` and uses Codex's native background-terminal
cleanup when available: interrupt alone intentionally leaves those terminals
running. Botpipe captures still-attached descendant process groups before cleanup
and checks their process identities before signalling them. After the configured
grace period, it closes the process tree before returning. A daemon already
detached from that tree is outside Botpipe's containment. Killing a shared app-server interrupts its other active
turns too; writable turns remain subject to reconciliation.

## Validation and release gate

The deterministic suite uses fake adapters and recorded app-server behavior,
without a Codex installation, model credentials or network access. Required CI
contract jobs install `@openai/codex@latest` on Linux, macOS and Windows and use
a local Responses fixture to exercise the protocol and sandbox. The nightly
schedule runs the same contracts to detect new-release incompatibility.

Local fixture evidence verifies transport and effects handling. It does not
establish authenticated model behavior. **Before tagging 2.0.0, run each preset
against a real model with credentials on each supported platform.** Record the
Codex version and doctor output alongside those release results.
